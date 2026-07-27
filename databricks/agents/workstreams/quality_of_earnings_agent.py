"""
quality_of_earnings_agent.py — Phase 3: Quality of Earnings Workstream Agent.

Applies the four-tier addback classification framework and revenue quality flags to
produce a structured pre-QofE scope document. Primary input: QofE report (if present)
and the addback_schedule_json passed through from financial_trends_agent.py.

This agent is NOT a replacement for the accounting provider. Its output is a
structured scope document for the deal team and QofE firm to act on.

Phase 3 outputs:
  - Table uc13.analysis.quality_of_earnings

Dependencies:
  - uc13.ingestion.embeddings
  - uc13.classification.doc_relevance
  - uc13.classification.company_profile
  - uc13.analysis.financial_trends      (reads addback_schedule_json)
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
# Secrets / params helpers — copied verbatim from financial_trends_agent.py
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
# Repo root resolver — copied verbatim from financial_trends_agent.py
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
# Numeric helper
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
    """Format a numeric value as '$1,234,567' or '—' if absent."""
    if val is None:
        return "—"
    if isinstance(val, (int, float)):
        return f"${float(val):,.0f}"
    n = _parse_numeric(str(val))
    if n is None:
        return str(val) if val else "—"
    return f"${n:,.0f}"


def _fmt_pct(val) -> str:
    """Format a numeric value as '12.3%' or '—' if absent."""
    if val is None:
        return "—"
    if isinstance(val, (int, float)):
        return f"{float(val):.1f}%"
    n = _parse_numeric(str(val))
    return f"{n:.1f}%" if n is not None else str(val)


def _tier_emoji(tier: str) -> str:
    """Return a traffic-light emoji for a tier classification string."""
    t = (tier or "").strip()
    if t == "Tier 1":
        return "🟢"
    if t in ("Tier 2", "Tier 3"):
        return "🟡"
    if t == "Tier 4":
        return "🔴"
    return "⚪"


# ---------------------------------------------------------------------------
# LLM prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a senior PE investment analyst extracting structured quality of earnings
information from financial due diligence documents. Rules:
1. Extract ONLY what is explicitly stated in the provided context.
2. Do NOT infer, compute, assume, or hallucinate any value.
3. If a value is absent from the context, return null for that field.
4. Every extracted value must have a citation: document name, location
   (page number or section title), and a quote of ≤30 words.
5. Return ONLY valid JSON with no preamble and no markdown fences.
6. Classify each addback into one of four tiers:
   - Tier 1 (Strong): clearly one-time, documented, no recurring substitute.
     Examples: closed legal settlement, facility relocation, one-time IT migration.
   - Tier 2 (Defensible): owner/private-company costs that won't recur under PE.
     Examples: above-market owner comp vs. comp survey, owner personal expenses,
     family members on payroll with no operational role.
   - Tier 3 (Stretch): defensible but require execution risk post-close.
     Examples: run-rate adjustments for hires not yet made, pro-forma synergies,
     cost cuts where the role may need replacing.
   - Tier 4 (Reach): unlikely to survive buyer QofE.
     Examples: recurring marketing labelled one-time, growth investments labelled
     addbacks, COVID/stimulus without contemporaneous documentation.
   ABSOLUTE RULE: any addback where supporting_doc_referenced is "Not referenced"
   or null MUST be classified Tier 4. Do not override this rule under any circumstances.
7. Revenue quality — detect these patterns if present in the document context:
   DSO trending up >10 days over trailing 12 months; bill-and-hold language;
   period-end revenue spike (last week >2x weekly average); non-recurring items
   in run-rate without normalization; addbacks growing faster than reported EBITDA;
   revenue recognition policy change between years; episodic/event-driven demand
   (healthcare: hard to forecast, inconsistent referral patterns).
   Unusual credits, rebates, discounts, refunds, or concessions that reduce stated
   revenue — flag if material or if the pattern repeats across periods
   (flag_type: unusual_credits_rebates_refunds).
   AR aging deterioration, write-offs, or collections issues — flag if DSO is
   rising alongside AR write-offs, if bad debt expense is growing, or if the
   aging schedule shows a shift toward older buckets
   (flag_type: ar_aging_writeoffs).
8. For each addback from the ADDBACK SCHEDULE passthrough block: re-evaluate it
   against the VDR context to confirm or update the tier. If the passthrough
   already has supporting_doc_referenced, use that; otherwise apply the Tier 4
   auto-classification rule.
9. pre_qofe_scope_items should be specific, actionable questions for the accounting
   provider — not generic. Each item should reference a specific addback, document,
   or financial pattern found in the context.\
"""

_USER_PROMPT_TEMPLATE = """\
COMPANY PROFILE (from Phase 2 output):
{company_profile_json}

{addback_context}

{working_capital_context}

RETRIEVED DOCUMENT CONTEXT:
{combined_chunk_text}

Extract quality of earnings fields and return this exact JSON structure:
{{
  "addback_ledger": [
    {{
      "item_id": "<sequential integer starting at 1>",
      "description": "<addback description as stated>",
      "amount_dollars": "<$ as stated>",
      "period": "<fiscal year or TTM>",
      "tier_classification": "<Tier 1 | Tier 2 | Tier 3 | Tier 4>",
      "tier_rationale": "<one-sentence explanation for this tier>",
      "supporting_doc_referenced": "<filename referenced in schedule, or 'Not referenced'>",
      "supporting_doc_in_vdr": "<true | false | unknown>",
      "source_doc": "<filename where this addback was found>",
      "source_location": "<page or section>",
      "raw_text": "<≤30 word quote>"
    }}
  ],
  "revenue_quality_flags": [
    {{
      "flag_type": "<dso_trending_up | period_end_spike | non_recurring_in_run_rate | addbacks_growing_faster | revenue_recognition_change | episodic_revenue | bill_and_hold | unusual_credits_rebates_refunds | ar_aging_writeoffs>",
      "evidence": "<description of what was found>",
      "severity": "<Red | Yellow>",
      "source_doc": "<filename>",
      "source_location": "<page or section>",
      "raw_text": "<≤30 word quote>"
    }}
  ],
  "reported_ebitda_base": {{
    "amount_dollars": "<most recent reported EBITDA $ as stated>",
    "period": "<period>",
    "source_doc": "<filename>"
  }},
  "pre_qofe_scope_items": [
    {{
      "item": "<specific actionable question for the QofE accounting provider>",
      "priority": "<high | medium>",
      "related_addback_ids": ["<item_id integers>"]
    }}
  ],
  "qofe_report_present": "<true | false>",
  "qofe_report_source": "<filename or null>",
  "citations": [
    {{
      "field": "<field_name>",
      "document": "<exact filename>",
      "location": "<page, section, or tab>",
      "quote": "<≤30 word quote>",
      "confidence": "<high | medium | low>"
    }}
  ],
  "executive_summary": "<2–3 sentence factual description of addback quantum, tier distribution, and key revenue quality observations. Describe what the data shows — do not opine on deal outcome.>",
  "extraction_notes": "<missing addback schedule, ambiguous tiers, data quality issues>"
}}\
"""


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

