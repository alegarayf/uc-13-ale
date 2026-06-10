"""
business_model_agent.py — Phase 3: Business Model Workstream Agent.

Extracts the business model profile of the target company from documents tagged
BUSINESS_MODEL. Produces one revenue model durability rating (Green/Yellow/Red),
a structured company description, and a rich multi-field output covering pricing,
customer profile, sales motion, revenue visibility, key dependencies, and recent
model changes. Writes output to uc13.analysis.business_model.

Portability: works against any data room regardless of industry overlay (healthcare,
tech_services, b2b_saas, industrial, consumer) or deal type (banked CIM vs. non-banked
management materials). Overlay-specific fields are nested under overlay_specific blocks
and completeness checks are gated on the confirmed overlay.

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
You are a senior PE investment analyst extracting structured business model
information from due diligence documents. You must follow all rules below precisely.

EXTRACTION RULES:
1. Extract ONLY what is explicitly stated in the provided context. Never infer,
   compute, assume, or hallucinate any value.
2. If a value is absent from the context, return null for that field.
3. Every extracted value must have a citation: document name, location (page
   number or section title), and a ≤30-word direct quote from the source.
4. Return ONLY valid JSON with no preamble, no commentary, and no markdown fences.
5. COMPANY PROFILE BLOCK IS METADATA ONLY: The block labelled "COMPANY PROFILE"
   is metadata used to configure thresholds. It is NOT a source document. Never
   cite "COMPANY PROFILE" as the source of any extracted value. All extracted
   values must come from the RETRIEVED DOCUMENT CONTEXT section only.
6. NON-BANKED DEALS: If the retrieved context does not include a
   Confidential Information Memorandum, Offering Memorandum, or equivalent
   banker-prepared marketing document, note this in extraction_notes and set
   confidence to "low" for all fields that would normally come from a CIM.
   Extract whatever is available from management accounts, financial models,
   board decks, or other documents present.

REVENUE MODEL TAG — choose exactly one:
  pure_recurring   → subscription, SaaS, contracted ARR; predictable period revenue
  repeat_services  → non-contracted but strongly habitual repeat business
  project_based    → discrete engagements; consulting, construction, custom dev
  transactional    → volume-driven, no commitment; e-commerce, per-use
  usage_based      → metered; cloud compute, API calls, utilities
  licensing        → IP or brand licensing; software licenses, franchises
  marketplace      → take-rate on third-party transactions
  hybrid           → material mix of two or more (state the mix in pct_split)

SALES MOTION TAG — choose exactly one:
  founder_led      → CEO/founder directly involved in major deals
  enterprise_sales → dedicated AE/BD team, structured deal process
  channel_partner  → relies on resellers, partners, or referral networks
  inbound_plg      → product-led or marketing-driven, low-touch
  outbound         → SDR/BDR-driven prospecting
  relationship     → relationship managers and network cultivation (common in
                     healthcare, professional services, financial services)

PRODUCTS AND SERVICES — margin by offering:
  Extract one record per distinct service type or product line. If the document
  shows margin at multiple levels of granularity (e.g. by service type AND by
  geography), use the service-type level as the primary record and note the
  geographic range. State ranges where multiple values appear — do not average.

OVERLAY-SPECIFIC FIELDS:
  The overlay_specific block contains fields that are only relevant for certain
  industry overlays. Only populate the sub-block that matches the confirmed
  overlay from the company profile. Return empty arrays for non-applicable blocks.
  Do NOT omit the overlay_specific block entirely — return it with empty arrays.\
"""

