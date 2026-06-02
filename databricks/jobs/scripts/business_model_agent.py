"""
business_model_agent.py — Phase 3: Business Model Workstream Agent.

Extracts the business model profile of the target company from documents tagged
BUSINESS_MODEL. Produces one revenue model durability rating (Green/Yellow/Red)
and a structured company description. Writes output to uc13.analysis.business_model.

Runs in parallel with financial_trends_agent.py after company_profiler.py completes.

Phase 3 outputs:
  - Table uc13.analysis.business_model

Dependencies:
  - uc13.ingestion.embeddings          (written by ingestion_parser.py)
  - uc13.classification.doc_relevance  (written by document_classifier.py)
  - uc13.classification.company_profile (written by company_profiler.py)
  - agents.shared.retrieval.semantic_search
  - agents.shared.agent_base.WorkstreamAgent
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Secrets / params helpers — copied verbatim from ingestion_parser.py
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
# Repo root resolver — copied verbatim from ingestion_parser.py
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
# Agent implementation
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a senior PE investment analyst extracting structured business model
information from due diligence documents. Rules:
1. Extract ONLY what is explicitly stated in the provided context.
2. Do NOT infer, compute, assume, or hallucinate any value.
3. If a value is absent from the context, return null for that field.
4. Every extracted value must have a citation: document name, location
   (page number or section title), and a quote of ≤30 words.
5. Return ONLY valid JSON with no preamble and no markdown fences.\
"""

_USER_PROMPT_TEMPLATE = """\
COMPANY PROFILE (from Phase 2 output):
{company_profile_json}

RETRIEVED DOCUMENT CONTEXT:
{combined_chunk_text}

Extract the business model fields and return this exact JSON structure:
{{
  "revenue_model_tag": "<tag or null>",
  "revenue_model_pct_split": "<stated split or null>",
  "revenue_model_note": "<brief explanation>",
  "products_services": [
    {{
      "name": "<product or service line name>",
      "revenue_pct": "<% as stated or null>",
      "gm_pct": "<gross margin % as stated or null>",
      "growth_note": "<growth rate or description as stated or null>"
    }}
  ],
  "customer_segments": "<description of end markets and customer sizes or null>",
  "sales_motion": "<tag or null>",
  "sales_motion_note": "<transitioning note or null>",
  "revenue_visibility": {{
    "contracted_pct_of_forward_12mo": "<% as stated or null>",
    "backlog_coverage_months": "<months as stated or null>"
  }},
  "key_dependencies": ["<dependency 1>", "<dependency 2>"],
  "recent_model_changes": ["<change 1 with approximate date>", "<change 2>"],
  "citations": [
    {{
      "field": "<field_name>",
      "document": "<exact filename>",
      "location": "<page number, section title, or tab name>",
      "quote": "<≤30 word direct quote from context>",
      "confidence": "<high|medium|low>"
    }}
  ],
  "executive_summary": "<2-3 sentence factual summary of the company's revenue model, primary service lines, and key revenue characteristics. Write only what is stated in the context. Do not include a rating or verdict — describe the model factually so a reader understands the business at a glance.>",
  "extraction_notes": "<note any ambiguities, missing data, or conflicting statements>"
}}\
"""

_VALID_REVENUE_TAGS = {
    "pure_recurring", "repeat_services", "project_based", "transactional",
    "usage_based", "licensing", "marketplace", "hybrid",
}

_VALID_SALES_MOTIONS = {
    "founder_led", "enterprise_sales", "channel_partner",
    "inbound_plg", "outbound", "marketplace",
}


