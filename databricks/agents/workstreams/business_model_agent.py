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
Apply all system prompt rules. Return null for any field genuinely absent from
the documents. Return ONLY the JSON object below.

BEFORE WRITING THE JSON — scan the entire retrieved context and identify:
a) All service/product lines with any stated price or margin → products_services
b) All referral source types with stated % → referral_source_breakdown
c) All payor types with stated % → payor_mix
d) Any named technology systems (ERP, CRM, EMR, payroll, scheduling) → key_dependencies
e) Any dated business changes (launches, acquisitions, hires, system changes) → recent_model_changes
f) Any customer tenure, utilization, cohort, or retention data → customer_operational_metrics
g) Revenue by geography, location, segment, or market → revenue_by_location
h) Any named executives with title, tenure, or background → people_and_org.key_executives
i) Any ownership table, equity %, or shareholder list → people_and_org.ownership
j) Any headcount by functional area, location, or type → workforce_capacity.headcount_by_function
k) Any hiring rate, workforce growth, or cost-per-hire data → workforce_capacity.hiring_and_growth
l) Any US vs. offshore/outsourced/contract workforce split → workforce_capacity.workforce_model

WORKED EXAMPLES — how to populate the most-missed fields.
These examples use placeholder values. The FORMAT and extraction logic are what matter.

Example: people_and_org.key_executives from any management section:
  "Jane Smith joined as CEO in [Year], previously [Background]"
  "John Doe, COO, [N] years with the company, prior role at [Company]"
→ One record per named executive:
  [{{"name": "Jane Smith", "title": "CEO", "tenure_with_company": "N years",
     "background_note": "Previously [background]", "operational_role": true,
     "source_doc": "filename.pdf", "source_location": "Management Team section"}}]

Example: people_and_org.ownership from an ownership/capitalization table:
  "Founder A: 75%, Co-founder B: 15%, Key Employee C: 10%"
→ One record per named owner:
  [{{"owner_name": "Founder A", "ownership_pct": "75%", "operational_role": "CEO",
     "source_doc": "filename.pdf"}}]
Include operational role description — this identifies key-man risk.

Example: workforce_capacity.headcount_by_function from any headcount table:
  "Functional Area | Count | Avg Salary"
  "Engineering     | 24    | $95,000"
  "Sales           | 12    | $85,000"
→ One record per functional area:
  [{{"function": "Engineering", "headcount": "24", "avg_salary_stated": "$95,000",
     "location_type": "onsite", "source_doc": "filename.pdf"}}]

Example: workforce_capacity.workforce_model from any US vs. offshore/contract split:
  "US employees: 64, Global/offshore resources: 44 (193% growth YoY)"
→  {{"us_headcount": "64", "offshore_or_contract_headcount": "44",
     "offshore_pct_of_total": "41%", "growth_note": "Global resources grew 193% YoY",
     "cost_advantage_note": "stated cost advantage if described",
     "source_doc": "filename.pdf"}}

Example: customer_operational_metrics.by_location from any client metrics table:
  "Location | Revenue/Client/Week | Units/Client | Clients Served"
  "Region A | $2,500              | 65 hrs       | 150"
  "Region B | $1,800              | 45 hrs       | 80"
→ One record per location:
  [{{"location": "Region A", "revenue_per_customer_per_period": "$2,500/week",
     "utilization_per_customer": "65 hrs/week", "customer_count": "150",
     "period": "TTM", "source_doc": "filename.pdf"}}]

Example: customer_operational_metrics.tenure_distribution from any cohort table:
  "<1 month: 13%, 1–3 months: 14%, 3–12 months: 12%, 1–3 years: 3%, 3+ years: 58%"
→  {{"distribution_buckets": [
      {{"bucket": "<1 month", "pct": "13%"}},
      {{"bucket": "1-3 months", "pct": "14%"}},
      {{"bucket": "3-12 months", "pct": "12%"}},
      {{"bucket": "1-3 years", "pct": "3%"}},
      {{"bucket": "3+ years", "pct": "58%"}}
    ],
    "longest_bucket_pct": "58%",
    "period_covered": "all customers since [date]",
    "source_doc": "filename.pdf"}}

Example: referral_source_breakdown (healthcare) from a table like:
  "Channel Type A    45%    FY2023"
  "Channel Type B    30%    FY2023"
→ Extract as:
  [{{"source_type": "Channel Type A", "pct_of_volume_or_profit": "45%", "period": "FY2023", "source_doc": "filename.pdf"}},
   {{"source_type": "Channel Type B", "pct_of_volume_or_profit": "30%", "period": "FY2023", "source_doc": "filename.pdf"}}]
RULE: MUST populate pct_of_volume_or_profit if a % is stated. Do NOT return null.

Example: payor_mix (healthcare) or revenue type breakdown (any overlay) from text like:
  "70% Payor Type A, 15% Payor Type B, 10% Payor Type C, 5% Other"
→ Extract as:
  [{{"payor_type": "Payor Type A", "pct_of_revenue": "70%", "source_doc": "filename.pdf"}},
   {{"payor_type": "Payor Type B", "pct_of_revenue": "15%", "source_doc": "filename.pdf"}}, ...]
RULE: MUST populate pct_of_revenue if a % is stated. Do NOT return a single record with null pct.

Example: sales_motion.compensation_model from text like:
  "sales representatives receive X% of revenue generated from their accounts"
  OR "salespeople earn a commission tied to the lifetime value of accounts they close"
→ Extract as: "Sales reps earn X% of account revenue [or: commission tied to account LTV]"
RULE: Do NOT return null if any compensation structure or incentive mechanism is described.

Example: key_dependencies from text mentioning any named system or team:
  Healthcare EMR: "The company uses [System Name] as its electronic medical record"
  SaaS infra: "All services run on AWS with a single-cloud architecture"
  Staffing: "Back-office operations are managed by a [City/Country]-based team of N people"
→ One record per named system, team, platform, or critical vendor:
  {{"dependency_type": "platform", "name": "[System Name] EMR",
    "description": "Electronic medical records platform used company-wide",
    "concentration_risk": "true", "source_doc": "filename.pdf"}}
RULE: Extract one record per named entity. Do NOT aggregate into "technology systems".

Example: recent_model_changes — one record per distinct dated business event:
  "In [Month Year], the Company transitioned [process] to [new approach]"
  "The Company acquired [Target] in [Year], entering the [Market] market"
  "In [Year], the Company launched [Product/Service/Office]"
→ One record per event:
  {{"change_type": "technology", "description": "Transitioned [process] to [new approach]",
    "approximate_date": "[Month Year]", "impact_note": "[stated quantified impact or null]",
    "source_doc": "filename.pdf", "source_location": "[section name]"}}
