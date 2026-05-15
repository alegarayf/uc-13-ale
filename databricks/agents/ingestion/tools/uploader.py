"""
UC Volume uploader — source-agnostic file upload for the UC13 ingestion pipeline.

Responsibilities
----------------
- Accept FilePayload objects (raw bytes + metadata) and write them to a Unity Catalog
  Volume, preserving the original folder structure
- Switch transparently between two runtime modes:
    LOCAL      — uploads via Databricks Files REST API (authenticated with a PAT)
    DATABRICKS — writes directly to the Volume filesystem path using pathlib
- Provide a convenience helper (upload_from_directory) to seed the Volume from a
  local directory during early development

What this module does NOT do
-----------------------------
- No parsing, OCR, or text extraction
- No Delta table writes — files land in the Volume only
- No SharePoint / connector logic
- No credential management beyond reading env vars

Future integration
------------------
When connector.py has SharePoint credentials, the caller builds FilePayload objects
from FileMetadata and passes them straight to upload_batch — nothing here changes.
See upload_batch docstring for the exact integration pattern.
"""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment variables
# ---------------------------------------------------------------------------

_LOCAL_REQUIRED_ENV = ("DATABRICKS_HOST", "DATABRICKS_TOKEN", "UC_VOLUME_PATH")


def _env() -> tuple[str, str, str]:
    """Return (DATABRICKS_HOST, DATABRICKS_TOKEN, UC_VOLUME_PATH).

    Only validated when running locally — inside Databricks these env vars may
    not be set and the runtime uses filesystem paths directly instead.
    """
    missing = [k for k in _LOCAL_REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}. "
            "Ensure .env is loaded before calling any uploader function."
        )
    return (
        os.environ["DATABRICKS_HOST"].rstrip("/"),
        os.environ["DATABRICKS_TOKEN"],
        os.environ["UC_VOLUME_PATH"].rstrip("/"),
    )


def _uc_volume_path() -> str:
    """Return UC_VOLUME_PATH regardless of runtime mode (always required)."""
    val = os.environ.get("UC_VOLUME_PATH", "").rstrip("/")
    if not val:
        raise ValueError(
            "UC_VOLUME_PATH environment variable is not set. "
            "Set it to the Unity Catalog Volume path, e.g. /Volumes/uc13/ingestion/raw_files"
        )
    return val


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class FilePayload:
    file_name: str
    relative_path: str   # path relative to source root; mirrors structure in Volume
    content: bytes       # raw file bytes — source-agnostic
    size_bytes: int


@dataclass
class UploadResult:
    file_name: str
    relative_path: str
    volume_path: str
    size_bytes: int
    status: str           # "success" or "failed"
    error_msg: str | None


@dataclass
class UploadSummary:
    total_files: int
    successful: int
    failed: int
    results: list[UploadResult] = field(default_factory=list)
    duration_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Runtime detection
# ---------------------------------------------------------------------------

_ALLOWED_EXTENSIONS = {
    ".pdf", ".xlsx", ".xls", ".docx", ".doc",
    ".pptx", ".ppt", ".csv", ".txt",
}


def _is_databricks_env() -> bool:
    """Return True when running inside a Databricks cluster/notebook."""
    return bool(os.environ.get("DATABRICKS_RUNTIME_VERSION"))


# ---------------------------------------------------------------------------
# Core upload
# ---------------------------------------------------------------------------


def upload_file(payload: FilePayload) -> UploadResult:
    """Write a single FilePayload to the Unity Catalog Volume.

    LOCAL mode  — HTTP PUT to the Databricks Files API.
    DATABRICKS  — direct filesystem write to the Volume mount path.

    Returns an UploadResult; never raises.
    """
    volume_path = _uc_volume_path()

    # Normalise relative_path: strip leading slashes so path joins work cleanly.
    rel = payload.relative_path.lstrip("/")
    dest_volume_path = f"{volume_path}/{rel}"

    try:
        if _is_databricks_env():
            dest = Path(dest_volume_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(payload.content)
            logger.debug("DATABRICKS write: %s", dest_volume_path)
        else:
            host, token, _ = _env()
            url = f"{host}/api/2.0/fs/files{dest_volume_path}"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/octet-stream",
            }
            resp = requests.put(url, headers=headers, data=payload.content, timeout=120)
            resp.raise_for_status()
            logger.debug("LOCAL upload: %s → %s", payload.file_name, dest_volume_path)

        return UploadResult(
            file_name=payload.file_name,
            relative_path=payload.relative_path,
            volume_path=dest_volume_path,
            size_bytes=payload.size_bytes,
            status="success",
            error_msg=None,
        )

    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to upload %s: %s", payload.file_name, exc)
        return UploadResult(
            file_name=payload.file_name,
            relative_path=payload.relative_path,
            volume_path=dest_volume_path,
            size_bytes=payload.size_bytes,
            status="failed",
            error_msg=str(exc),
        )


