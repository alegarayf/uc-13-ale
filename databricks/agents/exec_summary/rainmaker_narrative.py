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
import re
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


_KEY_PARTNER_CAP = 6

# Partner/platform relationships are a thesis input for a services, software or
# channel-driven business; for a provider of care they are not the story, and
# naming a "vendor partner" alongside a hospital or caregiver business reads as
# noise. Gate on the overlay the profiler already assigned rather than on
# anything company-specific — a new healthcare-adjacent overlay name is covered
# without a code change.
_HEALTHCARE_OVERLAY_RE = re.compile(r"health|care|hospital|medical|clinic|patient", re.IGNORECASE)


def _is_healthcare_overlay(bundle: dict[str, Any]) -> bool:
    return bool(_HEALTHCARE_OVERLAY_RE.search(str((bundle.get("meta") or {}).get("vertical_overlay") or "")))


def _key_partners(bundle: dict[str, Any]) -> list[dict[str, str]]:
    """``company_framing.key_partners``, empty for healthcare-overlay
    companies (see :data:`_HEALTHCARE_OVERLAY_RE`). Withholding the field is
    what keeps the prompt rule simple: "name them if you were given any"."""
    if _is_healthcare_overlay(bundle):
        return []
    partners: list[dict[str, str]] = []
    for row in (bundle.get("company_framing") or {}).get("key_partners") or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        partners.append(
            {
                "name": name,
                "relationship_type": str(row.get("relationship_type") or "").strip(),
                "description": str(row.get("description") or "").strip(),
            }
        )
        if len(partners) >= _KEY_PARTNER_CAP:
            break
    return partners


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


def _base_digest(
    bundle: dict[str, Any], financial_table: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Compact, whitelisted JSON core shared by every downstream digest
    (narrative and MPS — docs/plans/mps_score/mps_score_1st_draft.md §7.3).
    Reads ONLY the whitelisted bundle paths below; never spreads/copies the
    bundle wholesale, so it is structurally incapable of leaking
    chunks/embeddings/reasoning_trace/raw citation objects even if a caller
    passes a contaminated bundle. Callers may extend the returned dict with
    additional whitelisted fields, but must not weaken this guarantee by
    reading from the bundle any other way."""
    meta = bundle.get("meta") or {}
    executive = bundle.get("executive") or {}
    company_framing = bundle.get("company_framing") or {}
    revenue_quality = bundle.get("revenue_quality") or {}
    revenue_model = company_framing.get("revenue_model") or {}

    return {
        "vertical_overlay": str(meta.get("vertical_overlay") or ""),
        "in_one_line": str(executive.get("in_one_line") or ""),
        "business_description": str(company_framing.get("business_description") or ""),
        "sale_process": str(company_framing.get("sale_process") or ""),
        "key_partners": _key_partners(bundle),
        "thesis_bullets": _string_list(executive.get("thesis_bullets")),
        "overview_bullets": _string_list(company_framing.get("overview_bullets")),
        "key_watchouts": _string_list(executive.get("key_watchouts")),
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


def _build_narrative_digest(
    bundle: dict[str, Any], financial_table: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Compact, whitelisted JSON input shared by both narrative LLM calls."""
    return _base_digest(bundle, financial_table)


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
    "source attribution is handled separately by the render layer.\n\n"
    "One field value may start with the literal tag '[DATA ROOM MATERIAL NOT YET "
    "EXTRACTED]' — this means an automated check found matching material in the data "
    "room for that topic, but it was not captured by the extraction that produced "
    "this digest. Do NOT quote or repeat that bracketed tag verbatim. Instead, phrase "
    "the point as: this appears to be covered in the data room but has not yet been "
    "extracted into this analysis, so it should be pulled out and reviewed in the "
    "next pass. Do not treat this differently from a normal missing value in every "
    "other respect (still do not invent a figure) — the only difference is this "
    "specific phrasing, which is more accurate than claiming the data room says "
    "nothing on the topic."
)

