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

_LOCAL_REQUIRED_ENV = (
    "DATABRICKS_HOST",
    "DATABRICKS_TOKEN",
    "UC_VOLUME_PATH",
    "SP_COMPANY_NAME",
)


def _env() -> tuple[str, str, str, str]:
    """Return (DATABRICKS_HOST, DATABRICKS_TOKEN, UC_VOLUME_PATH, SP_COMPANY_NAME).

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
        os.environ["SP_COMPANY_NAME"],
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


def get_volume_company_path() -> str:
    """Return the Volume path scoped to the current company.

    Constructed as: {UC_VOLUME_PATH}/{SP_COMPANY_NAME}
    Example: /Volumes/uc13/ingestion/raw_files/Elder Care

    Each company's files are isolated under their own subfolder in the Volume,
    making it safe to process multiple companies without cross-contamination.
    """
    volume_path = _uc_volume_path()
    company_name = os.environ.get("SP_COMPANY_NAME", "").strip()
    if not company_name:
        raise ValueError(
            "SP_COMPANY_NAME environment variable is not set. "
            "Set it to the company name as it appears in SharePoint (e.g. 'Elder Care')."
        )
    return f"{volume_path}/{company_name}"


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


def _uc_makedirs(path: Path) -> None:
    """Create *path* and all missing parents, safe for UC Volume FUSE mounts.

    Standard ``Path.mkdir(parents=True)`` fails with ``[Errno 95] Operation not
    supported`` when it walks up to the Volume mount point itself
    (``/Volumes/<catalog>/<schema>``), because the FUSE layer returns
    ``EOPNOTSUPP`` instead of ``EEXIST``.  This helper finds the deepest
    already-existing ancestor and creates each missing sub-directory one level
    at a time, skipping the mount-point level where the error occurs.
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
        return
    except OSError as exc:
        if exc.errno != 95:
            raise

    # Walk upward to find the deepest path that already exists.
    to_create: list[Path] = []
    current = path
    while current != current.parent:
        if current.exists():
            break
        to_create.append(current)
        current = current.parent

    # Create missing directories from shallowest to deepest.
    for directory in reversed(to_create):
        try:
            directory.mkdir(exist_ok=True)
        except OSError as exc:
            if exc.errno != 95:
                raise


def upload_file(payload: FilePayload) -> UploadResult:
    """Write a single FilePayload to the Unity Catalog Volume under the company subfolder.

    Destination path: {UC_VOLUME_PATH}/{SP_COMPANY_NAME}/{payload.relative_path}

    LOCAL mode  — HTTP PUT to the Databricks Files API.
    DATABRICKS  — direct filesystem write to the Volume mount path.

    Returns an UploadResult; never raises.
    """
    company_volume_path = get_volume_company_path()

    # Normalise relative_path: strip leading slashes so path joins work cleanly.
    rel = payload.relative_path.lstrip("/")
    dest_volume_path = f"{company_volume_path}/{rel}"

    try:
        if _is_databricks_env():
            dest = Path(dest_volume_path)
            _uc_makedirs(dest.parent)
            dest.write_bytes(payload.content)
            logger.debug("DATABRICKS write: %s", dest_volume_path)
        else:
            host, token, _, _ = _env()
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

    Files are stored under UC_VOLUME_PATH/{SP_COMPANY_NAME}/ to isolate companies.
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


def upload_from_directory(local_dir: str, batch_size: int = 50) -> UploadSummary:
    """Walk *local_dir* recursively and upload every allowed file to the UC Volume.

    Files are processed in batches of *batch_size* to bound peak memory usage.
    Each batch is read into memory, uploaded, then freed before the next batch
    is loaded — safe for large data rooms (1 000+ files).

    - Hidden files (names starting with ``.``) are skipped.
    - Only files with extensions in ``_ALLOWED_EXTENSIONS`` are included.
    - The relative path from *local_dir* is preserved verbatim in the Volume.
    """
    root = Path(local_dir).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Source directory does not exist: {root}")

    # Collect file paths first (metadata only — no bytes loaded yet).
    file_paths = [
        fp for fp in root.rglob("*")
        if fp.is_file()
        and not fp.name.startswith(".")
        and fp.suffix.lower() in _ALLOWED_EXTENSIONS
    ]
    logger.info("Found %d uploadable files in %s", len(file_paths), local_dir)

    all_results: list[UploadResult] = []
    started = time.monotonic()

    for batch_start in range(0, len(file_paths), batch_size):
        batch_paths = file_paths[batch_start : batch_start + batch_size]
        payloads: list[FilePayload] = []

        for file_path in batch_paths:
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

        batch_summary = upload_batch(payloads)
        all_results.extend(batch_summary.results)

        batch_end = min(batch_start + batch_size, len(file_paths))
        logger.info(
            "Uploaded batch %d-%d / %d",
            batch_start + 1, batch_end, len(file_paths),
        )

        # Explicitly release batch memory before loading the next one.
        del payloads

    succeeded = sum(1 for r in all_results if r.status == "success")
    return UploadSummary(
        total_files=len(all_results),
        successful=succeeded,
        failed=len(all_results) - succeeded,
        results=all_results,
        duration_seconds=time.monotonic() - started,
    )


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

    host, token, _, _ = _env()
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

    company_vol_path = get_volume_company_path()
    company_name = os.environ.get("SP_COMPANY_NAME", "")

    print("=== Testing uploader ===")
    print(f"Company:      {company_name}")
    print(f"Volume path:  {company_vol_path}/")

    print("\nFiles currently in Volume:")
    existing = list_volume_files(prefix=company_name)
    if existing:
        for f in existing:
            print(f"  {f}")
    else:
        print("  (empty)")

    print(f"\nUploading {company_name} files to {company_vol_path}/...")
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
