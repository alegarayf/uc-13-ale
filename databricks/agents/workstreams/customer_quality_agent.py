"""
customer_quality_agent.py — Phase 3: Customer Quality Workstream Agent.

Extracts customer concentration, retention metrics, and payor mix from documents
tagged CUSTOMER. Applies Austin Hough's primary thresholds for tech services and
healthcare services. Generates a contract_trigger_list for any customer >20% of
revenue; this list is consumed by legal_contracts_agent.py.

Phase 1 posture: extract stated figures only. Never recompute NRR or GRR from
raw cohort data.

Phase 3 outputs:
  - Table uc13.analysis.customer_quality

Dependencies:
  - uc13.ingestion.embeddings
  - uc13.classification.doc_relevance
  - uc13.classification.company_profile
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


# ---------------------------------------------------------------------------
# LLM prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a senior PE investment analyst extracting structured customer quality
information from due diligence documents. Rules:
1. Extract ONLY what is explicitly stated in the provided context.
2. Do NOT infer, compute, assume, or hallucinate any value.
3. If a value is absent from the context, return null for that field.
4. Every extracted value must have a citation: document name, location
   (page number or section title), and a quote of ≤30 words.
5. Return ONLY valid JSON with no preamble and no markdown fences.
6. Extract the top 10 customers by revenue as a ranked list. Include all years
   available (up to 3 years of revenue %). If revenue % is stated, extract it exactly.
7. NRR must always be ≥ GRR arithmetically. If the documents state NRR lower than
   GRR, extract both values as stated and set a discrepancy note — do not correct them.
8. For healthcare documents: extract payor mix as % breakdown across Medicare,
   Medicaid, VA, commercial, managed care, and other. Payor mix is a required field
   for healthcare overlay — flag if absent.
9. Phase 1 posture is strict: extract stated NRR/GRR values verbatim. Do NOT
   recompute from cohort data. If the methodology is not explained in the document,
   note that in extraction_notes.
10. For each top customer: if the data room states gross margin by client (in a
    customer workbook, QofE report, or margin-by-customer tab), extract gm_pct and
    gm_dollars verbatim. Do NOT compute them. If the customer workbook has an AR aging
    schedule, payment terms, or collections notes, extract payment_behavior and
    discount_flag accordingly. These are stated-only fields — null when absent.
11. cohort_analysis: if a cohort schedule, vintage revenue table, or customer
    cohort analysis is present in any CUSTOMER or QUALITY_EARNINGS document, extract
    the available vintage years and a one-sentence summary of cohort performance.
    Do not compute cohort metrics; extract stated values only.
12. customer_health_indicators: scan AR aging schedules, customer notes, NPS
    summaries, and utilization reports. Extract stated metrics verbatim. For
    late_payment_note, look for DSO trends, overdue balances by customer, or
    collections commentary. For discount_flag on individual customers, look for
    line-item credits or concession notes in revenue workbooks.
13. contract_terms_summary: extract high-level contract term patterns across
    material customer contracts. Source is contract samples, MSA summaries, or
    legal due diligence prelim (if present in CUSTOMER or LEGAL workstream docs).
    Do not infer terms not stated. If no contract documents are in the retrieved
    context, all fields are 'unknown'.
14. revenue_type_mix: extract from CIM, management decks, or QofE revenue
    recognition notes. Use company's own definitions. If the company does not
    explicitly state a recurring vs. project split, set all fields to null and
    note in extraction_notes.
15. renewal_patterns: extract from customer workbook, CIM, or KPI files. Look
    for renewal rate tables, renewal cadence descriptions, or expansion ARR data.\
"""

_USER_PROMPT_TEMPLATE = """\
COMPANY PROFILE (from Phase 2 output):
{company_profile_json}

RETRIEVED DOCUMENT CONTEXT:
{combined_chunk_text}

Extract customer quality fields and return this exact JSON structure:
{{
  "top_customers": [
    {{
      "rank": 1,
      "customer_name": "<name or anonymized label as stated>",
      "revenue_pct_yr1": "<most recent year % or null>",
      "revenue_pct_yr2": "<prior year % or null>",
      "revenue_pct_yr3": "<2 years prior % or null>",
      "revenue_dollars": "<$ as stated or null>",
      "years_as_customer": "<stated or null>",
      "contract_status": "<contracted | month-to-month | unknown>",
      "gm_pct": "<gross margin % for this customer as stated in data room or null>",
      "gm_dollars": "<gross margin dollars for this customer as stated or null>",
      "payment_behavior": "<'on-time' | 'slow-pay' | 'disputed' | 'unknown' — as stated or inferred from AR aging note>",
      "discount_flag": "<true if discounts, rebates, or concessions are noted for this customer | false | null>",
      "revenue_trend_note": "<one-sentence description of growth, decline, or churn risk for this customer as stated, or null>",
      "source_doc": "<filename>",
      "source_location": "<page or section>"
    }}
  ],
  "concentration_summary": {{
    "top1_pct": "<% or null>",
    "top3_pct": "<% or null>",
    "top5_pct": "<% or null>",
    "top10_pct": "<% or null>",
    "source_doc": "<filename>"
  }},
  "retention": {{
    "nrr_pct": "<% as stated or null>",
    "nrr_period": "<period or null>",
    "nrr_methodology_explained": "<true | false>",
    "grr_pct": "<% as stated or null>",
    "grr_period": "<period or null>",
    "logo_churn_rate_annual_pct": "<% as stated or null>",
    "source_doc": "<filename>",
    "source_location": "<page or section>"
  }},
  "customer_tenure": {{
    "average_tenure_years": "<as stated or null>",
    "tenure_distribution_note": "<description as stated or null>",
    "source_doc": "<filename>"
  }},
  "cohort_analysis": {{
    "cohorts_available": "<true | false>",
    "cohort_vintage_years": ["<year>"],
    "cohort_summary_note": "<description of cohort performance as stated — revenue by vintage, expansion rate, or survival rate — or null>",
    "source_doc": "<filename or null>",
    "source_location": "<page, tab, or section or null>"
  }},
  "customer_health_indicators": {{
    "utilization_note": "<stated utilization rate or trend, or null>",
    "complaints_note": "<stated complaint rate, escalations, or NPS, or null>",
    "late_payment_note": "<late payment or collections trend as stated in AR aging or customer notes, or null>",
    "declining_spend_customers": ["<customer name or label if declining spend is explicitly stated, else empty list>"],
    "discounts_rebates_note": "<description of discount or concession patterns as stated, or null>",
    "source_doc": "<filename or null>"
  }},
  "contract_terms_summary": {{
    "termination_for_convenience": "<'yes' | 'no' | 'mixed' | 'unknown' — across material customer contracts>",
    "change_of_control_consent_required": "<'yes' | 'no' | 'mixed' | 'unknown'>",
    "pricing_escalators": "<'yes' | 'no' | 'unknown' — whether contracts have CPI or fixed escalators>",
    "exclusivity_clauses": "<'yes' | 'no' | 'unknown'>",
    "auto_renewal": "<'yes' | 'no' | 'mixed' | 'unknown'>",
    "typical_term_years": "<as stated or null>",
    "source_doc": "<filename or null>",
    "source_location": "<page or section or null>",
    "note": "<any material deviation from standard terms, or null>"
  }},
  "revenue_type_mix": {{
    "recurring_pct": "<% of revenue that is recurring/embedded — as stated or null>",
    "project_onetime_pct": "<% of revenue that is project-based or one-time — as stated or null>",
    "retainer_pct": "<% under MSA/retainer arrangements — as stated or null>",
    "source_doc": "<filename or null>",
    "methodology_note": "<how company defines recurring vs. project, or null>"
  }},
  "renewal_patterns": {{
    "avg_renewal_rate_pct": "<stated renewal rate or null>",
    "renewal_period_note": "<description of typical renewal cadence — annual, multi-year, evergreen — or null>",
    "upsell_expansion_note": "<any stated data on expansion revenue at renewal — or null>",
    "source_doc": "<filename or null>"
  }},
  "average_account_size": {{
    "acv_dollars": "<$ as stated or null>",
    "computation_note": "<if computed from revenue ÷ customer count in same doc, state both inputs; else null>",
    "source_doc": "<filename>"
  }},
  "payor_mix": [
    {{
      "payor_category": "<Medicare | Medicaid | VA | Commercial | Managed Care | Other>",
      "pct_of_revenue": "<% as stated or null>",
      "source_doc": "<filename>"
    }}
  ],
  "contract_trigger_list": [
    {{
      "customer_name": "<name>",
      "revenue_pct": "<% that triggered this>",
      "trigger_reason": "Customer >20% of revenue — contract review required",
      "contract_found_in_vdr": "<true | false | unknown>"
    }}
  ],
  "discrepancies": [
    {{
      "metric": "<e.g. NRR vs GRR inconsistency>",
      "note": "<description>"
    }}
  ],
  "citations": [
    {{
      "field": "<field_name>",
      "document": "<exact filename>",
      "location": "<page, section, or tab>",
      "quote": "<≤30 word quote>",
      "confidence": "<high | medium | low>"
    }}
  ],
  "executive_summary": "<2–3 sentence factual description of concentration profile, retention, and key risk. Describe what the data shows — do not render a verdict.>",
  "extraction_notes": "<ambiguities, missing fields, methodology concerns>"
}}\
"""


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

