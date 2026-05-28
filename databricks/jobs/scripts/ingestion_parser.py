"""
03_ingestion_parser.py — Phase 2b: Parsing, chunking, and embedding.

Reads files marked should_parse=true from uc13.classification.doc_relevance,
ordered by priority_tier DESC so Priority Tier documents are processed first.
Parses each file into semantic chunks, generates BGE Large embeddings, and
saves both to Delta tables.

Chunking improvements (vs. original notebook):
  PDF  — Section header carry-forward (no chunk is header-less), document title
          prefix on every chunk: "[Document: {title}] [Section: {header}]\n{text}"
  Excel — Document + sheet name prefix on every batch. Financial sheets (P&L,
          Balance Sheet, etc.) detect date-like column headers and add a summary
          line "Time periods covered: {cols}" at the top of each chunk.

Phase 2b outputs:
  - Table uc13.ingestion.chunks
  - Table uc13.ingestion.embeddings  (CDF enabled, workstream ARRAY<STRING>,
                                       priority_tier INT)

Dependencies:
  - uc13.classification.doc_relevance (written by 02_document_classifier.py)
  - Volume files under /Volumes/{catalog}/ingestion/raw_files/{company_name}/
  - python-docx, openpyxl (pre-installed via requirements.txt / cluster init)
  - MLflow endpoint: databricks-bge-large-en
  - Job parameters: sp_company_name, catalog, schema
"""

import csv
import hashlib
import json
import os
import re
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

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
# Chunk data model
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    file_name: str
    file_type: str
    relative_path: str
    chunk_index: int
    chunk_text: str
    section_header: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    tab: Optional[str] = None
    char_count: int = field(init=False)

    def __post_init__(self):
        self.char_count = len(self.chunk_text)


def make_doc_id(path: str) -> str:
    return hashlib.md5(path.encode()).hexdigest()


# ---------------------------------------------------------------------------
# PDF parser
# ---------------------------------------------------------------------------

_SKIP_ELEMENT_TYPES = {"page_footer", "page_number", "header"}
_HEADER_ELEMENT_TYPES = {"section_header", "title"}

# Regex to detect a date-column header (used in Excel financial sheet detection).
_DATE_HEADER_RE = re.compile(r"\d{4}|\w+ \d{4}|Q\d \d{4}", re.IGNORECASE)

# Keywords that mark a financial Excel sheet worth date-period annotation.
_FINANCIAL_SHEET_KEYWORDS = re.compile(
    r"p&l|profit.loss|income|balance sheet|cash flow|addback|ebitda|revenue|forecast",
    re.IGNORECASE,
)


def parse_pdf(file_path: str, doc_id: str, file_name: str, spark) -> list[Chunk]:
    """Parse a PDF using Databricks ai_parse_document.

    Every chunk is prefixed with "[Document: {title}] [Section: {header}]".
    When ai_parse_document returns a None section_header, the previous non-null
    header is carried forward so no chunk is context-free.
    """
    try:
        _df = spark.sql(f"""
            SELECT to_json(ai_parse_document(
                content,
                map('version', '2.0')
            )) AS parsed
            FROM read_files('{file_path}', format => 'binaryFile')
        """)
        _rows = _df.collect()
        if not _rows:
            print(f"  ⚠ Skipped (empty/unreadable file): {file_name}")
            return []
        row = _rows[0]["parsed"]

        result   = json.loads(row)
        elements = result["document"]["elements"]

        # Extract document title from the first title element.
        doc_title = next(
            (el["content"].strip() for el in elements if el.get("type") == "title"),
            Path(file_name).stem,
        )

        chunks: list[Chunk] = []
        current_header: Optional[str] = None
        last_known_header: Optional[str] = None
        current_texts: list[str] = []
        current_pages: list[int] = []
        chunk_index = 0

        def flush_chunk():
            nonlocal chunk_index
            if not current_texts:
                return
            text = "\n".join(current_texts).strip()
            if len(text) < 50:
                return
            effective_header = current_header or last_known_header or "Document body"
            chunk_text = (
                f"[Document: {doc_title}] [Section: {effective_header}]\n\n{text}"
            )
            chunks.append(Chunk(
                chunk_id=str(uuid.uuid4()),
                doc_id=doc_id,
                file_name=file_name,
                file_type="pdf",
                relative_path=file_path,
                chunk_index=chunk_index,
                chunk_text=chunk_text,
                section_header=effective_header,
                page_start=min(current_pages) + 1 if current_pages else None,
                page_end=max(current_pages) + 1 if current_pages else None,
            ))
            chunk_index += 1

        for el in elements:
            el_type = el.get("type", "")
            content = el.get("content", "").strip()
            page_id = el.get("page_id")

            if el_type in _SKIP_ELEMENT_TYPES or not content:
                continue

            if el_type in _HEADER_ELEMENT_TYPES:
                flush_chunk()
                current_header = content
                last_known_header = content
                current_texts  = []
                current_pages  = []
            else:
                current_texts.append(content)
                if page_id is not None:
                    current_pages.append(page_id)

        flush_chunk()
        print(f"  ✓ {file_name}: {len(chunks)} PDF chunks")
        return chunks

    except Exception as exc:
        print(f"  ✗ {file_name}: {exc}")
        return []


