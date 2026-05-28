"""
01_download_upload.py — Phase 1: SharePoint ingestion into UC Volume.

Downloads files for a given company from SharePoint, applies Priority Tier
detection based on filename and folder signals, uploads the files to the
Unity Catalog Volume under the company subfolder, and writes an upload log
Delta table that the classifier uses as its initial priority signal.

Phase 1 output:
  - Files in /Volumes/uc13/ingestion/raw_files/{company_name}/
  - Table uc13.ingestion.upload_log

Dependencies:
  - agents/ingestion/tools/connector.py
  - agents/ingestion/tools/uploader.py
  - Secrets scope "uc13": sp_tenant_id, sp_client_id, sp_client_secret,
    sp_site_url, sp_folder_path
  - Job parameters: sp_company_name, catalog, schema
"""

import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Secrets / params helpers
# ---------------------------------------------------------------------------

def _get_dbutils():
    """Return the Databricks dbutils object from any execution context.

    Works whether the code runs directly in a notebook cell or is called from
    an imported module (where dbutils is not a direct global but is reachable
    via the IPython user namespace injected by Databricks).
    """
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


def get_secret(key: str) -> str:
    _dbutils = _get_dbutils()
    if _dbutils is not None:
        try:
            return _dbutils.secrets.get("uc13", key)
        except Exception:
            pass
    value = os.environ.get(key)
    if value is None:
        raise RuntimeError(
            f"Secret '{key}' not found. "
            "On Databricks: add it to the 'uc13' secrets scope. "
            "Locally: add it to your .env file or export it as an env var."
        )
    return value


def get_param(key: str, default: str = None) -> str:
    _dbutils = _get_dbutils()
    if _dbutils is not None:
        try:
            value = _dbutils.widgets.get(key)
            if value:
                return value
        except Exception:
            pass
    value = os.environ.get(key, default)
    if value is None:
        raise RuntimeError(
            f"Parameter '{key}' not found. "
            "On Databricks: add it as a job task parameter. "
            "Locally: add it to your .env file or export it as an env var."
        )
    return value


# ---------------------------------------------------------------------------
# Repo root resolver
# ---------------------------------------------------------------------------

def get_current_path():
    try:
        notebook_path = (
            dbutils.notebook.entry_point  # noqa: F821
            .getDbutils()
            .notebook()
            .getContext()
            .notebookPath()
            .get()
        )
        return Path("/Workspace") / notebook_path.lstrip("/")
    except Exception:
        return Path(os.getcwd())


def find_repo_root(marker="agents"):
    current_path = get_current_path()
    if current_path.is_file():
        current_path = current_path.parent
    for path in [current_path, *current_path.parents]:
        if (path / marker).exists():
            return str(path)
    raise RuntimeError(f"Could not find a parent directory containing '{marker}'")


# ---------------------------------------------------------------------------
# Priority Tier detection
# ---------------------------------------------------------------------------

# Signals are applied to the combined string "{folder_path}/{file_name}" lowercased.
_PRIORITY_SIGNALS: list[tuple[str, list[str]]] = [
    ("CIM", [
        "cim", "confidential information memorandum",
        "offering memorandum", "investment overview", r"\bom\b",
    ]),
    ("QofE Report", [
        "quality of earnings", "qofe", "q of e",
        "financial due diligence", "sell-side qofe",
    ]),
    ("Financial Model", [
        r"model.*\.xlsx?$", r"forecast.*\.xlsx?$", r"projection.*\.xlsx?$",
        r"financial model", r"lbo.*\.xlsx?$",
    ]),
    ("KPI / Dashboard", [
        "kpi", "dashboard", r"\bmetrics\b", "scorecard", "operating",
    ]),
    ("Customer Revenue Workbook", [
        "customer", "revenue by customer", "client revenue",
        "arr by customer",
    ]),
    ("Pipeline / Backlog", [
        "pipeline", "backlog", "weighted pipeline",
        "forecast pipeline", "sales pipeline",
    ]),
    ("Cap Table", [
        "cap table", "capitalization", r"\bequity\b", "cap_table",
    ]),
    ("Material Contracts", [
        r"contract", r"agreement", r"msa",
    ]),
]

# Folders that gate "Material Contracts" detection.
_CONTRACT_FOLDERS = {"contracts", "customer agreements", "msas"}

# Extensions considered image-only (no OCR value without special handling).
_IMAGE_ONLY_EXTENSIONS = {".jpeg", ".jpg", ".png", ".gif", ".bmp", ".tiff", ".tif"}


def detect_priority_tier(
    file_name: str,
    relative_path: str,
    size_bytes: int,
) -> tuple[bool, str | None]:
    """Return (priority_tier, priority_reason) for a file.

    Returns (False, None) when no signal matches or the file should be skipped.
    """
    # Skip tiny files.
    if size_bytes < 1024:
        return False, None

    ext = Path(file_name).suffix.lower()

    # Skip image-only files.
    if ext in _IMAGE_ONLY_EXTENSIONS:
        return False, None

    target = (relative_path + "/" + file_name).lower()
    folder_parts = {p.strip().lower() for p in relative_path.split("/")}

    for reason, patterns in _PRIORITY_SIGNALS:
        # Material contracts require specific folder context.
        if reason == "Material Contracts":
            if not folder_parts.intersection(_CONTRACT_FOLDERS):
                continue

        for pattern in patterns:
            if re.search(pattern, target):
                return True, reason

    return False, None


