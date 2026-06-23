"""EBITDA & Addbacks sub-agent for the Financial Trends workstream.

Responsibility:
  Retrieval  — financial_statements (EBITDA rows), ebitda_and_margins,
               working_capital, addback_schedule  (4 focused queries)
  Extraction — ebitda (≤3 versions), addback_schedule, working_capital,
               budget_vs_actual, discrepancies_found

Each instance is autonomous: it runs its own semantic_search calls, builds its
own focused context (~22K chars), and performs a single LLM extraction call.
Designed to run in parallel with RevenueSubAgent and OpexSubAgent.

max_tokens = 8,000 — EBITDA records are the most token-intensive field
(up to 30 records × ~300 chars each). Isolating EBITDA into its own call
prevents it from crowding out revenue and OPEX.
"""

import json
from .shared_prompts import SYSTEM_PROMPT_EBITDA
from .context_utils import build_focused_context, semantic_search_with_fallback

_MAX_CONTEXT_CHARS = 22_000
_MAX_TOKENS = 8_000

_USER_PROMPT = """\
COMPANY PROFILE (metadata only — do NOT extract financial figures from this block):
{company_profile_json}

RETRIEVED FINANCIAL DOCUMENT CONTEXT (extract ALL financial figures from here only):
{focused_chunk_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXTRACTION TASK — EBITDA & ADDBACKS
Extract ONLY the five fields below. Return ONLY the JSON object — no preamble.

EBITDA VERSION LIMIT (Rule 13): Extract at most 3 version types:
  "reported"              — raw, unadjusted EBITDA as filed.
  "pf_adjusted"           — highest pro forma / management case adjusted figure.
                            If multiple adjusted concepts exist, use the highest only.
  "clinic_level_adjusted" — unit/location EBITDA, only if explicitly presented.
Skip ALL other intermediate adjusted EBITDA concepts.

{{
  "ebitda": [
    {{
      "period": "<time period ONLY — NEVER a geography or entity name>",
      "label": "<FULL exact label — e.g. 'PF Adj. EBITDA' or 'Reported EBITDA'>",
      "version": "<'reported' | 'pf_adjusted' | 'clinic_level_adjusted' ONLY>",
      "ebitda_dollars": "<$ as stated — e.g. '(342)' for loss>",
      "ebitda_margin_pct": "<margin % for this EBITDA line: Margin row, inline column, or narrative. Null if absent.>",
      "source_doc": "<exact filename — must NOT be 'COMPANY PROFILE'>",
      "source_location": "<page or section>"
    }}
  ],

  "addback_schedule": [
    {{
      "description": "<exact label — e.g. '[G] Run-rate executive compensation'>",
      "amount_stated": "<$ for most recent period>",
      "period": "<period this amount comes from>",
      "supporting_doc_referenced": "<cited support doc, or 'not referenced'>",
      "source_doc": "<exact filename>",
      "source_location": "<page or section>",
      "raw_text": "<≤30 word quote>"
    }}
  ],

  "working_capital": {{
    "dso_days": "<days as stated or null>",
    "dpo_days": "<days as stated or null>",
    "ar_aging_note": "<AR aging or cash collection note as stated, or null>",
    "source_doc": "<filename or null>"
  }},

  "budget_vs_actual": [
    {{
      "period": "<period>",
      "metric": "<Revenue | EBITDA>",
      "budget_stated": "<$ as stated>",
      "actual_stated": "<$ as stated>",
      "variance_note": "<variance description as stated>",
      "source_doc": "<filename>"
    }}
  ],

  "discrepancies_found": [
    {{
      "metric": "<metric name>",
      "conflicting_values": ["<doc A: $X>", "<doc B: $Y>"],
      "note": "<brief description>"
    }}
  ]
}}\
"""


