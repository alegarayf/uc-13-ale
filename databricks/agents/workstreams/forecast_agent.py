"""
forecast_agent.py — Phase 3: Forecast Workstream Agent (Spec §9, Guideline 7).

Evaluates the credibility of management's forecast / financial model against
trailing performance and contracted evidence, and produces downside-sensitivity
inputs for the deal team's LBO model.

Primary source: financial model / projection file (Priority Tier). If no model is
present, falls back to CIM forward projections + management presentation. Phase 1
posture: treat stated assumptions as source of truth; NOTE (do not verdict) where
assumptions are unsupported by data present in the VDR.

Phase 3 outputs:
  - Table uc13.analysis.forecast

Dependencies (all optional — the agent degrades gracefully and records a data-room
gap if a dependency has not run):
  - uc13.ingestion.embeddings                        (FORECAST-tagged chunks)
  - uc13.classification.doc_relevance
  - uc13.classification.company_profile
  - uc13.analysis.financial_trends   (trailing revenue / margin / EBITDA actuals)   REQUIRED-ish
  - uc13.analysis.quality_of_earnings (Tier 1+2 addbacks → addback-erosion case)     optional
  - uc13.analysis.customer_quality    (top customers → top-customer-loss case)       optional
  - agents.shared.retrieval.semantic_search
  - agents.shared.agent_base.WorkstreamAgent

The credibility rubric (Supported / Plausible / Stretch) is applied DETERMINISTICALLY
in Python from the trailing actuals — the LLM only extracts the stated assumptions and
whether a named driver / contracted backing exists. This mirrors the deterministic
flag logic in the other Phase 3 agents (values are never recomputed by the LLM).
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Secrets / params helpers — copied verbatim from quality_of_earnings_agent.py
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


# ---------------------------------------------------------------------------
# Repo root resolver — copied verbatim from quality_of_earnings_agent.py
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
# Numeric helpers — copied verbatim from quality_of_earnings_agent.py
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


def _fmt_dollars(val) -> str:
    if val is None:
        return "—"
    if isinstance(val, (int, float)):
        return f"${float(val):,.0f}"
    n = _parse_numeric(str(val))
    if n is None:
        return str(val) if val else "—"
    return f"${n:,.0f}"


def _fmt_pct(val) -> str:
    if val is None:
        return "—"
    if isinstance(val, (int, float)):
        return f"{float(val):.1f}%"
    n = _parse_numeric(str(val))
    return f"{n:.1f}%" if n is not None else str(val)


def _fmt_downside_md(downside: dict) -> str:
    """Format a downside sensitivity dict as readable markdown (no raw JSON)."""
    if not downside:
        return "_No downside sensitivity data extracted._"

    parts = []

    # Top customer loss
    top_loss = downside.get("topcustomerloss") or []
    if top_loss:
        rows = ["| Customer | Revenue % | Revenue Impact | GM % | EBITDA Impact | Note |",
                "|---|---|---|---|---|---|"]
        for c in top_loss:
            rows.append(
                f"| {c.get('customer') or '—'} "
                f"| {_fmt_pct(c.get('revenue_pct'))} "
                f"| {_fmt_dollars(c.get('revenueimpactdollars'))} "
                f"| {_fmt_pct(c.get('gm_pct'))} "
                f"| {_fmt_dollars(c.get('approxebitdaimpact_dollars'))} "
                f"| {c.get('note') or '—'} |"
            )
        parts.append("**Top Customer Loss Scenarios**\n\n" + "\n".join(rows))

    # Growth rate haircut
    haircut = downside.get("growthratehaircut") or {}
    if haircut:
        h_lines = ["**Growth Rate Haircut**", ""]
        if haircut.get("trailingcagrpct") is not None:
            h_lines.append(f"- Trailing CAGR: {_fmt_pct(haircut.get('trailingcagrpct'))}")
        if haircut.get("nforecastperiods") is not None:
            h_lines.append(f"- Forecast periods: {haircut.get('nforecastperiods')}")
        periods = haircut.get("haircutrevenueby_period") or []
        if periods:
            period_str = "  ·  ".join(_fmt_dollars(v) for v in periods)
            h_lines.append(f"- Revenue by period (haircut): {period_str}")
        parts.append("\n".join(h_lines))

    # Margin compression
    margin = downside.get("margin_compression") or {}
    if margin:
        m_lines = ["**Margin Compression**", ""]
        if margin.get("trailingavggrossmarginpct") is not None:
            m_lines.append(f"- Trailing avg gross margin: {_fmt_pct(margin.get('trailingavggrossmarginpct'))}")
        if margin.get("note"):
            m_lines.append(f"- {margin['note']}")
        parts.append("\n".join(m_lines))

    # Addback erosion
    addback = downside.get("addback_erosion") or {}
    if addback.get("note"):
        parts.append(f"**Addback Erosion**\n\n- {addback['note']}")

    # Pipeline miss
    pipeline = downside.get("pipeline_miss") or {}
    if pipeline:
        p_lines = ["**Pipeline Miss**", ""]
        field_labels = {
            "forecastnewcustomer_revenue": "Forecast new-customer revenue",
            "statedpipelinevalue":         "Stated pipeline value",
            "statedconversionrate":        "Stated conversion rate",
            "pipelinecoveragex":           "Pipeline coverage (x)",
        }
        for key, label in field_labels.items():
            val = pipeline.get(key)
            if val is not None:
                p_lines.append(f"- {label}: {val}")
        if pipeline.get("note"):
            p_lines.append(f"- Note: {pipeline['note']}")
        parts.append("\n".join(p_lines))

    return "\n\n".join(parts) if parts else "_No downside scenarios modeled._"


def _rating_emoji(rating: str) -> str:
    """Traffic-light emoji for a credibility rating string."""
    r = (rating or "").strip().lower()
    if r == "supported":
        return "🟢"
    if r == "plausible":
        return "🟡"
    if r == "stretch":
        return "🔴"
    return "⚪"


# Assumption types the agent evaluates (spec §9.2). The LLM maps each stated
# assumption to one of these; Python applies the rubric per type.
_ASSUMPTION_TYPES = [
    "revenue_growth_rate",
    "gross_margin_improvement",
    "new_customer_revenue",
    "hiring_plan",
    "backlog_pipeline_coverage",
    "capex_wc_assumptions",
]


# ---------------------------------------------------------------------------
# LLM prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a senior PE investment analyst extracting the assumptions embedded in a
company's forecast / financial model for diligence. Rules:
1. Extract ONLY what is explicitly stated in the provided context (the forecast/model,
   CIM forward projections, or management presentation).
2. Do NOT infer, compute, assume, or hallucinate any value. If a value is absent,
   return null for that field.
3. Every extracted assumption must have a citation: document name, location
   (page/tab/cell or section title), and a quote of ≤30 words.
4. Return ONLY valid JSON with no preamble and no markdown fences.
5. For each assumption, determine two qualitative signals that the deal team needs:
   - named_driver: the specific driver management cites for the assumption (e.g.
     "new product line", "contracted price increase", "signed pipeline"), or null
     if the forecast states a number with no named driver.
   - backing_evidence: one of "contracted" (backed by contracted revenue / signed
     pipeline / documented price change present in the VDR), "named_only" (a driver
     is named but not evidenced by a document in the VDR), or "none" (a number with
     no driver and no evidence).
   Do NOT assign the Supported/Plausible/Stretch rating yourself — that is computed
   downstream from trailing actuals. Only report the stated value and these signals.
6. Extract the forward revenue build (per forecast period) so it can be compared to
   trailing actuals: period label and forecast revenue as stated.
7. new_customer_revenue: report the % (or $) of forecast revenue attributed to NEW
   customers, and whether a pipeline/backlog file is referenced as support.
8. hiring_plan: report implied headcount growth and any stated revenue-per-FTE or
   revenue growth it is tied to.
9. capex_wc_assumptions: report any stated improvement to DSO, DPO, or capex ratio,
   and whether it is presented as assumed or demonstrated.\
"""

