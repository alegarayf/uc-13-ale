"""
ensure_coverage.py — Phase 2c: Incremental ingestion for workstream coverage gaps.

Checks which approved files (should_parse=true in doc_relevance) have NOT yet been
processed into uc13.ingestion.embeddings for a given company and tier range. Parses
and embeds only the missing files, APPENDing to the existing tables without deleting
rows that were written by ingestion_parser.py.

WHY THIS SCRIPT EXISTS
──────────────────────
ingestion_parser.py uses a full DELETE → APPEND pattern: every run replaces ALL of
a company's chunks and embeddings. Running it again with parse_priority_tiers=2 would
erase Tier 1 data. This script performs incremental, additive ingestion so you can
safely fill coverage gaps without touching already-processed files.

TYPICAL USAGE (from test_pipeline.ipynb)
─────────────────────────────────────────
  import ensure_coverage as ec
  importlib.reload(ec)

  # 1. Diagnose — see which workstreams have zero ingested files:
  report = ec.get_coverage_report(company_name, catalog="uc13", tiers=[1, 2], spark=spark)
  ec.print_coverage_report(report)

  # 2. Ingest any missing files (Tiers 1 and 2, skipping already-processed):
  summary = ec.ingest_missing(company_name, catalog="uc13", tiers=[1, 2], spark=spark)

  # 3. Or run both steps in sequence via main():
  ec.main()

OUTPUTS (incremental APPEND — existing rows are never deleted)
──────────────────────────────────────────────────────────────
  - uc13.ingestion.chunks
  - uc13.ingestion.embeddings  (triggers VS index sync after each ingest run)

DEPENDENCIES
────────────
  - uc13.classification.doc_relevance  (written by document_classifier.py)
  - ingestion_parser.py (imports parse_file, get_embeddings_batch, _print_chunk_diagnostics,
    _wait_for_index_sync, _ALLOWED_EXTENSIONS from the same scripts/ directory)
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from typing import Optional

# ---------------------------------------------------------------------------
# Secrets / params helpers — copied verbatim from ingestion_parser.py
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
# Coverage diagnostic
# ---------------------------------------------------------------------------

def get_coverage_report(
    company_name: str,
    catalog: str,
    tiers: list[int],
    spark,
) -> dict:
    """Return a workstream coverage report showing ingested vs. available files.

    Args:
        company_name: Target company (e.g. "Elder Care").
        catalog:      UC catalog name (e.g. "uc13").
        tiers:        List of priority tiers to check (e.g. [1, 2]).
        spark:        Active SparkSession.

    Returns:
        dict with keys:
          - company_name, tiers_checked
          - total_approved, total_ingested, total_missing
          - by_workstream: {ws: {approved, ingested, missing}} (lists of filenames)
    """
    schema           = "ingestion"
    table_relevance  = f"{catalog}.classification.doc_relevance"
    table_embeddings = f"{catalog}.{schema}.embeddings"

    tier_sql = (
        f"AND priority_tier IN ({', '.join(str(t) for t in tiers)})"
        if tiers else ""
    )

    approved_rows = spark.sql(f"""
        SELECT filename, workstream, priority_tier
        FROM   {table_relevance}
        WHERE  should_parse = true
          AND  company_name = '{company_name}'
          {tier_sql}
        ORDER BY priority_tier ASC NULLS LAST
    """).collect()

    try:
        ingested_rows = spark.sql(f"""
            SELECT DISTINCT file_name
            FROM   {table_embeddings}
            WHERE  company_name = '{company_name}'
        """).collect()
        ingested_names: set[str] = {r.file_name for r in ingested_rows}
    except Exception:
        ingested_names = set()

    by_ws: dict[str, dict] = {}
    approved_all: set[str] = set()

    for row in approved_rows:
        fname = row.filename
        approved_all.add(fname)
        for ws in (row.workstream or []):
            ws_entry = by_ws.setdefault(ws, {"approved": [], "ingested": [], "missing": []})
            if fname not in ws_entry["approved"]:
                ws_entry["approved"].append(fname)
            if fname in ingested_names:
                if fname not in ws_entry["ingested"]:
                    ws_entry["ingested"].append(fname)
            else:
                if fname not in ws_entry["missing"]:
                    ws_entry["missing"].append(fname)

    total_ingested_in_scope = len(approved_all & ingested_names)
    total_missing_in_scope  = len(approved_all - ingested_names)

    return {
        "company_name":    company_name,
        "tiers_checked":   tiers,
        "total_approved":  len(approved_all),
        "total_ingested":  total_ingested_in_scope,
        "total_missing":   total_missing_in_scope,
        "by_workstream":   by_ws,
    }


def print_coverage_report(report: dict) -> None:
    """Pretty-print a coverage report returned by get_coverage_report()."""
    company = report["company_name"]
    tiers   = report["tiers_checked"]
    print(f"\n{'═' * 62}")
    print(f"  Agent Coverage Report — {company}  (tiers {tiers})")
    print(f"{'═' * 62}")
    print(f"  Total approved files   : {report['total_approved']}")
    print(f"  Already ingested       : {report['total_ingested']}")
    print(f"  Missing (not ingested) : {report['total_missing']}")
    print()

    by_ws = report.get("by_workstream", {})
    if not by_ws:
        print("  (no approved files found for the given tiers)")
        return

    print(f"  {'Workstream':<22} {'Approved':>8}  {'Ingested':>8}  {'Missing':>8}  Status")
    print(f"  {'-' * 58}")
    for ws, counts in sorted(by_ws.items()):
        n_appr = len(counts["approved"])
        n_ing  = len(counts["ingested"])
        n_miss = len(counts["missing"])
        if n_ing == 0:
            status = "⚠ NO COVERAGE — agent will find 0 chunks"
        elif n_miss == 0:
            status = "✓ full"
        else:
            status = f"△ partial ({n_miss} missing)"
        print(f"  {ws:<22} {n_appr:>8}  {n_ing:>8}  {n_miss:>8}  {status}")

    # Detail: list missing files per workstream
    any_missing = any(counts["missing"] for counts in by_ws.values())
    if any_missing:
        print(f"\n  Missing files by workstream:")
        for ws, counts in sorted(by_ws.items()):
            if counts["missing"]:
                print(f"  [{ws}]")
                for f in counts["missing"][:10]:
                    print(f"    - {f}")
                if len(counts["missing"]) > 10:
                    print(f"    ... and {len(counts['missing']) - 10} more")
    print()


# ---------------------------------------------------------------------------
# Unprocessed file resolver
# ---------------------------------------------------------------------------

def get_unprocessed_files(
    company_name: str,
    catalog: str,
    tiers: list[int],
    spark,
) -> list[dict]:
    """Return approved files (in doc_relevance) that are NOT yet in embeddings.

    Returns:
        List of dicts with keys: file_name, folder_path, workstream, priority_tier.
        Ordered by priority_tier ASC so Tier 1 files are processed first.
    """
    schema           = "ingestion"
    table_relevance  = f"{catalog}.classification.doc_relevance"
    table_embeddings = f"{catalog}.{schema}.embeddings"

    tier_sql = (
        f"AND priority_tier IN ({', '.join(str(t) for t in tiers)})"
        if tiers else ""
    )

    try:
        ingested_rows = spark.sql(f"""
            SELECT DISTINCT file_name
            FROM   {table_embeddings}
            WHERE  company_name = '{company_name}'
        """).collect()
        ingested_names: set[str] = {r.file_name for r in ingested_rows}
    except Exception:
        ingested_names = set()

    approved_rows = spark.sql(f"""
        SELECT filename AS file_name, folder_path, workstream, priority_tier
        FROM   {table_relevance}
        WHERE  should_parse = true
          AND  company_name = '{company_name}'
          {tier_sql}
        ORDER BY priority_tier ASC NULLS LAST
    """).collect()

    return [
        {
            "file_name":     r.file_name,
            "folder_path":   r.folder_path,
            "workstream":    list(r.workstream or []),
            "priority_tier": r.priority_tier,
        }
        for r in approved_rows
        if r.file_name not in ingested_names
    ]


# ---------------------------------------------------------------------------
# Incremental ingest
# ---------------------------------------------------------------------------

def ingest_missing(
    company_name: str,
    catalog: str,
    tiers: list[int],
    spark,
    embedding_endpoint: str = "databricks-bge-large-en",
    schema: str = "ingestion",
    vision_endpoint: Optional[str] = None,
) -> dict:
    """Parse and embed files not yet present in embeddings. APPEND only — no DELETE.

    Imports parse_file, get_embeddings_batch, _wait_for_index_sync from
    ingestion_parser.py (must be on sys.path, i.e. in jobs/scripts/).

    Args:
        company_name:       Target company.
        catalog:            UC catalog name.
        tiers:              Priority tiers to fill (e.g. [1, 2]).
        spark:              Active SparkSession.
        embedding_endpoint: MLflow embedding endpoint.
        schema:             UC ingestion schema name.

    Returns:
        dict with keys: files_processed, chunks_written, embeddings_written, skipped.
    """
    # ── Import parse utilities from ingestion_parser ──────────────────────────
    try:
        import ingestion_parser as ip
    except ImportError:
        scripts_dir = str(Path(__file__).parent)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import ingestion_parser as ip

    _ALLOWED = ip._ALLOWED_EXTENSIONS
    parse_file          = ip.parse_file
    get_embeddings_b    = ip.get_embeddings_batch
    print_diagnostics   = ip._print_chunk_diagnostics
    wait_for_sync       = ip._wait_for_index_sync

    # ── Identify missing files ────────────────────────────────────────────────
    missing = get_unprocessed_files(company_name, catalog, tiers, spark)

    if not missing:
        print(f"✓ All approved Tier {tiers} files are already ingested for '{company_name}' — nothing to do.")
        return {"files_processed": 0, "chunks_written": 0, "embeddings_written": 0, "skipped": 0}

    print(f"\n=== Incremental Ingest — {company_name} (tiers {tiers}) ===")
    print(f"  Files to process : {len(missing)}")

    volume_path      = f"/Volumes/{catalog}/{schema}/raw_files/{company_name}"
    table_chunks     = f"{catalog}.{schema}.chunks"
    table_embeddings = f"{catalog}.{schema}.embeddings"

    # ── Resolve file paths and skip non-existent / unsupported ───────────────
    relevance_map: dict[str, dict] = {}
    file_paths: list[str] = []
    skipped = 0

    for f in missing:
        fname  = f["file_name"]
        folder = f.get("folder_path") or ""
        fpath  = (
            os.path.join(volume_path, folder, fname)
            if folder not in ("", ".", None)
            else os.path.join(volume_path, fname)
        )
        if not os.path.exists(fpath):
            print(f"  ⚠ File not found in volume, skipping: {fname}")
            skipped += 1
            continue
        if Path(fpath).suffix.lower() not in _ALLOWED:
            print(f"  — Unsupported extension, skipping: {fname}")
            skipped += 1
            continue
        relevance_map[fname] = {
            "workstream":    f["workstream"],
            "priority_tier": f["priority_tier"],
        }
        file_paths.append(fpath)

    print(f"  Resolvable files : {len(file_paths)}  (skipped={skipped})")

    if not file_paths:
        print("No resolvable files — exiting.")
        return {"files_processed": 0, "chunks_written": 0, "embeddings_written": 0, "skipped": skipped}

    # ── Parse ─────────────────────────────────────────────────────────────────
    all_chunks = []
    for fpath in file_paths:
        chunks = parse_file(fpath, spark, vision_endpoint=vision_endpoint)
        all_chunks.extend(chunks)
        fname = os.path.basename(fpath)
        print(f"  Parsed  {fname[:60]}: {len(chunks)} chunks")

    print_diagnostics(all_chunks)

    if not all_chunks:
        print("No chunks generated — nothing to write.")
        return {"files_processed": len(file_paths), "chunks_written": 0, "embeddings_written": 0, "skipped": skipped}

    # ── Write chunks (APPEND — no DELETE) ────────────────────────────────────
    from pyspark.sql import Row
    from pyspark.sql.types import (
        StructType, StructField, StringType, IntegerType,
        ArrayType, FloatType, TimestampType,
    )

    now = datetime.now(timezone.utc)

    chunk_schema = StructType([
        StructField("company_name",   StringType(),  False),
        StructField("chunk_id",       StringType(),  False),
        StructField("doc_id",         StringType(),  False),
        StructField("file_name",      StringType(),  False),
        StructField("file_type",      StringType(),  False),
        StructField("relative_path",  StringType(),  False),
        StructField("chunk_index",    IntegerType(), False),
        StructField("chunk_text",     StringType(),  False),
        StructField("section_header", StringType(),  True),
        StructField("page_start",     IntegerType(), True),
        StructField("page_end",       IntegerType(), True),
        StructField("tab",            StringType(),  True),
        StructField("source_type",    StringType(),  True),
        StructField("char_count",     IntegerType(), False),
        StructField("created_at",     TimestampType(), False),
    ])

    chunk_rows = [
        Row(
            company_name=company_name,
            chunk_id=c.chunk_id, doc_id=c.doc_id, file_name=c.file_name,
            file_type=c.file_type, relative_path=c.relative_path,
            chunk_index=int(c.chunk_index), chunk_text=c.chunk_text,
            section_header=c.section_header,
            page_start=int(c.page_start)   if c.page_start   is not None else None,
            page_end=int(c.page_end)       if c.page_end     is not None else None,
            tab=c.tab, source_type=getattr(c, "source_type", "text"),
            char_count=int(c.char_count), created_at=now,
        )
        for c in all_chunks
    ]
    df_chunks = spark.createDataFrame(chunk_rows, schema=chunk_schema)
    df_chunks.write.format("delta").mode("append").option("mergeSchema", "true").saveAsTable(table_chunks)
    chunks_written = df_chunks.count()
    print(f"✓ Appended {chunks_written} chunks → {table_chunks}")

    # ── Embed and write embeddings (APPEND — no DELETE) ───────────────────────
    import mlflow.deployments
    client = mlflow.deployments.get_deploy_client("databricks")
    texts  = [c.chunk_text for c in all_chunks]
    print(f"\nGenerating embeddings for {len(texts)} chunks...")
    embeddings = get_embeddings_b(texts, client, embedding_endpoint)
    print(f"Generated {len(embeddings)} embeddings")

    emb_schema = StructType([
        StructField("company_name",  StringType(),           False),
        StructField("chunk_id",      StringType(),           False),
        StructField("doc_id",        StringType(),           False),
        StructField("file_name",     StringType(),           False),
        StructField("workstream",    ArrayType(StringType()), True),
        StructField("priority_tier", IntegerType(),          True),
        StructField("source_type",   StringType(),           True),
        StructField("embedding",     ArrayType(FloatType()), False),
        StructField("created_at",    TimestampType(),        False),
    ])

    emb_rows = [
        Row(
            company_name=company_name,
            chunk_id=all_chunks[i].chunk_id,
            doc_id=all_chunks[i].doc_id,
            file_name=all_chunks[i].file_name,
            workstream=relevance_map.get(all_chunks[i].file_name, {}).get("workstream"),
            priority_tier=relevance_map.get(all_chunks[i].file_name, {}).get("priority_tier"),
            source_type=getattr(all_chunks[i], "source_type", "text"),
            embedding=[float(x) for x in embeddings[i]],
            created_at=now,
        )
        for i in range(len(all_chunks))
    ]
    df_emb = spark.createDataFrame(emb_rows, schema=emb_schema)
    df_emb.write.format("delta").mode("append").option("mergeSchema", "true").saveAsTable(table_embeddings)
    emb_written = df_emb.count()
    print(f"✓ Appended {emb_written} embeddings → {table_embeddings}")

    # ── Trigger vector search index sync ─────────────────────────────────────
    wait_for_sync(
        spark=spark,
        catalog=catalog,
        schema=schema,
        index_suffix="embeddings_index",
        table_embeddings=table_embeddings,
    )

    summary = {
        "files_processed":    len(file_paths),
        "chunks_written":     chunks_written,
        "embeddings_written": emb_written,
        "skipped":            skipped,
    }
    print(f"\n✓ Incremental ingest complete: {summary}")
    return summary


# ---------------------------------------------------------------------------
# main() — reads params from widgets / env vars and runs both steps
# ---------------------------------------------------------------------------

def main() -> dict:
    """Coverage check + incremental ingest. Callable from notebook or as a job task."""
    repo_root = find_repo_root()
    scripts_dir = str(Path(repo_root) / "jobs" / "scripts")
    for p in [repo_root, scripts_dir]:
        if p not in sys.path:
            sys.path.insert(0, p)

    company_name       = get_param("sp_company_name")
    catalog            = get_param("catalog",            default="uc13")
    schema             = get_param("schema",             default="ingestion")
    embedding_endpoint = get_param("embedding_endpoint", default="databricks-bge-large-en")
    _vision_raw        = get_param("vision_endpoint",    default="")
    vision_endpoint: Optional[str] = _vision_raw.strip() or None

    # parse_priority_tiers param follows the same convention as ingestion_parser:
    # "all" means [1, 2, 3], otherwise a comma-separated list like "1,2".
    tiers_raw = get_param("parse_priority_tiers", default="1,2").strip().lower()
    if tiers_raw == "all":
        tiers = [1, 2, 3]
    else:
        tiers = [int(t.strip()) for t in tiers_raw.split(",") if t.strip().isdigit()]

    from pyspark.sql import SparkSession
    spark = SparkSession.getActiveSession()
    if spark is None:
        raise RuntimeError("No active Spark session.")

    print(f"\n=== Ensure Agent Coverage ({company_name}, tiers {tiers}) ===")

    # Step 1: Coverage diagnostic
    report = get_coverage_report(company_name, catalog=catalog, tiers=tiers, spark=spark)
    print_coverage_report(report)

    if report["total_missing"] == 0:
        print("All approved files already ingested — no incremental ingest needed.")
        return {"coverage_report": report, "ingest_summary": None}

    # Step 2: Incremental ingest
    ingest_summary = ingest_missing(
        company_name=company_name,
        catalog=catalog,
        tiers=tiers,
        spark=spark,
        embedding_endpoint=embedding_endpoint,
        schema=schema,
        vision_endpoint=vision_endpoint,
    )

    # Step 3: Post-ingest coverage confirmation
    print("\n=== Post-Ingest Coverage Confirmation ===")
    post_report = get_coverage_report(company_name, catalog=catalog, tiers=tiers, spark=spark)
    print_coverage_report(post_report)

    return {"coverage_report": post_report, "ingest_summary": ingest_summary}


if __name__ == "__main__":
    main()
