"""
kpi_agent.py — Phase 3: KPI Workstream Agent.

Extracts the overlay-specific KPI set from documents tagged KPI_OPS. The KPI set
is entirely different between tech services, healthcare, SaaS, industrial, and
consumer overlays. The industry overlay from the Company Profiler is a required
input; if absent, extract all KPI sets and note reduced confidence.

A KPI that is expected for the confirmed overlay but absent from the documents is
itself a flag — returned as a missing_kpi and formatted as a management question.

Phase 3 outputs:
  - Table uc13.analysis.kpi

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


# ---------------------------------------------------------------------------
# LLM prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a senior PE investment analyst extracting structured KPI and operational
metrics from due diligence documents. Rules:
1. Extract ONLY what is explicitly stated in the provided context.
2. Do NOT infer, compute, assume, or hallucinate any value.
3. If a value is absent from the context, return null for that field.
4. Every extracted value must have a citation: document name, location
   (page number or section title), and a quote of ≤30 words.
5. Return ONLY valid JSON with no preamble and no markdown fences.
6. The industry overlay determines which KPI set to prioritize. Tech services:
   focus on utilization, bill rates, contractor %, ACV, backlog/pipeline, revenue
   per FTE, attrition. Healthcare: focus on census, payor mix, caregiver headcount,
   turnover, utilization/productivity, compliance incidents, referral source breakdown,
   AR aging by payor. If overlay is null or unknown: extract all KPI sets and note
   reduced confidence in extraction_notes.
7. A KPI that the agent expects to see for the confirmed overlay but cannot find in
   the documents is itself a finding. Return it in missing_kpis with a specific
   management question.
8. Delivery model (tech services): extract contractor % of total workforce and any
   mention of delivery geography concentration (e.g. India-heavy). If contractor %
   is not explicitly stated, return null — do not estimate.
9. Compliance (healthcare): extract any mention of audits, adverse survey findings,
   licensing issues, litigation, credentialing gaps, or billing/coding concerns.
   Any history qualifies — not just currently open matters.
10. Bill rates by role (tech services): if a rate card, staffing schedule, or
    utilization/billing report lists rates by role title (e.g. "Senior Consultant:
    $225/hr"), extract each row into bill_rates_by_role. If only a blended average
    is stated, set average_bill_rate_dollars and leave bill_rates_by_role empty.
    Never compute or average across stated values.
11. Utilization by segment (tech services): if utilization data is broken out by
    team, role, geography, or vertical, extract each breakout into
    utilization_by_segment. If only an overall rate is stated, set
    utilization_rate_pct and leave utilization_by_segment empty.
12. Bench size and cost (tech services): look for "bench", "unassigned", "available
    capacity", "overhead headcount", or "non-billable staff" in staffing schedules
    and financial reports. Extract headcount and cost only if explicitly stated.
    Do not estimate from total headcount minus billed headcount.
13. Gross margin by segment (tech services): if a financial model, project P&L, or
    customer margin schedule shows margin by project, client, delivery team, or
    vertical, extract each row into gross_margin_by_segment. Do not compute margins
    not explicitly shown.
14. Sales cycle and delivery capacity (tech services): extract average_sales_cycle_days
    from any CRM summary, management deck, or GTM document that states a typical sales
    cycle length. Extract delivery_capacity_note and pipeline_vs_capacity_note from
    capacity planning documents or management commentary comparing pipeline to
    available delivery bandwidth.
15. Wage pressure, labor availability, denials, collections (healthcare): scan
    management commentary, board updates, and financial notes for these topics.
    Extract verbatim descriptions — do not synthesize or infer trends not stated.
    For denials and collections, look in AR aging reports, revenue cycle summaries,
    and payor reconciliation schedules.\
"""

_USER_PROMPT_TEMPLATE = """\
COMPANY PROFILE (from Phase 2 output):
{company_profile_json}

RETRIEVED DOCUMENT CONTEXT:
{combined_chunk_text}

Extract KPI fields and return this exact JSON structure:
{{
  "overlay_confirmed": "<tech_services | healthcare_services | b2b_saas | industrial | consumer | unknown>",
  "tech_services_kpis": {{
    "utilization_rate_pct": "<% as stated or null>",
    "utilization_period": "<period or null>",
    "average_bill_rate_dollars": "<$ as stated or null>",
    "contractor_pct_of_workforce": "<% as stated or null>",
    "delivery_geography_note": "<description of geography concentration as stated or null>",
    "average_acv_dollars": "<$ as stated or null>",
    "bookings_stated": "<$ or description as stated or null>",
    "backlog_months_of_revenue": "<months as stated or null>",
    "pipeline_coverage_months": "<months as stated or null>",
    "revenue_per_fte_dollars": "<$ as stated or null>",
    "attrition_rate_pct": "<% as stated or null>",
    "bill_rates_by_role": [
      {{
        "role": "<role title as stated or null>",
        "bill_rate_dollars": "<$/hr or $/day as stated or null>",
        "basis": "<hourly | daily | project | null>",
        "source_doc": "<filename>"
      }}
    ],
    "utilization_by_segment": [
      {{
        "segment": "<role | team | geography | vertical — as stated>",
        "segment_label": "<label as stated, e.g. 'Senior Consultants', 'India team'>",
        "utilization_pct": "<% as stated or null>",
        "period": "<period as stated or null>",
        "source_doc": "<filename>"
      }}
    ],
    "bench_size": "<headcount as stated or null>",
    "bench_cost_dollars": "<$ annual as stated or null>",
    "bench_cost_pct_revenue": "<% as stated or null>",
    "bench_note": "<any description of bench management or utilization of bench, or null>",
    "gross_margin_by_segment": [
      {{
        "segment_type": "<project | client | delivery_team | vertical>",
        "segment_label": "<label as stated>",
        "gm_pct": "<% as stated or null>",
        "gm_dollars": "<$ as stated or null>",
        "source_doc": "<filename>"
      }}
    ],
    "average_sales_cycle_days": "<days as stated or null>",
    "average_sales_cycle_note": "<description of sales cycle stages or range, or null>",
    "delivery_capacity_note": "<stated headcount or FTE capacity available for new work, or null>",
    "pipeline_vs_capacity_note": "<any stated comparison of pipeline to delivery capacity, or null>",
    "source_doc": "<filename>"
  }},
  "healthcare_kpis": {{
    "census_or_patient_panel": "<count or description as stated or null>",
    "caregiver_headcount": "<count as stated or null>",
    "clinician_headcount": "<count as stated or null>",
    "turnover_rate_pct": "<% as stated or null>",
    "turnover_period": "<period or null>",
    "utilization_or_productivity_note": "<description as stated or null>",
    "referral_source_breakdown": "<description as stated or null>",
    "ar_aging_by_payor_note": "<description as stated or null>",
    "wage_pressure_note": "<any stated description of wage inflation, labor cost increases, or minimum wage / market rate pressures, or null>",
    "labor_availability_note": "<any stated description of difficulty recruiting, labor market tightness, or geographic staffing constraints, or null>",
    "revenue_per_client_dollars": "<$ per client/patient as stated or null>",
    "revenue_per_visit_dollars": "<$ per visit as stated or null>",
    "revenue_per_hour_dollars": "<$ per hour of service as stated or null>",
    "revenue_per_unit_note": "<which unit is relevant (client / visit / hour) and any trend, or null>",
    "denials_rate_pct": "<% of claims denied as stated or null>",
    "denials_note": "<description of denial trends, primary denial reasons, or appeals success, or null>",
    "collections_rate_pct": "<% collected of amounts billed as stated or null>",
    "collections_note": "<description of collections trends or write-offs as stated, or null>",
    "compliance_incidents": [
      {{
        "type": "<audit | adverse_survey | licensing | litigation | credentialing | billing_coding>",
        "description": "<as stated>",
        "status": "<open | closed | unknown>",
        "source_doc": "<filename>",
        "source_location": "<page or section>"
      }}
    ],
    "credentialing_status_note": "<as stated or null>",
    "site_level_visibility": "<true | false | partial>",
    "site_level_visibility_note": "<description as stated or null>",
    "source_doc": "<filename>"
  }},
  "saas_kpis": {{
    "nrr_pct": "<as stated or null>",
    "grr_pct": "<as stated or null>",
    "logo_churn_pct": "<as stated or null>",
    "cac_payback_months": "<as stated or null>",
    "rule_of_40_stated": "<as stated or null>",
    "arr_per_fte_dollars": "<$ as stated or null>",
    "magic_number_stated": "<as stated or null>",
    "source_doc": "<filename>"
  }},
  "industrial_kpis": {{
    "backlog_months": "<as stated or null>",
    "capacity_utilization_pct": "<as stated or null>",
    "on_time_delivery_pct": "<as stated or null>",
    "aftermarket_revenue_pct": "<as stated or null>",
    "inventory_turns": "<as stated or null>",
    "capex_pct_revenue": "<as stated or null>",
    "source_doc": "<filename>"
  }},
  "consumer_kpis": {{
    "repeat_rate_12mo_pct": "<as stated or null>",
    "contribution_margin_pct": "<as stated or null>",
    "return_rate_pct": "<as stated or null>",
    "ltv_cac_ratio": "<as stated or null>",
    "blended_cac_trend_note": "<as stated or null>",
    "channel_mix_note": "<as stated or null>",
    "platform_concentration_note": "<as stated or null>",
    "source_doc": "<filename>"
  }},
  "missing_kpis": [
    {{
      "kpi_name": "<name>",
      "overlay": "<tech_services | healthcare_services | etc.>",
      "why_expected": "<brief explanation per spec>",
      "management_question": "<specific question to ask management>"
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
  "executive_summary": "<2–3 sentence factual description of operational health visible in the KPI data. Note what is present and what is absent. Do not render a verdict.>",
  "extraction_notes": "<overlay uncertainty, missing KPIs, ambiguous data>"
}}\
"""


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

