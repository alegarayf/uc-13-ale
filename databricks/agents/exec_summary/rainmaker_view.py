"""Deterministic render-time projection from the canonical orchestrator bundle
into the fields the Rainmaker "Opportunity Summary" template needs.

Mirrors the pattern of :mod:`agents.exec_summary.tldr_compress` — a pure,
non-LLM function that derives a few display-only views (stat tiles, a
financial-data-availability table, severity labels) from the bundle. It never
mutates its input and never invents company-specific literals: every label
comes from ``kpi_dashboard[].display_name``, ``headline_metrics``, or a
generic fallback, so a healthcare company and a SaaS company render through
the same code path (plan §5.3 — data-driven rule).

See docs/plans/CIM-first-rainmaker-template/plan.md Apéndice A.3 for the
field-mapping spec this implements (this module makes a few pragmatic,
verified-against-real-bundle corrections to that sketch — see inline notes
where a field named in A.3 does not actually exist in
``orchestrator_bundle.schema.yaml``, e.g. ``qoe.ebitda_scenarios``).
"""

from __future__ import annotations

import re
from typing import Any

from agents.exec_summary.formatters import format_kpi_value, is_operator_gap

_NOT_IN_VDR = "NOT IN VDR"
_NONE = "NONE"

_SEVERITY_LABELS: dict[str, str] = {
    "critical": "CRITICAL",
    "material": "HIGH",
    "track": "OPEN",
}
_SEVERITY_COLOR_VARS: dict[str, str] = {
    "critical": "--red-txt",
    "material": "--ylw-txt",
    "track": "--meta",
}
_SEVERITY_BG_VARS: dict[str, str] = {
    "critical": "--red-bg",
    "material": "--ylw-bg",
    "track": "--box-bg",
}

_STAT_TILE_CAP = 6
_STAT_TILE_MIN = 3
_STAT_TILE_VALUE_MAX_LEN = 24  # kpi_dashboard.stated_value is often a narrative
_NUMERIC_LEAD_RE = re.compile(r"^[\$€]?-?[\d,]+(\.\d+)?\s*[%kKmMbB]?\b")

_AUDIT_TERMS = ("audit", "audited")


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    return not text or text == "—"


def _headline(bundle: dict[str, Any], key: str) -> str:
    return str((bundle.get("headline_metrics") or {}).get(key) or "").strip()


def _last_populated(rows: list[dict[str, Any]], field: str) -> str:
    """Most recent (last) row in ``financials.table_rows`` with a non-blank ``field``."""
    for row in reversed(rows):
        if isinstance(row, dict) and not _is_blank(row.get(field)):
            return str(row[field]).strip()
    return ""


_ADDBACK_LINE_ITEM_METRICS = frozenset({"tier4_addback", "large_unsupported_addback"})


def _addback_counts(qoe: dict[str, Any]) -> tuple[int, int]:
    """(items, tier4) counted from ``qoe.flags``.

    Only ``tier4_addback`` and ``large_unsupported_addback`` represent one
    row of the addback ledger each (verified against Elder Care/Clearsulting/
    GKF flags — those two metric names are the QoE agent's own per-line-item
    vocabulary). The other ``qoe.flags`` metrics (``total_addbacks_pct_of_ebitda``,
    ``revenue_quality_*``) are aggregate/comparison signals, not individual
    addback lines, and must not inflate the "N items" count. This is a schema
    vocabulary match, not a per-company literal — generalizes across verticals.
    """
    flags = qoe.get("flags") or []
    items = 0
    tier4 = 0
    for flag in flags:
        if not isinstance(flag, dict):
            continue
        metric = str(flag.get("metric") or "").lower()
        if metric not in _ADDBACK_LINE_ITEM_METRICS:
            continue
        items += 1
        if metric == "tier4_addback":
            tier4 += 1
    return items, tier4


