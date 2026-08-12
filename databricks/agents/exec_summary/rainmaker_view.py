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


def _leading_number(value: str) -> str:
    """Leading numeric fragment (e.g. ``"998"`` from ``"998 clients served
    TTM Aug-24; 2024E 1,251 total..."``), or ``""`` if the string doesn't
    start with one. Deterministic — pulls a number the agent already
    extracted, never invents one."""
    match = _NUMERIC_LEAD_RE.match(value.strip())
    return match.group(0).strip() if match else ""


def _tiles_from_kpi_dashboard(bundle: dict[str, Any]) -> list[dict[str, str]]:
    """KPI rows whose ``stated_value`` *starts* with a number. Agents commonly
    return a real figure followed by long narrative context (e.g. "998
    clients served TTM Aug-24; 2024E 1,251 total clients across...") — only
    the leading number is tile-worthy; the string doesn't need to be short
    or numeric-only as a whole."""
    tiles: list[dict[str, str]] = []
    for row in bundle.get("kpi_dashboard") or []:
        if not isinstance(row, dict):
            continue
        raw_value = format_kpi_value(row.get("stated_value")).strip()
        label = str(row.get("display_name") or "").strip()
        if not raw_value or not label:
            continue
        value = _leading_number(raw_value)
        if not value:
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

# Domain acronyms that must stay uppercase (or a fixed casing) through
# humanization — a plain .title() turns "ebitda" into "Ebitda" and "coc"
# into "Coc". Generic across companies/verticals — these are the workstream
# agents' own vocabulary, not a per-company literal.
_ACRONYMS: dict[str, str] = {
    "ebitda": "EBITDA", "cim": "CIM", "om": "OM", "coc": "CoC",
    "ioi": "IOI", "nda": "NDA", "kpi": "KPI", "kpis": "KPIs",
    "arr": "ARR", "nrr": "NRR", "grr": "GRR", "msa": "MSA", "sow": "SOW",
    "qofe": "QoE", "qoe": "QoE", "yoy": "YoY", "cagr": "CAGR",
    "pct": "%", "ar": "AR", "dso": "DSO", "capex": "CapEx",
}


def _humanize_slug(slug: str) -> str:
    """``"large_unsupported_addback"`` → ``"Large Unsupported Addback"``;
    ``"ebitda_margin_pct"`` → ``"EBITDA Margin %"``; ``"coc_consent_required"``
    → ``"CoC Consent Required"``. Falls back to plain title-case for any
    word not in ``_ACRONYMS``."""
    words = str(slug or "").replace("_", " ").split()
    return " ".join(_ACRONYMS.get(w.lower(), w.title()) for w in words)


