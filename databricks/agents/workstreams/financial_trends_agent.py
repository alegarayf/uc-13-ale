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

import concurrent.futures
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_CATALOG = os.environ.get("catalog", "uc13")

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
# Moved to agents/subagents/workstream/financial/shared_prompts.py
# (SYSTEM_PROMPT_BASE rules 1-10, SYSTEM_PROMPT_EBITDA rules 1-13)

# Extraction prompts and system prompts have moved to:
#   agents/subagents/workstream/financial/shared_prompts.py  (system prompts)
#   agents/subagents/workstream/financial/revenue_sub_agent.py
#   agents/subagents/workstream/financial/ebitda_sub_agent.py
#   agents/subagents/workstream/financial/opex_sub_agent.py
# The orchestrator (FinancialTrendsAgent.run) fans out to these three sub-agents
# in parallel via ThreadPoolExecutor(max_workers=3).


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


def _normalize_pct_for_threshold(value: Optional[float]) -> Optional[float]:
    """Convert decimal-fraction percentages to 0–100 scale before threshold comparison.

    Excel workbooks routinely store percentages as decimal fractions
    (e.g. 0.4093 meaning 40.93%).  When these values reach the threshold
    evaluation layer as-is, comparisons like `0.4093 < 30` fire false Red
    flags.  Heuristic: any value in (0, 1) exclusive is almost certainly a
    decimal fraction representing a percentage — multiply by 100.

    Values ≥ 1 (e.g. 40.93 already on a 0–100 scale) or ≤ 0 are returned
    unchanged.  Values exactly equal to 0 or 1 are ambiguous edge cases and
    are also returned unchanged to avoid inflating true 0% or 100% readings.
    """
    if value is None:
        return None
    return value * 100 if 0.0 < value < 1.0 else value


def _fmt_pct(value_str: Optional[str]) -> str:
    """Format a percentage value for display, handling decimal fractions.

    '0.4093201323802183' → '40.9%'
    '42.1%'             → '42.1%'
    '42.1'              → '42.1%'
    None / unparseable  → 'n/a'
    """
    if value_str is None:
        return "n/a"
    num = _parse_numeric(str(value_str))
    if num is None:
        return str(value_str)
    num = _normalize_pct_for_threshold(num)
    return f"{round(num, 1)}%"


