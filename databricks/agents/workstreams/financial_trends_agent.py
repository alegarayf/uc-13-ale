"""
financial_trends_agent.py — Phase 3: Financial Trends Workstream Agent.

Extracts financial performance metrics from documents tagged FINANCIAL and
QUALITY_EARNINGS. Applies Austin Hough's primary investment thresholds for tech
services and healthcare services. Stores addback schedule for the future Quality of
Earnings Agent to consume.

Phase 1 posture (strictly enforced): Extract stated figures only. Never recompute
a metric. If two documents give different EBITDA values, extract both and flag the
discrepancy — do not resolve it.

Phase 3 outputs:
  - Table uc13.analysis.financial_trends

Dependencies:
  - uc13.ingestion.embeddings          (written by ingestion_parser.py)
  - uc13.classification.doc_relevance  (written by document_classifier.py)
  - uc13.classification.company_profile (written by company_profiler.py)
  - agents.shared.retrieval.semantic_search
  - agents.shared.agent_base.WorkstreamAgent
"""

import json
import os
import re
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
# LLM prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a senior PE investment analyst extracting structured financial metrics
from due diligence documents. You must follow all rules below precisely.

EXTRACTION RULES:
1. Extract ONLY what is explicitly stated in the provided context. Never infer,
   compute, or hallucinate a value.
2. Do NOT recompute, reconcile, or choose between conflicting figures. If two
   documents show different EBITDA values, extract both and flag the discrepancy.
3. If a metric is absent from the context, return null for that field.
4. Mark computed_from_stated=true ONLY when you derive a % from two explicitly
   stated numbers in the SAME document. Never cross-document compute.
5. Every extracted value must have a citation: document name, location (page or
   section title), and a ≤30-word quote from the source.
6. Return ONLY valid JSON with no preamble, no commentary, and no markdown fences.
7. COMPANY PROFILE BLOCK IS METADATA ONLY: The block labelled "COMPANY PROFILE"
   at the top of the user prompt is metadata used to configure thresholds. It is
   NOT a financial source. Never extract revenue, EBITDA, gross margin, or addback
   values from the company profile block. All financial data must come exclusively
   from the RETRIEVED FINANCIAL DOCUMENT CONTEXT section.

READING FINANCIAL TABLES — LAYOUT-AGNOSTIC RULES:
Financial statements appear in many formats across different data rooms. These
rules apply regardless of layout:

8. MARGIN VALUES: For each dollar metric (Revenue, Gross Profit, EBITDA), find
   its corresponding margin % by any means present in the document — it may appear
   as a subordinate row labelled "Margin" immediately below the dollar row (common
   in banker CIMs), as an inline column, as a separate summary table, or as a
   narrative sentence (e.g. "Gross margin was 42% in FY2023"). Extract the margin %
   wherever it is stated. Do NOT skip a record because the margin % isn't in a
   subordinate row.
   When a "Margin" row does appear immediately below a dollar row, read its values
   directly into the parent row's margin field — do NOT create a separate record.
   Example: Row "PF Adj. EBITDA: 2,104 / 3,157 / 4,016 / 6,677 / 9,239" followed
   by "Margin: 23.5% / 22.3% / 19.3% / 19.5% / 19.9%" → margin % values belong
   in ebitda_margin_pct for each period's PF Adj. EBITDA record.

9. GROWTH VALUES: Find each revenue line's YoY growth % by any means present —
   subordinate "Growth" row, inline percentage, or bridge narrative. Do NOT compute
   growth. Extract the stated %. "N/A" for the first period means no prior year —
   return null for that period.
   Example: Row "Revenue: 8,955 / 14,176 / 20,846 / 34,160 / 46,423" followed by
   "Growth: N/A / 58.3% / 47.1% / 63.9% / 35.9%" → yoy_growth_pct values:
   null, "58.3%", "47.1%", "63.9%", "35.9%".

10. PERIOD LABELS — TIME ONLY: The "period" field must always be a time period:
    FY20A, FY21A, 2023A, TTM Aug-24, Q1-2024, LTM, H1 2024, etc. Geographic
    names (NY, MA, CT, states, countries) and entity names (company names,
    division names) are NOT time periods. If a table's column headers are
    geographies or entities, treat that table as revenue_by_segment data, not
    as revenue_trend or ebitda data.

EXTRACTING MULTIPLE NAMED EBITDA LINES:
11. A single document frequently presents MULTIPLE distinct named EBITDA lines.
    Each named EBITDA line is a SEPARATE concept and requires SEPARATE records —
    one record per period per named line.
    Common patterns (not exhaustive — labels vary by banker and company):
    - Raw/unadjusted: "Reported EBITDA", "EBITDA as reported", "Statutory EBITDA"
    - Accounting-adjusted: "Diligence Adjusted EBITDA", "Normalized EBITDA",
      "Adjusted EBITDA"
    - Sub-entity: "Clinic-Level EBITDA", "Store-Level EBITDA", "Location EBITDA"
    - Full pro forma: "PF Adj. EBITDA", "Pro Forma EBITDA", "Management EBITDA"
    Do NOT collapse these. Use the exact label from the document in the "label"
    field. A P&L with 5 periods and 4 named EBITDA lines must produce 20 records.

EXTRACTING ADDBACK AND ADJUSTMENT TABLES:
12. An addback table (may be titled "EBITDA Adjustment Detail", "Addback Schedule",
    "Management Adjustments", "Normalizing Adjustments", or similar) lists
    adjustment items as rows with fiscal periods as columns. Extract one record per
    ROW (one per adjustment item), using the most recent period's dollar value as
    amount_stated. Record the period that value comes from. Each row is a distinct
    item regardless of how it is labelled ([A], [1], a description, etc.).\
"""

_USER_PROMPT_TEMPLATE = """\
COMPANY PROFILE (metadata only — do NOT extract financial figures from this block):
{company_profile_json}