def _cim_presence(bundle: dict[str, Any]) -> str:
    """Parse ``meta.basis_of_preparation`` for the ``cim_detected=`` marker
    that :class:`BundleBuilder` embeds (Apéndice A.1 — no separate boolean
    field is exposed on ``meta`` itself)."""
    basis = str((bundle.get("meta") or {}).get("basis_of_preparation") or "")
    match = re.search(r"cim_detected=(True|False)", basis)
    if match:
        return "PRESENT" if match.group(1) == "True" else _NONE
    return _NONE


def _gaps_mention(bundle: dict[str, Any], terms: tuple[str, ...]) -> bool:
    for gap in bundle.get("data_room_gaps") or []:
        if not isinstance(gap, dict):
            continue
        item = str(gap.get("item") or "")
        if is_operator_gap(item):
            continue
        lowered = item.lower()
        if any(term in lowered for term in terms):
            return True
    return False


def _financial_availability(bundle: dict[str, Any]) -> list[dict[str, str]]:
    financials = bundle.get("financials") or {}
    qoe = bundle.get("qoe") or {}
    rows = financials.get("table_rows") or []

    ltm_revenue = _headline(bundle, "ltm_revenue")
    ltm_ebitda = _headline(bundle, "ltm_ebitda")
    revenue_cagr = _headline(bundle, "revenue_cagr")
    gross_margin = _last_populated(rows, "gross_margin_pct") if isinstance(rows, list) else ""

    addback_pct = qoe.get("addback_pct_of_ebitda")
    items, tier4 = _addback_counts(qoe)
    if items:
        addback_status = f"{items} ITEMS" + (f" · {tier4} TIER-4" if tier4 else "")
    else:
        addback_status = _NONE

    if not _is_blank(ltm_ebitda):
        adjusted_ebitda_status = ltm_ebitda
    elif not _is_blank(addback_pct):
        try:
            pct_num = float(addback_pct)
            adjusted_ebitda_status = f"NOT COMPUTABLE — ADDBACKS {pct_num:.0f}% OF REPORTED EBITDA"
        except (TypeError, ValueError):
            adjusted_ebitda_status = "NOT COMPUTABLE"
    else:
        adjusted_ebitda_status = "NOT COMPUTABLE"

    qoe_report_status = "NONE" if _is_blank(qoe.get("tier_summary")) else "PRESENT"
    audited_status = "FLAGGED — SEE GAPS" if _gaps_mention(bundle, _AUDIT_TERMS) else "NOT CONFIRMED"

    return [
        {"label": "LTM Revenue", "status": ltm_revenue or _NOT_IN_VDR},
        {"label": "Gross Margin", "status": gross_margin or "NOT EXTRACTED"},
        {"label": "Reported EBITDA", "status": ltm_ebitda or "NOT STATED"},
        {"label": "Adjusted EBITDA", "status": adjusted_ebitda_status},
        {"label": "Revenue CAGR / YoY", "status": revenue_cagr or "BLANK"},
        {"label": "Addback ledger", "status": addback_status},
        {"label": "Quality of Earnings report", "status": qoe_report_status},
        {"label": "CIM / Offering memo", "status": _cim_presence(bundle)},
        {"label": "Audited financials", "status": audited_status},
    ]


def _numeric_leading(value: str) -> bool:
    return bool(_NUMERIC_LEAD_RE.match(value.strip()))


def _tiles_from_kpi_dashboard(bundle: dict[str, Any]) -> list[dict[str, str]]:
    """Short, numeric-looking KPI rows only — long narrative ``stated_value``
    strings (common outside the healthcare overlay) are not tile material."""
    tiles: list[dict[str, str]] = []
    for row in bundle.get("kpi_dashboard") or []:
        if not isinstance(row, dict):
            continue
        value = format_kpi_value(row.get("stated_value")).strip()
        label = str(row.get("display_name") or "").strip()
        if not value or not label:
            continue
        if len(value) > _STAT_TILE_VALUE_MAX_LEN or not _numeric_leading(value):
            continue
        tiles.append({"value": value, "label": label})
        if len(tiles) >= _STAT_TILE_CAP:
            break
    return tiles