def _fmt_dollars(value_str: Optional[str]) -> str:
    """Format a dollar/number value for display, removing float noise.

    '159.94150000000002' → '159.9'
    '9,027'             → '9,027'
    '(342)'             → '(342)'
    None / unparseable  → 'n/a'
    """
    if value_str is None:
        return "n/a"
    s = str(value_str).strip()
    # Already nicely formatted (contains comma or parens)
    if "," in s or "(" in s:
        return s
    num = _parse_numeric(s)
    if num is None:
        return s
    # Drop floating-point noise: show up to 1 decimal place, strip trailing .0
    formatted = f"{num:,.1f}".rstrip("0").rstrip(".")
    return formatted


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

    def _tool_load_company_profile(self, company_name: str, spark):
        rows = spark.sql(f"""
            SELECT * FROM {_CATALOG}.classification.company_profile
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
            source_docs=[f"{_CATALOG}.classification.company_profile"],
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

        # Normalize decimal-fraction percentages (Excel stores 0.6917 meaning 69.17%)
        # before any threshold comparison.  Applied once here; both tech and
        # healthcare branches read from the same growth_num variable.
        growth_num = _normalize_pct_for_threshold(growth_num)

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
        gm_num = _normalize_pct_for_threshold(gm_num)

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
        ebitda_margin_num = _normalize_pct_for_threshold(ebitda_margin_num)

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
        bva_records = extracted.get("budget_vs_actual") or []

        # If no budget vs. actual data was extracted at all, log an actionable gap
        # rather than leaking a code-artifact message into the analyst output.
        if not bva_records or all(
            item.get("budget_stated") is None and item.get("actual_stated") is None
            for item in bva_records
        ):
            self._add_gap(
                "Budget vs. actual data was not found in retrieved documents. "
                "If the data room includes a management reporting package, board deck, "
                "monthly controller report, or rolling forecast, confirm those files are "
                "tagged with the FINANCIAL workstream and re-run the agent. "
                "Budget vs. actual is required to assess forecast credibility."
            )
            return

        for item in bva_records:
            budget_num = _parse_numeric(item.get("budget_stated"))
            actual_num = _parse_numeric(item.get("actual_stated"))
            metric     = item.get("metric", "unknown")
            period     = item.get("period", "unknown")
            source_doc = item.get("source_doc", "")

            if budget_num is None or actual_num is None or budget_num == 0:
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

    def run(self, company_name: str, spark, llm_endpoint: str,
            extraction_endpoint: str = None,
            retrieval_mode: str = "semantic") -> dict:
        self._reset_state()
        self._company_name = company_name
        _extract_ep = extraction_endpoint or llm_endpoint

        # ── Company profile (shared metadata for all sub-agents) ─────
        tr_profile   = self._tool_load_company_profile(company_name, spark)
        profile_dict = tr_profile.data
        overlay      = profile_dict.get("industry_overlay") if profile_dict else None

        # ── Autonomous sub-agents in parallel ─────────────────────────
        # Each sub-agent owns its own focused retrieval (2–5 semantic_search
        # calls) and builds its own context budget independently, so each
        # LLM call sees only the chunks relevant to its extraction domain.
        from agents.subagents.workstream.financial import (
            RevenueSubAgent, EbitdaSubAgent, OpexSubAgent,
        )

        _sub_args = (company_name, spark, _extract_ep, profile_dict, retrieval_mode)

        print(f"  Launching 3 autonomous sub-agents in parallel (retrieval_mode={retrieval_mode}) ...")
        _t0 = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as _pool:
            _f_rev  = _pool.submit(RevenueSubAgent().run, *_sub_args)
            _f_ebi  = _pool.submit(EbitdaSubAgent().run,  *_sub_args)
            _f_opex = _pool.submit(OpexSubAgent().run,    *_sub_args)
            _r_rev  = _f_rev.result()
            _r_ebi  = _f_ebi.result()
            _r_opex = _f_opex.result()
        _elapsed = time.time() - _t0
        print(f"  Sub-agents finished in {_elapsed:.0f}s (parallel)")

        # Merge: disjoint schemas — no key collision expected
        extracted = {
            **_r_rev.get("extracted",  {}),
            **_r_ebi.get("extracted",  {}),
            **_r_opex.get("extracted", {}),
        }

        # Propagate sub-agent gaps into the orchestrator's gap list
        for _gap in _r_rev.get("gaps", []) + _r_ebi.get("gaps", []) + _r_opex.get("gaps", []):
            self._add_gap(_gap)

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

        # Check 2: at least one adjusted EBITDA version (Rule 13: only pf_adjusted or clinic_level_adjusted)
        _adjusted_versions = {"pf_adjusted", "clinic_level_adjusted",
                              # legacy versions tolerated if LLM ignores the cap
                              "mgmt_adjusted", "diligence_adjusted"}
        if _ebitda_records and not _adjusted_versions.intersection(_versions_found):
            self._add_gap(
                "No adjusted EBITDA version found (pf_adjusted / clinic_level_adjusted). "
                "If an adjusted EBITDA concept exists in the documents, check retrieval and extraction coverage."
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

        _all_source_files = list({
            f for r in (_r_rev, _r_ebi, _r_opex) for f in r.get("source_files", [])
        })
        llm_step = len(self._base._trace) + 1
        self._base._trace.append({
            "step":       llm_step,
            "tool":       "llm_extraction_parallel_3_subagents",
            "input":      f"3 autonomous sub-agents (revenue/ebitda/opex) with focused retrieval | elapsed={_elapsed:.0f}s",
            "output":     (
                f"Revenue: {len(extracted.get('revenue_trend') or [])} periods | "
                f"GrossMargin: {len(extracted.get('gross_margin') or [])} | "
                f"Segments: {len(extracted.get('revenue_by_segment') or [])} | "
                f"OPEX: {len(extracted.get('opex_breakdown') or [])} | "
                f"EBITDA: {len(extracted.get('ebitda') or [])} records | "
                f"Addbacks: {len(extracted.get('addback_schedule') or [])}"
            ),
            "confidence": "high" if _all_source_files else "low",
            "sources":    _all_source_files,
        })
        print(
            f"  Extraction complete: "
            f"rev={len(extracted.get('revenue_trend') or [])} "
            f"gm={len(extracted.get('gross_margin') or [])} "
            f"seg={len(extracted.get('revenue_by_segment') or [])} "
            f"opex={len(extracted.get('opex_breakdown') or [])} "
            f"ebitda={len(extracted.get('ebitda') or [])} "
            f"addbacks={len(extracted.get('addback_schedule') or [])}"
        )

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
            "revenue_by_customer_json": json.dumps(extracted.get("revenue_by_customer") or []),
            "cost_structure_json":      json.dumps(extracted.get("cost_structure") or {}),
            "working_capital_json":     json.dumps(extracted.get("working_capital") or {}),
            "budget_vs_actual_json":    json.dumps(extracted.get("budget_vs_actual") or []),
            "addback_schedule_json":    json.dumps(extracted.get("addback_schedule") or []),
            "opex_breakdown_json":      json.dumps(extracted.get("opex_breakdown") or []),
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

    company_name   = result.get("company_name", "Company")
    generated_at   = result.get("created_at", "")
    overlay        = result.get("industry_overlay_used", "")
    exec_summary   = result.get("executive_summary") or ""
    addback_pct    = result.get("addback_pct_of_ebitda")
    flags          = result.get("flags") or []
    data_room_gaps = result.get("data_room_gaps") or []

    revenue_trend    = json.loads(result.get("revenue_trend_json")       or "[]")
    gross_margin     = json.loads(result.get("gross_margin_json")        or "[]")
    ebitda           = json.loads(result.get("ebitda_json")              or "[]")
    rev_by_segment   = json.loads(result.get("revenue_by_segment_json") or "[]")
    rev_by_customer  = json.loads(result.get("revenue_by_customer_json") or "[]")
    opex_breakdown   = json.loads(result.get("opex_breakdown_json")      or "[]")
    working_capital = json.loads(result.get("working_capital_json")     or "{}")
    budget_vs_actual= json.loads(result.get("budget_vs_actual_json")   or "[]")
    addbacks        = json.loads(result.get("addback_schedule_json")   or "[]")
    discrepancies   = json.loads(result.get("discrepancies")            or "[]")

    # ── Period sort key ────────────────────────────────────────────────────
    def _period_rank(p: str) -> int:
        p = (p or "").upper()
        if "TTM" in p or "LTM" in p:
            return 9999
        m = re.search(r"(\d{4})", p)
        return int(m.group(1)) if m else 0

    # ── Collect all periods present across key tables ──────────────────────
    _all_periods_raw = (
        [r.get("period") for r in revenue_trend] +
        [r.get("period") for r in ebitda] +
        [r.get("period") for r in gross_margin]
    )
    all_periods = sorted(
        list(dict.fromkeys(p for p in _all_periods_raw if p)),
        key=_period_rank,
    )

    # ── Lookup helpers ─────────────────────────────────────────────────────
    def _rev_lookup(period: str) -> str:
        for r in revenue_trend:
            if r.get("period") == period:
                return _fmt_dollars(r.get("revenue_stated"))
        return "—"

    def _growth_lookup(period: str) -> str:
        for r in revenue_trend:
            if r.get("period") == period and r.get("yoy_growth_pct"):
                return _fmt_pct(r.get("yoy_growth_pct"))
        return "—"

    def _gm_lookup(period: str, field: str) -> str:
        for r in gross_margin:
            if r.get("period") == period:
                val = r.get(field)
                if val:
                    return _fmt_dollars(val) if field == "gm_dollars_stated" else _fmt_pct(val)
        return "—"

    def _ebitda_lookup(period: str, version_keys: list) -> tuple:
        """Return (dollars, margin_pct) for the first matching version."""
        for r in ebitda:
            if r.get("period") == period and (r.get("version") or "") in version_keys:
                return (
                    _fmt_dollars(r.get("ebitda_dollars")),
                    _fmt_pct(r.get("ebitda_margin_pct")) if r.get("ebitda_margin_pct") else "—",
                )
        return ("—", "—")

    # ── Compact P&L grid (actuals + TTM only; no projected columns) ───────
    # Projected periods (2024E, 2025P, etc.) expand the table beyond one page
    # and distract from the historical signal that matters at IC stage.
    def _is_projected(p: str) -> bool:
        return bool(re.search(r"\d{4}[EP]", (p or "").upper()))

    _compact_periods = [p for p in all_periods if not _is_projected(p)]
    if not _compact_periods:
        _compact_periods = all_periods  # fallback: show whatever we have

    def _pl_row(label: str, values: list, bold: bool = False) -> str:
        lbl = f"**{label}**" if bold else label
        cells = " | ".join(str(v) for v in values)
        return f"| {lbl} | {cells} |"

    _cp = _compact_periods
    _n  = len(_cp)
    period_headers = " | ".join(_cp) if _cp else "(no periods extracted)"
    col_sep        = " | ".join(["---"] * _n) if _n else "---"

    pl_lines = [
        f"| Line Item | {period_headers} |",
        f"|---|{col_sep}|",
    ]

    # Revenue
    pl_lines.append(_pl_row("Revenue ($K)", [_rev_lookup(p) for p in _cp], bold=True))
    pl_lines.append(_pl_row("YoY Growth %", [_growth_lookup(p) for p in _cp]))

    # Revenue segments (≤5, dollar values preferred over pct)
    _seg_names = list(dict.fromkeys(r.get("segment", "") for r in rev_by_segment if r.get("segment")))[:5]
    for seg in _seg_names:
        seg_vals = []
        for p in _cp:
            match = next((r for r in rev_by_segment if r.get("segment") == seg and r.get("period") == p), None)
            if match:
                seg_vals.append(_fmt_dollars(match.get("revenue_dollars")) if match.get("revenue_dollars")
                                else (_fmt_pct(match.get("revenue_pct")) if match.get("revenue_pct") else "—"))
            else:
                seg_vals.append("—")
        pl_lines.append(_pl_row(f"↳ {seg}", seg_vals))

    # Gross Profit / Margin
    pl_lines.append(_pl_row("Gross Profit ($K)", [_gm_lookup(p, "gm_dollars_stated") for p in _cp], bold=True))
    pl_lines.append(_pl_row("Gross Margin %", [_gm_lookup(p, "gm_pct_stated") for p in _cp]))

    # Reported EBITDA
    _adj_versions = ["pf_adjusted", "mgmt_adjusted", "diligence_adjusted", "clinic_level_adjusted"]
    reported_vals = [_ebitda_lookup(p, ["reported"]) for p in _cp]
    pl_lines.append(_pl_row("EBITDA Reported ($K)", [v[0] for v in reported_vals], bold=True))
    pl_lines.append(_pl_row("EBITDA Margin %",      [v[1] for v in reported_vals]))

    # Adjusted EBITDA
    adj_vals = [_ebitda_lookup(p, _adj_versions) for p in _cp]
    pl_lines.append(_pl_row("EBITDA Adjusted ($K)", [v[0] for v in adj_vals], bold=True))
    pl_lines.append(_pl_row("Adj. EBITDA Margin %", [v[1] for v in adj_vals]))

    tbl_pl = "\n".join(pl_lines)

    # ── Customer concentration table (separate from P&L) ──────────────────
    _tbl_customers = ""
    if rev_by_customer:
        _cust_sorted = sorted(
            rev_by_customer,
            key=lambda r: (int(r.get("rank") or 99), -(_parse_numeric(r.get("revenue_dollars")) or 0)),
        )
        _seen_cust: set = set()
        _top_customers = []
        for _c in _cust_sorted:
            _nm = (_c.get("customer_name") or "").strip()
            if _nm and _nm not in _seen_cust:
                _seen_cust.add(_nm)
                _top_customers.append(_c)
            if len(_top_customers) >= 10:
                break
        _cust_lines = [
            "| # | Customer | Revenue ($K) | % of Revenue | Period |",
            "|---|---|---|---|---|",
        ]
        for _idx, _c in enumerate(_top_customers, 1):
            _nm  = (_c.get("customer_name") or "—")[:35]
            _amt = _fmt_dollars(_c.get("revenue_dollars"))
            _pct = _fmt_pct(_c.get("revenue_pct")) if _c.get("revenue_pct") else "—"
            _per = _c.get("period") or "—"
            _cust_lines.append(f"| {_idx} | {_nm} | {_amt} | {_pct} | {_per} |")
        _tbl_customers = "\n".join(_cust_lines)

    # ── Cost & EBITDA Detail table ─────────────────────────────────────────
    # OPEX: index records as {category: {period: amount}}
    _opex_idx: dict = {}
    for rec in opex_breakdown:
        cat = (rec.get("category") or "").strip()
        per = (rec.get("period") or "").strip()
        amt = _parse_numeric(rec.get("amount_stated"))
        if cat and per and amt is not None:
            _opex_idx.setdefault(cat, {})[per] = amt

    # Rank categories by total absolute magnitude across ALL periods (not just compact)
    _all_opex_cats = sorted(
        _opex_idx.keys(),
        key=lambda c: sum(abs(v) for v in _opex_idx[c].values()),
        reverse=True,
    )
    _top4_cats  = _all_opex_cats[:4]
    _other_cats = _all_opex_cats[4:]

    def _opex_cell(category: str, period: str) -> str:
        amt = _opex_idx.get(category, {}).get(period)
        return _fmt_dollars(amt) if amt is not None else "—"

    def _opex_other_cell(period: str) -> str:
        vals = [_opex_idx.get(c, {}).get(period) for c in _other_cats]
        vals = [v for v in vals if v is not None]
        return _fmt_dollars(sum(vals)) if vals else "—"

    def _opex_total_cell(period: str) -> str:
        vals = [_opex_idx.get(c, {}).get(period) for c in _all_opex_cats]
        vals = [v for v in vals if v is not None]
        return _fmt_dollars(sum(vals)) if vals else "—"

    # Addback per period: compute as (Adj EBITDA − Reported EBITDA) when available.
    # This is the net addback total — the itemized schedule lives in the Addback Bridge table.
    def _net_addback_cell(period: str) -> str:
        rep_d, _ = _ebitda_lookup(period, ["reported"])
        adj_d, _ = _ebitda_lookup(period, _adj_versions)
        rep_n = _parse_numeric(rep_d.replace("(", "-").replace(")", "")) if rep_d != "—" else None
        adj_n = _parse_numeric(adj_d.replace("(", "-").replace(")", "")) if adj_d != "—" else None
        if rep_n is not None and adj_n is not None:
            return _fmt_dollars(adj_n - rep_n)
        return "—"

    # Build the combined Cost & EBITDA Detail rows
    _ce_hdr  = " | ".join(_cp)
    _ce_sep  = " | ".join(["---"] * _n)
    _ce_lines = [
        f"| Line Item | {_ce_hdr} |",
        f"|---|{_ce_sep}|",
    ]

    # Gross Profit header row (context anchor for the OPEX section below)
    _ce_lines.append(_pl_row("Gross Profit ($K)", [_gm_lookup(p, "gm_dollars_stated") for p in _cp], bold=True))
    _ce_lines.append(_pl_row("Gross Margin %",    [_gm_lookup(p, "gm_pct_stated")      for p in _cp]))

    # OPEX section — only if we have data
    _has_opex_data = bool(_opex_idx)
    if _has_opex_data:
        for cat in _top4_cats:
            _ce_lines.append(_pl_row(f"↳ {cat}", [_opex_cell(cat, p) for p in _cp]))
        if _other_cats:
            _ce_lines.append(_pl_row("↳ Other OpEx", [_opex_other_cell(p) for p in _cp]))
        _total_vals = [_opex_total_cell(p) for p in _cp]
        if any(v != "—" for v in _total_vals):
            _ce_lines.append(_pl_row("Total OpEx ($K)", _total_vals, bold=True))
    else:
        _ce_lines.append(_pl_row("↳ (OpEx detail not extracted)", ["—"] * _n))

    # EBITDA bridge
    rep_ce_vals = [_ebitda_lookup(p, ["reported"]) for p in _cp]
    _ce_lines.append(_pl_row("EBITDA Reported ($K)", [v[0] for v in rep_ce_vals], bold=True))
    _ce_lines.append(_pl_row("EBITDA Margin %",      [v[1] for v in rep_ce_vals]))

    # Net addbacks row (computed; directs reader to itemized Addback Bridge table below)
    _net_ab_vals = [_net_addback_cell(p) for p in _cp]
    _ab_row_label = "↳ Total Addbacks (see bridge below)" if addbacks else "↳ Addback detail (not extracted)"
    _ce_lines.append(_pl_row(_ab_row_label, _net_ab_vals))

    # Adjusted EBITDA
    adj_ce_vals = [_ebitda_lookup(p, _adj_versions) for p in _cp]
    _ce_lines.append(_pl_row("EBITDA Adjusted ($K)", [v[0] for v in adj_ce_vals], bold=True))
    _ce_lines.append(_pl_row("Adj. EBITDA Margin %", [v[1] for v in adj_ce_vals]))

    # PF Adjusted EBITDA — only if a pf_adjusted version is present and has data
    pf_ce_vals = [_ebitda_lookup(p, ["pf_adjusted"]) for p in _cp]
    if any(v[0] != "—" for v in pf_ce_vals):
        _ce_lines.append(_pl_row("PF Adjusted EBITDA ($K)", [v[0] for v in pf_ce_vals], bold=True))
        _ce_lines.append(_pl_row("PF Adj. EBITDA Margin %", [v[1] for v in pf_ce_vals]))

    tbl_cost_ebitda = "\n".join(_ce_lines)

    # ── Material deviation flag ────────────────────────────────────────────
    _deviation_flags: list[str] = []
    for p in all_periods:
        rep_d, _ = _ebitda_lookup(p, ["reported"])
        adj_d, _ = _ebitda_lookup(p, _adj_versions)
        rep_n = _parse_numeric(rep_d.replace("(", "-").replace(")", "")) if rep_d != "—" else None
        adj_n = _parse_numeric(adj_d.replace("(", "-").replace(")", "")) if adj_d != "—" else None
        if rep_n is not None and adj_n is not None and rep_n != 0:
            gap_pct = abs((adj_n - rep_n) / abs(rep_n)) * 100
            if gap_pct >= 20:
                _deviation_flags.append(
                    f"⚠️ **{p}**: Reported EBITDA {rep_d} → Adjusted {adj_d} "
                    f"({gap_pct:.0f}% uplift). Verify addback support."
                )

    # ── Addback bridge table (period-column format, matches CIM EBITDA Adjustment Detail) ──
    # Build index: description → {period: amount}
    _ab_idx: dict = {}
    for _ab in addbacks:
        _ab_desc = (((_ab.get("description") or "")).strip())[:55]
        _ab_per  = (_ab.get("period") or "").strip()
        _ab_amt  = _parse_numeric(_ab.get("amount_stated"))
        if _ab_desc and _ab_per and _ab_amt is not None:
            _ab_idx.setdefault(_ab_desc, {})[_ab_per] = _ab_amt

    if _ab_idx or addbacks:
        _ab_hdr_cols = " | ".join(_cp)
        _ab_sep_cols = "|".join(["---"] * _n)
        ab_lines = [
            f"| Line Item | {_ab_hdr_cols} |",
            f"|---|{_ab_sep_cols}|",
        ]
        # Reported Revenue row
        ab_lines.append(_pl_row("Reported Revenue ($K)", [_rev_lookup(p) for p in _cp]))
        # Reported EBITDA + margin
        _ab_rep_vals = [_ebitda_lookup(p, ["reported"]) for p in _cp]
        ab_lines.append(_pl_row("Reported EBITDA ($K)", [v[0] for v in _ab_rep_vals], bold=True))
        ab_lines.append(_pl_row("EBITDA Margin %", [v[1] for v in _ab_rep_vals]))
        # Each addback item — amount in its period column, "—" elsewhere
        for _ab_desc, _ab_per_amts in _ab_idx.items():
            _ab_row_vals = []
            for p in _cp:
                _v = _ab_per_amts.get(p)
                _ab_row_vals.append(_fmt_dollars(_v) if _v is not None else "—")
            ab_lines.append(_pl_row(f"↳ {_ab_desc}", _ab_row_vals))
        # Adjusted EBITDA + margin
        _ab_adj_vals = [_ebitda_lookup(p, _adj_versions) for p in _cp]
        ab_lines.append(_pl_row("EBITDA Adjusted ($K)", [v[0] for v in _ab_adj_vals], bold=True))
        ab_lines.append(_pl_row("Adj. EBITDA Margin %", [v[1] for v in _ab_adj_vals]))
        # PF Adjusted EBITDA (only if data exists)
        _ab_pf_vals = [_ebitda_lookup(p, ["pf_adjusted"]) for p in _cp]
        if any(v[0] != "—" for v in _ab_pf_vals):
            ab_lines.append(_pl_row("PF Adjusted EBITDA ($K)", [v[0] for v in _ab_pf_vals], bold=True))
            ab_lines.append(_pl_row("PF Adj. EBITDA Margin %", [v[1] for v in _ab_pf_vals]))
    else:
        ab_lines = []
    tbl_addbacks = "\n".join(ab_lines) if ab_lines else "_No addbacks extracted._"

    # ── Budget vs actual ───────────────────────────────────────────────────
    bva_lines = []
    if budget_vs_actual:
        bva_lines = [
            "| Period | Metric | Budget | Actual | Variance |",
            "|---|---|---|---|---|",
        ]
        for item in budget_vs_actual:
            budget_n = _parse_numeric(item.get("budget_stated"))
            actual_n = _parse_numeric(item.get("actual_stated"))
            if budget_n and actual_n:
                var_abs = round(actual_n - budget_n, 0)
                var_str = f"{'+' if var_abs >= 0 else ''}{int(var_abs)}"
            else:
                var_str = "—"
            bva_lines.append(
                f"| {item.get('period','')} | {item.get('metric','')} | "
                f"{item.get('budget_stated','')} | {item.get('actual_stated','')} | {var_str} |"
            )
    tbl_bva = "\n".join(bva_lines) if bva_lines else "_No budget vs. actual data found._"

    # ══════════════════════════════════════════════════════════════════════
    # LLM narrative call — 6 focused questions, not 12
    # ══════════════════════════════════════════════════════════════════════
    # Customer concentration summary for narrative context
    _cust_lines = []
    if rev_by_customer:
        _cust_lines.append("CUSTOMER CONCENTRATION (top customers):")
        for _c in rev_by_customer[:10]:
            _pct = f" ({_fmt_pct(_c.get('revenue_pct'))})" if _c.get("revenue_pct") else ""
            _cust_lines.append(
                f"  {_c.get('customer_name','?')}: {_fmt_dollars(_c.get('revenue_dollars'))}{_pct} [{_c.get('period','')}]"
            )
    _cust_block = "\n".join(_cust_lines) if _cust_lines else "CUSTOMER CONCENTRATION: not available."

    _pl_context = f"""P&L SUMMARY (periods as columns):
{tbl_pl}

{_cust_block}

ADDBACK BRIDGE:
{tbl_addbacks}

BUDGET VS. ACTUAL:
{tbl_bva}

WORKING CAPITAL: DSO={working_capital.get('dso_days') or 'n/a'}  DPO={working_capital.get('dpo_days') or 'n/a'}  AR_note={working_capital.get('ar_aging_note') or 'n/a'}

DEVIATION FLAGS:
{chr(10).join(_deviation_flags) if _deviation_flags else 'None detected.'}

DATA ROOM GAPS (summarized — do not list in narrative):
{chr(10).join('- ' + g for g in data_room_gaps) if data_room_gaps else 'None.'}
"""

    _ASSESS_SYS = """\
You are a senior PE investment analyst writing a concise financial summary for an
internal diligence memo. Synthesize the P&L data provided and answer 6 questions.

Rules:
1. Write only what the data supports. Do not invent facts.
2. If a section cannot be assessed due to missing data, say so in ONE sentence.
3. Use concrete numbers. PE language only: "compressed", "addback-inflated",
   "operating leverage not visible", "top-line absent", etc.
4. Return pure markdown only — no preamble, no code fences.
5. Structure with exactly these 6 H3 headers:
   ### 1. Revenue Growth Quality
   ### 2. Margin Profile
   ### 3. EBITDA Reliability (Reported vs. Adjusted)
   ### 4. Cost Structure and Operating Leverage
   ### 5. Working Capital and Cash Conversion
   ### 6. Forecast Achievability
6. Each section: MAX 2 bullet points (≤30 words each) + one **Analyst take:** sentence.
   Do NOT repeat data already shown in the P&L table — reference it, don't restate it.
   Be ruthlessly concise.
"""

    _ASSESS_USER = f"""\
Use the financial data below to answer all 6 assessment questions. Markdown only.

COMPANY: {company_name}
INDUSTRY OVERLAY: {overlay}
EXECUTIVE SUMMARY: {exec_summary}

{_pl_context}
"""

    import mlflow.deployments
    _client = mlflow.deployments.get_deploy_client("databricks")
    os.environ.setdefault("DATABRICKS_HTTP_TIMEOUT", "600")
    _response = _client.predict(
        endpoint=llm_endpoint,
        inputs={
            "messages": [
                {"role": "system", "content": _ASSESS_SYS},
                {"role": "user",   "content": _ASSESS_USER},
            ],
            "max_tokens": 2000,
            "temperature": 0.1,
        },
    )
    narrative = _response["choices"][0]["message"]["content"].strip()

    # ══════════════════════════════════════════════════════════════════════
    # Assemble final markdown — P&L first, narrative below
    # ══════════════════════════════════════════════════════════════════════
    flag_severity_order = {"Red": 0, "Yellow": 1, "Green": 2}
    flags_sorted = sorted(flags, key=lambda f: flag_severity_order.get(f.get("severity", ""), 3))

    md_parts: list[str] = []
    md_parts.append(f"# {company_name} — Financial Summary")
    md_parts.append(f"**Generated:** {generated_at}  |  **Overlay:** {overlay}\n")

    if exec_summary:
        md_parts.append(f"> {exec_summary}\n")

    # Investment flags (if any)
    if flags_sorted:
        md_parts.append("---\n")
        md_parts.append("## Investment Flags\n")
        for f in flags_sorted:
            emoji = {"Red": "🔴", "Yellow": "🟡", "Green": "🟢"}.get(f.get("severity", ""), "⚪")
            md_parts.append(
                f"- {emoji} **{f.get('metric','')}**: {f.get('value','')} "
                f"(threshold: {f.get('threshold','')}) — {f.get('note','')}"
            )
        md_parts.append("")

    # Deviation alerts
    if _deviation_flags:
        md_parts.append("---\n")
        md_parts.append("## ⚠️ EBITDA Reported vs. Adjusted — Material Gaps\n")
        for d in _deviation_flags:
            md_parts.append(d)
        md_parts.append("")

    # Compact P&L grid
    md_parts.append("---\n")
    md_parts.append("## P&L Summary\n")
    md_parts.append("> All figures in $K unless stated. Actuals + TTM shown; projected periods excluded.\n")
    md_parts.append(tbl_pl)
    md_parts.append("")

    # Cost & EBITDA Detail (right after P&L, same accounting format)
    md_parts.append("### Cost & EBITDA Detail\n")
    md_parts.append(
        "> OpEx: top 4 categories by total spend; remainder summed into Other OpEx. "
        "Net Addbacks = Adjusted EBITDA − Reported EBITDA (per period); "
        "see Addback Bridge below for itemized detail. All figures in $K.\n"
    )
    md_parts.append(tbl_cost_ebitda)
    md_parts.append("")

    # Customer concentration (own table, not embedded in P&L rows)
    if _tbl_customers:
        md_parts.append("### Customer Concentration\n")
        md_parts.append(_tbl_customers)
        md_parts.append("")

    # Addback bridge
    if addbacks:
        md_parts.append(f"### Addback Bridge  _(Total addbacks as % of Reported EBITDA: {f'{addback_pct}%' if addback_pct is not None else 'n/a'})_\n")
        md_parts.append(tbl_addbacks)
        md_parts.append("")

    # Budget vs actual
    if budget_vs_actual:
        md_parts.append("### Budget vs. Actual\n")
        md_parts.append(tbl_bva)
        md_parts.append("")

    # Working capital
    if working_capital.get("dso_days") or working_capital.get("ar_aging_note"):
        md_parts.append("### Working Capital\n")
        wc_items = []
        if working_capital.get("dso_days"):
            wc_items.append(f"DSO: {working_capital['dso_days']} days")
        if working_capital.get("dpo_days"):
            wc_items.append(f"DPO: {working_capital['dpo_days']} days")
        if working_capital.get("ar_aging_note"):
            wc_items.append(f"AR: {working_capital['ar_aging_note']}")
        md_parts.append("  |  ".join(wc_items))
        md_parts.append("")

    # Discrepancies
    if discrepancies:
        md_parts.append("### Discrepancies Found\n")
        for d in discrepancies:
            md_parts.append(
                f"- **{d.get('metric','')}**: {' vs '.join(d.get('conflicting_values') or [])} — {d.get('note','')}"
            )
        md_parts.append("")

    # Narrative
    md_parts.append("---\n")
    md_parts.append("## Financial Story Assessment\n")
    md_parts.append(narrative)
    md_parts.append("")

    # Data room gaps
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
    revenue_trend    = json.loads(result.get("revenue_trend_json")        or "[]")
    gross_margin     = json.loads(result.get("gross_margin_json")         or "[]")
    ebitda           = json.loads(result.get("ebitda_json")               or "[]")
    rev_by_segment   = json.loads(result.get("revenue_by_segment_json")  or "[]")
    rev_by_customer  = json.loads(result.get("revenue_by_customer_json") or "[]")
    cost_structure   = json.loads(result.get("cost_structure_json")       or "{}")
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
        "revenue_by_customer": rev_by_customer,
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
    revenue_by_customer_json    STRING,
    cost_structure_json         STRING,
    working_capital_json        STRING,
    budget_vs_actual_json       STRING,
    addback_schedule_json       STRING,
    opex_breakdown_json         STRING,
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

    company_name         = get_param("sp_company_name")
    catalog              = get_param("catalog",              default="uc13")
    llm_endpoint         = get_param("llm_endpoint",         default="databricks-claude-sonnet-4-6")
    _widget_ep           = get_param("extraction_endpoint",  default="databricks-claude-sonnet-4-6") or "databricks-claude-sonnet-4-6"
    # FTA schema generates 10-14K output tokens (78+ EBITDA records, 17+ addbacks, segments,
    # OPEX). Haiku 4.5 is hard-capped at 8,192 on this workspace — always truncates before
    # reaching gross_margin / revenue_by_segment / opex_breakdown. Force Sonnet regardless
    # of widget setting; any non-Haiku selection (Opus, a custom endpoint) is respected.
    if "haiku" in _widget_ep.lower():
        extraction_endpoint = "databricks-claude-sonnet-4-6"
        print(f"  [override] extraction_endpoint '{_widget_ep}' → Sonnet (Haiku cap=8192 tokens; FTA schema needs 10K+)")
    else:
        extraction_endpoint = _widget_ep
    retrieval_mode       = get_param("retrieval_mode", default="semantic")

    from pyspark.sql import SparkSession
    spark = SparkSession.getActiveSession()
    if spark is None:
        raise RuntimeError("No active Spark session.")

    print(f"\n=== Financial Trends Agent ({company_name}) ===")
    print(f"  extraction: {extraction_endpoint or llm_endpoint}  narrative: {llm_endpoint}")
    print(f"  retrieval_mode: {retrieval_mode}")

    agent = FinancialTrendsAgent()
    result = agent.run(
        company_name=company_name,
        spark=spark,
        llm_endpoint=llm_endpoint,
        extraction_endpoint=extraction_endpoint,
        retrieval_mode=retrieval_mode,
    )

    # ── Save to Delta ─────────────────────────────────────────────────
    table = f"{catalog}.analysis.financial_trends"
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.analysis")

    # Schema migration guard: drop and recreate when expected columns are missing.
    _EXPECTED_COLS = {
        "company_name", "executive_summary", "industry_overlay_used",
        "revenue_trend_json", "gross_margin_json", "ebitda_json",
        "revenue_by_segment_json", "revenue_by_customer_json", "cost_structure_json", "working_capital_json",
        "budget_vs_actual_json", "addback_schedule_json", "opex_breakdown_json",
        "addback_pct_of_ebitda", "flags", "discrepancies", "data_room_gaps",
        "citations", "reasoning_trace", "created_at",
    }
    try:
        _live_cols = {f.name for f in spark.table(table).schema.fields}
        if not _EXPECTED_COLS.issubset(_live_cols):
            _missing = _EXPECTED_COLS - _live_cols
            print(f"  [schema_migration] {table}: dropping stale table. Missing: {sorted(_missing)}")
            spark.sql(f"DROP TABLE IF EXISTS {table}")
    except Exception:
        pass

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
        StructField("revenue_by_customer_json", StringType(),  True),
        StructField("cost_structure_json",      StringType(),  True),
        StructField("working_capital_json",     StringType(),  True),
        StructField("budget_vs_actual_json",    StringType(),  True),
        StructField("addback_schedule_json",    StringType(),  True),
        StructField("opex_breakdown_json",      StringType(),  True),
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
        "revenue_by_customer_json": result.get("revenue_by_customer_json"),
        "cost_structure_json":      result.get("cost_structure_json"),
        "working_capital_json":     result.get("working_capital_json"),
        "budget_vs_actual_json":    result.get("budget_vs_actual_json"),
        "addback_schedule_json":    result.get("addback_schedule_json"),
        "opex_breakdown_json":          result.get("opex_breakdown_json"),
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
