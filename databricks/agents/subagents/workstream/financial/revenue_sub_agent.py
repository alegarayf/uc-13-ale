"""Revenue & Margins sub-agent for the Financial Trends workstream.

Responsibility:
  Retrieval  — financial_statements, revenue_by_segment, revenue_by_geography,
               customer_revenue, quickbooks_pl  (5 focused queries)
  Extraction — revenue_trend, gross_margin, revenue_by_segment, revenue_by_customer

Each instance is autonomous: it runs its own semantic_search calls, builds its
own focused context (~25K chars), and performs a single LLM extraction call.
Designed to run in parallel with EbitdaSubAgent and OpexSubAgent.

max_tokens = 10,000 — focused context means higher extraction density per token
than the former 60K shared-context approach.
"""

import json
from .shared_prompts import SYSTEM_PROMPT_BASE
from .context_utils import build_focused_context, semantic_search_with_fallback

_MAX_CONTEXT_CHARS = 25_000
_MAX_TOKENS = 10_000

_USER_PROMPT = """\
COMPANY PROFILE (metadata only — do NOT extract financial figures from this block):
{company_profile_json}

RETRIEVED FINANCIAL DOCUMENT CONTEXT (extract ALL financial figures from here only):
{focused_chunk_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXTRACTION TASK — REVENUE & MARGINS
Extract ONLY the four fields below. Return ONLY the JSON object — no preamble.

RECORD COUNT CAPS (strictly enforced — to leave token budget for segments and customers):
- revenue_trend: at most 12 records total. If more periods exist, keep the most recent
  actuals and the TTM/LTM period. Drop projected future periods (2025P-2029P) from this
  array — they appear in the P&L table via gross_margin if needed.
- gross_margin: at most 12 records total. Same priority: actuals and TTM first.
- revenue_by_segment and revenue_by_customer must always be attempted — do not skip them
  even if revenue_trend and gross_margin are already large.

NOTE: Revenue figures may live in QuickBooks P&L exports, geographic segment
spreadsheets, or individual annual workbooks — NOT only the CIM. Check all
retrieved documents before leaving revenue_trend empty.

{{
  "revenue_trend": [
    {{
      "period": "<time period ONLY — NEVER a geography, state, or entity name>",
      "label": "<exact row label — e.g. 'Total Revenue' or 'Reported Net Revenue'>",
      "revenue_stated": "<$ amount exactly as written>",
      "yoy_growth_pct": "<YoY growth % as stated — e.g. '58.3%'. Null if absent.>",
      "computed_yoy": false,
      "source_doc": "<exact filename — must NOT be 'COMPANY PROFILE'>",
      "source_location": "<page or section>"
    }}
  ],

  "gross_margin": [
    {{
      "period": "<time period ONLY>",
      "label": "<exact row label — e.g. 'Gross Profit'>",
      "gm_dollars_stated": "<$ amount from the Gross Profit row>",
      "gm_pct_stated": "<gross margin % as stated — check subordinate Margin row, inline column, narrative. Null only if genuinely absent.>",
      "computed_from_stated": false,
      "source_doc": "<exact filename — must NOT be 'COMPANY PROFILE'>",
      "source_location": "<page or section>"
    }}
  ],

  "revenue_by_segment": [
    {{
      "segment": "<geography, service line, or location — e.g. 'NYC' or 'Long Island'>",
      "revenue_pct": "<% of total revenue as stated, or null>",
      "revenue_dollars": "<$ as stated>",
      "period": "<time period>",
      "source_doc": "<exact filename>"
    }}
  ],

  "revenue_by_customer": [
    {{
      "rank": "<1–10 rank, or null>",
      "customer_name": "<name as stated — use 'Customer [N]' if anonymized>",
      "revenue_dollars": "<$ as stated>",
      "revenue_pct": "<% of total as stated, or null>",
      "period": "<time period>",
      "source_doc": "<exact filename>"
    }}
  ]
}}\
"""

_BANK_STMT_KEYWORDS = ("bank statement", "bank stmt", "eastern bank", "checking", "deposit")


