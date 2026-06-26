"""
legal_contracts_agent.py — Phase 3: Legal & Contracts Workstream Agent.

Extracts contract terms and litigation exposure from documents tagged LEGAL. Receives
contract review triggers from customer_quality_agent.py (customers >20% of revenue)
and prioritizes those contracts as "triggered reviews."

Does not provide legal advice. Produces a structured contract register and CoC
consent list for the deal team and outside counsel.

Phase 3 outputs:
  - Table {catalog}.analysis.legal (M0 write target)
  - Compat view {catalog}.analysis.legal_contracts (legacy consumers)

Dependencies:
  - uc13.ingestion.embeddings
  - uc13.classification.doc_relevance
  - uc13.classification.company_profile
  - uc13.analysis.customer_quality      (reads contract_trigger_list)
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
# Module-level helper
# ---------------------------------------------------------------------------

def _parse_int(value) -> Optional[int]:
    """Parse to int, stripping whitespace. Returns None on failure."""
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# LLM prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a senior PE investment analyst extracting structured contract terms and
litigation data from legal due diligence documents. Rules:
1. Extract ONLY what is explicitly stated in the provided context.
2. Do NOT infer, compute, assume, or hallucinate any value.
3. If a value is absent from the context, return null for that field.
4. Every extracted value must have a citation: document name, location
   (page number or section title), and a quote of ≤30 words.
5. Return ONLY valid JSON with no preamble and no markdown fences.
6. Extract one record per CONTRACT. Each record covers all extractable fields from
   the schema. A contract may be an MSA, SOW, lease, employment agreement, or other
   binding agreement.
7. Change-of-control (CoC): extract whether consent is required, the consent
   standard, and the ownership % threshold. If absent from the contract text,
   return null — do not infer.
8. Termination for convenience: extract yes/no, notice period in days, and any
   penalty. Language like "either party may terminate upon X days notice" qualifies.
9. Anti-assignment: extract yes/no and whether it explicitly captures change of
   control as an assignment trigger.
10. Litigation register: capture every mention of open legal matters, demand letters,
    regulatory correspondence, or disclosed litigation. Do not filter or minimize.
11. IMPORTANT: This agent does NOT provide legal advice. Never opine on
    enforceability or legal outcome. Extract facts only.\
"""

_USER_PROMPT_TEMPLATE = """\
COMPANY PROFILE (from Phase 2 output):
{company_profile_json}

{trigger_context}

RETRIEVED DOCUMENT CONTEXT:
{combined_chunk_text}

Extract legal and contract fields and return this exact JSON structure:
{{
  "contract_register": [
    {{
      "contract_id": "<sequential integer starting at 1>",
      "counterparty_name": "<name as stated>",
      "contract_type": "<MSA | SOW | Lease | Employment | Partnership | License | Other>",
      "contract_date": "<date as stated or null>",
      "revenue_pct": "<% of revenue if identified as material customer, else null>",
      "triggered_review": "<true if counterparty matches contract_trigger_list, false otherwise>",
      "change_of_control": {{
        "clause_present": "<true | false | not_found>",
        "consent_required": "<true | false | null>",
        "consent_standard": "<description as stated or null>",
        "ownership_threshold_pct": "<% as stated or null>"
      }},
      "termination_for_convenience": {{
        "present": "<true | false | not_found>",
        "notice_days": "<integer as stated or null>",
        "penalty": "<description as stated or null>"
      }},
      "anti_assignment": {{
        "present": "<true | false | not_found>",
        "captures_coc": "<true | false | null>"
      }},
      "auto_renewal": {{
        "present": "<true | false | not_found>",
        "notice_for_non_renewal_days": "<integer or null>"
      }},
      "pricing_terms": {{
        "structure": "<fixed | indexed | customer_reset | escalator | null>",
        "customer_repricing_rights": "<true | false | null>"
      }},
      "liability_cap": {{
        "capped": "<true | false | null>",
        "cap_amount_note": "<description or null>",
        "unusual_indemnity": "<true | false | null>"
      }},
      "exclusivity_mfn_noncompete": {{
        "present": "<true | false | not_found>",
        "scope_note": "<description as stated or null>"
      }},
      "ip_data_obligations_note": "<key obligations as stated or null>",
      "source_doc": "<filename>",
      "source_location": "<page or section>",
      "raw_quote": "<≤30 word quote from a key clause>"
    }}
  ],
  "litigation_register": [
    {{
      "matter_type": "<lawsuit | arbitration | regulatory | demand_letter | settlement | other>",
      "description": "<as stated>",
      "counterparty": "<name as stated or null>",
      "status": "<open | closed | unknown>",
      "estimated_exposure": "<$ as stated or null>",
      "source_doc": "<filename>",
      "source_location": "<page or section>"
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
  "executive_summary": "<2–3 sentence factual description of contract register scope, CoC exposure, and any litigation. Describe what was found — do not opine on legal outcome.>",
  "extraction_notes": "<missing contracts, ambiguous clauses, documents not reviewed>"
}}\
"""


# ---------------------------------------------------------------------------
# Domain pass registry (spec §5.6.3 / §5.11)
# ---------------------------------------------------------------------------