def _enriched_risks(bundle: dict[str, Any]) -> list[dict[str, str]]:
    """``bundle.risks`` rows with ``risk_label``/``severity_label``/
    ``severity_color_var``/``severity_bg_var`` pre-resolved, so the Jinja
    template never has to call a Python function — it just iterates plain
    dicts, same as every other bundle section."""
    rows: list[dict[str, str]] = []
    for risk in bundle.get("risks") or []:
        if not isinstance(risk, dict):
            continue
        severity = risk.get("severity")
        rows.append(
            {
                "risk": str(risk.get("risk") or ""),
                "risk_label": _humanize_slug(risk.get("risk")),
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


_DILIGENCE_QUESTIONS_CAP = 6  # matches the 6 thesis-testing archetypes in rainmaker_narrative.py (plan Part B, B3)


def _deduped_diligence_questions(bundle: dict[str, Any]) -> list[dict[str, str]]:
    """``bundle.diligence_questions`` with exact (category, question) repeats
    collapsed — some agents emit the same question more than once (observed
    on a real run, not synthetic). Removing an exact duplicate never drops
    information, unlike any content-altering dedup would."""
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for q in bundle.get("diligence_questions") or []:
        if not isinstance(q, dict):
            continue
        category = str(q.get("category") or "")
        question = str(q.get("question") or "")
        if not question:
            continue
        key = (category.lower(), question.lower())
        if key in seen:
            continue
        seen.add(key)
        rows.append({"category": category, "question": question})
        if len(rows) >= _DILIGENCE_QUESTIONS_CAP:
            break
    return rows


# ---------------------------------------------------------------------------
# Capa A — deterministic financial projection (Iteración 2, plan §3.1).
# Reuses figures financial_trends_agent.py already extracted (via
# bundle.financials.table_rows) — never calls an LLM, never invents a figure
# that wasn't already extracted. All money/percent parsing is pure arithmetic
# on strings the agents produced.
# ---------------------------------------------------------------------------

_MONEY_STRIP_RE = re.compile(r"[^0-9.\-]")
_PERCENT_LEADING_RE = re.compile(r"-?\d+(\.\d+)?")

_FINANCIAL_TABLE_ROW_SPECS: tuple[tuple[str, str | None, bool], ...] = (
    ("Total Revenue", "revenue", False),
    ("% Growth", None, False),  # computed from consecutive Total Revenue values
    ("Gross Profit", "gross_profit", False),
    ("% Gross Margin", "gross_margin_pct", False),
    ("EBITDA", "ebitda", True),
    ("% EBITDA Margin", "ebitda_margin_pct", False),
)

# A $ row and its own % row, self-consistency-checked against the same
# period's Total Revenue (plan Part B, B4). ``financial_trends_agent`` and
# ``quality_of_earnings_agent`` extract the $ figure and the % figure as
# independent LLM calls — sometimes against different bases (reported vs.
# PF-adjusted) — so a stated % can silently contradict the $ shown right
# next to it (confirmed on a real render: a stated "36.6% Gross Margin" next
# to Gross Profit/Revenue figures that divide to 9.1%). Recomputing from the
# two $ figures already in the same row guarantees the displayed % is at
# least internally consistent with what the reader can verify by hand.
_MARGIN_ROW_PAIRS: tuple[tuple[str, str], ...] = (
    ("Gross Profit", "% Gross Margin"),
    ("EBITDA", "% EBITDA Margin"),
)
_MARGIN_RECONCILE_TOLERANCE_PTS = 1.0


def _parse_money(value: Any) -> float | None:
    """``"$1.9" -> 1.9``, ``"(0.3)" -> -0.3``, ``"" -> None``. Never raises —
    unparseable input (narrative text, blank) returns ``None`` rather than a
    fabricated number."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in ("-", "–"):
        return None
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    cleaned = _MONEY_STRIP_RE.sub("", text)
    if not cleaned or cleaned in ("-", "."):
        return None
    try:
        num = float(cleaned)
    except ValueError:
        return None
    return -num if negative else num


def _parse_percent(value: Any) -> float | None:
    """Leading numeric fragment of a percent string, e.g. ``"42.3% (Historical
    P&L) / 44.3% (Pro Forma — DISCREPANCY)" -> 42.3``. Same "extract the
    number the agent already gave us" rule as ``_leading_number`` above —
    never invents a figure, just tolerates narrative padding around it."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = _PERCENT_LEADING_RE.search(text)
    if not match:
        return None
    try:
        return float(match.group())
    except ValueError:
        return None


def _clean_cell(value: Any) -> str | None:
    return None if _is_blank(value) else str(value).strip()


def _financial_periods(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """``financials.table_rows`` deduped by ``year`` (defensive — protects
    against bundles persisted before the field_mapping dedup fix), preserving
    original order."""
    raw_rows = (bundle.get("financials") or {}).get("table_rows") or []
    periods: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        year = str(row.get("year") or "").strip()
        if not year or year in seen:
            continue
        seen.add(year)
        periods.append(row)
    return periods


def _financial_table(bundle: dict[str, Any]) -> dict[str, Any]:
    """P&L table for the Rainmaker template — ``{periods, rows, currency,
    unit}``. Every ``$`` cell is either a figure the agent extracted or
    ``None`` (renders as "-"); ``% Growth`` is the only computed row (pure
    arithmetic between two already-extracted revenue figures, never a
    fabricated input)."""
    period_rows = _financial_periods(bundle)
    periods = [str(r.get("year") or "") for r in period_rows]
    revenue_values = [_parse_money(r.get("revenue")) for r in period_rows]

    growth_values: list[str | None] = [None] if periods else []
    for prev, curr in zip(revenue_values, revenue_values[1:]):
        if prev not in (None, 0) and curr is not None:
            growth_values.append(f"{(curr - prev) / prev * 100:.1f}%")
        else:
            growth_values.append(None)

    rows = []
    for label, field, highlighted in _FINANCIAL_TABLE_ROW_SPECS:
        values = growth_values if field is None else [_clean_cell(r.get(field)) for r in period_rows]
        # NOTE: key is "cells", not "values" — Jinja resolves `row.values` as
        # the dict.values() bound method (attribute lookup wins over item
        # lookup), so a "values" key would silently break `{% for v in
        # row.values %}` in the template.
        rows.append({"metric_name": label, "cells": values, "is_highlighted": highlighted})

    _reconcile_margin_rows(rows, revenue_values, periods)

    return {"periods": periods, "rows": rows, "currency": "$", "unit": ""}


def _reconcile_margin_rows(
    rows: list[dict[str, Any]], revenue_values: list[float | None], periods: list[str]
) -> None:
    """Mutate ``rows`` in place so every % row is self-consistent with its own
    $ row and Total Revenue for that period (plan Part B, B4).

    ``financial_trends_agent``/``quality_of_earnings_agent`` extract a $
    figure and its % in independent LLM calls, sometimes against different
    bases — so a stated % can contradict the $ shown right next to it. This
    never touches the $ cells (those are the agent's own extracted figures,
    left untouched); it only ever overwrites a % cell, and only when the $
    figures needed to check it are both present. A blank stays blank; a
    genuinely unverifiable % (missing $ inputs) is left as the agent stated
    it — this is a consistency check, not a re-extraction.
    """
    by_metric = {row["metric_name"]: row for row in rows}
    for dollar_label, pct_label in _MARGIN_ROW_PAIRS:
        dollar_row = by_metric.get(dollar_label)
        pct_row = by_metric.get(pct_label)
        if dollar_row is None or pct_row is None:
            continue

        new_cells: list[str | None] = []
        for i, stated_cell in enumerate(pct_row["cells"]):
            revenue = revenue_values[i] if i < len(revenue_values) else None
            dollar_value = _parse_money(dollar_row["cells"][i]) if i < len(dollar_row["cells"]) else None

            if revenue in (None, 0) or dollar_value is None:
                # Nothing to check against — leave the agent's own figure
                # (or blank) exactly as extracted.
                new_cells.append(stated_cell)
                continue

            recomputed = dollar_value / revenue * 100
            stated_pct = _parse_percent(stated_cell)

            if stated_pct is not None and abs(recomputed - stated_pct) <= _MARGIN_RECONCILE_TOLERANCE_PTS:
                new_cells.append(stated_cell)  # already consistent — keep the agent's own text
                continue

            period = periods[i] if i < len(periods) else f"period #{i}"
            if stated_pct is None:
                print(
                    f"[rainmaker_view] {pct_label} ({period}): blank — filled from "
                    f"{dollar_label}/Total Revenue = {recomputed:.1f}%"
                )
            else:
                print(
                    f"[rainmaker_view] {pct_label} ({period}): stated {stated_pct:.1f}% does not "
                    f"reconcile with {dollar_label}/Total Revenue = {recomputed:.1f}% "
                    f"(diff {abs(recomputed - stated_pct):.1f}pts > {_MARGIN_RECONCILE_TOLERANCE_PTS}pt "
                    "tolerance) — using the recomputed value so the % never contradicts the $ shown."
                )
            new_cells.append(f"{recomputed:.1f}%")

        pct_row["cells"] = new_cells


def _rows_by_metric(table: dict[str, Any]) -> dict[str, list[Any]]:
    return {row["metric_name"]: row["cells"] for row in table.get("rows") or []}


def _cagr_from_series(values: list[float | None], periods: list[str], label: str) -> dict[str, str] | None:
    populated = [(p, v) for p, v in zip(periods, values) if v is not None]
    if len(populated) < 2:
        return None
    first_period, first_value = populated[0]
    last_period, last_value = populated[-1]
    n = len(populated) - 1
    if first_value <= 0 or n <= 0:
        return None
    cagr = (last_value / first_value) ** (1 / n) - 1
    return {"label": f"{label} {first_period}–{last_period}", "value": f"{cagr * 100:.0f}%"}


def _cagr_circles(table: dict[str, Any]) -> list[dict[str, str]]:
    """CAGR tiles (Revenue, EBITDA) computed only between periods that both
    have an extracted ``$`` figure — never interpolated or assumed. Omits a
    circle entirely rather than showing a fabricated/zero CAGR."""
    periods = table.get("periods") or []
    metrics = _rows_by_metric(table)
    revenue_values = [_parse_money(v) for v in metrics.get("Total Revenue", [])]
    ebitda_values = [_parse_money(v) for v in metrics.get("EBITDA", [])]

    circles = []
    for label, values in (("Revenue CAGR", revenue_values), ("EBITDA CAGR", ebitda_values)):
        circle = _cagr_from_series(values, periods, label)
        if circle:
            circles.append(circle)
    return circles


_RULE_OF_X_CAP = 2


def _rule_of_x(table: dict[str, Any]) -> list[dict[str, str]]:
    """"Rule of N" tiles (growth % + EBITDA margin %) for the most recent
    periods where both figures are available — mirrors the reference
    Rainmaker format's "Rule of 108 / Rule of 82" tiles, generalized (no
    period names hardcoded)."""
    periods = table.get("periods") or []
    metrics = _rows_by_metric(table)
    growth = metrics.get("% Growth", [])
    margin = metrics.get("% EBITDA Margin", [])

    tiles: list[dict[str, str]] = []
    for period, g, m in zip(periods, growth, margin):
        g_num = _parse_percent(g)
        m_num = _parse_percent(m)
        if g_num is None or m_num is None:
            continue
        tiles.append(
            {
                "label": f"Rule of {g_num + m_num:.0f}",
                "period_label": f"{period} growth + margin",
                "growth": g,
                "margin": m,
            }
        )
    return tiles[-_RULE_OF_X_CAP:]


def _snapshot_chart(table: dict[str, Any]) -> dict[str, Any]:
    """Numeric series for the Financial Snapshot chart — the template owns
    rendering (SVG/CSS bars); this only normalizes already-parsed values."""
    periods = table.get("periods") or []
    metrics = _rows_by_metric(table)
    revenue = [_parse_money(v) for v in metrics.get("Total Revenue", [])]
    ebitda = [_parse_money(v) for v in metrics.get("EBITDA", [])]
    margin_pct = [_parse_percent(v) for v in metrics.get("% EBITDA Margin", [])]

    all_values = [v for v in revenue + ebitda if v is not None]
    return {
        "periods": periods,
        "revenue": revenue,
        "ebitda": ebitda,
        "margin_pct": margin_pct,
        "max_value": max(all_values) if all_values else None,
        "has_data": bool(all_values),
    }


def _metadata(bundle: dict[str, Any]) -> dict[str, Any]:
    meta = bundle.get("meta") or {}
    company_name = str(meta.get("company_name") or "")
    generated_at = str(meta.get("generated_at") or "")
    return {
        "company_name": company_name,
        "project_name": company_name,
        "prepared_for": "Rallyday Partners",
        "prepared_by": "Rallyday Partners",
        "date": generated_at[:10] if generated_at else "",
        "status": str(meta.get("disclaimer_text") or "").strip()
        or "Preliminary — for internal discussion only. Not investment advice and not a recommendation; subject to confirmatory diligence.",
    }


def rainmaker_view(bundle: dict[str, Any]) -> dict[str, Any]:
    """Build the Rainmaker-template render view from a canonical bundle.

    Never mutates ``bundle``. Pure/deterministic — no LLM call. Returns both
    the legacy 4-page-template fields (``financial_availability``,
    ``stat_tiles``, ``confidence_rows``) and the Capa A fields for the
    3-page reference-format template (``metadata``, ``financials``,
    ``key_metrics``, ``cagr_circles``, ``rule_of_x``, ``snapshot``).
    """
    financial_table = _financial_table(bundle)
    stat_tiles = _stat_tiles(bundle)
    return {
        "financial_availability": _financial_availability(bundle),
        "stat_tiles": stat_tiles,
        "confidence_rows": _confidence_rows(bundle),
        "risks": _enriched_risks(bundle),
        "diligence_questions": _deduped_diligence_questions(bundle),
        "metadata": _metadata(bundle),
        "financials": financial_table,
        "key_metrics": stat_tiles,
        "cagr_circles": _cagr_circles(financial_table),
        "rule_of_x": _rule_of_x(financial_table),
        "snapshot": _snapshot_chart(financial_table),
    }