class RevenueSubAgent:
    """Extracts revenue_trend, gross_margin, revenue_by_segment, revenue_by_customer.

    Autonomous: owns retrieval + context building + LLM extraction.
    Designed to run in parallel with EbitdaSubAgent and OpexSubAgent.
    """

    def run(
        self,
        company_name: str,
        spark,
        llm_endpoint: str,
        company_profile: dict | None,
    ) -> dict:
        """Run retrieval → context build → extraction.

        Returns {"extracted": dict, "gaps": list[str], "source_files": list[str]}.
        """
        _wa = self._make_base()

        chunks = self._retrieve(company_name, spark)
        context_text, stats = build_focused_context(chunks, max_chars=_MAX_CONTEXT_CHARS)
        print(f"  [Revenue] {stats}")

        company_profile_json = json.dumps(company_profile or {}, default=str)
        user_prompt = _USER_PROMPT.format(
            company_profile_json=company_profile_json,
            focused_chunk_text=context_text,
        )
        raw = _wa._call_llm(SYSTEM_PROMPT_BASE, user_prompt, llm_endpoint, max_tokens=_MAX_TOKENS)
        parsed = _wa._parse_json_response(raw)
        source_files = list({getattr(c, "file_name", "") for c in chunks})
        return {
            "extracted":    parsed,
            "gaps":         list(_wa._data_room_gaps),
            "source_files": source_files,
        }

    def _retrieve(self, company_name: str, spark) -> list:
        """Run all revenue-domain retrieval queries."""
        chunks: list = []

        # 1. Financial statements — P&L revenue/gross-profit rows
        chunks += semantic_search_with_fallback(
            company_name=company_name, spark=spark,
            query=(
                "annual revenue gross profit income statement financial results reported net revenue "
                "pro forma adjusted revenue P&L summary historical financials cost of revenue "
                "gross margin management accounts"
            ),
            workstream_filter=["FINANCIAL", "BUSINESS_MODEL"],
            top_k=10,
            file_name_filter=[
                "P&L", "Profit", "Loss", "Income", "Financial", "Accounts",
                "Financials", "Audited", "Management", "CIM", "Model", "Summary",
            ],
            min_chunk_length=150, min_results=3,
        )

        # 2. Revenue by segment / product line / service line
        chunks += semantic_search_with_fallback(
            company_name=company_name, spark=spark,
            query=(
                "revenue by segment product line geography service line revenue split breakdown "
                "revenue by location revenue by office revenue by division revenue by customer type"
            ),
            workstream_filter=["FINANCIAL", "BUSINESS_MODEL"],
            top_k=5,
            file_name_filter=["P&L", "Financial", "Revenue", "Segment", "CIM"],
            min_chunk_length=150, min_results=3,
        )

        # 3. Revenue by geography / location (explicit geographic terms for Excel models
        #    whose rows are labelled 'Revenue - New York', 'Revenue - Westchester', etc.)
        chunks += semantic_search_with_fallback(
            company_name=company_name, spark=spark,
            query=(
                "revenue by location geography region state city office clinic "
                "Revenue New York Westchester Long Island Connecticut Massachusetts "
                "New Jersey revenue breakdown by office location segment "
                "revenue by geography per location revenue by clinic by state "
                "regional revenue split location P&L"
            ),
            workstream_filter=["FINANCIAL", "BUSINESS_MODEL"],
            top_k=6,
            file_name_filter=["P&L", "Financial", "Revenue", "Segment", "CIM", "Model", "Projection"],
            min_chunk_length=100, min_results=3,
            source_type_priority=True,
        )

        # 4. Customer concentration — 2-pass: CIM first, broader fallback
        cust = semantic_search_with_fallback(
            company_name=company_name, spark=spark,
            query=(
                "customer concentration top customers revenue by customer largest customers "
                "customer mix payor mix client revenue key customers top 10 customers "
                "customer revenue breakdown revenue by payor revenue by client"
            ),
            workstream_filter=["BUSINESS_MODEL", "FINANCIAL", "CUSTOMER_QUALITY"],
            top_k=6,
            file_name_filter=["CIM"],
            min_chunk_length=80, min_results=2,
            source_type_priority=True,
        )
        if len(cust) < 2:
            cust = semantic_search_with_fallback(
                company_name=company_name, spark=spark,
                query=(
                    "top customers revenue by customer customer concentration sales by customer "
                    "client revenue largest customers QuickBooks customer summary "
                    "revenue concentration payor concentration revenue by client top 10 customers"
                ),
                workstream_filter=["FINANCIAL", "BUSINESS_MODEL", "CUSTOMER_QUALITY"],
                top_k=6,
                file_name_filter=["Customer", "QuickBooks", "QBO", "Sales", "Concentration", "Client", "Payor", "Revenue"],
                min_chunk_length=80, min_results=2,
                source_type_priority=True,
            )
        cust = [c for c in cust if not any(kw in (getattr(c, "file_name", "") or "").lower() for kw in _BANK_STMT_KEYWORDS)]
        chunks += cust

        # 5. QuickBooks P&L exports and individual year workbooks
        chunks += semantic_search_with_fallback(
            company_name=company_name, spark=spark,
            query=(
                "total income total revenue net revenue gross revenue QuickBooks P&L "
                "annual income statement 2020 2021 2022 2023 revenue expenses "
                "total sales income from operations total operating revenue"
            ),
            workstream_filter=["FINANCIAL", "BUSINESS_MODEL"],
            top_k=8,
            file_name_filter=[
                "QuickBooks", "QBO", "2020", "2021", "2022", "2023", "2024",
                "P&L", "Income", "Profit", "Annual", "Financial",
            ],
            min_chunk_length=100, min_results=3,
            source_type_priority=True,
        )

        return chunks

    @staticmethod
    def _make_base():
        from agents.shared.agent_base import WorkstreamAgent
        wa = WorkstreamAgent.__new__(WorkstreamAgent)
        WorkstreamAgent.__init__(wa)
        return wa