_DOMAIN_PASS_BUDGETS: dict[str, dict] = {
    "contracts_vendors_platform": {
        "top_k": 14,
        "min_chunk_length": 150,
        "max_chars": 20_000,
        "max_tokens": 12_000,
        # A0: broaden beyond generic MSA tokens — lease/SA/staffing dominate Elder Care LEGAL
        "file_name_filter": [
            "Contract", "MSA", "Agreement", "SOW", "Customer", "Client", "Vendor", "Supplier",
            "SA", "Lease", "Sublease", "Staffing", "Purchase", "Temp", "Marketing", "Engagement",
        ],
    },
    "employment": {
        "top_k": 10,
        "min_chunk_length": 150,
        "max_chars": 15_000,
        "max_tokens": 10_000,
        # A0: handbook/orientation/401(k) filenames — default Employment|Offer returned 0 chunks
        "file_name_filter": [
            "Employment", "Offer", "Contractor", "Commission", "Founder",
            "Handbook", "Orientation", "401", "Restricted", "Stock", "Bylaws",
        ],
    },
    "litigation": {
        "top_k": 8,
        "min_chunk_length": 150,
        "max_chars": 15_000,
        "max_tokens": 10_000,
        # A0: regulatory survey + bond filenames — default Litigation|Dispute returned 0 chunks
        "file_name_filter": [
            "Litigation", "Dispute", "Legal", "Demand", "Regulatory",
            "Survey", "DOH", "Bond", "Compliance", "Engagement",
        ],
    },
    "ip_privacy": {
        "top_k": 8,
        "min_chunk_length": 150,
        "max_chars": 15_000,
        "max_tokens": 10_000,
        "file_name_filter": [
            "IP", "Privacy", "GDPR", "HIPAA", "OSS", "Data Processing", "BAA",
        ],
    },
    "insurance": {
        "top_k": 6,
        "min_chunk_length": 150,
        "max_chars": 12_000,
        "max_tokens": 8_000,
        "file_name_filter": [
            "Insurance", "Policy", "COI", "Indemnity", "Bond", "Renewal",
        ],
    },
}

# Per-pass semantic queries — tuned from A0 corpus decomposition (§5.6.3 / B2).
_DOMAIN_PASS_QUERIES: dict[str, str] = {
    "contracts_vendors_platform": (
        "material customer contract MSA master service agreement statement of work "
        "change of control termination vendor supplier platform reseller channel "
        "staffing agreement lease sublease asset purchase marketing contract"
    ),
    "employment": (
        "employment agreement offer letter contractor commission plan founder key employee "
        "employee handbook orientation restricted stock non-compete non-solicit "
        "severance 401k bylaws staffing agreement"
    ),
    "litigation": (
        "litigation lawsuit dispute regulatory compliance arbitration demand letter "
        "settlement survey DOH approval bond renewal regulatory correspondence "
        "threatened claim legal engagement letter"
    ),
    "ip_privacy": (
        "intellectual property IP ownership assignment data privacy GDPR HIPAA "
        "indemnification liability cap open source OSS data processing agreement BAA"
    ),
    "insurance": (
        "insurance certificate policy COI certificate of insurance indemnity "
        "coverage bond renewal liability unusual indemnity"
    ),
}

# Static registry: pass_id + budget_dict per §5.11 (retrieve/extract fns bound at runtime).
_DOMAIN_PASSES: list[tuple[str, dict]] = [
    (pass_id, _DOMAIN_PASS_BUDGETS[pass_id])
    for pass_id in (
        "contracts_vendors_platform",
        "employment",
        "litigation",
        "ip_privacy",
        "insurance",
    )
]


def _bind_domain_passes(agent: "LegalContractsAgent") -> list[tuple]:
    """Materialize full _DOMAIN_PASSES tuples with bound instance methods."""
    return [
        (
            pass_id,
            getattr(agent, f"_domain_retrieve_{pass_id}"),
            getattr(agent, f"_extract_{pass_id}"),
            budget,
        )
        for pass_id, budget in _DOMAIN_PASSES
    ]


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

from agents.shared.agent_base import WorkstreamAgent