_USER_PROMPT_TEMPLATE = """\
COMPANY PROFILE (from Phase 2 output):
{company_profile_json}

TRAILING ACTUALS (passed from Financial Trends Agent — treat as source of truth for
historical comparison; do NOT restate these, only reference them):
{trailing_context}

RETRIEVED FORECAST / MODEL CONTEXT:
{combined_chunk_text}

Extract the forecast assumptions and return this exact JSON structure:
{{
  "forecast_source_present": "<true | false>",
  "forecast_source": "<filename of the model/projection file, or null>",
  "forecast_assumptions": [
    {{
      "assumption_type": "<revenue_growth_rate | gross_margin_improvement | new_customer_revenue | hiring_plan | backlog_pipeline_coverage | capex_wc_assumptions>",
      "stated_value": "<the assumption value exactly as stated, e.g. '22% YoY', '800bps over 3 years', '$4.2m from new customers', '+35 FTE'>",
      "stated_value_numeric": "<the primary number as a bare figure if extractable, else null>",
      "named_driver": "<the driver management cites, or null>",
      "backing_evidence": "<contracted | named_only | none>",
      "description": "<one sentence describing the assumption as management frames it>",
      "source_doc": "<filename>",
      "source_location": "<page/tab/cell or section>",
      "raw_text": "<≤30 word quote>"
    }}
  ],
  "revenue_build": [
    {{
      "period": "<forecast period label, e.g. FY2025E>",
      "forecast_revenue": "<$ as stated>",
      "source_doc": "<filename>",
      "source_location": "<page/tab/cell>"
    }}
  ],
  "new_customer_forecast": {{
    "forecast_new_customer_revenue": "<$ or % of forecast revenue from new customers, or null>",
    "pipeline_file_referenced": "<true | false>",
    "stated_pipeline_value": "<$ pipeline/backlog as stated, or null>",
    "stated_conversion_rate": "<% historical conversion rate if stated, or null>"
  }},
  "citations": [
    {{
      "field": "<field_name>",
      "document": "<exact filename>",
      "location": "<page, section, tab, or cell>",
      "quote": "<≤30 word quote>",
      "confidence": "<high | medium | low>"
    }}
  ],
  "executive_summary": "<2–3 sentence factual description of what the forecast assumes (headline growth, margin trajectory, new-customer dependence). Describe what the model states — do not opine on deal outcome.>",
  "extraction_notes": "<no model found, assumptions implicit, data quality issues>"
}}\
"""


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

from agents.shared.agent_base import WorkstreamAgent


