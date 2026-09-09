"""The final report's section-level prose — the six "Analyst take" boxes plus
a structured recommendation (plan §3.5).

``rainmaker_narrative.py`` produces exactly the two keys the ER's own template
slots need (``business_model``/``key_watchouts``) and nothing the final
report's six section pages want. This module is additive and read-only with
respect to that file: it does not import its private helpers, so a future
edit to the ER's digest or prompt never silently changes this document's
prose. The two modules duplicate a small amount of digest plumbing on
purpose — the cheaper mistake, per the task that specified this module.

Same discipline as ``rainmaker_narrative.py``: pure digest builder (no LLM),
one bounded call through the gateway (``agents/shared/llm_client.py`` —
AD-001; nothing else may construct a deploy client), and a public function
that never raises. Any failure — the call, the JSON parse, a schema
mismatch — degrades to ``final_narrative_status="degraded"`` with every
prose field ``None``, so the template's ``{%- if report.X.take %}`` guards
simply omit the box.
"""

from __future__ import annotations

import json
import re
from typing import Any

from agents.exec_summary.final_report_view import _SCREENS, _pnl_table
from agents.shared import llm_client
from agents.shared.agent_base import accumulate_tokens

_MAX_TOKENS = 3_000

# --- Digest caps: the length budget of the call, not of the report -------
_CAP_STRING = 400
_CAP_LIST = 8
_CAP_PARTNERS = 6
_CAP_TOP_CUSTOMERS = 5
_CAP_ADDBACKS = 6
_CAP_ASSUMPTIONS = 5


def _trunc(value: Any, n: int = _CAP_STRING) -> str:
    text = str(value or "").strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _string_list(value: Any, cap: int = _CAP_LIST, item_cap: int = _CAP_STRING) -> list[str]:
    if not isinstance(value, list):
        return []
    out = [_trunc(v, item_cap) for v in value if isinstance(v, str) and str(v).strip()]
    return out[:cap]


# ---------------------------------------------------------------------------
# Digest builders — one per section, reading ONLY the bundle paths the
# matching take is supposed to comment on. Built from the bundle, never from
# ``final_report_view``'s output (that would be circular: the view takes
# ``narrative`` as an input).
# ---------------------------------------------------------------------------


def _business_digest(bundle: dict[str, Any]) -> dict[str, Any]:
    framing = bundle.get("company_framing") or {}
    revenue_quality = bundle.get("revenue_quality") or {}
    revenue_model = framing.get("revenue_model") or {}
    partners = []
    for row in (framing.get("key_partners") or [])[:_CAP_PARTNERS]:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if name:
            partners.append(name)
    return {
        "overview_bullets": _string_list(framing.get("overview_bullets")),
        "revenue_model": {
            "tag": str(revenue_model.get("tag") or ""),
            "quality_flag": str(revenue_model.get("quality_flag") or ""),
            "note": _trunc(revenue_model.get("note")),
        },
        "revenue_model_narrative": _trunc(revenue_quality.get("scale_narrative")),
        "business_description": _trunc(framing.get("business_description")),
        "sale_process": _trunc(framing.get("sale_process")),
        "key_partners": partners,
    }


def _financial_digest(bundle: dict[str, Any]) -> dict[str, Any]:
    table = _pnl_table(bundle)
    rows_by_label = {r.get("label"): r.get("cells") for r in table.get("rows") or []}

    def _latest(label: str) -> str | None:
        for value in reversed(rows_by_label.get(label) or []):
            if value:
                return value
        return None

    return {
        "periods": table.get("periods") or [],
        "latest_revenue": _latest("Revenue"),
        "latest_ebitda": _latest("EBITDA"),
        "latest_gross_margin_pct": _latest("Gross margin %"),
        "latest_ebitda_margin_pct": _latest("EBITDA margin %"),
        "observations": _string_list((bundle.get("financials") or {}).get("observations")),
    }