class LegalContractsAgent(WorkstreamAgent):
    """Phase 3 Legal & Contracts workstream agent."""

    agent_name = "legal_contracts"

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

    def _load_contract_triggers(self, company_name: str, spark) -> list:
        """Load contract review triggers from Customer Quality Agent output.

        Returns list of trigger dicts. Returns empty list if table not found or
        Customer Quality Agent has not yet run — graceful fallback so this agent
        can produce output independently.
        """
        try:
            rows = spark.sql(f"""
                SELECT contract_trigger_list FROM {self._catalog}.analysis.customer_quality
                WHERE company_name = '{company_name}'
                ORDER BY created_at DESC LIMIT 1
            """).collect()
            if rows and rows[0]["contract_trigger_list"]:
                return [json.loads(t) for t in rows[0]["contract_trigger_list"]]
        except Exception:
            pass
        self._add_gap(
            "contract_trigger_list not found — Customer Quality Agent has not run or "
            "returned no material customers. Legal Agent proceeding without triggered reviews."
        )
        return []

    # -----------------------------------------------------------------------
    # Retrieval tools
    # -----------------------------------------------------------------------

    def _tool_retrieve_material_contracts(self, spark) -> "ToolResult":  # noqa: F821
        from agents.shared.retrieval import semantic_search
        query = (
            "material customer contract MSA master service agreement "
            "statement of work change of control termination"
        )
        chunks = semantic_search(
            query=query,
            spark=spark,
            company_name=self._company_name,
            top_k=12,
            workstream_filter=["LEGAL"],
            file_name_filter=["Contract", "MSA", "Agreement", "SOW", "Customer", "Client"],
            min_chunk_length=150,
            catalog=self._catalog,
        )
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_material_contracts",
            input_summary=f"query='{query[:80]}…' | workstream=LEGAL | top_k=12 | file_name_filter=[Contract, MSA, Agreement, SOW, Customer, Client]",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_retrieve_coc_and_termination(self, spark) -> "ToolResult":  # noqa: F821
        from agents.shared.retrieval import semantic_search
        query = (
            "change of control consent termination for convenience "
            "notice period assignment anti-assignment"
        )
        chunks = semantic_search(
            query=query,
            spark=spark,
            company_name=self._company_name,
            top_k=10,
            workstream_filter=["LEGAL"],
            min_chunk_length=150,
            catalog=self._catalog,
        )
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_coc_and_termination",
            input_summary=f"query='{query[:80]}…' | workstream=LEGAL | top_k=10",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_retrieve_restrictive_covenants(self, spark) -> "ToolResult":  # noqa: F821
        from agents.shared.retrieval import semantic_search
        query = (
            "exclusivity non-compete MFN most favored nation "
            "non-solicitation restrictive covenant"
        )
        chunks = semantic_search(
            query=query,
            spark=spark,
            company_name=self._company_name,
            top_k=6,
            workstream_filter=["LEGAL"],
            min_chunk_length=150,
            catalog=self._catalog,
        )
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_restrictive_covenants",
            input_summary=f"query='{query[:80]}…' | workstream=LEGAL | top_k=6",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_retrieve_litigation(self, spark) -> "ToolResult":  # noqa: F821
        from agents.shared.retrieval import semantic_search
        query = (
            "litigation lawsuit dispute regulatory compliance "
            "arbitration demand letter settlement"
        )
        chunks = semantic_search(
            query=query,
            spark=spark,
            company_name=self._company_name,
            top_k=8,
            workstream_filter=["LEGAL"],
            min_chunk_length=150,
            catalog=self._catalog,
        )
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_litigation",
            input_summary=f"query='{query[:80]}…' | workstream=LEGAL | top_k=8",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_retrieve_ip_and_data(self, spark) -> "ToolResult":  # noqa: F821
        from agents.shared.retrieval import semantic_search
        query = (
            "intellectual property IP ownership data privacy "
            "GDPR HIPAA indemnification liability cap"
        )
        chunks = semantic_search(
            query=query,
            spark=spark,
            company_name=self._company_name,
            top_k=6,
            workstream_filter=["LEGAL"],
            min_chunk_length=150,
            catalog=self._catalog,
        )
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name="retrieve_ip_and_data",
            input_summary=f"query='{query[:80]}…' | workstream=LEGAL | top_k=6",
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _tool_load_company_profile(self, company_name: str, spark) -> "ToolResult":  # noqa: F821
        try:
            rows = spark.sql(
                f"SELECT * FROM {self._catalog}.classification.company_profile "
                f"WHERE company_name = '{company_name}' "
                f"ORDER BY created_at DESC LIMIT 1"
            ).collect()
            if not rows:
                self._add_gap("company_profile not found — run company_profiler.py first")
                return self._tool_call(
                    tool_name="load_company_profile",
                    input_summary=f"SELECT * FROM {self._catalog}.classification.company_profile WHERE company_name='{company_name}'",
                    data=None,
                    output_summary="No rows returned — company_profile not found",
                    confidence="low",
                    source_docs=[],
                )
            row_dict = rows[0].asDict()
            return self._tool_call(
                tool_name="load_company_profile",
                input_summary=f"SELECT * FROM {self._catalog}.classification.company_profile WHERE company_name='{company_name}'",
                data=row_dict,
                output_summary=f"Company profile loaded for '{company_name}'",
                confidence="high",
                source_docs=[f"{self._catalog}.classification.company_profile"],
            )
        except Exception as exc:
            self._add_gap(f"company_profile query failed: {exc} — run company_profiler.py first")
            return self._tool_call(
                tool_name="load_company_profile",
                input_summary=f"SELECT * FROM {self._catalog}.classification.company_profile WHERE company_name='{company_name}'",
                data=None,
                output_summary=f"Query failed: {exc}",
                confidence="low",
                source_docs=[],
            )

    # -----------------------------------------------------------------------
    # Domain pass retrieval (B2 — D3a catalog-threaded fallback)
    # -----------------------------------------------------------------------

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
        """Semantic search with filename-filter retry; always passes catalog=self._catalog (D3a).

        Do not use the financial context_utils fallback helper — it defaults catalog to uc13.
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
            catalog=self._catalog,
        )

        if len(chunks) < min_results and file_name_filter is not None:
            step = len(self._trace) + 1
            self._trace.append({
                "step":       step,
                "tool":       "retrieval_fallback",
                "input":      (
                    f"file_name_filter returned {len(chunks)} chunks (< {min_results}); "
                    f"retrying without filter"
                ),
                "output":     "fallback retrieval active — all workstream-tagged documents searched",
                "confidence": "medium",
                "sources":    [],
            })
            print(
                f"  Step {step} [retrieval_fallback]: filter returned {len(chunks)} chunks, "
                f"retrying without filename filter"
            )
            chunks = semantic_search(
                query=query,
                spark=spark,
                company_name=self._company_name,
                top_k=top_k,
                workstream_filter=workstream_filter,
                file_name_filter=None,
                min_chunk_length=min_chunk_length,
                catalog=self._catalog,
            )

        return chunks

    def _domain_retrieve_pass(self, spark, pass_id: str) -> "ToolResult":  # noqa: F821
        """Run semantic retrieval for one domain pass using §5.6.3 budgets."""
        budget = _DOMAIN_PASS_BUDGETS[pass_id]
        query = _DOMAIN_PASS_QUERIES[pass_id]
        file_name_filter = budget["file_name_filter"]
        filter_preview = ", ".join(file_name_filter[:6])
        if len(file_name_filter) > 6:
            filter_preview += ", …"

        chunks = self._semantic_search_with_fallback(
            spark=spark,
            query=query,
            workstream_filter=["LEGAL"],
            top_k=budget["top_k"],
            file_name_filter=file_name_filter,
            min_chunk_length=budget["min_chunk_length"],
        )
        source_docs = list({c.file_name for c in chunks})
        confidence = "high" if chunks else "low"
        return self._tool_call(
            tool_name=f"domain_retrieve_{pass_id}",
            input_summary=(
                f"pass={pass_id} | workstream=LEGAL | top_k={budget['top_k']} | "
                f"file_name_filter=[{filter_preview}]"
            ),
            data=chunks,
            output_summary=f"{len(chunks)} chunks returned from {len(source_docs)} files",
            confidence=confidence,
            source_docs=source_docs,
        )

    def _domain_retrieve_contracts_vendors_platform(self, spark) -> "ToolResult":  # noqa: F821
        return self._domain_retrieve_pass(spark, "contracts_vendors_platform")

    def _domain_retrieve_employment(self, spark) -> "ToolResult":  # noqa: F821
        return self._domain_retrieve_pass(spark, "employment")

    def _domain_retrieve_litigation(self, spark) -> "ToolResult":  # noqa: F821
        return self._domain_retrieve_pass(spark, "litigation")

    def _domain_retrieve_ip_privacy(self, spark) -> "ToolResult":  # noqa: F821
        return self._domain_retrieve_pass(spark, "ip_privacy")

    def _domain_retrieve_insurance(self, spark) -> "ToolResult":  # noqa: F821
        return self._domain_retrieve_pass(spark, "insurance")

    # -----------------------------------------------------------------------
    # Domain pass extract (B3 — stubs until T3)
    # -----------------------------------------------------------------------

    def _extract_contracts_vendors_platform(
        self,
        chunks,
        company_profile,
        contract_triggers,
        extraction_endpoint: str,
        budget: dict,
    ) -> dict:
        self._tool_call(
            tool_name="domain_extract_contracts_vendors_platform",
            input_summary=f"pass=contracts_vendors_platform | {len(chunks)} chunks | stub (T3)",
            data=None,
            output_summary="0 contracts, 0 vendors, 0 platform deps",
            confidence="low",
            source_docs=[],
        )
        return {
            "contract_register": [],
            "vendor_register": [],
            "platform_dependency_register": [],
        }

    def _extract_employment(
        self,
        chunks,
        company_profile,
        contract_triggers,
        extraction_endpoint: str,
        budget: dict,
    ) -> dict:
        self._tool_call(
            tool_name="domain_extract_employment",
            input_summary=f"pass=employment | {len(chunks)} chunks | stub (T3)",
            data=None,
            output_summary="0 employment records",
            confidence="low",
            source_docs=[],
        )
        return {"employment_register": []}

    def _extract_litigation(
        self,
        chunks,
        company_profile,
        contract_triggers,
        extraction_endpoint: str,
        budget: dict,
    ) -> dict:
        self._tool_call(
            tool_name="domain_extract_litigation",
            input_summary=f"pass=litigation | {len(chunks)} chunks | stub (T3)",
            data=None,
            output_summary="0 litigation records",
            confidence="low",
            source_docs=[],
        )
        return {"litigation_register": []}

    def _extract_ip_privacy(
        self,
        chunks,
        company_profile,
        contract_triggers,
        extraction_endpoint: str,
        budget: dict,
    ) -> dict:
        self._tool_call(
            tool_name="domain_extract_ip_privacy",
            input_summary=f"pass=ip_privacy | {len(chunks)} chunks | stub (T3)",
            data=None,
            output_summary="0 IP records, 0 privacy/security records",
            confidence="low",
            source_docs=[],
        )
        return {"ip_register": [], "privacy_security_register": []}

    def _extract_insurance(
        self,
        chunks,
        company_profile,
        contract_triggers,
        extraction_endpoint: str,
        budget: dict,
    ) -> dict:
        self._tool_call(
            tool_name="domain_extract_insurance",
            input_summary=f"pass=insurance | {len(chunks)} chunks | stub (T3)",
            data=None,
            output_summary="0 insurance records",
            confidence="low",
            source_docs=[],
        )
        return {"insurance_register": []}

    # -----------------------------------------------------------------------
    # Roll-up computations (deterministic Python — no LLM)
    # -----------------------------------------------------------------------

    def _build_coc_consent_list(self, contract_register: list) -> list:
        """All contracts where change_of_control.consent_required == 'true'."""
        return [
            {
                "contract_id": c.get("contract_id"),
                "counterparty_name": c.get("counterparty_name"),
                "revenue_pct": c.get("revenue_pct"),
                "consent_standard_note": c.get("change_of_control", {}).get("consent_standard"),
            }
            for c in contract_register
            if str(c.get("change_of_control", {}).get("consent_required", "")).lower() == "true"
        ]

    def _build_termination_exposure(self, contract_register: list) -> list:
        """Contracts with termination for convenience AND notice < 90 days."""
        result = []
        for c in contract_register:
            tfc = c.get("termination_for_convenience", {})
            if str(tfc.get("present", "")).lower() != "true":
                continue
            notice = _parse_int(tfc.get("notice_days"))
            if notice is not None and notice < 90:
                result.append({
                    "contract_id": c.get("contract_id"),
                    "counterparty_name": c.get("counterparty_name"),
                    "notice_days": notice,
                    "revenue_pct": c.get("revenue_pct"),
                })
        return result

    def _build_restrictive_covenant_map(self, contract_register: list) -> list:
        return [
            {
                "contract_id": c.get("contract_id"),
                "counterparty_name": c.get("counterparty_name"),
                "scope_note": c.get("exclusivity_mfn_noncompete", {}).get("scope_note"),
            }
            for c in contract_register
            if str(c.get("exclusivity_mfn_noncompete", {}).get("present", "")).lower() == "true"
        ]

    # -----------------------------------------------------------------------
    # Threshold flagging
    # -----------------------------------------------------------------------

    def _apply_legal_flags(self, extracted: dict, contract_triggers: list):
        contract_register = extracted.get("contract_register") or []
        litigation_register = extracted.get("litigation_register") or []

        trigger_names = {(t.get("customer_name") or "").lower() for t in contract_triggers}

        triggered_contracts = [
            c for c in contract_register
            if str(c.get("triggered_review", "")).lower() == "true"
        ]

        matched_triggers = set()
        for c in triggered_contracts:
            cpname = c.get("counterparty_name", "")
            rev_pct = c.get("revenue_pct")
            try:
                rev_num = float(str(rev_pct).replace("%", "").strip())
            except (ValueError, TypeError):
                rev_num = None

            matched_triggers.add(cpname.lower())

            coc = c.get("change_of_control", {})
            if str(coc.get("consent_required", "")).lower() == "true" and (rev_num is None or rev_num > 20):
                self._add_flag(
                    metric="coc_consent_required_material_customer",
                    value=f"{cpname} — CoC consent required, revenue_pct={rev_pct}",
                    threshold="CoC consent + >20% revenue (triggered review)",
                    severity="Red",
                    note=(
                        f"CoC consent required for {cpname} ({rev_pct} of revenue) — "
                        f"deal-relevant. Must obtain consent pre-close. "
                        f"Source: {c.get('source_doc', '')}."
                    ),
                    source_doc=c.get("source_doc", ""),
                    confidence="high",
                )

            tfc = c.get("termination_for_convenience", {})
            notice = _parse_int(tfc.get("notice_days"))
            if (
                str(tfc.get("present", "")).lower() == "true"
                and notice is not None
                and notice < 60
                and (rev_num is None or rev_num > 20)
            ):
                self._add_flag(
                    metric="short_termination_notice_material_customer",
                    value=f"{cpname} — notice={notice} days, revenue_pct={rev_pct}",
                    threshold="<60 days notice on >20% revenue customer",
                    severity="Red",
                    note=(
                        f"Termination for convenience with {notice}-day notice on material "
                        f"customer ({cpname}, {rev_pct} of revenue). "
                        f"Acquirer exposed to rapid revenue loss post-close."
                    ),
                    source_doc=c.get("source_doc", ""),
                    confidence="high",
                )

        for trigger in contract_triggers:
            tname = (trigger.get("customer_name") or "").lower()
            if tname not in {(c.get("counterparty_name") or "").lower() for c in contract_register}:
                self._add_gap(
                    f"Contract not found for {trigger.get('customer_name')} "
                    f"({trigger.get('revenue_pct')}% of revenue) — "
                    f"high-priority information request"
                )

        for c in contract_register:
            cpname = c.get("counterparty_name", "")
            rev_pct = c.get("revenue_pct")
            try:
                rev_num = float(str(rev_pct).replace("%", "").strip())
            except (ValueError, TypeError):
                rev_num = None
            source_doc = c.get("source_doc", "")

            auto = c.get("auto_renewal", {})
            if str(auto.get("present", "")).lower() == "false" and rev_num is not None and rev_num > 10:
                self._add_flag(
                    metric="no_auto_renewal_material_customer",
                    value=f"{cpname} — auto_renewal=false, revenue_pct={rev_pct}",
                    threshold="No auto-renewal on >10% revenue customer",
                    severity="Yellow",
                    note=(
                        f"No auto-renewal on >10% customer ({cpname}, {rev_pct} of revenue). "
                        f"Revenue continuity risk at contract expiration. "
                        f"Source: {source_doc}."
                    ),
                    source_doc=source_doc,
                    confidence="high",
                )

            exc = c.get("exclusivity_mfn_noncompete", {})
            if str(exc.get("present", "")).lower() == "true":
                scope = exc.get("scope_note", "scope not stated")
                self._add_flag(
                    metric="restrictive_covenant",
                    value=f"{cpname}: {scope}",
                    threshold="Any restrictive covenant (exclusivity/MFN/non-compete)",
                    severity="Yellow",
                    note=(
                        f"Restrictive covenant ({scope}) found in {cpname} contract. "
                        f"May limit add-on M&A options. Source: {source_doc}."
                    ),
                    source_doc=source_doc,
                    confidence="high",
                )

            liab = c.get("liability_cap", {})
            if str(liab.get("unusual_indemnity", "")).lower() == "true":
                self._add_flag(
                    metric="unusual_indemnity",
                    value=f"{cpname} — unusual_indemnity=true",
                    threshold="Unusual indemnity scope",
                    severity="Yellow",
                    note=(
                        f"Unusual indemnity scope in {cpname} contract. "
                        f"Refer to outside counsel for assessment. Source: {source_doc}."
                    ),
                    source_doc=source_doc,
                    confidence="medium",
                )

        for item in litigation_register:
            status = (item.get("status") or "").lower()
            matter_type = item.get("matter_type", "unknown")
            description = item.get("description", "")
            source_doc = item.get("source_doc", "")

            if status == "open":
                self._add_flag(
                    metric=f"open_legal_matter_{matter_type}",
                    value=f"{matter_type}: {description[:80]}",
                    threshold="Any open legal matter",
                    severity="Red",
                    note=(
                        f"Open legal matter ({matter_type}): {description[:200]}. "
                        f"Source: {source_doc}."
                    ),
                    source_doc=source_doc,
                    confidence="high",
                )
            elif matter_type == "regulatory":
                self._add_flag(
                    metric="regulatory_matter",
                    value=f"regulatory: {description[:80]}",
                    threshold="Any regulatory matter (regardless of status)",
                    severity="Red",
                    note=(
                        f"Regulatory matter (status={status}): {description[:200]}. "
                        f"Source: {source_doc}."
                    ),
                    source_doc=source_doc,
                    confidence="high",
                )

    # -----------------------------------------------------------------------
    # run()
    # -----------------------------------------------------------------------

    def run(self, company_name: str, spark, extraction_endpoint: str, catalog: str) -> dict:
        self._reset_state()
        self._company_name = company_name
        self._catalog = catalog

        # Stage 1 — company profile + contract triggers (D8a: read-only triggers)
        print(f"  Loading contract triggers ...")
        contract_triggers = self._load_contract_triggers(company_name, spark)

        print(f"  Loading company profile ...")
        profile_result = self._tool_load_company_profile(company_name, spark)
        company_profile = profile_result.data

        # Pass-owned register accumulators (M1 interim — no cross-pass merge)
        registers: dict[str, list] = {
            "contract_register": [],
            "vendor_register": [],
            "platform_dependency_register": [],
            "employment_register": [],
            "litigation_register": [],
            "ip_register": [],
            "privacy_security_register": [],
            "insurance_register": [],
        }

        domain_passes = _bind_domain_passes(self)
        print(f"  Running {len(domain_passes)} domain passes ...")
        for pass_id, retrieve_fn, extract_fn, budget in domain_passes:
            retrieve_result = retrieve_fn(spark)
            chunks = retrieve_result.data or []
            print(f"    [{pass_id}] retrieve: {len(chunks)} chunks")

            extracted = extract_fn(
                chunks,
                company_profile,
                contract_triggers,
                extraction_endpoint,
                budget,
            )
            for key, rows in extracted.items():
                if key in registers and rows:
                    registers[key].extend(rows)

            register_summary = ", ".join(
                f"{k}={len(extracted.get(k, []))}"
                for k in sorted(extracted.keys())
            )
            print(f"    [{pass_id}] extract: {register_summary}")

        return {
            "company_name":                  company_name,
            "executive_summary":             None,
            "contract_register_json":        json.dumps(registers["contract_register"]),
            "litigation_register_json":      json.dumps(registers["litigation_register"]),
            "coc_consent_list_json":         json.dumps([]),
            "termination_exposure_json":     json.dumps([]),
            "restrictive_covenant_map_json": json.dumps([]),
            "triggered_reviews_loaded":      len(contract_triggers),
            "flags":                         [],
            "data_room_gaps":                list(self._data_room_gaps),
            "citations":                     json.dumps(self._citations_as_dicts()),
            "reasoning_trace":               list(self._trace),
            "created_at":                    datetime.now(timezone.utc).isoformat(),
        }


# ---------------------------------------------------------------------------
# Stakeholder report export
# ---------------------------------------------------------------------------

def _write_stakeholder_report(result: dict, catalog: str, spark) -> str:
    """Write a clean, human-readable YAML report to a UC Volume.

    Saves to /Volumes/{catalog}/analysis/reports/{company_name}/
    legal_contracts_report.yaml (or .json if PyYAML is unavailable).
    Returns the full volume path of the written file.
    """
    company_name = result["company_name"]

    contract_register   = json.loads(result.get("contract_register_json")        or "[]")
    litigation_register = json.loads(result.get("litigation_register_json")       or "[]")
    coc_consent_list    = json.loads(result.get("coc_consent_list_json")          or "[]")
    termination_exp     = json.loads(result.get("termination_exposure_json")      or "[]")
    covenant_map        = json.loads(result.get("restrictive_covenant_map_json")  or "[]")
    citations           = json.loads(result.get("citations")                      or "[]")

    report = {
        "report": {
            "agent":        "legal_contracts",
            "company":      company_name,
            "generated_at": result.get("created_at", ""),
        },
        "executive_summary":       result.get("executive_summary"),
        "contract_register":       contract_register,
        "coc_consent_list":        coc_consent_list,
        "termination_exposure":    termination_exp,
        "restrictive_covenant_map": covenant_map,
        "litigation_register":     litigation_register,
        "triggered_reviews_loaded": result.get("triggered_reviews_loaded", 0),
        "flags":                   result.get("flags") or [],
        "data_room_gaps":          result.get("data_room_gaps") or [],
        "citations":               citations,
    }

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

    spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.analysis.reports")
    safe_name = company_name.replace(" ", "_").replace("/", "_")
    dir_path = f"/Volumes/{catalog}/analysis/reports/{safe_name}"
    os.makedirs(dir_path, exist_ok=True)

    file_path = f"{dir_path}/legal_contracts_report.{ext}"
    with open(file_path, "w", encoding="utf-8") as fh:
        fh.write(content)

    return file_path


# ---------------------------------------------------------------------------
# Delta table DDL — Appendix A (legal_agent.md v0.2.2)
# ---------------------------------------------------------------------------

_EXPECTED_COLS = {
    "company_name",
    "executive_summary",
    "section_confidence",
    "contract_register_json",
    "vendor_register_json",
    "platform_dependency_register_json",
    "employment_register_json",
    "litigation_register_json",
    "privacy_security_register_json",
    "ip_register_json",
    "insurance_register_json",
    "coc_consent_list_json",
    "termination_exposure_json",
    "restrictive_covenant_map_json",
    "unable_to_assess_json",
    "recommended_diligence_json",
    "flags",
    "data_room_gaps",
    "citations",
    "reasoning_trace",
    "created_at",
}

_CREATE_LEGAL_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {catalog}.analysis.legal (
    company_name                          STRING,
    executive_summary                     STRING,
    section_confidence                    STRING,
    contract_register_json                STRING,
    vendor_register_json                  STRING,
    platform_dependency_register_json     STRING,
    employment_register_json              STRING,
    litigation_register_json              STRING,
    privacy_security_register_json        STRING,
    ip_register_json                      STRING,
    insurance_register_json               STRING,
    coc_consent_list_json                 STRING,
    termination_exposure_json             STRING,
    restrictive_covenant_map_json         STRING,
    unable_to_assess_json                 STRING,
    recommended_diligence_json            STRING,
    flags                                 STRING,
    data_room_gaps                        ARRAY<STRING>,
    citations                             STRING,
    reasoning_trace                       STRING,
    created_at                            TIMESTAMP
) USING DELTA
"""

