"""
SharePoint connector — device code flow (temporary until Azure AD app registration).

Authentication will be swapped to client credentials flow once we have a registered
app. The public interface (function signatures and return types) is stable and will
not change at that time.

Responsibilities
----------------
- Authenticate against Microsoft Graph via MSAL device code flow
- List files under a SharePoint folder (recursively, paginated)
- Download files individually or in parallel, preserving folder structure
- NO parsing, transformation, or text extraction of file contents
"""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import msal
import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment variables — validated lazily on first use
# ---------------------------------------------------------------------------

_REQUIRED_ENV = ("SP_TENANT_ID", "SP_SITE_URL", "SP_FOLDER_PATH")

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _env() -> tuple[str, str, str]:
    """Return (SP_TENANT_ID, SP_SITE_URL, SP_FOLDER_PATH), raising early if any are absent."""
    missing = [k for k in _REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}. "
            "Ensure .env is loaded (e.g. via python-dotenv) before calling any connector function."
        )
    return os.environ["SP_TENANT_ID"], os.environ["SP_SITE_URL"], os.environ["SP_FOLDER_PATH"]
SCOPES = [
    "https://graph.microsoft.com/Sites.Read.All",
    "https://graph.microsoft.com/Files.Read.All",
]

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class FileMetadata:
    item_id: str
    name: str
    file_type: str
    size_bytes: int
    relative_path: str
    last_modified: str


# ---------------------------------------------------------------------------
# Module-level MSAL app — created once, token cached in memory
# ---------------------------------------------------------------------------

_msal_app: msal.PublicClientApplication | None = None
_cached_token: str | None = None


def _get_msal_app() -> msal.PublicClientApplication:
    global _msal_app
    if _msal_app is None:
        tenant_id, _, _ = _env()
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        # "9bc3ab49-b65d-410a-85ad-de819febfddc" is the well-known Microsoft
        # Graph Explorer client ID, acceptable for device-code / delegated flows.
        _msal_app = msal.PublicClientApplication(
            client_id="9bc3ab49-b65d-410a-85ad-de819febfddc",
            authority=authority,
        )
    return _msal_app


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def authenticate() -> str:
    """
    Return a valid Microsoft Graph bearer token.

    On the first call (or after token expiry) this triggers device code flow
    and prints instructions for the user. Subsequent calls within the same
    process reuse the cached token.
    """
    global _cached_token

    app = _get_msal_app()

    # Try silent acquisition from MSAL's in-memory token cache first.
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            _cached_token = result["access_token"]
            logger.info("Authentication successful (token from cache)")
            return _cached_token

    # Fall back to interactive device code flow.
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(
            f"Failed to create device flow: {flow.get('error_description', flow)}"
        )

    # This message must always be visible to the user.
    print("\n" + flow["message"])
    print("Waiting for authentication…\n")

    result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        raise RuntimeError(
            f"Authentication failed: {result.get('error_description', result)}"
        )

    _cached_token = result["access_token"]
    logger.info("Authentication successful")
    return _cached_token


# ---------------------------------------------------------------------------
# Site resolution
# ---------------------------------------------------------------------------


def get_site_id(token: str) -> str:
    """
    Resolve the SharePoint site ID from SP_SITE_URL via the Graph API.

    SP_SITE_URL is expected to be the full HTTPS URL, e.g.:
        https://rallydaypartnerscom.sharepoint.com/teams/RallydayPartnersExternal
    """
    from urllib.parse import urlparse

    _, sp_site_url, _ = _env()
    parsed = urlparse(sp_site_url)
    hostname = parsed.netloc          # e.g. rallydaypartnerscom.sharepoint.com
    site_path = parsed.path.lstrip("/")  # e.g. teams/RallydayPartnersExternal

    url = f"{GRAPH_BASE}/sites/{hostname}:{site_path}"
    headers = {"Authorization": f"Bearer {token}"}

    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()

    site_id: str = resp.json()["id"]
    logger.debug("Resolved site_id=%s", site_id)
    return site_id


# ---------------------------------------------------------------------------
# File listing
# ---------------------------------------------------------------------------


def list_files(folder_path: str | None = None) -> list[FileMetadata]:
    """
    Recursively list all files under *folder_path* (defaults to SP_FOLDER_PATH).

    Subfolders are traversed but not included in the returned list — only
    leaf files are returned. Pagination via ``@odata.nextLink`` is handled
    automatically.
    """
    _, _, sp_folder_path = _env()
    token = authenticate()
    site_id = get_site_id(token)
    root_path = (folder_path or sp_folder_path).rstrip("/")

    headers = {"Authorization": f"Bearer {token}"}
    results: list[FileMetadata] = []

    def _collect(path: str, relative_base: str) -> None:
        url = f"{GRAPH_BASE}/sites/{site_id}/drive/root:{path}:/children"
        while url:
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("value", []):
                if "folder" in item:
                    child_relative = (
                        f"{relative_base}/{item['name']}" if relative_base else item["name"]
                    )
                    _collect(f"{path}/{item['name']}", child_relative)
                elif "file" in item:
                    name: str = item["name"]
                    relative_path = f"{relative_base}/{name}" if relative_base else name
                    ext = Path(name).suffix.lstrip(".").lower()
                    results.append(
                        FileMetadata(
                            item_id=item["id"],
                            name=name,
                            file_type=ext,
                            size_bytes=item.get("size", 0),
                            relative_path=relative_path,
                            last_modified=item.get("lastModifiedDateTime", ""),
                        )
                    )

            url = data.get("@odata.nextLink")

    _collect(root_path, "")
    logger.info("Listed %d files under %s", len(results), root_path)
    return results