# ---------------------------------------------------------------------------
# Excel parser
# ---------------------------------------------------------------------------

def parse_excel(file_path: str, doc_id: str, file_name: str) -> list[Chunk]:
    """Parse an Excel workbook into chunks, one per sheet (or per 100-row batch).

    Each chunk is prefixed with "[Document: {file}] [Sheet: {sheet}] [Rows N-M]".
    Financial sheets (P&L, Balance Sheet, etc.) get an additional summary line
    listing date-like column headers so the retrieval model can anchor to periods.
    """
    import openpyxl

    chunks: list[Chunk] = []
    ROWS_PER_CHUNK = 100

    try:
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        chunk_index = 0

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            all_rows: list[list[str]] = []
            headers: Optional[list[str]] = None

            for row in ws.iter_rows(values_only=True):
                vals = [str(c) if c is not None else "" for c in row]
                if not any(v.strip() for v in vals):
                    continue
                if headers is None:
                    headers = vals
                    continue
                all_rows.append(vals)

            if not headers:
                continue

            # Detect date-like column headers for financial sheets.
            is_financial = bool(
                _FINANCIAL_SHEET_KEYWORDS.search(sheet_name)
                or _FINANCIAL_SHEET_KEYWORDS.search(file_name)
            )
            date_cols = [h for h in headers if _DATE_HEADER_RE.search(h)]
            date_summary = (
                f"Time periods covered: {', '.join(date_cols)}\n"
                if is_financial and date_cols
                else ""
            )

            batches = [all_rows] if len(all_rows) <= ROWS_PER_CHUNK else [
                all_rows[s : s + ROWS_PER_CHUNK]
                for s in range(0, len(all_rows), ROWS_PER_CHUNK)
            ]

            for batch_idx, batch in enumerate(batches):
                start_row = batch_idx * ROWS_PER_CHUNK + 1
                end_row   = start_row + len(batch) - 1
                row_range = f"Rows {start_row}–{end_row}"

                header_line = "Headers: " + " | ".join(headers)
                data_lines  = [header_line]
                for row in batch:
                    row_str = " | ".join(
                        f"{headers[i]}: {row[i]}"
                        for i in range(min(len(headers), len(row)))
                        if row[i].strip()
                    )
                    if row_str:
                        data_lines.append(row_str)

                chunk_text = (
                    f"[Document: {file_name}] [Sheet: {sheet_name}] [{row_range}]\n"
                    f"{date_summary}"
                    + "\n".join(data_lines)
                )
                chunks.append(Chunk(
                    chunk_id=str(uuid.uuid4()),
                    doc_id=doc_id,
                    file_name=file_name,
                    file_type="xlsx",
                    relative_path=file_path,
                    chunk_index=chunk_index,
                    chunk_text=chunk_text,
                    section_header=f"Sheet: {sheet_name} {row_range}",
                    tab=sheet_name,
                ))
                chunk_index += 1

        print(f"  ✓ {file_name}: {len(chunks)} Excel chunks")
    except Exception as exc:
        print(f"  ✗ {file_name}: {exc}")

    return chunks