_CREATE_LEGAL_CONTRACTS_VIEW_SQL = """
CREATE OR REPLACE VIEW {catalog}.analysis.legal_contracts AS
SELECT
  company_name, executive_summary,
  contract_register_json, litigation_register_json,
  coc_consent_list_json, termination_exposure_json, restrictive_covenant_map_json,
  0 AS triggered_reviews_loaded,
  flags, data_room_gaps, citations, reasoning_trace, created_at
FROM {catalog}.analysis.legal
"""


def _map_legacy_result_to_legal_row(result: dict) -> dict:
    """Map legacy run() output to analysis.legal row; MVP-only columns get empty JSON."""
    return {
        "company_name":                  result["company_name"],
        "executive_summary":             result.get("executive_summary"),
        "section_confidence":            None,
        "contract_register_json":        result.get("contract_register_json"),
        "vendor_register_json":          "[]",
        "platform_dependency_register_json": "[]",
        "employment_register_json":      "[]",
        "litigation_register_json":      result.get("litigation_register_json"),
        "privacy_security_register_json": "[]",
        "ip_register_json":              "[]",
        "insurance_register_json":       "[]",
        "coc_consent_list_json":         result.get("coc_consent_list_json"),
        "termination_exposure_json":     result.get("termination_exposure_json"),
        "restrictive_covenant_map_json": result.get("restrictive_covenant_map_json"),
        "unable_to_assess_json":         "[]",
        "recommended_diligence_json":    "[]",
        "flags":                         json.dumps(result.get("flags") or []),
        "data_room_gaps":                result.get("data_room_gaps") or [],
        "citations":                     result.get("citations"),
        "reasoning_trace":               json.dumps(result.get("reasoning_trace") or []),
        "created_at":                    datetime.now(timezone.utc),
    }