def _customer_digest(bundle: dict[str, Any]) -> dict[str, Any]:
    rq = bundle.get("revenue_quality") or {}
    conc = rq.get("concentration_summary") or {}
    ret = rq.get("retention") or {}
    top_customers = []
    for c in (rq.get("top_customers") or [])[:_CAP_TOP_CUSTOMERS]:
        if not isinstance(c, dict):
            continue
        top_customers.append(
            {"name": _trunc(c.get("customer_name"), 60), "share_pct": c.get("revenue_pct_yr1")}
        )
    return {
        "concentration_summary": {"top1_pct": conc.get("top1_pct"), "top5_pct": conc.get("top5_pct")},
        "retention": {"nrr_pct": ret.get("nrr_pct"), "grr_pct": ret.get("grr_pct")},
        "top_customers": top_customers,
        "concentration_note": _trunc(rq.get("concentration")),
        "retention_notes": _trunc(rq.get("retention_notes")),
    }


def _kpi_digest(bundle: dict[str, Any], sector: str) -> dict[str, Any]:
    screens = [
        {"name": s["name"], "threshold": s["threshold"], "dir": s["dir"]}
        for s in _SCREENS
        if s["sector"] == sector
    ]
    kpis = []
    for kpi in (bundle.get("kpi_dashboard") or [])[:_CAP_LIST]:
        if not isinstance(kpi, dict):
            continue
        name = str(kpi.get("display_name") or "").strip()
        value = str(kpi.get("stated_value") or "").strip()
        if name and value:
            kpis.append({"name": name, "value": value})
    return {"kpis": kpis, "screens": screens}


def _quality_digest(bundle: dict[str, Any]) -> dict[str, Any]:
    qoe = bundle.get("qoe") or {}
    addbacks = []
    for a in (qoe.get("addbacks") or [])[:_CAP_ADDBACKS]:
        if not isinstance(a, dict):
            continue
        addbacks.append({"label": _trunc(a.get("label"), 60), "amount": a.get("amount")})
    return {
        "addback_pct_of_ebitda": qoe.get("addback_pct_of_ebitda"),
        "addbacks": addbacks,
        "flags": _string_list([str((f or {}).get("description") or f) for f in (qoe.get("flags") or [])]),
    }


def _forecast_digest(bundle: dict[str, Any]) -> dict[str, Any]:
    fin = bundle.get("financials") or {}
    forecast_rows = [r for r in (fin.get("forecast_rows") or []) if isinstance(r, dict)][:_CAP_LIST]
    forecast_assumptions = [
        {"assumption": _trunc(a.get("assumption")), "support": a.get("support")}
        for a in (fin.get("forecast_assumptions") or [])[:_CAP_ASSUMPTIONS]
        if isinstance(a, dict)
    ]
    if forecast_rows or forecast_assumptions:
        return {"forecast_rows": forecast_rows, "forecast_assumptions": forecast_assumptions}
    # No forecast data path (plan §1.5/§1.7) — fall back to the historical
    # P&L so the take can still ground itself in real, extracted figures
    # rather than rendering over an empty digest.
    history = [r for r in (fin.get("table_rows") or []) if isinstance(r, dict)][-3:]
    return {
        "history": [
            {"year": r.get("year"), "revenue": r.get("revenue"), "ebitda_margin_pct": r.get("ebitda_margin_pct")}
            for r in history
        ]
    }


def build_final_report_narrative_digest(bundle: dict[str, Any]) -> dict[str, Any]:
    """Compact, whitelisted per-section digest. Each section is built solely
    from the bundle paths that section's take is allowed to comment on."""
    meta = bundle.get("meta") or {}
    sector = str(meta.get("vertical_overlay") or "tech_services")
    return {
        "business": _business_digest(bundle),
        "financial": _financial_digest(bundle),
        "customer": _customer_digest(bundle),
        "kpi": _kpi_digest(bundle, sector),
        "quality": _quality_digest(bundle),
        "forecast": _forecast_digest(bundle),
        "gaps_needing_reason": _gaps_needing_reason(bundle),
    }


_CAP_GAP_REASONS = 10