# ---------------------------------------------------------------------------
# Word parser
# ---------------------------------------------------------------------------

def parse_word(file_path: str, doc_id: str, file_name: str) -> list[Chunk]:
    """Parse a Word document, splitting on Heading styles."""
    from docx import Document

    chunks: list[Chunk] = []
    chunk_index = 0
    current_header: Optional[str] = None
    current_texts: list[str] = []

    def flush_chunk():
        nonlocal chunk_index
        if not current_texts:
            return
        text = "\n".join(current_texts).strip()
        if len(text) < 50:
            return
        chunk_text = f"{current_header}\n\n{text}" if current_header else text
        chunks.append(Chunk(
            chunk_id=str(uuid.uuid4()),
            doc_id=doc_id,
            file_name=file_name,
            file_type="docx",
            relative_path=file_path,
            chunk_index=chunk_index,
            chunk_text=chunk_text,
            section_header=current_header,
        ))
        chunk_index += 1

    try:
        doc = Document(file_path)
        for para in doc.paragraphs:
            if not para.text.strip():
                continue
            if para.style.name.startswith("Heading"):
                flush_chunk()
                current_header = para.text.strip()
                current_texts  = []
            else:
                current_texts.append(para.text.strip())
        flush_chunk()
        print(f"  ✓ {file_name}: {len(chunks)} Word chunks")
    except Exception as exc:
        print(f"  ✗ {file_name}: {exc}")

    return chunks


# ---------------------------------------------------------------------------
# CSV parser
# ---------------------------------------------------------------------------

def parse_csv(file_path: str, doc_id: str, file_name: str) -> list[Chunk]:
    """Parse a CSV file in 50-row batches."""
    chunks: list[Chunk] = []
    BATCH_SIZE = 50
    chunk_index = 0

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
            rows = list(csv.reader(fh))
        if not rows:
            return chunks

        headers = rows[0]
        for start in range(1, len(rows), BATCH_SIZE):
            batch = rows[start : start + BATCH_SIZE]
            lines = ["Headers: " + " | ".join(headers)]
            for row in batch:
                row_str = " | ".join(
                    f"{headers[i]}: {row[i]}"
                    for i in range(min(len(headers), len(row)))
                    if row[i].strip()
                )
                if row_str:
                    lines.append(row_str)

            chunk_text = "\n".join(lines)
            chunks.append(Chunk(
                chunk_id=str(uuid.uuid4()),
                doc_id=doc_id,
                file_name=file_name,
                file_type="csv",
                relative_path=file_path,
                chunk_index=chunk_index,
                chunk_text=chunk_text,
                section_header=f"Rows {start}–{start + len(batch) - 1}",
            ))
            chunk_index += 1

        print(f"  ✓ {file_name}: {len(chunks)} CSV chunks ({len(rows) - 1} rows)")
    except Exception as exc:
        print(f"  ✗ {file_name}: {exc}")

    return chunks


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".xlsm", ".docx", ".doc", ".csv"}


def parse_file(file_path: str, spark) -> list[Chunk]:
    file_name = os.path.basename(file_path)
    ext       = Path(file_name).suffix.lower()
    doc_id    = make_doc_id(file_path)

    if ext == ".pdf":
        return parse_pdf(file_path, doc_id, file_name, spark)
    elif ext in {".xlsx", ".xls", ".xlsm"}:
        return parse_excel(file_path, doc_id, file_name)
    elif ext in {".docx", ".doc"}:
        return parse_word(file_path, doc_id, file_name)
    elif ext == ".csv":
        return parse_csv(file_path, doc_id, file_name)
    else:
        print(f"  — skipped unsupported type: {file_name}")
        return []