def _ensure_legal_storage(catalog: str, spark) -> None:
    """Idempotent Appendix A DDL: analysis.legal table + legal_contracts compat view."""
    legal_table = f"{catalog}.analysis.legal"
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.analysis")

    try:
        live_cols = {f.name for f in spark.table(legal_table).schema.fields}
        if not _EXPECTED_COLS.issubset(live_cols):
            missing = _EXPECTED_COLS - live_cols
            print(f"  [schema_migration] {legal_table}: dropping stale table. Missing: {sorted(missing)}")
            spark.sql(f"DROP TABLE IF EXISTS {legal_table}")
    except Exception:
        pass

    spark.sql(_CREATE_LEGAL_TABLE_SQL.format(catalog=catalog))
    spark.sql(f"DROP TABLE IF EXISTS {catalog}.analysis.legal_contracts")
    spark.sql(_CREATE_LEGAL_CONTRACTS_VIEW_SQL.format(catalog=catalog))


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------

def main() -> dict:
    repo_root = find_repo_root()
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    company_name        = get_param("sp_company_name")
    catalog             = get_param("catalog",             default="uc13_ale")
    _widget_ep          = get_param("extraction_endpoint", default="databricks-claude-sonnet-4-6") or "databricks-claude-sonnet-4-6"
    llm_endpoint        = get_param("llm_endpoint",        default=_widget_ep)

    if "haiku" in _widget_ep.lower() or "llama" in _widget_ep.lower():
        extraction_endpoint = "databricks-claude-sonnet-4-6"
        print(f"  [override] extraction_endpoint '{_widget_ep}' → Sonnet (Haiku/Llama cap=8192 tokens; legal multi-pass schema needs Sonnet)")
    else:
        extraction_endpoint = _widget_ep

    from pyspark.sql import SparkSession
    spark = SparkSession.getActiveSession()
    if spark is None:
        raise RuntimeError("No active Spark session.")

    print(f"\n=== Legal Contracts Agent ({company_name}) ===")
    print(f"  catalog={catalog}  extraction_endpoint={extraction_endpoint}  llm_endpoint={llm_endpoint}")
    print(f"  write target={catalog}.analysis.legal")

    _ensure_legal_storage(catalog, spark)

    agent = LegalContractsAgent()
    result = agent.run(
        company_name=company_name,
        spark=spark,
        extraction_endpoint=extraction_endpoint,
        catalog=catalog,
    )

    table = f"{catalog}.analysis.legal"
    spark.sql(f"DELETE FROM {table} WHERE company_name = '{company_name}'")

    from pyspark.sql import Row
    from pyspark.sql.types import (
        StructType, StructField, StringType,
        ArrayType, TimestampType,
    )

    schema = StructType([
        StructField("company_name",                          StringType(),            True),
        StructField("executive_summary",                     StringType(),            True),
        StructField("section_confidence",                    StringType(),            True),
        StructField("contract_register_json",                StringType(),            True),
        StructField("vendor_register_json",                  StringType(),            True),
        StructField("platform_dependency_register_json",     StringType(),            True),
        StructField("employment_register_json",              StringType(),            True),
        StructField("litigation_register_json",              StringType(),            True),
        StructField("privacy_security_register_json",        StringType(),            True),
        StructField("ip_register_json",                      StringType(),            True),
        StructField("insurance_register_json",               StringType(),            True),
        StructField("coc_consent_list_json",                 StringType(),            True),
        StructField("termination_exposure_json",             StringType(),            True),
        StructField("restrictive_covenant_map_json",         StringType(),            True),
        StructField("unable_to_assess_json",                 StringType(),            True),
        StructField("recommended_diligence_json",            StringType(),            True),
        StructField("flags",                                 StringType(),            True),
        StructField("data_room_gaps",                        ArrayType(StringType()), True),
        StructField("citations",                             StringType(),            True),
        StructField("reasoning_trace",                       StringType(),            True),
        StructField("created_at",                            TimestampType(),         True),
    ])

    row_data = _map_legacy_result_to_legal_row(result)

    df = spark.createDataFrame([Row(**row_data)], schema=schema)
    df.write.format("delta").mode("append").saveAsTable(table)

    print(f"\n✓ Saved legal output → {table}")

    report_path = _write_stakeholder_report(result, catalog, spark)
    result["report_path"] = report_path
    print(f"✓ Stakeholder report → {report_path}")

    return result


if __name__ == "__main__":
    main()