from agents.shared.agent_base import WorkstreamAgent


class KPIAgent(WorkstreamAgent):
    """Phase 3 KPI workstream agent."""

    agent_name = "kpi"

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

    # -----------------------------------------------------------------------
    # Tool methods
    # -----------------------------------------------------------------------

    def _tool_retrieve_kpi_dashboard(self, spark):
        from agents.shared.retrieval import semantic_search
        chunks = semantic_search(
            query="KPI dashboard metrics scorecard utilization revenue per FTE headcount operating",
            spark=spark,
            company_name=self._company_name,
            top_k=12,
            workstream_filter=["KPI_OPS"],
            file_name_filter=["KPI", "Dashboard", "Metrics", "Scorecard", "Operating", "Performance"],
            min_chunk_length=150,
        ).chunks
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_kpi_dashboard",
            input_summary="semantic search: KPI dashboard metrics scorecard utilization revenue per FTE headcount operating",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_retrieve_pipeline_backlog(self, spark):
        from agents.shared.retrieval import semantic_search
        chunks = semantic_search(
            query="pipeline backlog weighted pipeline bookings conversion forecast coverage months",
            spark=spark,
            company_name=self._company_name,
            top_k=8,
            workstream_filter=["KPI_OPS", "FINANCIAL"],
            min_chunk_length=150,
        ).chunks
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_pipeline_backlog",
            input_summary="semantic search: pipeline backlog weighted pipeline bookings conversion forecast coverage months",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_retrieve_delivery_model(self, spark):
        from agents.shared.retrieval import semantic_search
        chunks = semantic_search(
            query="contractor employee utilization bill rate delivery model geography offshore onshore",
            spark=spark,
            company_name=self._company_name,
            top_k=6,
            workstream_filter=["KPI_OPS", "BUSINESS_MODEL"],
            min_chunk_length=150,
        ).chunks
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_delivery_model",
            input_summary="semantic search: contractor employee utilization bill rate delivery model geography offshore onshore",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_retrieve_healthcare_ops(self, spark):
        from agents.shared.retrieval import semantic_search
        chunks = semantic_search(
            query="caregiver clinician turnover attrition census patient headcount referral compliance credentialing",
            spark=spark,
            company_name=self._company_name,
            top_k=8,
            workstream_filter=["KPI_OPS", "FINANCIAL"],
            min_chunk_length=150,
        ).chunks
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_healthcare_ops",
            input_summary="semantic search: caregiver clinician turnover attrition census patient headcount referral compliance credentialing",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_retrieve_headcount_attrition(self, spark):
        from agents.shared.retrieval import semantic_search
        chunks = semantic_search(
            query="headcount full time employees FTE attrition turnover rate hiring plan revenue per employee",
            spark=spark,
            company_name=self._company_name,
            top_k=6,
            workstream_filter=["KPI_OPS", "FINANCIAL"],
            min_chunk_length=150,
        ).chunks
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_headcount_attrition",
            input_summary="semantic search: headcount full time employees FTE attrition turnover rate hiring plan revenue per employee",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_retrieve_bill_rates_and_margins(self, spark):
        from agents.shared.retrieval import semantic_search
        chunks = semantic_search(
            query=(
                "bill rate by role hourly rate rate card blended rate consultant rate "
                "senior manager director rate gross margin by project client delivery team "
                "project P&L margin by vertical margin by customer segment margin schedule"
            ),
            spark=spark,
            company_name=self._company_name,
            top_k=10,
            workstream_filter=["KPI_OPS", "FINANCIAL", "CUSTOMER"],
            file_name_filter=["Rate", "Bill", "Billing", "Margin", "Project", "P&L",
                              "Revenue", "Customer", "KPI", "Dashboard", "Pricing"],
            min_chunk_length=150,
        ).chunks
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_bill_rates_and_margins",
            input_summary="semantic_search: bill rate by role rate card gross margin by project client delivery team (top_k=10)",
            data=chunks,
            output_summary=f"{len(chunks)} chunks from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_retrieve_bench_and_capacity(self, spark):
        from agents.shared.retrieval import semantic_search
        chunks = semantic_search(
            query=(
                "bench size bench cost unassigned headcount non-billable available capacity "
                "delivery capacity sales pipeline coverage capacity planning staffing plan "
                "billable vs non-billable overhead headcount average sales cycle pipeline conversion"
            ),
            spark=spark,
            company_name=self._company_name,
            top_k=8,
            workstream_filter=["KPI_OPS", "BUSINESS_MODEL", "FINANCIAL"],
            file_name_filter=["Bench", "Capacity", "Staffing", "Pipeline", "Workforce",
                              "Headcount", "KPI", "Operations", "GTM", "Sales"],
            min_chunk_length=150,
        ).chunks
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_bench_and_capacity",
            input_summary="semantic_search: bench size cost unassigned capacity delivery capacity vs pipeline sales cycle (top_k=8)",
            data=chunks,
            output_summary=f"{len(chunks)} chunks from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_retrieve_healthcare_revenue_per_unit(self, spark):
        from agents.shared.retrieval import semantic_search
        chunks = semantic_search(
            query=(
                "revenue per client revenue per patient revenue per visit revenue per hour "
                "reimbursement rate per visit billing rate per service "
                "denials rate claim denial appeals collections rate write-offs "
                "revenue cycle management payor collections aging receivables"
            ),
            spark=spark,
            company_name=self._company_name,
            top_k=8,
            workstream_filter=["KPI_OPS", "FINANCIAL", "CUSTOMER"],
            file_name_filter=["Revenue", "Collections", "Denials", "AR", "Aging",
                              "Payor", "Billing", "Claims", "Reimbursement", "KPI"],
            min_chunk_length=150,
        ).chunks
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_healthcare_revenue_per_unit",
            input_summary="semantic_search: revenue per visit/client/hour denials collections AR aging payor (top_k=8)",
            data=chunks,
            output_summary=f"{len(chunks)} chunks from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_retrieve_healthcare_labor_market(self, spark):
        from agents.shared.retrieval import semantic_search
        chunks = semantic_search(
            query=(
                "wage pressure labor cost inflation minimum wage market rate caregiver pay "
                "labor availability recruiting difficulty staffing shortage geographic staffing "
                "compensation increase salary inflation workforce availability talent pipeline "
                "nurse shortage caregiver shortage clinician shortage"
            ),
            spark=spark,
            company_name=self._company_name,
            top_k=8,
            workstream_filter=["KPI_OPS", "BUSINESS_MODEL", "FINANCIAL"],
            file_name_filter=["Workforce", "Recruiting", "Labor", "Staff", "Compensation",
                              "HR", "Operations", "KPI", "Board", "Management"],
            min_chunk_length=150,
        ).chunks
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_healthcare_labor_market",
            input_summary="semantic_search: wage pressure labor availability recruiting difficulty staffing shortage (top_k=8)",
            data=chunks,
            output_summary=f"{len(chunks)} chunks from {len(source_docs)} files",
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
        profile_dict = rows[0].asDict()
        return self._tool_call(
            tool_name="load_company_profile",
            input_summary=f"SQL: company_profile WHERE company_name='{company_name}'",
            data=profile_dict,
            output_summary=f"Company profile loaded (overlay={profile_dict.get('industry_overlay')})",
            confidence="high",
            source_docs=[],
        )

    # -----------------------------------------------------------------------
    # Flag application
    # -----------------------------------------------------------------------

    def _apply_kpi_flags(self, extracted: dict, overlay: Optional[str]):
        overlay_lower = (overlay or "").lower()
        apply_tech       = "tech" in overlay_lower or overlay is None
        apply_healthcare = "healthcare" in overlay_lower or overlay is None

        tech   = extracted.get("tech_services_kpis") or {}
        health = extracted.get("healthcare_kpis") or {}

        # --- Tech flags ---
        if apply_tech:
            # Contractor workforce %
            contr_raw = tech.get("contractor_pct_of_workforce")
            contr_num = _parse_numeric(contr_raw)
            contr_doc = tech.get("source_doc", "")
            if contr_num is None:
                self._add_gap("Contractor % of workforce not stated — required for tech services delivery risk assessment")
            elif contr_num > 50:
                self._add_flag(
                    metric="contractor_pct_of_workforce",
                    value=str(contr_raw),
                    threshold=">50% (tech services)",
                    severity="Yellow",
                    note=f"Contractor workforce concentration of {contr_raw} exceeds 50%. High contractor mix may indicate wage/classification risk and limited bench control. Source: {contr_doc}.",
                    source_doc=contr_doc,
                    confidence="high",
                )
            else:
                self._log_no_flag("contractor_pct_of_workforce (tech)", str(contr_raw), "≤50%")

            # Delivery geography
            geo_note = tech.get("delivery_geography_note")
            if geo_note:
                geo_lower = geo_note.lower()
                if "india" in geo_lower or any(phrase in geo_lower for phrase in ["single geography", "heavily concentrated", "primarily "]):
                    self._add_flag(
                        metric="delivery_geography_concentration",
                        value=geo_note[:100],
                        threshold="Single-geography delivery concentration",
                        severity="Yellow",
                        note=f"Delivery geography concentration noted: '{geo_note[:120]}'. Single-market concentration increases operational and geopolitical risk.",
                        source_doc=contr_doc,
                        confidence="medium",
                    )
                else:
                    self._log_no_flag("delivery_geography_concentration", geo_note[:50], "No single-geography concentration")

            # Average ACV
            acv_raw = tech.get("average_acv_dollars")
            acv_num = _parse_numeric(acv_raw)
            if acv_num is None:
                self._add_gap("Average ACV not stated — required for tech services market segment assessment")
            elif acv_num < 100_000:
                self._add_flag(
                    metric="average_acv_dollars",
                    value=str(acv_raw),
                    threshold="<$100,000 (tech services)",
                    severity="Yellow",
                    note=f"Average ACV of {acv_raw} is below $100K, suggesting an SMB-heavy customer base with potential support burden and margin pressure.",
                    source_doc=contr_doc,
                    confidence="high",
                )
            else:
                self._log_no_flag("average_acv_dollars (tech)", str(acv_raw), "≥$100,000")

            # Utilization rate
            util_raw = tech.get("utilization_rate_pct")
            util_num = _parse_numeric(util_raw)
            util_doc = contr_doc
            if util_num is None:
                self._add_gap("Utilization rate not stated — key margin driver for tech services overlay; request from management")
            elif util_num < 65:
                self._add_flag(
                    metric="utilization_rate_pct",
                    value=str(util_raw),
                    threshold="<65% (tech services — Red)",
                    severity="Red",
                    note=f"Billable utilization of {util_raw} is critically low (threshold <65%). Indicates significant bench overhead and likely margin compression.",
                    source_doc=util_doc,
                    confidence="high",
                )
            elif util_num < 75:
                self._add_flag(
                    metric="utilization_rate_pct",
                    value=str(util_raw),
                    threshold="65–75% (tech services — Yellow)",
                    severity="Yellow",
                    note=f"Billable utilization of {util_raw} is in the caution zone (65–75%). Below 75% indicates potential bench underperformance.",
                    source_doc=util_doc,
                    confidence="high",
                )
            else:
                self._log_no_flag("utilization_rate_pct (tech)", str(util_raw), "≥75% (Green)")

            # Pipeline/backlog coverage
            pipe_raw = tech.get("pipeline_coverage_months")
            back_raw = tech.get("backlog_months_of_revenue")
            pipe_num = _parse_numeric(pipe_raw)
            back_num = _parse_numeric(back_raw)
            coverage_num = None
            coverage_label = None
            if pipe_num is not None and back_num is not None:
                coverage_num = min(pipe_num, back_num)
                coverage_label = f"min(pipeline={pipe_raw}, backlog={back_raw})"
            elif pipe_num is not None:
                coverage_num = pipe_num
                coverage_label = f"pipeline_coverage={pipe_raw}"
            elif back_num is not None:
                coverage_num = back_num
                coverage_label = f"backlog={back_raw}"
            if coverage_num is None:
                self._add_gap("Pipeline and backlog coverage data not stated — required for revenue visibility assessment")
            elif coverage_num < 6:
                self._add_flag(
                    metric="pipeline_backlog_coverage_months",
                    value=coverage_label,
                    threshold="<6 months (tech services)",
                    severity="Yellow",
                    note=f"Coverage of {coverage_label} is below 6 months. Limited forward revenue visibility creates forecast risk.",
                    source_doc=contr_doc,
                    confidence="high",
                )
            else:
                self._log_no_flag("pipeline_backlog_coverage_months (tech)", str(coverage_label), "≥6 months")

            # Bench cost as % of revenue
            bench_cost_pct_raw = tech.get("bench_cost_pct_revenue")
            bench_cost_pct_num = _parse_numeric(bench_cost_pct_raw)
            if bench_cost_pct_num is not None and bench_cost_pct_num > 15:
                self._add_flag(
                    metric="bench_cost_pct_revenue",
                    value=str(bench_cost_pct_raw),
                    threshold=">15% of revenue (tech services)",
                    severity="Yellow",
                    note=(
                        f"Bench cost represents {bench_cost_pct_raw} of revenue. "
                        "Elevated bench cost compresses margins and signals poor capacity planning "
                        "or insufficient pipeline. Source: " + tech.get("source_doc", "") + "."
                    ),
                    source_doc=tech.get("source_doc", ""),
                    confidence="high",
                )
            elif bench_cost_pct_num is None and not tech.get("bench_size") and not tech.get("bench_cost_dollars"):
                self._add_gap(
                    "Bench size and bench cost not stated — required for delivery margin and "
                    "capacity utilization assessment (tech services)."
                )
            else:
                self._log_no_flag("bench_cost_pct_revenue (tech)", str(bench_cost_pct_raw), "≤15%")

            # Gross margin by segment — flag if absent
            gm_segments = tech.get("gross_margin_by_segment") or []
            if not gm_segments:
                self._add_gap(
                    "Gross margin by project / client / delivery team not stated — "
                    "required to identify margin dilution at the account or delivery level."
                )

            # Sales cycle data — flag if absent
            if not tech.get("average_sales_cycle_days") and not tech.get("average_sales_cycle_note"):
                self._add_gap(
                    "Average sales cycle not stated — required for pipeline coverage and "
                    "forecast achievability assessment."
                )

            # Delivery capacity vs. pipeline — flag if absent
            if not tech.get("delivery_capacity_note") and not tech.get("pipeline_vs_capacity_note"):
                self._add_gap(
                    "Delivery capacity vs. sales pipeline not stated — required to assess "
                    "whether the company can execute against its forward pipeline."
                )

        # --- Healthcare flags ---
        if apply_healthcare:
            # Caregiver/staff turnover
            turn_raw = health.get("turnover_rate_pct")
            turn_num = _parse_numeric(turn_raw)
            health_doc = health.get("source_doc", "")
            if turn_num is None:
                self._add_gap("Staff turnover rate not stated — required for healthcare services workforce risk assessment")
            elif turn_num > 30:
                self._add_flag(
                    metric="turnover_rate_pct",
                    value=str(turn_raw),
                    threshold=">30% (healthcare services)",
                    severity="Red",
                    note=f"Caregiver/staff turnover of {turn_raw} exceeds 30%. High turnover drives wage inflation, quality risk, and limits census capacity. Source: {health_doc}.",
                    source_doc=health_doc,
                    confidence="high",
                )
            else:
                self._log_no_flag("turnover_rate_pct (healthcare)", str(turn_raw), "≤30%")

            # Utilization data absent
            util_note = health.get("utilization_or_productivity_note")
            if not util_note:
                self._add_flag(
                    metric="utilization_or_productivity_data",
                    value="null",
                    threshold="Required for healthcare overlay",
                    severity="Yellow",
                    note="Utilization/productivity data absent for healthcare overlay — major margin driver. Request occupancy/census data and caregiver productivity metrics from management.",
                    source_doc=health_doc,
                    confidence="high",
                )
            else:
                self._log_no_flag("utilization_or_productivity_data (healthcare)", util_note[:50], "Present")

            # Compliance incidents
            for incident in (health.get("compliance_incidents") or []):
                inc_type = incident.get("type", "unknown")
                inc_desc = incident.get("description", "")
                inc_doc  = incident.get("source_doc", health_doc)
                self._add_flag(
                    metric=f"compliance_incident_{inc_type}",
                    value=f"{inc_type}: {inc_desc[:80]}",
                    threshold="Any compliance incident (healthcare)",
                    severity="Red",
                    note=f"Compliance incident ({inc_type}): {inc_desc[:200]}. Source: {inc_doc}.",
                    source_doc=inc_doc,
                    confidence="high",
                )

            # Site-level visibility
            site_vis = (health.get("site_level_visibility") or "").lower()
            if site_vis in ("false", "partial"):
                self._add_flag(
                    metric="site_level_visibility",
                    value=site_vis,
                    threshold="full (healthcare multi-site)",
                    severity="Yellow",
                    note="Multi-site company cannot produce location-level metrics — management capability flag. Request site-level P&L and operational metrics.",
                    source_doc=health_doc,
                    confidence="high",
                )
            elif site_vis == "true":
                self._log_no_flag("site_level_visibility (healthcare)", "true", "Full visibility")

            # Wage pressure — flag if mentioned
            wage_note = health.get("wage_pressure_note")
            if wage_note:
                self._add_flag(
                    metric="wage_pressure",
                    value=wage_note[:100],
                    threshold="Any stated wage pressure (healthcare)",
                    severity="Yellow",
                    note=(
                        f"Wage pressure noted: '{wage_note[:150]}'. "
                        "Labor cost inflation directly compresses caregiver margins and can "
                        "limit census growth if compensation cannot be passed through. "
                        "Source: " + health.get("source_doc", "") + "."
                    ),
                    source_doc=health.get("source_doc", ""),
                    confidence="medium",
                )

            # Labor availability — flag if constrained
            labor_note = health.get("labor_availability_note")
            if labor_note:
                labor_lower = labor_note.lower()
                if any(w in labor_lower for w in ["shortage", "difficult", "constrained", "tight", "limited", "challenge"]):
                    self._add_flag(
                        metric="labor_availability",
                        value=labor_note[:100],
                        threshold="Constrained labor availability (healthcare)",
                        severity="Yellow",
                        note=(
                            f"Labor availability constraint noted: '{labor_note[:150]}'. "
                            "Constrained recruiting can cap census growth even when referral flow is strong. "
                            "Source: " + health.get("source_doc", "") + "."
                        ),
                        source_doc=health.get("source_doc", ""),
                        confidence="medium",
                    )

            # Denials rate — flag if elevated
            denials_raw = health.get("denials_rate_pct")
            denials_num = _parse_numeric(denials_raw)
            if denials_num is not None and denials_num > 10:
                self._add_flag(
                    metric="denials_rate_pct",
                    value=str(denials_raw),
                    threshold=">10% claims denial rate (healthcare)",
                    severity="Yellow",
                    note=(
                        f"Claims denial rate of {denials_raw} is elevated. "
                        "High denials indicate coding/billing issues, payor mix risk, or "
                        "documentation gaps — all of which pressure net revenue. "
                        "Source: " + health.get("source_doc", "") + "."
                    ),
                    source_doc=health.get("source_doc", ""),
                    confidence="high",
                )
            elif denials_num is None:
                self._add_gap(
                    "Claims denial rate not stated — required for healthcare revenue cycle assessment."
                )

            # Revenue per unit — flag if absent
            if not any([health.get("revenue_per_client_dollars"),
                        health.get("revenue_per_visit_dollars"),
                        health.get("revenue_per_hour_dollars")]):
                self._add_gap(
                    "Revenue per client / visit / hour not stated — required for healthcare "
                    "unit economics and reimbursement rate assessment."
                )

        # Missing KPIs → data room gaps
        for kpi in (extracted.get("missing_kpis") or []):
            kpi_name = kpi.get("kpi_name", "unknown")
            mgmt_q   = kpi.get("management_question", "")
            self._add_gap(f"Missing KPI [{kpi_name}]: {mgmt_q}")

    # -----------------------------------------------------------------------
    # run()
    # -----------------------------------------------------------------------

    def run(self, company_name: str, spark, llm_endpoint: str, catalog: str) -> dict:
        self._reset_state()
        self._company_name = company_name
        self._catalog = catalog
        print(f"  Running 10 tools ...")

        tr1 = self._tool_retrieve_kpi_dashboard(spark)
        tr2 = self._tool_retrieve_pipeline_backlog(spark)
        tr3 = self._tool_retrieve_delivery_model(spark)
        tr4 = self._tool_retrieve_healthcare_ops(spark)
        tr5 = self._tool_retrieve_headcount_attrition(spark)
        tr6 = self._tool_load_company_profile(company_name, spark)

        print("  Running 4 additional retrieval tools ...")
        tr_rates    = self._tool_retrieve_bill_rates_and_margins(spark)
        tr_bench    = self._tool_retrieve_bench_and_capacity(spark)
        tr_hc_rev   = self._tool_retrieve_healthcare_revenue_per_unit(spark)
        tr_hc_labor = self._tool_retrieve_healthcare_labor_market(spark)

        seen_texts: set[str] = set()
        all_chunks = []
        for tr in (tr1, tr2, tr3, tr4, tr5, tr_rates, tr_bench, tr_hc_rev, tr_hc_labor):
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
            "output":     f"Extracted overlay={extracted.get('overlay_confirmed')}, missing_kpis={len(extracted.get('missing_kpis') or [])}",
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

        print("  Applying KPI thresholds ...")
        self._apply_kpi_flags(extracted, overlay)

        return {
            "company_name":            company_name,
            "executive_summary":       extracted.get("executive_summary"),
            "overlay_confirmed":       extracted.get("overlay_confirmed"),
            "tech_services_kpis_json": json.dumps(extracted.get("tech_services_kpis") or {}),
            "healthcare_kpis_json":    json.dumps(extracted.get("healthcare_kpis") or {}),
            "saas_kpis_json":          json.dumps(extracted.get("saas_kpis") or {}),
            "industrial_kpis_json":    json.dumps(extracted.get("industrial_kpis") or {}),
            "consumer_kpis_json":      json.dumps(extracted.get("consumer_kpis") or {}),
            "missing_kpis_json":       json.dumps(extracted.get("missing_kpis") or []),
            "flags":                   self._flags_as_dicts(),
            "data_room_gaps":          list(self._data_room_gaps),
            "citations":               json.dumps(self._citations_as_dicts()),
            "reasoning_trace":         list(self._trace),
            "created_at":              datetime.now(timezone.utc).isoformat(),
            "report_path":             None,
        }