class BusinessModelAgent:
    """Phase 3 Business Model workstream agent.

    Orchestrates: tool calls → single LLM call → deterministic flag evaluation
    → Delta write. Extends WorkstreamAgent for trace/flag infrastructure.
    """

    agent_name = "business_model"

    def __init__(self):
        from agents.shared.agent_base import WorkstreamAgent
        # Inherit instance state from base without Python MRO complexity —
        # composition so the import path remains explicit.
        self._base = WorkstreamAgent.__new__(WorkstreamAgent)
        WorkstreamAgent.__init__(self._base)
        # Expose base methods directly on self for ergonomics.
        self._tool_call   = self._base._tool_call
        self._call_llm    = self._base._call_llm
        self._parse_json_response = self._base._parse_json_response
        self._add_flag    = self._base._add_flag
        self._add_citation = self._base._add_citation
        self._add_gap     = self._base._add_gap
        self._reset_state = self._base._reset_state
        self._flags_as_dicts = self._base._flags_as_dicts
        self._citations_as_dicts = self._base._citations_as_dicts

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    def _tool_retrieve_business_model_context(self, spark):
        from agents.shared.retrieval import semantic_search
        chunks = semantic_search(
            query="company overview business model products services what does this company do",
            spark=spark,
            top_k=10,
            workstream_filter=["BUSINESS_MODEL"],
            file_name_filter=["CIM", "Business", "Overview", "Summary", "Profile",
                              "OM", "Offering", "Memorandum", "Deck", "Presentation"],
            min_chunk_length=150,
        )
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_business_model_context",
            input_summary="query=company overview business model; workstream=BUSINESS_MODEL; top_k=10",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_retrieve_revenue_model_detail(self, spark):
        from agents.shared.retrieval import semantic_search
        chunks = semantic_search(
            query="recurring revenue subscription contract retention repeat revenue percentage split",
            spark=spark,
            top_k=8,
            workstream_filter=["BUSINESS_MODEL", "FINANCIAL"],
            file_name_filter=["CIM", "Business", "Model", "Revenue", "Contract"],
            min_chunk_length=150,
        )
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_revenue_model_detail",
            input_summary="query=recurring revenue subscription contract; workstream=BUSINESS_MODEL,FINANCIAL; top_k=8",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_retrieve_sales_and_growth(self, spark):
        from agents.shared.retrieval import semantic_search
        chunks = semantic_search(
            query="sales motion go to market pipeline growth strategy new customers acquisition",
            spark=spark,
            top_k=6,
            workstream_filter=["BUSINESS_MODEL", "KPI_OPS"],
            file_name_filter=["CIM", "Business", "Sales", "GTM", "Pipeline", "Growth"],
            min_chunk_length=150,
        )
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_sales_and_growth",
            input_summary="query=sales motion go to market pipeline growth; workstream=BUSINESS_MODEL,KPI_OPS; top_k=6",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_load_company_profile(self, company_name: str, spark):
        rows = spark.sql(f"""
            SELECT * FROM uc13.classification.company_profile
            WHERE company_name = '{company_name}'
            ORDER BY created_at DESC LIMIT 1
        """).collect()
        if not rows:
            self._add_gap("company_profile not found — run company_profiler.py first")
            return self._tool_call(
                tool_name="load_company_profile",
                input_summary=f"SQL read company_profile WHERE company_name='{company_name}'",
                data=None,
                output_summary="No company profile found — overlay check skipped",
                confidence="low",
                source_docs=[],
            )
        row = rows[0]
        profile_dict = row.asDict()
        return self._tool_call(
            tool_name="load_company_profile",
            input_summary=f"SQL read company_profile WHERE company_name='{company_name}'",
            data=profile_dict,
            output_summary=f"Profile loaded: industry_overlay={profile_dict.get('industry_overlay')}",
            confidence="high",
            source_docs=["uc13.classification.company_profile"],
        )

    # ------------------------------------------------------------------
    # Revenue model durability flag — deterministic Python logic
    # ------------------------------------------------------------------

    def _apply_revenue_durability_flag(
        self,
        revenue_model_tag: Optional[str],
        revenue_model_pct_split: Optional[str],
        source_doc: str,
    ) -> tuple[str, str, str]:
        """Return (severity, flag_confidence, flag_rule_applied).

        Logic is applied deterministically in Python — the LLM is not involved.
        """
        tag = (revenue_model_tag or "").lower().strip()
        split_text = (revenue_model_pct_split or "").lower()

        # Attempt to parse a recurring % from the stated split string.
        recurring_pct: Optional[float] = None
        import re
        numbers = re.findall(r"(\d+(?:\.\d+)?)\s*%", split_text)
        if numbers:
            # Heuristic: if the split says "70% recurring, 30% project", the first
            # number after words like "recurring" or "contracted" is our signal.
            recurring_match = re.search(
                r"(\d+(?:\.\d+)?)\s*%\s*(?:recurring|contracted|subscription)",
                split_text,
            )
            if recurring_match:
                recurring_pct = float(recurring_match.group(1))
            else:
                # No directional label — take the first number as a best-effort proxy.
                recurring_pct = float(numbers[0])

        # Determine flag_confidence.
        if recurring_pct is not None:
            flag_confidence = "high"
        elif tag in ("pure_recurring", "repeat_services", "project_based",
                     "transactional", "usage_based", "licensing", "marketplace", "hybrid"):
            flag_confidence = "medium"
        else:
            flag_confidence = "low"

        # Apply the threshold logic.
        RECURRING_TAGS = {"pure_recurring", "usage_based", "licensing"}
        REPEAT_TAGS    = {"repeat_services"}
        PROJECT_TAGS   = {"project_based", "transactional"}

        if recurring_pct is not None:
            if recurring_pct >= 70:
                severity = "Green"
                rule = "≥70% recurring or contracted revenue stated in source document"
            elif recurring_pct >= 40:
                severity = "Yellow"
                rule = "40–70% recurring/contracted revenue stated in source document"
            else:
                severity = "Red"
                rule = (
                    "<40% recurring/contracted AND no demonstrated repeat-rate. "
                    "Not necessarily a deal-killer, but usually deserves a flag — "
                    "project-driven revenue raises questions about revenue durability "
                    "and sales engine maturity."
                )
        elif tag in RECURRING_TAGS:
            severity = "Green"
            rule = "Revenue model tag indicates recurring/contracted revenue; no explicit % stated"
        elif tag in REPEAT_TAGS:
            severity = "Yellow"
            rule = (
                "Repeat-services model with informal but stated strong customer relationships. "
                "No explicit recurring % stated."
            )
        elif tag in PROJECT_TAGS:
            severity = "Red"
            rule = (
                "Revenue is described as mostly one-time project work. "
                "Not necessarily a deal-killer, but usually deserves a flag — "
                "project-driven revenue raises questions about revenue durability "
                "and sales engine maturity."
            )
        elif tag == "hybrid":
            severity = "Yellow"
            rule = "Hybrid model — recurring component unclear without stated %"
        else:
            severity = "Yellow"
            rule = "Revenue model tag unclear or not extractable from documents"

        return severity, flag_confidence, rule

    # ------------------------------------------------------------------
    # Industry overlay conflict check
    # ------------------------------------------------------------------

    def _check_overlay_conflict(
        self,
        extracted: dict,
        profile: Optional[dict],
    ) -> tuple[bool, str]:
        """Compare extracted revenue model against company_profile industry overlay.

        Returns (conflict: bool, conflict_note: str).
        """
        if profile is None:
            return False, ""

        overlay = (profile.get("industry_overlay") or "").lower()
        revenue_tag = (extracted.get("revenue_model_tag") or "").lower()
        segments = (extracted.get("customer_segments") or "").lower()

        conflict = False
        notes = []

        # Healthcare overlay but extracted segments look like software/SaaS.
        if "healthcare" in overlay:
            sw_keywords = ("software", "saas", "subscription", "platform", "api",
                           "cloud", "digital", "technology", "enterprise software")
            if any(k in segments for k in sw_keywords):
                conflict = True
                notes.append(
                    f"Industry overlay is '{overlay}' but extracted customer segments "
                    f"describe software/SaaS-type customers ('{segments[:80]}...'). "
                    "This may indicate a health-tech hybrid or misclassification."
                )

        # Tech services overlay but extracted model tag is project-based.
        if "tech" in overlay and revenue_tag == "project_based":
            conflict = True
            notes.append(
                f"Industry overlay is '{overlay}' but revenue model is project-based. "
                "Premium tech services platforms typically have higher recurring revenue ratios."
            )

        # Software overlay but healthcare-specific segments.
        if "tech" in overlay or "software" in overlay:
            health_keywords = ("patient", "clinical", "physician", "hospital",
                               "health system", "payor", "reimbursement", "medicare")
            if any(k in segments for k in health_keywords):
                conflict = True
                notes.append(
                    f"Industry overlay is '{overlay}' but extracted segments describe "
                    f"healthcare-specific customers. Overlay may need revision."
                )

        note_str = " | ".join(notes) if notes else ""
        return conflict, note_str

    # ------------------------------------------------------------------
    # Main run() orchestration
    # ------------------------------------------------------------------

    def run(self, company_name: str, spark, llm_endpoint: str) -> dict:
        self._reset_state()

        print(f"  Running {len(['tool1', 'tool2', 'tool3', 'tool4'])} tools ...")

        # ── Tool calls ────────────────────────────────────────────────
        tr1 = self._tool_retrieve_business_model_context(spark)
        tr2 = self._tool_retrieve_revenue_model_detail(spark)
        tr3 = self._tool_retrieve_sales_and_growth(spark)
        tr4 = self._tool_load_company_profile(company_name, spark)

        # ── Build combined context (deduplicate by chunk text) ────────
        seen_texts: set[str] = set()
        all_chunks = []
        for tr in (tr1, tr2, tr3):
            for chunk in (tr.data or []):
                if chunk.chunk_text not in seen_texts:
                    seen_texts.add(chunk.chunk_text)
                    all_chunks.append(chunk)

        combined_chunk_text = "\n\n---\n\n".join(
            f"[File: {c.file_name}] [Section: {c.section_header}]\n{c.chunk_text}"
            for c in all_chunks
        )

        profile_dict = tr4.data
        company_profile_json = json.dumps(profile_dict, default=str) if profile_dict else "{}"

        # ── Single LLM call ───────────────────────────────────────────
        print("  Calling LLM for extraction ...")
        user_prompt = _USER_PROMPT_TEMPLATE.format(
            company_profile_json=company_profile_json,
            combined_chunk_text=combined_chunk_text,
        )
        raw_response = self._call_llm(_SYSTEM_PROMPT, user_prompt, llm_endpoint)
        extracted = self._parse_json_response(raw_response)

        # Log LLM call to trace.
        self._base._trace.append({
            "step":       len(self._base._trace) + 1,
            "tool":       "llm_extraction",
            "input":      f"combined context: {len(all_chunks)} chunks from {len(seen_texts)} unique texts",
            "output":     f"Extracted revenue_model_tag={extracted.get('revenue_model_tag')}",
            "confidence": "high" if all_chunks else "low",
            "sources":    list({c.file_name for c in all_chunks}),
        })

        # ── Accumulate citations from LLM output ──────────────────────
        for cit in (extracted.get("citations") or []):
            self._add_citation(
                claim=cit.get("field", ""),
                document=cit.get("document", ""),
                location=cit.get("location", ""),
                confidence=cit.get("confidence", "low"),
                raw_text=cit.get("quote", ""),
            )

        # ── Revenue durability flag — deterministic Python ────────────
        primary_source = (
            tr1.source_docs[0] if tr1.source_docs
            else tr2.source_docs[0] if tr2.source_docs
            else ""
        )
        severity, flag_confidence, flag_rule = self._apply_revenue_durability_flag(
            revenue_model_tag=extracted.get("revenue_model_tag"),
            revenue_model_pct_split=extracted.get("revenue_model_pct_split"),
            source_doc=primary_source,
        )
        self._add_flag(
            metric="revenue_model_durability",
            value=str(extracted.get("revenue_model_pct_split") or extracted.get("revenue_model_tag") or "unknown"),
            threshold="≥70% recurring=Green, 40–70%=Yellow, <40%=Red",
            severity=severity,
            note=flag_rule,
            source_doc=primary_source,
            confidence=flag_confidence,
        )

        # ── Overlay conflict check ────────────────────────────────────
        overlay_conflict, overlay_conflict_note = self._check_overlay_conflict(
            extracted=extracted,
            profile=profile_dict,
        )
        overlay_step = len(self._base._trace) + 1
        self._base._trace.append({
            "step":       overlay_step,
            "tool":       "industry_overlay_conflict_check",
            "input":      f"revenue_model_tag={extracted.get('revenue_model_tag')}, "
                          f"customer_segments={str(extracted.get('customer_segments', ''))[:80]}",
            "output":     f"conflict={overlay_conflict}" + (f" — {overlay_conflict_note[:120]}" if overlay_conflict_note else ""),
            "confidence": "high" if profile_dict else "low",
            "sources":    ["uc13.classification.company_profile"],
        })
        print(f"  Step {overlay_step} [industry_overlay_conflict_check]: conflict={overlay_conflict}")

        # ── Build result dict ─────────────────────────────────────────
        vis = extracted.get("revenue_visibility") or {}
        return {
            "company_name":                  company_name,
            "revenue_model_tag":             extracted.get("revenue_model_tag"),
            "revenue_model_pct_split":       extracted.get("revenue_model_pct_split"),
            "revenue_model_note":            extracted.get("revenue_model_note"),
            "revenue_durability_flag":       severity,
            "flag_confidence":               flag_confidence,
            "flag_rule_applied":             flag_rule,
            "products_services":             json.dumps(extracted.get("products_services") or []),
            "customer_segments":             extracted.get("customer_segments"),
            "sales_motion":                  extracted.get("sales_motion"),
            "sales_motion_note":             extracted.get("sales_motion_note"),
            "revenue_visibility_contracted_pct": vis.get("contracted_pct_of_forward_12mo"),
            "backlog_coverage_months":       vis.get("backlog_coverage_months"),
            "key_dependencies":              extracted.get("key_dependencies") or [],
            "recent_model_changes":          extracted.get("recent_model_changes") or [],
            "overlay_conflict":              overlay_conflict,
            "overlay_conflict_note":         overlay_conflict_note,
            "executive_summary":             extracted.get("executive_summary"),
            "data_room_gaps":                list(self._base._data_room_gaps),
            "citations":                     json.dumps(self._citations_as_dicts()),
            "reasoning_trace":               list(self._base._trace),
            "flags":                         self._flags_as_dicts(),
            "created_at":                    datetime.now(timezone.utc).isoformat(),
        }


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {table} (
    company_name                       STRING,
    executive_summary                  STRING,
    revenue_model_tag                  STRING,
    revenue_model_pct_split            STRING,
    revenue_model_note                 STRING,
    revenue_durability_flag            STRING,
    flag_confidence                    STRING,
    flag_rule_applied                  STRING,
    products_services                  STRING,
    customer_segments                  STRING,
    sales_motion                       STRING,
    sales_motion_note                  STRING,
    revenue_visibility_contracted_pct  STRING,
    backlog_coverage_months            STRING,
    key_dependencies                   ARRAY<STRING>,
    recent_model_changes               ARRAY<STRING>,
    overlay_conflict                   BOOLEAN,
    overlay_conflict_note              STRING,
    data_room_gaps                     ARRAY<STRING>,
    citations                          STRING,
    reasoning_trace                    STRING,
    created_at                         TIMESTAMP
)
USING DELTA
"""


def main() -> dict:
    repo_root = find_repo_root()
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    company_name = get_param("sp_company_name")
    catalog      = get_param("catalog",      default="uc13")
    llm_endpoint = get_param("llm_endpoint", default="databricks-meta-llama-3-3-70b-instruct")

    from pyspark.sql import SparkSession
    spark = SparkSession.getActiveSession()
    if spark is None:
        raise RuntimeError("No active Spark session.")

    print(f"\n=== Business Model Agent ({company_name}) ===")

    agent = BusinessModelAgent()
    result = agent.run(company_name=company_name, spark=spark, llm_endpoint=llm_endpoint)

    # ── Save to Delta ─────────────────────────────────────────────────
    table = f"{catalog}.analysis.business_model"
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.analysis")
    spark.sql(_CREATE_TABLE_SQL.format(table=table))
    spark.sql(f"DELETE FROM {table} WHERE company_name = '{company_name}'")

    from pyspark.sql import Row
    from pyspark.sql.types import (
        StructType, StructField, StringType, BooleanType,
        ArrayType, TimestampType,
    )

    schema = StructType([
        StructField("company_name",                       StringType(),  True),
        StructField("executive_summary",                  StringType(),  True),
        StructField("revenue_model_tag",                  StringType(),  True),
        StructField("revenue_model_pct_split",            StringType(),  True),
        StructField("revenue_model_note",                 StringType(),  True),
        StructField("revenue_durability_flag",            StringType(),  True),
        StructField("flag_confidence",                    StringType(),  True),
        StructField("flag_rule_applied",                  StringType(),  True),
        StructField("products_services",                  StringType(),  True),
        StructField("customer_segments",                  StringType(),  True),
        StructField("sales_motion",                       StringType(),  True),
        StructField("sales_motion_note",                  StringType(),  True),
        StructField("revenue_visibility_contracted_pct",  StringType(),  True),
        StructField("backlog_coverage_months",            StringType(),  True),
        StructField("key_dependencies",    ArrayType(StringType()),       True),
        StructField("recent_model_changes", ArrayType(StringType()),      True),
        StructField("overlay_conflict",                   BooleanType(), True),
        StructField("overlay_conflict_note",              StringType(),  True),
        StructField("data_room_gaps",      ArrayType(StringType()),       True),
        StructField("citations",                          StringType(),  True),
        StructField("reasoning_trace",                    StringType(),  True),
        StructField("created_at",                         TimestampType(), True),
    ])

    from datetime import datetime, timezone
    row_data = {
        "company_name":                      result["company_name"],
        "executive_summary":                 result.get("executive_summary"),
        "revenue_model_tag":                 result.get("revenue_model_tag"),
        "revenue_model_pct_split":           result.get("revenue_model_pct_split"),
        "revenue_model_note":                result.get("revenue_model_note"),
        "revenue_durability_flag":           result.get("revenue_durability_flag"),
        "flag_confidence":                   result.get("flag_confidence"),
        "flag_rule_applied":                 result.get("flag_rule_applied"),
        "products_services":                 result.get("products_services"),
        "customer_segments":                 result.get("customer_segments"),
        "sales_motion":                      result.get("sales_motion"),
        "sales_motion_note":                 result.get("sales_motion_note"),
        "revenue_visibility_contracted_pct": result.get("revenue_visibility_contracted_pct"),
        "backlog_coverage_months":           result.get("backlog_coverage_months"),
        "key_dependencies":                  result.get("key_dependencies") or [],
        "recent_model_changes":              result.get("recent_model_changes") or [],
        "overlay_conflict":                  result.get("overlay_conflict", False),
        "overlay_conflict_note":             result.get("overlay_conflict_note"),
        "data_room_gaps":                    result.get("data_room_gaps") or [],
        "citations":                         result.get("citations"),
        "reasoning_trace":                   json.dumps(result.get("reasoning_trace") or []),
        "created_at":                        datetime.now(timezone.utc),
    }

    df = spark.createDataFrame([Row(**row_data)], schema=schema)
    df.write.format("delta").mode("append").saveAsTable(table)

    print(f"\n✓ Saved business model output → {table}")
    return result


if __name__ == "__main__":
    main()
