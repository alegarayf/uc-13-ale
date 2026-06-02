"""
SharePoint connector — client credentials flow (MSAL ConfidentialClientApplication).

Authenticates silently using an Azure AD app registration (SP_CLIENT_ID /
SP_CLIENT_SECRET). No interactive prompt is required; the token is acquired
and cached in memory for the lifetime of the process.

Responsibilities
----------------
- Authenticate against Microsoft Graph via MSAL client credentials flow
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

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# ---------------------------------------------------------------------------
# Secret / env helpers — Databricks-first, .env fallback for local dev
# ---------------------------------------------------------------------------

def _get_dbutils():
    """Return the Databricks dbutils object from any execution context."""
    try:
        return dbutils  # noqa: F821
    except NameError:
        pass
    try:
        import IPython
        user_ns = IPython.get_ipython().user_ns
        if "dbutils" in user_ns:
            return user_ns["dbutils"]
    except Exception:
        pass
    return None


def _load_dotenv_if_local():
    if _get_dbutils() is None:
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

_load_dotenv_if_local()


def _get_secret(key: str) -> str:
    """Read a secret from the Databricks 'uc13' scope, falling back to os.environ / .env."""
    dbu = _get_dbutils()
    if dbu is not None:
        try:
            return dbu.secrets.get("uc13", key)
        except Exception:
            pass
    value = os.environ.get(key.upper()) or os.environ.get(key.lower())
    if not value:
        raise RuntimeError(
            f"Secret '{key}' not found. "
            "On Databricks: add it to the 'uc13' secrets scope. "
            "Locally: set it in your .env file or export as an env var."
        )
    return value


# ---------------------------------------------------------------------------
# Credential accessor — validated lazily on first use
# ---------------------------------------------------------------------------

def _env() -> tuple[str, str, str, str, str, str]:
    """Return (tenant_id, client_id, client_secret, site_url, folder_path, company_name).

    Reads from Databricks secrets scope 'uc13' when running on Databricks,
    otherwise falls back to environment variables / .env file.
    SP_COMPANY_NAME defaults to '' — validate it explicitly via get_company_folder_path().
    """
    return (
        _get_secret("sp_tenant_id"),
        _get_secret("sp_client_id"),
        _get_secret("sp_client_secret"),
        _get_secret("sp_site_url"),
        _get_secret("sp_folder_path"),
        os.environ.get("sp_company_name") or os.environ.get("SP_COMPANY_NAME", ""),
    )


def get_company_folder_path() -> str:
    """Return the drive-relative path scoped to the current company.

    Constructed as: {SP_FOLDER_PATH}/Example Data Room/{SP_COMPANY_NAME}
    Example: /Nimble Gravity UC13/Example Data Room/Elder Care
    """
    _, _, _, _, folder_path, company_name = _env()
    return f"{folder_path.rstrip('/')}/Example Data Room/{company_name}"


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

_msal_app: msal.ConfidentialClientApplication | None = None


def _get_msal_app() -> msal.ConfidentialClientApplication:
    global _msal_app
    if _msal_app is None:
        tenant_id, client_id, client_secret, _, _, _ = _env()
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        _msal_app = msal.ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=authority,
        )
    return _msal_app


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def authenticate() -> str:
    """
    Return a valid Microsoft Graph bearer token using client credentials flow.

    Fully silent — no interactive prompt. MSAL's in-memory cache is used so
    the token is only fetched once per process (refreshed automatically when
    it expires).
    """
    app = _get_msal_app()

    # .default scope instructs AAD to issue a token for all app-level
    # permissions granted to the service principal in the portal.
    result = app.acquire_token_for_client(
        scopes=["https://graph.microsoft.com/.default"]
    )

    if "access_token" not in result:
        raise RuntimeError(
            f"Authentication failed: {result.get('error_description', result)}"
        )

    logger.info("Authentication successful")
    return result["access_token"]


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

    _, _, _, sp_site_url, _, _ = _env()
    parsed = urlparse(sp_site_url)
    hostname = parsed.netloc   # e.g. rallydaypartnerscom.sharepoint.com
    site_path = parsed.path    # e.g. /teams/RallydayPartnersExternal — keep leading slash

    # Graph API colon-path syntax: /sites/{hostname}:/{path}
    # The leading slash on site_path satisfies the required colon+slash separator.
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

import re as _re

# Strips version/date suffixes from file stems before grouping duplicates.
# Matches patterns like: vSHARE_5.29.25, v5.30.25, 2025-June-13, _final,
# _UPLOAD, _vF, v1, v2, trailing date strings, etc.
_VERSION_SUFFIX_RE = _re.compile(
    r"[-_\s]*(v\w+|v\d[\d.]*|\d{4}[-_]\w+[-_]\d+|final|upload)+",
    _re.IGNORECASE,
)


def _base_name(file_name: str) -> str:
    """Return the version-stripped stem + lowercased extension for dedup grouping."""
    stem = Path(file_name).stem
    ext = Path(file_name).suffix.lower()
    base = _VERSION_SUFFIX_RE.sub("", stem).strip()
    return f"{base}{ext}"


def _deduplicate(files: list[FileMetadata]) -> list[FileMetadata]:
    """Within each folder+basename group, keep the most recently modified file.

    The dedup key is ``"{folder}/{base_name}"`` so that files with the same
    name in different folders (e.g. monthly payroll PDFs all named
    ``2023_01.pdf``) are treated as distinct documents and never collapsed.
    Only true version duplicates — same base name, same folder, different
    version suffix — are deduplicated.
    """
    groups: dict[str, list[FileMetadata]] = {}
    for f in files:
        folder = str(Path(f.relative_path).parent)
        key = f"{folder}|{_base_name(f.name)}"
        groups.setdefault(key, []).append(f)

    kept: list[FileMetadata] = []
    for group in groups.values():
        if len(group) == 1:
            kept.append(group[0])
            continue
        # Sort descending by last_modified (ISO 8601 strings sort lexicographically).
        group.sort(key=lambda f: f.last_modified, reverse=True)
        winner, *dupes = group
        logger.warning(
            "Keeping %s (most recent), skipping %d older version(s): %s",
            winner.name,
            len(dupes),
            [d.name for d in dupes],
        )
        kept.append(winner)

    return kept


def list_companies() -> list[str]:
    """Return a sorted list of company folder names under the Example Data Room.

    Reads the immediate subfolders of ``{SP_FOLDER_PATH}/Example Data Room``
    from SharePoint — no recursion, no file downloads.  Use this to discover
    which companies are available before setting SP_COMPANY_NAME.

    Example::

        companies = list_companies()
        # ['Clearsulting', 'Elder Care', 'GKF', 'SPG']
    """
    token = authenticate()
    site_id = get_site_id(token)
    _, _, _, _, sp_folder_path, _ = _env()

    base_path = f"{sp_folder_path.rstrip('/')}/Example Data Room"
    url = f"{GRAPH_BASE}/sites/{site_id}/drive/root:{base_path}:/children"
    headers = {"Authorization": f"Bearer {token}"}

    companies: list[str] = []
    while url:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("value", []):
            if "folder" in item:
                companies.append(item["name"])
        url = data.get("@odata.nextLink")

    return sorted(companies)


def list_files(folder_path: str | None = None) -> list[FileMetadata]:
    """Recursively list all files under *folder_path*, deduplicated by version.

    If *folder_path* is ``None``, defaults to the company-scoped path returned
    by :func:`get_company_folder_path` (i.e. SP_FOLDER_PATH/Example Data Room/SP_COMPANY_NAME).

    *folder_path* must be drive-relative (relative to "Shared Documents/"), NOT
    the full server-relative SharePoint URL.  Example::

        correct:   /Nimble Gravity UC13/Example Data Room/Elder Care
        incorrect: /teams/RallydayPartnersExternal/Shared Documents/…

    Subfolders are traversed but not returned — only leaf files are returned.
    Pagination via ``@odata.nextLink`` is handled automatically.
    Files that appear to be older versions of the same document (matched by
    a version-suffix regex) are deduplicated: only the most recently modified
    copy is kept.
    """
    token = authenticate()
    site_id = get_site_id(token)
    root_path = (folder_path or get_company_folder_path()).rstrip("/")

    headers = {"Authorization": f"Bearer {token}"}
    raw: list[FileMetadata] = []

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
                    raw.append(
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
    logger.info("Found %d files (pre-dedup) under %s", len(raw), root_path)

    results = _deduplicate(raw)
    skipped = len(raw) - len(results)
    logger.info(
        "After deduplication: %d files kept, %d older version(s) skipped",
        len(results),
        skipped,
    )
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
    import logging as _logging

    _logging.basicConfig(level=_logging.WARNING)  # surface dedup warnings to console

    from dotenv import load_dotenv

    # In Databricks, set env vars from secrets before running:
    # import os
    # os.environ["SP_CLIENT_ID"] = dbutils.secrets.get("uc13", "sp_client_id")
    # os.environ["SP_CLIENT_SECRET"] = dbutils.secrets.get("uc13", "sp_client_secret")
    # os.environ["SP_TENANT_ID"] = dbutils.secrets.get("uc13", "sp_tenant_id")
    # os.environ["SP_SITE_URL"] = dbutils.secrets.get("uc13", "sp_site_url")
    # os.environ["SP_FOLDER_PATH"] = dbutils.secrets.get("uc13", "sp_folder_path")
    # os.environ["SP_COMPANY_NAME"] = dbutils.secrets.get("uc13", "sp_company_name")
    load_dotenv()  # locally: picks up databricks/.env when run from the databricks/ directory

    LOCAL_DEST = "./tmp/dataroom"

    company_path = get_company_folder_path()
    print("=== Testing SharePoint connector ===")
    print(f"Company folder: {company_path}")

    all_files = list_files()
    dedup_count = len(all_files)
    print(f"\nFound {dedup_count} files after deduplication")

    print(f"\nDownloading first 3 files to {LOCAL_DEST}...")
    results = download_batch(all_files[:3], destination_root=LOCAL_DEST)
    for item_id, path in results.items():
        if path:
            print(f"  ✓ Saved: {path}")
        else:
            print(f"  ✗ Failed: {item_id}")