_USER_PROMPT_TEMPLATE = """\
COMPANY PROFILE (metadata only — do NOT extract values from this block):
{company_profile_json}

DEAL TYPE CONTEXT:
{deal_type_context}

RETRIEVED DOCUMENT CONTEXT (extract ALL values from here only):
{combined_chunk_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXTRACTION TASK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Extract the complete business model profile from the RETRIEVED DOCUMENT CONTEXT.
Apply all system prompt rules. Return null for any field not stated in the
documents — do not guess. Return ONLY the JSON object below.

{{
  "revenue_model": {{
    "tag": "<choose one tag from the system prompt list>",
    "pct_split": "<stated split or null — e.g. '70% repeat-services, 30% project'>",
    "note": "<1–2 sentence description of how the company earns revenue>",
    "source_doc": "<exact VDR filename — must NOT be 'COMPANY PROFILE'>",
    "source_location": "<page or section>"
  }},

  "products_services": [
    {{
      "name": "<exact product or service line name as stated>",
      "revenue_pct": "<% of total revenue as stated, or null>",
      "revenue_dollars": "<$ as stated, or null>",
      "gm_pct_stated": "<gross margin % as stated — state a range if multiple values, e.g. '43.7%–52.8%'>",
      "gm_pct_note": "<context for the margin figure — e.g. 'range across 6 office locations' or 'FY2023 blended'>",
      "avg_price_or_rate": "<stated price, rate, or ACV — e.g. '$37/hr', '$510/day', '$120K ACV', or null>",
      "growth_note": "<growth rate or trend as stated, or null>",
      "source_doc": "<exact VDR filename>",
      "source_location": "<page or section>"
    }}
  ],

  "customer_profile": {{
    "segments_description": "<description of who the customers are — demographics, company size, buyer type>",
    "end_markets": ["<end market 1>", "<end market 2>"],
    "geographic_concentration": "<description of customer or revenue concentration by region/state/country as stated, or null>",
    "client_tenure": {{
      "avg_tenure_stated": "<average tenure as stated — e.g. '2.3 years' or '60% stay >6 months', or null>",
      "tenure_distribution_note": "<any stated distribution of tenure lengths, or null>",
      "source_doc": "<exact filename or null>"
    }},
    "overlay_specific": {{
      "healthcare": {{
        "referral_source_breakdown": [
          {{
            "source_type": "<e.g. 'Rehab / Nursing Home' or 'Hospital'>",
            "pct_of_volume_or_profit": "<% as stated>",
            "period": "<period>",
            "source_doc": "<exact filename>"
          }}
        ],
        "payor_mix": [
          {{
            "payor_type": "<e.g. 'Private Pay' or 'Medicare' or 'Medicaid'>",
            "pct_of_revenue": "<% as stated or null>",
            "source_doc": "<exact filename>"
          }}
        ]
      }},
      "tech_services": {{
        "customer_size_mix": "<description of enterprise vs. mid-market vs. SMB split as stated, or null>",
        "vertical_concentration": "<any stated vertical or industry concentration, or null>"
      }},
      "b2b_saas": {{
        "arr_by_tier": "<any stated ARR split by plan tier or segment, or null>",
        "icp_description": "<ideal customer profile as stated, or null>"
      }}
    }}
  }},

  "sales_motion": {{
    "tag": "<choose one tag from the system prompt list>",
    "description": "<factual description of the sales process as described in the documents>",
    "key_roles": ["<e.g. 'VP of Sales — 15+ years industry experience' or 'Founder-led enterprise AEs'>"],
    "process_note": "<any stated touchpoint cadence, deal cycle length, or qualification process>",
    "compensation_model": "<salesperson/BD compensation structure as stated, or null>",
    "source_doc": "<exact VDR filename>",
    "source_location": "<page or section>"
  }},

  "revenue_visibility": {{
    "contracted_pct_of_forward_12mo": "<% as stated or null>",
    "backlog_coverage_months": "<months as stated or null>",
    "backlog_dollars": "<$ backlog as stated or null>",
    "pipeline_description": "<any forward revenue pipeline description — formal or informal>",
    "renewal_cadence_note": "<stated renewal rate, auto-renewal language, or retention mechanism, or null>",
    "msa_sow_coverage_note": "<description of MSA, SOW, or retainer coverage as stated, or null>",
    "recurring_revenue_proxy": "<any stated proxy for recurring revenue where formal backlog is absent — e.g. 'length of stay', 'customer tenure', 'renewal rate', or null>",
    "source_doc": "<exact VDR filename>"
  }},

  "key_dependencies": [
    {{
      "dependency_type": "<vendor | platform | channel | partner | person | geography | customer>",
      "name": "<specific name as stated — e.g. 'Salesforce CRM' or 'AWS infrastructure' or 'Philippines back-office team'>",
      "description": "<role or nature of the dependency as stated in the documents>",
      "concentration_risk": "<true | false | null — true if loss of this dependency would materially harm the business>",
      "source_doc": "<exact VDR filename>"
    }}
  ],

  "recent_model_changes": [
    {{
      "change_type": "<revenue_model | pricing | gtm | customer_mix | technology | geography | ma | staffing | product>",
      "description": "<factual description of the change as stated in the documents>",
      "approximate_date": "<year or quarter as stated — e.g. 'May 2024' or 'Q3 2023' or 'FY2021'>",
      "impact_note": "<stated impact or rationale for the change, or null>",
      "source_doc": "<exact VDR filename>",
      "source_location": "<page or section>"
    }}
  ],

  "overlay_conflict_evidence": "<any text in the documents inconsistent with the confirmed industry overlay, or null>",

  "citations": [
    {{
      "field": "<field_name this citation supports>",
      "document": "<exact VDR filename — must NOT be 'COMPANY PROFILE'>",
      "location": "<page number or section title>",
      "quote": "<≤30 word direct quote>",
      "confidence": "<high | medium | low>"
    }}
  ],

  "executive_summary": "<4–5 sentence factual summary covering: (1) what the company does and where it operates, (2) how it earns revenue and at what scale, (3) the key growth driver and customer acquisition mechanism, (4) a notable dependency or concentration risk, (5) what has changed recently. Write only what is stated. Do not render a verdict.>",

  "extraction_notes": "<note: whether a CIM was present; any fields null because genuinely absent; overlay-specific fields skipped because overlay doesn't apply; any conflicting statements found>"
}}
"""

_VALID_REVENUE_TAGS = {
    "pure_recurring", "repeat_services", "project_based", "transactional",
    "usage_based", "licensing", "marketplace", "hybrid",
}