def _gaps_needing_reason(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """The appendix gaps that carry no rationale of their own.

    Several agents write the reason into the gap sentence and it is split out
    deterministically upstream; those are skipped here. Only the ones that
    arrive as a bare request are sent, each with the index it must come back
    under so a reason can never be attached to a different row than the one
    it was written for.
    """
    out: list[dict[str, Any]] = []
    for index, gap in enumerate(bundle.get("data_room_gaps") or []):
        if not isinstance(gap, dict) or gap.get("why"):
            continue
        item = str(gap.get("item") or "").strip()
        if item:
            out.append({"i": index, "item": _trunc(item, 200)})
        if len(out) >= _CAP_GAP_REASONS:
            break
    return out


# ---------------------------------------------------------------------------
# The bounded LLM call
# ---------------------------------------------------------------------------

_NON_FABRICATION_RULE = (
    "Use ONLY the facts and figures present in the input JSON below. Never invent a figure, "
    "name, date or fact that is not in the input — you have no access to the original source "
    "documents, only this already-extracted digest."
)

_EMPTY_SECTION_RULE = (
    "For EACH of the six sections (business, financial, customer, kpi, quality, forecast): if that "
    "section's digest is empty (no figures, no bullets, nothing to comment on), return null for its "
    "take. Do NOT produce a take for a section whose digest is empty. A section where the agents "
    "extracted nothing must render no box at all — a confident-sounding take over absent data is "
    "fabrication, which is worse than a blank box."
)

_MPS_SILENCE_RULE = (
    "Never mention the Minimum Pursuit Score, any score, or a threshold/pass-fail verdict in any "
    "take or in the recommendation. The score appears once, on its own page, and is not previewed "
    "or restated anywhere else in the report."
)

_SYSTEM_PROMPT = f"""You are drafting the six "Analyst take" boxes and the cover recommendation for a \
private-equity final diligence report. Your audience is an investment team that has already read the \
table, chart or list each take sits below — your job is to say what it MEANS for the deal, not to \
restate it. A take that paraphrases the chart above it is worse than no take, because it costs the \
reader a second look for nothing.

{_NON_FABRICATION_RULE}

{_EMPTY_SECTION_RULE}

{_MPS_SILENCE_RULE}

Each take (business_take, financial_take, customer_take, kpi_take, quality_take, forecast_take): ONE \
or TWO sentences, maximum 240 characters, leading with the specific figure or fact from that section's \
digest.

Business take: when the input's "business" section has a non-empty "sale_process", one clause must \
state how the business is being brought to market, naming the bank/advisor exactly as the field names \
it — never infer or correct a name that is not in the field. When "key_partners" is non-empty, name the \
most important of them. Never mention either topic when its field is empty — an unbanked deal is not a \
fact you may assert from silence, and an absent partner list is not a fact either.

"recommendation": a short structured call.
- "verdict": a few words, the headline call.
- "rationale": ONE sentence, grounded in the digest as a whole — never narrowed to a single metric.
- "conditions": at most 3 short bullets, the things that would need to be true.
- "tone": the literal string "pass" when the read is positive, otherwise null.
If there is not enough digest across all six sections to support a call, return "recommendation" as \
null rather than inventing one.

"gap_reasons": one entry for EACH object in the input's "gaps_needing_reason" list, echoing its "i" \
unchanged and adding "why": ONE sentence, maximum 160 characters, saying why a private-equity buyer \
needs that missing item — what it would let the team confirm or price. This is diligence reasoning \
about a document that is ABSENT, so it is the one place you are not restating an extracted figure; \
it must still never assert anything about THIS company's numbers, since the item was not extracted. \
Return an empty list when the input list is empty.

Respond with ONLY a JSON object, no markdown fences, with these exact keys:
{{
  "business_take": "<take or null>",
  "financial_take": "<take or null>",
  "customer_take": "<take or null>",
  "kpi_take": "<take or null>",
  "quality_take": "<take or null>",
  "forecast_take": "<take or null>",
  "recommendation": {{"verdict": "<or null>", "rationale": "<or null>", "conditions": ["<bullet>", "..."], "tone": "<'pass' or null>"}} or null,
  "gap_reasons": [{{"i": <index from the input>, "why": "<one sentence>"}}, "..."]
}}"""

_TAKE_KEYS = (
    "business_take",
    "financial_take",
    "customer_take",
    "kpi_take",
    "quality_take",
    "forecast_take",
)
_RESULT_KEYS = _TAKE_KEYS + ("recommendation", "gap_reasons")

_DEGRADED_FIELDS: dict[str, Any] = {key: None for key in _RESULT_KEYS}
# A degraded run contributes no reasons rather than a null the view must guard.
_DEGRADED_FIELDS["gap_reasons"] = {}

_FENCE_RE = re.compile(r"```(?:json)?|```")


def _parse_json_response(raw: str) -> Any:
    return json.loads(_FENCE_RE.sub("", raw).strip())


def _coerce_recommendation(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    conditions = value.get("conditions")
    return {
        "verdict": value.get("verdict") if isinstance(value.get("verdict"), str) else None,
        "rationale": value.get("rationale") if isinstance(value.get("rationale"), str) else None,
        "conditions": [str(c) for c in conditions if isinstance(c, str)] if isinstance(conditions, list) else [],
        "tone": "pass" if value.get("tone") == "pass" else None,
    }


def _validate_and_coerce(parsed: dict[str, Any]) -> dict[str, Any]:
    """Drops unknown keys, coerces each take to ``str | None``, coerces the
    recommendation to its exact shape. A model that returns a dict/list where
    a string was asked for must not reach Jinja."""
    result: dict[str, Any] = {}
    for key in _TAKE_KEYS:
        value = parsed.get(key)
        result[key] = value if isinstance(value, str) and value.strip() else None
    result["recommendation"] = _coerce_recommendation(parsed.get("recommendation"))
    result["gap_reasons"] = _coerce_gap_reasons(parsed.get("gap_reasons"))
    return result


def _coerce_gap_reasons(value: Any) -> dict[int, str]:
    """``{gap index: why}``, keeping only well-formed entries.

    Keyed by the index the model was asked to echo rather than by position in
    its reply, so a model that drops, reorders or invents an entry cannot
    attach a reason to a gap it was not written for — it simply contributes
    nothing for the rows it got wrong.
    """
    out: dict[int, str] = {}
    if not isinstance(value, list):
        return out
    for entry in value:
        if not isinstance(entry, dict):
            continue
        index, why = entry.get("i"), entry.get("why")
        if isinstance(index, bool) or not isinstance(index, int):
            continue
        if isinstance(why, str) and why.strip():
            out[index] = why.strip()
    return out


def synthesize_final_report_narrative(
    bundle: dict[str, Any],
    llm_endpoint: str,
    spark: Any = None,
) -> dict[str, Any]:
    """The final report's section-level prose: one analyst take per section
    page plus a structured recommendation. Never raises — any failure (the
    gateway call, a malformed JSON response, valid JSON with the wrong shape)
    degrades to every field ``None`` with ``final_narrative_status="degraded"``,
    so the template's per-box guards simply render fewer boxes rather than a
    broken page.
    """
    del spark  # reserved for future retrieval-backed grounding; unused today

    digest = build_final_report_narrative_digest(bundle)

    try:
        raw, usage = llm_client.chat(
            system_prompt=_SYSTEM_PROMPT,
            user_content=json.dumps(digest),
            endpoint=llm_endpoint,
            max_tokens=_MAX_TOKENS,
            temperature=0.0,
        )
        accumulate_tokens(usage, endpoint=llm_endpoint)
        parsed = _parse_json_response(raw)
        if not isinstance(parsed, dict):
            raise ValueError("LLM response was not a JSON object")
    except Exception as exc:  # noqa: BLE001 - this synthesis must never raise (T11)
        print(f"[final_report_narrative] bounded call failed, degrading: {exc!r}")
        return {**_DEGRADED_FIELDS, "final_narrative_status": "degraded"}

    result = _validate_and_coerce(parsed)
    result["final_narrative_status"] = "success"
    return result