_SYSTEM_PROMPT_FRAMING = f"""You are drafting the "Company & Investment Framing" section of a private-equity \
first-pass opportunity summary (the Rainmaker format). Your audience is an investment team deciding whether \
this deal is worth pursuing further. This summary must stay SHORT and GENERAL — the full operational detail \
belongs in the underlying workstream reports, not here.

{_NON_FABRICATION_RULE}

LENGTH DISCIPLINE (strict, do not exceed — every section on this page must fit on ONE physical page, so brevity \
here is not optional):
- "core_business": EXACTLY 3 lines, in this order and no other — (1) WHAT the business does: the product or \
  service it sells and who buys it; (2) HOW it does it: the delivery or operating mechanism it runs on \
  (locations, platform, workforce, channel, partner network — whichever is this business's own mechanism); \
  (3) ONE high-impact KPI from the input, stated with its figure and what it measures — pick the single \
  number that best conveys scale or performance, not a repeat of a figure used in line 1 or 2. Ground lines \
  1-2 in the input's "business_description" when it is present. This is the reader's first paragraph: it must \
  read as three plain statements of fact, never as a pitch, a caveat or a restatement of the recommendation.
- "company_overview": EXACTLY 4 bullets, HIGH-LEVEL only — what the company does, its market/footprint, its \
  scale and growth in aggregate terms. Do NOT include granular operational detail such as specific hourly \
  rates, per-location billed hours/week, individual location-by-location pricing, or other line-item \
  operating metrics — those are workstream-report detail, not first-pass framing. Generalize: e.g. write \
  "operates across N markets with private-pay pricing" rather than listing each market's rate card.
- "business_model": EXACTLY 4 bullets, covering — in this order — (1) where the revenue comes from (the \
  revenue model itself), (2) one notable change or signal in gross margin, or the single most relevant KPI \
  tied to the revenue model, (3) the reported EBITDA figure and its behavior/trend (not a full addback \
  bridge — that belongs in Revenue Quality, not here), (4) one additional customer/growth/retention signal \
  already present in the input (e.g. customer count, tenure/stickiness, segment mix) — pick whichever real \
  figure is most decision-relevant, never a restatement of bullets 1-3. Use bullets 1-3 as the model for how \
  terse every other bullet on this page should be — one clean fact per bullet, no stacked clauses.
- "investment_thesis.why_special": REQUIRED, exactly 1 sentence, the single most compelling reason this could \
  be special. "investment_thesis.value_drivers": EXACTLY 3 supporting bullets (why_special + these 3 bullets \
  is the full card — do not pad beyond that).
- "key_watchouts": the input's "key_watchouts" field already lists this business's key risks — your job here \
  is COMPACTION, not new analysis: rewrite it into EXACTLY 3 bullets, each ONE short sentence, preserving the \
  single most decision-relevant risk and its most important figure from the original bullet. Do not add a \
  risk that isn't already in the input, and do not drop the concrete figure to save space — cut connective \
  narration instead (e.g. "X is elevated at Y%, driven by Z" → "X is elevated at Y% in Z"). If the input has \
  fewer than 3 watchouts, return that many — never pad with a generic or duplicate point.
- Every line in "core_business" and every bullet in "company_overview", "business_model", \
  "investment_thesis.value_drivers", "investment_thesis.why_special", and "key_watchouts" must be ONE short \
  sentence, maximum 140 characters — \
  as terse as the "business_model" bullets above. Lead with the specific figure or fact; drop qualifying \
  clauses, hedges, and restatements. If you cannot fit the point in 140 characters, cut detail rather than \
  run past the limit.

TWO CONDITIONAL FACTS the investment team always asks about. Each belongs INSIDE the 4 "company_overview" \
bullets — never as a fifth bullet, and never anywhere else on the page:
- "sale_process": when this field is non-empty, ONE "company_overview" bullet must state how the business is \
  being brought to market and by whom, naming the bank, advisor or broker exactly as the field names it. Never \
  infer, complete or correct a firm name that is not in the field. When the field is empty, say nothing about \
  the process at all — an unbanked deal is not a fact you may assert from silence.
- "key_partners": when this list is non-empty, ONE "company_overview" bullet must name the most important of \
  these partner, platform or channel relationships (2-3 names, the ones the input describes as most central). \
  Never invent a partner, and never name one that is not in the list. When the list is empty or absent, omit \
  the topic entirely.
When both fields are populated, they take two of the four bullets: drop the two least decision-relevant of the \
bullets you would otherwise have written. "company_overview" is EXACTLY 4 bullets either way.

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
  "core_business": ["<what the business does and for whom>", "<how it delivers/operates>", "<one high-impact KPI with its figure>"],
  "company_overview": ["<bullet>", "<bullet>", "<bullet>", "<bullet>"],
  "business_model": ["<revenue source bullet>", "<gross margin/KPI signal bullet>", "<reported EBITDA status bullet>", "<additional customer/growth signal bullet>"],
  "investment_thesis": {{"value_drivers": ["<bullet>", "<bullet>", "<bullet>"], "why_special": "<1 sentence connecting the drivers>"}},
  "key_watchouts": ["<compacted watchout bullet>", "<compacted watchout bullet>", "<compacted watchout bullet>"],
  "recommendation": "<the recommendation sentence, exact structure above>"
}}"""