class ForecastAgent(WorkstreamAgent):
    """Phase 3 Forecast workstream agent (spec §9)."""

    agent_name = "forecast"

    def __init__(self):
        super().__init__()
        self._catalog = "uc13"

    def _log_no_flag(self, metric: str, value_str: str, threshold: str, note: str = ""):
        step = len(self._trace) + 1
        self._trace.append({
            "step":       step,
            "tool":       "threshold_evaluation",
            "input":      f"metric={metric}, value={value_str}, threshold={threshold}",
            "output":     f"No flag triggered — {note}" if note else "No flag triggered",
            "confidence": "high",
            "sources":    [],
        })
        print(f"  Step {step} [threshold_evaluation]: {metric}={value_str} vs {threshold} → no flag")

    # -----------------------------------------------------------------------
    # Passthrough loaders (read prior Phase 3 agents from Delta — never chunks)
    # -----------------------------------------------------------------------

    def _load_financial_trends(self, company_name: str, spark) -> dict:
        """Load trailing revenue / margin / EBITDA / working-capital actuals.

        Returns a dict with keys revenue_trend, gross_margin, ebitda,
        working_capital. Records a gap and returns empties if FTA has not run —
        the credibility rubric then degrades to "cannot compare to trailing".
        """
        try:
            rows = spark.sql(
                "SELECT revenue_trend_json, gross_margin_json, ebitda_json, working_capital_json "
                f"FROM {self._catalog}.analysis.financial_trends "
                "WHERE company_name = :company_name "
                "ORDER BY created_at DESC LIMIT 1",
                args={"company_name": company_name},
            ).collect()
            if rows:
                r = rows[0]
                return {
                    "revenue_trend":   json.loads(r["revenue_trend_json"]  or "[]"),
                    "gross_margin":    json.loads(r["gross_margin_json"]   or "[]"),
                    "ebitda":          json.loads(r["ebitda_json"]         or "[]"),
                    "working_capital": json.loads(r["working_capital_json"] or "{}"),
                }
        except Exception as e:
            self._add_gap(f"Could not load financial_trends table: {e}")
            return {"revenue_trend": [], "gross_margin": [], "ebitda": [], "working_capital": {}}
        self._add_gap(
            "financial_trends output not found — Financial Trends Agent has not run. "
            "Forecast credibility cannot be benchmarked against trailing actuals; all "
            "assumptions default to 'cannot assess' pending FTA."
        )
        return {"revenue_trend": [], "gross_margin": [], "ebitda": [], "working_capital": {}}

    def _load_qofe_addbacks(self, company_name: str, spark) -> dict:
        """Load Tier 1+2 adjusted EBITDA scenario for the addback-erosion case.

        Returns {"tier12_ebitda": float|None, "reported_ebitda": float|None,
                 "scenarios": dict}. Empty with a gap note if QofE has not run.
        """
        try:
            rows = spark.sql(
                f"SELECT ebitda_scenarios_json FROM {self._catalog}.analysis.quality_of_earnings "
                "WHERE company_name = :company_name "
                "ORDER BY created_at DESC LIMIT 1",
                args={"company_name": company_name},
            ).collect()
            if rows and rows[0]["ebitda_scenarios_json"]:
                scenarios = json.loads(rows[0]["ebitda_scenarios_json"])
                return {
                    "scenarios": scenarios,
                    "tier12_ebitda": _parse_numeric(
                        scenarios.get("tier_1_and_2_only")
                        or scenarios.get("tier_1_2_only")
                        or scenarios.get("adjusted_tier_1_and_2")
                    ),
                    "reported_ebitda": _parse_numeric(
                        scenarios.get("reported") or scenarios.get("reported_ebitda")
                    ),
                }
        except Exception as e:
            self._add_gap(f"Could not load quality_of_earnings table: {e}")
            return {"scenarios": {}, "tier12_ebitda": None, "reported_ebitda": None}
        self._add_gap(
            "quality_of_earnings output not found — QofE Agent has not run. "
            "Addback-erosion downside case will be omitted."
        )
        return {"scenarios": {}, "tier12_ebitda": None, "reported_ebitda": None}

    def _load_top_customers(self, company_name: str, spark) -> list:
        """Load top customers for the top-customer-loss sensitivity case.

        Empty with a gap note if CQA has not run.
        """
        try:
            rows = spark.sql(
                f"SELECT top_customers_json FROM {self._catalog}.analysis.customer_quality "
                "WHERE company_name = :company_name "
                "ORDER BY created_at DESC LIMIT 1",
                args={"company_name": company_name},
            ).collect()
            if rows and rows[0]["top_customers_json"]:
                return json.loads(rows[0]["top_customers_json"])
        except Exception as e:
            self._add_gap(f"Could not load customer_quality table: {e}")
            return []
        self._add_gap(
            "customer_quality output not found — Customer Quality Agent has not run. "
            "Top-customer-loss downside case will be omitted."
        )
        return []

    # -----------------------------------------------------------------------
    # Retrieval tool methods
    # -----------------------------------------------------------------------

    def _tool_retrieve_financial_model(self, spark):
        from agents.shared.retrieval import semantic_search
        chunks = semantic_search(
            query="financial model projection forecast budget five year plan revenue projection assumptions",
            spark=spark,
            company_name=self._company_name,
            top_k=12,
            workstream_filter=["FORECAST", "FINANCIAL"],
            file_name_filter=["Model", "Forecast", "Projection", "Budget", "Plan", "5yr", "Five Year"],
            source_type_priority=True,
            min_chunk_length=120,
        ).chunks
        source_docs = list({c.file_name for c in chunks})
        return self._tool_call(
            tool_name="retrieve_financial_model",
            input_summary="query: financial model projection forecast budget five year plan revenue assumptions",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence="high" if chunks else "low",
            source_docs=source_docs,
        )

    def _tool_retrieve_forward_guidance(self, spark):
        from agents.shared.retrieval import semantic_search
        chunks = semantic_search(
            query="forward guidance growth strategy margin expansion new product line management projections outlook",
            spark=spark,
            company_name=self._company_name,
            top_k=8,
            workstream_filter=["FORECAST", "BUSINESS_MODEL"],
            min_chunk_length=150,
        ).chunks
        source_docs = list({c.file_name for c in chunks})
        return self._tool_call(
            tool_name="retrieve_forward_guidance",
            input_summary="query: forward guidance growth strategy margin expansion new product line outlook",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence="high" if chunks else "low",
            source_docs=source_docs,
        )

    def _tool_retrieve_pipeline_backlog(self, spark):
        from agents.shared.retrieval import semantic_search
        chunks = semantic_search(
            query="sales pipeline backlog bookings contracted revenue win rate conversion rate new logos coverage",
            spark=spark,
            company_name=self._company_name,
            top_k=8,
            workstream_filter=["FORECAST", "CUSTOMER", "KPI_OPS"],
            min_chunk_length=120,
        ).chunks
        source_docs = list({c.file_name for c in chunks})
        return self._tool_call(
            tool_name="retrieve_pipeline_backlog",
            input_summary="query: sales pipeline backlog bookings contracted revenue win rate conversion coverage",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence="high" if chunks else "low",
            source_docs=source_docs,
        )

    def _tool_load_company_profile(self, company_name: str, spark):
        try:
            rows = spark.sql(
                f"SELECT * FROM {self._catalog}.classification.company_profile "
                "WHERE company_name = :company_name "
                "ORDER BY created_at DESC LIMIT 1",
                args={"company_name": company_name},
            ).collect()
            if not rows:
                self._add_gap("company_profile not found — run company_profiler.py first")
                return self._tool_call(
                    tool_name="load_company_profile",
                    input_summary=f"company_name={company_name}",
                    data=None,
                    output_summary="No company profile found",
                    confidence="low",
                    source_docs=[],
                )
            profile_dict = rows[0].asDict()
            return self._tool_call(
                tool_name="load_company_profile",
                input_summary=f"company_name={company_name}",
                data=profile_dict,
                output_summary="Company profile loaded",
                confidence="high",
                source_docs=[f"{self._catalog}.classification.company_profile"],
            )
        except Exception as exc:
            self._add_gap(f"company_profile query failed: {exc} — run company_profiler.py first")
            return self._tool_call(
                tool_name="load_company_profile",
                input_summary=f"company_name={company_name}",
                data=None,
                output_summary=f"Query error: {exc}",
                confidence="low",
                source_docs=[],
            )

    # -----------------------------------------------------------------------
    # Trailing-actuals helpers (deterministic — no LLM)
    # -----------------------------------------------------------------------

    @staticmethod
    def _period_rank(period: str) -> int:
        """Extract a 4-digit year for chronological sorting; 0 if none found."""
        m = re.search(r"(19|20)\d{2}", str(period or ""))
        return int(m.group(0)) if m else 0

    def _trailing_revenue_series(self, financials: dict) -> list:
        """Sorted (year, revenue) list from FTA revenue_trend, actuals only."""
        series = []
        for r in financials.get("revenue_trend") or []:
            rev = _parse_numeric(r.get("revenue_stated"))
            yr = self._period_rank(r.get("period"))
            if rev is not None and yr:
                series.append((yr, rev))
        series.sort(key=lambda t: t[0])
        return series

    def _trailing_cagr_pct(self, financials: dict) -> Optional[float]:
        """Trailing revenue CAGR % over the available actual periods (≥2)."""
        series = self._trailing_revenue_series(financials)
        if len(series) < 2:
            return None
        first, last = series[0][1], series[-1][1]
        n = series[-1][0] - series[0][0]
        if first <= 0 or n <= 0:
            return None
        return ((last / first) ** (1.0 / n) - 1.0) * 100.0

    def _trailing_avg_gross_margin_pct(self, financials: dict) -> Optional[float]:
        vals = []
        for g in financials.get("gross_margin") or []:
            v = _parse_numeric(g.get("gm_pct_stated") or g.get("gm_pct"))
            if v is not None:
                vals.append(v)
        return sum(vals) / len(vals) if vals else None

    # -----------------------------------------------------------------------
    # Credibility rubric (spec §9.1) — DETERMINISTIC
    # -----------------------------------------------------------------------

    def _rate_assumption(self, assumption: dict, trailing: dict) -> dict:
        """Apply the Supported / Plausible / Stretch rubric deterministically.

        Logic (spec §9.1):
          - Supported: consistent with trailing performance OR backed by contracted
            revenue / signed pipeline / documented price change.
          - Plausible: a step-change from trailing but a named driver exists.
          - Stretch: materially outside the historical envelope with no contracted
            backing, OR contradicted by recent trends.

        The numeric comparison is done here; the qualitative signals
        (named_driver, backing_evidence) come from the LLM extraction.
        """
        atype = assumption.get("assumption_type")
        backing = (assumption.get("backing_evidence") or "none").lower()
        has_driver = bool(assumption.get("named_driver"))
        stated_num = _parse_numeric(assumption.get("stated_value_numeric")
                                    or assumption.get("stated_value"))

        # Contracted backing short-circuits to Supported regardless of magnitude.
        if backing == "contracted":
            return {"credibility_rating": "Supported",
                    "rationale": "Backed by contracted revenue / signed pipeline / documented "
                                 "price change present in the VDR.",
                    "trailing_reference": None}

        trailing_ref = None
        delta_pp = None

        if atype == "revenue_growth_rate":
            cagr = self._trailing_cagr_pct(trailing)
            trailing_ref = f"trailing revenue CAGR {cagr:.1f}%" if cagr is not None else None
            if stated_num is not None and cagr is not None:
                delta_pp = stated_num - cagr
        elif atype == "gross_margin_improvement":
            avg_gm = self._trailing_avg_gross_margin_pct(trailing)
            trailing_ref = f"trailing avg gross margin {avg_gm:.1f}%" if avg_gm is not None else None
            # stated_num here is typically the expansion (e.g. 800bps) — treat as delta.
            if stated_num is not None:
                delta_pp = stated_num if stated_num < 100 else None

        # No trailing basis to compare against.
        if delta_pp is None:
            if has_driver:
                return {"credibility_rating": "Plausible",
                        "rationale": "A named driver exists but the assumption could not be "
                                     "benchmarked against trailing actuals (missing FTA data or "
                                     "non-numeric assumption). Requires management substantiation.",
                        "trailing_reference": trailing_ref}
            return {"credibility_rating": "Stretch",
                    "rationale": "No named driver and no trailing basis to corroborate the "
                                 "assumption. Presented as a number without support.",
                    "trailing_reference": trailing_ref}

        # Numeric comparison available. Thresholds are neutral heuristics, not verdicts.
        if delta_pp <= 3.0:
            rating = "Supported"
            rationale = (f"In line with trailing performance ({trailing_ref}); "
                         f"implied step-up of {delta_pp:+.1f}pp is within the historical envelope.")
        elif delta_pp <= 10.0:
            if has_driver:
                rating = "Plausible"
                rationale = (f"A step-change of {delta_pp:+.1f}pp vs {trailing_ref}, but a named "
                             f"driver ('{assumption.get('named_driver')}') is cited. Not yet in the "
                             f"actuals — validate with management.")
            else:
                rating = "Stretch"
                rationale = (f"A step-change of {delta_pp:+.1f}pp vs {trailing_ref} with no named "
                             f"driver.")
        else:
            rating = "Stretch"
            rationale = (f"Requires sustained performance {delta_pp:+.1f}pp outside the historical "
                         f"envelope ({trailing_ref})"
                         + (f"; driver cited ('{assumption.get('named_driver')}') but magnitude is "
                            f"materially beyond trailing." if has_driver else " with no named driver."))

        return {"credibility_rating": rating, "rationale": rationale,
                "trailing_reference": trailing_ref}

    def _build_revenue_build_comparison(self, revenue_build: list, trailing: dict) -> list:
        """Forecast revenue vs trailing actuals: implied YoY, CAGR, delta, flag."""
        cagr = self._trailing_cagr_pct(trailing)
        series = self._trailing_revenue_series(trailing)
        last_actual = series[-1][1] if series else None
        last_actual_yr = series[-1][0] if series else None

        rows = []
        prev_rev = last_actual
        prev_yr = last_actual_yr
        for rec in sorted(revenue_build, key=lambda r: self._period_rank(r.get("period"))):
            fc_rev = _parse_numeric(rec.get("forecast_revenue"))
            yr = self._period_rank(rec.get("period"))
            implied_yoy = None
            if fc_rev is not None and prev_rev not in (None, 0) and prev_yr and yr and yr > prev_yr:
                implied_yoy = ((fc_rev / prev_rev) ** (1.0 / (yr - prev_yr)) - 1.0) * 100.0
            delta_pp = (implied_yoy - cagr) if (implied_yoy is not None and cagr is not None) else None
            flag = None
            if delta_pp is not None:
                flag = "Green" if delta_pp <= 3 else ("Yellow" if delta_pp <= 10 else "Red")
            rows.append({
                "period": rec.get("period"),
                "forecast_revenue": rec.get("forecast_revenue"),
                "implied_yoy_growth_pct": round(implied_yoy, 1) if implied_yoy is not None else None,
                "trailing_cagr_pct": round(cagr, 1) if cagr is not None else None,
                "delta_pp": round(delta_pp, 1) if delta_pp is not None else None,
                "flag": flag,
                "source_doc": rec.get("source_doc"),
                "source_location": rec.get("source_location"),
            })
            if fc_rev is not None:
                prev_rev, prev_yr = fc_rev, yr
        return rows

    # -----------------------------------------------------------------------
    # Downside sensitivity inputs (spec §9.3) — DETERMINISTIC
    # -----------------------------------------------------------------------

    def _build_downside_sensitivities(self, extracted, trailing, qofe, top_customers) -> dict:
        sens = {}

        # 1. Top-customer loss case (top 3 individually).
        top_loss = []
        for c in sorted(top_customers,
                        key=lambda x: -(_parse_numeric(x.get("revenue_pct_yr1")) or 0))[:3]:
            rev_pct = c.get("revenue_pct_yr1")
            rev_dol = _parse_numeric(c.get("revenue_dollars"))
            gm_pct = _parse_numeric(c.get("gm_pct"))
            ebitda_impact = None
            if rev_dol is not None and gm_pct is not None:
                ebitda_impact = rev_dol * (gm_pct / 100.0)
            top_loss.append({
                "customer": c.get("customer_name", "Unknown"),
                "revenue_pct": rev_pct,
                "revenue_impact_dollars": rev_dol,
                "gm_pct": gm_pct,
                "approx_ebitda_impact_dollars": round(ebitda_impact) if ebitda_impact is not None else None,
                "note": "EBITDA impact approximated at the customer's gross margin; "
                        "confirm contribution margin with management." if ebitda_impact is not None
                        else "Per-customer revenue/GM not available — quantify with management.",
            })
        sens["top_customer_loss"] = top_loss

        # 2. Growth-rate haircut: revenue if growth tracks trailing CAGR instead of forecast.
        cagr = self._trailing_cagr_pct(trailing)
        series = self._trailing_revenue_series(trailing)
        last_actual = series[-1][1] if series else None
        rev_build = extracted.get("revenue_build") or []
        n_fc_periods = len([r for r in rev_build if _parse_numeric(r.get("forecast_revenue")) is not None])
        haircut = {"trailing_cagr_pct": round(cagr, 1) if cagr is not None else None,
                   "n_forecast_periods": n_fc_periods}
        if last_actual is not None and cagr is not None and n_fc_periods:
            haircut["haircut_revenue_by_period"] = [
                round(last_actual * ((1 + cagr / 100.0) ** (i + 1))) for i in range(n_fc_periods)
            ]
        else:
            haircut["note"] = "Insufficient trailing/forecast data to compute the haircut series."
        sens["growth_rate_haircut"] = haircut

        # 3. Margin compression: EBITDA at trailing avg gross margin vs projected.
        avg_gm = self._trailing_avg_gross_margin_pct(trailing)
        sens["margin_compression"] = {
            "trailing_avg_gross_margin_pct": round(avg_gm, 1) if avg_gm is not None else None,
            "note": "Apply trailing average gross margin to forecast revenue instead of the "
                    "projected expanded margin to size the downside.",
        }

        # 4. Addback erosion: EBITDA with only Tier 1 + Tier 2 addbacks (from QofE).
        if qofe.get("tier12_ebitda") is not None:
            sens["addback_erosion"] = {
                "tier_1_and_2_only_ebitda": qofe["tier12_ebitda"],
                "reported_ebitda": qofe.get("reported_ebitda"),
                "note": "Downside adjusted EBITDA recognizing only Tier 1 + Tier 2 addbacks "
                        "(source: Quality of Earnings Agent).",
            }
        else:
            sens["addback_erosion"] = {
                "note": "QofE Tier 1+2 scenario unavailable — run the Quality of Earnings Agent.",
            }

        # 5. Pipeline miss: new-customer revenue at 50% if pipeline coverage < 2x.
        ncf = extracted.get("new_customer_forecast") or {}
        fc_new = _parse_numeric(ncf.get("forecast_new_customer_revenue"))
        pipeline = _parse_numeric(ncf.get("stated_pipeline_value"))
        conv = _parse_numeric(ncf.get("stated_conversion_rate"))
        coverage = None
        if fc_new not in (None, 0) and pipeline is not None:
            expected = pipeline * (conv / 100.0) if conv is not None else pipeline
            coverage = expected / fc_new
        pipeline_miss = {
            "forecast_new_customer_revenue": ncf.get("forecast_new_customer_revenue"),
            "stated_pipeline_value": ncf.get("stated_pipeline_value"),
            "stated_conversion_rate": ncf.get("stated_conversion_rate"),
            "pipeline_coverage_x": round(coverage, 2) if coverage is not None else None,
        }
        if coverage is not None and coverage < 2.0:
            pipeline_miss["downside_new_customer_revenue"] = round(fc_new * 0.5) if fc_new else None
            pipeline_miss["note"] = ("Pipeline coverage < 2x — model new-customer revenue at 50% of "
                                     "forecast as the downside case.")
        elif coverage is not None:
            pipeline_miss["note"] = "Pipeline coverage ≥ 2x — new-customer revenue better supported."
        else:
            pipeline_miss["note"] = ("Pipeline coverage not computable — new-customer revenue, "
                                     "pipeline value, or conversion rate missing.")
        sens["pipeline_miss"] = pipeline_miss

        return sens

    # -----------------------------------------------------------------------
    # Flags (spec-neutral, presented as questions)
    # -----------------------------------------------------------------------

    def _apply_forecast_flags(self, rated_assumptions: list):
        for a in rated_assumptions:
            rating = a.get("credibility_rating")
            if rating == "Stretch":
                self._add_flag(
                    metric=f"forecast_assumption::{a.get('assumption_type')}",
                    value=str(a.get("stated_value")),
                    threshold="Supported/Plausible/Stretch rubric",
                    severity="Red",
                    note=a.get("rationale", ""),
                    source_doc=a.get("source_doc", ""),
                    confidence="medium",
                )
            elif rating == "Plausible":
                self._add_flag(
                    metric=f"forecast_assumption::{a.get('assumption_type')}",
                    value=str(a.get("stated_value")),
                    threshold="Supported/Plausible/Stretch rubric",
                    severity="Yellow",
                    note=a.get("rationale", ""),
                    source_doc=a.get("source_doc", ""),
                    confidence="medium",
                )
            else:
                self._log_no_flag(
                    f"forecast_assumption::{a.get('assumption_type')}",
                    str(a.get("stated_value")), "Supported", a.get("rationale", ""),
                )

    def _build_management_validation_items(self, rated_assumptions: list) -> list:
        """Assumptions requiring management to substantiate (spec §9.4)."""
        items = []
        for a in rated_assumptions:
            if a.get("credibility_rating") in ("Plausible", "Stretch"):
                items.append({
                    "item": f"Substantiate the {a.get('assumption_type','').replace('_',' ')} "
                            f"assumption ({a.get('stated_value')}): {a.get('rationale')}",
                    "priority": "high" if a.get("credibility_rating") == "Stretch" else "medium",
                    "related_assumption": a.get("assumption_type"),
                })
        return items

    # -----------------------------------------------------------------------
    # run()
    # -----------------------------------------------------------------------

    def run(self, company_name: str, spark, llm_endpoint: str, catalog: str = "uc13") -> dict:
        self._reset_state()
        self._company_name = company_name
        self._catalog = catalog

        print("  Loading trailing actuals from Financial Trends Agent ...")
        trailing = self._load_financial_trends(company_name, spark)
        print("  Loading Tier 1+2 EBITDA scenario from QofE Agent ...")
        qofe = self._load_qofe_addbacks(company_name, spark)
        print("  Loading top customers from Customer Quality Agent ...")
        top_customers = self._load_top_customers(company_name, spark)

        print("  Running retrieval tools ...")
        tr1 = self._tool_retrieve_financial_model(spark)
        tr2 = self._tool_retrieve_forward_guidance(spark)
        tr3 = self._tool_retrieve_pipeline_backlog(spark)
        tr4 = self._tool_load_company_profile(company_name, spark)

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

        # Compact trailing context — series only, never raw chunks.
        trailing_context = json.dumps({
            "revenue_trend": trailing.get("revenue_trend"),
            "gross_margin": trailing.get("gross_margin"),
            "ebitda": trailing.get("ebitda"),
        }, default=str)[:8000]

        print("  Calling LLM for forecast assumption extraction ...")
        user_prompt = _USER_PROMPT_TEMPLATE.format(
            company_profile_json=company_profile_json,
            trailing_context=trailing_context,
            combined_chunk_text=combined_chunk_text,
        )
        raw_response = self._call_llm(_SYSTEM_PROMPT, user_prompt, llm_endpoint, max_tokens=12_000)
        extracted = self._parse_json_response(raw_response)

        llm_step = len(self._trace) + 1
        self._trace.append({
            "step":       llm_step,
            "tool":       "llm_extraction",
            "input":      f"combined context: {len(all_chunks)} deduplicated chunks",
            "output":     f"Extracted {len(extracted.get('forecast_assumptions') or [])} assumptions, "
                          f"{len(extracted.get('revenue_build') or [])} revenue-build periods",
            "confidence": "high" if all_chunks else "low",
            "sources":    list({c.file_name for c in all_chunks}),
        })

        for cit in (extracted.get("citations") or []):
            self._add_citation(
                claim=cit.get("field", ""),
                document=cit.get("document", ""),
                location=cit.get("location", ""),
                confidence=cit.get("confidence", "low"),
                raw_text=cit.get("quote", ""),
            )

        # ── Deterministic credibility rubric ──────────────────────────────
        print("  Applying forecast credibility rubric (Supported/Plausible/Stretch) ...")
        rated_assumptions = []
        for a in (extracted.get("forecast_assumptions") or []):
            verdict = self._rate_assumption(a, trailing)
            rated_assumptions.append({**a, **verdict})

        revenue_build_comparison = self._build_revenue_build_comparison(
            extracted.get("revenue_build") or [], trailing
        )

        print("  Building downside sensitivity inputs ...")
        downside = self._build_downside_sensitivities(extracted, trailing, qofe, top_customers)

        print("  Applying forecast flags ...")
        self._apply_forecast_flags(rated_assumptions)
        management_validation = self._build_management_validation_items(rated_assumptions)

        counts = {"supported": 0, "plausible": 0, "stretch": 0}
        for a in rated_assumptions:
            counts[(a.get("credibility_rating") or "").lower()] = \
                counts.get((a.get("credibility_rating") or "").lower(), 0) + 1

        return {
            "company_name":                  company_name,
            "executive_summary":             extracted.get("executive_summary"),
            "forecast_source_present":       str(extracted.get("forecast_source_present")).lower() == "true",
            "forecast_source":               extracted.get("forecast_source"),
            "forecast_assumptions_json":     json.dumps(rated_assumptions),
            "revenue_build_comparison_json": json.dumps(revenue_build_comparison),
            "downside_sensitivity_json":     json.dumps(downside),
            "management_validation_items_json": json.dumps(management_validation),
            "credibility_summary_json":      json.dumps(counts),
            "stretch_assumption_count":      counts.get("stretch", 0),
            "flags":                         self._flags_as_dicts(),
            "data_room_gaps":                list(self._data_room_gaps),
            "citations":                     json.dumps(self._citations_as_dicts()),
            "reasoning_trace":               list(self._trace),
            "created_at":                    datetime.now(timezone.utc).isoformat(),
        }


