"""
04_company_profiler.py — Phase 2b: Company Profiler (runs in parallel with parser).

Uses semantic search to retrieve relevant document chunks for each profiling
dimension, calls the LLM to extract a structured company profile, and saves
results to uc13.classification.company_profile.

Key constraints:
  - company_name ALWAYS comes from the runtime parameter sp_company_name.
    Documents frequently contain [REDACTED] in place of the company name
    (standard anonymisation in banked processes), so LLM-extracted names are
    unreliable and must never be used.
  - banked/non-banked detection is done by checking doc_relevance BEFORE the
    LLM call, not by asking the LLM.
  - When no chunks are found for a profile dimension after all filters, the
    field is recorded as null and the gap is appended to data_room_gaps.

Phase 2b output:
  - Table uc13.classification.company_profile

Dependencies:
  - uc13.classification.doc_relevance (written by 02_document_classifier.py)
  - uc13.ingestion.chunks + uc13.ingestion.embeddings_index
  - agents/shared/retrieval.py
  - MLflow endpoints: databricks-bge-large-en, databricks-meta-llama-3-3-70b-instruct
  - Job parameters: sp_company_name, catalog, schema
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Secrets / params helpers
# ---------------------------------------------------------------------------

def _load_dotenv_if_local():
    try:
        dbutils  # noqa: F821
    except NameError:
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

_load_dotenv_if_local()


def get_secret(key: str) -> str:
    try:
        return dbutils.secrets.get("uc13", key)  # noqa: F821
    except NameError:
        value = os.environ.get(key)
        if value is None:
            raise RuntimeError(
                f"Secret '{key}' not found. "
                "On Databricks: add it to the 'uc13' secrets scope. "
                "Locally: add it to your .env file or export it as an env var."
            )
        return value


def get_param(key: str, default: str = None) -> str:
    try:
        value = dbutils.widgets.get(key)  # noqa: F821
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
# Retrieval dimension config
# ---------------------------------------------------------------------------

# Each entry: (query, file_name_filter, workstream_filter)
_PROFILING_QUERIES: dict[str, tuple[str, list[str], list[str]]] = {
    "industry_overlay": (
        "industry sector service type end market vertical",
        ["CIM", "Business", "Overview", "Summary", "Profile"],
        ["BUSINESS_MODEL"],
    ),
    "revenue_model": (
        "revenue model contract type recurring revenue subscription retainer",
        ["CIM", "Business", "Overview", "Summary", "Profile"],
        ["BUSINESS_MODEL"],
    ),
    "business_description": (
        "company description what the company does services offered overview",
        ["CIM", "Business", "Overview", "Summary", "Profile"],
        ["BUSINESS_MODEL"],
    ),
    "company_size_indicators": (
        "revenue headcount EBITDA gross margin employees size scale",
        ["CIM", "Financial", "P&L", "Profit", "EBITDA"],
        ["FINANCIAL", "BUSINESS_MODEL"],
    ),
    "deal_type": (
        "buyout growth equity recapitalization transaction type deal structure",
        ["CIM", "Business", "Overview", "Summary"],
        ["BUSINESS_MODEL"],
    ),
    "banked_vs_nonbanked": (
        "CIM offering memorandum banker investment bank process",
        ["CIM", "Offering", "OM"],
        ["BUSINESS_MODEL"],
    ),
    "vertical_subsector": (
        "sub-sector specialty product lines service lines niche segment",
        ["CIM", "Business", "Overview", "Summary", "Profile"],
        ["BUSINESS_MODEL"],
    ),
}


# ---------------------------------------------------------------------------
# Banked detection (pre-LLM, from doc_relevance)
# ---------------------------------------------------------------------------

def detect_banked(spark, table_relevance: str, company_name: str) -> tuple[bool, str | None]:
    """Check doc_relevance for CIM/OM presence before calling the LLM.

    Returns (banked: bool, note: str | None).
    """
    _CIM_KEYWORDS = re.compile(
        r"\bcim\b|offering memorandum|\bom\b|confidential information memorandum",
        re.IGNORECASE,
    )
    try:
        filenames = [
            row.filename
            for row in spark.sql(f"""
                SELECT filename FROM {table_relevance}
                WHERE array_contains(workstream, 'BUSINESS_MODEL')
                  AND company_name = '{company_name}'
            """).collect()
        ]
        if any(_CIM_KEYWORDS.search(f) for f in filenames):
            return True, None
    except Exception:
        pass

    return False, (
        "Reduced confidence across all sections — no CIM found. "
        "Profile based on available documents only."
    )


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def call_llm(client, endpoint: str, prompt: str) -> str:
    response = client.predict(
        endpoint=endpoint,
        inputs={
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1500,
            "temperature": 0.0,
        },
    )
    return response["choices"][0]["message"]["content"].strip()


# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------

def main():
    repo_root = find_repo_root()
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    print("repo_root:", repo_root)

    from agents.shared.retrieval import semantic_search

    # Never trust LLM output for company_name — documents may contain [REDACTED].
    company_name       = get_param("sp_company_name")
    catalog            = get_param("catalog",  default="uc13")
    schema             = get_param("schema",   default="ingestion")
    embedding_endpoint = get_param("embedding_endpoint", default="databricks-bge-large-en")
    llm_endpoint       = get_param("llm_endpoint",       default="databricks-meta-llama-3-3-70b-instruct")

    table_relevance = f"{catalog}.classification.doc_relevance"
    table_profile   = f"{catalog}.classification.company_profile"

    try:
        _spark = spark  # noqa: F821
    except NameError:
        raise RuntimeError("'spark' is not defined. This script must run on a Databricks cluster.")

    print(f"\n=== UC13 Phase 2b — Company Profiler ({company_name}) ===")

    # --- Ensure output table exists ---
    _spark.sql("CREATE SCHEMA IF NOT EXISTS uc13.classification")
    _spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {table_profile} (
            company_name            STRING,
            industry_overlay        STRING,
            overlay_confidence      STRING,
            revenue_model           STRING,
            revenue_model_note      STRING,
            business_description    STRING,
            company_size_indicators STRING,
            deal_type               STRING,
            banked                  BOOLEAN,
            banked_note             STRING,
            vertical_subsector      STRING,
            data_room_gaps          ARRAY<STRING>,
            created_at              TIMESTAMP
        ) USING DELTA
    """)

    # --- Detect banked/non-banked from classifier output (no LLM needed) ---
    banked, banked_note = detect_banked(_spark, table_relevance, company_name)
    print(f"Banked: {banked}" + (f" — {banked_note}" if banked_note else ""))

    # --- Retrieve context for each profiling dimension ---
    import mlflow.deployments
    client = mlflow.deployments.get_deploy_client("databricks")

    retrieved_context: dict[str, str] = {}
    data_room_gaps: list[str] = []

    for dimension, (query, fn_filter, ws_filter) in _PROFILING_QUERIES.items():
        chunks = semantic_search(
            query=query,
            spark=_spark,
            top_k=5,
            file_name_filter=fn_filter,
            workstream_filter=ws_filter,
            tier_filter=True,
            min_chunk_length=100,
            embedding_endpoint=embedding_endpoint,
        )

        if not chunks:
            # Try again without the tier filter to widen the net.
            chunks = semantic_search(
                query=query,
                spark=_spark,
                top_k=5,
                file_name_filter=fn_filter,
                workstream_filter=ws_filter,
                min_chunk_length=100,
                embedding_endpoint=embedding_endpoint,
            )

        if chunks:
            retrieved_context[dimension] = "\n---\n".join([
                f"[Source: {c.file_name} | Section: {c.section_header or 'N/A'}]\n{c.chunk_text[:800]}"
                for c in chunks
            ])
            print(f"  ✓ {dimension}: {len(chunks)} chunks")
        else:
            retrieved_context[dimension] = ""
            gap_label = {
                "industry_overlay":        "No CIM or Business Overview found",
                "revenue_model":           "No revenue model documentation found",
                "business_description":    "No CIM or Overview found",
                "company_size_indicators": "No financial or CIM document found",
                "deal_type":               "No CIM or deal documentation found",
                "banked_vs_nonbanked":     "No CIM or Offering Memorandum found",
                "vertical_subsector":      "No CIM or business description found",
            }.get(dimension, f"No content found for {dimension}")
            data_room_gaps.append(gap_label)
            print(f"  ✗ {dimension}: no chunks — recorded as gap")

    # --- Build LLM prompt ---
    # Only include dimensions that have retrieved context.
    context_parts = []
    for dimension, context in retrieved_context.items():
        if context:
            context_parts.append(f"## {dimension.upper()}\n{context[:800]}")

    full_context = "\n\n========\n\n".join(context_parts)

    # company_name is injected explicitly — the LLM must NOT generate it.
    json_template = """{
  "industry_overlay": "one of: tech_services, healthcare_services, b2b_saas, industrial_manufacturing, consumer_dtc, other",
  "overlay_confidence": "high | medium | low",
  "revenue_model": "one of: pure_recurring, repeat_services, project_based, transactional, usage_based, licensing, marketplace, hybrid",
  "revenue_model_note": "free text — % split or explanation if stated in documents",
  "business_description": "2-3 sentence structured description of what the company does and how it operates",
  "company_size_indicators": "revenue, headcount, and EBITDA as extracted verbatim — do not compute or infer",
  "deal_type": "one of: buyout, growth_equity, recapitalization, unknown",
  "vertical_subsector": "specific sub-sector within the overlay (e.g. home_care, IT_staffing, behavioral_health)"
}"""

    prompt = (
        "You are a private equity analyst building a structured company profile "
        "from due diligence documents.\n\n"
        "IMPORTANT:\n"
        "- Do NOT generate the company name. It is provided by the system.\n"
        "- Use only information found in the documents below.\n"
        "- If a field cannot be determined from the documents, use null.\n"
        "- For industry_overlay, the two primary overlays are:\n"
        "    tech_services     — tech-enabled services, IT services, digital services\n"
        "    healthcare_services — physician practices, home care, hospice, behavioral "
        "health, dental, dermatology\n"
        "  Secondary overlays: b2b_saas, industrial_manufacturing, consumer_dtc.\n"
        "  Use 'other' only when none clearly match.\n"
        "- For company_size_indicators, quote the numbers as stated — do not compute.\n\n"
        "Return ONLY a valid JSON object matching this template (no markdown):\n"
        + json_template
        + "\n\nDue Diligence Documents:\n"
        + full_context[:12000]
    )

    print(f"\nLLM context length: {len(full_context)} chars")
    raw_text = call_llm(client, llm_endpoint, prompt)
    clean_text = re.sub(r"```json\s*|\s*```", "", raw_text).strip()

    try:
        profile: dict[str, Any] = json.loads(clean_text)
        print("✓ Profile extracted:")
        for k, v in profile.items():
            print(f"  {k:<28} {v}")
    except Exception as exc:
        print(f"Parse error: {exc}\nRaw: {raw_text[:500]}")
        profile = {}

    # --- Save to Delta ---
    from pyspark.sql import Row
    from pyspark.sql.types import (
        StructType, StructField, StringType, BooleanType,
        ArrayType, TimestampType,
    )

    save_schema = StructType([
        StructField("company_name",            StringType(),           True),
        StructField("industry_overlay",        StringType(),           True),
        StructField("overlay_confidence",      StringType(),           True),
        StructField("revenue_model",           StringType(),           True),
        StructField("revenue_model_note",      StringType(),           True),
        StructField("business_description",    StringType(),           True),
        StructField("company_size_indicators", StringType(),           True),
        StructField("deal_type",               StringType(),           True),
        StructField("banked",                  BooleanType(),          True),
        StructField("banked_note",             StringType(),           True),
        StructField("vertical_subsector",      StringType(),           True),
        StructField("data_room_gaps",          ArrayType(StringType()), True),
        StructField("created_at",              TimestampType(),        True),
    ])

    # Never trust LLM output for company_name — documents may contain [REDACTED].
    row = Row(
        company_name=company_name,
        industry_overlay=profile.get("industry_overlay"),
        overlay_confidence=profile.get("overlay_confidence"),
        revenue_model=profile.get("revenue_model"),
        revenue_model_note=profile.get("revenue_model_note"),
        business_description=profile.get("business_description"),
        company_size_indicators=profile.get("company_size_indicators"),
        deal_type=profile.get("deal_type"),
        banked=banked,
        banked_note=banked_note,
        vertical_subsector=profile.get("vertical_subsector"),
        data_room_gaps=data_room_gaps if data_room_gaps else None,
        created_at=datetime.now(timezone.utc),
    )

    df = _spark.createDataFrame([row], schema=save_schema)

    # Upsert: replace this company's profile row, preserve all other companies.
    from delta.tables import DeltaTable
    delta_tbl = DeltaTable.forName(_spark, table_profile)
    (
        delta_tbl.alias("t")
        .merge(df.alias("s"), "t.company_name = s.company_name")
        .whenMatchedUpdateAll()
        .whenNotMatchedInsertAll()
        .execute()
    )
    print(f"\n✓ Profile saved → {table_profile}")

    if data_room_gaps:
        print(f"\nData room gaps ({len(data_room_gaps)}):")
        for gap in data_room_gaps:
            print(f"  ! {gap}")


if __name__ == "__main__":
    main()