# ---------------------------------------------------------------------------
# Stakeholder report
# ---------------------------------------------------------------------------

def _write_stakeholder_report(result: dict, catalog: str, spark) -> str:
    """Write a clean, human-readable YAML report to a UC Volume.

    Saves to /Volumes/{catalog}/analysis/reports/{company_name}/
    kpi_report.yaml (or .json if PyYAML is unavailable).
    Returns the full volume path of the written file.
    """
    company_name = result["company_name"]

    # Parse JSON blobs back to Python objects for clean rendering
    tech_kpis     = json.loads(result.get("tech_services_kpis_json") or "{}")
    health_kpis   = json.loads(result.get("healthcare_kpis_json")    or "{}")
    saas_kpis     = json.loads(result.get("saas_kpis_json")          or "{}")
    industrial    = json.loads(result.get("industrial_kpis_json")    or "{}")
    consumer      = json.loads(result.get("consumer_kpis_json")      or "{}")
    missing_kpis  = json.loads(result.get("missing_kpis_json")       or "[]")
    citations     = json.loads(result.get("citations")               or "[]")
    flags         = result.get("flags") or []
    gaps          = result.get("data_room_gaps") or []

    # Build the curated report dict
    report: dict = {
        "report": {
            "agent":        "kpi",
            "company":      company_name,
            "generated_at": result.get("created_at", ""),
            "overlay":      result.get("overlay_confirmed"),
        },
        "executive_summary": result.get("executive_summary"),
        "overlay_confirmed": result.get("overlay_confirmed"),
    }

    if tech_kpis and any(v for k, v in tech_kpis.items() if k != "source_doc" and v not in (None, "null")):
        report["tech_services_kpis"] = tech_kpis

    if health_kpis and any(v for k, v in health_kpis.items() if k != "source_doc" and v not in (None, "null", [])):
        report["healthcare_kpis"] = health_kpis

    if saas_kpis and any(v for k, v in saas_kpis.items() if k != "source_doc" and v not in (None, "null")):
        report["saas_kpis"] = saas_kpis

    if industrial and any(v for k, v in industrial.items() if k != "source_doc" and v not in (None, "null")):
        report["industrial_kpis"] = industrial

    if consumer and any(v for k, v in consumer.items() if k != "source_doc" and v not in (None, "null")):
        report["consumer_kpis"] = consumer

    if missing_kpis:
        report["missing_kpis"] = missing_kpis

    report["flags"] = {
        "count": len(flags),
        "items": flags,
    }
    report["data_room_gaps"] = gaps
    report["citations"] = citations

    # Render as YAML (preferred) or JSON fallback
    try:
        import yaml

        def _str_representer(dumper, data):
            if "\n" in data:
                return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
            return dumper.represent_scalar("tag:yaml.org,2002:str", data)

        yaml.add_representer(str, _str_representer)
        content = yaml.dump(report, allow_unicode=True, sort_keys=False, width=120)
        ext = "yaml"
    except ImportError:
        content = json.dumps(report, indent=2, ensure_ascii=False)
        ext = "json"

    # Ensure the UC Volume and directory exist
    spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.analysis.reports")
    safe_name = company_name.replace(" ", "_").replace("/", "_")
    dir_path  = f"/Volumes/{catalog}/analysis/reports/{safe_name}"
    os.makedirs(dir_path, exist_ok=True)

    file_path = f"{dir_path}/kpi_report.{ext}"
    with open(file_path, "w", encoding="utf-8") as fh:
        fh.write(content)

    return file_path


