"""
02_document_classifier.py — Phase 2a: Dual Classification (Document Classifier).

Reads all files uploaded to the UC Volume for the current company, calls the LLM
in batches of 20 to assign workstream tags and priority classification, applies
post-classification deduplication, and saves results to uc13.classification.doc_relevance.

Phase 2a output:
  - Table uc13.classification.doc_relevance

Workstream tags (ARRAY<STRING> — a file can receive multiple):
  FINANCIAL, CUSTOMER, KPI_OPS, LEGAL, QUALITY_EARNINGS,
  FORECAST, BUSINESS_MODEL, BACKGROUND

Priority tier is BOOLEAN:
  True  = priority document (high-value; confirm or override signal from Phase 1)
  False = non-priority

Dependencies:
  - uc13.ingestion.upload_log (written by 01_download_upload.py)
  - Volume files under /Volumes/{catalog}/ingestion/raw_files/{company_name}/
  - MLflow endpoint: databricks-meta-llama-3-3-70b-instruct
  - Job parameters: sp_company_name, catalog, schema
"""

import json
import os
import re
import sys
import uuid
from collections import defaultdict
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
# LLM classification
# ---------------------------------------------------------------------------

_VALID_WORKSTREAMS = {
    "FINANCIAL", "CUSTOMER", "KPI_OPS", "LEGAL",
    "QUALITY_EARNINGS", "FORECAST", "BUSINESS_MODEL", "BACKGROUND",
}

_SANITIZE = str.maketrans({
    '"': "'", "\\": "/", "\n": " ",
    "\u2013": "-", "\u2014": "-", "–": "-", "—": "-",
    "\u00a0": " ", "(": "[", ")": "]",
})


def _sanitize(name: str) -> str:
    return name.translate(_SANITIZE)


def classify_batch(
    files_batch: list[dict],
    client,
    upload_signals: dict[str, dict],
) -> list[dict] | None:
    """Call the LLM to classify a batch of files.

    Each entry in files_batch has: file_name, relative_path, folder_path.
    upload_signals maps file_name → {priority_tier, priority_reason} from Phase 1.
    """
    file_list = "\n".join([
        (
            f"{i+1}. [folder: {_sanitize(f['folder_path'])}] "
            f"{_sanitize(f['file_name'])}"
            + (
                f" [Phase1: priority={upload_signals.get(f['file_name'], {}).get('priority_tier', False)},"
                f" reason={upload_signals.get(f['file_name'], {}).get('priority_reason') or 'none'}]"
            )
        )
        for i, f in enumerate(files_batch)
    ])

    prompt = """You are a private equity analyst classifying documents from a PE due diligence data room.

WORKSTREAM TAGS (assign one or more per file — except BACKGROUND which is exclusive):
  FINANCIAL       — P&L, balance sheet, cash flow, tax returns, audited financials, monthly management accounts
  CUSTOMER        — Customer lists, revenue by customer, cohort analyses, churn schedules, NRR schedules
  KPI_OPS         — KPI dashboards, utilization reports, headcount files, pipeline/backlog, operational metrics
  LEGAL           — Contracts, MSAs, SOWs, leases, employment agreements, litigation files, IP documents
  QUALITY_EARNINGS — QofE reports, EBITDA bridges, addback schedules, revenue reconciliations
  FORECAST        — Financial models, projection files, management presentations with forward guidance
  BUSINESS_MODEL  — CIM, investor presentations, management decks, org charts, product/service descriptions
  BACKGROUND      — Anything not matching above (individual employee contracts, payroll, insurance certs).
                    BACKGROUND is mutually exclusive — do NOT combine with other tags.

PRIORITY TIER (Boolean):
  true  — high-value documents: CIM, QofE, Financial Model, KPI dashboard, audited financials,
          QofE/FDD databook, Revenue by customer, Cap Table, Primary contracts/MSAs,
          Org chart, Company Tax returns, EBITDA bridge, Addbacks schedule.
          Use the Phase1 signal as a strong hint; override only if the filename/folder
          clearly contradicts it (e.g. Phase1 flagged a blank template).
  false — everything else.

IMPORTANT RULES:
  - priority_tier must be true when should_parse is true AND file is high-value.
  - should_parse=false for: individual weekly payroll PDFs, I-9/W-4/onboarding forms,
    blank templates, ZIP files, images (.jpeg/.png/.gif), binary Excel (.xlsb),
    dozens of identical individual employee or caregiver contracts, background checks.
  - extraction_confidence: "high" | "medium" | "low"

Return ONLY a JSON array, no markdown, no explanation. One object per file, in order:
[{"workstream":["FINANCIAL","QUALITY_EARNINGS"],"priority_tier":true,"should_parse":true,"extraction_confidence":"high","priority_reason":"QofE report"}]

Files:
""" + file_list

    response = client.predict(
        endpoint="databricks-meta-llama-3-3-70b-instruct",
        inputs={
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4000,
            "temperature": 0.0,
        },
    )

    text = response["choices"][0]["message"]["content"].strip()
    text = re.sub(r"```json\s*|\s*```", "", text).strip()

    try:
        result = json.loads(text)
        if isinstance(result, list) and len(result) > 0:
            for r in result:
                # Normalise workstream to uppercase list.
                ws_raw = r.get("workstream", ["BACKGROUND"])
                if isinstance(ws_raw, str):
                    ws_raw = [ws_raw]
                ws_clean = [w.upper() for w in ws_raw if w.upper() in _VALID_WORKSTREAMS]
                if not ws_clean:
                    ws_clean = ["BACKGROUND"]
                # BACKGROUND is exclusive.
                if "BACKGROUND" in ws_clean and len(ws_clean) > 1:
                    ws_clean = [w for w in ws_clean if w != "BACKGROUND"]
                r["workstream"] = ws_clean

                # Normalise priority_tier to bool.
                r["priority_tier"] = bool(r.get("priority_tier", False))

                # Normalise confidence.
                conf = str(r.get("extraction_confidence", "low")).lower()
                r["extraction_confidence"] = conf if conf in ("high", "medium", "low") else "low"

            # Pad if LLM returned fewer rows than the batch.
            while len(result) < len(files_batch):
                result.append({
                    "workstream": ["BACKGROUND"],
                    "priority_tier": False,
                    "should_parse": False,
                    "extraction_confidence": "low",
                    "priority_reason": "missing from LLM response — needs manual review",
                })

            return result[: len(files_batch)]
    except Exception as e:
        print(f"  Parse error: {e} | Response: {text[:300]}")
    return None


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def _base_name(file_name: str) -> str:
    stem = Path(file_name).stem
    ext  = Path(file_name).suffix.lower()
    clean = re.sub(
        r"[-_\s]*(v\w+|\d{4}[-_]\w+[-_]\d+|\d{1,2}[._]\d{1,2}[._]\d{2,4}"
        r"|vSHARE_[\d.]+|vRevised|vF|vUPLOAD|final|updated|copy"
        r"|\(\d+\)|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[-_\s]*",
        "",
        stem,
        flags=re.IGNORECASE,
    ).strip()
    return clean.lower() + ext


