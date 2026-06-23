"""OPEX & Cost Structure sub-agent for the Financial Trends workstream.

Responsibility:
  Retrieval  — financial_statements (opex rows), working_capital,
               projected_financials  (3 focused queries)
  Extraction — opex_breakdown, cost_structure, executive_summary, extraction_notes

Each instance is autonomous: it runs its own semantic_search calls, builds its
own focused context (~15K chars), and performs a single LLM extraction call.
Designed to run in parallel with RevenueSubAgent and EbitdaSubAgent.

max_tokens = 3,000 — OPEX has at most ~10 category records; light schema.
"""

import json
from .shared_prompts import SYSTEM_PROMPT_BASE
from .context_utils import build_focused_context, semantic_search_with_fallback

_MAX_CONTEXT_CHARS = 15_000
_MAX_TOKENS = 3_000

_USER_PROMPT = """\
COMPANY PROFILE (metadata only — do NOT extract financial figures from this block):
{company_profile_json}

RETRIEVED FINANCIAL DOCUMENT CONTEXT (extract ALL financial figures from here only):
{focused_chunk_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXTRACTION TASK — OPEX & COST STRUCTURE
Extract ONLY the four fields below. Return ONLY the JSON object — no preamble.

For opex_breakdown: extract the top 4 named cost categories by dollar amount
(e.g. 'Payroll Expenses', 'Benefits', 'Rent', 'G&A'). If more than 4 categories
exist, bucket the rest into a single "Other OPEX" record.

{{
  "opex_breakdown": [
    {{
      "category": "<cost category — e.g. 'Payroll Expenses (COGS)' or 'Clinic-Level Rent'>",
      "amount_stated": "<$ as stated>",
      "period": "<time period>",
      "pct_of_revenue": "<% of revenue as stated, or null>",
      "source_doc": "<exact filename>",
      "source_location": "<page or section>"
    }}
  ],

  "cost_structure": {{
    "headcount_pct_of_revenue": "<% as stated or null>",
    "fixed_vs_variable_note": "<fixed vs variable split as stated, or null>",
    "key_categories": ["<e.g. 'Payroll expenses'>"],
    "source_doc": "<filename or null>"
  }},

  "executive_summary": "<1–2 sentence factual summary: revenue scale if visible, reported vs adjusted EBITDA profile, and the single most notable financial risk. Write only what is stated. Do not render a verdict.>",

  "extraction_notes": "<Semicolon-separated list: fields null because absent; tables partially readable; multiple metric versions found; any layout anomalies.>"
}}\
"""


class OpexSubAgent:
    """Extracts opex_breakdown, cost_structure, executive_summary, extraction_notes.

    Autonomous: owns retrieval + context building + LLM extraction.
    Light schema — OPEX categories are bounded in number.
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
        print(f"  [Opex]    {stats}")

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
        """Run all OPEX-domain retrieval queries."""
        chunks: list = []

        # 1. Financial statements — P&L opex rows (salaries, G&A, overhead, etc.)
        chunks += semantic_search_with_fallback(
            company_name=company_name, spark=spark,
            query=(
                "operating expenses OPEX cost of revenue salaries compensation benefits "
                "payroll expenses rent overhead G&A selling expenses labor costs "
                "cost structure headcount expenses breakdown income statement"
            ),
            workstream_filter=["FINANCIAL", "BUSINESS_MODEL"],
            top_k=8,
            file_name_filter=[
                "P&L", "Profit", "Loss", "Income", "Financial", "Accounts",
                "Financials", "Audited", "Management", "CIM", "Model", "Summary",
            ],
            min_chunk_length=150, min_results=3,
        ).chunks

        # 2. Working capital — opex context (current liabilities, payables)
        chunks += semantic_search_with_fallback(
            company_name=company_name, spark=spark,
            query=(
                "accounts payable DPO days payable outstanding operating expenses "
                "working capital current liabilities cash flow from operations"
            ),
            workstream_filter=["FINANCIAL"],
            top_k=4,
            file_name_filter=["Balance Sheet", "Financial", "Accounts", "Working Capital", "CIM"],
            min_chunk_length=150, min_results=3,
        ).chunks

        # 3. Projected financials — forward OPEX / cost assumptions
        chunks += semantic_search_with_fallback(
            company_name=company_name, spark=spark,
            query=(
                "projected revenue forecast 2025 2026 2027 2028 2029 "
                "gross profit gross margin operating expenses OPEX salaries labor "
                "projected EBITDA summary P&L income statement forward projections "
                "revenue projection plan financial model projection assumptions "
                "cost of revenue compensation benefits G&A overhead"
            ),
            workstream_filter=["FINANCIAL", "BUSINESS_MODEL"],
            top_k=8,
            file_name_filter=["Model", "Projection", "Forecast", "Budget", "CIM", "Financial", "P&L"],
            min_chunk_length=100, min_results=3,
            source_type_priority=True,
        ).chunks

        return chunks

    @staticmethod
    def _make_base():
        from agents.shared.agent_base import WorkstreamAgent
        wa = WorkstreamAgent.__new__(WorkstreamAgent)
        WorkstreamAgent.__init__(wa)
        return wa