# ---------------------------------------------------------------------------
# Batch upload
# ---------------------------------------------------------------------------


def upload_batch(
    payloads: list[FilePayload],
    max_workers: int = 5,
) -> UploadSummary:
    """Upload a list of FilePayload objects to the UC Volume in parallel.

    Never raises — all failures are captured in the returned UploadSummary.

    Future integration with connector.py
    -------------------------------------
    When connector.py has SharePoint credentials, wire it up like this::

        from connector import list_files, download_file, FileMetadata
        from uploader import FilePayload, upload_batch

        files: list[FileMetadata] = list_files()
        payloads = [
            FilePayload(
                file_name=f.name,
                relative_path=f.relative_path,
                content=download_file(f.item_id),
                size_bytes=f.size_bytes,
            )
            for f in files
        ]
        summary = upload_batch(payloads)

    No changes to uploader.py will be needed at that point.
    """
    started = time.monotonic()
    results: list[UploadResult] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(upload_file, p): p for p in payloads}
        for future in as_completed(futures):
            payload = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001
                # upload_file should never raise, but guard defensively.
                logger.error("Unexpected error for %s: %s", payload.file_name, exc)
                result = UploadResult(
                    file_name=payload.file_name,
                    relative_path=payload.relative_path,
                    volume_path="",
                    size_bytes=payload.size_bytes,
                    status="failed",
                    error_msg=str(exc),
                )
            results.append(result)

    succeeded = sum(1 for r in results if r.status == "success")
    return UploadSummary(
        total_files=len(results),
        successful=succeeded,
        failed=len(results) - succeeded,
        results=results,
        duration_seconds=time.monotonic() - started,
    )


# ---------------------------------------------------------------------------
# Directory convenience helper (LOCAL development only)
# ---------------------------------------------------------------------------


def upload_from_directory(local_dir: str) -> UploadSummary:
    """Walk *local_dir* recursively and upload every allowed file to the UC Volume.

    - Hidden files (names starting with ``.``) are skipped.
    - Only files with extensions in ``_ALLOWED_EXTENSIONS`` are included.
    - The relative path from *local_dir* is preserved verbatim in the Volume.

    This function is a convenience shim for today's local-first workflow.
    Once connector.py streams FilePayload objects directly, callers can bypass
    this function and call upload_batch instead.
    """
    root = Path(local_dir).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Source directory does not exist: {root}")

    payloads: list[FilePayload] = []
    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.name.startswith("."):
            continue
        if file_path.suffix.lower() not in _ALLOWED_EXTENSIONS:
            logger.debug("Skipping %s (extension not allowed)", file_path.name)
            continue

        rel = file_path.relative_to(root)
        content = file_path.read_bytes()
        payloads.append(
            FilePayload(
                file_name=file_path.name,
                relative_path=str(rel),
                content=content,
                size_bytes=len(content),
            )
        )

    logger.info(
        "Found %d uploadable files in %s", len(payloads), local_dir
    )
    return upload_batch(payloads)


# ---------------------------------------------------------------------------
# Volume listing
# ---------------------------------------------------------------------------


def list_volume_files(prefix: str = "") -> list[str]:
    """Return the paths of files already stored in UC_VOLUME_PATH/prefix.

    LOCAL mode  — Databricks Files API GET.
    DATABRICKS  — os.walk on the Volume filesystem path.

    Useful for verifying uploads or skipping files already present.
    """
    volume_path = _uc_volume_path()
    base = f"{volume_path}/{prefix.lstrip('/')}" if prefix else volume_path

    if _is_databricks_env():
        found: list[str] = []
        for dirpath, _, filenames in os.walk(base):
            for fname in filenames:
                found.append(os.path.join(dirpath, fname))
        return found

    host, token, _ = _env()
    url = f"{host}/api/2.0/fs/files{base}"
    headers = {"Authorization": f"Bearer {token}"}

    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()

    data = resp.json()
    # The Files API returns {"files": [{"path": "...", ...}, ...]}
    return [entry["path"] for entry in data.get("files", [])]


# ---------------------------------------------------------------------------
# Local smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv

    load_dotenv()

    local_dir = sys.argv[1] if len(sys.argv) > 1 else "./tmp/dataroom"

    print("=== Testing uploader ===")

    print("\nFiles currently in Volume:")
    existing = list_volume_files()
    if existing:
        for f in existing:
            print(f"  {f}")
    else:
        print("  (empty)")

    print(f"\nUploading files from {local_dir}...")
    summary = upload_from_directory(local_dir)

    print("\n--- Upload summary ---")
    print(f"Total:      {summary.total_files}")
    print(f"Successful: {summary.successful}")
    print(f"Failed:     {summary.failed}")
    print(f"Duration:   {summary.duration_seconds:.1f}s")
    for r in summary.results:
        if r.status == "success":
            print(f"  ✓ {r.file_name} -> {r.volume_path}")
        else:
            print(f"  ✗ {r.file_name}: {r.error_msg}")