def _generic_fallback_tiles(bundle: dict[str, Any]) -> list[dict[str, str]]:
    """Company-agnostic tiles built only from fields every bundle has, used
    to top up when ``kpi_dashboard`` has too few numeric-looking rows (e.g.
    non-healthcare overlays whose KPI rows are narrative or boolean)."""
    candidates = [
        (_headline(bundle, "ltm_ebitda_margin_pct"), "LTM EBITDA Margin"),
        (_headline(bundle, "revenue_cagr"), "Revenue CAGR"),
        (str(len(bundle.get("risks") or [])), "Flagged Risks"),
        (str(len(bundle.get("data_room_gaps") or [])), "Data Room Gaps"),
        (str((bundle.get("meta") or {}).get("overall_confidence") or "").upper(), "Overall Confidence"),
    ]
    return [{"value": v, "label": lbl} for v, lbl in candidates if v]


def _stat_tiles(bundle: dict[str, Any]) -> list[dict[str, str]]:
    tiles = _tiles_from_kpi_dashboard(bundle)
    if len(tiles) < _STAT_TILE_MIN:
        for tile in _generic_fallback_tiles(bundle):
            if len(tiles) >= _STAT_TILE_CAP:
                break
            if tile not in tiles:
                tiles.append(tile)
    return tiles[:_STAT_TILE_CAP]


def severity_label(severity: str) -> str:
    """Bundle severity (``critical|material|track``) → template label."""
    return _SEVERITY_LABELS.get(str(severity or "").lower(), str(severity or "").upper())


def severity_color_var(severity: str) -> str:
    """CSS text-color variable name (Apéndice A.4) for a bundle severity."""
    return _SEVERITY_COLOR_VARS.get(str(severity or "").lower(), "--meta")


def severity_bg_var(severity: str) -> str:
    """CSS background-color variable name (Apéndice A.4) for a bundle severity."""
    return _SEVERITY_BG_VARS.get(str(severity or "").lower(), "--box-bg")


def _confidence_rows(bundle: dict[str, Any]) -> list[dict[str, str]]:
    cba = bundle.get("confidence_by_area") or {}
    rows = [
        {"area": key.replace("_", " ").title(), "level": str(level or "").upper()}
        for key, level in cba.items()
    ]
    overall = str((bundle.get("meta") or {}).get("overall_confidence") or "").upper()
    if overall:
        rows.append({"area": "Overall", "level": overall})
    return rows


_RISK_CAP = 8


def _enriched_risks(bundle: dict[str, Any]) -> list[dict[str, str]]:
    """``bundle.risks`` rows with ``severity_label``/``severity_color_var``/
    ``severity_bg_var`` pre-resolved, so the Jinja template never has to call
    a Python function — it just iterates plain dicts, same as every other
    bundle section."""
    rows: list[dict[str, str]] = []
    for risk in bundle.get("risks") or []:
        if not isinstance(risk, dict):
            continue
        severity = risk.get("severity")
        rows.append(
            {
                "risk": str(risk.get("risk") or ""),
                "evidence": str(risk.get("evidence") or ""),
                "mitigant_or_question": str(risk.get("mitigant_or_question") or ""),
                "severity_label": severity_label(severity),
                "severity_color_var": severity_color_var(severity),
                "severity_bg_var": severity_bg_var(severity),
            }
        )
        if len(rows) >= _RISK_CAP:
            break
    return rows


def rainmaker_view(bundle: dict[str, Any]) -> dict[str, Any]:
    """Build the Rainmaker-template render view from a canonical bundle.

    Never mutates ``bundle``. Pure/deterministic — no LLM call.
    """
    return {
        "financial_availability": _financial_availability(bundle),
        "stat_tiles": _stat_tiles(bundle),
        "confidence_rows": _confidence_rows(bundle),
        "risks": _enriched_risks(bundle),
    }