def classify_format(file_name: str) -> str:
    ext = Path(file_name).suffix.lower()
    mapping = {
        ".pdf": "pdf",
        ".xlsx": "xlsx", ".xls": "xlsx", ".xlsm": "xlsx",
        ".docx": "docx", ".doc": "docx",
        ".pptx": "pptx", ".ppt": "pptx",
        ".csv": "other", ".txt": "other",
    }
    return mapping.get(ext, "other")


# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------

def main():
    repo_root = find_repo_root()
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    print("repo_root:", repo_root)

    # Runtime parameters.
    company_name = get_param("sp_company_name")
    catalog      = get_param("catalog",  default="uc13")
    schema       = get_param("schema",   default="ingestion")

    # Inject SharePoint credentials into env so connector/uploader can read them.
    os.environ["SP_TENANT_ID"]     = get_secret("sp_tenant_id")
    os.environ["SP_CLIENT_ID"]     = get_secret("sp_client_id")
    os.environ["SP_CLIENT_SECRET"] = get_secret("sp_client_secret")
    os.environ["SP_SITE_URL"]      = get_secret("sp_site_url")
    os.environ["SP_FOLDER_PATH"]   = get_secret("sp_folder_path")
    os.environ["SP_COMPANY_NAME"]  = company_name
    os.environ["UC_VOLUME_PATH"]   = f"/Volumes/{catalog}/{schema}/raw_files"

    # Import after env vars are set (lazy validation in connector/uploader).
    from agents.ingestion.tools.connector import (
        list_files,
        download_batch,
        get_company_folder_path,
    )
    from agents.ingestion.tools.uploader import (
        get_volume_company_path,
        upload_from_directory,
    )

    print(f"\n=== UC13 Phase 1 — Download & Upload ({company_name}) ===")
    print(f"SharePoint folder : {get_company_folder_path()}")
    print(f"UC Volume target  : {get_volume_company_path()}/")

    # Step 1: list files (deduplication handled inside list_files).
    print("\n[1/3] Listing files from SharePoint...")
    files = list_files()
    print(f"  {len(files)} files after deduplication")

    # Step 2: download to a temp directory.
    with tempfile.TemporaryDirectory(prefix="uc13_download_") as tmp_dir:
        print(f"\n[2/3] Downloading to {tmp_dir}...")
        download_results = download_batch(files, destination_root=tmp_dir)
        succeeded_downloads = sum(1 for p in download_results.values() if p is not None)
        print(f"  {succeeded_downloads}/{len(files)} files downloaded")

        # Step 3: upload from temp dir to UC Volume.
        print(f"\n[3/3] Uploading to UC Volume...")
        summary = upload_from_directory(tmp_dir)
        print(f"  {summary.successful}/{summary.total_files} files uploaded")

    # Build upload_log records — one per file, using FileMetadata for metadata.
    file_lookup = {f.name: f for f in files}
    log_rows = []
    now = datetime.now(timezone.utc)

    for upload_result in summary.results:
        meta = file_lookup.get(upload_result.file_name)
        folder_path = str(Path(upload_result.relative_path).parent)
        size_bytes = meta.size_bytes if meta else upload_result.size_bytes

        priority_tier, priority_reason = detect_priority_tier(
            file_name=upload_result.file_name,
            relative_path=upload_result.relative_path,
            size_bytes=size_bytes,
        )

        try:
            mod_date = (
                meta.last_modified[:10] if meta and meta.last_modified else None
            )
        except Exception:
            mod_date = None

        log_rows.append({
            "company_name":   company_name,
            "file_name":      upload_result.file_name,
            "relative_path":  upload_result.relative_path,
            "folder_path":    folder_path,
            "priority_tier":  priority_tier,
            "priority_reason": priority_reason,
            "mod_date":       mod_date,
            "format":         classify_format(upload_result.file_name),
            "size_bytes":     size_bytes,
            "upload_status":  upload_result.status,
            "uploaded_at":    now,
        })

    # Save upload_log to Delta.
    try:
        _spark = spark  # noqa: F821

        from pyspark.sql import Row
        from pyspark.sql.types import (
            StructType, StructField, StringType, BooleanType,
            LongType, TimestampType,
        )

        table_log = f"{catalog}.{schema}.upload_log"
        _spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
        _spark.sql(f"""
            CREATE TABLE IF NOT EXISTS {table_log} (
                company_name   STRING,
                file_name      STRING,
                relative_path  STRING,
                folder_path    STRING,
                priority_tier  BOOLEAN,
                priority_reason STRING,
                mod_date       STRING,
                format         STRING,
                size_bytes     BIGINT,
                upload_status  STRING,
                uploaded_at    TIMESTAMP
            ) USING DELTA
        """)

        # Replace this company's rows so re-runs are idempotent and
        # other companies' rows are preserved.
        try:
            _spark.sql(f"DELETE FROM {table_log} WHERE company_name = '{company_name}'")
        except Exception:
            pass  # Column may not exist on an older table — mergeSchema below handles it.

        rows = [Row(**r) for r in log_rows]
        df = _spark.createDataFrame(rows)
        df.write.mode("append").option("mergeSchema", "true").saveAsTable(table_log)
        print(f"\n✓ Upload log saved: {len(log_rows)} rows → {table_log}")

    except NameError:
        # Running locally without Spark — print summary instead.
        print("\n[local mode] Spark not available; skipping upload_log table write.")

    # Summary.
    priority_count = sum(1 for r in log_rows if r["priority_tier"])
    print(f"\n=== Phase 1 complete ===")
    print(f"  Total files    : {len(log_rows)}")
    print(f"  Priority Tier  : {priority_count}")
    print(f"  Non-priority   : {len(log_rows) - priority_count}")
    print(f"  Failed uploads : {summary.failed}")


if __name__ == "__main__":
    main()
