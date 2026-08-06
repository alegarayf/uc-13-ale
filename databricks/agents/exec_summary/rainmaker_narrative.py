"""Capa B — LLM-bounded narrative synthesis for the Rainmaker template.

Iteración 2 (docs/plans/plan_raimaker_format.md §3.2-3.3). Runs strictly
downstream of a validated bundle and Capa A's deterministic financial
projection (``rainmaker_view.py``) — never touches chunks/embeddings/
reasoning_trace, never mutates the bundle, and never raises: any failure
(timeout, invalid JSON, missing endpoint) degrades to
``synthesis_status="degraded"`` with narrative fields set to ``None``,
letting the template fall back to bundle bullets / "Not yet assessed in
this preview." (the existing fallback pattern already used by the legacy
4-page template).

Company-agnostic by construction (plan §Principios rectores, P2): the
system prompts below are fixed strings describing *how* to synthesize —
they never reference a company, vertical, or period literal. All
company-specific content flows through ``_build_narrative_digest`` at
call time.
"""

from __future__ import annotations

import json
from typing import Any

from agents.exec_summary.rainmaker_view import _financial_table
from agents.shared.agent_base import WorkstreamAgent

_KPI_HIGHLIGHT_CAP = 8
_RISK_CAP = 8
_GAP_CAP = 6

_FRAMING_MAX_TOKENS = 4_000
_REVQUAL_DILIGENCE_MAX_TOKENS = 4_000


class _RainmakerNarrativeLlm(WorkstreamAgent):
    """Minimal shim to reuse WorkstreamAgent._call_llm/_parse_json_response —
    same pattern as bundle_builder.py's ``_OrchestratorLlm``."""

    agent_name = "rainmaker_narrative"


# ---------------------------------------------------------------------------
# Paso 3 — pure digest builder (no LLM call). Reads ONLY the whitelisted
# bundle paths below; never spreads/copies the bundle wholesale, so it is
# structurally incapable of leaking chunks/embeddings/reasoning_trace/raw
# citation objects even if a caller passes a contaminated bundle.
# ---------------------------------------------------------------------------


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if isinstance(v, str) and str(v).strip()]


def _kpi_highlights(bundle: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for row in bundle.get("kpi_dashboard") or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("display_name") or "").strip()
        value = str(row.get("stated_value") or "").strip()
        if not name or not value:
            continue
        out.append({"display_name": name, "stated_value": value})
        if len(out) >= _KPI_HIGHLIGHT_CAP:
            break
    return out


def _risk_summaries(bundle: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for row in bundle.get("risks") or []:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "risk": str(row.get("risk") or ""),
                "severity": str(row.get("severity") or ""),
                "evidence": str(row.get("evidence") or ""),
                "mitigant_or_question": str(row.get("mitigant_or_question") or ""),
            }
        )
        if len(out) >= _RISK_CAP:
            break
    return out