# ---------------------------------------------------------------------------
# Single-file download
# ---------------------------------------------------------------------------

_MAX_RETRIES = 3


def download_file(
    item_id: str,
    file_name: str,
    destination_path: str,
) -> str | None:
    """
    Download a single file by Graph item ID and save it to *destination_path/file_name*.

    Retries up to 3 times with exponential backoff on network errors.
    Returns the full saved path on success, or ``None`` if all retries fail.
    """
    token = authenticate()
    site_id = get_site_id(token)

    dest_dir = Path(destination_path)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / file_name

    url = f"{GRAPH_BASE}/sites/{site_id}/drive/items/{item_id}/content"
    headers = {"Authorization": f"Bearer {token}"}

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            with requests.get(url, headers=headers, stream=True, timeout=60) as resp:
                resp.raise_for_status()
                with open(dest_file, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=8192):
                        fh.write(chunk)
            logger.debug("Downloaded %s → %s", file_name, dest_file)
            return str(dest_file)
        except requests.RequestException as exc:
            if attempt == _MAX_RETRIES:
                logger.error(
                    "Failed to download %s after %d attempts: %s",
                    file_name,
                    _MAX_RETRIES,
                    exc,
                )
                return None
            wait = 2 ** attempt
            logger.warning(
                "Download attempt %d/%d failed for %s (%s). Retrying in %ds…",
                attempt,
                _MAX_RETRIES,
                file_name,
                exc,
                wait,
            )
            time.sleep(wait)

    return None  # unreachable, but satisfies type checker


# ---------------------------------------------------------------------------
# Batch download
# ---------------------------------------------------------------------------


def download_batch(
    files: list[FileMetadata],
    destination_root: str,
    max_workers: int = 5,
) -> dict[str, str | None]:
    """
    Download *files* in parallel, preserving their ``relative_path`` structure
    under *destination_root*.

    Returns a mapping of ``item_id → saved_path`` (``None`` for failures).
    """
    results: dict[str, str | None] = {}

    def _download_one(meta: FileMetadata) -> tuple[str, str | None]:
        # Reconstruct the subdirectory from relative_path, excluding the
        # filename itself so we don't create a directory named like the file.
        rel = Path(meta.relative_path)
        subdir = rel.parent  # may be "." for files directly in root folder
        dest_dir = (
            Path(destination_root) / subdir
            if str(subdir) != "."
            else Path(destination_root)
        )
        saved = download_file(meta.item_id, meta.name, str(dest_dir))
        return meta.item_id, saved

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_download_one, f): f for f in files}
        for future in as_completed(futures):
            meta = futures[future]
            try:
                item_id, saved_path = future.result()
                results[item_id] = saved_path
                if saved_path is None:
                    logger.error("Download failed for %s (%s)", meta.name, meta.item_id)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Unexpected error downloading %s: %s", meta.name, exc
                )
                results[meta.item_id] = None

    return results


# ---------------------------------------------------------------------------
# Convenience all-in-one
# ---------------------------------------------------------------------------


def download_all(destination_root: str) -> dict[str, str | None]:
    """
    List all files under SP_FOLDER_PATH and download them to *destination_root*.

    Prints a human-readable summary when done.
    """
    files = list_files()
    results = download_batch(files, destination_root=destination_root)

    total = len(results)
    succeeded = sum(1 for p in results.values() if p is not None)
    failed = total - succeeded

    print(f"\n=== Download summary ===")
    print(f"  Total files:  {total}")
    print(f"  Successful:   {succeeded}")
    print(f"  Failed:       {failed}")

    return results


# ---------------------------------------------------------------------------
# Local smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()  # picks up databricks/.env when run from the databricks/ directory

    LOCAL_DEST = "./tmp/dataroom"

    print("=== Testing SharePoint connector ===")
    files = list_files()
    print(f"Found {len(files)} files")

    print(f"\nDownloading first 3 files to {LOCAL_DEST}...")
    results = download_batch(files[:3], destination_root=LOCAL_DEST)
    for item_id, path in results.items():
        if path:
            print(f"  ✓ Saved: {path}")
        else:
            print(f"  ✗ Failed: {item_id}")
