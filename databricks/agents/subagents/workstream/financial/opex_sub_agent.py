"""OPEX & Cost Structure sub-agent for the Financial Trends workstream.

Responsibility: extract opex_breakdown, cost_structure, executive_summary,
extraction_notes.

max_tokens = 3,000 — OPEX has at most ~10 category records; light schema.
"""

from .shared_prompts import SYSTEM_PROMPT_BASE

_USER_PROMPT = """\
COMPANY PROFILE (metadata only — do NOT extract financial figures from this block):
{company_profile_json}

RETRIEVED FINANCIAL DOCUMENT CONTEXT (extract ALL financial figures from here only):
{combined_chunk_text}

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

_MAX_TOKENS = 3_000


class OpexSubAgent:
    """Extracts opex_breakdown, cost_structure, executive_summary, extraction_notes.

    Light schema — OPEX categories are bounded in number. Designed to run in
    parallel with RevenueSubAgent and EbitdaSubAgent.
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