# ---------------------------------------------------------------------------
# Embedding helper
# ---------------------------------------------------------------------------

def get_embeddings_batch(texts: list[str], client, endpoint: str, batch_size: int = 20) -> list:
    """Generate embeddings in batches, truncating each text to 8 000 chars
    to stay within the BGE Large token limit (~32 K chars ≈ 8 K tokens)."""
    embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = [t[:8000] for t in texts[i : i + batch_size]]
        response = client.predict(endpoint=endpoint, inputs={"input": batch})
        embeddings.extend([item["embedding"] for item in response["data"]])
        if i % 100 == 0:
            print(f"  Embedded {i}/{len(texts)} chunks...")
    return embeddings


# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------

def main():
    repo_root = find_repo_root()
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    print("repo_root:", repo_root)

    company_name       = get_param("sp_company_name")
    catalog            = get_param("catalog",  default="uc13")
    schema             = get_param("schema",   default="ingestion")
    embedding_endpoint = get_param("embedding_endpoint", default="databricks-bge-large-en")

    # parse_priority_tiers: "all" | "1" | "2" | "3" | "1,2" | "1,2,3" etc.
    parse_tiers_raw = get_param("parse_priority_tiers", default="all").strip().lower()
    if parse_tiers_raw == "all":
        tier_filter = ""
        tier_label  = "all tiers"
    else:
        tiers = [t.strip() for t in parse_tiers_raw.split(",") if t.strip().isdigit()]
        tier_filter = f"AND priority_tier IN ({', '.join(tiers)})"
        tier_label  = f"tier(s) {', '.join(tiers)}"

    volume_path      = f"/Volumes/{catalog}/{schema}/raw_files/{company_name}"
    table_relevance  = f"{catalog}.classification.doc_relevance"
    table_chunks     = f"{catalog}.{schema}.chunks"
    table_embeddings = f"{catalog}.{schema}.embeddings"

    from pyspark.sql import SparkSession as _SparkSession
    _spark = _SparkSession.getActiveSession()
    if _spark is None:
        raise RuntimeError("No active Spark session. This script must run on a Databricks cluster.")

    print(f"\n=== UC13 Phase 2b — Ingestion Parser ({company_name}) ===")
    print(f"Volume     : {volume_path}")
    print(f"Parsing    : {tier_label}")

    # --- Ensure output tables exist ---
    _spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
    _spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {table_chunks} (
            company_name   STRING,
            chunk_id       STRING,
            doc_id         STRING,
            file_name      STRING,
            file_type      STRING,
            relative_path  STRING,
            chunk_index    INT,
            chunk_text     STRING,
            section_header STRING,
            page_start     INT,
            page_end       INT,
            tab            STRING,
            char_count     INT,
            created_at     TIMESTAMP
        ) USING DELTA
    """)
    _spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {table_embeddings} (
            company_name  STRING,
            chunk_id      STRING NOT NULL,
            doc_id        STRING,
            file_name     STRING,
            workstream    ARRAY<STRING>,
            priority_tier INT,
            embedding     ARRAY<FLOAT>,
            created_at    TIMESTAMP
        ) USING DELTA
        TBLPROPERTIES (
            'delta.enableChangeDataFeed'         = 'true',
            'delta.deletedFileRetentionDuration' = 'interval 30 days'
        )
    """)

    # --- Read files approved by classifier, lowest tier number first (1 = highest value) ---
    approved_rows = _spark.sql(f"""
        SELECT filename AS file_name, folder_path, workstream, priority_tier
        FROM {table_relevance}
        WHERE should_parse = true
          AND company_name = '{company_name}'
          {tier_filter}
        ORDER BY priority_tier ASC NULLS LAST
    """).collect()

    relevance_map = {
        r.file_name: {"workstream": list(r.workstream or []), "priority_tier": r.priority_tier}
        for r in approved_rows
    }

    file_paths = [
        os.path.join(volume_path, row.folder_path, row.file_name)
        if row.folder_path not in ("", ".", None)
        else os.path.join(volume_path, row.file_name)
        for row in approved_rows
    ]
    file_paths = [
        p for p in file_paths
        if os.path.exists(p) and Path(p).suffix.lower() in _ALLOWED_EXTENSIONS
    ]
    print(f"Files to parse: {len(file_paths)}")

    # --- Parse ---
    all_chunks: list[Chunk] = []
    for file_path in file_paths:
        chunks = parse_file(file_path, _spark)
        all_chunks.extend(chunks)

    print(f"\nTotal chunks: {len(all_chunks)}")
    print(f"Total characters: {sum(c.char_count for c in all_chunks):,}")

    if not all_chunks:
        print("No chunks generated — exiting.")
        return

    # --- Save chunks ---
    from pyspark.sql import Row
    from pyspark.sql.types import (
        StructType, StructField, StringType, IntegerType, BooleanType,
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
            page_start=int(c.page_start) if c.page_start is not None else None,
            page_end=int(c.page_end) if c.page_end is not None else None,
            tab=c.tab, char_count=int(c.char_count), created_at=now,
        )
        for c in all_chunks
    ]
    df_chunks = _spark.createDataFrame(chunk_rows, schema=chunk_schema)
    # Replace this company's chunks so re-runs are idempotent.
    try:
        _spark.sql(f"DELETE FROM {table_chunks} WHERE company_name = '{company_name}'")
    except Exception:
        pass
    df_chunks.write.mode("append").option("mergeSchema", "true").saveAsTable(table_chunks)
    print(f"✓ Saved {df_chunks.count()} chunks → {table_chunks}")

    # --- Generate and save embeddings ---
    import mlflow.deployments

    client = mlflow.deployments.get_deploy_client("databricks")
    texts  = [c.chunk_text for c in all_chunks]
    print(f"\nGenerating embeddings for {len(texts)} chunks...")
    embeddings = get_embeddings_batch(texts, client, embedding_endpoint)
    print(f"Generated {len(embeddings)} embeddings")

    emb_schema = StructType([
        StructField("company_name",  StringType(),           False),
        StructField("chunk_id",      StringType(),           False),
        StructField("doc_id",        StringType(),           False),
        StructField("file_name",     StringType(),           False),
        StructField("workstream",    ArrayType(StringType()), True),
        StructField("priority_tier", IntegerType(),          True),
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
            embedding=[float(x) for x in embeddings[i]],
            created_at=now,
        )
        for i in range(len(all_chunks))
    ]
    df_emb = _spark.createDataFrame(emb_rows, schema=emb_schema)
    # Replace this company's embeddings so re-runs are idempotent.
    try:
        _spark.sql(f"DELETE FROM {table_embeddings} WHERE company_name = '{company_name}'")
    except Exception:
        pass
    df_emb.write.mode("append").option("mergeSchema", "true").saveAsTable(table_embeddings)
    print(f"✓ Saved {df_emb.count()} embeddings → {table_embeddings}")

    # --- Trigger vector search index sync ---
    index_name = f"{catalog}.{schema}.embeddings_index"
    try:
        from databricks.sdk import WorkspaceClient
        import time

        w = WorkspaceClient()
        w.vector_search_indexes.sync_index(index_name=index_name)
        print(f"\nVector search sync triggered → {index_name}")
        print("Waiting for sync to complete (checks every 30s)...")

        while True:
            idx    = w.vector_search_indexes.get_index(index_name=index_name)
            ready  = idx.status.ready
            msg    = idx.status.message or ""
            print(f"  status: ready={ready}  {msg}")
            if ready:
                print(f"✓ Index ready — {index_name}")
                break
            time.sleep(30)
    except Exception as e:
        print(f"⚠ Could not sync vector index ({e}). Run sync manually before using semantic_search.")


if __name__ == "__main__":
    main()