_VALID_SALES_MOTIONS = {
    "founder_led", "enterprise_sales", "channel_partner",
    "inbound_plg", "outbound", "relationship",
}


# ---------------------------------------------------------------------------
# Agent implementation
# ---------------------------------------------------------------------------

class BusinessModelAgent:
    """Phase 3 Business Model workstream agent.

    Orchestrates: tool calls → single LLM call → deterministic flag evaluation
    → Delta write. Extends WorkstreamAgent for trace/flag infrastructure.
    """

    agent_name = "business_model"

    def __init__(self):
        from agents.shared.agent_base import WorkstreamAgent
        self._base = WorkstreamAgent.__new__(WorkstreamAgent)
        WorkstreamAgent.__init__(self._base)
        # Expose base methods directly on self for ergonomics.
        self._tool_call             = self._base._tool_call
        self._call_llm              = self._base._call_llm
        self._parse_json_response   = self._base._parse_json_response
        self._add_flag              = self._base._add_flag
        self._add_citation          = self._base._add_citation
        self._add_gap               = self._base._add_gap
        self._reset_state           = self._base._reset_state
        self._flags_as_dicts        = self._base._flags_as_dicts
        self._citations_as_dicts    = self._base._citations_as_dicts
        self._company_name: str     = ""

    # ------------------------------------------------------------------
    # Retrieval helper — copied from financial_trends_agent.py
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
             with non-standard filenames are not silently excluded.

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

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    def _tool_retrieve_business_overview(self, spark):
        """Company description, service/product lines, geographic footprint.

        Works for: CIM, management deck, investor presentation, website excerpts,
        executive summary PDF, board materials — any document describing the business.
        """
        chunks = self._semantic_search_with_fallback(
            spark=spark,
            query=(
                "company overview what does this company do products services offerings "
                "geographic footprint locations markets business description revenue streams "
                "what the company sells how it makes money"
            ),
            workstream_filter=["BUSINESS_MODEL"],
            top_k=12,
            file_name_filter=["CIM", "OM", "Overview", "Offering", "Memorandum",
                              "Profile", "Summary", "Presentation", "Deck",
                              "Management", "Executive"],
            min_chunk_length=150,
            min_results=3,
        )
        source_docs = list({c.file_name for c in chunks})
        return self._tool_call(
            tool_name="retrieve_business_overview",
            input_summary="query=company overview products services geographic footprint; workstream=BUSINESS_MODEL; top_k=12 (with fallback)",
            data=chunks,
            output_summary=f"{len(chunks)} chunks from {len(source_docs)} files",
            confidence="high" if chunks else "low",
            source_docs=source_docs,
        )

    def _tool_retrieve_pricing_and_margins(self, spark):
        """Per-offering pricing, bill rates, gross margin by product or service type.

        Industry-agnostic: works for services (bill rates, hourly rates), SaaS
        (pricing tiers, ACV), industrial (product margin, ASP), healthcare (service
        type margins), or any other model.
        """
        chunks = self._semantic_search_with_fallback(
            spark=spark,
            query=(
                "pricing gross margin by product service offering bill rate price per unit "
                "margin by service type average selling price ASP revenue per offering "
                "contribution margin by product line pricing table rate card"
            ),
            workstream_filter=["BUSINESS_MODEL", "FINANCIAL"],
            top_k=10,
            file_name_filter=["CIM", "Pricing", "Financial", "Revenue", "Margin",
                              "OM", "Overview", "Rate", "Card"],
            min_chunk_length=100,
            min_results=3,
        )
        source_docs = list({c.file_name for c in chunks})
        return self._tool_call(
            tool_name="retrieve_pricing_and_margins",
            input_summary="query=pricing gross margin by service/product bill rate; workstream=BUSINESS_MODEL,FINANCIAL; top_k=10 (with fallback)",
            data=chunks,
            output_summary=f"{len(chunks)} chunks from {len(source_docs)} files",
            confidence="high" if chunks else "low",
            source_docs=source_docs,
        )

    def _tool_retrieve_sales_and_customers(self, spark):
        """Sales motion, customer acquisition, customer segments, GTM strategy.

        Industry-agnostic: covers enterprise sales, referral-based (healthcare),
        inbound/PLG (SaaS), channel (tech), outbound (services), or any motion.
        """
        chunks = self._semantic_search_with_fallback(
            spark=spark,
            query=(
                "sales motion go to market customer acquisition business development "
                "customer segment end market vertical buyer persona channel partner "
                "referral network enterprise sales inbound outbound sales process "
                "new customer acquisition how we sell who we sell to"
            ),
            workstream_filter=["BUSINESS_MODEL", "KPI_OPS"],
            top_k=10,
            file_name_filter=["CIM", "Sales", "GTM", "Customer", "Marketing",
                              "Overview", "OM", "Strategy", "Presentation"],
            min_chunk_length=150,
            min_results=3,
        )
        source_docs = list({c.file_name for c in chunks})
        return self._tool_call(
            tool_name="retrieve_sales_and_customers",
            input_summary="query=sales motion GTM customer acquisition segments; workstream=BUSINESS_MODEL,KPI_OPS; top_k=10 (with fallback)",
            data=chunks,
            output_summary=f"{len(chunks)} chunks from {len(source_docs)} files",
            confidence="high" if chunks else "low",
            source_docs=source_docs,
        )

    def _tool_retrieve_revenue_visibility(self, spark):
        """Forward revenue signals: backlog, contracted revenue, pipeline, retention proxies.

        Industry-agnostic: formal backlog (tech/industrial), contracted ARR (SaaS),
        length of stay (healthcare), pipeline coverage (services), renewal rates (any).
        """
        chunks = self._semantic_search_with_fallback(
            spark=spark,
            query=(
                "backlog contracted revenue pipeline forward revenue visibility "
                "renewal rate retention MSA SOW retainer recurring revenue "
                "average customer tenure length of stay contract coverage "
                "revenue predictability pipeline coverage months weighted pipeline"
            ),
            workstream_filter=["BUSINESS_MODEL", "FINANCIAL", "KPI_OPS"],
            top_k=8,
            file_name_filter=["CIM", "Pipeline", "Backlog", "Contract", "Revenue",
                              "KPI", "Metrics", "Overview", "Model"],
            min_chunk_length=100,
            min_results=3,
        )
        source_docs = list({c.file_name for c in chunks})
        return self._tool_call(
            tool_name="retrieve_revenue_visibility",
            input_summary="query=backlog contracted pipeline retention tenure; workstream=BUSINESS_MODEL,FINANCIAL,KPI_OPS; top_k=8 (with fallback)",
            data=chunks,
            output_summary=f"{len(chunks)} chunks from {len(source_docs)} files",
            confidence="high" if chunks else "low",
            source_docs=source_docs,
        )

    def _tool_retrieve_model_changes_and_dependencies(self, spark):
        """Recent business model/pricing/GTM changes and key vendor/platform dependencies.

        Industry-agnostic: covers software platform changes (SaaS), acquisition history
        (any), outsourcing model changes (services/healthcare), pricing changes (any),
        technology system dependencies (any), key vendor or partner risks (any).
        """
        chunks = self._semantic_search_with_fallback(
            spark=spark,
            query=(
                "business model change pricing change go to market change recent initiative "
                "key vendor platform dependency technology system software EMR payroll HR "
                "acquisition M&A history strategic initiative timeline milestones "
                "outsourcing partnership key dependency concentration risk"
            ),
            workstream_filter=["BUSINESS_MODEL", "KPI_OPS"],
            top_k=10,
            file_name_filter=["CIM", "Overview", "Timeline", "History", "OM",
                              "Strategy", "Presentation", "Management", "Deck"],
            min_chunk_length=150,
            min_results=3,
        )
        source_docs = list({c.file_name for c in chunks})
        return self._tool_call(
            tool_name="retrieve_model_changes_and_dependencies",
            input_summary="query=model changes pricing GTM dependencies vendor platform; workstream=BUSINESS_MODEL,KPI_OPS; top_k=10 (with fallback)",
            data=chunks,
            output_summary=f"{len(chunks)} chunks from {len(source_docs)} files",
            confidence="high" if chunks else "low",
            source_docs=source_docs,
        )

    def _tool_detect_cim_presence(self, spark):
        """Detect whether a banker-prepared CIM or equivalent primary marketing document
        exists in the data room. Used to set deal_type and confidence level.

        A CIM-equivalent includes: Confidential Information Memorandum, Offering
        Memorandum, Investment Overview, management presentation with full financial
        summary. If absent, the deal is treated as non-banked and confidence is reduced.
        """
        chunks = self._semantic_search_with_fallback(
            spark=spark,
            query=(
                "confidential information memorandum offering memorandum investment overview "
                "executive summary business overview financial highlights deal overview "
                "transaction overview management presentation"
            ),
            workstream_filter=["BUSINESS_MODEL"],
            top_k=3,
            file_name_filter=["CIM", "OM", "Offering", "Memorandum", "Investment",
                              "Overview", "Presentation"],
            min_chunk_length=50,
            min_results=1,
        )
        cim_found = len(chunks) > 0
        source_docs = list({c.file_name for c in chunks})
        return self._tool_call(
            tool_name="detect_cim_presence",
            input_summary="query=CIM OM investment overview executive summary; workstream=BUSINESS_MODEL; top_k=3",
            data={"cim_found": cim_found, "source_docs": source_docs},
            output_summary=f"CIM/OM detected: {cim_found} — {source_docs if cim_found else 'none found'}",
            confidence="high" if cim_found else "low",
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
        revenue_tag = ((extracted.get("revenue_model") or {}).get("tag") or "").lower()
        segments = ((extracted.get("customer_profile") or {}).get("segments_description") or "").lower()

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
        self._company_name = company_name

        print(f"  Running 7 tools ...")

        # ── Tool calls ──────────────────────────────────────────────────
        tr_cim  = self._tool_detect_cim_presence(spark)
        tr1     = self._tool_retrieve_business_overview(spark)
        tr2     = self._tool_retrieve_pricing_and_margins(spark)
        tr3     = self._tool_retrieve_sales_and_customers(spark)
        tr4     = self._tool_retrieve_revenue_visibility(spark)
        tr5     = self._tool_retrieve_model_changes_and_dependencies(spark)
        tr6     = self._tool_load_company_profile(company_name, spark)

        # ── CIM / deal type detection ───────────────────────────────────
        cim_found = (tr_cim.data or {}).get("cim_found", False)
        if not cim_found:
            self._add_gap(
                "No CIM or Offering Memorandum detected in the data room. "
                "This appears to be a non-banked deal. Confidence is reduced across "
                "all business model sections. Primary sources will be financial models, "
                "management presentations, and P&L documents."
            )
        deal_type_context = (
            "DEAL TYPE: Banked — CIM or Offering Memorandum detected. "
            "Full business model detail expected."
            if cim_found else
            "DEAL TYPE: Non-banked — No CIM detected. Extract from available "
            "management presentations, financial models, and board materials. "
            "Note reduced confidence in extraction_notes."
        )

        # ── Build combined context (deduplicate by chunk text) ──────────
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
        overlay = (profile_dict or {}).get("industry_overlay", "") if profile_dict else ""

        # ── Single LLM call ─────────────────────────────────────────────
        print("  Calling LLM for extraction ...")
        user_prompt = _USER_PROMPT_TEMPLATE.format(
            company_profile_json=company_profile_json,
            deal_type_context=deal_type_context,
            combined_chunk_text=combined_chunk_text,
        )
        raw_response = self._call_llm(_SYSTEM_PROMPT, user_prompt, llm_endpoint)
        extracted = self._parse_json_response(raw_response)

        # ── Source doc validation: reject records sourced from the company profile ──
        _PROFILE_SENTINEL = "COMPANY PROFILE"

        # Validate list fields
        for _list_path in (
            ("products_services",),
            ("key_dependencies",),
            ("recent_model_changes",),
            ("customer_profile", "overlay_specific", "healthcare", "referral_source_breakdown"),
            ("customer_profile", "overlay_specific", "healthcare", "payor_mix"),
        ):
            _obj = extracted
            for _part in _list_path[:-1]:
                _obj = (_obj or {}).get(_part) or {}
            _list = _obj.get(_list_path[-1]) if isinstance(_obj, dict) else None
            if not isinstance(_list, list):
                continue
            _clean = []
            for _rec in _list:
                if (_rec.get("source_doc") or "").upper().startswith(_PROFILE_SENTINEL):
                    self._add_gap(
                        f"{'→'.join(_list_path)} record excluded: source_doc is company "
                        f"profile metadata. name='{_rec.get('name') or _rec.get('source_type')}' excluded."
                    )
                else:
                    _clean.append(_rec)
            _obj[_list_path[-1]] = _clean

        # Validate single-record fields
        for _key in ("revenue_model", "sales_motion", "revenue_visibility"):
            _rec = extracted.get(_key)
            if isinstance(_rec, dict):
                if (_rec.get("source_doc") or "").upper().startswith(_PROFILE_SENTINEL):
                    self._add_gap(
                        f"{_key}.source_doc is company profile metadata — "
                        f"check retrieval coverage for this field."
                    )
                    _rec["source_doc"] = None

        # ── Post-extraction completeness check (overlay-gated) ──────────
        _ps  = extracted.get("products_services") or []
        _cp  = extracted.get("customer_profile") or {}
        _sm  = extracted.get("sales_motion") or {}
        _rv  = extracted.get("revenue_visibility") or {}
        _rc  = extracted.get("recent_model_changes") or []
        _kd  = extracted.get("key_dependencies") or []
        _overlay_lower = (overlay or "").lower()

        # Universal checks (apply to any overlay)
        if not _ps:
            self._add_gap(
                "products_services is empty — service or product lines and margin profile "
                "not extracted. Check retrieval coverage of pricing/offering sections."
            )

        if not _sm.get("tag"):
            self._add_gap(
                "sales_motion tag not extracted — sales process description may be absent "
                "from retrieved chunks. Check retrieval coverage of GTM/sales sections."
            )

        if not any([
            _rv.get("contracted_pct_of_forward_12mo"),
            _rv.get("backlog_coverage_months"),
            _rv.get("backlog_dollars"),
            _rv.get("recurring_revenue_proxy"),
        ]):
            self._add_gap(
                "revenue_visibility has no forward revenue signal — backlog, contracted %, "
                "and recurring revenue proxies all null. Flag for management Q&A."
            )

        if not _rc:
            self._add_gap(
                "recent_model_changes is empty — no business model, pricing, GTM, or "
                "technology changes extracted. Check retrieval of timeline/MD&A sections."
            )

        if not _kd:
            self._add_gap(
                "key_dependencies is empty — vendor, platform, channel, and people "
                "dependencies not extracted. Check retrieval coverage."
            )

        # Healthcare-specific checks (only fire for healthcare overlay)
        if "healthcare" in _overlay_lower:
            _hc = (_cp.get("overlay_specific") or {}).get("healthcare") or {}
            if not _hc.get("referral_source_breakdown"):
                self._add_gap(
                    "healthcare overlay: referral_source_breakdown is empty — customer "
                    "acquisition channel mix not extracted. Referral source breakdown is "
                    "a primary KPI for healthcare; check retrieval of sales sections."
                )
            if not _hc.get("payor_mix"):
                self._add_gap(
                    "healthcare overlay: payor_mix is empty — payor/customer type breakdown "
                    "not extracted. Required for government payor concentration threshold check."
                )

        # Tech services-specific checks
        if "tech" in _overlay_lower:
            _tech = (_cp.get("overlay_specific") or {}).get("tech_services") or {}
            if not _tech.get("customer_size_mix") and not _cp.get("segments_description"):
                self._add_gap(
                    "tech_services overlay: customer size mix (enterprise/mid/SMB) not "
                    "extracted. Required for average account size threshold evaluation."
                )

        # ── Log LLM step to trace ────────────────────────────────────────
        llm_step = len(self._base._trace) + 1
        self._base._trace.append({
            "step":       llm_step,
            "tool":       "llm_extraction",
            "input":      f"combined context: {len(all_chunks)} chunks from {len(seen_texts)} unique texts",
            "output":     (
                f"Extracted revenue_model_tag={(extracted.get('revenue_model') or {}).get('tag')}, "
                f"products_services={len(extracted.get('products_services') or [])}, "
                f"key_dependencies={len(extracted.get('key_dependencies') or [])}, "
                f"recent_model_changes={len(extracted.get('recent_model_changes') or [])}"
            ),
            "confidence": "high" if all_chunks else "low",
            "sources":    list({c.file_name for c in all_chunks}),
        })

        # ── Accumulate citations from LLM output ─────────────────────────
        for cit in (extracted.get("citations") or []):
            self._add_citation(
                claim=cit.get("field", ""),
                document=cit.get("document", ""),
                location=cit.get("location", ""),
                confidence=cit.get("confidence", "low"),
                raw_text=cit.get("quote", ""),
            )

        # ── Revenue durability flag — deterministic Python ────────────────
        primary_source = (
            tr1.source_docs[0] if tr1.source_docs
            else tr2.source_docs[0] if tr2.source_docs
            else ""
        )
        severity, flag_confidence, flag_rule = self._apply_revenue_durability_flag(
            revenue_model_tag=(extracted.get("revenue_model") or {}).get("tag"),
            revenue_model_pct_split=(extracted.get("revenue_model") or {}).get("pct_split"),
            source_doc=primary_source,
        )
        self._add_flag(
            metric="revenue_model_durability",
            value=str(
                (extracted.get("revenue_model") or {}).get("pct_split")
                or (extracted.get("revenue_model") or {}).get("tag")
                or "unknown"
            ),
            threshold="≥70% recurring=Green, 40–70%=Yellow, <40%=Red",
            severity=severity,
            note=flag_rule,
            source_doc=primary_source,
            confidence=flag_confidence,
        )

        if severity == "Green":
            self._log_no_flag(
                "revenue_model_durability",
                str(
                    (extracted.get("revenue_model") or {}).get("pct_split")
                    or (extracted.get("revenue_model") or {}).get("tag")
                    or "unknown"
                ),
                "≥70% recurring=Green threshold",
                note="Revenue model meets durability threshold",
            )

        # ── Overlay conflict check ────────────────────────────────────────
        overlay_conflict, overlay_conflict_note = self._check_overlay_conflict(
            extracted=extracted,
            profile=profile_dict,
        )
        overlay_step = len(self._base._trace) + 1
        self._base._trace.append({
            "step":       overlay_step,
            "tool":       "industry_overlay_conflict_check",
            "input":      (
                f"revenue_model_tag={(extracted.get('revenue_model') or {}).get('tag')}, "
                f"segments_description={str((extracted.get('customer_profile') or {}).get('segments_description', ''))[:80]}"
            ),
            "output":     f"conflict={overlay_conflict}" + (f" — {overlay_conflict_note[:120]}" if overlay_conflict_note else ""),
            "confidence": "high" if profile_dict else "low",
            "sources":    ["uc13.classification.company_profile"],
        })
        print(f"  Step {overlay_step} [industry_overlay_conflict_check]: conflict={overlay_conflict}")

        # ── Build result dict ─────────────────────────────────────────────
        return {
            "company_name":                  company_name,
            "cim_detected":                  cim_found,
            "executive_summary":             extracted.get("executive_summary"),
            "revenue_model_tag":             (extracted.get("revenue_model") or {}).get("tag"),
            "revenue_model_pct_split":       (extracted.get("revenue_model") or {}).get("pct_split"),
            "revenue_model_note":            (extracted.get("revenue_model") or {}).get("note"),
            "revenue_durability_flag":       severity,
            "flag_confidence":               flag_confidence,
            "flag_rule_applied":             flag_rule,
            "products_services_json":        json.dumps(extracted.get("products_services") or []),
            "customer_profile_json":         json.dumps(extracted.get("customer_profile") or {}),
            "sales_motion_tag":              (extracted.get("sales_motion") or {}).get("tag"),
            "sales_motion_json":             json.dumps(extracted.get("sales_motion") or {}),
            "revenue_visibility_json":       json.dumps(extracted.get("revenue_visibility") or {}),
            "key_dependencies_json":         json.dumps(extracted.get("key_dependencies") or []),
            "recent_model_changes_json":     json.dumps(extracted.get("recent_model_changes") or []),
            "overlay_conflict":              overlay_conflict,
            "overlay_conflict_note":         overlay_conflict_note,
            "overlay_conflict_evidence":     extracted.get("overlay_conflict_evidence"),
            "data_room_gaps":                list(self._base._data_room_gaps),
            "citations":                     json.dumps(self._citations_as_dicts()),
            "reasoning_trace":               list(self._base._trace),
            "flags":                         self._flags_as_dicts(),
            "report_path":                   None,
            "created_at":                    datetime.now(timezone.utc).isoformat(),
        }


# ---------------------------------------------------------------------------
# Stakeholder report export
# ---------------------------------------------------------------------------

def _write_stakeholder_report(result: dict, catalog: str, spark) -> str:
    """Write a clean, human-readable YAML report to a UC Volume.

    Saves to /Volumes/{catalog}/analysis/reports/{company_name}/
    business_model_report.yaml (or .json if PyYAML is unavailable).
    Returns the full volume path of the written file.
    """
    company_name = result["company_name"]

    report = {
        "report": {
            "agent":        "business_model",
            "company":      company_name,
            "generated_at": result.get("created_at", ""),
            "cim_detected": result.get("cim_detected", False),
        },
        "executive_summary":     result.get("executive_summary"),
        "revenue_model":         {
            "tag":               result.get("revenue_model_tag"),
            "pct_split":         result.get("revenue_model_pct_split"),
            "note":              result.get("revenue_model_note"),
            "durability_rating": result.get("revenue_durability_flag"),
            "flag_confidence":   result.get("flag_confidence"),
            "flag_rule":         result.get("flag_rule_applied"),
        },
        "products_and_services": json.loads(result.get("products_services_json") or "[]"),
        "customer_profile":      json.loads(result.get("customer_profile_json") or "{}"),
        "sales_motion":          json.loads(result.get("sales_motion_json") or "{}"),
        "revenue_visibility":    json.loads(result.get("revenue_visibility_json") or "{}"),
        "key_dependencies":      json.loads(result.get("key_dependencies_json") or "[]"),
        "recent_model_changes":  json.loads(result.get("recent_model_changes_json") or "[]"),
        "overlay_conflict": {
            "detected":  result.get("overlay_conflict", False),
            "note":      result.get("overlay_conflict_note") or None,
            "evidence":  result.get("overlay_conflict_evidence") or None,
        },
        "flags":          result.get("flags") or [],
        "data_room_gaps": result.get("data_room_gaps") or [],
        "citations":      json.loads(result.get("citations") or "[]"),
    }

    # ── Render as YAML (preferred) or JSON fallback ────────────────────
    try:
        import yaml

        def _str_representer(dumper, data):
            if "\n" in data:
                return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
            return dumper.represent_scalar("tag:yaml.org,2002:str", data)

        yaml.add_representer(str, _str_representer)
        content  = yaml.dump(report, allow_unicode=True, sort_keys=False, width=120)
        ext      = "yaml"
    except ImportError:
        content  = json.dumps(report, indent=2, ensure_ascii=False)
        ext      = "json"

    # ── Ensure the UC Volume and directory exist ───────────────────────
    spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.analysis.reports")
    safe_name = company_name.replace(" ", "_").replace("/", "_")
    dir_path  = f"/Volumes/{catalog}/analysis/reports/{safe_name}"
    os.makedirs(dir_path, exist_ok=True)

    file_path = f"{dir_path}/business_model_report.{ext}"
    with open(file_path, "w", encoding="utf-8") as fh:
        fh.write(content)

    return file_path


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {table} (
    company_name                  STRING,
    cim_detected                  BOOLEAN,
    executive_summary             STRING,
    revenue_model_tag             STRING,
    revenue_model_pct_split       STRING,
    revenue_model_note            STRING,
    revenue_durability_flag       STRING,
    flag_confidence               STRING,
    flag_rule_applied             STRING,
    products_services_json        STRING,
    customer_profile_json         STRING,
    sales_motion_tag              STRING,
    sales_motion_json             STRING,
    revenue_visibility_json       STRING,
    key_dependencies_json         STRING,
    recent_model_changes_json     STRING,
    overlay_conflict              BOOLEAN,
    overlay_conflict_note         STRING,
    overlay_conflict_evidence     STRING,
    data_room_gaps                ARRAY<STRING>,
    citations                     STRING,
    reasoning_trace               STRING,
    flags                         STRING,
    report_path                   STRING,
    created_at                    TIMESTAMP
) USING DELTA
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

    # Schema migration guard: compare live column names against the expected set.
    # When they diverge (schema was updated), DROP and recreate so the new columns
    # are picked up cleanly. All prior rows are lost on a migration — intentional
    # in development. Production deployments should use ALTER TABLE instead.
    _EXPECTED_COLS = {
        "company_name", "cim_detected", "executive_summary",
        "revenue_model_tag", "revenue_model_pct_split", "revenue_model_note",
        "revenue_durability_flag", "flag_confidence", "flag_rule_applied",
        "products_services_json", "customer_profile_json",
        "sales_motion_tag", "sales_motion_json", "revenue_visibility_json",
        "key_dependencies_json", "recent_model_changes_json",
        "overlay_conflict", "overlay_conflict_note", "overlay_conflict_evidence",
        "data_room_gaps", "citations", "reasoning_trace",
        "flags", "report_path", "created_at",
    }
    try:
        _live_cols = {f.name for f in spark.table(table).schema.fields}
        if not _EXPECTED_COLS.issubset(_live_cols):
            _missing = _EXPECTED_COLS - _live_cols
            print(
                f"  [schema_migration] {table} has stale schema — dropping and "
                f"recreating. Missing columns: {sorted(_missing)}"
            )
            spark.sql(f"DROP TABLE IF EXISTS {table}")
    except Exception:
        pass  # Table doesn't exist yet — CREATE below handles it.

    spark.sql(_CREATE_TABLE_SQL.format(table=table))
    spark.sql(f"DELETE FROM {table} WHERE company_name = '{company_name}'")

    from pyspark.sql import Row
    from pyspark.sql.types import (
        StructType, StructField, StringType, BooleanType,
        ArrayType, TimestampType,
    )

    schema = StructType([
        StructField("company_name",               StringType(),            True),
        StructField("cim_detected",               BooleanType(),           True),
        StructField("executive_summary",           StringType(),            True),
        StructField("revenue_model_tag",           StringType(),            True),
        StructField("revenue_model_pct_split",     StringType(),            True),
        StructField("revenue_model_note",          StringType(),            True),
        StructField("revenue_durability_flag",     StringType(),            True),
        StructField("flag_confidence",             StringType(),            True),
        StructField("flag_rule_applied",           StringType(),            True),
        StructField("products_services_json",      StringType(),            True),
        StructField("customer_profile_json",       StringType(),            True),
        StructField("sales_motion_tag",            StringType(),            True),
        StructField("sales_motion_json",           StringType(),            True),
        StructField("revenue_visibility_json",     StringType(),            True),
        StructField("key_dependencies_json",       StringType(),            True),
        StructField("recent_model_changes_json",   StringType(),            True),
        StructField("overlay_conflict",            BooleanType(),           True),
        StructField("overlay_conflict_note",       StringType(),            True),
        StructField("overlay_conflict_evidence",   StringType(),            True),
        StructField("data_room_gaps",              ArrayType(StringType()), True),
        StructField("citations",                   StringType(),            True),
        StructField("reasoning_trace",             StringType(),            True),
        StructField("flags",                       StringType(),            True),
        StructField("report_path",                 StringType(),            True),
        StructField("created_at",                  TimestampType(),         True),
    ])

    row_data = {
        "company_name":               result["company_name"],
        "cim_detected":               result.get("cim_detected", False),
        "executive_summary":          result.get("executive_summary"),
        "revenue_model_tag":          result.get("revenue_model_tag"),
        "revenue_model_pct_split":    result.get("revenue_model_pct_split"),
        "revenue_model_note":         result.get("revenue_model_note"),
        "revenue_durability_flag":    result.get("revenue_durability_flag"),
        "flag_confidence":            result.get("flag_confidence"),
        "flag_rule_applied":          result.get("flag_rule_applied"),
        "products_services_json":     result.get("products_services_json"),
        "customer_profile_json":      result.get("customer_profile_json"),
        "sales_motion_tag":           result.get("sales_motion_tag"),
        "sales_motion_json":          result.get("sales_motion_json"),
        "revenue_visibility_json":    result.get("revenue_visibility_json"),
        "key_dependencies_json":      result.get("key_dependencies_json"),
        "recent_model_changes_json":  result.get("recent_model_changes_json"),
        "overlay_conflict":           result.get("overlay_conflict", False),
        "overlay_conflict_note":      result.get("overlay_conflict_note"),
        "overlay_conflict_evidence":  result.get("overlay_conflict_evidence"),
        "data_room_gaps":             result.get("data_room_gaps") or [],
        "citations":                  result.get("citations"),
        "reasoning_trace":            json.dumps(result.get("reasoning_trace") or []),
        "flags":                      json.dumps(result.get("flags") or []),
        "report_path":                result.get("report_path"),
        "created_at":                 datetime.now(timezone.utc),
    }

    df = spark.createDataFrame([Row(**row_data)], schema=schema)
    df.write.format("delta").mode("append").saveAsTable(table)

    print(f"\n✓ Saved business model output → {table}")

    # ── Export stakeholder report ──────────────────────────────────────
    report_path = _write_stakeholder_report(result, catalog, spark)
    result["report_path"] = report_path
    print(f"✓ Stakeholder report → {report_path}")

    return result


if __name__ == "__main__":
    main()
