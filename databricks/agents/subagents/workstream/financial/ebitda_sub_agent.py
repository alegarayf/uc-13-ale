"""EBITDA & Addbacks sub-agent for the Financial Trends workstream.

Responsibility: extract ebitda (≤3 version types), addback_schedule,
working_capital, budget_vs_actual, discrepancies_found.

max_tokens = 8,000 — EBITDA records are the most token-intensive field
(up to 30 records × ~300 chars each). Isolating EBITDA into its own call
prevents it from crowding out revenue and OPEX.
"""

from .shared_prompts import SYSTEM_PROMPT_EBITDA

_USER_PROMPT = """\
COMPANY PROFILE (metadata only — do NOT extract financial figures from this block):
{company_profile_json}

RETRIEVED FINANCIAL DOCUMENT CONTEXT (extract ALL financial figures from here only):
{combined_chunk_text}

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

_MAX_TOKENS = 8_000


class EbitdaSubAgent:
    """Extracts ebitda, addback_schedule, working_capital, budget_vs_actual, discrepancies.

    Uses SYSTEM_PROMPT_EBITDA (rules 1-13) which includes the EBITDA version limit
    (Rule 13) and addback extraction rules (Rule 12). Designed to run in parallel
    with RevenueSubAgent and OpexSubAgent.
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
        raw = _wa._call_llm(SYSTEM_PROMPT_EBITDA, user_prompt, llm_endpoint, max_tokens=_MAX_TOKENS)
        parsed = _wa._parse_json_response(raw)
        return {"extracted": parsed, "gaps": list(_wa._data_room_gaps)}

    @staticmethod
    def _make_base():
        """Instantiate a WorkstreamAgent used as a utility (LLM client + JSON parser)."""
        from agents.shared.agent_base import WorkstreamAgent
        wa = WorkstreamAgent.__new__(WorkstreamAgent)
        WorkstreamAgent.__init__(wa)
        return wa