# ---------------------------------------------------------------------------
# Section extraction helpers
# ---------------------------------------------------------------------------

def _extract_section(narrative_text: str, header: str) -> str:
    """Pull the content under a given ### header (exact match) from the narrative."""
    pattern = rf"###\s*{re.escape(header)}\s*\n(.*?)(?=\n###|\Z)"
    m = re.search(pattern, narrative_text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _extract_section_by_num(narrative_text: str, num: int) -> str:
    """Pull the content under a numbered ### header (any title after the number)."""
    pattern = rf"###\s*{num}\.[^\n]*\n(.*?)(?=\n###|\Z)"
    m = re.search(pattern, narrative_text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""


# ---------------------------------------------------------------------------
# KPI assessment report (rich markdown with LLM narrative)
# ---------------------------------------------------------------------------

def generate_kpi_assessment(
    result: dict,
    spark,
    llm_endpoint: str,
    catalog: str = "uc13",
    write_to_volume: bool = True,
) -> str:
    """Generate a structured markdown KPI assessment from agent output.

    Three-phase: deterministic table construction → single LLM narrative call →
    markdown assembly + optional volume write.

    Args:
        result:          Output dict from KPIAgent.run() or main().
        spark:           Active SparkSession (needed only when write_to_volume=True).
        llm_endpoint:    Databricks model-serving endpoint name.
        catalog:         UC catalog for volume write (default 'uc13').
        write_to_volume: If True, writes kpi_assessment.md to the reports volume.

    Returns:
        Markdown string.
    """
    import mlflow.deployments

    # ── Parse result dict ─────────────────────────────────────────────────
    overlay         = result.get("overlay_confirmed", "unknown")
    tech_kpis       = json.loads(result.get("tech_services_kpis_json") or "{}")
    health_kpis     = json.loads(result.get("healthcare_kpis_json")    or "{}")
    saas_kpis       = json.loads(result.get("saas_kpis_json")          or "{}")
    industrial_kpis = json.loads(result.get("industrial_kpis_json")    or "{}")
    consumer_kpis   = json.loads(result.get("consumer_kpis_json")      or "{}")
    missing_kpis    = json.loads(result.get("missing_kpis_json")       or "[]")
    _flags_raw      = result.get("flags") or []
    flags           = json.loads(_flags_raw) if isinstance(_flags_raw, str) else _flags_raw
    data_room_gaps  = result.get("data_room_gaps") or []
    company_name    = result.get("company_name", "Unknown")
    generated_at    = result.get("created_at", "")

    overlay_lower = overlay.lower()
    is_tech       = "tech" in overlay_lower
    is_healthcare = "healthcare" in overlay_lower

    # ── Shared helpers ────────────────────────────────────────────────────
    def _v(val):
        """Return value or em-dash sentinel."""
        if val is None or val == "null" or val == "":
            return "\u2014"
        return str(val)

    _EMOJI = {"Red": "\U0001f534", "Yellow": "\U0001f7e1", "Green": "\U0001f7e2"}

    def _flag_emoji(metric_name: str) -> str:
        for f in flags:
            if f.get("metric", "").lower() == metric_name.lower():
                return _EMOJI.get(f.get("severity", ""), "")
        return ""

    def _flag_threshold(metric_name: str) -> str:
        for f in flags:
            if f.get("metric", "").lower() == metric_name.lower():
                return f.get("threshold", "")
        return ""

    def _pipe_table(headers: list, rows: list) -> str:
        """Build a GitHub-flavoured markdown pipe table."""
        sep        = "| " + " | ".join("---" for _ in headers) + " |"
        header_row = "| " + " | ".join(headers) + " |"
        if not rows:
            return header_row + "\n" + sep
        body = "\n".join(
            "| " + " | ".join(str(cell) for cell in row) + " |"
            for row in rows
        )
        return "\n".join([header_row, sep, body])

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 1 — Deterministic tables
    # ══════════════════════════════════════════════════════════════════════

    _kpi_src = (
        tech_kpis.get("source_doc") or health_kpis.get("source_doc")
        or saas_kpis.get("source_doc") or industrial_kpis.get("source_doc")
        or consumer_kpis.get("source_doc") or "\u2014"
    )

    if is_tech:
        _dash_rows = [
            ("Utilization Rate",           _v(tech_kpis.get("utilization_rate_pct")),      _flag_emoji("utilization_rate_pct"),          _flag_threshold("utilization_rate_pct") or "\u226575% (Green)",  _kpi_src),
            ("Avg Bill Rate ($/hr)",       _v(tech_kpis.get("average_bill_rate_dollars")),  "",                                           "\u2014",                                                         _kpi_src),
            ("Contractor % of Workforce",  _v(tech_kpis.get("contractor_pct_of_workforce")), _flag_emoji("contractor_pct_of_workforce"),  _flag_threshold("contractor_pct_of_workforce") or "\u226450%",   _kpi_src),
            ("Bench Size (headcount)",     _v(tech_kpis.get("bench_size")),                  "",                                          "\u2014",                                                         _kpi_src),
            ("Bench Cost % of Revenue",    _v(tech_kpis.get("bench_cost_pct_revenue")),      _flag_emoji("bench_cost_pct_revenue"),        _flag_threshold("bench_cost_pct_revenue") or "\u226415%",         _kpi_src),
            ("Average ACV ($)",            _v(tech_kpis.get("average_acv_dollars")),         _flag_emoji("average_acv_dollars"),           _flag_threshold("average_acv_dollars") or "\u2265$100K",          _kpi_src),
            ("Bookings",                   _v(tech_kpis.get("bookings_stated")),              "",                                          "\u2014",                                                         _kpi_src),
            ("Backlog (months)",           _v(tech_kpis.get("backlog_months_of_revenue")),   _flag_emoji("pipeline_backlog_coverage_months"), _flag_threshold("pipeline_backlog_coverage_months") or "\u22656 mo", _kpi_src),
            ("Pipeline Coverage (months)", _v(tech_kpis.get("pipeline_coverage_months")),    _flag_emoji("pipeline_backlog_coverage_months"), "\u22656 months",                                             _kpi_src),
            ("Revenue per FTE ($)",        _v(tech_kpis.get("revenue_per_fte_dollars")),      "",                                          "\u2014",                                                         _kpi_src),
            ("Attrition Rate",             _v(tech_kpis.get("attrition_rate_pct")),           "",                                          "\u2014",                                                         _kpi_src),
            ("Avg Sales Cycle (days)",     _v(tech_kpis.get("average_sales_cycle_days")),     "",                                          "\u2014",                                                         _kpi_src),
        ]
    elif is_healthcare:
        _hc_src = health_kpis.get("source_doc", "\u2014")
        _dash_rows = [
            ("Census / Patient Panel",    _v(health_kpis.get("census_or_patient_panel")),   "",                                   "\u2014",                                                         _hc_src),
            ("Caregiver Headcount",       _v(health_kpis.get("caregiver_headcount")),        "",                                   "\u2014",                                                         _hc_src),
            ("Clinician Headcount",       _v(health_kpis.get("clinician_headcount")),         "",                                  "\u2014",                                                         _hc_src),
            ("Turnover Rate",             _v(health_kpis.get("turnover_rate_pct")),           _flag_emoji("turnover_rate_pct"),    _flag_threshold("turnover_rate_pct") or "\u226430%",              _hc_src),
            ("Revenue / Client ($)",      _v(health_kpis.get("revenue_per_client_dollars")), "",                                   "\u2014",                                                         _hc_src),
            ("Revenue / Visit ($)",       _v(health_kpis.get("revenue_per_visit_dollars")),  "",                                   "\u2014",                                                         _hc_src),
            ("Revenue / Hour ($)",        _v(health_kpis.get("revenue_per_hour_dollars")),   "",                                   "\u2014",                                                         _hc_src),
            ("Denials Rate",              _v(health_kpis.get("denials_rate_pct")),            _flag_emoji("denials_rate_pct"),     _flag_threshold("denials_rate_pct") or "\u226410%",               _hc_src),
            ("Collections Rate",          _v(health_kpis.get("collections_rate_pct")),        "",                                  "\u2014",                                                         _hc_src),
        ]
    elif "saas" in overlay_lower:
        _s_src = saas_kpis.get("source_doc", "\u2014")
        _dash_rows = [
            ("NRR",                  _v(saas_kpis.get("nrr_pct")),              "", "\u2014", _s_src),
            ("GRR",                  _v(saas_kpis.get("grr_pct")),              "", "\u2014", _s_src),
            ("Logo Churn",           _v(saas_kpis.get("logo_churn_pct")),       "", "\u2014", _s_src),
            ("CAC Payback (months)", _v(saas_kpis.get("cac_payback_months")),   "", "\u2014", _s_src),
            ("Rule of 40",           _v(saas_kpis.get("rule_of_40_stated")),    "", "\u2014", _s_src),
            ("ARR per FTE ($)",      _v(saas_kpis.get("arr_per_fte_dollars")),  "", "\u2014", _s_src),
            ("Magic Number",         _v(saas_kpis.get("magic_number_stated")),  "", "\u2014", _s_src),
        ]
    elif "industrial" in overlay_lower:
        _i_src = industrial_kpis.get("source_doc", "\u2014")
        _dash_rows = [
            ("Backlog (months)",      _v(industrial_kpis.get("backlog_months")),           "", "\u2014", _i_src),
            ("Capacity Utilization",  _v(industrial_kpis.get("capacity_utilization_pct")), "", "\u2014", _i_src),
            ("On-Time Delivery %",    _v(industrial_kpis.get("on_time_delivery_pct")),     "", "\u2014", _i_src),
            ("Inventory Turns",       _v(industrial_kpis.get("inventory_turns")),          "", "\u2014", _i_src),
        ]
    elif "consumer" in overlay_lower:
        _c_src = consumer_kpis.get("source_doc", "\u2014")
        _dash_rows = [
            ("12-mo Repeat Rate",   _v(consumer_kpis.get("repeat_rate_12mo_pct")),    "", "\u2014", _c_src),
            ("Contribution Margin", _v(consumer_kpis.get("contribution_margin_pct")), "", "\u2014", _c_src),
            ("Return Rate",         _v(consumer_kpis.get("return_rate_pct")),          "", "\u2014", _c_src),
            ("LTV / CAC",           _v(consumer_kpis.get("ltv_cac_ratio")),            "", "\u2014", _c_src),
        ]
    else:
        _dash_rows = []

    tbl_dashboard = _pipe_table(
        ["KPI", "Stated Value", "Flag", "Threshold", "Source Doc"],
        _dash_rows,
    )
    tbl_dashboard += (
        "\n> KPI Dashboard \u2014 overlay: " + overlay + ". Values extracted from data room as stated; "
        "flags applied per Austin\u2019s primary thresholds. N/A = not available in data room."
    )

    # TABLE 2 — Bill Rates by Role (tech only)
    _bill_rows = [
        (r.get("role") or "\u2014", r.get("bill_rate_dollars") or "\u2014",
         r.get("basis") or "\u2014", r.get("source_doc") or "\u2014")
        for r in (tech_kpis.get("bill_rates_by_role") or [])
    ]
    tbl_bill_rates = (
        _pipe_table(["Role", "Bill Rate", "Basis", "Source Doc"], _bill_rows)
        if _bill_rows else "_No bill rate detail by role extracted._"
    )

    # TABLE 3 — Utilization by Segment (tech only)
    _util_rows = [
        (r.get("segment") or "\u2014", r.get("segment_label") or "\u2014",
         r.get("utilization_pct") or "\u2014", r.get("period") or "\u2014",
         r.get("source_doc") or "\u2014")
        for r in (tech_kpis.get("utilization_by_segment") or [])
    ]
    tbl_util_segment = (
        _pipe_table(["Segment Type", "Label", "Utilization %", "Period", "Source Doc"], _util_rows)
        if _util_rows else "_No segment-level utilization extracted._"
    )

    # TABLE 4 — Gross Margin by Segment (tech only)
    _gm_rows = [
        (r.get("segment_type") or "\u2014", r.get("segment_label") or "\u2014",
         r.get("gm_pct") or "\u2014", r.get("gm_dollars") or "\u2014",
         r.get("source_doc") or "\u2014")
        for r in (tech_kpis.get("gross_margin_by_segment") or [])
    ]
    tbl_gm_segment = (
        _pipe_table(["Segment Type", "Label", "GM %", "GM $", "Source Doc"], _gm_rows)
        if _gm_rows else "_No segment-level GM extracted._"
    )

    # TABLE 5 — Missing KPIs
    _missing_rows = [
        (m.get("kpi_name") or "\u2014", m.get("overlay") or "\u2014",
         m.get("why_expected") or "\u2014", m.get("management_question") or "\u2014")
        for m in (missing_kpis or [])
    ]
    tbl_missing = (
        _pipe_table(["KPI", "Overlay", "Why Expected", "Management Question"], _missing_rows)
        if _missing_rows else "_All expected KPIs present in data room._"
    )

    # TABLE 6 — Investment Flags
    _sev_order  = {"Red": 0, "Yellow": 1, "Green": 2}
    _flags_sorted = sorted(flags, key=lambda f: _sev_order.get(f.get("severity", ""), 3))
    _flag_rows  = [
        (
            _EMOJI.get(f.get("severity", ""), "\u26aa"),
            f.get("metric") or "\u2014",
            str(f.get("value") or "\u2014")[:60],
            f.get("threshold") or "\u2014",
            str(f.get("note") or "\u2014")[:100],
            f.get("source_doc") or "\u2014",
        )
        for f in _flags_sorted
    ]
    tbl_flags = (
        _pipe_table(["Severity", "Metric", "Value", "Threshold", "Note", "Source"], _flag_rows)
        if _flag_rows else "_No flags raised._"
    )

    # TABLE 7 — Data Room Gaps
    tbl_gaps = (
        "\n".join("- " + g for g in data_room_gaps)
        if data_room_gaps else "_None identified._"
    )

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 2 — Single LLM narrative call
    # ══════════════════════════════════════════════════════════════════════

    _flag_lines = "\n".join(
        "  " + _EMOJI.get(f.get("severity", ""), "\u26aa") + " "
        + str(f.get("metric", "")) + ": " + str(f.get("value", ""))
        + " vs " + str(f.get("threshold", ""))
        for f in _flags_sorted[:10]
    ) or "  None."

    _top_missing  = (missing_kpis or [])[:3]
    _missing_lines = "\n".join(
        "  - " + str(m.get("kpi_name", "")) + ": " + str(m.get("management_question", ""))
        for m in _top_missing
    ) or "  None."

    if is_tech:
        _bench_block = (
            "\nBENCH & CAPACITY:\n"
            "  Bench size: " + _v(tech_kpis.get("bench_size")) + "\n"
            "  Bench cost: " + _v(tech_kpis.get("bench_cost_dollars"))
            + " / " + _v(tech_kpis.get("bench_cost_pct_revenue")) + " of revenue\n"
            "  Bench note: " + _v(tech_kpis.get("bench_note")) + "\n"
            "  Delivery capacity: " + _v(tech_kpis.get("delivery_capacity_note")) + "\n"
            "  Pipeline vs. capacity: " + _v(tech_kpis.get("pipeline_vs_capacity_note")) + "\n"
        )
        if _bill_rows:
            _bench_block += "\nBILL RATES BY ROLE:\n" + tbl_bill_rates + "\n"
        if _util_rows:
            _bench_block += "\nUTILIZATION BY SEGMENT:\n" + tbl_util_segment + "\n"
        if _gm_rows:
            _bench_block += "\nGROSS MARGIN BY SEGMENT:\n" + tbl_gm_segment + "\n"
    elif is_healthcare:
        _bench_block = (
            "\nWAGE PRESSURE: " + _v(health_kpis.get("wage_pressure_note")) + "\n"
            "LABOR AVAILABILITY: " + _v(health_kpis.get("labor_availability_note")) + "\n"
            "DENIALS NOTE: " + _v(health_kpis.get("denials_note")) + "\n"
            "COLLECTIONS NOTE: " + _v(health_kpis.get("collections_note")) + "\n"
            "REVENUE PER UNIT NOTE: " + _v(health_kpis.get("revenue_per_unit_note")) + "\n"
        )
    else:
        _bench_block = ""

    _KPI_CONTEXT = (
        "COMPANY: " + company_name + "\n"
        "OVERLAY: " + overlay + "\n\n"
        "KPI DASHBOARD:\n" + tbl_dashboard + "\n"
        + _bench_block
        + "\nINVESTMENT FLAGS (" + str(len(_flags_sorted)) + " total):\n"
        + _flag_lines + "\n\n"
        + "MISSING KPIs (" + str(len(missing_kpis)) + " total \u2014 top 3):\n"
        + _missing_lines + "\n"
    )

    _ASSESS_SYS = """\
You are a senior PE investment analyst writing the Operating KPI section of an
internal diligence memo. Use the structured data provided to answer 7 specific
questions about the company's operational health, delivery efficiency, capacity,
sales productivity, and cost structure.

Rules:
1. Write only what the data supports. Do not invent facts.
2. If a section has no data, write one sentence stating what is missing and why
   it matters for underwriting.
3. Use concrete figures from the KPI tables.
4. Use PE language: "margin-dilutive bench", "delivery-constrained pipeline",
   "rate compression risk", "utilization-driven upside", "turnover-driven margin
   pressure", "collection cycle risk", "labor-capped growth", "denial-prone payor mix".
5. No deal verdicts. Use "warrants scrutiny", "requires management confirmation",
   or "flag for operating diligence" \u2014 never "deal-breaker" or "acceptable".
6. Return pure markdown only \u2014 no preamble, no code fences.
7. Structure with exactly these 7 H3 headers:
   ### 1. Utilization & Delivery Efficiency
   ### 2. Pricing Power & Rate Quality
   ### 3. Bench & Capacity Management
   ### 4. Sales Productivity & Pipeline Visibility
   ### 5. Workforce Quality (Attrition / Turnover / Labor Market)
   ### 6. Margin Profile by Segment
   ### 7. Key Operating Diligence Questions
8. Sections 1\u20136: MAX 2 bullet points (\u226430 words each) + one **Analyst take:** sentence
   (\u226420 words). Section 7: numbered list of \u22644 specific questions drawn only from flags
   and missing KPIs shown \u2014 do not invent new questions.
9. For healthcare overlays: replace sections 1\u20134 with census/referral, payor mix,
   revenue per unit, and denials/collections \u2014 keep the same 7-section structure.
10. Be concise. The entire section must fit within a 2-page memo section.\
"""

    _ASSESS_USER = (
        "Use the KPI data below to answer all 7 assessment questions. Markdown only.\n\n"
        + _KPI_CONTEXT
    )

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

    md: list[str] = []
    md.append(f"# KPI & Operating Metrics Assessment \u2014 {company_name}")
    md.append(f"_Generated: {generated_at}  |  Overlay: {overlay}_\n")

    md.append("## Executive Summary")
    md.append(result.get("executive_summary") or "_No executive summary extracted._")
    md.append("")

    md.append("---\n")
    md.append("## KPI Dashboard\n")
    md.append(tbl_dashboard)
    md.append("")
    _sec1 = _extract_section(narrative, "1. Utilization & Delivery Efficiency")
    if _sec1:
        md.append(_sec1)
        md.append("")

    if is_tech:
        md.append("---\n")
        md.append("## Bill Rates by Role\n")
        md.append(tbl_bill_rates)
        md.append("")
        _sec2 = _extract_section(narrative, "2. Pricing Power & Rate Quality")
        if _sec2:
            md.append(_sec2)
            md.append("")

        md.append("---\n")
        md.append("## Utilization by Segment\n")
        md.append(tbl_util_segment)
        md.append("")

        md.append("---\n")
        md.append("## Gross Margin by Segment\n")
        md.append(tbl_gm_segment)
        md.append("")
        _sec6 = _extract_section(narrative, "6. Margin Profile by Segment")
        if _sec6:
            md.append(_sec6)
            md.append("")

        md.append("---\n")
        md.append("## Bench & Capacity\n")
        md.append("**Bench size:** " + _v(tech_kpis.get("bench_size")))
        md.append(
            "**Bench cost:** " + _v(tech_kpis.get("bench_cost_dollars"))
            + " / " + _v(tech_kpis.get("bench_cost_pct_revenue")) + " of revenue"
        )
        md.append("**Bench note:** " + _v(tech_kpis.get("bench_note")))
        md.append("**Delivery capacity:** " + _v(tech_kpis.get("delivery_capacity_note")))
        md.append("**Pipeline vs. capacity:** " + _v(tech_kpis.get("pipeline_vs_capacity_note")))
        md.append("")
        _sec3 = _extract_section(narrative, "3. Bench & Capacity Management")
        if _sec3:
            md.append(_sec3)
            md.append("")

        md.append("---\n")
        md.append("## Sales Productivity & Pipeline\n")
        md.append(
            "**Avg sales cycle:** " + _v(tech_kpis.get("average_sales_cycle_days"))
            + " days \u2014 " + _v(tech_kpis.get("average_sales_cycle_note"))
        )
        md.append("")
        _sec4 = _extract_section(narrative, "4. Sales Productivity & Pipeline Visibility")
        if _sec4:
            md.append(_sec4)
            md.append("")

    elif is_healthcare:
        md.append("---\n")
        md.append("## Census & Referral Trends\n")
        md.append("**Census / Patient Panel:** " + _v(health_kpis.get("census_or_patient_panel")))
        md.append("**Referral source breakdown:** " + _v(health_kpis.get("referral_source_breakdown")))
        md.append("**Utilization / productivity:** " + _v(health_kpis.get("utilization_or_productivity_note")))
        md.append("")
        _hc1 = _extract_section_by_num(narrative, 1)
        if _hc1:
            md.append(_hc1)
            md.append("")

        md.append("---\n")
        md.append("## Payor Mix\n")
        md.append("**AR aging by payor:** " + _v(health_kpis.get("ar_aging_by_payor_note")))
        md.append("")
        _hc2 = _extract_section_by_num(narrative, 2)
        if _hc2:
            md.append(_hc2)
            md.append("")

        md.append("---\n")
        md.append("## Revenue per Unit\n")
        md.append("**Revenue / client:** " + _v(health_kpis.get("revenue_per_client_dollars")))
        md.append("**Revenue / visit:** " + _v(health_kpis.get("revenue_per_visit_dollars")))
        md.append("**Revenue / hour:** " + _v(health_kpis.get("revenue_per_hour_dollars")))
        md.append("**Revenue per unit note:** " + _v(health_kpis.get("revenue_per_unit_note")))
        md.append("")
        _hc3 = _extract_section_by_num(narrative, 3)
        if _hc3:
            md.append(_hc3)
            md.append("")

        md.append("---\n")
        md.append("## Denials & Collections\n")
        md.append("**Denials rate:** " + _v(health_kpis.get("denials_rate_pct")))
        md.append("**Denials note:** " + _v(health_kpis.get("denials_note")))
        md.append("**Collections rate:** " + _v(health_kpis.get("collections_rate_pct")))
        md.append("**Collections note:** " + _v(health_kpis.get("collections_note")))
        md.append("")
        _hc4 = _extract_section_by_num(narrative, 4)
        if _hc4:
            md.append(_hc4)
            md.append("")

    md.append("---\n")
    md.append("## Workforce Quality\n")
    _sec5 = _extract_section(narrative, "5. Workforce Quality (Attrition / Turnover / Labor Market)")
    if not _sec5:
        _sec5 = _extract_section_by_num(narrative, 5)
    md.append(_sec5 if _sec5 else "_Workforce data not available._")
    md.append("")

    md.append("---\n")
    md.append("## Investment Flags\n")
    md.append(tbl_flags)
    md.append("")

    md.append("---\n")
    md.append("## Missing KPIs \u2014 Management Information Request\n")
    md.append(tbl_missing)
    md.append("")

    md.append("---\n")
    md.append("## Key Operating Diligence Questions\n")
    _sec7 = _extract_section(narrative, "7. Key Operating Diligence Questions")
    if not _sec7:
        _sec7 = _extract_section_by_num(narrative, 7)
    md.append(_sec7 if _sec7 else "_See missing KPIs and flags above._")
    md.append("")

    md.append("---\n")
    md.append("## Data Room Gaps\n")
    md.append(tbl_gaps)
    md.append("")

    final_markdown = "\n".join(md)

    # ── Optional volume write ──────────────────────────────────────────────
    if write_to_volume:
        spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.analysis.reports")
        safe_name = company_name.replace(" ", "_").replace("/", "_")
        dir_path  = f"/Volumes/{catalog}/analysis/reports/{safe_name}"
        os.makedirs(dir_path, exist_ok=True)
        file_path = f"{dir_path}/kpi_assessment.md"
        with open(file_path, "w", encoding="utf-8") as fh:
            fh.write(final_markdown)
        print(f"\u2713 KPI assessment \u2192 {file_path}")

    return final_markdown


# ---------------------------------------------------------------------------
# One-pager data builder (for Orchestrator Agent)
# ---------------------------------------------------------------------------

def build_kpi_one_pager_data(result: dict) -> dict:
    """Extract the KPI fields needed by the Orchestrator to populate
    Section 3 (Customer Snapshot & KPI Dashboard) and the KPI rows in
    Section 4 (Top Risks) of the UC13 one-pager template.

    Returns a dict with two keys:
      - kpi_dashboard_rows: list of dicts for the KPI table in Section 3
      - kpi_risk_rows: list of Red/Yellow flags formatted for Section 4

    Call this from the Orchestrator Agent, not from main().
    The result dict is the output of KPIAgent.run().
    """
    overlay  = result.get("overlay_confirmed", "unknown")
    tech     = json.loads(result.get("tech_services_kpis_json") or "{}")
    health   = json.loads(result.get("healthcare_kpis_json")    or "{}")
    flags    = result.get("flags") or []
    missing  = json.loads(result.get("missing_kpis_json")       or "[]")

    # ── KPI dashboard rows for the one-pager Section 3 table ──────────────
    def _flag_emoji(metric_name):
        for f in flags:
            if f.get("metric", "").lower() == metric_name.lower():
                return {"Red": "\U0001f534", "Yellow": "\U0001f7e1", "Green": "\U0001f7e2"}.get(
                    f.get("severity", ""), "N/A"
                )
        return "N/A"

    overlay_lower = overlay.lower()
    is_tech       = "tech" in overlay_lower
    is_healthcare = "healthcare" in overlay_lower

    kpi_rows = []

    if is_tech:
        kpi_rows = [
            {
                "kpi":       "Utilization / Bill Rate",
                "value":     (
                    str(tech.get("utilization_rate_pct") or "\u2014") + " util  /  $"
                    + str(tech.get("average_bill_rate_dollars") or "\u2014") + "/hr"
                ),
                "threshold": "\u226575% util (Green); $100\u2013200K+ ACV",
                "flag":      _flag_emoji("utilization_rate_pct") or _flag_emoji("average_acv_dollars"),
            },
            {
                "kpi":       "Backlog / Pipeline Coverage (months)",
                "value":     tech.get("backlog_months_of_revenue") or tech.get("pipeline_coverage_months") or "\u2014",
                "threshold": "\u22656 months",
                "flag":      _flag_emoji("pipeline_backlog_coverage_months"),
            },
            {
                "kpi":       "Revenue per FTE",
                "value":     "$" + str(tech.get("revenue_per_fte_dollars") or "\u2014"),
                "threshold": "N/A",
                "flag":      "N/A",
            },
            {
                "kpi":       "Employee Turnover / Attrition",
                "value":     tech.get("attrition_rate_pct") or "\u2014",
                "threshold": "N/A",
                "flag":      "N/A",
            },
        ]
    elif is_healthcare:
        kpi_rows = [
            {
                "kpi":       "Utilization / Bill Rate",
                "value":     health.get("utilization_or_productivity_note") or "\u2014",
                "threshold": "Flag if absent",
                "flag":      _flag_emoji("utilization_or_productivity_data"),
            },
            {
                "kpi":       "Backlog / Pipeline Coverage (months)",
                "value":     "N/A (healthcare)",
                "threshold": "N/A",
                "flag":      "N/A",
            },
            {
                "kpi":       "Revenue per FTE",
                "value":     (
                    "$" + str(health.get("revenue_per_client_dollars") or health.get("revenue_per_visit_dollars") or "\u2014")
                    + " per visit/client"
                ),
                "threshold": "N/A",
                "flag":      "N/A",
            },
            {
                "kpi":       "Employee Turnover / Attrition",
                "value":     health.get("turnover_rate_pct") or "\u2014",
                "threshold": ">30% = Red",
                "flag":      _flag_emoji("turnover_rate_pct"),
            },
        ]

    # ── Risk rows for Section 4 — only Red/Yellow KPI flags ───────────────
    risk_rows = []
    for f in flags:
        if f.get("severity") in ("Red", "Yellow"):
            sev_label = "CRIT" if f.get("severity") == "Red" else "MATE"
            risk_rows.append({
                "risk":     str(f.get("note", f.get("metric", "")))[:120],
                "severity": sev_label,
                "source":   f.get("source_doc", "KPI Agent"),
                "mitigant": (
                    "Confirm with management: " + str(f.get("metric", ""))
                    + " vs threshold " + str(f.get("threshold", ""))
                ),
            })

    # ── Missing KPI rows as information request items ──────────────────────
    info_requests = [
        {
            "gap":      m.get("kpi_name", ""),
            "question": m.get("management_question", ""),
        }
        for m in missing
    ]

    return {
        "overlay":            overlay,
        "kpi_dashboard_rows": kpi_rows,
        "kpi_risk_rows":      risk_rows,
        "info_requests":      info_requests,
    }


# ---------------------------------------------------------------------------
# Delta table DDL
# ---------------------------------------------------------------------------

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {table} (
    company_name             STRING,
    executive_summary        STRING,
    overlay_confirmed        STRING,
    tech_services_kpis_json  STRING,
    healthcare_kpis_json     STRING,
    saas_kpis_json           STRING,
    industrial_kpis_json     STRING,
    consumer_kpis_json       STRING,
    missing_kpis_json        STRING,
    flags                    STRING,
    data_room_gaps           ARRAY<STRING>,
    citations                STRING,
    reasoning_trace          STRING,
    report_path              STRING,
    created_at               TIMESTAMP
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

    print(f"\n=== KPI Agent ({company_name}) ===")

    open_agent_run(
        "kpi",
        company_name=company_name,
        catalog=catalog,
        affected_intents=load_affected_intents("kpi"),
        spark=spark,
    )
    try:
        agent  = KPIAgent()
        result = agent.run(company_name=company_name, spark=spark, llm_endpoint=llm_endpoint, catalog=catalog)

        # Save to Delta
        table = f"{catalog}.analysis.kpi"
        spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.analysis")

        # Schema migration guard: drop and recreate when expected columns are missing.
        _EXPECTED_COLS = {
            "company_name", "executive_summary", "overlay_confirmed",
            "tech_services_kpis_json", "healthcare_kpis_json", "saas_kpis_json",
            "industrial_kpis_json", "consumer_kpis_json", "missing_kpis_json",
            "flags", "data_room_gaps", "citations", "reasoning_trace",
            "report_path", "created_at",
        }
        try:
            _live_cols = {f.name for f in spark.table(table).schema.fields}
            if not _EXPECTED_COLS.issubset(_live_cols):
                _missing = _EXPECTED_COLS - _live_cols
                print(f"  [schema_migration] {table}: dropping stale table. Missing cols: {sorted(_missing)}")
                spark.sql(f"DROP TABLE IF EXISTS {table}")
        except Exception:
            pass

        spark.sql(_CREATE_TABLE_SQL.format(table=table))
        spark.sql(f"DELETE FROM {table} WHERE company_name = '{company_name}'")

        from pyspark.sql import Row
        from pyspark.sql.types import (
            StructType, StructField, StringType,
            ArrayType, TimestampType,
        )

        schema = StructType([
            StructField("company_name",             StringType(),            True),
            StructField("executive_summary",        StringType(),            True),
            StructField("overlay_confirmed",        StringType(),            True),
            StructField("tech_services_kpis_json",  StringType(),            True),
            StructField("healthcare_kpis_json",     StringType(),            True),
            StructField("saas_kpis_json",           StringType(),            True),
            StructField("industrial_kpis_json",     StringType(),            True),
            StructField("consumer_kpis_json",       StringType(),            True),
            StructField("missing_kpis_json",        StringType(),            True),
            StructField("flags",                    StringType(),            True),
            StructField("data_room_gaps",           ArrayType(StringType()), True),
            StructField("citations",                StringType(),            True),
            StructField("reasoning_trace",          StringType(),            True),
            StructField("report_path",              StringType(),            True),
            StructField("created_at",               TimestampType(),         True),
        ])

        row_data = {
            "company_name":            result["company_name"],
            "executive_summary":       result.get("executive_summary"),
            "overlay_confirmed":       result.get("overlay_confirmed"),
            "tech_services_kpis_json": result.get("tech_services_kpis_json"),
            "healthcare_kpis_json":    result.get("healthcare_kpis_json"),
            "saas_kpis_json":          result.get("saas_kpis_json"),
            "industrial_kpis_json":    result.get("industrial_kpis_json"),
            "consumer_kpis_json":      result.get("consumer_kpis_json"),
            "missing_kpis_json":       result.get("missing_kpis_json"),
            "flags":                   json.dumps(result.get("flags") or []),
            "data_room_gaps":          result.get("data_room_gaps") or [],
            "citations":               result.get("citations"),
            "reasoning_trace":         json.dumps(result.get("reasoning_trace") or []),
            "report_path":             result.get("report_path"),
            "created_at":              datetime.now(timezone.utc),
        }

        df = spark.createDataFrame([Row(**row_data)], schema=schema)
        df.write.format("delta").mode("append").saveAsTable(table)

        print(f"\n✓ Saved KPI output → {table}")

        # Export stakeholder report
        report_path = _write_stakeholder_report(result, catalog, spark)
        result["report_path"] = report_path
        print(f"✓ Stakeholder report → {report_path}")

        # Generate rich markdown assessment
        assessment_md = generate_kpi_assessment(
            result=result, spark=spark, llm_endpoint=llm_endpoint,
            catalog=catalog, write_to_volume=True,
        )
        print(f"✓ KPI assessment → written to volume")

        return result
    finally:
        close_agent_run()


# Golden checklist row vocabulary — spec §6.1 / eval harness M1-T1 (Decision B: item_id + display_name only).
GOLDEN_CHECKLIST_COVERAGE: list[dict] = [
    {
        "item_id": "overlay_confirmed",
        "display_name": "Overlay confirmation extraction fidelity",
    },
    {
        "item_id": "overlay_block_fields",
        "display_name": "Selected overlay KPI block field presence",
    },
    {
        "item_id": "missing_kpis_json",
        "display_name": "Missing KPI list accuracy",
    },
]

assert len(GOLDEN_CHECKLIST_COVERAGE) == 3
assert all(set(req) == {"item_id", "display_name"} for req in GOLDEN_CHECKLIST_COVERAGE)
assert len({req["item_id"] for req in GOLDEN_CHECKLIST_COVERAGE}) == 3


# ---------------------------------------------------------------------------
# Agent Bricks / MLflow 3 endpoint wrapper
# ---------------------------------------------------------------------------
# KPIAgent inherits WorkstreamAgent directly (unlike FTA/BMA which compose it).
# KPIAgentEndpoint is provided for symmetry with other agents and to make
# Model Serving deployment explicit and documented.
# Deploy this class to Model Serving; the main() function and direct run()
# calls in test_pipeline.ipynb bypass this wrapper entirely.
# ---------------------------------------------------------------------------


class KPIAgentEndpoint(WorkstreamAgent):
    """Thin ResponsesAgent wrapper for KPIAgent.

    Delegates run() to KPIAgent(). Deploy this class — not KPIAgent directly —
    to Databricks Model Serving so the Supervisor Agent can call it via
    ResponsesAgentRequest with company_name / llm_endpoint in custom_inputs.
    """

    agent_name = "kpi"

    def run(self, company_name: str, spark, llm_endpoint: str, catalog: str = "uc13") -> dict:
        return KPIAgent().run(
            company_name=company_name,
            spark=spark,
            llm_endpoint=llm_endpoint,
            catalog=catalog,
        )


if __name__ == "__main__":
    main()