from agents.shared.agent_base import WorkstreamAgent  # noqa: E402


class CustomerQualityAgent(WorkstreamAgent):
    """Phase 3 Customer Quality workstream agent."""

    agent_name = "customer_quality"

    def __init__(self):
        super().__init__()

    # ------------------------------------------------------------------
    # Threshold logging helper (defined on this class, not in base)
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Tool methods
    # ------------------------------------------------------------------

    def _tool_retrieve_customer_concentration(self, spark):
        from agents.shared.retrieval import semantic_search
        query = "top customers revenue concentration customer list percentage revenue share"
        chunks = semantic_search(
            query=query,
            spark=spark,
            company_name=self._company_name,
            top_k=12,
            workstream_filter=["CUSTOMER"],
            file_name_filter=["Customer", "Revenue", "Concentration", "CIM", "QofE"],
            min_chunk_length=150,
        ).chunks
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_customer_concentration",
            input_summary=f"semantic_search: top customers revenue concentration (top_k=12, workstream=CUSTOMER)",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_retrieve_retention_metrics(self, spark):
        from agents.shared.retrieval import semantic_search
        query = "net revenue retention NRR gross revenue retention GRR churn logo retention cohort"
        chunks = semantic_search(
            query=query,
            spark=spark,
            company_name=self._company_name,
            top_k=8,
            workstream_filter=["CUSTOMER", "QUALITY_EARNINGS"],
            min_chunk_length=150,
        ).chunks
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_retention_metrics",
            input_summary=f"semantic_search: NRR/GRR/churn retention metrics (top_k=8, workstream=CUSTOMER,QUALITY_EARNINGS)",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_retrieve_customer_tenure(self, spark):
        from agents.shared.retrieval import semantic_search
        query = "customer tenure average tenure years relationship length customer vintage"
        chunks = semantic_search(
            query=query,
            spark=spark,
            company_name=self._company_name,
            top_k=6,
            workstream_filter=["CUSTOMER", "BUSINESS_MODEL"],
            min_chunk_length=150,
        ).chunks
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_customer_tenure",
            input_summary=f"semantic_search: customer tenure and relationship length (top_k=6, workstream=CUSTOMER,BUSINESS_MODEL)",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_retrieve_payor_mix(self, spark):
        from agents.shared.retrieval import semantic_search
        query = "payor mix Medicare Medicaid government commercial insurance reimbursement"
        chunks = semantic_search(
            query=query,
            spark=spark,
            company_name=self._company_name,
            top_k=6,
            workstream_filter=["CUSTOMER", "FINANCIAL"],
            min_chunk_length=150,
        ).chunks
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_payor_mix",
            input_summary=f"semantic_search: payor mix Medicare Medicaid government commercial (top_k=6, workstream=CUSTOMER,FINANCIAL)",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_retrieve_account_size(self, spark):
        from agents.shared.retrieval import semantic_search
        query = "average account size ACV annual contract value revenue per customer SMB enterprise"
        chunks = semantic_search(
            query=query,
            spark=spark,
            company_name=self._company_name,
            top_k=6,
            workstream_filter=["CUSTOMER", "KPI_OPS"],
            min_chunk_length=150,
        ).chunks
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_account_size",
            input_summary=f"semantic_search: average account size ACV annual contract value (top_k=6, workstream=CUSTOMER,KPI_OPS)",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_retrieve_cohort_data(self, spark):
        from agents.shared.retrieval import semantic_search
        query = (
            "cohort analysis customer vintage revenue by cohort retention by cohort "
            "new customer revenue expansion churn by year acquired"
        )
        chunks = semantic_search(
            query=query,
            spark=spark,
            company_name=self._company_name,
            top_k=8,
            workstream_filter=["CUSTOMER", "QUALITY_EARNINGS"],
            file_name_filter=["Cohort", "Customer", "Retention", "Revenue", "QofE"],
            min_chunk_length=150,
        ).chunks
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_cohort_data",
            input_summary="semantic_search: cohort analysis customer vintage revenue by cohort (top_k=8, workstream=CUSTOMER,QUALITY_EARNINGS)",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_retrieve_customer_health(self, spark):
        from agents.shared.retrieval import semantic_search
        query = (
            "customer health AR aging late payment overdue DSO discounts rebates "
            "concessions complaints NPS utilization declining spend collections"
        )
        chunks = semantic_search(
            query=query,
            spark=spark,
            company_name=self._company_name,
            top_k=8,
            workstream_filter=["CUSTOMER", "QUALITY_EARNINGS", "FINANCIAL"],
            file_name_filter=["AR", "Aging", "Customer", "Collections", "Revenue", "QofE"],
            min_chunk_length=150,
        ).chunks
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_customer_health",
            input_summary="semantic_search: customer health AR aging late payment discounts complaints utilization (top_k=8)",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_retrieve_contract_terms(self, spark):
        from agents.shared.retrieval import semantic_search
        query = (
            "contract terms termination for convenience change of control pricing escalator "
            "CPI escalation auto-renewal exclusivity MSA SOW renewal mechanics "
            "notice period right to terminate"
        )
        chunks = semantic_search(
            query=query,
            spark=spark,
            company_name=self._company_name,
            top_k=10,
            workstream_filter=["CUSTOMER", "LEGAL"],
            file_name_filter=["Contract", "MSA", "Agreement", "SOW", "Legal", "Customer"],
            min_chunk_length=150,
        ).chunks
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_contract_terms",
            input_summary="semantic_search: contract terms termination change of control escalator renewal (top_k=10, workstream=CUSTOMER,LEGAL)",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_retrieve_revenue_type_and_renewals(self, spark):
        from agents.shared.retrieval import semantic_search
        query = (
            "recurring revenue project revenue one-time revenue retainer ARR MRR "
            "renewal rate expansion revenue upsell revenue mix contracted backlog"
        )
        chunks = semantic_search(
            query=query,
            spark=spark,
            company_name=self._company_name,
            top_k=8,
            workstream_filter=["CUSTOMER", "BUSINESS_MODEL", "FINANCIAL"],
            file_name_filter=["CIM", "Revenue", "Customer", "Model", "KPI", "Metrics"],
            min_chunk_length=150,
        ).chunks
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_revenue_type_and_renewals",
            input_summary="semantic_search: recurring vs project revenue renewal rate expansion upsell (top_k=8, workstream=CUSTOMER,BUSINESS_MODEL,FINANCIAL)",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_load_company_profile(self, company_name: str, spark):
        sql = f"SELECT * FROM {self._catalog}.classification.company_profile WHERE company_name = '{company_name}' ORDER BY created_at DESC LIMIT 1"
        rows = spark.sql(sql).collect()
        if not rows:
            self._add_gap("company_profile not found — run company_profiler.py first")
            return self._tool_call(
                tool_name="load_company_profile",
                input_summary=f"SQL: company_profile WHERE company_name='{company_name}'",
                data=None,
                output_summary="No company profile found",
                confidence="low",
                source_docs=[],
            )
        row_dict = rows[0].asDict()
        return self._tool_call(
            tool_name="load_company_profile",
            input_summary=f"SQL: company_profile WHERE company_name='{company_name}'",
            data=row_dict,
            output_summary=f"Company profile loaded: industry_overlay={row_dict.get('industry_overlay')}",
            confidence="high",
            source_docs=[f"{self._catalog}.classification.company_profile"],
        )

    # ------------------------------------------------------------------
    # Post-LLM enforcement: contract trigger list
    # ------------------------------------------------------------------

    def _build_contract_trigger_list(self, extracted: dict) -> list[dict]:
        llm_triggers = {t.get("customer_name"): t for t in (extracted.get("contract_trigger_list") or [])}
        for customer in (extracted.get("top_customers") or []):
            pct = _parse_numeric(customer.get("revenue_pct_yr1"))
            if pct is not None and pct > 20:
                name = customer.get("customer_name", "Unknown")
                if name not in llm_triggers:
                    llm_triggers[name] = {
                        "customer_name": name,
                        "revenue_pct": customer.get("revenue_pct_yr1"),
                        "trigger_reason": "Customer >20% of revenue — contract review required",
                        "contract_found_in_vdr": "unknown",
                    }
        return list(llm_triggers.values())

    # ------------------------------------------------------------------
    # Threshold flagging
    # ------------------------------------------------------------------

    def _apply_customer_flags(self, extracted: dict, overlay: Optional[str]):
        overlay_lower = (overlay or "").lower()
        apply_tech       = "tech" in overlay_lower or overlay is None
        apply_healthcare = "healthcare" in overlay_lower or overlay is None

        top_customers = extracted.get("top_customers") or []
        retention = extracted.get("retention") or {}
        payor_mix = extracted.get("payor_mix") or []

        # Top customer concentration
        top1_raw = None
        top1_doc = ""
        if top_customers:
            top1_raw = top_customers[0].get("revenue_pct_yr1")
            top1_doc = top_customers[0].get("source_doc", "")
        top1_num = _parse_numeric(top1_raw)

        if apply_tech:
            if top1_num is None:
                if top_customers:
                    self._add_gap("Top customer revenue % not stated — required for concentration threshold evaluation (tech)")
            elif top1_num > 25:
                self._add_flag(
                    metric="top_customer_concentration",
                    value=str(top1_raw),
                    threshold=">25% (tech services)",
                    severity="Red",
                    note=f"Top customer represents {top1_raw} of revenue, above the 25% concentration threshold for tech services. Source: {top1_doc}.",
                    source_doc=top1_doc,
                    confidence="high",
                )
            else:
                self._log_no_flag("top_customer_concentration (tech)", str(top1_raw), "≤25%")

        if apply_healthcare:
            if top1_num is None:
                if top_customers:
                    self._add_gap("Top referral source/customer revenue % not stated — required for concentration threshold evaluation (healthcare)")
            elif top1_num > 20:
                self._add_flag(
                    metric="top_customer_concentration",
                    value=str(top1_raw),
                    threshold=">20% (healthcare services)",
                    severity="Red",
                    note=f"Top customer/referral source represents {top1_raw} of revenue, above the 20% concentration threshold for healthcare services. Source: {top1_doc}.",
                    source_doc=top1_doc,
                    confidence="high",
                )
            else:
                self._log_no_flag("top_customer_concentration (healthcare)", str(top1_raw), "≤20%")

        # NRR
        nrr_raw = retention.get("nrr_pct")
        nrr_num = _parse_numeric(nrr_raw)
        nrr_doc = retention.get("source_doc", "")

        if apply_tech:
            if nrr_num is None:
                self._add_gap("NRR not stated — required for retention threshold evaluation")
            elif nrr_num < 90:
                self._add_flag(
                    metric="nrr_pct",
                    value=str(nrr_raw),
                    threshold="<90% (tech services)",
                    severity="Red",
                    note=f"NRR of {nrr_raw} is below the 90% threshold, indicating net revenue contraction from existing customers. Source: {nrr_doc}.",
                    source_doc=nrr_doc,
                    confidence="high",
                )
            else:
                self._log_no_flag("nrr_pct (tech)", str(nrr_raw), "≥90%")

        # GRR
        grr_raw = retention.get("grr_pct")
        grr_num = _parse_numeric(grr_raw)

        if apply_tech:
            if grr_num is None:
                self._add_gap("GRR not stated — required for retention threshold evaluation")
            elif grr_num < 80:
                self._add_flag(
                    metric="grr_pct",
                    value=str(grr_raw),
                    threshold="<80% (tech services)",
                    severity="Red",
                    note=f"GRR of {grr_raw} is below the 80% threshold, indicating significant gross revenue churn. Source: {nrr_doc}.",
                    source_doc=nrr_doc,
                    confidence="high",
                )
            else:
                self._log_no_flag("grr_pct (tech)", str(grr_raw), "≥80%")

        # NRR < GRR inconsistency check
        if nrr_num is not None and grr_num is not None and nrr_num < grr_num:
            self._add_gap("NRR stated lower than GRR — metric error or methodology issue; pass to QofE Agent")

        # Average account size (tech)
        if apply_tech:
            acv_raw = (extracted.get("average_account_size") or {}).get("acv_dollars")
            acv_num = _parse_numeric(acv_raw)
            acv_doc = (extracted.get("average_account_size") or {}).get("source_doc", "")
            if acv_num is None:
                self._add_gap("Average account size (ACV) not stated — required for tech services threshold evaluation")
            elif acv_num < 100_000:
                self._add_flag(
                    metric="average_acv_dollars",
                    value=str(acv_raw),
                    threshold="<$100,000 (tech services)",
                    severity="Yellow",
                    note=f"Average ACV of {acv_raw} is below $100K, suggesting an SMB-heavy customer base which may affect margin and support burden. Source: {acv_doc}.",
                    source_doc=acv_doc,
                    confidence="high",
                )
            else:
                self._log_no_flag("average_acv_dollars (tech)", str(acv_raw), "≥$100,000")

        # Revenue type mix — project-heavy flag
        rev_type = extracted.get("revenue_type_mix") or {}
        project_pct_raw = rev_type.get("project_onetime_pct")
        project_pct_num = _parse_numeric(project_pct_raw)
        recurring_pct_raw = rev_type.get("recurring_pct")
        recurring_pct_num = _parse_numeric(recurring_pct_raw)
        revtype_doc = rev_type.get("source_doc", "")

        if apply_tech:
            if project_pct_num is not None and project_pct_num > 50:
                self._add_flag(
                    metric="revenue_type_mix_project_heavy",
                    value=str(project_pct_raw),
                    threshold=">50% project/one-time (tech services)",
                    severity="Yellow",
                    note=(
                        f"Project/one-time revenue represents {project_pct_raw} of total revenue. "
                        f"A predominantly project-based model implies lower revenue visibility and "
                        f"higher re-signing risk. Source: {revtype_doc}."
                    ),
                    source_doc=revtype_doc,
                    confidence="high",
                )
            elif recurring_pct_num is None and project_pct_num is None:
                self._add_gap(
                    "Revenue type split (recurring vs. project) not stated — "
                    "required to assess revenue visibility and durability."
                )
            else:
                self._log_no_flag("revenue_type_mix_project_heavy (tech)", str(project_pct_raw), "≤50%")

        # Contract terms — termination for convenience flag
        contract_terms = extracted.get("contract_terms_summary") or {}
        tfc = contract_terms.get("termination_for_convenience", "unknown")
        coc = contract_terms.get("change_of_control_consent_required", "unknown")
        contract_doc = contract_terms.get("source_doc", "")

        if tfc == "yes":
            self._add_flag(
                metric="termination_for_convenience",
                value="yes",
                threshold="present in material customer contracts",
                severity="Yellow",
                note=(
                    "Material customer contracts include termination-for-convenience provisions. "
                    "Buyer should confirm whether these could be triggered post-close. "
                    f"Source: {contract_doc}."
                ),
                source_doc=contract_doc,
                confidence="medium",
            )
        elif tfc == "unknown":
            self._add_gap(
                "Termination-for-convenience terms not determinable from retrieved documents — "
                "contract review required for material customers."
            )
        else:
            self._log_no_flag("termination_for_convenience", tfc, "not present")

        if coc == "yes":
            self._add_flag(
                metric="change_of_control_consent_required",
                value="yes",
                threshold="CoC consent required by material customers",
                severity="Red",
                note=(
                    "One or more material customer contracts require change-of-control consent. "
                    "This is a deal execution risk that must be resolved before close. "
                    f"Source: {contract_doc}."
                ),
                source_doc=contract_doc,
                confidence="medium",
            )
        elif coc == "unknown":
            self._add_gap(
                "Change-of-control consent terms not determinable — "
                "contract review required for all customers >20% of revenue."
            )
        else:
            self._log_no_flag("change_of_control_consent_required", coc, "not required")

        # Customer health — declining spend flag
        health = extracted.get("customer_health_indicators") or {}
        declining = health.get("declining_spend_customers") or []
        if declining:
            self._add_flag(
                metric="declining_spend_customers",
                value=str(declining),
                threshold="one or more customers with explicitly stated declining spend",
                severity="Yellow",
                note=(
                    f"Data room documents explicitly note declining spend for: {', '.join(declining)}. "
                    "Verify whether this reflects project completion, churn risk, or scope reduction."
                ),
                source_doc=health.get("source_doc", ""),
                confidence="medium",
            )

        # Government payor concentration (healthcare)
        if apply_healthcare:
            govt_categories = {"medicare", "medicaid", "va", "managed care"}
            govt_pct = 0.0
            govt_found = False
            for pm in payor_mix:
                cat = (pm.get("payor_category") or "").lower()
                if any(g in cat for g in govt_categories):
                    num = _parse_numeric(pm.get("pct_of_revenue"))
                    if num is not None:
                        govt_pct += num
                        govt_found = True
            if not govt_found and apply_healthcare:
                self._add_gap("Payor mix not stated — required field for healthcare overlay; request from management")
            elif govt_found:
                if govt_pct > 50:
                    self._add_flag(
                        metric="government_payor_concentration",
                        value=f"{round(govt_pct, 1)}%",
                        threshold=">50% government payor (healthcare services)",
                        severity="Yellow",
                        note=f"Government payor concentration (Medicare/Medicaid/VA/Managed Care) is {round(govt_pct, 1)}%, above 50%. Reimbursement rate risk and regulatory exposure should be assessed.",
                        source_doc="payor_mix",
                        confidence="high",
                    )
                else:
                    self._log_no_flag("government_payor_concentration (healthcare)", f"{round(govt_pct, 1)}%", "≤50%")

        # Contract trigger gaps
        for trigger in (extracted.get("contract_trigger_list") or []):
            status = (trigger.get("contract_found_in_vdr") or "").lower()
            if status in ("false", "unknown"):
                self._add_gap(
                    f"Contract for {trigger.get('customer_name')} ({trigger.get('revenue_pct')}% of revenue) "
                    "not found in VDR — high-priority information request"
                )

    # ------------------------------------------------------------------
    # Main run method
    # ------------------------------------------------------------------

    def run(self, company_name: str, spark, llm_endpoint: str, catalog: str) -> dict:
        self._reset_state()
        self._company_name = company_name
        self._catalog = catalog
        print(f"  Running 6 tools ...")

        tr1 = self._tool_retrieve_customer_concentration(spark)
        tr2 = self._tool_retrieve_retention_metrics(spark)
        tr3 = self._tool_retrieve_customer_tenure(spark)
        tr4 = self._tool_retrieve_payor_mix(spark)
        tr5 = self._tool_retrieve_account_size(spark)
        tr6 = self._tool_load_company_profile(company_name, spark)

        print("  Running 4 additional retrieval tools (cohort, health, contracts, revenue type) ...")
        tr_cohort    = self._tool_retrieve_cohort_data(spark)
        tr_health    = self._tool_retrieve_customer_health(spark)
        tr_contracts = self._tool_retrieve_contract_terms(spark)
        tr_revtype   = self._tool_retrieve_revenue_type_and_renewals(spark)

        seen_texts: set[str] = set()
        all_chunks = []
        for tr in (tr1, tr2, tr3, tr4, tr5, tr_cohort, tr_health, tr_contracts, tr_revtype):
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
        overlay = profile_dict.get("industry_overlay") if profile_dict else None

        print("  Calling LLM for extraction ...")
        user_prompt = _USER_PROMPT_TEMPLATE.format(
            company_profile_json=company_profile_json,
            combined_chunk_text=combined_chunk_text,
        )
        raw_response = self._call_llm(_SYSTEM_PROMPT, user_prompt, llm_endpoint)
        extracted = self._parse_json_response(raw_response)

        llm_step = len(self._trace) + 1
        self._trace.append({
            "step":       llm_step,
            "tool":       "llm_extraction",
            "input":      f"combined context: {len(all_chunks)} deduplicated chunks",
            "output":     f"Extracted {len(extracted.get('top_customers') or [])} customers, retention={extracted.get('retention', {}).get('nrr_pct')}",
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

        # Enforce contract trigger list in Python
        trigger_list = self._build_contract_trigger_list(extracted)

        print("  Applying customer quality thresholds ...")
        self._apply_customer_flags(extracted, overlay)

        return {
            "company_name":                company_name,
            "executive_summary":           extracted.get("executive_summary"),
            "top_customers_json":          json.dumps(extracted.get("top_customers") or []),
            "concentration_summary_json":  json.dumps(extracted.get("concentration_summary") or {}),
            "retention_json":              json.dumps(extracted.get("retention") or {}),
            "customer_tenure_json":        json.dumps(extracted.get("customer_tenure") or {}),
            "average_account_size_json":   json.dumps(extracted.get("average_account_size") or {}),
            "payor_mix_json":                  json.dumps(extracted.get("payor_mix") or []),
            "cohort_analysis_json":            json.dumps(extracted.get("cohort_analysis") or {}),
            "customer_health_indicators_json": json.dumps(extracted.get("customer_health_indicators") or {}),
            "contract_terms_summary_json":     json.dumps(extracted.get("contract_terms_summary") or {}),
            "revenue_type_mix_json":           json.dumps(extracted.get("revenue_type_mix") or {}),
            "renewal_patterns_json":           json.dumps(extracted.get("renewal_patterns") or {}),
            "contract_trigger_list":           [json.dumps(t) for t in trigger_list],
            "flags":                       self._flags_as_dicts(),
            "discrepancies_json":          json.dumps(extracted.get("discrepancies") or []),
            "data_room_gaps":              list(self._data_room_gaps),
            "citations":                   json.dumps(self._citations_as_dicts()),
            "reasoning_trace":             list(self._trace),
            "created_at":                  datetime.now(timezone.utc).isoformat(),
        }


# ---------------------------------------------------------------------------
# Stakeholder YAML report
# ---------------------------------------------------------------------------

def _write_stakeholder_report(result: dict, catalog: str, spark) -> str:
    """Write a clean, human-readable YAML report to a UC Volume.

    Saves to /Volumes/{catalog}/analysis/reports/{company_name}/
    customer_quality_report.yaml (or .json if PyYAML is unavailable).
    Returns the full volume path of the written file.
    """
    company_name = result["company_name"]

    # ── Parse JSON blobs back to Python objects for clean rendering ────
    top_customers        = json.loads(result.get("top_customers_json")         or "[]")
    concentration        = json.loads(result.get("concentration_summary_json") or "{}")
    retention            = json.loads(result.get("retention_json")             or "{}")
    customer_tenure      = json.loads(result.get("customer_tenure_json")       or "{}")
    average_account_size = json.loads(result.get("average_account_size_json")  or "{}")
    payor_mix            = json.loads(result.get("payor_mix_json")             or "[]")
    cohort_analysis      = json.loads(result.get("cohort_analysis_json")            or "{}")
    customer_health      = json.loads(result.get("customer_health_indicators_json") or "{}")
    contract_terms       = json.loads(result.get("contract_terms_summary_json")     or "{}")
    revenue_type_mix     = json.loads(result.get("revenue_type_mix_json")           or "{}")
    renewal_patterns     = json.loads(result.get("renewal_patterns_json")           or "{}")
    contract_triggers_raw = result.get("contract_trigger_list") or []
    contract_trigger_list = [
        json.loads(t) if isinstance(t, str) else t
        for t in contract_triggers_raw
    ]
    citations            = json.loads(result.get("citations")                  or "[]")

    # ── Build the curated report dict ──────────────────────────────────
    report = {
        "report": {
            "agent":        "customer_quality",
            "company":      company_name,
            "generated_at": result.get("created_at", ""),
        },
        "executive_summary":    result.get("executive_summary"),
        "top_customers":        top_customers,
        "concentration_summary": concentration,
        "retention":            retention,
        "customer_tenure":      customer_tenure,
        "average_account_size": average_account_size,
        "payor_mix":            payor_mix,
        "contract_trigger_list": contract_trigger_list,
        "flags":                result.get("flags") or [],
        "data_room_gaps":       result.get("data_room_gaps") or [],
        "citations":            citations,
    }

    if cohort_analysis:
        report["cohort_analysis"] = cohort_analysis
    if customer_health:
        report["customer_health"] = customer_health
    if contract_terms:
        report["contract_terms"] = contract_terms
    if revenue_type_mix:
        report["revenue_type_mix"] = revenue_type_mix
    if renewal_patterns:
        report["renewal_patterns"] = renewal_patterns

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

    file_path = f"{dir_path}/customer_quality_report.{ext}"
    with open(file_path, "w", encoding="utf-8") as fh:
        fh.write(content)

    return file_path


# ---------------------------------------------------------------------------
# Markdown assessment report
# ---------------------------------------------------------------------------

def generate_customer_quality_assessment(
    result: dict,
    spark,
    llm_endpoint: str,
    catalog: str = "uc13",
    write_to_volume: bool = True,
) -> str:
    """Generate a human-readable markdown Customer Quality assessment from agent output.

    Combines deterministic table construction (concentration, retention, revenue type,
    contract terms, customer health, cohort summary) with a single LLM call that writes
    7-section narrative. Mirrors the pattern in generate_financial_assessment() and
    generate_business_model_assessment().

    Args:
        result:          Output dict from CustomerQualityAgent.run() or main().
        spark:           Active SparkSession (needed only when write_to_volume=True).
        llm_endpoint:    Databricks model-serving endpoint name.
        catalog:         UC catalog for volume write (default 'uc13').
        write_to_volume: If True, writes the markdown to the reports volume.

    Returns:
        Markdown string.
    """
    # ── Parse all JSON blobs ───────────────────────────────────────────────
    company_name    = result.get("company_name", "Unknown")
    generated_at    = result.get("created_at", "")
    overlay         = result.get("industry_overlay_used", "")
    exec_summary    = result.get("executive_summary") or ""

    top_customers   = json.loads(result.get("top_customers_json")               or "[]")
    concentration   = json.loads(result.get("concentration_summary_json")       or "{}")
    retention       = json.loads(result.get("retention_json")                   or "{}")
    customer_tenure = json.loads(result.get("customer_tenure_json")             or "{}")
    average_account = json.loads(result.get("average_account_size_json")        or "{}")
    payor_mix       = json.loads(result.get("payor_mix_json")                   or "[]")
    cohort          = json.loads(result.get("cohort_analysis_json")             or "{}")
    health          = json.loads(result.get("customer_health_indicators_json")  or "{}")
    contract_terms  = json.loads(result.get("contract_terms_summary_json")      or "{}")
    revenue_type    = json.loads(result.get("revenue_type_mix_json")            or "{}")
    renewal         = json.loads(result.get("renewal_patterns_json")            or "{}")
    _flags_raw      = result.get("flags") or []
    flags           = json.loads(_flags_raw) if isinstance(_flags_raw, str) else _flags_raw
    data_room_gaps  = result.get("data_room_gaps") or []
    discrepancies   = json.loads(result.get("discrepancies_json")               or "[]")
    citations       = json.loads(result.get("citations")                        or "[]")

    def _d(val) -> str:
        """Return '—' for any falsy value, else str(val)."""
        return str(val) if val not in (None, "", [], {}) else "—"

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 1 — Deterministic table construction
    # ══════════════════════════════════════════════════════════════════════

    # ── TABLE 1 — Customer Concentration ──────────────────────────────────
    sev_emoji = {"Red": "🔴", "Yellow": "🟡", "Green": "🟢"}
    overlay_lower = (overlay or "").lower()
    is_healthcare = "healthcare" in overlay_lower

    tc_lines = [
        "| Rank | Customer | Rev % (Yr1) | Rev % (Yr2) | Rev % (Yr3) | Rev $ | Tenure (yrs) | Contract | GM % | Payment | Flag |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for c in top_customers[:10]:
        rank         = _d(c.get("rank"))
        name         = (_d(c.get("customer_name")))[:35]
        pct_yr1      = _d(c.get("revenue_pct_yr1"))
        pct_yr2      = _d(c.get("revenue_pct_yr2"))
        pct_yr3      = _d(c.get("revenue_pct_yr3"))
        rev_dollars  = _fmt_dollars(c.get("revenue_dollars")) if c.get("revenue_dollars") else "—"
        tenure       = _d(c.get("years_as_customer"))
        contract     = _d(c.get("contract_status"))
        gm_pct       = _d(c.get("gm_pct"))
        payment      = _d(c.get("payment_behavior"))

        num = _parse_numeric(pct_yr1)
        threshold = 20 if is_healthcare else 25
        mid_lo    = 15
        if num is not None and num > threshold:
            flag_cell = "🔴"
        elif num is not None and num >= mid_lo:
            flag_cell = "🟡"
        else:
            flag_cell = ""

        tc_lines.append(
            f"| {rank} | {name} | {pct_yr1} | {pct_yr2} | {pct_yr3} | "
            f"{rev_dollars} | {tenure} | {contract} | {gm_pct} | {payment} | {flag_cell} |"
        )

    tbl_concentration = "\n".join(tc_lines) if top_customers else "_No top-customer data extracted._"

    # ── TABLE 2 — Concentration Summary ───────────────────────────────────
    conc_src = concentration.get("source_doc") or "—"
    conc_caption = f"> Customer revenue concentration summary. Source: {conc_src}.\n"
    conc_lines = [
        "| Top 1 % | Top 3 % | Top 5 % | Top 10 % |",
        "|---|---|---|---|",
        f"| {_d(concentration.get('top1_pct'))} | {_d(concentration.get('top3_pct'))} | "
        f"{_d(concentration.get('top5_pct'))} | {_d(concentration.get('top10_pct'))} |",
    ]
    tbl_conc_summary = conc_caption + "\n".join(conc_lines) if concentration else ""

    # ── TABLE 3 — Retention Metrics (key-value block) ─────────────────────
    nrr_pct   = _d(retention.get("nrr_pct"))
    nrr_per   = _d(retention.get("nrr_period"))
    nrr_expl  = _d(retention.get("nrr_methodology_explained"))
    grr_pct   = _d(retention.get("grr_pct"))
    grr_per   = _d(retention.get("grr_period"))
    logo_churn = _d(retention.get("logo_churn_rate_annual_pct"))
    ret_src   = _d(retention.get("source_doc"))
    ret_loc   = _d(retention.get("source_location"))

    ret_lines = [
        f"- **NRR:** {nrr_pct} ({nrr_per}) — methodology explained: {nrr_expl}",
        f"- **GRR:** {grr_pct} ({grr_per})",
        f"- **Logo Churn (annual):** {logo_churn}",
        f"- **Source:** {ret_src} — {ret_loc}",
    ]
    nrr_num = _parse_numeric(nrr_pct)
    grr_num = _parse_numeric(grr_pct)
    if nrr_num is not None and grr_num is not None and nrr_num < grr_num:
        ret_lines.append(
            "\n⚠ **NRR stated below GRR — possible metric error, flagged for QoE review.**"
        )
    tbl_retention = "\n".join(ret_lines)

    # ── TABLE 4 — Revenue Type Mix (key-value block) ───────────────────────
    rev_all_null = all(
        revenue_type.get(k) is None
        for k in ("recurring_pct", "project_onetime_pct", "retainer_pct")
    )
    if rev_all_null or not revenue_type:
        tbl_revenue_type = "_Revenue type split not stated in data room._"
    else:
        rt_lines = [
            f"- **Recurring:** {_d(revenue_type.get('recurring_pct'))}",
            f"- **Project / One-time:** {_d(revenue_type.get('project_onetime_pct'))}",
            f"- **Retainer / MSA:** {_d(revenue_type.get('retainer_pct'))}",
            f"- **Methodology:** {_d(revenue_type.get('methodology_note'))}",
            f"- **Source:** {_d(revenue_type.get('source_doc'))}",
        ]
        tbl_revenue_type = "\n".join(rt_lines)

    # ── TABLE 5 — Contract Terms Summary (key-value block) ────────────────
    ct_src = contract_terms.get("source_doc")
    if not ct_src and not contract_terms:
        tbl_contract_terms = "_No contract documents in retrieved context — terms unknown._"
    else:
        ct_lines = [
            f"- **Termination for convenience:** {_d(contract_terms.get('termination_for_convenience'))}",
            f"- **Change-of-control consent:** {_d(contract_terms.get('change_of_control_consent_required'))}",
            f"- **Pricing escalators:** {_d(contract_terms.get('pricing_escalators'))}",
            f"- **Exclusivity clauses:** {_d(contract_terms.get('exclusivity_clauses'))}",
            f"- **Auto-renewal:** {_d(contract_terms.get('auto_renewal'))}",
            f"- **Typical term:** {_d(contract_terms.get('typical_term_years'))} years",
            f"- **Source:** {_d(ct_src)} — {_d(contract_terms.get('source_location'))}",
            f"- **Note:** {_d(contract_terms.get('note'))}",
        ]
        if not ct_src:
            ct_lines.append("\n_No contract documents in retrieved context — terms unknown._")
        tbl_contract_terms = "\n".join(ct_lines)

    # ── TABLE 6 — Customer Health Indicators (key-value block) ────────────
    declining = health.get("declining_spend_customers") or []
    declining_str = ", ".join(declining) if declining else "None stated"
    h_lines = [
        f"- **Utilization:** {_d(health.get('utilization_note'))}",
        f"- **Complaints / NPS:** {_d(health.get('complaints_note'))}",
        f"- **Late payment / AR trend:** {_d(health.get('late_payment_note'))}",
        f"- **Declining spend customers:** {declining_str}",
        f"- **Discounts / rebates:** {_d(health.get('discounts_rebates_note'))}",
        f"- **Source:** {_d(health.get('source_doc'))}",
    ]
    tbl_health = "\n".join(h_lines)

    # ── TABLE 7 — Flags (pipe table) ──────────────────────────────────────
    flag_severity_order = {"Red": 0, "Yellow": 1, "Green": 2}
    flags_sorted = sorted(flags, key=lambda f: flag_severity_order.get(f.get("severity", ""), 3))
    if flags_sorted:
        fl_lines = [
            "| Severity | Metric | Value | Threshold | Note | Source |",
            "|---|---|---|---|---|---|",
        ]
        for f in flags_sorted:
            emoji   = sev_emoji.get(f.get("severity", ""), "⚪")
            metric  = (f.get("metric") or "")
            val     = (f.get("value") or "")[:60]
            thresh  = (f.get("threshold") or "")[:50]
            note    = (f.get("note") or "")[:90]
            src     = (f.get("source_doc") or "—")[:35]
            fl_lines.append(f"| {emoji} {f.get('severity','')} | {metric} | {val} | {thresh} | {note} | {src} |")
        tbl_flags = "\n".join(fl_lines)
    else:
        tbl_flags = "_No flags raised._"

    # ── TABLE 8 — Cohort Summary (conditional) ────────────────────────────
    cohort_avail = cohort.get("cohorts_available")
    cohort_is_present = str(cohort_avail).lower() == "true" or cohort_avail is True
    if cohort_is_present:
        vintage_years = cohort.get("cohort_vintage_years") or []
        vintage_str   = ", ".join(str(y) for y in vintage_years) if vintage_years else "—"
        coh_lines = [
            f"- **Vintage years available:** {vintage_str}",
            f"- **Performance note:** {_d(cohort.get('cohort_summary_note'))}",
            f"- **Source:** {_d(cohort.get('source_doc'))} — {_d(cohort.get('source_location'))}",
        ]
        tbl_cohort = "\n".join(coh_lines)
    else:
        tbl_cohort = ""

    # ── TABLE 9 — Data Room Gaps ───────────────────────────────────────────
    if data_room_gaps:
        tbl_gaps = "\n".join(f"- {g}" for g in data_room_gaps)
    else:
        tbl_gaps = "_None identified._"

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 2 — Single LLM narrative call
    # ══════════════════════════════════════════════════════════════════════
    _flags_summary = "\n".join(
        f"  {f.get('severity','')} {f.get('metric','')}: {f.get('value','')} vs {f.get('threshold','')}"
        for f in flags_sorted
    ) or "  None."

    _CQA_CONTEXT = f"""\
COMPANY: {company_name}
INDUSTRY OVERLAY: {overlay or 'not stated'}

CUSTOMER CONCENTRATION (top customers):
{tbl_concentration}

CONCENTRATION SUMMARY:
Top 1%={_d(concentration.get('top1_pct'))}  Top 3%={_d(concentration.get('top3_pct'))}  \
Top 5%={_d(concentration.get('top5_pct'))}  Top 10%={_d(concentration.get('top10_pct'))}

RETENTION METRICS:
{tbl_retention}

REVENUE TYPE MIX:
{tbl_revenue_type}

CONTRACT TERMS:
{tbl_contract_terms}

CUSTOMER HEALTH:
{tbl_health}

COHORT DYNAMICS:
{tbl_cohort if tbl_cohort else 'Not available — no cohort schedule in data room.'}

INVESTMENT FLAGS:
{_flags_summary}

DATA ROOM GAPS: {len(data_room_gaps)} gaps — see report
"""

    _ASSESS_SYS = """\
You are a senior PE investment analyst writing the Customer Quality section of an
internal diligence memo. Use the structured data provided to answer 7 specific
questions about customer concentration, retention quality, revenue durability,
contract risk, customer health, and cohort dynamics.

Rules:
1. Write only what the data supports. Do not invent facts.
2. If a section has no data, write one sentence stating what is missing and why
   it matters for underwriting.
3. Use concrete details from the tables (names, percentages, contract terms).
4. Use PE language: "contractually uncommitted", "project-driven concentration",
   "churn pressure", "NRR compression", "re-signing risk", "payor-dependent",
   "vintage erosion", "account-level margin dilution".
5. No deal verdicts. Flag as "warrants scrutiny" or "requires confirmation" — never
   "deal-breaker" or "acceptable risk".
6. Return pure markdown only — no preamble, no code fences.
7. Structure with exactly these 7 H3 headers:
   ### 1. Concentration Risk
   ### 2. Retention Quality (NRR / GRR / Logo Churn)
   ### 3. Revenue Durability (Recurring vs. Project Mix)
   ### 4. Contract Risk (Terms, CoC, Termination)
   ### 5. Customer Health Indicators
   ### 6. Cohort Dynamics and Vintage Performance
   ### 7. Key Diligence Questions for Management
8. Sections 1–6: MAX 2 bullet points (≤30 words each) + one **Analyst take:**
   sentence (≤20 words). Section 7: numbered list of ≤4 specific questions drawn
   only from the flags and data room gaps shown — do not invent new questions.
9. Be concise. The entire section must fit within a 2-page memo section.
"""

    _ASSESS_USER = f"""\
Use the customer quality data below to answer all 7 assessment questions.
Markdown only.

{_CQA_CONTEXT}
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

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 3 — Assemble final markdown
    # ══════════════════════════════════════════════════════════════════════
    def _extract_section(narrative_text: str, header: str) -> str:
        """Pull the content under a given ### header from the narrative string."""
        pattern = rf"###\s*{re.escape(header)}\s*\n(.*?)(?=\n###|\Z)"
        m = re.search(pattern, narrative_text, re.DOTALL | re.IGNORECASE)
        return m.group(1).strip() if m else ""

    overlay_tag = f"  |  Overlay: {overlay}" if overlay else ""
    md: list[str] = []
    md.append(f"# Customer Quality Assessment — {company_name}")
    md.append(f"_Generated: {generated_at}{overlay_tag}_\n")

    md.append("## Executive Summary\n")
    md.append(exec_summary if exec_summary else "_No executive summary extracted._")
    md.append("")

    # ── Customer Concentration ─────────────────────────────────────────────
    md.append("---\n")
    md.append("## Customer Concentration\n")
    md.append(
        "> Top customers by revenue share (3-year history). GM % and payment behavior\n"
        "> extracted from customer workbook where stated. Flag: 🔴 >25% concentration risk.\n"
    )
    md.append(tbl_concentration)
    md.append("")
    if tbl_conc_summary:
        md.append(tbl_conc_summary)
        md.append("")

    conc_narrative = _extract_section(narrative, "1. Concentration Risk")
    if conc_narrative:
        md.append(conc_narrative)
        md.append("")

    # ── Retention Metrics ─────────────────────────────────────────────────
    md.append("---\n")
    md.append("## Retention Metrics\n")
    md.append(tbl_retention)
    md.append("")

    ret_narrative = _extract_section(narrative, "2. Retention Quality (NRR / GRR / Logo Churn)")
    if ret_narrative:
        md.append(ret_narrative)
        md.append("")

    # ── Revenue Durability ────────────────────────────────────────────────
    md.append("---\n")
    md.append("## Revenue Durability\n")
    md.append(tbl_revenue_type)
    md.append("")

    rev_narrative = _extract_section(narrative, "3. Revenue Durability (Recurring vs. Project Mix)")
    if rev_narrative:
        md.append(rev_narrative)
        md.append("")

    # ── Contract Terms ────────────────────────────────────────────────────
    md.append("---\n")
    md.append("## Contract Terms\n")
    md.append(tbl_contract_terms)
    md.append("")

    ct_narrative = _extract_section(narrative, "4. Contract Risk (Terms, CoC, Termination)")
    if ct_narrative:
        md.append(ct_narrative)
        md.append("")

    # ── Customer Health ───────────────────────────────────────────────────
    md.append("---\n")
    md.append("## Customer Health\n")
    md.append(tbl_health)
    md.append("")

    health_narrative = _extract_section(narrative, "5. Customer Health Indicators")
    if health_narrative:
        md.append(health_narrative)
        md.append("")

    # ── Cohort Dynamics (conditional) ─────────────────────────────────────
    if tbl_cohort:
        md.append("---\n")
        md.append("## Cohort Dynamics\n")
        md.append(tbl_cohort)
        md.append("")

        cohort_narrative = _extract_section(narrative, "6. Cohort Dynamics and Vintage Performance")
        if cohort_narrative:
            md.append(cohort_narrative)
            md.append("")

    # ── Investment Flags ──────────────────────────────────────────────────
    md.append("---\n")
    md.append("## Investment Flags\n")
    md.append(tbl_flags)
    md.append("")

    # ── Key Diligence Questions ────────────────────────────────────────────
    md.append("---\n")
    md.append("## Key Diligence Questions for Management\n")
    kq_narrative = _extract_section(narrative, "7. Key Diligence Questions for Management")
    md.append(kq_narrative if kq_narrative else "_See data room gaps and flags above._")
    md.append("")

    # ── Data Room Gaps ────────────────────────────────────────────────────
    md.append("---\n")
    md.append("## Data Room Gaps\n")
    md.append(tbl_gaps)
    md.append("")

    md.append("---")
    md.append(
        "_Citations available in `customer_quality_report.yaml` "
        f"and `{catalog}.analysis.customer_quality`._"
    )

    final_markdown = "\n".join(md)

    # ── Optional volume write ──────────────────────────────────────────────
    if write_to_volume:
        spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.analysis.reports")
        safe_name = company_name.replace(" ", "_").replace("/", "_")
        dir_path  = f"/Volumes/{catalog}/analysis/reports/{safe_name}"
        os.makedirs(dir_path, exist_ok=True)
        file_path = f"{dir_path}/customer_quality_assessment.md"
        with open(file_path, "w", encoding="utf-8") as fh:
            fh.write(final_markdown)
        print(f"✓ Customer quality assessment → {file_path}")

    return final_markdown


# ---------------------------------------------------------------------------
# Delta table DDL
# ---------------------------------------------------------------------------

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {table} (
    company_name               STRING,
    executive_summary          STRING,
    top_customers_json         STRING,
    concentration_summary_json STRING,
    retention_json             STRING,
    customer_tenure_json       STRING,
    average_account_size_json  STRING,
    payor_mix_json             STRING,
    cohort_analysis_json           STRING,
    customer_health_indicators_json STRING,
    contract_terms_summary_json    STRING,
    revenue_type_mix_json          STRING,
    renewal_patterns_json          STRING,
    contract_trigger_list      ARRAY<STRING>,
    flags                      STRING,
    discrepancies_json         STRING,
    data_room_gaps             ARRAY<STRING>,
    citations                  STRING,
    reasoning_trace            STRING,
    created_at                 TIMESTAMP
) USING DELTA
"""


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


def main(spark=None) -> dict:
    repo_root = find_repo_root()
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    company_name = get_param("sp_company_name")
    catalog      = get_param("catalog",      default="uc13")
    llm_endpoint = get_param("llm_endpoint", default="databricks-meta-llama-3-3-70b-instruct")

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

    print(f"\n=== Customer Quality Agent ({company_name}) ===")

    open_agent_run(
        "cqa",
        company_name=company_name,
        catalog=catalog,
        affected_intents=load_affected_intents("cqa"),
    )
    try:
        agent = CustomerQualityAgent()
        result = agent.run(company_name=company_name, spark=spark, llm_endpoint=llm_endpoint, catalog=catalog)

        table = f"{catalog}.analysis.customer_quality"
        spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.analysis")

        _EXPECTED_COLS = {
            "company_name", "executive_summary",
            "top_customers_json", "concentration_summary_json", "retention_json",
            "customer_tenure_json", "average_account_size_json", "payor_mix_json",
            "cohort_analysis_json", "customer_health_indicators_json",
            "contract_terms_summary_json", "revenue_type_mix_json", "renewal_patterns_json",
            "contract_trigger_list", "flags", "discrepancies_json",
            "data_room_gaps", "citations", "reasoning_trace", "created_at",
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
            StructType, StructField, StringType, ArrayType, TimestampType,
        )

        schema = StructType([
            StructField("company_name",               StringType(),  True),
            StructField("executive_summary",           StringType(),  True),
            StructField("top_customers_json",          StringType(),  True),
            StructField("concentration_summary_json",  StringType(),  True),
            StructField("retention_json",              StringType(),  True),
            StructField("customer_tenure_json",        StringType(),  True),
            StructField("average_account_size_json",   StringType(),  True),
            StructField("payor_mix_json",                     StringType(),  True),
            StructField("cohort_analysis_json",               StringType(),  True),
            StructField("customer_health_indicators_json",    StringType(),  True),
            StructField("contract_terms_summary_json",        StringType(),  True),
            StructField("revenue_type_mix_json",              StringType(),  True),
            StructField("renewal_patterns_json",              StringType(),  True),
            StructField("contract_trigger_list",              ArrayType(StringType()), True),
            StructField("flags",                       StringType(),  True),
            StructField("discrepancies_json",          StringType(),  True),
            StructField("data_room_gaps",              ArrayType(StringType()), True),
            StructField("citations",                   StringType(),  True),
            StructField("reasoning_trace",             StringType(),  True),
            StructField("created_at",                  TimestampType(), True),
        ])

        row_data = {
            "company_name":               result["company_name"],
            "executive_summary":          result.get("executive_summary"),
            "top_customers_json":         result.get("top_customers_json"),
            "concentration_summary_json": result.get("concentration_summary_json"),
            "retention_json":             result.get("retention_json"),
            "customer_tenure_json":       result.get("customer_tenure_json"),
            "average_account_size_json":  result.get("average_account_size_json"),
            "payor_mix_json":                     result.get("payor_mix_json"),
            "cohort_analysis_json":               result.get("cohort_analysis_json"),
            "customer_health_indicators_json":    result.get("customer_health_indicators_json"),
            "contract_terms_summary_json":        result.get("contract_terms_summary_json"),
            "revenue_type_mix_json":              result.get("revenue_type_mix_json"),
            "renewal_patterns_json":              result.get("renewal_patterns_json"),
            "contract_trigger_list":              result.get("contract_trigger_list") or [],
            "flags":                      json.dumps(result.get("flags") or []),
            "discrepancies_json":         result.get("discrepancies_json"),
            "data_room_gaps":             result.get("data_room_gaps") or [],
            "citations":                  result.get("citations"),
            "reasoning_trace":            json.dumps(result.get("reasoning_trace") or []),
            "created_at":                 datetime.now(timezone.utc),
        }

        df = spark.createDataFrame([Row(**row_data)], schema=schema)
        df.write.format("delta").mode("append").option("mergeSchema", "true").saveAsTable(table)

        print(f"\n✓ Saved customer quality output → {table}")

        report_path = _write_stakeholder_report(result, catalog, spark)
        result["report_path"] = report_path
        print(f"✓ Stakeholder report → {report_path}")

        # ── Export markdown assessment report ──────────────────────────
        generate_customer_quality_assessment(
            result=result,
            spark=spark,
            llm_endpoint=llm_endpoint,
            catalog=catalog,
            write_to_volume=True,
        )
        print("✓ Customer quality assessment → written to volume")

        return result
    finally:
        close_agent_run()


# Golden checklist row vocabulary — spec §6.1 / eval harness M1-T1 (Decision B: item_id + display_name only).
GOLDEN_CHECKLIST_COVERAGE: list[dict] = [
    {
        "item_id": "concentration",
        "display_name": "Customer concentration extraction",
    },
    {
        "item_id": "retention",
        "display_name": "Retention metrics extraction",
    },
    {
        "item_id": "customer_tenure",
        "display_name": "Customer tenure extraction",
    },
    {
        "item_id": "payor_mix",
        "display_name": "Payor mix extraction",
    },
    {
        "item_id": "discrepancies_json",
        "display_name": "Discrepancies correctly reported",
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
