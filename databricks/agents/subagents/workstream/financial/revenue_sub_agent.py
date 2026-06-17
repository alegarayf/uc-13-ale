"""Revenue & Margins sub-agent for the Financial Trends workstream.

Responsibility: extract revenue_trend, gross_margin, revenue_by_segment,
revenue_by_customer from the combined chunk context.

max_tokens = 6,000 — enough for ~10 periods × 4 arrays without crowding
out other fields.
"""

from .shared_prompts import SYSTEM_PROMPT_BASE

_USER_PROMPT = """\
COMPANY PROFILE (metadata only — do NOT extract financial figures from this block):
{company_profile_json}

RETRIEVED FINANCIAL DOCUMENT CONTEXT (extract ALL financial figures from here only):
{combined_chunk_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXTRACTION TASK — REVENUE & MARGINS
Extract ONLY the four fields below. Return ONLY the JSON object — no preamble.

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

_MAX_TOKENS = 6_000


class RevenueSubAgent:
    """Extracts revenue_trend, gross_margin, revenue_by_segment, revenue_by_customer.

    Designed to run in parallel with EbitdaSubAgent and OpexSubAgent via
    ThreadPoolExecutor. Each instance is independent with its own LLM client
    and gap-tracking state.
    """

    def run(
        self,
        combined_chunk_text: str,
        company_profile_json: str,
        llm_endpoint: str,
    ) -> dict:
        """Run extraction. Returns {"extracted": dict, "gaps": list[str]}."""
        _wa = self._make_base()
        user_prompt = _USER_PROMPT.format(
            company_profile_json=company_profile_json,
            combined_chunk_text=combined_chunk_text,
        )
        raw = _wa._call_llm(SYSTEM_PROMPT_BASE, user_prompt, llm_endpoint, max_tokens=_MAX_TOKENS)
        parsed = _wa._parse_json_response(raw)
        return {"extracted": parsed, "gaps": list(_wa._data_room_gaps)}

    @staticmethod
    def _make_base():
        """Instantiate a WorkstreamAgent used as a utility (LLM client + JSON parser)."""
        from agents.shared.agent_base import WorkstreamAgent
        wa = WorkstreamAgent.__new__(WorkstreamAgent)
        WorkstreamAgent.__init__(wa)
        return wa