def deduplicate(results: list[dict]) -> list[dict]:
    """Mark older versions of the same document as should_parse=False."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        key = f"{r['folder_path']}|{_base_name(r['file_name'])}"
        groups[key].append(r)

    final = []
    for group in groups.values():
        if len(group) == 1:
            final.extend(group)
            continue
        # Sort by mod_date descending; keep newest as canonical.
        group.sort(key=lambda x: x.get("mod_date") or "", reverse=True)
        canonical, *older = group
        final.append(canonical)
        for doc in older:
            final.append({
                **doc,
                "should_parse": False,
                "priority_reason": f"older version of: {canonical['file_name']}",
                "extraction_confidence": "high",
            })
    return final


# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------

def main():
    repo_root = find_repo_root()
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    print("repo_root:", repo_root)

    company_name = get_param("sp_company_name")
    catalog      = get_param("catalog",  default="uc13")
    schema       = get_param("schema",   default="ingestion")

    volume_path    = f"/Volumes/{catalog}/{schema}/raw_files/{company_name}"
    table_log      = f"{catalog}.{schema}.upload_log"
    table_relevance = f"{catalog}.classification.doc_relevance"

    from pyspark.sql import SparkSession as _SparkSession
    _spark = _SparkSession.getActiveSession()
    if _spark is None:
        raise RuntimeError("No active Spark session. This script must run on a Databricks cluster.")

    print(f"\n=== UC13 Phase 2a — Document Classifier ({company_name}) ===")
    print(f"Volume: {volume_path}")

    # --- Ensure schemas and output table exist ---
    _spark.sql("CREATE SCHEMA IF NOT EXISTS uc13.classification")
    _spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {table_relevance} (
            company_name         STRING,
            document_id          STRING,
            filename             STRING,
            folder_path          STRING,
            workstream           ARRAY<STRING>,
            priority_tier        BOOLEAN,
            priority_reason      STRING,
            should_parse         BOOLEAN,
            extraction_confidence STRING,
            mod_date             STRING,
            format               STRING
        ) USING DELTA
    """)

    # --- Load Phase 1 priority signals ---
    upload_signals: dict[str, dict] = {}
    try:
        rows = _spark.sql(f"""
            SELECT file_name, priority_tier, priority_reason, mod_date, format
            FROM {table_log}
            WHERE company_name = '{company_name}'
        """).collect()
        upload_signals = {
            r.file_name: {
                "priority_tier":   r.priority_tier,
                "priority_reason": r.priority_reason,
                "mod_date":        r.mod_date,
                "format":          r.format,
            }
            for r in rows
        }
        print(f"Loaded {len(upload_signals)} Phase 1 upload signals")
    except Exception as e:
        print(f"Warning: could not load upload_log ({e}). Continuing without Phase 1 signals.")

    # --- Walk volume and build file list ---
    all_files: list[dict] = []
    for root, _dirs, files in os.walk(volume_path):
        for fname in files:
            if fname.startswith("."):
                continue
            full_path = os.path.join(root, fname)
            relative  = full_path.replace(volume_path + "/", "")
            folder    = str(Path(relative).parent)
            all_files.append({
                "file_name":    fname,
                "relative_path": relative,
                "folder_path":  folder,
            })

    print(f"Total files in volume: {len(all_files)}")

    # --- Classify in batches of 20 ---
    import mlflow.deployments
    client = mlflow.deployments.get_deploy_client("databricks")

    BATCH_SIZE = 20
    all_results: list[dict] = []
    total_batches = -(-len(all_files) // BATCH_SIZE)

    for batch_start in range(0, len(all_files), BATCH_SIZE):
        batch     = all_files[batch_start : batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1

        result = classify_batch(batch, client, upload_signals)

        if result and len(result) == len(batch):
            for f, r in zip(batch, result):
                sig = upload_signals.get(f["file_name"], {})
                all_results.append({
                    "company_name":         company_name,
                    "document_id":          str(uuid.uuid4()),
                    "filename":             f["file_name"],
                    "folder_path":          f["folder_path"],
                    "workstream":           r["workstream"],
                    "priority_tier":        r["priority_tier"],
                    "priority_reason":      r.get("priority_reason") or sig.get("priority_reason"),
                    "should_parse":         bool(r.get("should_parse", False)),
                    "extraction_confidence": r["extraction_confidence"],
                    "mod_date":             sig.get("mod_date"),
                    "format":               sig.get("format", "other"),
                })
            print(f"  Batch {batch_num}/{total_batches}: {len(batch)} files ✓")
        else:
            # Fall back to individual classification.
            print(f"  Batch {batch_num}/{total_batches}: batch failed — retrying individually")
            for single_file in batch:
                single = classify_batch([single_file], client, upload_signals)
                sig    = upload_signals.get(single_file["file_name"], {})
                if single and len(single) == 1:
                    r = single[0]
                    all_results.append({
                        "company_name":         company_name,
                        "document_id":          str(uuid.uuid4()),
                        "filename":             single_file["file_name"],
                        "folder_path":          single_file["folder_path"],
                        "workstream":           r["workstream"],
                        "priority_tier":        r["priority_tier"],
                        "priority_reason":      r.get("priority_reason") or sig.get("priority_reason"),
                        "should_parse":         bool(r.get("should_parse", False)),
                        "extraction_confidence": r["extraction_confidence"],
                        "mod_date":             sig.get("mod_date"),
                        "format":               sig.get("format", "other"),
                    })
                else:
                    all_results.append({
                        "company_name":         company_name,
                        "document_id":          str(uuid.uuid4()),
                        "filename":             single_file["file_name"],
                        "folder_path":          single_file["folder_path"],
                        "workstream":           ["BACKGROUND"],
                        "priority_tier":        False,
                        "priority_reason":      None,
                        "should_parse":         False,
                        "extraction_confidence": "low",
                        "mod_date":             sig.get("mod_date"),
                        "format":               sig.get("format", "other"),
                    })

    # --- Deduplication ---
    final_results = deduplicate(all_results)
    skipped = sum(1 for r in final_results if not r["should_parse"])
    print(
        f"\nDeduplication complete: {len(final_results)} total, "
        f"{len(final_results) - skipped} to parse, {skipped} skipped"
    )

    # --- Save to Delta ---
    from pyspark.sql import Row
    from pyspark.sql.types import (
        StructType, StructField, StringType, BooleanType, ArrayType,
    )

    schema_spark = StructType([
        StructField("company_name",          StringType(),           False),
        StructField("document_id",           StringType(),           False),
        StructField("filename",              StringType(),           False),
        StructField("folder_path",           StringType(),           True),
        StructField("workstream",            ArrayType(StringType()), True),
        StructField("priority_tier",         BooleanType(),          True),
        StructField("priority_reason",       StringType(),           True),
        StructField("should_parse",          BooleanType(),          False),
        StructField("extraction_confidence", StringType(),           True),
        StructField("mod_date",              StringType(),           True),
        StructField("format",               StringType(),           True),
    ])

    rows = [Row(**r) for r in final_results]
    df = _spark.createDataFrame(rows, schema=schema_spark)

    # Upsert: replace this company's rows, preserve all other companies.
    from delta.tables import DeltaTable
    delta_tbl = DeltaTable.forName(_spark, table_relevance)
    (
        delta_tbl.alias("t")
        .merge(
            df.alias("s"),
            "t.company_name = s.company_name AND t.filename = s.filename",
        )
        .whenMatchedUpdateAll()
        .whenNotMatchedInsertAll()
        .execute()
    )

    print(f"✓ Saved {len(final_results)} classifications → {table_relevance}")
    print(f"\n  Priority Tier (True)  : {sum(1 for r in final_results if r['priority_tier'])}")
    print(f"  Will parse            : {len(final_results) - skipped}")
    print(f"  Will skip             : {skipped}")


if __name__ == "__main__":
    main()
