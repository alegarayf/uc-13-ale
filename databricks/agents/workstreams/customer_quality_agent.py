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
   note that in extraction_notes.\
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
        )
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
        )
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
        )
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
        )
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
        )
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

    def _tool_load_company_profile(self, company_name: str, spark):
        sql = f"SELECT * FROM uc13.classification.company_profile WHERE company_name = '{company_name}' ORDER BY created_at DESC LIMIT 1"
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
            source_docs=["uc13.classification.company_profile"],
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

    def run(self, company_name: str, spark, llm_endpoint: str) -> dict:
        self._reset_state()
        self._company_name = company_name
        print(f"  Running 6 tools ...")

        tr1 = self._tool_retrieve_customer_concentration(spark)
        tr2 = self._tool_retrieve_retention_metrics(spark)
        tr3 = self._tool_retrieve_customer_tenure(spark)
        tr4 = self._tool_retrieve_payor_mix(spark)
        tr5 = self._tool_retrieve_account_size(spark)
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
            "payor_mix_json":              json.dumps(extracted.get("payor_mix") or []),
            "contract_trigger_list":       [json.dumps(t) for t in trigger_list],
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

    print(f"\n=== Customer Quality Agent ({company_name}) ===")

    agent = CustomerQualityAgent()
    result = agent.run(company_name=company_name, spark=spark, llm_endpoint=llm_endpoint)

    table = f"{catalog}.analysis.customer_quality"
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.analysis")
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
        StructField("payor_mix_json",              StringType(),  True),
        StructField("contract_trigger_list",       ArrayType(StringType()), True),
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
        "payor_mix_json":             result.get("payor_mix_json"),
        "contract_trigger_list":      result.get("contract_trigger_list") or [],
        "flags":                      json.dumps(result.get("flags") or []),
        "discrepancies_json":         result.get("discrepancies_json"),
        "data_room_gaps":             result.get("data_room_gaps") or [],
        "citations":                  result.get("citations"),
        "reasoning_trace":            json.dumps(result.get("reasoning_trace") or []),
        "created_at":                 datetime.now(timezone.utc),
    }

    df = spark.createDataFrame([Row(**row_data)], schema=schema)
    df.write.format("delta").mode("append").saveAsTable(table)

    print(f"\n✓ Saved customer quality output → {table}")

    report_path = _write_stakeholder_report(result, catalog, spark)
    result["report_path"] = report_path
    print(f"✓ Stakeholder report → {report_path}")
    return result


if __name__ == "__main__":
    main()