RETRIEVED FINANCIAL DOCUMENT CONTEXT (extract ALL financial figures from here only):
{combined_chunk_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXTRACTION TASK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Extract all available financial metrics from the RETRIEVED FINANCIAL DOCUMENT
CONTEXT above. Apply all system prompt rules. Return ONLY the JSON object below.

BEFORE YOU WRITE THE JSON: Scan the context for how many distinct named revenue
lines and EBITDA lines are present. For each named line × each period, you must
produce one record. A document with 5 fiscal periods and 4 named EBITDA lines
must produce 20 EBITDA records. Do not abbreviate.

{{
  "revenue_trend": [
    {{
      "period": "<time period ONLY: FY20A | FY21A | 2023A | TTM Aug-24 | Q1-2024 | etc. — NEVER a geography, state, or entity name>",
      "label": "<exact row label from the document — e.g. 'Pro Forma Adjusted Revenue' or 'Reported Net Revenue' or 'Total Revenue'>",
      "revenue_stated": "<$ amount exactly as written — e.g. '8,955' or '46,423' or '$14.2M'>",
      "yoy_growth_pct": "<YoY growth % for this period, extracted from wherever it is stated in the document (Growth row, inline %, narrative). E.g. '58.3%' or '35.9%'. Return null if N/A or absent.>",
      "computed_yoy": false,
      "source_doc": "<exact filename of the VDR document — must NOT be 'COMPANY PROFILE'>",
      "source_location": "<page number or section title — e.g. 'p.49 Historical P&L Summary'>"
    }}
  ],

  "gross_margin": [
    {{
      "period": "<time period ONLY>",
      "label": "<exact row label — e.g. 'Gross Profit' or 'Pro Forma Adjusted Gross Profit'>",
      "gm_dollars_stated": "<$ amount from the Gross Profit row for this period — e.g. '3,770' or '20,170'>",
      "gm_pct_stated": "<gross margin % for this period, found anywhere in the document: subordinate Margin row, inline column, summary table, or narrative. E.g. '42.1%' or '44.3%'. Return null only if genuinely absent from the document.>",
      "computed_from_stated": false,
      "source_doc": "<exact filename — must NOT be 'COMPANY PROFILE'>",
      "source_location": "<page number or section title>"
    }}
  ],

  "ebitda": [
    {{
      "period": "<time period ONLY — NEVER a geography, state, or entity name>",
      "label": "<FULL exact label from the document — e.g. 'PF Adjusted Clinic-Level EBITDA' or 'PF Adj. EBITDA' or 'Reported EBITDA' or 'Diligence Adjusted EBITDA' or 'Adjusted EBITDA' or 'Normalized EBITDA'>",
      "version": "<classify the version: 'reported' for raw/as-reported | 'diligence_adjusted' for accounting-adjusted | 'clinic_level_adjusted' for location/unit-level | 'pf_adjusted' for full pro forma | 'mgmt_adjusted' for management-adjusted | 'other' for anything else>",
      "ebitda_dollars": "<$ as stated — e.g. '(342)' for a loss, '9,239' for profit>",
      "ebitda_margin_pct": "<EBITDA margin % for this period, found anywhere in the document for THIS specific EBITDA line: subordinate Margin row, inline column, summary table, or narrative. E.g. '23.5%'. Each named EBITDA line has its own margin. Return null if genuinely absent.>",
      "source_doc": "<exact VDR document filename — must NOT be 'COMPANY PROFILE'>",
      "source_location": "<page number or section title>"
    }}
  ],

  "revenue_by_segment": [
    {{
      "segment": "<segment, geography, service line, or location name — e.g. 'NYC' or 'Home Health Aides' or 'Northeast'>",
      "revenue_pct": "<% of total revenue as stated, or null>",
      "revenue_dollars": "<$ as stated — e.g. '$25M' or '13,588'>",
      "period": "<time period for this figure>",
      "source_doc": "<exact filename>"
    }}
  ],

  "cost_structure": {{
    "headcount_pct_of_revenue": "<% as stated or null>",
    "fixed_vs_variable_note": "<description of fixed vs. variable cost split as stated, or null>",
    "key_categories": ["<e.g. 'Payroll expenses'>", "<e.g. 'Rent expense'>"],
    "source_doc": "<filename or null>"
  }},

  "working_capital": {{
    "dso_days": "<days as stated or null>",
    "dpo_days": "<days as stated or null>",
    "ar_aging_note": "<AR aging or cash collection description as stated, or null>",
    "source_doc": "<filename or null>"
  }},

  "budget_vs_actual": [
    {{
      "period": "<period>",
      "metric": "<Revenue | EBITDA>",
      "budget_stated": "<$ as stated>",
      "actual_stated": "<$ as stated>",
      "variance_note": "<description of variance as stated in the document>",
      "source_doc": "<filename>"
    }}
  ],

  "addback_schedule": [
    {{
      "description": "<exact label of this adjustment item as written — e.g. '[G] Run-rate executive compensation' or 'Owner compensation normalization' or 'Non-recurring legal fees'>",
      "amount_stated": "<$ for the most recent period as stated>",
      "period": "<the period this amount_stated value comes from>",
      "supporting_doc_referenced": "<name of any supporting document cited in the schedule for this item, or 'not referenced'>",
      "source_doc": "<exact VDR document filename>",
      "source_location": "<page number or section title — e.g. 'p.50 EBITDA Adjustment Detail'>",
      "raw_text": "<≤30 word direct quote>"
    }}
  ],

  "discrepancies_found": [
    {{
      "metric": "<metric name>",
      "conflicting_values": ["<doc A: $X>", "<doc B: $Y>"],
      "note": "<brief description>"
    }}
  ],

  "executive_summary": "<3–4 sentence factual summary covering: (1) revenue scale and growth trajectory if visible, (2) gross margin level and trend, (3) EBITDA profile across the versions present, (4) most notable financial risk or pattern. Write only what is stated in the documents. Do not render a verdict.>",

  "extraction_notes": "<Single string. Enumerate separated by semicolons: fields returned as null because absent from documents; tables present but only partially readable; multiple versions of the same metric found; any ambiguity in how margin rows were assigned to parent rows; any layout patterns that differ from the rules above.>"
}}\
"""


# ---------------------------------------------------------------------------
# Numeric parsing helper
# ---------------------------------------------------------------------------

def _parse_numeric(value_str: Optional[str]) -> Optional[float]:
    """Strip $, commas, % and parse to float. Returns None on failure."""
    if value_str is None:
        return None
    cleaned = re.sub(r"[$,%\s]", "", str(value_str)).replace("(", "-").replace(")", "")
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _most_recent_value(records: list[dict], value_key: str) -> tuple[Optional[float], Optional[str], Optional[str]]:
    """Return (numeric_value, stated_string, source_doc) for the most recent period.

    Periods are sorted heuristically: TTM/LTM > FY2024 > FY2023 > … > FY2019.
    Returns (None, None, None) if no parseable value found.
    """
    def period_rank(rec: dict) -> int:
        period = (rec.get("period") or "").upper()
        if "TTM" in period or "LTM" in period:
            return 9999
        m = re.search(r"(\d{4})", period)
        return int(m.group(1)) if m else 0

    sorted_recs = sorted(records, key=period_rank, reverse=True)
    for rec in sorted_recs:
        raw = rec.get(value_key)
        num = _parse_numeric(raw)
        if num is not None:
            return num, raw, rec.get("source_doc", "")
    return None, None, None


def _compute_margin_from_dollars(
    ebitda_records: list[dict],
    revenue_records: list[dict],
) -> tuple[Optional[float], Optional[str], Optional[str]]:
    """Compute EBITDA (or gross) margin % from dollar amounts when a margin % row is absent.

    Matches records by period string (case-insensitive) and picks the most recent
    matched period. Returns (margin_float, margin_str, source_doc).

    Only used as a fallback when the stated margin % is null for all periods.
    The computation is single-document-safe because both values come from the same
    extracted context — period matching ensures they belong to the same column.
    """
    def period_rank(period_str: str) -> int:
        p = (period_str or "").upper()
        if "TTM" in p or "LTM" in p:
            return 9999
        m = re.search(r"(\d{4})", p)
        return int(m.group(1)) if m else 0

    rev_by_period: dict[str, tuple[float, str]] = {}
    for r in revenue_records:
        period = (r.get("period") or "").strip().upper()
        if not period:
            continue
        rev_num = _parse_numeric(r.get("revenue_stated"))
        if rev_num is not None and rev_num != 0:
            rev_by_period[period] = (rev_num, r.get("source_doc", ""))

    candidates = []
    for e in ebitda_records:
        period = (e.get("period") or "").strip().upper()
        ebitda_num = _parse_numeric(e.get("ebitda_dollars"))
        if period and ebitda_num is not None and period in rev_by_period:
            rev_num, rev_doc = rev_by_period[period]
            margin = (ebitda_num / rev_num) * 100
            candidates.append((period_rank(period), margin, e.get("source_doc", ""), period))

    if not candidates:
        return None, None, None

    candidates.sort(key=lambda x: x[0], reverse=True)
    _, margin, source_doc, period = candidates[0]
    margin_str = f"{round(margin, 1)}% (computed from stated dollars, period={period})"
    return round(margin, 1), margin_str, source_doc


def _compute_yoy_growth(
    revenue_records: list[dict],
) -> tuple[Optional[float], Optional[str], Optional[str]]:
    """Compute the most recent YoY growth % from consecutive stated revenue values.

    Only used as a fallback when yoy_growth_pct is null for the most recent period.
    Requires at least two periods with parseable revenue_stated values.
    Returns (growth_float, growth_str, source_doc).
    """
    def period_rank(rec: dict) -> int:
        p = (rec.get("period") or "").upper()
        if "TTM" in p or "LTM" in p:
            return 9999
        m = re.search(r"(\d{4})", p)
        return int(m.group(1)) if m else 0

    sorted_recs = sorted(revenue_records, key=period_rank)
    parseable = [
        (period_rank(r), _parse_numeric(r.get("revenue_stated")), r.get("source_doc", ""), r.get("period", ""))
        for r in sorted_recs
        if _parse_numeric(r.get("revenue_stated")) is not None
    ]
    if len(parseable) < 2:
        return None, None, None

    _, prev_val, _, _       = parseable[-2]
    _, curr_val, doc, period = parseable[-1]

    if prev_val == 0:
        return None, None, None

    growth = ((curr_val - prev_val) / abs(prev_val)) * 100
    growth_str = f"{round(growth, 1)}% (computed from consecutive stated revenue values, period={period})"
    return round(growth, 1), growth_str, doc


# ---------------------------------------------------------------------------
# Agent implementation
# ---------------------------------------------------------------------------

class FinancialTrendsAgent:
    """Phase 3 Financial Trends workstream agent.

    Orchestrates: tool calls → single LLM call → deterministic threshold
    evaluation → Delta write.
    """

    agent_name = "financial_trends"

    def __init__(self):
        from agents.shared.agent_base import WorkstreamAgent
        self._base = WorkstreamAgent.__new__(WorkstreamAgent)
        WorkstreamAgent.__init__(self._base)
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
    # Retrieval helper
    # ------------------------------------------------------------------

    def _semantic_search_with_fallback(
        self,
        spark,
        query: str,
        workstream_filter: list,
        top_k: int,
        file_name_filter,
        min_chunk_length: int = 150,
        min_results: int = 3,
    ) -> list:
        """Semantic search with automatic fallback when the filename filter is too narrow.

        Strategy:
          1. Try with file_name_filter (preferred — focuses on high-signal docs).
          2. If result count < min_results, retry without file_name_filter so documents
             with non-standard filenames (e.g. 'Project Maple Model vF.xlsx') are not
             silently excluded.

        This makes retrieval portable across data rooms without needing to know each
        banker's or management team's document naming conventions in advance.
        """
        from agents.shared.retrieval import semantic_search

        chunks = semantic_search(
            query=query,
            spark=spark,
            company_name=self._company_name,
            top_k=top_k,
            workstream_filter=workstream_filter,
            file_name_filter=file_name_filter,
            min_chunk_length=min_chunk_length,
        )

        if len(chunks) < min_results and file_name_filter is not None:
            step = len(self._base._trace) + 1
            self._base._trace.append({
                "step":       step,
                "tool":       "retrieval_fallback",
                "input":      f"file_name_filter returned {len(chunks)} chunks (< {min_results}); retrying without filter",
                "output":     "fallback retrieval active — all workstream-tagged documents searched",
                "confidence": "medium",
                "sources":    [],
            })
            print(f"  Step {step} [retrieval_fallback]: filter returned {len(chunks)} chunks, retrying without filename filter")
            chunks = semantic_search(
                query=query,
                spark=spark,
                company_name=self._company_name,
                top_k=top_k,
                workstream_filter=workstream_filter,
                file_name_filter=None,
                min_chunk_length=min_chunk_length,
            )

        return chunks

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    def _tool_retrieve_financial_statements(self, spark):
        chunks = self._semantic_search_with_fallback(
            spark=spark,
            query=(
                "annual revenue gross profit EBITDA profit loss income statement "
                "financial results reported net revenue pro forma adjusted revenue "
                "management accounts P&L summary historical financials"
            ),
            workstream_filter=["FINANCIAL"],
            top_k=15,
            file_name_filter=[
                "P&L", "Profit", "Loss", "Income", "Financial", "Accounts",
                "Financials", "Audited", "Management", "QofE", "Quality", "CIM",
            ],
            min_chunk_length=150,
            min_results=3,
        )
        source_docs = list({c.file_name for c in chunks})
        pt_count = sum(1 for c in chunks if getattr(c, "priority_tier", None) == 1)
        print(f"    Priority Tier chunks: {pt_count} / {len(chunks)}")
        confidence = "high" if pt_count > 0 else ("medium" if chunks else "low")
        return self._tool_call(
            tool_name="retrieve_financial_statements",
            input_summary="query=revenue gross profit EBITDA income statement; workstream=FINANCIAL; top_k=15 (with fallback)",
            data=chunks,
            output_summary=f"{len(chunks)} chunks ({pt_count} Priority Tier) from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_retrieve_ebitda_and_margins(self, spark):
        chunks = self._semantic_search_with_fallback(
            spark=spark,
            query=(
                "EBITDA margin gross margin adjusted EBITDA addback bridge earnings profitability "
                "clinic level EBITDA diligence adjusted pro forma margin operating income "
                "adjusted operating profit contribution margin"
            ),
            workstream_filter=["FINANCIAL", "QUALITY_EARNINGS"],
            top_k=12,
            file_name_filter=[
                "EBITDA", "Margin", "Addback", "Bridge", "Adjusted",
                "QofE", "Quality", "P&L", "CIM", "Financial",
            ],
            min_chunk_length=150,
            min_results=3,
        )
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_ebitda_and_margins",
            input_summary="query=EBITDA margin gross margin adjusted pro forma; workstream=FINANCIAL,QUALITY_EARNINGS; top_k=12 (with fallback)",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_retrieve_revenue_by_segment(self, spark):
        chunks = self._semantic_search_with_fallback(
            spark=spark,
            query=(
                "revenue by segment product line geography service line revenue split breakdown "
                "revenue by location revenue by office revenue by division revenue by customer type"
            ),
            workstream_filter=["FINANCIAL", "BUSINESS_MODEL"],
            top_k=8,
            file_name_filter=[
                "P&L", "Financial", "Revenue", "Segment", "CIM",
            ],
            min_chunk_length=150,
            min_results=3,
        )
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_revenue_by_segment",
            input_summary="query=revenue by segment product geography service; workstream=FINANCIAL,BUSINESS_MODEL; top_k=8 (with fallback)",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_retrieve_working_capital(self, spark):
        chunks = self._semantic_search_with_fallback(
            spark=spark,
            query=(
                "DSO DPO days sales outstanding accounts receivable aging working capital "
                "cash collection cash conversion cycle AR balance sheet current assets"
            ),
            workstream_filter=["FINANCIAL"],
            top_k=6,
            file_name_filter=[
                "Balance Sheet", "Financial", "Accounts", "AR", "Aging",
                "Working Capital", "CIM",
            ],
            min_chunk_length=150,
            min_results=3,
        )
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_working_capital",
            input_summary="query=DSO DPO AR aging working capital; workstream=FINANCIAL; top_k=6 (with fallback)",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_retrieve_addback_schedule(self, spark):
        chunks = self._semantic_search_with_fallback(
            spark=spark,
            query=(
                "addback adjustments owner compensation one-time non-recurring EBITDA bridge "
                "diligence adjustment normalized expense run-rate executive compensation "
                "EBITDA adjustment detail credit card allocation non-operating transactions "
                "management addbacks seller adjustments earnings quality"
            ),
            workstream_filter=["FINANCIAL", "QUALITY_EARNINGS", "BUSINESS_MODEL"],
            top_k=12,
            file_name_filter=[
                "Addback", "Bridge", "EBITDA", "QofE", "Quality", "Adjusted",
                "CIM", "Adjustment", "Financial", "P&L",
            ],
            min_chunk_length=100,
            min_results=3,
        )
        if not chunks:
            self._add_gap("No addback schedule found — expected for QofE review")
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_addback_schedule",
            input_summary="query=addback EBITDA bridge adjustments normalized expense; workstream=FINANCIAL,QUALITY_EARNINGS,BUSINESS_MODEL; top_k=12 (with fallback)",
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
            self._add_gap("company_profile not found — run company_profiler.py first; defaulting overlay to None (both threshold sets applied)")
            return self._tool_call(
                tool_name="load_company_profile",
                input_summary=f"SQL read company_profile WHERE company_name='{company_name}'",
                data=None,
                output_summary="No company profile found — both threshold sets will be applied",
                confidence="low",
                source_docs=[],
            )
        row = rows[0]
        profile_dict = row.asDict()
        overlay = profile_dict.get("industry_overlay")
        return self._tool_call(
            tool_name="load_company_profile",
            input_summary=f"SQL read company_profile WHERE company_name='{company_name}'",
            data=profile_dict,
            output_summary=f"Profile loaded: industry_overlay={overlay}",
            confidence="high",
            source_docs=["uc13.classification.company_profile"],
        )

    # ------------------------------------------------------------------
    # Threshold evaluation — deterministic Python
    # ------------------------------------------------------------------

    def _log_no_flag(self, metric: str, value_str: str, threshold: str, note: str = ""):
        """Log a threshold evaluation that did NOT trigger a flag."""
        step = len(self._base._trace) + 1
        self._base._trace.append({
            "step":       step,
            "tool":       "threshold_evaluation",
            "input":      f"metric={metric}, value={value_str}, threshold={threshold}",
            "output":     f"No flag triggered — {note}" if note else "No flag triggered",
            "confidence": "high",
            "sources":    [],
        })
        print(f"  Step {step} [threshold_evaluation]: {metric}={value_str} vs {threshold} → no flag")

    def _apply_financial_flags(self, extracted: dict, overlay: Optional[str]):
        """Apply Austin Hough's primary investment thresholds.

        overlay: "tech_services" | "healthcare_services" | None (apply both).

        For each metric:
          1. Find the most recent period's value.
          2. Parse to float (strip $, commas, %).
          3. Compare against threshold.
          4. Call self._add_flag() if threshold breached, or log "no flag" to trace.
          5. If value is null, call self._add_gap() instead of flagging.
        """
        overlay_lower = (overlay or "").lower()
        apply_tech       = "tech" in overlay_lower or overlay is None
        apply_healthcare = "healthcare" in overlay_lower or overlay is None

        # ── Revenue growth ─────────────────────────────────────────────
        revenue_records = extracted.get("revenue_trend") or []
        # Attempt to find the most recent stated YoY growth %.
        growth_num, growth_str, growth_doc = _most_recent_value(revenue_records, "yoy_growth_pct")

        if apply_tech:
            tech_growth_num, tech_growth_str, tech_growth_doc = growth_num, growth_str, growth_doc
            if tech_growth_num is None and revenue_records:
                tech_growth_num, tech_growth_str, tech_growth_doc = _compute_yoy_growth(revenue_records)
                if tech_growth_num is not None:
                    step = len(self._base._trace) + 1
                    self._base._trace.append({
                        "step":       step,
                        "tool":       "compute_yoy_growth_fallback",
                        "input":      "yoy_growth_pct not stated; computing from consecutive stated revenue values (tech)",
                        "output":     f"Computed YoY growth: {tech_growth_str}",
                        "confidence": "medium",
                        "sources":    [tech_growth_doc] if tech_growth_doc else [],
                    })
                    print(f"  Step {step} [compute_yoy_growth_fallback]: {tech_growth_str}")

            if tech_growth_num is None:
                if revenue_records:
                    self._add_gap("Organic revenue growth % not stated and could not be computed — required for tech services threshold evaluation")
            elif tech_growth_num < 10:
                self._add_flag(
                    metric="organic_revenue_growth_yoy_pct",
                    value=tech_growth_str,
                    threshold="<~10–15% (tech services)",
                    severity="Red",
                    note=(
                        f"Revenue growth of {tech_growth_str} is below the ~10–15% threshold, "
                        "which may suggest questions about market positioning, sales engine "
                        "maturity, and customer demand for a premium tech services platform. "
                        f"Source: {tech_growth_doc}."
                    ),
                    source_doc=tech_growth_doc,
                    confidence="medium" if "computed" in (tech_growth_str or "") else "high",
                )
            else:
                self._log_no_flag("organic_revenue_growth_yoy_pct (tech)", tech_growth_str, "≥~10–15%")

        if apply_healthcare:
            hc_growth_num, hc_growth_str, hc_growth_doc = growth_num, growth_str, growth_doc
            if hc_growth_num is None and revenue_records:
                hc_growth_num, hc_growth_str, hc_growth_doc = _compute_yoy_growth(revenue_records)
                if hc_growth_num is not None:
                    step = len(self._base._trace) + 1
                    self._base._trace.append({
                        "step":       step,
                        "tool":       "compute_yoy_growth_fallback",
                        "input":      "yoy_growth_pct not stated; computing from consecutive stated revenue values (healthcare)",
                        "output":     f"Computed YoY growth: {hc_growth_str}",
                        "confidence": "medium",
                        "sources":    [hc_growth_doc] if hc_growth_doc else [],
                    })
                    print(f"  Step {step} [compute_yoy_growth_fallback]: {hc_growth_str}")

            if hc_growth_num is None:
                if revenue_records:
                    self._add_gap("Same-store revenue growth % not stated and could not be computed — required for healthcare services threshold evaluation")
            elif hc_growth_num < 5:
                self._add_flag(
                    metric="revenue_growth_same_store_yoy_pct",
                    value=hc_growth_str,
                    threshold="<~5–10% (healthcare services)",
                    severity="Red",
                    note=(
                        f"Revenue growth of {hc_growth_str} is below the ~5–10% threshold, "
                        "which may prompt questions on referral trends, reimbursement "
                        f"pressure, and provider availability. Source: {hc_growth_doc}."
                    ),
                    source_doc=hc_growth_doc,
                    confidence="medium" if "computed" in (hc_growth_str or "") else "high",
                )
            else:
                self._log_no_flag("revenue_growth_same_store_yoy_pct (healthcare)", hc_growth_str, "≥~5–10%")

        # ── Gross margin ───────────────────────────────────────────────
        gm_records = extracted.get("gross_margin") or []
        gm_num, gm_str, gm_doc = _most_recent_value(gm_records, "gm_pct_stated")

        # Fallback: compute from gm_dollars_stated ÷ revenue_stated for the same period.
        if gm_num is None and gm_records and revenue_records:
            gm_num, gm_str, gm_doc = _compute_margin_from_dollars(
                [{"period": r.get("period"), "ebitda_dollars": r.get("gm_dollars_stated"),
                  "source_doc": r.get("source_doc")} for r in gm_records],
                revenue_records,
            )
            if gm_num is not None:
                step = len(self._base._trace) + 1
                self._base._trace.append({
                    "step":       step,
                    "tool":       "compute_gm_margin_fallback",
                    "input":      "gm_pct_stated not available; computing from gm_dollars_stated ÷ revenue_stated (same period)",
                    "output":     f"Computed gross margin: {gm_str}",
                    "confidence": "medium",
                    "sources":    [gm_doc] if gm_doc else [],
                })
                print(f"  Step {step} [compute_gm_margin_fallback]: {gm_str}")

        if apply_tech:
            if gm_num is None:
                if gm_records:
                    self._add_gap("Gross margin % not stated — required for tech services threshold evaluation")
            elif gm_num < 40:
                self._add_flag(
                    metric="gross_margin_pct",
                    value=gm_str,
                    threshold="<~40% (tech services)",
                    severity="Red",
                    note=(
                        f"Gross margin of {gm_str} is below the ~40% threshold, which could "
                        "indicate lower-value work, weak utilization, poor delivery leverage, "
                        "or insufficient pricing power. Premium digital services: ≥45–50% preferred. "
                        f"Source: {gm_doc}."
                    ),
                    source_doc=gm_doc,
                    confidence="high" if gm_str else "medium",
                )
            else:
                self._log_no_flag("gross_margin_pct (tech)", gm_str, "≥~40%")

        if apply_healthcare:
            if gm_num is None:
                if gm_records:
                    self._add_gap("Gross margin % not stated — required for healthcare services threshold evaluation")
            elif gm_num < 30:
                self._add_flag(
                    metric="gross_margin_pct",
                    value=gm_str,
                    threshold="<~30–35% (healthcare services)",
                    severity="Red",
                    note=(
                        f"Gross margin of {gm_str} is below the ~30–35% threshold, which may "
                        "indicate wage pressure, poor labor utilization, pricing constraints, "
                        f"or unfavorable payor mix. Source: {gm_doc}."
                    ),
                    source_doc=gm_doc,
                    confidence="high" if gm_str else "medium",
                )
            else:
                self._log_no_flag("gross_margin_pct (healthcare)", gm_str, "≥~30–35%")

        # ── EBITDA margin ──────────────────────────────────────────────
        ebitda_records = extracted.get("ebitda") or []

        # Primary: use stated ebitda_margin_pct.
        ebitda_margin_num, ebitda_margin_str, ebitda_margin_doc = _most_recent_value(
            ebitda_records, "ebitda_margin_pct"
        )

        # Fallback: compute from ebitda_dollars ÷ revenue_stated for the same period.
        if ebitda_margin_num is None and ebitda_records and revenue_records:
            ebitda_margin_num, ebitda_margin_str, ebitda_margin_doc = _compute_margin_from_dollars(
                ebitda_records, revenue_records
            )
            if ebitda_margin_num is not None:
                step = len(self._base._trace) + 1
                self._base._trace.append({
                    "step":       step,
                    "tool":       "compute_ebitda_margin_fallback",
                    "input":      "ebitda_margin_pct not stated; computing from ebitda_dollars ÷ revenue_stated (same period)",
                    "output":     f"Computed EBITDA margin: {ebitda_margin_str} (source: {ebitda_margin_doc})",
                    "confidence": "medium",
                    "sources":    [ebitda_margin_doc] if ebitda_margin_doc else [],
                })
                print(f"  Step {step} [compute_ebitda_margin_fallback]: {ebitda_margin_str}")

        _ebitda_margin_confidence = "medium" if "computed" in (ebitda_margin_str or "") else "high"

        if apply_tech:
            if ebitda_margin_num is None:
                if ebitda_records:
                    self._add_gap("EBITDA margin % not stated and could not be computed — required for tech services threshold evaluation")
            elif ebitda_margin_num < 10:
                self._add_flag(
                    metric="ebitda_margin_pct",
                    value=ebitda_margin_str,
                    threshold="<~10–15% (tech services)",
                    severity="Yellow",
                    note=(
                        f"EBITDA margin of {ebitda_margin_str} is below the ~10–15% threshold. "
                        "Depends on company stage — may be fine, but flagged for discussion. "
                        f"Source: {ebitda_margin_doc}."
                    ),
                    source_doc=ebitda_margin_doc,
                    confidence=_ebitda_margin_confidence,
                )
            else:
                self._log_no_flag("ebitda_margin_pct (tech)", ebitda_margin_str, "≥~10–15%")

        if apply_healthcare:
            if ebitda_margin_num is None:
                if ebitda_records:
                    self._add_gap("EBITDA margin % not stated and could not be computed — required for healthcare services threshold evaluation")
            elif ebitda_margin_num < 10:
                self._add_flag(
                    metric="ebitda_margin_pct",
                    value=ebitda_margin_str,
                    threshold="<~10% (healthcare services)",
                    severity="Red",
                    note=(
                        f"EBITDA margin of {ebitda_margin_str} is below the ~10% threshold, "
                        "which may indicate labor inefficiency, weak reimbursement, poor "
                        "scheduling/utilization, high admin burden, or lack of scale. "
                        f"Source: {ebitda_margin_doc}."
                    ),
                    source_doc=ebitda_margin_doc,
                    confidence=_ebitda_margin_confidence,
                )
            else:
                self._log_no_flag("ebitda_margin_pct (healthcare)", ebitda_margin_str, "≥~10%")

        # ── Healthcare episodic/event-driven revenue ───────────────────
        if apply_healthcare:
            _raw_notes = extracted.get("extraction_notes") or ""
            notes = (" ".join(_raw_notes) if isinstance(_raw_notes, list) else str(_raw_notes)).lower()
            episodic_keywords = ("episodic", "event-driven", "referral", "discrete event",
                                 "hard to forecast", "inconsistent referral")
            if any(k in notes for k in episodic_keywords):
                self._add_flag(
                    metric="episodic_event_driven_revenue",
                    value="narrative indicator in extraction notes",
                    threshold="Flag if volume hard to forecast, referral patterns inconsistent, or revenue depends on discrete events (healthcare services)",
                    severity="Yellow",
                    note=(
                        "Extraction notes indicate episodic or event-driven revenue patterns. "
                        "Similar to project revenue in tech — flagged for discussion on "
                        "referral pattern consistency and revenue predictability."
                    ),
                    source_doc="extraction_notes",
                    confidence="low",
                )
            else:
                self._log_no_flag("episodic_event_driven_revenue (healthcare)", "not indicated", "no episodic keywords in extraction notes")

    def _apply_addback_flag(self, extracted: dict) -> Optional[float]:
        """Compute addback % of EBITDA and flag if >20%.

        Returns the computed pct or None if either value is unavailable.
        """
        addbacks = extracted.get("addback_schedule") or []
        ebitda_records = extracted.get("ebitda") or []

        if not addbacks:
            return None

        # Sum addback amounts.
        total_addback = 0.0
        any_parsed = False
        for ab in addbacks:
            num = _parse_numeric(ab.get("amount_stated"))
            if num is not None:
                total_addback += abs(num)
                any_parsed = True

        if not any_parsed:
            self._add_gap("Addback amounts not parseable as numbers — addback % of EBITDA not computed")
            return None

        # Get most recent reported EBITDA.
        reported = [r for r in ebitda_records if (r.get("version") or "").lower() == "reported"]
        ebitda_num, ebitda_str, ebitda_doc = _most_recent_value(
            reported or ebitda_records, "ebitda_dollars"
        )
        if ebitda_num is None or ebitda_num == 0:
            self._add_gap("Reported EBITDA $ not parseable — addback % of EBITDA not computed")
            return None

        addback_pct = round((total_addback / abs(ebitda_num)) * 100, 1)

        if addback_pct > 20:
            self._add_flag(
                metric="addback_pct_of_ebitda",
                value=f"{addback_pct}%",
                threshold=">20% of reported EBITDA",
                severity="Yellow",
                note=(
                    f"Addbacks represent {addback_pct}% of reported EBITDA; "
                    "QofE Agent review is high priority."
                ),
                source_doc=ebitda_doc or "",
                confidence="medium",
            )
        else:
            self._log_no_flag("addback_pct_of_ebitda", f"{addback_pct}%", "≤20%")

        return addback_pct

    def _apply_ebitda_growth_divergence_check(self, extracted: dict):
        """Check if mgmt-adjusted EBITDA is growing faster than reported over 3+ years.

        Does NOT apply a severity flag — adds a gap note for the QofE Agent.
        """
        ebitda_records = extracted.get("ebitda") or []
        reported = [r for r in ebitda_records if (r.get("version") or "").lower() == "reported"]
        adjusted = [r for r in ebitda_records if (r.get("version") or "").lower() == "mgmt_adjusted"]

        if len(reported) < 3 or len(adjusted) < 3:
            self._log_no_flag(
                "ebitda_growth_divergence",
                "insufficient periods",
                "need ≥3 periods of both reported and mgmt_adjusted EBITDA",
            )
            return

        def year_sort(rec):
            m = re.search(r"(\d{4})", rec.get("period") or "")
            return int(m.group(1)) if m else 0

        rep_sorted  = sorted(reported,  key=year_sort)
        adj_sorted  = sorted(adjusted,  key=year_sort)

        rep_vals = [_parse_numeric(r.get("ebitda_dollars")) for r in rep_sorted]
        adj_vals = [_parse_numeric(r.get("ebitda_dollars")) for r in adj_sorted]

        rep_clean = [v for v in rep_vals  if v is not None]
        adj_clean = [v for v in adj_vals  if v is not None]

        if len(rep_clean) < 2 or len(adj_clean) < 2:
            return

        rep_growth = (rep_clean[-1] - rep_clean[0]) / abs(rep_clean[0]) if rep_clean[0] else None
        adj_growth = (adj_clean[-1] - adj_clean[0]) / abs(adj_clean[0]) if adj_clean[0] else None

        if rep_growth is not None and adj_growth is not None and adj_growth > rep_growth:
            self._add_gap(
                "Mgmt-adjusted EBITDA growing faster than reported EBITDA — QofE Agent review required."
            )
            step = len(self._base._trace) + 1
            self._base._trace.append({
                "step":       step,
                "tool":       "ebitda_growth_divergence_check",
                "input":      f"reported_growth={round(rep_growth*100,1)}%, adj_growth={round(adj_growth*100,1)}%",
                "output":     "Mgmt-adjusted EBITDA growing faster than reported EBITDA — gap logged for QofE Agent",
                "confidence": "medium",
                "sources":    [],
            })
            print(f"  Step {step} [ebitda_growth_divergence_check]: divergence detected — gap logged")
        else:
            self._log_no_flag("ebitda_growth_divergence", "no divergence detected", "adjusted not growing faster than reported")

    def _apply_budget_miss_flags(self, extracted: dict):
        """Flag budget misses where |actual - budget| / budget > 10%."""
        for item in (extracted.get("budget_vs_actual") or []):
            budget_num = _parse_numeric(item.get("budget_stated"))
            actual_num = _parse_numeric(item.get("actual_stated"))
            metric     = item.get("metric", "unknown")
            period     = item.get("period", "unknown")
            source_doc = item.get("source_doc", "")

            if budget_num is None or actual_num is None or budget_num == 0:
                self._add_gap(
                    f"Budget vs. actual for {metric} in {period} not parseable — skipping miss check"
                )
                continue

            miss_pct = abs(actual_num - budget_num) / abs(budget_num)
            if miss_pct > 0.10:
                self._add_flag(
                    metric=f"budget_miss_{metric.lower()}",
                    value=f"actual={item.get('actual_stated')}, budget={item.get('budget_stated')}",
                    threshold=">10% variance (budget vs. actual)",
                    severity="Yellow",
                    note=(
                        f"Budget miss on {metric} in {period}: "
                        f"budget={item.get('budget_stated')}, actual={item.get('actual_stated')} "
                        f"({round(miss_pct*100,1)}% variance). "
                        "Requires explanation from management."
                    ),
                    source_doc=source_doc,
                    confidence="high",
                )
            else:
                self._log_no_flag(
                    f"budget_miss_{metric.lower()}",
                    f"{round(miss_pct*100,1)}% variance",
                    "≤10%",
                )

    # ------------------------------------------------------------------
    # Main run() orchestration
    # ------------------------------------------------------------------

    def run(self, company_name: str, spark, llm_endpoint: str) -> dict:
        self._reset_state()
        self._company_name = company_name

        print(f"  Running 6 tools ...")

        # ── Tool calls ────────────────────────────────────────────────
        tr1 = self._tool_retrieve_financial_statements(spark)
        tr2 = self._tool_retrieve_ebitda_and_margins(spark)
        tr3 = self._tool_retrieve_revenue_by_segment(spark)
        tr4 = self._tool_retrieve_working_capital(spark)
        tr5 = self._tool_retrieve_addback_schedule(spark)
        tr6 = self._tool_load_company_profile(company_name, spark)

        # ── Build combined context (deduplicate by chunk text) ────────
        seen_texts: set[str] = set()
        all_chunks = []
        for tr in (tr1, tr2, tr3, tr4, tr5):
            for chunk in (tr.data or []):
                if chunk.chunk_text not in seen_texts:
                    seen_texts.add(chunk.chunk_text)
                    all_chunks.append(chunk)

        # ── Cap context to avoid LLM timeout — Priority Tier chunks first ─
        # Llama 70B prefill time scales with input tokens; uncapped contexts of
        # 50+ chunks can push total processing over the 10-minute SDK timeout.
        # Retaining Priority Tier chunks first ensures the highest-signal pages
        # (the P&L summary, CIM financials) are never dropped by the cap.
        _MAX_CONTEXT_CHARS = 25_000
        _pt_chunks    = [c for c in all_chunks if getattr(c, "priority_tier", None) == 1]
        _other_chunks = [c for c in all_chunks if getattr(c, "priority_tier", None) != 1]
        _context_parts: list[str] = []
        _total_chars = 0
        for _c in (_pt_chunks + _other_chunks):
            _part = f"[File: {_c.file_name}] [Section: {_c.section_header}]\n{_c.chunk_text}"
            if _total_chars + len(_part) + 8 > _MAX_CONTEXT_CHARS:
                break
            _context_parts.append(_part)
            _total_chars += len(_part) + 8  # 8 = separator length
        _excluded = len(all_chunks) - len(_context_parts)
        if _excluded > 0:
            self._add_gap(
                f"Context capped at {_MAX_CONTEXT_CHARS:,} chars to prevent LLM timeout "
                f"({_excluded} of {len(all_chunks)} chunks excluded). "
                f"Priority Tier chunks were retained first; increase _MAX_CONTEXT_CHARS "
                f"or reduce top_k values if important pages are being dropped."
            )
            print(f"  [context_cap] {len(_context_parts)} chunks included, {_excluded} excluded "
                  f"(Priority Tier first, cap={_MAX_CONTEXT_CHARS:,} chars)")

        combined_chunk_text = "\n\n---\n\n".join(_context_parts)

        profile_dict = tr6.data
        company_profile_json = json.dumps(profile_dict, default=str) if profile_dict else "{}"
        overlay = profile_dict.get("industry_overlay") if profile_dict else None

        # ── Single LLM call ───────────────────────────────────────────
        print("  Calling LLM for extraction ...")
        user_prompt = _USER_PROMPT_TEMPLATE.format(
            company_profile_json=company_profile_json,
            combined_chunk_text=combined_chunk_text,
        )
        raw_response = self._call_llm(_SYSTEM_PROMPT, user_prompt, llm_endpoint)
        extracted = self._parse_json_response(raw_response)

        # ── Source doc validation: reject any record sourced from the company profile ──
        _PROFILE_SENTINEL = "COMPANY PROFILE"
        for _list_key in ("revenue_trend", "gross_margin", "ebitda", "addback_schedule"):
            _clean = []
            for _rec in (extracted.get(_list_key) or []):
                if (_rec.get("source_doc") or "").upper().startswith(_PROFILE_SENTINEL):
                    self._add_gap(
                        f"{_list_key} record excluded: source_doc='{_rec.get('source_doc')}' "
                        f"is the company profile metadata block, not a financial document. "
                        f"label='{_rec.get('label') or _rec.get('description')}' "
                        f"period='{_rec.get('period')}'. "
                        f"Improve retrieval coverage so this value is found in the VDR."
                    )
                else:
                    _clean.append(_rec)
            extracted[_list_key] = _clean

        # ── Post-extraction completeness check (portable — version-based, not label-based) ──
        _ebitda_records  = extracted.get("ebitda") or []
        _revenue_records = extracted.get("revenue_trend") or []
        _versions_found  = {(r.get("version") or "").lower() for r in _ebitda_records}

        # Check 1: at least one reported EBITDA version
        if _ebitda_records and "reported" not in _versions_found:
            self._add_gap(
                "No 'reported' EBITDA version found — the as-reported/unadjusted EBITDA line "
                "was not extracted. Check retrieval coverage of the P&L table."
            )

        # Check 2: at least one adjusted EBITDA version
        _adjusted_versions = {"pf_adjusted", "mgmt_adjusted", "diligence_adjusted",
                              "clinic_level_adjusted"}
        if _ebitda_records and not _adjusted_versions.intersection(_versions_found):
            self._add_gap(
                "No adjusted EBITDA version found (pf_adjusted / mgmt_adjusted / "
                "diligence_adjusted / clinic_level_adjusted). If an adjusted EBITDA concept "
                "exists in the documents, check retrieval and extraction coverage."
            )

        # Check 3: EBITDA margin % populated for at least one adjusted record
        _adjusted_with_margin = [
            r for r in _ebitda_records
            if (r.get("version") or "") in _adjusted_versions
            and r.get("ebitda_margin_pct") is not None
        ]
        if _ebitda_records and _adjusted_versions.intersection(_versions_found) \
                and not _adjusted_with_margin:
            self._add_gap(
                "Adjusted EBITDA records found but none have ebitda_margin_pct populated. "
                "Margin % may be present in the document but was not extracted — check "
                "whether a subordinate Margin row, inline column, or summary table was missed."
            )

        # Check 4: gross_margin array non-empty when financial statements were retrieved
        if not extracted.get("gross_margin") and _revenue_records:
            self._add_gap(
                "gross_margin array is empty despite revenue records being present. "
                "Gross Profit and its margin % were not extracted — check that the P&L "
                "table pages were retrieved and that the Gross Profit row was identified."
            )

        # Check 5: at least some YoY growth % values populated when multiple periods exist
        _revenue_with_growth = [
            r for r in _revenue_records if r.get("yoy_growth_pct") is not None
        ]
        if len(_revenue_records) > 1 and not _revenue_with_growth:
            self._add_gap(
                "Multiple revenue periods found but no YoY growth % extracted. "
                "The growth % row (subordinate row, inline column, or narrative) was not "
                "identified — check system prompt rule 9 and retrieval coverage."
            )

        # Check 6: addback schedule has at least one item when financial docs were retrieved
        if not extracted.get("addback_schedule") and _revenue_records:
            self._add_gap(
                "addback_schedule is empty. If an addback or EBITDA adjustment table exists "
                "in the data room, check retrieval coverage — the addback tool may need "
                "broader query terms or the document may not be workstream-tagged correctly."
            )

        llm_step = len(self._base._trace) + 1
        self._base._trace.append({
            "step":       llm_step,
            "tool":       "llm_extraction",
            "input":      f"combined context: {len(all_chunks)} deduplicated chunks",
            "output":     f"Extracted {len(extracted.get('revenue_trend') or [])} revenue periods, "
                          f"{len(extracted.get('ebitda') or [])} EBITDA records, "
                          f"{len(extracted.get('addback_schedule') or [])} addbacks",
            "confidence": "high" if all_chunks else "low",
            "sources":    list({c.file_name for c in all_chunks}),
        })

        # ── Post-LLM Python processing ────────────────────────────────
        print("  Applying financial thresholds ...")
        self._apply_financial_flags(extracted, overlay)
        addback_pct = self._apply_addback_flag(extracted)
        self._apply_ebitda_growth_divergence_check(extracted)
        self._apply_budget_miss_flags(extracted)

        # ── Build result dict ─────────────────────────────────────────
        return {
            "company_name":             company_name,
            "industry_overlay_used":    overlay or "both (no profile found)",
            "revenue_trend_json":       json.dumps(extracted.get("revenue_trend") or []),
            "gross_margin_json":        json.dumps(extracted.get("gross_margin") or []),
            "ebitda_json":              json.dumps(extracted.get("ebitda") or []),
            "revenue_by_segment_json":  json.dumps(extracted.get("revenue_by_segment") or []),
            "cost_structure_json":      json.dumps(extracted.get("cost_structure") or {}),
            "working_capital_json":     json.dumps(extracted.get("working_capital") or {}),
            "budget_vs_actual_json":    json.dumps(extracted.get("budget_vs_actual") or []),
            "addback_schedule_json":    json.dumps(extracted.get("addback_schedule") or []),
            "addback_pct_of_ebitda":    addback_pct,
            "executive_summary":        extracted.get("executive_summary"),
            "flags":                    self._flags_as_dicts(),
            "discrepancies":            json.dumps(extracted.get("discrepancies_found") or []),
            "data_room_gaps":           list(self._base._data_room_gaps),
            "citations":                json.dumps(self._citations_as_dicts()),
            "reasoning_trace":          list(self._base._trace),
            "created_at":               datetime.now(timezone.utc).isoformat(),
        }


# ---------------------------------------------------------------------------
# Stakeholder report export
# ---------------------------------------------------------------------------

def generate_financial_assessment(
    result: dict,
    spark,
    llm_endpoint: str,
    catalog: str = "uc13",
    write_to_volume: bool = True,
) -> str:
    """Generate a structured markdown financial-story assessment from agent output.

    Answers 12 diligence questions by combining deterministic table construction
    (revenue bridge, margin deltas, EBITDA multi-version, addback quality, budget
    variance) with a single LLM call that writes narrative for each section.

    Args:
        result:          Output dict from FinancialTrendsAgent.run().
        spark:           Active SparkSession (needed only when write_to_volume=True).
        llm_endpoint:    Databricks model-serving endpoint name.
        catalog:         UC catalog for volume write (default 'uc13').
        write_to_volume: If True, also writes the markdown to the reports volume.

    Returns:
        Markdown string.
    """

    company_name     = result.get("company_name", "Company")
    generated_at     = result.get("created_at", "")
    overlay          = result.get("industry_overlay_used", "")
    exec_summary     = result.get("executive_summary") or ""
    addback_pct      = result.get("addback_pct_of_ebitda")
    flags            = result.get("flags") or []
    data_room_gaps   = result.get("data_room_gaps") or []

    revenue_trend    = json.loads(result.get("revenue_trend_json")      or "[]")
    gross_margin     = json.loads(result.get("gross_margin_json")       or "[]")
    ebitda           = json.loads(result.get("ebitda_json")             or "[]")
    rev_by_segment   = json.loads(result.get("revenue_by_segment_json") or "[]")
    cost_structure   = json.loads(result.get("cost_structure_json")     or "{}")
    working_capital  = json.loads(result.get("working_capital_json")    or "{}")
    budget_vs_actual = json.loads(result.get("budget_vs_actual_json")   or "[]")
    addbacks         = json.loads(result.get("addback_schedule_json")   or "[]")
    discrepancies    = json.loads(result.get("discrepancies")           or "[]")

    # ── Helper: period sort key ────────────────────────────────────────────
    def _period_rank(period_str: str) -> int:
        p = (period_str or "").upper()
        if "TTM" in p or "LTM" in p:
            return 9999
        m = re.search(r"(\d{4})", p)
        return int(m.group(1)) if m else 0

    # ── Helper: format a markdown table from list-of-dicts ────────────────
    def _md_table(headers: list[str], rows: list[list]) -> str:
        if not rows:
            return "_No data extracted._\n"
        col_w = [max(len(str(h)), max((len(str(r[i])) for r in rows), default=0))
                 for i, h in enumerate(headers)]
        sep = "| " + " | ".join("-" * w for w in col_w) + " |"
        head = "| " + " | ".join(str(h).ljust(col_w[i]) for i, h in enumerate(headers)) + " |"
        body = "\n".join(
            "| " + " | ".join(str(r[i] if i < len(r) else "").ljust(col_w[i]) for i in range(len(headers))) + " |"
            for r in rows
        )
        return "\n".join([head, sep, body]) + "\n"

    # ── Helper: delta arrow ───────────────────────────────────────────────
    def _arrow(current, previous) -> str:
        if current is None or previous is None:
            return ""
        try:
            diff = float(str(current).replace("%", "").replace(",", "").replace("(", "-").replace(")", ""))
            prev = float(str(previous).replace("%", "").replace(",", "").replace("(", "-").replace(")", ""))
            d = diff - prev
            return f" ▲{round(d,1)}" if d > 0 else (f" ▼{abs(round(d,1))}" if d < 0 else " →0")
        except (ValueError, TypeError):
            return ""

    # ══════════════════════════════════════════════════════════════════════
    # TABLE 1 — Revenue trend (all named lines, all periods + YoY)
    # ══════════════════════════════════════════════════════════════════════
    rev_sorted = sorted(revenue_trend, key=lambda r: (_period_rank(r.get("period", "")), r.get("label", "")))
    rev_rows = []
    for r in rev_sorted:
        rev_rows.append([
            r.get("period", ""),
            r.get("label", ""),
            r.get("revenue_stated", ""),
            r.get("yoy_growth_pct") or "n/a",
        ])
    tbl_revenue = _md_table(["Period", "Revenue Line", "Revenue ($K)", "YoY Growth %"], rev_rows)

    # ══════════════════════════════════════════════════════════════════════
    # TABLE 2 — Gross margin (with period-over-period margin delta)
    # ══════════════════════════════════════════════════════════════════════
    gm_sorted = sorted(gross_margin, key=lambda r: _period_rank(r.get("period", "")))
    gm_rows = []
    prev_gm_pct = None
    for r in gm_sorted:
        pct   = r.get("gm_pct_stated")
        delta = _arrow(pct, prev_gm_pct) if prev_gm_pct is not None else ""
        gm_rows.append([
            r.get("period", ""),
            r.get("label", ""),
            r.get("gm_dollars_stated", ""),
            pct or "n/a",
            delta or "—",
        ])
        prev_gm_pct = pct
    tbl_gm = _md_table(["Period", "Label", "GP ($K)", "GM %", "ΔMargin (pp)"], gm_rows)

    # ══════════════════════════════════════════════════════════════════════
    # TABLE 3 — EBITDA multi-version pivot
    # Rows = periods; columns = distinct EBITDA versions
    # ══════════════════════════════════════════════════════════════════════
    ebitda_sorted = sorted(ebitda, key=lambda r: (_period_rank(r.get("period", "")), r.get("label", "")))
    ebitda_labels = list(dict.fromkeys(r.get("label", "") for r in ebitda_sorted))
    ebitda_periods = list(dict.fromkeys(r.get("period", "") for r in ebitda_sorted))
    ebitda_lookup: dict[tuple, dict] = {
        (r.get("period", ""), r.get("label", "")): r for r in ebitda_sorted
    }
    ebitda_rows = []
    for period in ebitda_periods:
        row = [period]
        for label in ebitda_labels:
            rec = ebitda_lookup.get((period, label))
            if rec:
                dollars = rec.get("ebitda_dollars", "")
                margin  = rec.get("ebitda_margin_pct")
                cell    = f"{dollars}" + (f" ({margin})" if margin else "")
            else:
                cell = "—"
            row.append(cell)
        ebitda_rows.append(row)
    tbl_ebitda = _md_table(["Period"] + [lbl[:35] for lbl in ebitda_labels], ebitda_rows)
    # Margin-only sub-table
    ebitda_margin_rows = []
    for period in ebitda_periods:
        row = [period]
        for label in ebitda_labels:
            rec = ebitda_lookup.get((period, label))
            row.append(rec.get("ebitda_margin_pct") or "—" if rec else "—")
        ebitda_margin_rows.append(row)
    tbl_ebitda_margin = _md_table(["Period"] + [lbl[:35] for lbl in ebitda_labels], ebitda_margin_rows)

    # ══════════════════════════════════════════════════════════════════════
    # TABLE 4 — Revenue by segment
    # ══════════════════════════════════════════════════════════════════════
    seg_rows = [[
        r.get("segment", ""), r.get("revenue_dollars", ""), r.get("revenue_pct") or "—", r.get("period", "")
    ] for r in rev_by_segment]
    tbl_segment = _md_table(["Segment / Line", "Revenue ($K)", "% of Total", "Period"], seg_rows)

    # ══════════════════════════════════════════════════════════════════════
    # TABLE 5 — Addback quality
    # ══════════════════════════════════════════════════════════════════════
    ab_rows = [[
        a.get("description", "")[:60],
        a.get("amount_stated", ""),
        a.get("period", ""),
        a.get("supporting_doc_referenced", "not referenced"),
    ] for a in addbacks]
    tbl_addbacks = _md_table(["Addback Item", "Amount ($K)", "Period", "Supporting Doc"], ab_rows)

    # ══════════════════════════════════════════════════════════════════════
    # TABLE 6 — Budget vs. actual variance
    # ══════════════════════════════════════════════════════════════════════
    bva_rows = []
    for item in budget_vs_actual:
        budget_num = _parse_numeric(item.get("budget_stated"))
        actual_num = _parse_numeric(item.get("actual_stated"))
        if budget_num and actual_num:
            var_abs = round(actual_num - budget_num, 0)
            var_pct = round((actual_num - budget_num) / abs(budget_num) * 100, 1) if budget_num else None
            var_str = f"{'+' if var_abs >= 0 else ''}{int(var_abs)}"
            var_pct_str = f"{'+' if (var_pct or 0) >= 0 else ''}{var_pct}%" if var_pct is not None else "—"
        else:
            var_str = var_pct_str = "—"
        bva_rows.append([
            item.get("period", ""), item.get("metric", ""),
            item.get("budget_stated", ""), item.get("actual_stated", ""),
            var_str, var_pct_str,
        ])
    tbl_bva = _md_table(["Period", "Metric", "Budget", "Actual", "Variance $", "Variance %"], bva_rows)

    # ══════════════════════════════════════════════════════════════════════
    # TABLE 7 — Flags summary
    # ══════════════════════════════════════════════════════════════════════
    flag_rows = [[
        {"Red": "🔴", "Yellow": "🟡", "Green": "🟢"}.get(f.get("severity", ""), "⚪") + " " + f.get("severity", ""),
        f.get("metric", ""),
        f.get("value", ""),
        f.get("threshold", ""),
    ] for f in flags]
    tbl_flags = _md_table(["Severity", "Metric", "Value", "Threshold"], flag_rows)

    # ══════════════════════════════════════════════════════════════════════
    # Assemble data summary passed to the LLM for narrative generation
    # ══════════════════════════════════════════════════════════════════════
    data_summary = f"""
COMPANY: {company_name}
INDUSTRY OVERLAY: {overlay}
EXECUTIVE SUMMARY: {exec_summary}
ADDBACK % OF EBITDA: {f"{addback_pct}%" if addback_pct is not None else "not computed"}

REVENUE TREND TABLE:
{tbl_revenue}

GROSS MARGIN TABLE:
{tbl_gm}

EBITDA MULTI-VERSION TABLE (dollars + margin %):
{tbl_ebitda}

EBITDA MARGIN % TABLE:
{tbl_ebitda_margin}

REVENUE BY SEGMENT TABLE:
{tbl_segment}

ADDBACK SCHEDULE TABLE:
{tbl_addbacks}

BUDGET VS. ACTUAL TABLE:
{tbl_bva}

COST STRUCTURE:
{json.dumps(cost_structure, indent=2)}

WORKING CAPITAL:
{json.dumps(working_capital, indent=2)}

DISCREPANCIES:
{json.dumps(discrepancies, indent=2)}

INVESTMENT FLAGS:
{json.dumps(flags, indent=2)}

DATA ROOM GAPS:
{chr(10).join("- " + g for g in data_room_gaps) if data_room_gaps else "None"}
""".strip()

    # ══════════════════════════════════════════════════════════════════════
    # LLM call — financial story narrative
    # ══════════════════════════════════════════════════════════════════════
    _ASSESS_SYS = """\
You are a senior PE investment analyst writing a financial story assessment section
of an internal diligence memo. Your task is to synthesize the structured financial
data provided and answer 12 specific questions about whether the financial story is
improving, deteriorating, or being distorted by mix, timing, addbacks, or accounting.

Rules:
1. Write only what the data supports. Do not invent facts.
2. If a section cannot be assessed because data is missing, write one sentence
   explaining what is missing and why it matters.
3. Use concrete numbers from the tables when making observations.
4. Be direct and use PE language (e.g. "compressed", "diluted", "held back by",
   "inflated by addbacks", "ahead of revenue growth", "operating leverage not yet
   visible", "not achievable without acceleration").
5. Return your response as pure markdown only — no preamble, no code fences.
6. Structure your response with exactly these 12 section headers (H3):
   ### 1. Revenue Growth
   ### 2. Gross Margin Expansion or Compression
   ### 3. EBITDA Margin Trends
   ### 4. Contribution Margin by Dimension
   ### 5. Revenue Bridge (Price / Volume / Mix / New Logos / Churn / Expansion)
   ### 6. Cost Structure and Operating Leverage
   ### 7. Addback Quality and Recurrence
   ### 8. Seasonality and Timing Effects
   ### 9. Working Capital Trends
   ### 10. Cash Conversion and EBITDA-to-Cash Flow Bridge
   ### 11. Budget vs. Actual Performance
   ### 12. Forecast Achievability vs. Historical Run-Rate
7. For each section use at most 4 bullet points followed by a 1–2 sentence
   "**Analyst take:**" line that states the signal and what it means for underwriting.
"""

    _ASSESS_USER = f"""\
Use the financial data below to answer all 12 assessment questions.
Write the markdown narrative only — no extra commentary.

{data_summary}
"""

    import mlflow.deployments
    _client = mlflow.deployments.get_deploy_client("databricks")
    _response = _client.predict(
        endpoint=llm_endpoint,
        inputs={
            "messages": [
                {"role": "system", "content": _ASSESS_SYS},
                {"role": "user",   "content": _ASSESS_USER},
            ],
            "max_tokens": 4000,
            "temperature": 0.1,
        },
    )
    narrative = _response["choices"][0]["message"]["content"].strip()

    # ══════════════════════════════════════════════════════════════════════
    # Assemble final markdown
    # ══════════════════════════════════════════════════════════════════════
    flag_severity_order = {"Red": 0, "Yellow": 1, "Green": 2}
    flags_sorted = sorted(flags, key=lambda f: flag_severity_order.get(f.get("severity", ""), 3))

    md_parts: list[str] = []

    md_parts.append(f"# {company_name} — Financial Story Assessment")
    md_parts.append(f"**Generated:** {generated_at}  \n**Industry Overlay:** {overlay}\n")

    if exec_summary:
        md_parts.append(f"> {exec_summary}\n")

    md_parts.append("---\n")

    # ── Investment flags quick-reference ──────────────────────────────────
    if flags_sorted:
        md_parts.append("## Investment Flags\n")
        md_parts.append(tbl_flags)
        md_parts.append("")

    # ── Supporting data tables ─────────────────────────────────────────────
    md_parts.append("---\n")
    md_parts.append("## Supporting Data\n")

    md_parts.append("### Revenue Trend\n")
    md_parts.append(tbl_revenue)

    md_parts.append("### Gross Margin\n")
    md_parts.append(tbl_gm)

    md_parts.append("### EBITDA — All Named Versions\n")
    md_parts.append("> Cells show `dollars (margin %)` where available.\n")
    md_parts.append(tbl_ebitda)

    md_parts.append("### EBITDA Margin % by Version\n")
    md_parts.append(tbl_ebitda_margin)

    if rev_by_segment:
        md_parts.append("### Revenue by Segment / Geography\n")
        md_parts.append(tbl_segment)

    if addbacks:
        md_parts.append(f"### Addback Schedule  _(Addback % of Reported EBITDA: {f'{addback_pct}%' if addback_pct is not None else 'n/a'})_\n")
        md_parts.append(tbl_addbacks)

    if budget_vs_actual:
        md_parts.append("### Budget vs. Actual\n")
        md_parts.append(tbl_bva)

    if working_capital.get("dso_days") or working_capital.get("dpo_days") or working_capital.get("ar_aging_note"):
        md_parts.append("### Working Capital\n")
        wc_rows = [
            ["DSO (days)", working_capital.get("dso_days") or "n/a"],
            ["DPO (days)", working_capital.get("dpo_days") or "n/a"],
            ["AR Aging Note", working_capital.get("ar_aging_note") or "n/a"],
        ]
        md_parts.append(_md_table(["Metric", "Value"], wc_rows))

    if cost_structure.get("headcount_pct_of_revenue") or cost_structure.get("fixed_vs_variable_note"):
        md_parts.append("### Cost Structure\n")
        cs_rows = [
            ["Headcount % of Revenue", cost_structure.get("headcount_pct_of_revenue") or "n/a"],
            ["Fixed vs. Variable", cost_structure.get("fixed_vs_variable_note") or "n/a"],
            ["Key Categories", ", ".join(cost_structure.get("key_categories") or []) or "n/a"],
        ]
        md_parts.append(_md_table(["Item", "Detail"], cs_rows))

    if discrepancies:
        md_parts.append("### Discrepancies Found\n")
        disc_rows = [[d.get("metric", ""), " vs ".join(d.get("conflicting_values") or []), d.get("note", "")] for d in discrepancies]
        md_parts.append(_md_table(["Metric", "Conflicting Values", "Note"], disc_rows))

    # ── LLM narrative ─────────────────────────────────────────────────────
    md_parts.append("---\n")
    md_parts.append("## Financial Story Assessment\n")
    md_parts.append(narrative)
    md_parts.append("")

    # ── Data room gaps ─────────────────────────────────────────────────────
    if data_room_gaps:
        md_parts.append("---\n")
        md_parts.append("## Data Room Gaps\n")
        for gap in data_room_gaps:
            md_parts.append(f"- {gap}")
        md_parts.append("")

    final_markdown = "\n".join(md_parts)

    # ── Optional volume write ──────────────────────────────────────────────
    if write_to_volume:
        spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.analysis.reports")
        safe_name = company_name.replace(" ", "_").replace("/", "_")
        dir_path  = f"/Volumes/{catalog}/analysis/reports/{safe_name}"
        os.makedirs(dir_path, exist_ok=True)
        file_path = f"{dir_path}/financial_assessment.md"
        with open(file_path, "w", encoding="utf-8") as fh:
            fh.write(final_markdown)
        print(f"✓ Financial assessment → {file_path}")

    return final_markdown


def _write_stakeholder_report(result: dict, catalog: str, spark) -> str:
    """Write a clean, human-readable YAML report to a UC Volume.

    Saves to /Volumes/{catalog}/analysis/reports/{company_name}/
    financial_trends_report.yaml (or .json if PyYAML is unavailable).
    Returns the full volume path of the written file.
    """
    company_name = result["company_name"]

    # ── Parse JSON blobs back to Python objects for clean rendering ────
    revenue_trend    = json.loads(result.get("revenue_trend_json")       or "[]")
    gross_margin     = json.loads(result.get("gross_margin_json")        or "[]")
    ebitda           = json.loads(result.get("ebitda_json")              or "[]")
    rev_by_segment   = json.loads(result.get("revenue_by_segment_json")  or "[]")
    cost_structure   = json.loads(result.get("cost_structure_json")      or "{}")
    working_capital  = json.loads(result.get("working_capital_json")     or "{}")
    budget_vs_actual = json.loads(result.get("budget_vs_actual_json")    or "[]")
    addbacks         = json.loads(result.get("addback_schedule_json")    or "[]")
    discrepancies    = json.loads(result.get("discrepancies")            or "[]")
    citations        = json.loads(result.get("citations")                or "[]")

    addback_pct = result.get("addback_pct_of_ebitda")

    # ── Build the curated report dict ──────────────────────────────────
    report = {
        "report": {
            "agent":              "financial_trends",
            "company":            company_name,
            "generated_at":       result.get("created_at", ""),
            "industry_overlay":   result.get("industry_overlay_used"),
        },
        "executive_summary": result.get("executive_summary"),
        "revenue_trend":     revenue_trend,
        "gross_margin":      gross_margin,
        "ebitda":            ebitda,
        "revenue_by_segment": rev_by_segment,
        "cost_structure":    cost_structure,
        "working_capital":   working_capital,
        "budget_vs_actual":  budget_vs_actual,
        "addback_schedule": {
            "items":                addbacks,
            "addback_pct_of_ebitda": addback_pct,
        },
        "flags":           result.get("flags") or [],
        "discrepancies":   discrepancies,
        "data_room_gaps":  result.get("data_room_gaps") or [],
        "citations":       citations,
    }

    # ── Note any fields that were computed rather than directly stated ──
    computed_notes = []
    for item in ebitda:
        if item.get("ebitda_margin_pct") and "computed" in str(item.get("ebitda_margin_pct", "")):
            computed_notes.append(
                f"EBITDA margin for '{item.get('label', 'EBITDA')}' "
                f"period {item.get('period')} was computed from stated dollar values, "
                "not extracted from a stated margin % row."
            )
    for item in gross_margin:
        if item.get("gm_pct_stated") and "computed" in str(item.get("gm_pct_stated", "")):
            computed_notes.append(
                f"Gross margin for period {item.get('period')} was computed from stated "
                "dollar values, not extracted from a stated margin % row."
            )
    for item in revenue_trend:
        if item.get("yoy_growth_pct") and "computed" in str(item.get("yoy_growth_pct", "")):
            computed_notes.append(
                f"YoY growth for period {item.get('period')} was computed from "
                "consecutive stated revenue values, not extracted from a stated Growth row."
            )
    if computed_notes:
        report["computed_fields_notes"] = computed_notes

    # ── Render as YAML (preferred) or JSON fallback ────────────────────
    try:
        import yaml

        def _str_representer(dumper, data):
            if "\n" in data:
                return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
            return dumper.represent_scalar("tag:yaml.org,2002:str", data)

        yaml.add_representer(str, _str_representer)
        content = yaml.dump(report, allow_unicode=True, sort_keys=False, width=120)
        ext     = "yaml"
    except ImportError:
        content = json.dumps(report, indent=2, ensure_ascii=False)
        ext     = "json"

    # ── Ensure the UC Volume and directory exist ───────────────────────
    spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.analysis.reports")
    safe_name = company_name.replace(" ", "_").replace("/", "_")
    dir_path  = f"/Volumes/{catalog}/analysis/reports/{safe_name}"
    import os
    os.makedirs(dir_path, exist_ok=True)

    file_path = f"{dir_path}/financial_trends_report.{ext}"
    with open(file_path, "w", encoding="utf-8") as fh:
        fh.write(content)

    return file_path


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {table} (
    company_name                STRING,
    executive_summary           STRING,
    industry_overlay_used       STRING,
    revenue_trend_json          STRING,
    gross_margin_json           STRING,
    ebitda_json                 STRING,
    revenue_by_segment_json     STRING,
    cost_structure_json         STRING,
    working_capital_json        STRING,
    budget_vs_actual_json       STRING,
    addback_schedule_json       STRING,
    addback_pct_of_ebitda       FLOAT,
    flags                       STRING,
    discrepancies               STRING,
    data_room_gaps              ARRAY<STRING>,
    citations                   STRING,
    reasoning_trace             STRING,
    created_at                  TIMESTAMP
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

    print(f"\n=== Financial Trends Agent ({company_name}) ===")

    agent = FinancialTrendsAgent()
    result = agent.run(company_name=company_name, spark=spark, llm_endpoint=llm_endpoint)

    # ── Save to Delta ─────────────────────────────────────────────────
    table = f"{catalog}.analysis.financial_trends"
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.analysis")
    spark.sql(_CREATE_TABLE_SQL.format(table=table))
    spark.sql(f"DELETE FROM {table} WHERE company_name = '{company_name}'")

    from pyspark.sql import Row
    from pyspark.sql.types import (
        StructType, StructField, StringType, FloatType,
        ArrayType, TimestampType,
    )

    schema = StructType([
        StructField("company_name",             StringType(),  True),
        StructField("executive_summary",        StringType(),  True),
        StructField("industry_overlay_used",    StringType(),  True),
        StructField("revenue_trend_json",       StringType(),  True),
        StructField("gross_margin_json",        StringType(),  True),
        StructField("ebitda_json",              StringType(),  True),
        StructField("revenue_by_segment_json",  StringType(),  True),
        StructField("cost_structure_json",      StringType(),  True),
        StructField("working_capital_json",     StringType(),  True),
        StructField("budget_vs_actual_json",    StringType(),  True),
        StructField("addback_schedule_json",    StringType(),  True),
        StructField("addback_pct_of_ebitda",    FloatType(),   True),
        StructField("flags",                    StringType(),  True),
        StructField("discrepancies",            StringType(),  True),
        StructField("data_room_gaps",           ArrayType(StringType()), True),
        StructField("citations",                StringType(),  True),
        StructField("reasoning_trace",          StringType(),  True),
        StructField("created_at",               TimestampType(), True),
    ])

    row_data = {
        "company_name":             result["company_name"],
        "executive_summary":        result.get("executive_summary"),
        "industry_overlay_used":    result.get("industry_overlay_used"),
        "revenue_trend_json":       result.get("revenue_trend_json"),
        "gross_margin_json":        result.get("gross_margin_json"),
        "ebitda_json":              result.get("ebitda_json"),
        "revenue_by_segment_json":  result.get("revenue_by_segment_json"),
        "cost_structure_json":      result.get("cost_structure_json"),
        "working_capital_json":     result.get("working_capital_json"),
        "budget_vs_actual_json":    result.get("budget_vs_actual_json"),
        "addback_schedule_json":    result.get("addback_schedule_json"),
        "addback_pct_of_ebitda":    result.get("addback_pct_of_ebitda"),
        "flags":                    json.dumps(result.get("flags") or []),
        "discrepancies":            result.get("discrepancies"),
        "data_room_gaps":           result.get("data_room_gaps") or [],
        "citations":                result.get("citations"),
        "reasoning_trace":          json.dumps(result.get("reasoning_trace") or []),
        "created_at":               datetime.now(timezone.utc),
    }

    df = spark.createDataFrame([Row(**row_data)], schema=schema)
    df.write.format("delta").mode("append").saveAsTable(table)

    print(f"\n✓ Saved financial trends output → {table}")

    # ── Export stakeholder report ──────────────────────────────────────
    report_path = _write_stakeholder_report(result, catalog, spark)
    result["report_path"] = report_path
    print(f"✓ Stakeholder report → {report_path}")

    return result


if __name__ == "__main__":
    main()