def _gap_summaries(bundle: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for gap in bundle.get("data_room_gaps") or []:
        item = str((gap.get("item") if isinstance(gap, dict) else gap) or "").strip()
        if item:
            out.append(item)
        if len(out) >= _GAP_CAP:
            break
    return out


def _financials_summary(financial_table: dict[str, Any] | None) -> dict[str, Any]:
    """Compact numeric summary derived from Capa A's already-deterministic
    table — never the raw ``table_rows`` list — so the narrative prompt can
    cite real figures without a large/duplicated payload."""
    table = financial_table or {}
    periods = table.get("periods") or []
    rows_by_metric = {r.get("metric_name"): r.get("cells") for r in table.get("rows") or []}

    def _latest(metric: str) -> str | None:
        for value in reversed(rows_by_metric.get(metric) or []):
            if value:
                return value
        return None

    return {
        "periods": periods,
        "latest_revenue": _latest("Total Revenue"),
        "latest_ebitda": _latest("EBITDA"),
        "latest_gross_margin_pct": _latest("% Gross Margin"),
        "latest_ebitda_margin_pct": _latest("% EBITDA Margin"),
    }


def _build_narrative_digest(
    bundle: dict[str, Any], financial_table: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Compact, whitelisted JSON input shared by both narrative LLM calls."""
    meta = bundle.get("meta") or {}
    executive = bundle.get("executive") or {}
    company_framing = bundle.get("company_framing") or {}
    revenue_quality = bundle.get("revenue_quality") or {}
    revenue_model = company_framing.get("revenue_model") or {}

    return {
        "vertical_overlay": str(meta.get("vertical_overlay") or ""),
        "in_one_line": str(executive.get("in_one_line") or ""),
        "thesis_bullets": _string_list(executive.get("thesis_bullets")),
        "overview_bullets": _string_list(company_framing.get("overview_bullets")),
        "revenue_model": {
            "tag": str(revenue_model.get("tag") or ""),
            "quality_flag": str(revenue_model.get("quality_flag") or ""),
            "note": str(revenue_model.get("note") or ""),
        },
        "revenue_quality": {
            "scale_narrative": str(revenue_quality.get("scale_narrative") or ""),
            "concentration": str(revenue_quality.get("concentration") or ""),
            "end_market_mix": str(revenue_quality.get("end_market_mix") or ""),
            "retention_notes": str(revenue_quality.get("retention_notes") or ""),
        },
        "kpi_highlights": _kpi_highlights(bundle),
        "risks": _risk_summaries(bundle),
        "data_room_gaps": _gap_summaries(bundle),
        "financials_summary": _financials_summary(financial_table),
    }


# ---------------------------------------------------------------------------
# Paso 4 — bounded LLM synthesis (2 calls, max_tokens=4000 each — plan §3.2,
# CLAUDE.md ~120s serving timeout). Prompts are fixed, company-agnostic
# templates (P2): they describe HOW to synthesize, never WHAT company.
# ---------------------------------------------------------------------------

_NON_FABRICATION_RULE = (
    "Use ONLY the facts, figures and names present in the input JSON. If information "
    "for a section is missing, say so explicitly (e.g. 'Not yet assessed in this "
    "preview') — never invent figures, names, dates or facts that are not in the "
    "input. You do not have access to the original source documents, only this "
    "already-extracted digest. Never embed bracketed source citations or file/page "
    "references (e.g. '(file.pdf p.12)') inside your prose — write plain sentences; "
    "source attribution is handled separately by the render layer."
)

_SYSTEM_PROMPT_FRAMING = f"""You are drafting the "Company & Investment Framing" section of a private-equity \
first-pass opportunity summary (the Rainmaker format). Your audience is an investment team deciding whether \
this deal is worth pursuing further.

{_NON_FABRICATION_RULE}

Write a BALANCED AND AFFIRMATIVE investment thesis: connect the attractive elements present in the input \
(e.g. growth, margins, recurring-revenue signals, operational strengths) into ONE coherent reason the business \
could be special — do not just list caveats or lead with exceptions. Maintain tone continuity with any \
thesis_bullets/in_one_line already present in the input.

End with a single "recommendation" sentence in this exact structure: "This appears worthy of additional \
pursuit because of <A>, <B> and <C>, subject primarily to proving <X>, <Y> and <Z>." Do not narrow the \
recommendation to a single financial metric — ground it in the thesis as a whole.

Respond with ONLY a JSON object, no markdown fences, with these exact keys:
{{
  "one_liner": "<1 sentence — what the business is and why it could be interesting>",
  "company_overview": ["<bullet>", "..."],
  "business_model": ["<bullet>", "..."],
  "investment_thesis": {{"value_drivers": ["<bullet>", "..."], "why_special": "<1-2 sentences connecting the drivers>"}},
  "recommendation": "<the recommendation sentence, exact structure above>"
}}"""

_SYSTEM_PROMPT_REVQUAL_DILIGENCE = f"""You are drafting the "Revenue Quality & Customer Base" and "Priority \
Diligence Questions" sections of a private-equity first-pass opportunity summary (the Rainmaker format).

{_NON_FABRICATION_RULE}

CRITICAL — diligence question relevance: the input includes "revenue_model" (how this specific business earns \
revenue). Every diligence question you generate MUST be relevant to that revenue model. Do NOT ask questions \
that only make sense for a different revenue model than the one described (e.g. do not ask about payor mix or \
insurance claims for a business explicitly described as private-pay-only; do not ask about seat-based pricing \
for a usage-based business). Prioritize the questions an investor would actually ask given THIS business's \
revenue_model and revenue_quality signals.

Respond with ONLY a JSON object, no markdown fences, with these exact keys:
{{
  "commercial_revenue_quality": [{{"topic": "<short topic>", "detail": "<1 sentence>"}}, "..."],
  "diligence_priorities": ["<question>", "..."]
}}"""

_FRAMING_RESULT_KEYS = ("one_liner", "company_overview", "business_model", "investment_thesis", "recommendation")
_REVQUAL_RESULT_KEYS = ("commercial_revenue_quality", "diligence_priorities")

_DEGRADED_FRAMING_FIELDS: dict[str, Any] = {key: None for key in _FRAMING_RESULT_KEYS}
_DEGRADED_REVQUAL_FIELDS: dict[str, Any] = {key: None for key in _REVQUAL_RESULT_KEYS}


def _framing_user_payload(digest: dict[str, Any]) -> dict[str, Any]:
    return {
        "vertical_overlay": digest["vertical_overlay"],
        "in_one_line": digest["in_one_line"],
        "thesis_bullets": digest["thesis_bullets"],
        "overview_bullets": digest["overview_bullets"],
        "revenue_model": digest["revenue_model"],
        "kpi_highlights": digest["kpi_highlights"],
        "financials_summary": digest["financials_summary"],
    }


def _revqual_diligence_user_payload(digest: dict[str, Any]) -> dict[str, Any]:
    return {
        "revenue_model": digest["revenue_model"],
        "revenue_quality": digest["revenue_quality"],
        "risks": digest["risks"],
        "data_room_gaps": digest["data_room_gaps"],
    }


def _call_bounded(
    llm: Any,
    system_prompt: str,
    user_payload: dict[str, Any],
    endpoint: str,
    max_tokens: int,
    degraded_fields: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Runs one bounded LLM call; NEVER raises — any failure (timeout,
    malformed/non-dict JSON, missing endpoint) returns the degraded shape."""
    try:
        raw = llm._call_llm(system_prompt, json.dumps(user_payload), endpoint, max_tokens=max_tokens)
        parsed = llm._parse_json_response(raw)
        if not isinstance(parsed, dict):
            raise ValueError("LLM response was not a JSON object")
        return parsed, True
    except Exception as exc:  # noqa: BLE001 - narrative synthesis must never propagate (plan §3.2/R3)
        print(f"[rainmaker_narrative] bounded call failed, degrading: {exc!r}")
        return dict(degraded_fields), False


def synthesize_rainmaker_narrative(
    bundle: dict[str, Any],
    llm_endpoint: str,
    spark: Any = None,
) -> dict[str, Any]:
    """Two bounded LLM calls producing the Rainmaker template's prose
    sections. Never raises — any failure degrades gracefully so the render
    layer can fall back to the bundle's deterministic bullets.

    ``synthesis_status``: ``"success"`` (both calls ok), ``"partial"`` (one
    ok), or ``"degraded"`` (neither ok / LLM client unavailable).
    """
    del spark  # reserved for future retrieval-backed grounding; unused today

    try:
        llm = _RainmakerNarrativeLlm()
    except Exception as exc:  # noqa: BLE001 - must never raise (plan §3.2/R3)
        print(f"[rainmaker_narrative] LLM client unavailable, degrading: {exc!r}")
        return {
            **_DEGRADED_FRAMING_FIELDS,
            **_DEGRADED_REVQUAL_FIELDS,
            "synthesis_status": "degraded",
        }

    digest = _build_narrative_digest(bundle, _financial_table(bundle))

    framing_result, framing_ok = _call_bounded(
        llm,
        _SYSTEM_PROMPT_FRAMING,
        _framing_user_payload(digest),
        llm_endpoint,
        _FRAMING_MAX_TOKENS,
        _DEGRADED_FRAMING_FIELDS,
    )
    revqual_result, revqual_ok = _call_bounded(
        llm,
        _SYSTEM_PROMPT_REVQUAL_DILIGENCE,
        _revqual_diligence_user_payload(digest),
        llm_endpoint,
        _REVQUAL_DILIGENCE_MAX_TOKENS,
        _DEGRADED_REVQUAL_FIELDS,
    )

    if framing_ok and revqual_ok:
        status = "success"
    elif framing_ok or revqual_ok:
        status = "partial"
    else:
        status = "degraded"

    result: dict[str, Any] = {key: framing_result.get(key) for key in _FRAMING_RESULT_KEYS}
    result.update({key: revqual_result.get(key) for key in _REVQUAL_RESULT_KEYS})
    result["synthesis_status"] = status
    return result