from agents.shared.agent_base import WorkstreamAgent


class QualityOfEarningsAgent(WorkstreamAgent):
    """Phase 3 Quality of Earnings workstream agent."""

    agent_name = "quality_of_earnings"

    def __init__(self):
        super().__init__()

    def _log_no_flag(self, metric: str, value_str: str, threshold: str, note: str = ""):
        """Log a threshold evaluation that did NOT trigger a flag."""
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

    def _load_addback_passthrough(self, company_name: str, spark) -> list[dict]:
        """Load addback schedule extracted by the Financial Trends Agent.

        Returns list of addback dicts. Returns empty list with a gap note if the
        Financial Trends Agent has not yet run — graceful fallback.

        NOTE: this single query intentionally keeps catalog + company_name inline
        (not :company_name bind args). ``tests/test_qoe_precondition_gate.py`` pins
        this behaviour: it asserts both the catalog and the company name appear in
        the emitted SQL text and stubs ``spark.sql(query)`` with no ``args`` kwarg.
        The company_name parameterization (bind args) is applied to every other
        SQL site in this module; see decision log T5 for the rationale.
        """
        try:
            rows = spark.sql(f"""
                SELECT addback_schedule_json FROM {self._catalog}.analysis.financial_trends
                WHERE company_name = '{company_name}'
                ORDER BY created_at DESC LIMIT 1
            """).collect()
            if rows and rows[0]["addback_schedule_json"]:
                return json.loads(rows[0]["addback_schedule_json"])
        except Exception:
            pass
        self._add_gap(
            f"addback_schedule_json not found in {self._catalog}.analysis.financial_trends — "
            "Financial Trends Agent has not run or found no addbacks. "
            "QofE scope will rely on direct VDR retrieval only."
        )
        return []

    def _load_customer_quality(self, company_name: str, spark) -> list:
        """Load top_customers from {catalog}.analysis.customer_quality.

        Returns [] with a gap note if CQA has not run or GM data is absent.
        Only returns customers when at least one has gm_pct or gm_dollars populated.
        """
        try:
            rows = spark.sql(
                f"SELECT top_customers_json FROM {self._catalog}.analysis.customer_quality "
                "WHERE company_name = :company_name "
                "ORDER BY created_at DESC LIMIT 1",
                args={"company_name": company_name},
            ).collect()
            if not rows:
                self._add_gap(
                    "Customer Quality Agent output not found — "
                    "customer profitability cross-check skipped."
                )
                return []
            customers = json.loads(rows[0]["top_customers_json"] or "[]")
            has_gm = any(c.get("gm_pct") or c.get("gm_dollars") for c in customers)
            if not has_gm:
                self._add_gap(
                    "Customer Quality Agent output present but no per-customer "
                    "gross margin data (gm_pct / gm_dollars) — "
                    "customer profitability cross-check skipped."
                )
                return []
            return customers
        except Exception as e:
            self._add_gap(f"Could not load customer_quality table: {e}")
            return []

    def _detect_profitability_outliers(self, customers: list) -> list:
        """Flag customers whose GM is materially below the portfolio average.

        Only runs when gm_pct is available for at least 2 customers.
        Returns [] if insufficient data — never raises.
        threshold_delta = 10pp below portfolio average.
        severity: 'material' if revenue_pct_yr1 > 20%, else 'track'.
        """
        if not customers:
            return []

        gm_values = []
        for c in customers:
            val = c.get("gm_pct")
            if val is not None:
                try:
                    gm_values.append(
                        (c, float(str(val).replace("%", "").strip()))
                    )
                except (ValueError, TypeError):
                    pass

        if len(gm_values) < 2:
            return []

        avg_gm = sum(v for _, v in gm_values) / len(gm_values)
        threshold_delta = 10.0  # Flag if >10pp below portfolio average

        outliers = []
        for customer, gm in gm_values:
            delta = gm - avg_gm
            if delta < -threshold_delta:
                rev_pct_raw = customer.get("revenue_pct_yr1", "unknown")
                try:
                    rev_pct_num = float(
                        str(rev_pct_raw).replace("%", "").strip() or 0
                    )
                except (ValueError, TypeError):
                    rev_pct_num = 0.0

                outliers.append({
                    "customer":               customer.get("customer_name", "Unknown"),
                    "revenue_pct":            rev_pct_raw,
                    "gm_pct":                 gm,
                    "portfolio_avg_gm_pct":   round(avg_gm, 1),
                    "delta_pp":               round(delta, 1),
                    "source_doc":             customer.get("source_doc", "customer_quality_agent"),
                    "source_location":        customer.get("source_location", ""),
                    "severity":               "material" if rev_pct_num > 20 else "track",
                    "note": (
                        f"GM of {gm:.1f}% is {abs(delta):.1f}pp below the "
                        f"portfolio average of {avg_gm:.1f}%. "
                        f"Revenue share: {rev_pct_raw}."
                    ),
                })
        return outliers

    def _load_working_capital_passthrough(self, company_name: str, spark) -> dict:
        """Load working-capital indicators extracted by the Financial Trends Agent.

        Returns a dict with at least ``dso_days``, ``dpo_days``, ``ar_aging_note``
        when available. Returns an empty dict with a gap note if the Financial
        Trends Agent has not yet run or produced no working-capital data.
        """
        try:
            rows = spark.sql(
                f"SELECT working_capital_json FROM {self._catalog}.analysis.financial_trends "
                "WHERE company_name = :company_name "
                "ORDER BY created_at DESC LIMIT 1",
                args={"company_name": company_name},
            ).collect()
            if rows and rows[0]["working_capital_json"]:
                return json.loads(rows[0]["working_capital_json"])
        except Exception:
            pass
        self._add_gap(
            f"working_capital_json not found in {self._catalog}.analysis.financial_trends — "
            "Financial Trends Agent has not run or found no working-capital data. "
            "Period-end maneuver flags and DSO/DPO trend review will be skipped."
        )
        return {}

    # -----------------------------------------------------------------------
    # Retrieval tool methods
    # -----------------------------------------------------------------------

    def _tool_retrieve_qofe_report(self, spark):
        from agents.shared.retrieval import semantic_search
        chunks = semantic_search(
            query="quality of earnings QofE adjusted EBITDA addback schedule sell-side accounting due diligence",
            spark=spark,
            company_name=self._company_name,
            top_k=12,
            workstream_filter=["QUALITY_EARNINGS"],
            file_name_filter=["QofE", "Quality", "Earnings", "Due Diligence", "Accounting", "Addback"],
            min_chunk_length=150,
        ).chunks
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_qofe_report",
            input_summary="query: quality of earnings QofE adjusted EBITDA addback schedule sell-side accounting due diligence",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_retrieve_ebitda_bridge(self, spark):
        from agents.shared.retrieval import semantic_search
        chunks = semantic_search(
            query="EBITDA bridge adjusted EBITDA reported EBITDA walkthrough reconciliation addback adjustment",
            spark=spark,
            company_name=self._company_name,
            top_k=10,
            workstream_filter=["QUALITY_EARNINGS", "FINANCIAL"],
            min_chunk_length=150,
        ).chunks
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_ebitda_bridge",
            input_summary="query: EBITDA bridge adjusted EBITDA reported EBITDA walkthrough reconciliation addback adjustment",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_retrieve_revenue_quality(self, spark):
        from agents.shared.retrieval import semantic_search
        chunks = semantic_search(
            query="revenue recognition deferred revenue bill and hold DSO period end spike one-time non-recurring",
            spark=spark,
            company_name=self._company_name,
            top_k=8,
            workstream_filter=["QUALITY_EARNINGS", "FINANCIAL"],
            min_chunk_length=150,
        ).chunks
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_revenue_quality",
            input_summary="query: revenue recognition deferred revenue bill and hold DSO period end spike one-time non-recurring",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_retrieve_owner_comp_support(self, spark):
        from agents.shared.retrieval import semantic_search
        chunks = semantic_search(
            query="owner compensation above market salary family members payroll personal expenses comp survey",
            spark=spark,
            company_name=self._company_name,
            top_k=6,
            workstream_filter=["QUALITY_EARNINGS", "FINANCIAL"],
            min_chunk_length=150,
        ).chunks
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_owner_comp_support",
            input_summary="query: owner compensation above market salary family members payroll personal expenses comp survey",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_retrieve_revenue_footnotes(self, spark):
        from agents.shared.retrieval import semantic_search
        chunks = semantic_search(
            query="revenue recognition policy footnote accounting policy change prior year restatement audit",
            spark=spark,
            company_name=self._company_name,
            top_k=6,
            workstream_filter=["QUALITY_EARNINGS", "FINANCIAL"],
            min_chunk_length=150,
        ).chunks
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_revenue_footnotes",
            input_summary="query: revenue recognition policy footnote accounting policy change prior year restatement audit",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence=confidence,
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
    # Post-LLM Python computations
    # -----------------------------------------------------------------------

    def _compute_ebitda_scenarios(self, extracted: dict) -> dict:
        """Compute three adjusted EBITDA scenarios from the addback ledger.

        Scenarios per spec: (1) reported, (2) Tier 1+2 addbacks only, (3) Tier 1 only.
        All computed from stated dollar values — never cross-document.
        """
        ledger = extracted.get("addback_ledger") or []
        base_rec = extracted.get("reported_ebitda_base") or {}
        base = _parse_numeric(base_rec.get("amount_dollars"))

        t1 = sum(abs(_parse_numeric(a.get("amount_dollars")) or 0)
                 for a in ledger if a.get("tier_classification") == "Tier 1")
        t2 = sum(abs(_parse_numeric(a.get("amount_dollars")) or 0)
                 for a in ledger if a.get("tier_classification") == "Tier 2")

        return {
            "reported_ebitda":         base,
            "tier1_plus_tier2_ebitda": (base + t1 + t2) if base is not None else None,
            "tier1_only_ebitda":       (base + t1)       if base is not None else None,
            "tier1_addback_total":     t1,
            "tier2_addback_total":     t2,
            "note": (
                "Three scenarios per spec §8.3: (1) reported, (2) Tier 1+2 addbacks only, "
                "(3) Tier 1 only. Computed from stated dollar values in addback ledger."
            ),
        }

    def _compute_addback_summary(self, extracted: dict) -> tuple[Optional[float], int]:
        """Return (total_addbacks_pct_of_ebitda, tier4_count)."""
        ledger = extracted.get("addback_ledger") or []
        base_rec = extracted.get("reported_ebitda_base") or {}
        base = _parse_numeric(base_rec.get("amount_dollars"))

        total = sum(abs(_parse_numeric(a.get("amount_dollars")) or 0) for a in ledger)
        tier4_count = sum(1 for a in ledger if a.get("tier_classification") == "Tier 4")
        total_pct = round((total / abs(base)) * 100, 1) if base else None

        return total_pct, tier4_count

    # -----------------------------------------------------------------------
    # Flag application
    # -----------------------------------------------------------------------

    def _apply_qofe_flags(self, extracted: dict, total_pct: Optional[float], tier4_count: int):
        ledger = extracted.get("addback_ledger") or []
        revenue_quality_flags = extracted.get("revenue_quality_flags") or []
        base_rec = extracted.get("reported_ebitda_base") or {}
        base = _parse_numeric(base_rec.get("amount_dollars"))

        # Tier 4 addbacks → Red per item
        for item in ledger:
            if item.get("tier_classification") == "Tier 4":
                desc = item.get("description", "")
                amt = item.get("amount_dollars", "unknown")
                source_doc = item.get("source_doc", "")
                self._add_flag(
                    metric="tier4_addback",
                    value=f"{desc[:80]} (${amt})",
                    threshold="Tier 4 classification",
                    severity="Red",
                    note=f"Tier 4 addback: {desc[:200]} (${amt}) — unlikely to survive buyer QofE. Source: {source_doc}.",
                    source_doc=source_doc,
                    confidence="high",
                )

        # Addback >5% of EBITDA with no VDR support
        for item in ledger:
            amt_num = _parse_numeric(item.get("amount_dollars"))
            if (amt_num is not None and base is not None and abs(base) > 0
                    and abs(amt_num) / abs(base) > 0.05
                    and str(item.get("supporting_doc_in_vdr", "")).lower() != "true"):
                desc = item.get("description", "")
                pct = round(abs(amt_num) / abs(base) * 100, 1)
                source_doc = item.get("source_doc", "")
                self._add_flag(
                    metric="large_unsupported_addback",
                    value=f"{desc[:60]} (${item.get('amount_dollars')}, {pct}% of EBITDA)",
                    threshold=">5% of EBITDA with no VDR support",
                    severity="Red",
                    note=f"Addback >5% of EBITDA ({pct}%) with no VDR document support: {desc[:200]}. Source: {source_doc}.",
                    source_doc=source_doc,
                    confidence="high",
                )

        # Total addbacks > 20% of EBITDA
        if total_pct is not None:
            if total_pct > 20:
                self._add_flag(
                    metric="total_addbacks_pct_of_ebitda",
                    value=f"{total_pct}%",
                    threshold=">20% of reported EBITDA",
                    severity="Yellow",
                    note=f"Total addbacks represent {total_pct}% of reported EBITDA — QofE review high priority. Heavy reliance on addbacks increases deal risk.",
                    source_doc=base_rec.get("source_doc", ""),
                    confidence="high",
                )
            else:
                self._log_no_flag("total_addbacks_pct_of_ebitda", f"{total_pct}%", "≤20%")
        else:
            self._add_gap("Cannot compute total addbacks % of EBITDA — reported EBITDA base not stated")

        # Revenue quality flags from LLM
        for rqf in revenue_quality_flags:
            severity = rqf.get("severity", "Yellow")
            evidence = rqf.get("evidence", "")
            flag_type = rqf.get("flag_type", "revenue_quality")
            source_doc = rqf.get("source_doc", "")
            self._add_flag(
                metric=f"revenue_quality_{flag_type}",
                value=evidence[:100],
                threshold=f"Revenue quality pattern: {flag_type}",
                severity=severity,
                note=f"Revenue quality concern ({flag_type}): {evidence[:200]}. Source: {source_doc}.",
                source_doc=source_doc,
                confidence="medium",
            )

        # No QofE report → data room gap
        if extracted.get("qofe_report_present") == "false":
            self._add_gap("No QofE report found in VDR — flag as data room gap")

    def _apply_working_capital_flags(self, wc: dict):
        """Generate deterministic flags from working-capital passthrough data.

        Flags period-end maneuvers and DSO/DPO trends using stated figures only.
        No computation of the peg — that is the QofE provider's scope.
        """
        if not wc:
            return

        source = f"{self._catalog}.analysis.financial_trends (working_capital_json)"

        dso = wc.get("dso_days")
        dpo = wc.get("dpo_days")
        ar_aging_note = wc.get("ar_aging_note") or ""

        # DSO trend — flag if list of period values shows >10 day increase
        if isinstance(dso, list) and len(dso) >= 2:
            dso_trend = dso[-1] - dso[0]
            if dso_trend > 10:
                self._add_flag(
                    metric="dso_trend",
                    value=f"DSO increased {round(dso_trend, 1)} days over period",
                    threshold=">10 day increase over measurement period",
                    severity="Yellow",
                    note=(
                        f"DSO increased {round(dso_trend, 1)} days over the measurement period "
                        f"(from {dso[0]} to {dso[-1]} days) — potential period-end acceleration of "
                        "collections or organic AR deterioration. Validate with AR aging schedule."
                    ),
                    source_doc=source,
                    confidence="medium",
                )
            else:
                self._log_no_flag("dso_trend", f"{dso_trend:+.1f} days", "≤+10 days")
        elif isinstance(dso, (int, float)):
            step = len(self._trace) + 1
            self._trace.append({
                "step":       step,
                "tool":       "working_capital_review",
                "input":      f"dso_days={dso}",
                "output":     f"DSO stated at {dso} days — single period, no trend to evaluate",
                "confidence": "medium",
                "sources":    [source],
            })

        # DPO trend — flag if list of period values shows >10 day stretch
        if isinstance(dpo, list) and len(dpo) >= 2:
            dpo_trend = dpo[-1] - dpo[0]
            if dpo_trend > 10:
                self._add_flag(
                    metric="dpo_stretch",
                    value=f"DPO increased {round(dpo_trend, 1)} days over period",
                    threshold=">10 day increase over measurement period",
                    severity="Yellow",
                    note=(
                        f"DPO increased {round(dpo_trend, 1)} days over the measurement period "
                        f"(from {dpo[0]} to {dpo[-1]} days) — potential AP stretch to manage "
                        "period-end working capital. Validate with AP aging and supplier payment terms."
                    ),
                    source_doc=source,
                    confidence="medium",
                )
            else:
                self._log_no_flag("dpo_stretch", f"{dpo_trend:+.1f} days", "≤+10 days")
        elif isinstance(dpo, (int, float)):
            step = len(self._trace) + 1
            self._trace.append({
                "step":       step,
                "tool":       "working_capital_review",
                "input":      f"dpo_days={dpo}",
                "output":     f"DPO stated at {dpo} days — single period, no trend to evaluate",
                "confidence": "medium",
                "sources":    [source],
            })

        # AR aging note — pass through as Yellow flag when present
        if ar_aging_note:
            self._add_flag(
                metric="ar_aging_note",
                value=ar_aging_note[:120],
                threshold="AR aging note from Financial Trends Agent",
                severity="Yellow",
                note=f"AR aging observation: {ar_aging_note[:300]}",
                source_doc=source,
                confidence="medium",
            )

    # -----------------------------------------------------------------------
    # run()
    # -----------------------------------------------------------------------

    def run(self, company_name: str, spark, llm_endpoint: str, catalog: str) -> dict:
        self._reset_state()
        self._company_name = company_name
        self._catalog = catalog
        print(f"  Loading addback passthrough from Financial Trends Agent ...")
        addback_passthrough = self._load_addback_passthrough(company_name, spark)
        print(f"  Loading working-capital passthrough from Financial Trends Agent ...")
        wc_passthrough = self._load_working_capital_passthrough(company_name, spark)
        print("  Loading customer quality data for profitability outlier detection ...")
        customers     = self._load_customer_quality(company_name, spark)
        prof_outliers = self._detect_profitability_outliers(customers)

        print(f"  Running 6 retrieval tools ...")
        tr1 = self._tool_retrieve_qofe_report(spark)
        tr2 = self._tool_retrieve_ebitda_bridge(spark)
        tr3 = self._tool_retrieve_revenue_quality(spark)
        tr4 = self._tool_retrieve_owner_comp_support(spark)
        tr5 = self._tool_retrieve_revenue_footnotes(spark)
        tr6 = self._tool_load_company_profile(company_name, spark)

        seen_texts: set[str] = set()
        all_chunks = []
        for tr in (tr1, tr2, tr3, tr4, tr5):
            for chunk in (tr.data or []):
                if chunk.chunk_text not in seen_texts:
                    seen_texts.add(chunk.chunk_text)
                    all_chunks.append(chunk)

        combined_chunk_text = "\n\n---\n\n".join(
            f"[File: {c.file_name}] [Section: {c.section_header}]\n{c.chunk_text}"
            for c in all_chunks
        )

        profile_dict = tr6.data
        company_profile_json = json.dumps(profile_dict, default=str) if profile_dict else "{}"

        addback_context = (
            f"ADDBACK SCHEDULE (passed from Financial Trends Agent):\n"
            f"{json.dumps(addback_passthrough, indent=2)}"
            if addback_passthrough
            else "ADDBACK SCHEDULE: Not available from Financial Trends Agent."
        )

        working_capital_context = (
            f"WORKING CAPITAL INDICATORS (passed from Financial Trends Agent):\n"
            f"{json.dumps(wc_passthrough, indent=2)}"
            if wc_passthrough
            else "WORKING CAPITAL INDICATORS: Not available from Financial Trends Agent."
        )

        print("  Calling LLM for extraction ...")
        user_prompt = _USER_PROMPT_TEMPLATE.format(
            company_profile_json=company_profile_json,
            addback_context=addback_context,
            working_capital_context=working_capital_context,
            combined_chunk_text=combined_chunk_text,
        )
        raw_response = self._call_llm(_SYSTEM_PROMPT, user_prompt, llm_endpoint)
        extracted = self._parse_json_response(raw_response)

        llm_step = len(self._trace) + 1
        self._trace.append({
            "step":       llm_step,
            "tool":       "llm_extraction",
            "input":      f"combined context: {len(all_chunks)} deduplicated chunks, {len(addback_passthrough)} addback passthrough items",
            "output":     f"Extracted {len(extracted.get('addback_ledger') or [])} addbacks, {len(extracted.get('revenue_quality_flags') or [])} revenue quality flags",
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

        # Post-LLM deterministic computations
        ebitda_scenarios = self._compute_ebitda_scenarios(extracted)
        total_pct, tier4_count = self._compute_addback_summary(extracted)

        print("  Applying QofE threshold flags ...")
        self._apply_qofe_flags(extracted, total_pct, tier4_count)

        print("  Applying working-capital flags ...")
        self._apply_working_capital_flags(wc_passthrough)

        # Append standing NWC peg scope item — always present; peg computation
        # is the QofE provider's scope, not Phase 1.
        pre_qofe_scope = list(extracted.get("pre_qofe_scope_items") or [])
        pre_qofe_scope.append({
            "item": (
                "Establish the net working capital peg over a trailing 12–24 month period"
            ),
            "priority": "high",
            "related_addback_ids": [],
        })

        return {
            "company_name":                 company_name,
            "executive_summary":            extracted.get("executive_summary"),
            "addback_ledger_json":          json.dumps(extracted.get("addback_ledger") or []),
            "revenue_quality_flags_json":   json.dumps(extracted.get("revenue_quality_flags") or []),
            "ebitda_scenarios_json":        json.dumps(ebitda_scenarios),
            "pre_qofe_scope_items_json":    json.dumps(pre_qofe_scope),
            "working_capital_awareness_json":       json.dumps(wc_passthrough) if wc_passthrough else "{}",
            "customer_profitability_outliers_json": json.dumps(prof_outliers),
            "qofe_report_present":          extracted.get("qofe_report_present") == "true",
            "total_addbacks_pct_of_ebitda": total_pct,
            "tier4_addback_count":          tier4_count,
            "flags":                        self._flags_as_dicts(),
            "data_room_gaps":               list(self._data_room_gaps),
            "citations":                    json.dumps(self._citations_as_dicts()),
            "reasoning_trace":              list(self._trace),
            "created_at":                   datetime.now(timezone.utc).isoformat(),
        }


# ---------------------------------------------------------------------------
# Stakeholder report
# ---------------------------------------------------------------------------

def _write_stakeholder_report(result: dict, catalog: str, spark) -> str:
    """Write a clean, human-readable YAML report to a UC Volume.

    Saves to /Volumes/{catalog}/analysis/reports/{company_name}/
    quality_of_earnings_report.yaml (or .json if PyYAML is unavailable).
    Returns the full volume path of the written file.
    """
    company_name = result["company_name"]

    # ── Parse JSON blobs back to Python objects for clean rendering ────
    addback_ledger       = json.loads(result.get("addback_ledger_json")        or "[]")
    revenue_quality_flags = json.loads(result.get("revenue_quality_flags_json") or "[]")
    ebitda_scenarios     = json.loads(result.get("ebitda_scenarios_json")       or "{}")
    pre_qofe_scope_items = json.loads(result.get("pre_qofe_scope_items_json")   or "[]")
    working_capital      = json.loads(result.get("working_capital_awareness_json") or "{}")
    citations            = json.loads(result.get("citations")                   or "[]")

    # ── Summarise addback ledger by tier for report header ─────────────
    tier_summary: dict[str, dict] = {}
    for item in addback_ledger:
        tier = item.get("tier_classification", "Unknown")
        amt_num = _parse_numeric(item.get("amount_dollars"))
        if tier not in tier_summary:
            tier_summary[tier] = {"count": 0, "total_dollars": 0.0}
        tier_summary[tier]["count"] += 1
        tier_summary[tier]["total_dollars"] += abs(amt_num) if amt_num is not None else 0.0

    # ── Build the curated report dict ──────────────────────────────────
    report = {
        "report": {
            "agent":        "quality_of_earnings",
            "company":      company_name,
            "generated_at": result.get("created_at", ""),
        },
        "executive_summary":            result.get("executive_summary"),
        "ebitda_scenarios":             ebitda_scenarios,
        "addback_ledger_by_tier": {
            tier: {
                "count":         info["count"],
                "total_dollars": round(info["total_dollars"], 2),
            }
            for tier, info in sorted(tier_summary.items())
        },
        "addback_ledger":               addback_ledger,
        "revenue_quality_flags":        revenue_quality_flags,
        "working_capital_awareness":    working_capital,
        "qofe_report_present":          result.get("qofe_report_present"),
        "total_addbacks_pct_of_ebitda": result.get("total_addbacks_pct_of_ebitda"),
        "tier4_addback_count":          result.get("tier4_addback_count"),
        "pre_qofe_scope_items":         pre_qofe_scope_items,
        "flags":                        result.get("flags") or [],
        "data_room_gaps":               result.get("data_room_gaps") or [],
        "citations":                    citations,
    }

    prof_outliers_raw = result.get("customer_profitability_outliers_json")
    if prof_outliers_raw:
        try:
            prof_outliers_parsed = json.loads(prof_outliers_raw)
            if prof_outliers_parsed:
                report["customer_profitability_outliers"] = prof_outliers_parsed
        except Exception:
            pass

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
    os.makedirs(dir_path, exist_ok=True)

    file_path = f"{dir_path}/quality_of_earnings_report.{ext}"
    with open(file_path, "w", encoding="utf-8") as fh:
        fh.write(content)

    return file_path


# ---------------------------------------------------------------------------
# Markdown assessment report
# ---------------------------------------------------------------------------

def generate_qoe_assessment(
    result: dict,
    spark,
    llm_endpoint: str,
    catalog: str = "uc13",
    write_to_volume: bool = True,
) -> str:
    """Generate a human-readable markdown Quality of Earnings assessment.

    Mirrors the ``generate_financial_assessment()`` pattern in
    ``financial_trends_agent.py``:
      1. Build deterministic tables from the result dict (no LLM).
      2. Make one LLM narrative call (max_tokens=3,000) for section paragraphs.
      3. Assemble and return the final markdown string.
      4. Optionally write to a UC Volume as ``quality_of_earnings_assessment.md``.

    Args:
        result:          Output dict from ``QualityOfEarningsAgent.run()`` or
                         the dict returned by ``main()``.
        spark:           Active SparkSession (needed only when write_to_volume=True).
        llm_endpoint:    Databricks model-serving endpoint name.
        catalog:         UC catalog for volume write (default 'uc13').
        write_to_volume: If True, writes the markdown to the reports volume.

    Returns:
        Markdown string.
    """
    company_name   = result.get("company_name", "Company")
    generated_at   = result.get("created_at", "")
    exec_summary   = result.get("executive_summary") or ""
    qofe_present   = result.get("qofe_report_present")
    total_pct      = result.get("total_addbacks_pct_of_ebitda")
    tier4_count    = result.get("tier4_addback_count") or 0
    data_room_gaps = result.get("data_room_gaps") or []
    _flags_raw     = result.get("flags") or []
    flags          = json.loads(_flags_raw) if isinstance(_flags_raw, str) else _flags_raw

    addback_ledger    = json.loads(result.get("addback_ledger_json")              or "[]")
    revenue_flags     = json.loads(result.get("revenue_quality_flags_json")       or "[]")
    ebitda_scenarios  = json.loads(result.get("ebitda_scenarios_json")            or "{}")
    scope_items       = json.loads(result.get("pre_qofe_scope_items_json")        or "[]")
    wc                = json.loads(result.get("working_capital_awareness_json")   or "{}")

    # ── EBITDA Scenarios table ─────────────────────────────────────────────
    rep   = ebitda_scenarios.get("reported_ebitda")
    t12   = ebitda_scenarios.get("tier1_plus_tier2_ebitda")
    t1o   = ebitda_scenarios.get("tier1_only_ebitda")

    def _delta_str(base, adj) -> str:
        if base is None or adj is None:
            return "—"
        delta = adj - base
        pct   = (delta / abs(base) * 100) if base else 0
        return f"{'+' if delta >= 0 else ''}{_fmt_dollars(delta)} ({pct:+.1f}%)"

    tbl_scenarios_lines = [
        "| Scenario | EBITDA ($) | Delta vs. Reported |",
        "|---|---|---|",
        f"| **Reported** | **{_fmt_dollars(rep)}** | — |",
        f"| Tier 1 + Tier 2 addbacks | {_fmt_dollars(t12)} | {_delta_str(rep, t12)} |",
        f"| Tier 1 addbacks only | {_fmt_dollars(t1o)} | {_delta_str(rep, t1o)} |",
    ]
    tbl_scenarios = "\n".join(tbl_scenarios_lines)

    # ── Addback Ledger table ───────────────────────────────────────────────
    _tier_rank = {"Tier 1": 0, "Tier 2": 1, "Tier 3": 2, "Tier 4": 3}
    sorted_addbacks = sorted(
        addback_ledger,
        key=lambda a: (
            _tier_rank.get(a.get("tier_classification", ""), 9),
            -abs(_parse_numeric(a.get("amount_dollars")) or 0),
        ),
    )

    ab_lines = [
        "| # | Description | Amount ($) | Tier | Supporting Doc | Flag |",
        "|---|---|---|---|---|---|",
    ]
    for idx, item in enumerate(sorted_addbacks, 1):
        desc    = (item.get("description") or "")[:60]
        amt     = _fmt_dollars(item.get("amount_dollars"))
        tier    = item.get("tier_classification") or "—"
        sup_doc = (item.get("supporting_doc_referenced") or "—")[:40]
        # Treat Tier 4 OR items with no VDR support as red
        no_support = str(item.get("supporting_doc_in_vdr", "")).lower() != "true"
        if tier == "Tier 4" or (tier not in ("Tier 1", "Tier 2", "Tier 3") and no_support):
            emoji = "🔴"
        else:
            emoji = _tier_emoji(tier)
        ab_lines.append(f"| {idx} | {desc} | {amt} | {tier} | {sup_doc} | {emoji} |")

    # Tier summary rows
    _tier_totals: dict[str, dict] = {}
    for item in addback_ledger:
        t   = item.get("tier_classification", "Unknown")
        amt = abs(_parse_numeric(item.get("amount_dollars")) or 0.0)
        if t not in _tier_totals:
            _tier_totals[t] = {"count": 0, "total": 0.0}
        _tier_totals[t]["count"] += 1
        _tier_totals[t]["total"] += amt

    ab_lines.append("|---|---|---|---|---|---|")
    for tier_label in sorted(_tier_totals, key=lambda t: _tier_rank.get(t, 9)):
        info = _tier_totals[tier_label]
        ab_lines.append(
            f"| | **{tier_label} subtotal ({info['count']} items)** "
            f"| **{_fmt_dollars(info['total'])}** | | | {_tier_emoji(tier_label)} |"
        )

    tbl_addbacks = "\n".join(ab_lines) if sorted_addbacks else "_No addbacks extracted._"

    # ── Revenue Quality Flags table ────────────────────────────────────────
    sev_emoji = {"Red": "🔴", "Yellow": "🟡", "Green": "🟢"}
    rqf_lines = [
        "| Flag Type | Evidence | Severity | Source Doc |",
        "|---|---|---|---|",
    ]
    for rqf in revenue_flags:
        flag_type  = (rqf.get("flag_type") or "").replace("_", " ")
        evidence   = (rqf.get("evidence") or "")[:90]
        sev        = rqf.get("severity", "Yellow")
        source     = (rqf.get("source_doc") or "—")[:40]
        rqf_lines.append(
            f"| {flag_type} | {evidence} | {sev_emoji.get(sev, '⚪')} {sev} | {source} |"
        )
    tbl_rqf = "\n".join(rqf_lines) if revenue_flags else "_No revenue quality flags identified._"

    # ── Working Capital key-value block ───────────────────────────────────
    wc_lines = []
    if wc.get("dso_days") is not None:
        wc_lines.append(f"- **DSO:** {wc['dso_days']} days")
    if wc.get("dpo_days") is not None:
        wc_lines.append(f"- **DPO:** {wc['dpo_days']} days")
    if wc.get("ar_aging_note"):
        wc_lines.append(f"- **AR Aging:** {wc['ar_aging_note']}")
    for k, v in wc.items():
        if k not in ("dso_days", "dpo_days", "ar_aging_note") and v is not None:
            wc_lines.append(f"- **{k}:** {v}")
    wc_block = "\n".join(wc_lines) if wc_lines else "_No working capital data extracted._"
    wc_available = bool(wc_lines)

    # ── Pre-QoE Scope Items list ───────────────────────────────────────────
    scope_lines = []
    for i, item in enumerate(scope_items, 1):
        text     = item.get("item") or str(item)
        priority = item.get("priority", "")
        pri_tag  = f" _{priority}_" if priority else ""
        scope_lines.append(f"{i}. {text}{pri_tag}")
    scope_block = "\n".join(scope_lines) if scope_lines else "_No scope items extracted._"

    # ── LLM narrative call ────────────────────────────────────────────────
    _tier4_items = [
        f"  - {a.get('description', '')[:80]} (${a.get('amount_dollars', '?')})"
        for a in addback_ledger if a.get("tier_classification") == "Tier 4"
    ]
    _tier4_block = "\n".join(_tier4_items) if _tier4_items else "  None identified."

    _rqf_summary = "\n".join(
        f"  - {rqf.get('flag_type','')}: {(rqf.get('evidence') or '')[:100]}"
        for rqf in revenue_flags
    ) or "  None identified."

    _scope_summary = "\n".join(
        f"  {i}. {item.get('item','')}"
        for i, item in enumerate(scope_items, 1)
    ) or "  None."

    _wc_summary = (
        f"DSO={wc.get('dso_days','n/a')}  DPO={wc.get('dpo_days','n/a')}  "
        f"AR_note={wc.get('ar_aging_note','n/a')}"
        if wc_available else "Not available."
    )

    _ASSESS_SYS = """\
You are a senior PE investment analyst writing a concise Quality of Earnings
assessment for an internal diligence memo. Write observations, not conclusions.

Rules:
1. Ground every statement in the data provided. Do not invent, infer, or speculate
   beyond what is shown.
2. No deal verdicts ("walk away", "proceed", "attractive", "concerning deal risk").
   Use neutral PE language: "warrants scrutiny", "requires provider confirmation",
   "tier distribution suggests", "flag language is consistent with".
3. If a section has no data, say so in one sentence.
4. Return pure markdown only — no preamble, no code fences.
5. Use exactly these 5 H3 headers (in order):
   ### Addback Quality
   ### Revenue Quality Observations
   ### EBITDA Scenario Implications
   ### Working Capital Observations
   ### Key Questions for the QoE Provider
6. Each of the first four sections: ≤2 sentences. Last section: numbered list of
   ≤4 specific questions (no answers). Questions must be drawn from the scope items
   and Tier 4 flags already shown — do not invent new questions.
7. Be concise. The entire QoE section must fit within 1 page of the memo.
"""

    _ASSESS_USER = f"""\
Use the Quality of Earnings data below to write the 5-section assessment.

COMPANY: {company_name}
QofE REPORT IN VDR: {'Yes' if qofe_present else 'No'}
TOTAL ADDBACKS AS % OF EBITDA: {_fmt_pct(total_pct)}
TIER 4 COUNT: {tier4_count}

EBITDA SCENARIOS:
{tbl_scenarios}

ADDBACK TIER DISTRIBUTION:
{json.dumps({t: d for t, d in _tier_totals.items()}, indent=2)}

TIER 4 ITEMS:
{_tier4_block}

REVENUE QUALITY FLAGS:
{_rqf_summary}

WORKING CAPITAL:
{_wc_summary}

PRE-QoE SCOPE ITEMS (numbered list from agent):
{_scope_summary}

EXECUTIVE SUMMARY (from extraction agent):
{exec_summary}
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
            "max_tokens": 3_000,
            "temperature": 0.0,
        },
    )
    from agents.shared.agent_base import accumulate_tokens as _accum_tokens
    _accum_tokens(_response.get("usage", {}), endpoint=llm_endpoint)
    narrative = _response["choices"][0]["message"]["content"].strip()

    # ── Assemble final markdown ────────────────────────────────────────────
    qofe_yn   = "Yes" if qofe_present else "No"
    overlay   = result.get("industry_overlay_used", "")

    md: list[str] = []
    md.append(f"# Quality of Earnings Assessment — {company_name}")
    md.append(
        f"_Generated: {generated_at}  |  "
        f"{'Overlay: ' + overlay + '  |  ' if overlay else ''}"
        f"QofE report in VDR: {qofe_yn}_\n"
    )

    md.append("## Executive Summary\n")
    md.append(exec_summary if exec_summary else "_No executive summary extracted._")
    md.append("")

    md.append("---\n")
    md.append("## EBITDA Scenarios\n")
    md.append("> Three scenarios per spec §8.3. Computed from stated figures in the addback ledger.\n")
    md.append(tbl_scenarios)
    md.append("")

    # Extract and append just the EBITDA scenario narrative paragraph
    def _extract_section(narrative_text: str, header: str) -> str:
        """Pull the content under a given ### header from the narrative string."""
        pattern = rf"###\s*{re.escape(header)}\s*\n(.*?)(?=\n###|\Z)"
        m = re.search(pattern, narrative_text, re.DOTALL | re.IGNORECASE)
        return m.group(1).strip() if m else ""

    ebitda_narrative = _extract_section(narrative, "EBITDA Scenario Implications")
    if ebitda_narrative:
        md.append(ebitda_narrative)
        md.append("")

    md.append("---\n")
    md.append("## Addback Ledger\n")
    md.append(
        f"> Sorted by tier (Tier 1 first), then amount descending. "
        f"Total addbacks as % of reported EBITDA: **{_fmt_pct(total_pct)}**. "
        f"Tier 4 count: **{tier4_count}**.\n"
    )
    md.append(tbl_addbacks)
    md.append("")

    addback_narrative = _extract_section(narrative, "Addback Quality")
    if addback_narrative:
        md.append(addback_narrative)
        md.append("")

    md.append("---\n")
    md.append("## Revenue Quality Flags\n")
    md.append(tbl_rqf)
    md.append("")

    rqf_narrative = _extract_section(narrative, "Revenue Quality Observations")
    if rqf_narrative:
        md.append(rqf_narrative)
        md.append("")

    md.append("---\n")
    md.append("## Working Capital\n")
    md.append(wc_block)
    md.append("")

    wc_narrative = _extract_section(narrative, "Working Capital Observations")
    if wc_narrative:
        md.append(wc_narrative)
        md.append("")

    md.append("---\n")
    md.append("## Pre-QoE Scope Items\n")
    md.append(scope_block)
    md.append("")

    md.append("---\n")
    md.append("## Key Questions for the QoE Provider\n")
    kq_narrative = _extract_section(narrative, "Key Questions for the QoE Provider")
    md.append(kq_narrative if kq_narrative else "_See scope items above._")
    md.append("")

    md.append("---\n")
    md.append("## Data Room Gaps\n")
    if data_room_gaps:
        for gap in data_room_gaps:
            md.append(f"- {gap}")
    else:
        md.append("None identified.")
    md.append("")

    md.append("---")
    md.append(
        "_Citations available in `quality_of_earnings_report.yaml` "
        f"and `{catalog}.analysis.quality_of_earnings`._"
    )

    final_markdown = "\n".join(md)

    # ── Optional volume write ──────────────────────────────────────────────
    if write_to_volume:
        spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.analysis.reports")
        safe_name = company_name.replace(" ", "_").replace("/", "_")
        dir_path  = f"/Volumes/{catalog}/analysis/reports/{safe_name}"
        os.makedirs(dir_path, exist_ok=True)
        file_path = f"{dir_path}/quality_of_earnings_assessment.md"
        with open(file_path, "w", encoding="utf-8") as fh:
            fh.write(final_markdown)
        print(f"✓ QoE assessment → {file_path}")

    return final_markdown


# ---------------------------------------------------------------------------
# Delta table DDL
# ---------------------------------------------------------------------------

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {table} (
    company_name                   STRING,
    executive_summary              STRING,
    addback_ledger_json            STRING,
    revenue_quality_flags_json     STRING,
    ebitda_scenarios_json          STRING,
    pre_qofe_scope_items_json      STRING,
    working_capital_awareness_json STRING,
    customer_profitability_outliers_json STRING,
    qofe_report_present            BOOLEAN,
    total_addbacks_pct_of_ebitda   FLOAT,
    tier4_addback_count            INT,
    flags                          STRING,
    data_room_gaps                 ARRAY<STRING>,
    citations                      STRING,
    reasoning_trace                STRING,
    created_at                     TIMESTAMP
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
    catalog       = get_param("catalog",       default="uc13")
    llm_endpoint  = get_param("llm_endpoint",  default="databricks-meta-llama-3-3-70b-instruct")

    from pyspark.sql import SparkSession
    from agents.shared.run_context import (
        close_agent_run,
        load_affected_intents,
        open_agent_run,
    )
    if spark is None:
        spark = SparkSession.getActiveSession()
    if spark is None:
        raise RuntimeError("No active Spark session.")

    print(f"\n=== Quality of Earnings Agent ({company_name}) ===")

    open_agent_run(
        "qoe",
        company_name=company_name,
        catalog=catalog,
        affected_intents=load_affected_intents("qoe"),
        spark=spark,
    )
    try:
        agent  = QualityOfEarningsAgent()
        result = agent.run(company_name=company_name, spark=spark, llm_endpoint=llm_endpoint, catalog=catalog)

        # ── Save to Delta ──────────────────────────────────────────────────
        table = f"{catalog}.analysis.quality_of_earnings"
        spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.analysis")

        _EXPECTED_COLS = {
            "company_name", "executive_summary",
            "addback_ledger_json", "revenue_quality_flags_json", "ebitda_scenarios_json",
            "pre_qofe_scope_items_json", "working_capital_awareness_json",
            "customer_profitability_outliers_json",
            "qofe_report_present", "total_addbacks_pct_of_ebitda", "tier4_addback_count",
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
            StructType, StructField, StringType, BooleanType, FloatType,
            IntegerType, ArrayType, TimestampType,
        )

        schema = StructType([
            StructField("company_name",                   StringType(),  True),
            StructField("executive_summary",              StringType(),  True),
            StructField("addback_ledger_json",            StringType(),  True),
            StructField("revenue_quality_flags_json",     StringType(),  True),
            StructField("ebitda_scenarios_json",          StringType(),  True),
            StructField("pre_qofe_scope_items_json",      StringType(),  True),
            StructField("working_capital_awareness_json",          StringType(),  True),
            StructField("customer_profitability_outliers_json",    StringType(),  True),
            StructField("qofe_report_present",                     BooleanType(), True),
            StructField("total_addbacks_pct_of_ebitda",   FloatType(),   True),
            StructField("tier4_addback_count",            IntegerType(), True),
            StructField("flags",                          StringType(),  True),
            StructField("data_room_gaps",                 ArrayType(StringType()), True),
            StructField("citations",                      StringType(),  True),
            StructField("reasoning_trace",                StringType(),  True),
            StructField("created_at",                     TimestampType(), True),
        ])

        row_data = {
            "company_name":                 result["company_name"],
            "executive_summary":            result.get("executive_summary"),
            "addback_ledger_json":          result.get("addback_ledger_json"),
            "revenue_quality_flags_json":   result.get("revenue_quality_flags_json"),
            "ebitda_scenarios_json":        result.get("ebitda_scenarios_json"),
            "pre_qofe_scope_items_json":    result.get("pre_qofe_scope_items_json"),
            "working_capital_awareness_json":       result.get("working_capital_awareness_json", "{}"),
            "customer_profitability_outliers_json": result.get("customer_profitability_outliers_json"),
            "qofe_report_present":          result.get("qofe_report_present"),
            "total_addbacks_pct_of_ebitda": result.get("total_addbacks_pct_of_ebitda"),
            "tier4_addback_count":          result.get("tier4_addback_count"),
            "flags":                        json.dumps(result.get("flags") or []),
            "data_room_gaps":               result.get("data_room_gaps") or [],
            "citations":                    result.get("citations"),
            "reasoning_trace":              json.dumps(result.get("reasoning_trace") or []),
            "created_at":                   datetime.now(timezone.utc),
        }

        df = spark.createDataFrame([Row(**row_data)], schema=schema)
        df.write.format("delta").mode("append").option("mergeSchema", "true").saveAsTable(table)

        print(f"\n✓ Saved quality of earnings output → {table}")

        # ── Export stakeholder report ──────────────────────────────────────
        report_path = _write_stakeholder_report(result, catalog, spark)
        result["report_path"] = report_path
        print(f"✓ Stakeholder report → {report_path}")

        return result
    finally:
        close_agent_run()


GOLDEN_CHECKLIST_COVERAGE: list[dict] = [
    {
        "item_id": "revenue_quality_flags",
        "display_name": "Revenue quality flags extraction",
    },
    {
        "item_id": "ebitda_scenarios",
        "display_name": "EBITDA scenarios computation",
    },
    {
        "item_id": "pre_qofe_scope",
        "display_name": "Pre-QofE scope items extraction",
    },
    {
        "item_id": "qofe_report_present",
        "display_name": "QofE report presence detection",
    },
    {
        "item_id": "tier_classification_fidelity",
        "display_name": "Addback tier classification fidelity",
    },
    {
        "item_id": "data_room_gaps",
        "display_name": "Data-room gaps correctly reported",
    },
]

assert len(GOLDEN_CHECKLIST_COVERAGE) == 6
assert all(set(req) == {"item_id", "display_name"} for req in GOLDEN_CHECKLIST_COVERAGE)
assert len({req["item_id"] for req in GOLDEN_CHECKLIST_COVERAGE}) == 6


if __name__ == "__main__":
    main()