class EbitdaSubAgent:
    """Extracts ebitda, addback_schedule, working_capital, budget_vs_actual, discrepancies.

    Autonomous: owns retrieval + context building + LLM extraction.
    Uses SYSTEM_PROMPT_EBITDA (rules 1-13) which includes the EBITDA version limit
    (Rule 13) and addback extraction rules (Rule 12).
    """

    def run(
        self,
        company_name: str,
        spark,
        llm_endpoint: str,
        company_profile: dict | None,
        retrieval_mode: str = "semantic",
    ) -> dict:
        """Run retrieval → context build → extraction.

        Returns {"extracted": dict, "gaps": list[str], "source_files": list[str]}.
        """
        _wa = self._make_base()

        chunks, gaps = self._retrieve(company_name, spark, retrieval_mode)
        context_text, stats = build_focused_context(chunks, max_chars=_MAX_CONTEXT_CHARS)
        print(f"  [EBITDA] {stats}")

        company_profile_json = json.dumps(company_profile or {}, default=str)
        user_prompt = _USER_PROMPT.format(
            company_profile_json=company_profile_json,
            focused_chunk_text=context_text,
        )
        raw = _wa._call_llm(SYSTEM_PROMPT_EBITDA, user_prompt, llm_endpoint, max_tokens=_MAX_TOKENS)
        parsed = _wa._parse_json_response(raw)
        source_files = list({getattr(c, "file_name", "") for c in chunks})
        return {
            "extracted":    parsed,
            "gaps":         list(_wa._data_room_gaps) + gaps,
            "source_files": source_files,
        }

    def _retrieve(self, company_name: str, spark, retrieval_mode: str = "semantic") -> tuple[list, list[str]]:
        """Run all EBITDA-domain retrieval queries.

        Returns (chunks, retrieval_gaps) where retrieval_gaps are gap strings
        detected during retrieval (e.g. empty addback results).
        """
        chunks: list = []
        retrieval_gaps: list[str] = []

        # 1. Financial statements — P&L EBITDA rows + margin rows
        chunks += semantic_search_with_fallback(
            company_name=company_name, spark=spark,
            query=(
                "EBITDA profit loss income statement operating income earnings before interest "
                "tax depreciation amortization reported EBITDA clinic level EBITDA pro forma "
                "adjusted EBITDA management accounts P&L summary historical financials "
                "diligence adjusted EBITDA summary P&L"
            ),
            workstream_filter=["FINANCIAL", "BUSINESS_MODEL"],
            top_k=10,
            file_name_filter=[
                "P&L", "Profit", "Loss", "Income", "Financial", "Accounts",
                "Financials", "Audited", "Management", "QofE", "Quality", "CIM",
                "Model", "Summary",
            ],
            min_chunk_length=150, min_results=3,
            retrieval_mode=retrieval_mode,
        ).chunks

        # 2. EBITDA and margins
        chunks += semantic_search_with_fallback(
            company_name=company_name, spark=spark,
            query=(
                "EBITDA margin gross margin adjusted EBITDA addback bridge earnings profitability "
                "clinic level EBITDA diligence adjusted pro forma margin operating income "
                "adjusted operating profit contribution margin historical P&L summary"
            ),
            workstream_filter=["FINANCIAL", "QUALITY_EARNINGS", "BUSINESS_MODEL"],
            top_k=8,
            file_name_filter=["EBITDA", "Margin", "Addback", "Bridge", "Adjusted", "QofE", "Quality", "P&L", "CIM", "Financial"],
            min_chunk_length=150, min_results=3,
            retrieval_mode=retrieval_mode,
        ).chunks

        # 3. Working capital
        chunks += semantic_search_with_fallback(
            company_name=company_name, spark=spark,
            query=(
                "DSO DPO days sales outstanding accounts receivable aging working capital "
                "cash collection cash conversion cycle AR balance sheet current assets"
            ),
            workstream_filter=["FINANCIAL"],
            top_k=4,
            file_name_filter=["Balance Sheet", "Financial", "Accounts", "AR", "Aging", "Working Capital", "CIM"],
            min_chunk_length=150, min_results=3,
            retrieval_mode=retrieval_mode,
        ).chunks

        # 4. Addback schedule
        addback_chunks = semantic_search_with_fallback(
            company_name=company_name, spark=spark,
            query=(
                "EBITDA adjustment detail addback schedule non-recurring one-time "
                "owner salary management fee adjustment reported adjusted EBITDA reconciliation "
                "pro forma adjustments normalization items addback bridge "
                "diligence adjustment normalized expense run-rate executive compensation "
                "credit card allocation non-operating transactions management addbacks "
                "seller adjustments earnings quality"
            ),
            workstream_filter=["FINANCIAL", "QUALITY_EARNINGS", "BUSINESS_MODEL"],
            top_k=10,
            file_name_filter=["Addback", "Bridge", "EBITDA", "QofE", "Quality", "Adjusted", "CIM", "Adjustment", "Financial", "P&L"],
            min_chunk_length=50,
            min_results=3,
            source_type_priority=True,
            retrieval_mode=retrieval_mode,
        ).chunks
        if not addback_chunks:
            retrieval_gaps.append(
                "addback_schedule retrieval returned 0 chunks. If an addback or EBITDA adjustment "
                "table exists in the data room (look for sections titled 'EBITDA Adjustment Detail', "
                "'Diligence Adjusted Income Statement', or 'Addback Schedule'), confirm those "
                "documents are tagged with the FINANCIAL or QUALITY_EARNINGS workstream and "
                "re-run the agent."
            )
        chunks += addback_chunks

        return chunks, retrieval_gaps

    @staticmethod
    def _make_base():
        from agents.shared.agent_base import WorkstreamAgent
        wa = WorkstreamAgent.__new__(WorkstreamAgent)
        WorkstreamAgent.__init__(wa)
        return wa