# ---------------------------------------------------------------------------
# Stakeholder report (YAML/JSON to UC Volume)
# ---------------------------------------------------------------------------

def _write_stakeholder_report(result: dict, catalog: str, spark) -> str:
    company_name = result["company_name"]

    assumptions   = json.loads(result.get("forecast_assumptions_json")      or "[]")
    rev_build     = json.loads(result.get("revenue_build_comparison_json")  or "[]")
    downside      = json.loads(result.get("downside_sensitivity_json")      or "{}")
    mgmt_items    = json.loads(result.get("management_validation_items_json") or "[]")
    counts        = json.loads(result.get("credibility_summary_json")       or "{}")
    citations     = json.loads(result.get("citations")                      or "[]")

    report = {
        "report": {
            "agent":        "forecast",
            "company":      company_name,
            "generated_at": result.get("created_at", ""),
        },
        "executive_summary":            result.get("executive_summary"),
        "forecast_source_present":      result.get("forecast_source_present"),
        "forecast_source":              result.get("forecast_source"),
        "credibility_summary":          counts,
        "forecast_assumptions":         assumptions,
        "revenue_build_comparison":     rev_build,
        "downside_sensitivity_inputs":  downside,
        "management_validation_items":  mgmt_items,
        "flags":                        result.get("flags") or [],
        "data_room_gaps":               result.get("data_room_gaps") or [],
        "citations":                    citations,
    }

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

    spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.analysis.reports")
    safe_name = company_name.replace(" ", "_").replace("/", "_")
    dir_path  = f"/Volumes/{catalog}/analysis/reports/{safe_name}"
    os.makedirs(dir_path, exist_ok=True)

    file_path = f"{dir_path}/forecast_report.{ext}"
    with open(file_path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return file_path


# ---------------------------------------------------------------------------
# Markdown assessment report
# ---------------------------------------------------------------------------

def generate_forecast_assessment(
    result: dict,
    spark,
    llm_endpoint: str,
    catalog: str = "uc13",
    write_to_volume: bool = True,
) -> str:
    """Generate a human-readable markdown Forecast assessment.

    Mirrors generate_qoe_assessment(): deterministic tables from the result dict +
    one LLM narrative call (max_tokens=6,000) for section paragraphs.
    Returns the markdown string; optionally writes forecast_assessment.md to the volume.
    """
    company_name = result["company_name"]
    assumptions  = json.loads(result.get("forecast_assumptions_json")      or "[]")
    rev_build    = json.loads(result.get("revenue_build_comparison_json")  or "[]")
    downside     = json.loads(result.get("downside_sensitivity_json")      or "{}")
    mgmt_items   = json.loads(result.get("management_validation_items_json") or "[]")
    counts       = json.loads(result.get("credibility_summary_json")       or "{}")

    # ── Deterministic tables ───────────────────────────────────────────
    cred_rows = ["| Assumption | Stated | Rating | Rationale |",
                 "|---|---|---|---|"]
    for a in assumptions:
        cred_rows.append(
            f"| {a.get('assumption_type','').replace('_',' ')} "
            f"| {a.get('stated_value','—')} "
            f"| {_rating_emoji(a.get('credibility_rating'))} {a.get('credibility_rating','—')} "
            f"| {(a.get('rationale') or '').replace(chr(10),' ')} |"
        )
    cred_table = "\n".join(cred_rows)

    build_rows = ["| Period | Forecast Revenue | Implied YoY | Trailing CAGR | Δ (pp) | Flag |",
                  "|---|---|---|---|---|---|"]
    for r in rev_build:
        build_rows.append(
            f"| {r.get('period','—')} | {_fmt_dollars(r.get('forecast_revenue'))} "
            f"| {_fmt_pct(r.get('implied_yoy_growth_pct'))} | {_fmt_pct(r.get('trailing_cagr_pct'))} "
            f"| {r.get('delta_pp') if r.get('delta_pp') is not None else '—'} | {r.get('flag') or '—'} |"
        )
    build_table = "\n".join(build_rows)

    # ── One narrative LLM call ─────────────────────────────────────────
    narrative_system = (
        "You are a senior PE analyst writing the Forecast section of a diligence memo. "
        "Write factual, neutral prose. Cite documents where the underlying data provides "
        "them. Do not opine on whether to do the deal. 2–3 concise paragraphs only — "
        "each paragraph no more than 3 sentences. Be brief; the section must fit 1 page."
    )
    narrative_user = (
        f"Company: {company_name}\n\n"
        f"Executive summary (extracted): {result.get('executive_summary')}\n\n"
        f"Credibility summary: {json.dumps(counts)}\n\n"
        f"Rated assumptions: {json.dumps(assumptions)[:6000]}\n\n"
        f"Revenue build vs trailing: {json.dumps(rev_build)[:2000]}\n\n"
        f"Downside sensitivities: {json.dumps(downside)[:2000]}\n\n"
        "Write: (1) an overview of what the forecast assumes; (2) how credible the "
        "assumptions are vs trailing performance; (3) the key downside cases the deal "
        "team should model; (4) what management must substantiate."
    )
    from agents.shared.agent_base import WorkstreamAgent as _WA
    narrative = _WA()._call_llm(narrative_system, narrative_user, llm_endpoint, max_tokens=3_000)

    n_stretch = counts.get("stretch", 0)
    headline_flag = "🔴" if n_stretch else ("🟡" if counts.get("plausible") else "🟢")

    md = f"""# Forecast Assessment — {company_name}

**Overall forecast credibility:** {headline_flag}  ·  Supported: {counts.get('supported',0)} · Plausible: {counts.get('plausible',0)} · Stretch: {counts.get('stretch',0)}
**Forecast/model present:** {"Yes" if result.get('forecast_source_present') else "No — assumptions inferred from CIM / management presentation"}

{narrative}

## Assumption Credibility

{cred_table}

## Revenue Build vs. Trailing Actuals

{build_table}

## Downside Sensitivity Inputs (for the LBO model)

{_fmt_downside_md(downside)}

## Management Validation Items

"""
    if mgmt_items:
        for it in mgmt_items:
            md += f"- **[{it.get('priority','')}]** {it.get('item','')}\n"
    else:
        md += "- None — all assumptions rated Supported.\n"

    gaps = result.get("data_room_gaps") or []
    if gaps:
        md += "\n## Data Room Gaps\n\n"
        for g in gaps:
            md += f"- {g}\n"

    if write_to_volume:
        spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.analysis.reports")
        safe_name = company_name.replace(" ", "_").replace("/", "_")
        dir_path  = f"/Volumes/{catalog}/analysis/reports/{safe_name}"
        os.makedirs(dir_path, exist_ok=True)
        with open(f"{dir_path}/forecast_assessment.md", "w", encoding="utf-8") as fh:
            fh.write(md)

    return md


# ---------------------------------------------------------------------------
# Table DDL
# ---------------------------------------------------------------------------

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {table} (
    company_name                    STRING,
    executive_summary               STRING,
    forecast_source_present         BOOLEAN,
    forecast_source                 STRING,
    forecast_assumptions_json       STRING,
    revenue_build_comparison_json   STRING,
    downside_sensitivity_json       STRING,
    management_validation_items_json STRING,
    credibility_summary_json        STRING,
    stretch_assumption_count        INT,
    flags                           STRING,
    data_room_gaps                  ARRAY<STRING>,
    citations                       STRING,
    reasoning_trace                 STRING,
    created_at                      TIMESTAMP
) USING DELTA
"""


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------

def main(spark=None) -> dict:
    repo_root = find_repo_root()
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    company_name  = get_param("sp_company_name")
    catalog       = get_param("catalog",      default="uc13")
    llm_endpoint  = get_param("llm_endpoint", default="databricks-claude-sonnet-4-6")

    from pyspark.sql import SparkSession
    if spark is None:
        spark = SparkSession.getActiveSession()
    if spark is None:
        raise RuntimeError("No active Spark session.")

    print(f"\n=== Forecast Agent ({company_name}) ===")

    agent  = ForecastAgent()
    result = agent.run(company_name=company_name, spark=spark, llm_endpoint=llm_endpoint, catalog=catalog)

    # ── Save to Delta ──────────────────────────────────────────────────
    table = f"{catalog}.analysis.forecast"
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.analysis")

    _EXPECTED_COLS = {
        "company_name", "executive_summary", "forecast_source_present", "forecast_source",
        "forecast_assumptions_json", "revenue_build_comparison_json",
        "downside_sensitivity_json", "management_validation_items_json",
        "credibility_summary_json", "stretch_assumption_count",
        "flags", "data_room_gaps", "citations", "reasoning_trace", "created_at",
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
    spark.sql(f"DELETE FROM {table} WHERE company_name = :company_name", args={"company_name": company_name})

    from pyspark.sql import Row
    from pyspark.sql.types import (
        StructType, StructField, StringType, BooleanType, IntegerType,
        ArrayType, TimestampType,
    )

    schema = StructType([
        StructField("company_name",                    StringType(),  True),
        StructField("executive_summary",               StringType(),  True),
        StructField("forecast_source_present",         BooleanType(), True),
        StructField("forecast_source",                 StringType(),  True),
        StructField("forecast_assumptions_json",       StringType(),  True),
        StructField("revenue_build_comparison_json",   StringType(),  True),
        StructField("downside_sensitivity_json",       StringType(),  True),
        StructField("management_validation_items_json", StringType(), True),
        StructField("credibility_summary_json",        StringType(),  True),
        StructField("stretch_assumption_count",        IntegerType(), True),
        StructField("flags",                           StringType(),  True),
        StructField("data_room_gaps",                  ArrayType(StringType()), True),
        StructField("citations",                       StringType(),  True),
        StructField("reasoning_trace",                 StringType(),  True),
        StructField("created_at",                      TimestampType(), True),
    ])

    row_data = {
        "company_name":                    result["company_name"],
        "executive_summary":               result.get("executive_summary"),
        "forecast_source_present":         result.get("forecast_source_present"),
        "forecast_source":                 result.get("forecast_source"),
        "forecast_assumptions_json":       result.get("forecast_assumptions_json"),
        "revenue_build_comparison_json":   result.get("revenue_build_comparison_json"),
        "downside_sensitivity_json":       result.get("downside_sensitivity_json"),
        "management_validation_items_json": result.get("management_validation_items_json"),
        "credibility_summary_json":        result.get("credibility_summary_json"),
        "stretch_assumption_count":        result.get("stretch_assumption_count"),
        "flags":                           json.dumps(result.get("flags") or []),
        "data_room_gaps":                  result.get("data_room_gaps") or [],
        "citations":                       result.get("citations"),
        "reasoning_trace":                 json.dumps(result.get("reasoning_trace") or []),
        "created_at":                      datetime.now(timezone.utc),
    }

    df = spark.createDataFrame([Row(**row_data)], schema=schema)
    df.write.format("delta").mode("append").option("mergeSchema", "true").saveAsTable(table)

    print(f"\n✓ Saved forecast output → {table}")

    # ── Export stakeholder report ──────────────────────────────────────
    report_path = _write_stakeholder_report(result, catalog, spark)
    result["report_path"] = report_path
    print(f"✓ Stakeholder report → {report_path}")

    return result


if __name__ == "__main__":
    main()
