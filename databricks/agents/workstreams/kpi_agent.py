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

_CATALOG = os.environ.get("catalog", "uc13")


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
   Any history qualifies — not just currently open matters.\
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

    def _tool_load_company_profile(self, company_name: str, spark):
        sql = f"SELECT * FROM {_CATALOG}.classification.company_profile WHERE company_name = '{company_name}' ORDER BY created_at DESC LIMIT 1"
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

        # Missing KPIs → data room gaps
        for kpi in (extracted.get("missing_kpis") or []):
            kpi_name = kpi.get("kpi_name", "unknown")
            mgmt_q   = kpi.get("management_question", "")
            self._add_gap(f"Missing KPI [{kpi_name}]: {mgmt_q}")

    # -----------------------------------------------------------------------
    # run()
    # -----------------------------------------------------------------------

    def run(self, company_name: str, spark, llm_endpoint: str) -> dict:
        self._reset_state()
        self._company_name = company_name
        print(f"  Running 6 tools ...")

        tr1 = self._tool_retrieve_kpi_dashboard(spark)
        tr2 = self._tool_retrieve_pipeline_backlog(spark)
        tr3 = self._tool_retrieve_delivery_model(spark)
        tr4 = self._tool_retrieve_healthcare_ops(spark)
        tr5 = self._tool_retrieve_headcount_attrition(spark)
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
    created_at               TIMESTAMP
) USING DELTA
"""


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------

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

    print(f"\n=== KPI Agent ({company_name}) ===")

    agent  = KPIAgent()
    result = agent.run(company_name=company_name, spark=spark, llm_endpoint=llm_endpoint)

    # Save to Delta
    table = f"{catalog}.analysis.kpi"
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.analysis")
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
        "created_at":              datetime.now(timezone.utc),
    }

    df = spark.createDataFrame([Row(**row_data)], schema=schema)
    df.write.format("delta").mode("append").saveAsTable(table)

    print(f"\n✓ Saved KPI output → {table}")

    # Export stakeholder report
    report_path = _write_stakeholder_report(result, catalog, spark)
    result["report_path"] = report_path
    print(f"✓ Stakeholder report → {report_path}")

    return result


if __name__ == "__main__":
    main()