RULE: Extract every distinct dated event. A company with a 7-year history should
produce many records — do not stop at 1 or 2.

{{
  "revenue_model": {{
    "tag": "<choose one tag from the system prompt list>",
    "pct_split": "<stated split or null — e.g. '80% recurring SaaS, 20% professional services'>",
    "note": "<1–2 sentence description of how the company earns revenue, including scale if stated>",
    "source_doc": "<exact VDR filename — must NOT be 'COMPANY PROFILE'>",
    "source_location": "<page or section>"
  }},

  "products_services": [
    {{
      "name": "<exact service/product name as stated>",
      "revenue_pct": "<% of total revenue as stated, or null>",
      "revenue_dollars": "<$ as stated or null>",
      "gm_pct_stated": "<gross margin % as stated — state a range if multiple values>",
      "gm_pct_note": "<context for the margin figure>",
      "avg_price_or_rate": "<stated price, rate, or ACV or null>",
      "growth_note": "<growth rate or trend as stated, or null>",
      "source_doc": "<exact VDR filename>",
      "source_location": "<page or section>"
    }}
  ],

  "revenue_by_location": [
    {{
      "location": "<location, market, segment, or geography name as stated>",
      "revenue_dollars": "<$ as stated>",
      "revenue_pct": "<% of total revenue as stated or null>",
      "period": "<period this figure applies to>",
      "source_doc": "<exact filename>"
    }}
  ],

  "people_and_org": {{
    "key_executives": [
      {{
        "name": "<full name as stated>",
        "title": "<exact title as stated — e.g. 'Chief Executive Officer' or 'VP of Sales'>",
        "tenure_with_company": "<years or date joined as stated — e.g. '8 years' or 'joined 2017'>",
        "background_note": "<prior role, company, or credential as stated — e.g. 'Previously at Morgan Stanley Investment Banking'>",
        "operational_role": "<true if actively involved in operations; false if passive/non-operational>",
        "source_doc": "<exact VDR filename>",
        "source_location": "<page or section>"
      }}
    ],
    "ownership": [
      {{
        "owner_name": "<name as stated>",
        "ownership_pct": "<% as stated — e.g. '92%'>",
        "entity": "<which entity they own % in, if multiple entities stated>",
        "operational_role": "<their role description as stated — e.g. 'CEO' or 'no involvement in operations' or 'part-time nurse'>",
        "source_doc": "<exact VDR filename>"
      }}
    ],
    "entity_structure_note": "<description of corporate/entity structure as stated — e.g. 'S-Corp operating entity, with LLC subsidiaries in CT, MA, NJ' or null>",
    "management_depth_note": "<any stated description of bench strength, management layers, or key-man risk, or null>",
    "source_doc": "<exact VDR filename>"
  }},

  "workforce_capacity": {{
    "total_headcount": "<total stated headcount as of most recent period — e.g. '108 as of Dec-24'>",
    "headcount_period": "<period this headcount applies to>",
    "headcount_by_function": [
      {{
        "function": "<functional area name as stated — e.g. 'Engineering', 'Sales', 'Clinical', 'Finance'>",
        "headcount": "<count as stated>",
        "avg_salary_stated": "<average salary as stated, or null>",
        "location_type": "<onsite | offshore | hybrid | contract | unknown>",
        "source_doc": "<exact VDR filename>"
      }}
    ],
    "workforce_model": {{
      "us_or_onsite_headcount": "<count as stated or null>",
      "offshore_or_contract_headcount": "<count as stated or null>",
      "offshore_pct_of_total": "<% as stated or computed from two stated numbers — e.g. '41%'>",
      "cost_advantage_note": "<any stated cost arbitrage or savings from the workforce model>",
      "growth_note": "<headcount growth % or absolute change vs prior period as stated>",
      "source_doc": "<exact VDR filename>"
    }},
    "hiring_and_growth": {{
      "hiring_rate": "<stated hiring rate — e.g. '25 hires/month', '6 caregivers/week in NYC', '1,300/year'>",
      "time_to_fill_note": "<any stated time-to-fill or recruiting cycle length>",
      "capacity_constraint_note": "<any stated constraint on hiring or scaling capacity>",
      "source_doc": "<exact VDR filename>"
    }}
  }},

  "customer_operational_metrics": {{
    "total_customers_or_accounts": "<total active customers/accounts/clients as of most recent period>",
    "customer_count_period": "<period this count applies to>",
    "by_location": [
      {{
        "location": "<location, market, or segment name as stated>",
        "customer_count": "<count as stated>",
        "revenue_per_customer_per_period": "<$ per customer per period as stated — e.g. '$2,749/week' or '$85K ACV' or null>",
        "utilization_per_customer": "<usage or activity metric per customer as stated — e.g. '67 hrs/week', '4.2 sessions/month', '85% seat utilization' or null>",
        "period": "<period>",
        "source_doc": "<exact VDR filename>"
      }}
    ],
    "tenure_distribution": {{
      "distribution_buckets": [
        {{
          "bucket": "<duration bucket label as stated — e.g. '<1 month', '1-3 months', '1-2 years', '3+ years'>",
          "pct": "<% of customers in this bucket as stated>"
        }}
      ],
      "longest_bucket_pct": "<% of customers in the longest-tenure bucket — key stickiness indicator>",
      "avg_tenure_stated": "<stated average tenure or null>",
      "period_covered": "<which cohort or period this distribution covers>",
      "source_doc": "<exact VDR filename>"
    }},
    "growth_trend_note": "<description of customer count trend over time as stated — e.g. 'clients grew from 125 to 595 Q1-20 to Q4-24E'>",
    "source_doc": "<exact VDR filename>"
  }},

  "customer_profile": {{
    "segments_description": "<description of who the customers are — demographics, size, buyer type>",
    "end_markets": ["<end market 1>", "<end market 2>"],
    "geographic_concentration": "<factual description with $ or % amounts where stated>",
    "client_tenure": {{
      "avg_tenure_stated": "<average tenure as stated, or null>",
      "tenure_distribution_note": "<summary of distribution if customer_operational_metrics.tenure_distribution is populated>",
      "source_doc": "<exact filename or null>"
    }},
    "overlay_specific": {{
      "healthcare": {{
        "referral_source_breakdown": [
          {{
            "source_type": "<exact label from the document>",
            "pct_of_volume_or_profit": "<% as stated — MUST populate if a % is present>",
            "period": "<period>",
            "source_doc": "<exact filename>"
          }}
        ],
        "payor_mix": [
          {{
            "payor_type": "<exact label from the document>",
            "pct_of_revenue": "<% as stated — MUST populate if a % is present>",
            "source_doc": "<exact filename>"
          }}
        ]
      }},
      "tech_services": {{
        "customer_size_mix": "<enterprise vs. mid-market vs. SMB split as stated, or null>",
        "vertical_concentration": "<any stated vertical or industry concentration, or null>"
      }},
      "b2b_saas": {{
        "arr_by_tier": "<any stated ARR split by plan tier or segment, or null>",
        "icp_description": "<ideal customer profile as stated, or null>"
      }}
    }}
  }},

  "sales_motion": {{
    "tag": "<choose one tag from the system prompt list. 'relationship' = growth depends on personal networks with referral sources/partners. 'enterprise_sales' = structured inbound/outbound pipeline with dedicated AEs>",
    "description": "<factual description of the sales process using document language>",
    "key_roles": ["<specific names and titles as stated>"],
    "process_note": "<any stated touchpoint cadence, deal cycle, or qualification process>",
    "compensation_model": "<salesperson/BD compensation structure as stated — do NOT return null if any mechanism is described>",
    "source_doc": "<exact VDR filename>",
    "source_location": "<page or section>"
  }},

  "revenue_visibility": {{
    "contracted_pct_of_forward_12mo": "<% as stated or null>",
    "backlog_coverage_months": "<months as stated or null>",
    "backlog_dollars": "<$ backlog as stated or null>",
    "pipeline_description": "<any forward revenue pipeline description>",
    "renewal_cadence_note": "<any stated renewal rate, auto-renewal, or retention mechanism>",
    "msa_sow_coverage_note": "<MSA, SOW, or retainer coverage as stated, or null>",
    "recurring_revenue_proxy": "<any stated proxy for forward revenue — tenure data, utilization, pipeline coverage>",
    "source_doc": "<exact VDR filename>"
  }},

  "key_dependencies": [
    {{
      "dependency_type": "<vendor | platform | channel | partner | person | geography | customer | team>",
      "name": "<specific named system, team, vendor, or person — one record per named entity>",
      "description": "<role or nature of the dependency as stated>",
      "concentration_risk": "<true | false | null>",
      "source_doc": "<exact VDR filename>"
    }}
  ],

  "recent_model_changes": [
    {{
      "change_type": "<revenue_model | pricing | gtm | customer_mix | technology | geography | ma | staffing | product | operational>",
      "description": "<specific factual description using document language>",
      "approximate_date": "<year or quarter as stated>",
      "impact_note": "<stated quantified or qualitative impact, or null>",
      "source_doc": "<exact VDR filename>",
      "source_location": "<page or section>"
    }}
  ],

  "overlay_conflict_evidence": "<any text inconsistent with the confirmed industry overlay, or null>",

  "citations": [
    {{
      "field": "<field_name>",
      "document": "<exact VDR filename — must NOT be 'COMPANY PROFILE'>",
      "location": "<page number or section title>",
      "quote": "<≤30 word direct quote>",
      "confidence": "<high | medium | low>"
    }}
  ],

  "executive_summary": "<5–6 sentence factual summary covering: (1) what the company does and at what revenue scale; (2) how it earns revenue and the margin profile; (3) who leads the company and any ownership/key-man context; (4) workforce model and delivery capacity; (5) customer stickiness signal from tenure or utilization data; (6) what has changed recently. Use numbers where stated.>",

  "extraction_notes": "<note: whether a CIM was present; fields null because genuinely absent; overlay-specific fields skipped; any ambiguities>"
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
            top_k=18,
            file_name_filter=["CIM", "OM", "Overview", "Offering", "Memorandum",
                              "Profile", "Summary", "Presentation", "Deck",
                              "Management", "Executive"],
            min_chunk_length=150,
            min_results=3,
        )
        source_docs = list({c.file_name for c in chunks})
        return self._tool_call(
            tool_name="retrieve_business_overview",
            input_summary="query=company overview products services geographic footprint; workstream=BUSINESS_MODEL; top_k=18 (with fallback)",
            data=chunks,
            output_summary=f"{len(chunks)} chunks from {len(source_docs)} files",
            confidence="high" if chunks else "low",
            source_docs=source_docs,
        )

    def _tool_retrieve_people_and_org(self, spark):
        """Key executives, management team depth, ownership structure, entity structure.

        Industry-agnostic — retrieves whatever people and org content is present:
        - Healthcare: physician/clinical owner, practice administrator, COO, directors
        - Tech services: founder/CEO, CTO, VP Sales, delivery head, practice leads
        - SaaS: founding team, CTO, VP Product, VP Customer Success, board composition
        - Industrial: plant manager, engineering director, operations VP, GM
        - All: ownership table (% per shareholder), entity structure, key-man assessment,
          management bench depth, tenure of leadership team
        """
        chunks = self._semantic_search_with_fallback(
            spark=spark,
            query=(
                "management team key executives CEO founder CTO COO VP president director "
                "ownership structure capitalization shareholder equity ownership percentage "
                "organizational chart org chart key personnel management depth bench "
                "entity structure subsidiary holding company operating entity "
                "executive biography background experience years tenure "
                "key man risk leadership team senior management"
            ),
            workstream_filter=["BUSINESS_MODEL"],
            top_k=15,
            file_name_filter=["CIM", "OM", "Management", "Team", "Overview",
                              "Org", "Chart", "Cap", "Table", "Personnel",
                              "Executive", "Leadership", "Presentation"],
            min_chunk_length=100,
            min_results=3,
        )
        source_docs = list({c.file_name for c in chunks})
        return self._tool_call(
            tool_name="retrieve_people_and_org",
            input_summary=(
                "query=management team executives ownership structure org chart entity; "
                "workstream=BUSINESS_MODEL; top_k=15 (with fallback)"
            ),
            data=chunks,
            output_summary=f"{len(chunks)} chunks from {len(source_docs)} files",
            confidence="high" if chunks else "low",
            source_docs=source_docs,
        )

    def _tool_retrieve_workforce_and_capacity(self, spark):
        """Workforce headcount, cost structure, hiring rate, and delivery capacity.

        Industry-agnostic — retrieves whatever workforce data is present:
        - Healthcare: caregiver headcount by location, hiring rate, US vs offshore split,
          admin staff count and cost, scheduled caregiver growth trend
        - Tech services: billable headcount, bench, utilization, offshore delivery team,
          revenue per FTE, contractor vs. employee split
        - SaaS: R&D headcount, sales headcount, CS headcount, revenue per employee
        - Industrial: plant workers, engineers, contract labor, capacity utilization
        - All: total headcount, headcount growth trend, average compensation, payroll cost
        """
        chunks = self._semantic_search_with_fallback(
            spark=spark,
            query=(
                "headcount employees staff workforce count by location by function "
                "average salary compensation payroll cost by team by department "
                "hiring rate hires per week time to fill recruiting capacity "
                "US versus offshore global outsourced contract versus full-time "
                "workforce growth headcount trend prior period current period "
                "billable staff delivery team bench utilization per employee "
                "caregiver count clinician count consultant count engineer count "
                "scheduled workforce active workforce capacity by market by region"
            ),
            workstream_filter=["BUSINESS_MODEL", "KPI_OPS", "FINANCIAL"],
            top_k=15,
            file_name_filter=["CIM", "OM", "Team", "Headcount", "Workforce",
                              "Staff", "Recruiting", "Capacity", "Operations",
                              "Overview", "KPI", "Dashboard", "Metrics"],
            min_chunk_length=100,
            min_results=3,
        )
        source_docs = list({c.file_name for c in chunks})
        return self._tool_call(
            tool_name="retrieve_workforce_and_capacity",
            input_summary=(
                "query=headcount employees salary compensation hiring rate US vs offshore "
                "delivery capacity workforce growth; workstream=BUSINESS_MODEL,KPI_OPS,FINANCIAL; "
                "top_k=15 (with fallback)"
            ),
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
            top_k=15,
            file_name_filter=["CIM", "Pricing", "Financial", "Revenue", "Margin",
                              "OM", "Overview", "Rate", "Card"],
            min_chunk_length=100,
            min_results=3,
        )
        source_docs = list({c.file_name for c in chunks})
        return self._tool_call(
            tool_name="retrieve_pricing_and_margins",
            input_summary="query=pricing gross margin by service/product bill rate; workstream=BUSINESS_MODEL,FINANCIAL; top_k=15 (with fallback)",
            data=chunks,
            output_summary=f"{len(chunks)} chunks from {len(source_docs)} files",
            confidence="high" if chunks else "low",
            source_docs=source_docs,
        )

    def _tool_retrieve_revenue_by_location_and_metrics(self, spark):
        """Revenue breakdown by location/segment and operational metrics that
        serve as recurring revenue proxies.

        Industry-agnostic — adapts to whatever operational data is present:
        - Healthcare: billed hours per client, census, length of stay, patient tenure
        - SaaS: ARR by cohort, NRR by segment, logo count by tier
        - Tech services: utilization by practice, revenue per FTE, backlog by client
        - Industrial: revenue by product line, capacity utilization, order intake
        - Consumer: repeat rate, LTV by cohort, revenue by channel or geography
        - All: headline CAGR, EBITDA summary, revenue by geography, M&A pipeline
        """
        chunks = self._semantic_search_with_fallback(
            spark=spark,
            query=(
                "clients served active accounts customers by location by market by segment "
                "billed hours per client revenue per customer revenue per account "
                "utilization per customer sessions per user visits per patient "
                "customer count trend quarterly growth by location by geography "
                "length of stay customer tenure distribution cohort by duration "
                "revenue per location revenue by market adjusted revenue by geography "
                "revenue CAGR financial highlights headline metrics acquisition pipeline "
                "same store revenue organic growth by market revenue goal by location"
            ),
            workstream_filter=["BUSINESS_MODEL", "FINANCIAL", "KPI_OPS"],
            top_k=15,
            file_name_filter=["CIM", "OM", "Financial", "Revenue", "Metrics",
                              "Overview", "Summary", "KPI", "Dashboard"],
            min_chunk_length=100,
            min_results=3,
        )
        source_docs = list({c.file_name for c in chunks})
        return self._tool_call(
            tool_name="retrieve_revenue_by_location_and_metrics",
            input_summary=(
                "query=revenue by location segment client metrics billed hours tenure "
                "acquisition pipeline; workstream=BUSINESS_MODEL,FINANCIAL,KPI_OPS; "
                "top_k=15 (with fallback)"
            ),
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
            top_k=15,
            file_name_filter=["CIM", "Sales", "GTM", "Customer", "Marketing",
                              "Overview", "OM", "Strategy", "Presentation"],
            min_chunk_length=150,
            min_results=3,
        )
        source_docs = list({c.file_name for c in chunks})
        return self._tool_call(
            tool_name="retrieve_sales_and_customers",
            input_summary="query=sales motion GTM customer acquisition segments; workstream=BUSINESS_MODEL,KPI_OPS; top_k=15 (with fallback)",
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
                "customer tenure average tenure length of stay cohort distribution "
                "revenue per customer units per client usage per account sessions per user "
                "acquisition pipeline M&A targets addressable market revenue goal by market "
                "revenue predictability pipeline coverage months weighted pipeline "
                "repeat purchase rate retention cohort same store revenue trajectory "
                "order backlog booking rate renewal cadence contract coverage"
            ),
            workstream_filter=["BUSINESS_MODEL", "FINANCIAL", "KPI_OPS"],
            top_k=12,
            file_name_filter=["CIM", "Pipeline", "Backlog", "Contract", "Revenue",
                              "KPI", "Metrics", "Overview", "Model"],
            min_chunk_length=100,
            min_results=3,
        )
        source_docs = list({c.file_name for c in chunks})
        return self._tool_call(
            tool_name="retrieve_revenue_visibility",
            input_summary="query=backlog contracted pipeline retention tenure; workstream=BUSINESS_MODEL,FINANCIAL,KPI_OPS; top_k=12 (with fallback)",
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
                "ERP CRM EMR payroll HR software scheduling platform technology system "
                "outsourcing offshore remote team global staffing third-party operations "
                "acquisition M&A history strategic initiative timeline milestones "
                "launched expanded hired opened acquired transitioned implemented automated "
                "key dependency concentration risk single vendor platform tool "
                "new product new service new geography new channel new pricing model "
                "digital transformation process improvement technology adoption"
            ),
            workstream_filter=["BUSINESS_MODEL", "KPI_OPS"],
            top_k=18,
            file_name_filter=["CIM", "Overview", "Timeline", "History", "OM",
                              "Strategy", "Presentation", "Management", "Deck"],
            min_chunk_length=150,
            min_results=5,
        )
        source_docs = list({c.file_name for c in chunks})
        return self._tool_call(
            tool_name="retrieve_model_changes_and_dependencies",
            input_summary="query=model changes pricing GTM dependencies vendor platform; workstream=BUSINESS_MODEL,KPI_OPS; top_k=18 (with fallback)",
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
        tr_ppl  = self._tool_retrieve_people_and_org(spark)
        tr_wf   = self._tool_retrieve_workforce_and_capacity(spark)
        tr1     = self._tool_retrieve_business_overview(spark)
        tr2     = self._tool_retrieve_pricing_and_margins(spark)
        tr7     = self._tool_retrieve_revenue_by_location_and_metrics(spark)
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
        for tr in (tr_ppl, tr_wf, tr1, tr2, tr3, tr4, tr5, tr7):
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

        # People & org checks
        _pao = extracted.get("people_and_org") or {}
        if not (_pao.get("key_executives") or []):
            self._add_gap(
                "people_and_org.key_executives is empty — management team not extracted. "
                "Check retrieval coverage of management team and org sections."
            )

        if not (_pao.get("ownership") or []):
            self._add_gap(
                "people_and_org.ownership is empty — ownership structure not extracted. "
                "Key-man and equity structure assessment requires this. Check retrieval of "
                "capitalization, entity structure, or transaction overview sections."
            )

        # Workforce checks
        _wfc = extracted.get("workforce_capacity") or {}
        if not _wfc.get("total_headcount") and not (_wfc.get("headcount_by_function") or []):
            self._add_gap(
                "workforce_capacity is empty — headcount and workforce model not extracted. "
                "Check retrieval of team, staffing, and operational sections."
            )

        # Customer operational metrics checks
        _com = extracted.get("customer_operational_metrics") or {}
        if not (_com.get("by_location") or []) and not _com.get("total_customers_or_accounts"):
            self._add_gap(
                "customer_operational_metrics is empty — customer count, utilization, and "
                "tenure data not extracted. Check retrieval of client metrics sections."
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
            "input":      f"combined context: {len(all_chunks)} chunks from {len(seen_texts)} unique texts (9 retrieval tools)",
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
            "revenue_by_location_json":      json.dumps(extracted.get("revenue_by_location") or []),
            "people_and_org_json":               json.dumps(extracted.get("people_and_org") or {}),
            "workforce_capacity_json":           json.dumps(extracted.get("workforce_capacity") or {}),
            "customer_operational_metrics_json": json.dumps(extracted.get("customer_operational_metrics") or {}),
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
        "products_and_services":            json.loads(result.get("products_services_json") or "[]"),
        "revenue_by_location":              json.loads(result.get("revenue_by_location_json") or "[]"),
        "people_and_org":                   json.loads(result.get("people_and_org_json") or "{}"),
        "workforce_capacity":               json.loads(result.get("workforce_capacity_json") or "{}"),
        "customer_operational_metrics":     json.loads(result.get("customer_operational_metrics_json") or "{}"),
        "customer_profile":                 json.loads(result.get("customer_profile_json") or "{}"),
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
# Business model assessment report (rich markdown with LLM narrative)
# ---------------------------------------------------------------------------

def generate_business_model_assessment(
    result: dict,
    spark,
    llm_endpoint: str,
    catalog: str = "uc13",
    write_to_volume: bool = True,
) -> str:
    """Generate a structured markdown business model assessment from agent output.

    Builds deterministic tables (products/services, customer profile, sales motion,
    revenue visibility, key dependencies, recent changes) then makes a single LLM
    call to write narrative for each section.

    Args:
        result:          Output dict from BusinessModelAgent.run() or bma.main().
        spark:           Active SparkSession (needed only when write_to_volume=True).
        llm_endpoint:    Databricks model-serving endpoint name.
        catalog:         UC catalog for volume write (default 'uc13').
        write_to_volume: If True, also writes the markdown to the reports volume.

    Returns:
        Markdown string.
    """
    import mlflow.deployments

    company_name   = result.get("company_name", "Company")
    generated_at   = result.get("created_at", "")
    cim_detected   = result.get("cim_detected", False)
    exec_summary   = result.get("executive_summary") or ""
    rm_tag         = result.get("revenue_model_tag") or ""
    rm_split       = result.get("revenue_model_pct_split") or ""
    rm_note        = result.get("revenue_model_note") or ""
    rm_flag        = result.get("revenue_durability_flag") or ""
    rm_flag_rule   = result.get("flag_rule_applied") or ""
    sm_tag         = result.get("sales_motion_tag") or ""
    flags          = result.get("flags") or []
    data_room_gaps = result.get("data_room_gaps") or []

    products        = json.loads(result.get("products_services_json")    or "[]")
    cp              = json.loads(result.get("customer_profile_json")     or "{}")
    sm              = json.loads(result.get("sales_motion_json")         or "{}")
    rv              = json.loads(result.get("revenue_visibility_json")   or "{}")
    key_deps        = json.loads(result.get("key_dependencies_json")     or "[]")
    model_changes   = json.loads(result.get("recent_model_changes_json") or "[]")

    # ── Helper: markdown table ─────────────────────────────────────────────
    def _md_table(headers: list[str], rows: list[list]) -> str:
        if not rows:
            return "_No data extracted._\n"
        col_w = [
            max(len(str(h)), max((len(str(r[i] if i < len(r) else "")) for r in rows), default=0))
            for i, h in enumerate(headers)
        ]
        sep  = "| " + " | ".join("-" * w for w in col_w) + " |"
        head = "| " + " | ".join(str(h).ljust(col_w[i]) for i, h in enumerate(headers)) + " |"
        body = "\n".join(
            "| " + " | ".join(str(r[i] if i < len(r) else "").ljust(col_w[i]) for i in range(len(headers))) + " |"
            for r in rows
        )
        return "\n".join([head, sep, body]) + "\n"

    # ── Helper: severity emoji ─────────────────────────────────────────────
    def _flag_emoji(severity: str) -> str:
        return {"Red": "🔴", "Yellow": "🟡", "Green": "🟢"}.get(severity, "⚪")

    # ══════════════════════════════════════════════════════════════════════
    # TABLE 1 — Products & Services (margin by offering)
    # ══════════════════════════════════════════════════════════════════════
    ps_rows = []
    for p in products:
        ps_rows.append([
            p.get("name") or "—",
            p.get("revenue_pct") or "—",
            p.get("gm_pct_stated") or "—",
            p.get("avg_price_or_rate") or "—",
            (p.get("gm_pct_note") or "")[:60],
        ])
    tbl_products = _md_table(
        ["Offering", "Rev %", "GM %", "Avg Price / Rate", "Margin Note"],
        ps_rows,
    )

    # ══════════════════════════════════════════════════════════════════════
    # TABLE — Revenue by location
    # ══════════════════════════════════════════════════════════════════════
    rev_loc = json.loads(result.get("revenue_by_location_json") or "[]")
    rev_loc_rows = [
        [
            r.get("location") or "—",
            r.get("revenue_dollars") or "—",
            r.get("revenue_pct") or "—",
            r.get("period") or "—",
        ]
        for r in rev_loc
    ]
    tbl_rev_loc = _md_table(
        ["Location / Market", "Revenue ($)", "Rev %", "Period"],
        rev_loc_rows,
    ) if rev_loc_rows else ""

    # ══════════════════════════════════════════════════════════════════════
    # TABLE — Key executives
    # ══════════════════════════════════════════════════════════════════════
    pao       = json.loads(result.get("people_and_org_json") or "{}")
    execs     = pao.get("key_executives") or []
    exec_rows = [
        [
            e.get("name") or "—",
            e.get("title") or "—",
            e.get("tenure_with_company") or "—",
            (e.get("background_note") or "—")[:80],
            "Yes" if e.get("operational_role") else "No",
        ]
        for e in execs
    ]
    tbl_execs = _md_table(
        ["Name", "Title", "Tenure", "Background", "Operational"],
        exec_rows,
    ) if exec_rows else ""

    # ══════════════════════════════════════════════════════════════════════
    # TABLE — Ownership
    # ══════════════════════════════════════════════════════════════════════
    owners     = pao.get("ownership") or []
    owner_rows = [
        [
            o.get("owner_name") or "—",
            o.get("ownership_pct") or "—",
            o.get("entity") or "—",
            (o.get("operational_role") or "—")[:60],
        ]
        for o in owners
    ]
    tbl_ownership = _md_table(
        ["Owner", "Ownership %", "Entity", "Role"],
        owner_rows,
    ) if owner_rows else ""

    # ══════════════════════════════════════════════════════════════════════
    # TABLE — Workforce capacity
    # ══════════════════════════════════════════════════════════════════════
    wfc        = json.loads(result.get("workforce_capacity_json") or "{}")
    wf_model   = wfc.get("workforce_model") or {}
    hbf        = wfc.get("headcount_by_function") or []
    hbf_rows   = [
        [
            h.get("function") or "—",
            h.get("headcount") or "—",
            h.get("avg_salary_stated") or "—",
            h.get("location_type") or "—",
        ]
        for h in hbf
    ]
    tbl_workforce = _md_table(
        ["Function", "Headcount", "Avg Salary", "Type"],
        hbf_rows,
    ) if hbf_rows else ""

    # ══════════════════════════════════════════════════════════════════════
    # TABLE — Customer operational metrics by location
    # ══════════════════════════════════════════════════════════════════════
    com        = json.loads(result.get("customer_operational_metrics_json") or "{}")
    com_locs   = com.get("by_location") or []
    com_rows   = [
        [
            c.get("location") or "—",
            c.get("customer_count") or "—",
            c.get("revenue_per_customer_per_period") or "—",
            c.get("utilization_per_customer") or "—",
            c.get("period") or "—",
        ]
        for c in com_locs
    ]
    tbl_com = _md_table(
        ["Location", "Customers", "Rev/Customer", "Utilization", "Period"],
        com_rows,
    ) if com_rows else ""

    # ══════════════════════════════════════════════════════════════════════
    # TABLE — Customer tenure distribution
    # ══════════════════════════════════════════════════════════════════════
    ten_dist   = (com.get("tenure_distribution") or {}).get("distribution_buckets") or []
    ten_rows   = [
        [b.get("bucket") or "—", b.get("pct") or "—"]
        for b in ten_dist
    ]
    tbl_tenure = _md_table(["Tenure Bucket", "% of Customers"], ten_rows) if ten_rows else ""

    # ══════════════════════════════════════════════════════════════════════
    # TABLE 2 — Revenue visibility
    # ══════════════════════════════════════════════════════════════════════
    rv_rows = []
    rv_field_labels = {
        "contracted_pct_of_forward_12mo": "Contracted % (fwd 12mo)",
        "backlog_coverage_months":         "Backlog (months)",
        "backlog_dollars":                 "Backlog ($)",
        "pipeline_description":            "Pipeline",
        "renewal_cadence_note":            "Renewal / Retention",
        "msa_sow_coverage_note":           "MSA / SOW Coverage",
        "recurring_revenue_proxy":         "Recurring Proxy",
    }
    for field, label in rv_field_labels.items():
        val = rv.get(field)
        if val:
            rv_rows.append([label, str(val)[:120]])
    tbl_visibility = _md_table(["Signal", "Detail"], rv_rows)

    # ══════════════════════════════════════════════════════════════════════
    # TABLE 3 — Key dependencies
    # ══════════════════════════════════════════════════════════════════════
    dep_rows = []
    for d in key_deps:
        risk = "⚠ Yes" if str(d.get("concentration_risk")).lower() == "true" else "—"
        dep_rows.append([
            d.get("dependency_type") or "—",
            d.get("name") or "—",
            (d.get("description") or "")[:80],
            risk,
        ])
    tbl_deps = _md_table(["Type", "Name", "Description", "Conc. Risk"], dep_rows)

    # ══════════════════════════════════════════════════════════════════════
    # TABLE 4 — Recent model changes
    # ══════════════════════════════════════════════════════════════════════
    chg_rows = []
    for c in model_changes:
        chg_rows.append([
            c.get("change_type") or "—",
            c.get("approximate_date") or "—",
            (c.get("description") or "")[:90],
        ])
    tbl_changes = _md_table(["Type", "Date", "Description"], chg_rows)

    # ══════════════════════════════════════════════════════════════════════
    # TABLE 5 — Flags summary
    # ══════════════════════════════════════════════════════════════════════
    flag_rows = [
        [
            _flag_emoji(f.get("severity", "")) + " " + f.get("severity", ""),
            f.get("metric", ""),
            f.get("value", "")[:60],
            f.get("threshold", "")[:60],
        ]
        for f in flags
    ]
    tbl_flags = _md_table(["Severity", "Metric", "Value", "Threshold"], flag_rows)

    # ══════════════════════════════════════════════════════════════════════
    # Customer profile sub-sections
    # ══════════════════════════════════════════════════════════════════════
    ov_specific = cp.get("overlay_specific") or {}
    hc          = ov_specific.get("healthcare") or {}
    tech        = ov_specific.get("tech_services") or {}
    saas        = ov_specific.get("b2b_saas") or {}

    ref_rows = [
        [r.get("source_type") or "—", r.get("pct_of_volume_or_profit") or "—", r.get("period") or "—"]
        for r in (hc.get("referral_source_breakdown") or [])
    ]
    tbl_referrals = _md_table(["Referral Source", "% of Volume / Profit", "Period"], ref_rows) if ref_rows else ""

    payor_rows = [
        [p.get("payor_type") or "—", p.get("pct_of_revenue") or "—"]
        for p in (hc.get("payor_mix") or [])
    ]
    tbl_payor = _md_table(["Payor Type", "% of Revenue"], payor_rows) if payor_rows else ""

    # ══════════════════════════════════════════════════════════════════════
    # Assemble data context passed to the LLM for narrative
    # ══════════════════════════════════════════════════════════════════════
    tenure = cp.get("client_tenure") or {}

    data_summary = f"""
COMPANY: {company_name}
CIM DETECTED: {cim_detected}
EXECUTIVE SUMMARY: {exec_summary}

REVENUE MODEL:
  Tag: {rm_tag}
  Pct Split: {rm_split or 'not stated'}
  Note: {rm_note}
  Durability Flag: {rm_flag} — {rm_flag_rule}

SALES MOTION:
  Tag: {sm_tag}
  Description: {sm.get('description') or 'not stated'}
  Key Roles: {sm.get('key_roles') or []}
  Process Note: {sm.get('process_note') or 'not stated'}
  Compensation: {sm.get('compensation_model') or 'not stated'}

CUSTOMER PROFILE:
  Segments: {cp.get('segments_description') or 'not stated'}
  End Markets: {cp.get('end_markets') or []}
  Geographic Concentration: {cp.get('geographic_concentration') or 'not stated'}
  Client Tenure: {tenure.get('avg_tenure_stated') or 'not stated'} — {tenure.get('tenure_distribution_note') or ''}
  Customer Size Mix (tech): {tech.get('customer_size_mix') or 'n/a'}
  Vertical Concentration (tech): {tech.get('vertical_concentration') or 'n/a'}
  ICP (SaaS): {saas.get('icp_description') or 'n/a'}

PRODUCTS & SERVICES TABLE:
{tbl_products}

REVENUE VISIBILITY TABLE:
{tbl_visibility}

KEY DEPENDENCIES TABLE:
{tbl_deps}

RECENT MODEL CHANGES TABLE:
{tbl_changes}

{"REFERRAL SOURCE BREAKDOWN:" + chr(10) + tbl_referrals if tbl_referrals else ""}
{"PAYOR MIX:" + chr(10) + tbl_payor if tbl_payor else ""}

OVERLAY CONFLICT: {result.get("overlay_conflict", False)}
{"CONFLICT NOTE: " + result.get("overlay_conflict_note", "") if result.get("overlay_conflict") else ""}

INVESTMENT FLAGS:
{json.dumps(flags, indent=2)}

DATA ROOM GAPS:
{chr(10).join("- " + g for g in data_room_gaps) if data_room_gaps else "None"}

PEOPLE AND ORG:
  Key Executives: {json.dumps([{k: v for k, v in e.items() if k != 'source_doc'} for e in execs], indent=2) if execs else 'not extracted'}
  Ownership: {json.dumps([{k: v for k, v in o.items() if k != 'source_doc'} for o in owners], indent=2) if owners else 'not extracted'}
  Entity Structure: {pao.get('entity_structure_note') or 'not stated'}
  Management Depth: {pao.get('management_depth_note') or 'not stated'}

WORKFORCE CAPACITY:
  Total Headcount: {wfc.get('total_headcount') or 'not stated'}
  Workforce Model: US/onsite={wf_model.get('us_or_onsite_headcount') or 'null'}, Offshore/contract={wf_model.get('offshore_or_contract_headcount') or 'null'}, Offshore%={wf_model.get('offshore_pct_of_total') or 'null'}
  Cost Advantage: {wf_model.get('cost_advantage_note') or 'not stated'}
  Growth: {wf_model.get('growth_note') or 'not stated'}
  Hiring Rate: {(wfc.get('hiring_and_growth') or {}).get('hiring_rate') or 'not stated'}
  Headcount by Function:
{tbl_workforce}

CUSTOMER OPERATIONAL METRICS:
  Total Customers: {com.get('total_customers_or_accounts') or 'not stated'}
  Growth Trend: {com.get('growth_trend_note') or 'not stated'}
  By Location:
{tbl_com}
  Tenure Distribution:
{tbl_tenure}
  Longest Tenure Bucket: {(com.get('tenure_distribution') or {}).get('longest_bucket_pct') or 'not stated'}
""".strip()

    # ══════════════════════════════════════════════════════════════════════
    # LLM call — business model narrative
    # ══════════════════════════════════════════════════════════════════════
    _ASSESS_SYS = """\
You are a senior PE investment analyst writing the Business Model section of an
internal diligence memo. Use the structured data provided to answer 9 specific
questions about the company's revenue model, management team, workforce, customer
profile, go-to-market, revenue visibility, key risks, and recent changes.

Rules:
1. Write only what the data supports. Do not invent facts.
2. If a section cannot be assessed because data is missing, write one sentence
   explaining what is missing and why it matters for underwriting.
3. Use concrete details from the tables (names, percentages, dates).
4. Be direct and use PE language (e.g. "referral-dependent", "low contractual
   visibility", "single-vendor dependency", "model in transition").
5. Return pure markdown only — no preamble, no code fences.
6. Structure your response with exactly these 9 section headers (H3):
   ### 1. Revenue Model & Durability
   ### 2. Products, Services & Margin Profile
   ### 3. Management Team & Ownership
   ### 4. Workforce Model & Delivery Capacity
   ### 5. Customer Profile & Acquisition
   ### 6. Sales Motion & Go-to-Market
   ### 7. Revenue Visibility & Forward Signals
   ### 8. Key Dependencies & Concentration Risks
   ### 9. Recent Business Model Changes & Trajectory
7. For each section use at most 4 bullet points followed by a 1–2 sentence
   "**Analyst take:**" line that states the signal and what it means for underwriting.
"""

    _ASSESS_USER = f"""\
Use the business model data below to answer all 7 assessment questions.
Write the markdown narrative only — no extra commentary.

{data_summary}
"""

    _client   = mlflow.deployments.get_deploy_client("databricks")
    _response = _client.predict(
        endpoint=llm_endpoint,
        inputs={
            "messages": [
                {"role": "system", "content": _ASSESS_SYS},
                {"role": "user",   "content": _ASSESS_USER},
            ],
            "max_tokens": 3000,
            "temperature": 0.1,
        },
    )
    narrative = _response["choices"][0]["message"]["content"].strip()

    # ══════════════════════════════════════════════════════════════════════
    # Assemble final markdown
    # ══════════════════════════════════════════════════════════════════════
    flag_order = {"Red": 0, "Yellow": 1, "Green": 2}
    flags_sorted = sorted(flags, key=lambda f: flag_order.get(f.get("severity", ""), 3))

    md: list[str] = []

    md.append(f"# {company_name} — Business Model Assessment")
    md.append(
        f"**Generated:** {generated_at}  \n"
        f"**CIM / Banker Document Detected:** {'Yes' if cim_detected else 'No — non-banked deal; confidence reduced'}\n"
    )

    if exec_summary:
        md.append(f"> {exec_summary}\n")

    md.append("---\n")

    # ── Investment flags quick-reference ──────────────────────────────────
    if flags_sorted:
        md.append("## Investment Flags\n")
        md.append(tbl_flags)
        md.append("")

    # ── Supporting data tables ─────────────────────────────────────────────
    md.append("---\n")
    md.append("## Supporting Data\n")

    md.append("### Revenue Model\n")
    md.append(_md_table(
        ["Field", "Value"],
        [
            ["Tag",              rm_tag or "—"],
            ["Pct Split",        rm_split or "not stated"],
            ["Note",             (rm_note or "—")[:120]],
            ["Durability Flag",  f"{_flag_emoji(rm_flag)} {rm_flag}"],
            ["Flag Rule",        (rm_flag_rule or "—")[:100]],
        ],
    ))

    md.append("### Products & Services\n")
    md.append(tbl_products)

    if tbl_rev_loc:
        md.append("### Revenue by Location\n")
        md.append(tbl_rev_loc)

    if tbl_execs:
        md.append("### Key Executives\n")
        md.append(tbl_execs)
        if pao.get("entity_structure_note"):
            md.append(f"**Entity structure:** {pao['entity_structure_note']}\n")
        if pao.get("management_depth_note"):
            md.append(f"**Management depth:** {pao['management_depth_note']}\n")

    if tbl_ownership:
        md.append("### Ownership Structure\n")
        md.append(tbl_ownership)

    if tbl_workforce or wf_model:
        md.append("### Workforce & Capacity\n")
        if wfc.get("total_headcount"):
            md.append(f"**Total headcount:** {wfc['total_headcount']}\n")
        if tbl_workforce:
            md.append(tbl_workforce)
        if wf_model:
            wf_summary_rows = [
                [k.replace("_", " ").title(), str(v)[:100]]
                for k, v in wf_model.items()
                if v and k != "source_doc"
            ]
            if wf_summary_rows:
                md.append(_md_table(["Workforce Model Field", "Detail"], wf_summary_rows))
        hiring = wfc.get("hiring_and_growth") or {}
        if hiring.get("hiring_rate"):
            md.append(f"**Hiring rate:** {hiring['hiring_rate']}\n")
        if hiring.get("capacity_constraint_note"):
            md.append(f"**Capacity constraint:** {hiring['capacity_constraint_note']}\n")

    if tbl_com:
        md.append("### Customer Metrics by Location\n")
        if com.get("total_customers_or_accounts"):
            md.append(f"**Total active customers:** {com['total_customers_or_accounts']}\n")
        md.append(tbl_com)
        if com.get("growth_trend_note"):
            md.append(f"**Growth trend:** {com['growth_trend_note']}\n")

    if tbl_tenure:
        md.append("### Customer Tenure Distribution\n")
        md.append(tbl_tenure)
        ten = com.get("tenure_distribution") or {}
        if ten.get("longest_bucket_pct"):
            md.append(f"**Longest tenure bucket:** {ten['longest_bucket_pct']} of customers\n")
        if ten.get("period_covered"):
            md.append(f"**Cohort covers:** {ten['period_covered']}\n")

    md.append("### Sales Motion\n")
    md.append(_md_table(
        ["Field", "Detail"],
        [
            ["Tag",           sm_tag or "—"],
            ["Description",   (sm.get("description") or "—")[:120]],
            ["Key Roles",     ", ".join(sm.get("key_roles") or []) or "—"],
            ["Process Note",  (sm.get("process_note") or "—")[:120]],
            ["Compensation",  sm.get("compensation_model") or "—"],
        ],
    ))

    md.append("### Revenue Visibility\n")
    md.append(tbl_visibility)

    md.append("### Customer Profile\n")
    cp_rows = [
        ["Segments",              (cp.get("segments_description") or "—")[:120]],
        ["End Markets",           ", ".join(cp.get("end_markets") or []) or "—"],
        ["Geographic Conc.",      (cp.get("geographic_concentration") or "—")[:120]],
        ["Avg Client Tenure",     tenure.get("avg_tenure_stated") or "—"],
        ["Tenure Distribution",   (tenure.get("tenure_distribution_note") or "—")[:100]],
    ]
    if tech.get("customer_size_mix"):
        cp_rows.append(["Customer Size Mix (tech)", tech["customer_size_mix"][:100]])
    if saas.get("icp_description"):
        cp_rows.append(["ICP (SaaS)", saas["icp_description"][:100]])
    md.append(_md_table(["Field", "Detail"], cp_rows))

    if tbl_referrals:
        md.append("### Referral Source Breakdown\n")
        md.append(tbl_referrals)

    if tbl_payor:
        md.append("### Payor Mix\n")
        md.append(tbl_payor)

    if dep_rows:
        md.append("### Key Dependencies\n")
        md.append(tbl_deps)

    if chg_rows:
        md.append("### Recent Model Changes\n")
        md.append(tbl_changes)

    if result.get("overlay_conflict"):
        md.append("### Overlay Conflict\n")
        md.append(f"> ⚠ {result.get('overlay_conflict_note')}\n")
        if result.get("overlay_conflict_evidence"):
            md.append(f"\n**Evidence:** {result.get('overlay_conflict_evidence')}\n")

    # ── LLM narrative ─────────────────────────────────────────────────────
    md.append("---\n")
    md.append("## Business Model Assessment\n")
    md.append(narrative)
    md.append("")

    # ── Data room gaps ─────────────────────────────────────────────────────
    if data_room_gaps:
        md.append("---\n")
        md.append("## Data Room Gaps\n")
        for gap in data_room_gaps:
            md.append(f"- {gap}")
        md.append("")

    final_markdown = "\n".join(md)

    # ── Optional volume write ──────────────────────────────────────────────
    if write_to_volume:
        spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.analysis.reports")
        safe_name = company_name.replace(" ", "_").replace("/", "_")
        dir_path  = f"/Volumes/{catalog}/analysis/reports/{safe_name}"
        os.makedirs(dir_path, exist_ok=True)
        file_path = f"{dir_path}/business_model_assessment.md"
        with open(file_path, "w", encoding="utf-8") as fh:
            fh.write(final_markdown)
        print(f"✓ Business model assessment → {file_path}")

    return final_markdown


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
    revenue_by_location_json      STRING,
    people_and_org_json                  STRING,
    workforce_capacity_json              STRING,
    customer_operational_metrics_json    STRING,
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
        "products_services_json", "revenue_by_location_json",
        "people_and_org_json", "workforce_capacity_json", "customer_operational_metrics_json",
        "customer_profile_json",
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
        StructField("products_services_json",               StringType(),            True),
        StructField("revenue_by_location_json",             StringType(),            True),
        StructField("people_and_org_json",                  StringType(),            True),
        StructField("workforce_capacity_json",              StringType(),            True),
        StructField("customer_operational_metrics_json",    StringType(),            True),
        StructField("customer_profile_json",                StringType(),            True),
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
        "products_services_json":               result.get("products_services_json"),
        "revenue_by_location_json":             result.get("revenue_by_location_json"),
        "people_and_org_json":                  result.get("people_and_org_json"),
        "workforce_capacity_json":              result.get("workforce_capacity_json"),
        "customer_operational_metrics_json":    result.get("customer_operational_metrics_json"),
        "customer_profile_json":                result.get("customer_profile_json"),
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