_SYSTEM_PROMPT_REVQUAL_DILIGENCE = f"""You are drafting the "Revenue Quality & Customer Base" and "Priority \
Diligence Questions" sections of a private-equity first-pass opportunity summary (the Rainmaker format). Keep \
both sections tight — this is a first-pass screen, not the full workstream report.

{_NON_FABRICATION_RULE}

LENGTH DISCIPLINE (strict, do not exceed):
- "commercial_revenue_quality": at most 5 bullets — the most decision-relevant revenue-quality/customer-base \
  signals only.
- "diligence_priorities": EXACTLY 6 questions, one for each of these six THESIS-TESTING archetypes, in this \
  order. Each is a question about whether the business's OWN operating reality supports its OWN thesis — never \
  a request for a document, schedule, or data room material. If the thesis-test genuinely cannot be answered \
  without a specific missing document, still ask the operating question and add the missing document as a \
  short trailing clause (e.g. "...; the data room does not yet include X to confirm this") rather than making \
  the document itself the question. \
  (1) growth-engine conversion — does the input this business invests in to grow (e.g. hiring, marketing \
  spend, unit/location build-out — whatever this business's own growth engine is) actually convert into the \
  revenue-bearing output (utilization, staffed capacity, activated accounts)? \
  (2) demand durability — is this business's demand channel (referrals, renewals, a sales channel, key \
  accounts — whatever applies here) institutional and diversified, or dependent on a handful of individuals \
  or relationships that could walk? \
  (3) unit economics vs. cost inflation — can this business's pricing keep outrunning its own dominant \
  cost driver (labor, materials, cloud/compute, etc. — whatever applies here) going forward? \
  (4) quality/consistency at scale — does the quality or consistency of what this business delivers hold up \
  as volume or locations/markets grow? \
  (5) replicability — do this business's newer or acquired units reach the unit economics of its mature \
  units, and on what timeline? \
  (6) earnings quality — how much of this business's reported earnings power is durable and recurring versus \
  dependent on adjustments, pro forma addbacks, or one-time synergies? \
  Instantiate each archetype using THIS business's own mechanism, terms, and nouns from the input — never a \
  generic or another company's version of the question, and never invent a mechanism the input doesn't support.
- Every "commercial_revenue_quality[].detail" and every "diligence_priorities[]" question must be ONE sentence, \
  maximum ~180 characters. Prefer the specific figure over the qualifying clause; drop hedges and restatements.

CRITICAL — diligence question relevance: the input includes "revenue_model" (how this specific business earns \
revenue). Every diligence question you generate MUST be relevant to that revenue model. Do NOT ask questions \
that only make sense for a different revenue model than the one described (e.g. do not ask about payor mix or \
insurance claims for a business explicitly described as private-pay-only; do not ask about seat-based pricing \
for a usage-based business). Prioritize the questions an investor would actually ask given THIS business's \
revenue_model and revenue_quality signals.

Respond with ONLY a JSON object, no markdown fences, with these exact keys:
{{
  "commercial_revenue_quality": [{{"topic": "<short topic>", "detail": "<1 sentence>"}}, "..."],
  "diligence_priorities": ["<growth-engine conversion question>", "<demand durability question>", "<unit economics vs. cost inflation question>", "<quality/consistency at scale question>", "<replicability question>", "<earnings quality question>"]
}}"""

_FRAMING_RESULT_KEYS = (
    "one_liner",
    "core_business",
    "company_overview",
    "business_model",
    "investment_thesis",
    "key_watchouts",
    "recommendation",
)
_REVQUAL_RESULT_KEYS = ("commercial_revenue_quality", "diligence_priorities")

_DEGRADED_FRAMING_FIELDS: dict[str, Any] = {key: None for key in _FRAMING_RESULT_KEYS}
_DEGRADED_REVQUAL_FIELDS: dict[str, Any] = {key: None for key in _REVQUAL_RESULT_KEYS}


def _framing_user_payload(digest: dict[str, Any]) -> dict[str, Any]:
    return {
        "vertical_overlay": digest["vertical_overlay"],
        "in_one_line": digest["in_one_line"],
        "business_description": digest["business_description"],
        "sale_process": digest["sale_process"],
        "key_partners": digest["key_partners"],
        "thesis_bullets": digest["thesis_bullets"],
        "overview_bullets": digest["overview_bullets"],
        "revenue_model": digest["revenue_model"],
        "kpi_highlights": digest["kpi_highlights"],
        "financials_summary": digest["financials_summary"],
        "key_watchouts": digest["key_watchouts"],
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
