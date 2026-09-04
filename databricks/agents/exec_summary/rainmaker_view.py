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

import math
import re
import statistics
from typing import Any

from agents.exec_summary.formatters import format_kpi_value, is_operator_gap
from agents.exec_summary.mps_rubric import RubricError, load_rubric, mps_total, mps_verdict

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


def _revenue_growth_tile(
    bundle: dict[str, Any], financial_table: dict[str, Any] | None
) -> tuple[str, str] | None:
    """``(value, label)`` for the revenue-growth tile.

    Prefers the CAGR the financial table already computed and displays in its
    own growth column, so the tile and the table can never disagree — they
    used to, because ``headline_metrics.revenue_cagr`` is the FTA's *latest
    YoY growth* (``field_mapping._headline_from_fta``), not a CAGR at all.
    When there is no table CAGR the headline is still shown, but under the
    label that figure actually earns.
    """
    for row in (financial_table or {}).get("rows") or []:
        if row.get("metric_name") == "Total Revenue" and row.get("growth"):
            return str(row["growth"]), "Revenue CAGR"
    headline = _headline(bundle, "revenue_cagr")
    return (headline, "Revenue Growth (YoY)") if headline else None


def _generic_fallback_tiles(
    bundle: dict[str, Any], financial_table: dict[str, Any] | None = None
) -> list[dict[str, str]]:
    """Company-agnostic tiles built only from fields every bundle has, used
    to top up when ``kpi_dashboard`` has too few numeric-looking rows (e.g.
    non-healthcare overlays whose KPI rows are narrative or boolean)."""
    candidates: list[tuple[str, str] | None] = [
        (_headline(bundle, "ltm_ebitda_margin_pct"), "LTM EBITDA Margin"),
        _revenue_growth_tile(bundle, financial_table),
        (str(len(bundle.get("risks") or [])), "Flagged Risks"),
        (str(len(bundle.get("data_room_gaps") or [])), "Data Room Gaps"),
        (str((bundle.get("meta") or {}).get("overall_confidence") or "").upper(), "Overall Confidence"),
    ]
    return [
        {"value": candidate[0], "label": candidate[1]}
        for candidate in candidates
        if candidate and candidate[0]
    ]


def _stat_tiles(
    bundle: dict[str, Any], financial_table: dict[str, Any] | None = None
) -> list[dict[str, str]]:
    tiles = _tiles_from_kpi_dashboard(bundle)
    if len(tiles) < _STAT_TILE_MIN:
        for tile in _generic_fallback_tiles(bundle, financial_table):
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


# Period labels the agents produce are free-form ("2024A", "2025B", "LTM MAY
# 2025", "FY23"), and ``financials.table_rows`` arrives in whatever order the
# extraction happened to emit — observed on a real render: 2023A, 2024A, LTM
# MAY 2025, 2022, which makes every growth/CAGR figure computed left-to-right
# meaningless. Sorting by the year the label names is company-agnostic: it
# reads the agent's own label and never renames or drops a period.
_PERIOD_YEAR_RE = re.compile(r"(?:19|20)\d{2}")
_PERIOD_SHORT_YEAR_RE = re.compile(r"(?:^|[^0-9A-Za-z])(?:FY|CY)\s*'?(\d{2})(?![0-9])", re.IGNORECASE)


def _period_sort_year(label: str) -> int | None:
    """Calendar year named by a period label, or ``None`` when it names none.
    ``"LTM MAY 2025"`` → 2025; ``"FY23"`` → 2023; ``"Budget"`` → ``None``."""
    match = _PERIOD_YEAR_RE.search(label)
    if match:
        return int(match.group(0))
    short = _PERIOD_SHORT_YEAR_RE.search(label)
    if short:
        return 2000 + int(short.group(1))
    return None


def _financial_periods(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """``financials.table_rows`` deduped by ``year`` (defensive — protects
    against bundles persisted before the field_mapping dedup fix) and sorted
    chronologically. Periods whose label names no year keep their original
    relative order and go last, so an unparseable label is never reordered on
    a guess."""
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

    labels = [str(r.get("year") or "").strip() for r in periods]
    years = [_period_sort_year(label) for label in labels]
    if not any(year is not None for year in years):
        return periods

    order = sorted(
        range(len(periods)),
        key=lambda i: (years[i] is None, years[i] if years[i] is not None else 0, i),
    )
    if order != list(range(len(periods))):
        print(
            "[rainmaker_view] financial periods were not in chronological order — "
            f"reordered {labels} → {[labels[i] for i in order]}"
        )
    return [periods[i] for i in order]


# A single period extracted in a different unit than its neighbours (e.g. one
# column in raw dollars while the rest of the table is in thousands) makes the
# growth and CAGR columns nonsense — confirmed on a real render, where a
# $40,251,450 period sitting next to $58,082 produced "64572.4% growth". The
# ratio between two adjacent periods of the same P&L is never this large, so a
# gap of ≥500× against the table's own median is a unit mismatch, not a real
# move. Only exact powers of 1000 are ever applied, and only to the $ cells of
# the offending period — this rescales the unit the agent read, it does not
# invent or adjust a figure.
_UNIT_OUTLIER_FACTOR = 500.0
_MONEY_FIELDS = ("revenue", "gross_profit", "ebitda")


def _nearest_power_of_1000(ratio: float) -> float:
    return 1000.0 ** round(math.log(ratio, 1000))


def _format_money(value: float, original: Any) -> str:
    """Re-render a rescaled figure in the same style the agent used (currency
    symbol, parenthesised negatives) so the table stays visually uniform."""
    text = str(original).strip()
    prefix = "$" if text.startswith("$") or text.startswith("($") else ""
    magnitude = abs(value)
    body = f"{magnitude:,.0f}" if magnitude >= 100 else f"{magnitude:,.1f}"
    if value < 0:
        return f"({prefix}{body})" if text.startswith("(") else f"-{prefix}{body}"
    return f"{prefix}{body}"


def _normalize_period_units(period_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy of ``period_rows`` with any period whose figures were extracted in
    a different unit rescaled onto the table's dominant unit. Never mutates
    its input (the rows belong to the caller's bundle)."""
    revenues = [_parse_money(row.get("revenue")) for row in period_rows]
    known = [abs(v) for v in revenues if v not in (None, 0)]
    if len(known) < 3:
        # With two periods there is no majority to call the third an outlier —
        # leave both exactly as extracted rather than guess which one is wrong.
        return period_rows

    median = statistics.median(known)
    if median <= 0:
        return period_rows

    normalized: list[dict[str, Any]] = []
    for row, revenue in zip(period_rows, revenues):
        ratio = abs(revenue) / median if revenue not in (None, 0) else 1.0
        if _UNIT_OUTLIER_FACTOR > ratio > 1 / _UNIT_OUTLIER_FACTOR:
            normalized.append(row)
            continue
        scale = _nearest_power_of_1000(ratio)
        if scale == 1.0:
            normalized.append(row)
            continue
        rescaled = dict(row)
        for field in _MONEY_FIELDS:
            value = _parse_money(row.get(field))
            if value is not None:
                rescaled[field] = _format_money(value / scale, row.get(field))
        print(
            f"[rainmaker_view] period {row.get('year')!r} was extracted {scale:,.0f}× the "
            f"table's other periods (revenue {row.get('revenue')!r} vs median {median:,.0f}) — "
            "rescaled onto the table's unit so growth and CAGR stay meaningful."
        )
        normalized.append(rescaled)
    return normalized


# Display unit for the table header. Hardcoding "in millions" (what the
# template used to do) mislabels every table the agents extract in thousands,
# which is most of them.
_UNIT_LABELS: tuple[tuple[float, str], ...] = (
    (1_000_000.0, "in millions"),
    (1_000.0, "in thousands"),
    (1.0, "in dollars"),
)
_HEADLINE_MONEY_RE = re.compile(
    r"^\s*[\$€]?\s*(-?[\d,]+(?:\.\d+)?)\s*(bn|bb|mm|b|m|k)\b", re.IGNORECASE
)
_HEADLINE_SUFFIX_MULTIPLIERS: dict[str, float] = {
    "bn": 1e9, "bb": 1e9, "b": 1e9, "mm": 1e6, "m": 1e6, "k": 1e3,
}


def _headline_absolute_dollars(text: str) -> float | None:
    """``"$23.0mm"`` → ``23_000_000``. Returns ``None`` unless the headline
    carries an explicit magnitude suffix — a bare ``"$23,022"`` says nothing
    about the unit the table is in, which is the whole question here."""
    match = _HEADLINE_MONEY_RE.match(text or "")
    if not match:
        return None
    try:
        value = float(match.group(1).replace(",", ""))
    except ValueError:
        return None
    return value * _HEADLINE_SUFFIX_MULTIPLIERS[match.group(2).lower()]


def _unit_label(bundle: dict[str, Any], revenue_values: list[float | None]) -> str:
    """Unit the table's figures are stated in, derived from the data itself.

    Preferred signal: ``headline_metrics.ltm_revenue``, which the agents state
    with an explicit suffix ("$23.0mm") — its ratio to the same figure in the
    table gives the unit directly. Falls back to the magnitude of the figures
    themselves, which separates the three units a P&L is realistically stated
    in. Never invents a unit: a table with no $ figures returns ``""`` and the
    header simply states no unit, instead of the hardcoded "in millions" that
    mislabelled every table extracted in thousands.
    """
    populated = [v for v in revenue_values if v not in (None, 0)]
    if not populated:
        return ""  # no $ figures to characterise — the header states no unit at all

    anchor = abs(populated[-1])
    absolute = _headline_absolute_dollars(_headline(bundle, "ltm_revenue"))
    if absolute:
        scale = _nearest_power_of_1000(absolute / anchor)
        for multiplier, label in _UNIT_LABELS:
            if scale >= multiplier:
                return label

    median = statistics.median(abs(v) for v in populated)
    if median >= 1_000_000:
        return "in dollars"
    if median >= 1_000:
        return "in thousands"
    return "in millions"


def _financial_table(bundle: dict[str, Any]) -> dict[str, Any]:
    """P&L table for the Rainmaker template — ``{periods, rows, currency,
    unit}``. Every ``$`` cell is either a figure the agent extracted or
    ``None`` (renders as "-"); ``% Growth`` is the only computed row (pure
    arithmetic between two already-extracted revenue figures, never a
    fabricated input)."""
    period_rows = _normalize_period_units(_financial_periods(bundle))
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

    # Growth column (round 3, A3) — computed AFTER margin reconciliation, so
    # a % row's growth reads the reconciled cells, not the agent's original
    # (possibly contradicting) stated percent.
    growth_col_label = _apply_row_growth(rows, periods)

    return {
        "periods": periods,
        "rows": rows,
        "currency": "$",
        "unit": "",
        "unit_label": _unit_label(bundle, revenue_values),
        "growth_col_label": growth_col_label,
    }


# Row metric names that show a CAGR (first-to-last populated period) in the
# growth column — dollar figures only; a CAGR on a percentage is meaningless.
_CAGR_GROWTH_ROWS = frozenset({"Total Revenue", "Gross Profit", "EBITDA"})
# Row metric names that show a point-delta (last minus first populated
# period) in the growth column — the two margin rows.
_DELTA_PTS_GROWTH_ROWS = frozenset({"% Gross Margin", "% EBITDA Margin"})


def _populated_first_last(
    values: list[float | None], periods: list[str]
) -> tuple[float, float, int] | None:
    """``(first_value, last_value, n_periods_between)`` from the first and
    last period that actually have a value, or ``None`` when fewer than 2
    periods are populated. Shared by the CAGR circles and the growth column
    so "first/last populated period" means the same thing in both places."""
    populated = [v for p, v in zip(periods, values) if v is not None]
    if len(populated) < 2:
        return None
    return populated[0], populated[-1], len(populated) - 1


def _cagr_between(first_value: float, last_value: float, n: int) -> float | None:
    """Compound annual growth rate, or ``None`` when it can't be computed
    (non-positive base, zero periods) — never a fabricated/zero fallback."""
    if first_value <= 0 or n <= 0:
        return None
    return (last_value / first_value) ** (1 / n) - 1


def _row_growth(metric_name: str, cells: list[str | None], periods: list[str]) -> tuple[str | None, str | None]:
    """``(growth, growth_kind)`` for one financial-table row's growth-column
    cell — a CAGR for $ rows, a point-delta for % margin rows, ``None`` for
    everything else (including ``% Growth``, where a CAGR-of-growth would be
    noise). Never fabricates: returns ``(None, None)`` when fewer than 2
    periods have an extracted figure."""
    if metric_name in _CAGR_GROWTH_ROWS:
        bounds = _populated_first_last([_parse_money(c) for c in cells], periods)
        if bounds is None:
            return None, None
        first_value, last_value, n = bounds
        cagr = _cagr_between(first_value, last_value, n)
        return (f"{cagr * 100:.0f}%", "cagr") if cagr is not None else (None, None)
    if metric_name in _DELTA_PTS_GROWTH_ROWS:
        bounds = _populated_first_last([_parse_percent(c) for c in cells], periods)
        if bounds is None:
            return None, None
        first_value, last_value, _n = bounds
        delta = last_value - first_value
        sign = "+" if delta >= 0 else ""
        return f"{sign}{delta:.1f} pts", "delta_pts"
    return None, None


def _apply_row_growth(rows: list[dict[str, Any]], periods: list[str]) -> str | None:
    """Mutates each row with its ``growth``/``growth_kind`` cell; returns the
    growth column's header label, or ``None`` (template omits the column
    entirely) when no row produced a growth figure."""
    any_growth = False
    for row in rows:
        growth, growth_kind = _row_growth(row["metric_name"], row["cells"], periods)
        row["growth"] = growth
        row["growth_kind"] = growth_kind
        any_growth = any_growth or growth is not None
    if not any_growth or len(periods) < 2:
        return None
    return f"CAGR / Δ {periods[0]}–{periods[-1]}"


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


_RULE_OF_X_CAP = 2

# The standard Rule-of-40 threshold (growth% + margin% >= 40) used across the
# industry to judge growth/profitability trade-off — not a judgment about
# any specific company, so a tile below it is presented neutrally, never as
# a warning (round 3, A5).
_RULE_OF_40_BENCHMARK = 40.0


def _rule_of_x(table: dict[str, Any]) -> list[dict[str, str]]:
    """"Rule of N" tiles (growth % + EBITDA margin %) for the most recent
    periods where both figures are available — mirrors the reference
    Rainmaker format's "Rule of 108 / Rule of 82" tiles, generalized (no
    period names hardcoded). Each tile also carries presentation-only fields
    (``components``, ``benchmark``) so the template can render a highlighted
    band (A5) without recomputing anything."""
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
        value_num = g_num + m_num
        tiles.append(
            {
                "label": f"Rule of {value_num:.0f}",
                "period_label": f"{period} growth + margin",
                "growth": g,
                "margin": m,
                "value_num": value_num,
                "components": f"{g} growth + {m} margin",
                "benchmark": "above" if value_num >= _RULE_OF_40_BENCHMARK else "below",
            }
        )
    return tiles[-_RULE_OF_X_CAP:]


# ---------------------------------------------------------------------------
# MPS (Minimum Pursuit Score) — pure render-time projection (T2, plan §8).
# Never does arithmetic of its own: every score/verdict number that reaches
# the template comes from mps_rubric.mps_total()/mps_verdict(). The rubric
# file (not the LLM's own ordering) is the source of the 7-row skeleton, so
# the section always has exactly 7 rows even when a run degraded or was
# never computed (§8.2 "Degraded / partial").
# ---------------------------------------------------------------------------

_MPS_RUN_MODE_LABELS: dict[str, str] = {
    "cim_only": "CIM-only preview",
    "full_vdr_no_cim": "Full data room",
}
_MPS_EVIDENCE_MARKERS: dict[str, str] = {
    "contact_dependent": "◇",
    "judgment_over_context": "◇",
}
_MPS_EVIDENCE_LEGEND = (
    "◇ assessed from proxies and judgment; not directly evidenced in the data room"
)
_MPS_COMMENTARY_CAP = 4
_MPS_NOT_ASSESSED = "Not yet assessed in this preview."


def _mps_run_mode_label(run_mode: Any) -> str:
    """Human-readable run_mode label via a safe-default lookup (§8.2) — an
    unknown/future run_mode degrades to the raw string rather than raising."""
    raw = str(run_mode or "")
    return _MPS_RUN_MODE_LABELS.get(raw, raw)


def _mps_column_header(run: dict[str, Any]) -> str:
    label = _mps_run_mode_label(run.get("run_mode"))
    date = str(run.get("generated_at") or "").strip()[:10]
    if label and date:
        return f"{label} · {date}"
    return label or date


def _mps_category_skeleton() -> list[dict[str, str]]:
    """The 7-category skeleton (key/display_name/evidence_basis), read from
    the rubric file — never from a run's own (possibly missing or
    model-ordered) ``categories`` list. Returns ``[]`` only if the rubric
    itself fails to load, which callers must treat as "no rows" rather than
    inventing placeholder categories."""
    try:
        rubric = load_rubric()
    except RubricError:
        return []
    return [
        {
            "key": category["key"],
            "display_name": category["display_name"],
            "evidence_basis": category["evidence_basis"],
        }
        for category in rubric.get("categories", [])
    ]


def _mps_commentary_bullets(category: dict[str, Any]) -> list[dict[str, str | None]]:
    """Merged bullet list for one category's Commentary cell — sub-axis
    notes first, then rationale, then counter-evidence last, capped at 4
    total (§8.2). Never fabricates: a blank field simply contributes no
    bullet."""
    bullets: list[dict[str, str | None]] = []
    for note in category.get("sub_axis_notes") or []:
        if not isinstance(note, dict):
            continue
        text = str(note.get("note") or "").strip()
        if not text:
            continue
        bullets.append({"kind": "sub_axis", "axis": str(note.get("axis") or "").strip(), "text": text})

    rationale = str(category.get("rationale") or "").strip()
    if rationale:
        bullets.append({"kind": "rationale", "axis": None, "text": rationale})

    counter_evidence = str(category.get("counter_evidence") or "").strip()
    if counter_evidence:
        bullets.append({"kind": "counter_evidence", "axis": None, "text": counter_evidence})

    return bullets[:_MPS_COMMENTARY_CAP]


def _mps_score(category: dict[str, Any]) -> int | None:
    score = category.get("score")
    return score if isinstance(score, int) and not isinstance(score, bool) else None


def _mps_empty_row(category: dict[str, str]) -> dict[str, Any]:
    return {
        "key": category["key"],
        "display_name": category["display_name"],
        "evidence_basis": category["evidence_basis"],
        "evidence_marker": _MPS_EVIDENCE_MARKERS.get(category["evidence_basis"]),
        "score_cells": [],
        "bullets": [],
    }


def _mps_table(mps_runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Pure projection from MPSAgent output(s) to the MPS page's render
    shape. ``mps_runs`` is a list of runs shaped per plan §4 (the agent's
    ``score()`` return value) — F-10's trend view is column-generic, but the
    POC always passes a single-element list.

    Never computes a total/verdict itself beyond calling
    :func:`mps_rubric.mps_total` / :func:`mps_rubric.mps_verdict` — those
    functions are the single source of MPS arithmetic. Always returns
    exactly 7 rows (in rubric-file order), degraded or not (§8.2).
    """
    skeleton = _mps_category_skeleton()

    if not mps_runs:
        rows = [_mps_empty_row(category) for category in skeleton]
        return {
            "mps_status": "degraded",
            "degraded_reason": "MPS has not been run for this preview",
            "columns": [],
            "rows": rows,
            "total_cells": [],
            "threshold": None,
            "verdict": None,
            "n_scored": 0,
            "show_legend": any(row["evidence_marker"] for row in rows),
        }

    key_order = [category["key"] for category in skeleton]

    columns: list[dict[str, str]] = []
    per_run_by_key: list[dict[str, dict[str, Any]]] = []
    total_cells: list[float | None] = []
    for run in mps_runs:
        by_key = {
            category["key"]: category
            for category in (run.get("categories") or [])
            if isinstance(category, dict) and category.get("key")
        }
        per_run_by_key.append(by_key)
        columns.append({"header": _mps_column_header(run)})
        scores = [_mps_score(by_key.get(key) or {}) for key in key_order]
        total_cells.append(mps_total(scores))

    latest_run = mps_runs[-1]
    latest_by_key = per_run_by_key[-1]
    threshold = latest_run.get("threshold")
    verdict = mps_verdict(total_cells[-1], threshold) if threshold is not None else None

    rows: list[dict[str, Any]] = []
    n_scored = 0
    for category in skeleton:
        key = category["key"]
        score_cells = [_mps_score(by_key.get(key) or {}) for by_key in per_run_by_key]
        if score_cells and score_cells[-1] is not None:
            n_scored += 1
        rows.append(
            {
                "key": key,
                "display_name": category["display_name"],
                "evidence_basis": category["evidence_basis"],
                "evidence_marker": _MPS_EVIDENCE_MARKERS.get(category["evidence_basis"]),
                "score_cells": score_cells,
                "bullets": _mps_commentary_bullets(latest_by_key.get(key) or {}),
            }
        )

    return {
        "mps_status": str(latest_run.get("mps_status") or "degraded"),
        "degraded_reason": latest_run.get("degraded_reason"),
        "columns": columns,
        "rows": rows,
        "total_cells": [f"{total:.1f}" if total is not None else None for total in total_cells],
        "threshold": threshold,
        "verdict": verdict,
        "n_scored": n_scored,
        "show_legend": any(row["evidence_marker"] for row in rows),
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


def rainmaker_view(
    bundle: dict[str, Any], mps_runs: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Build the Rainmaker-template render view from a canonical bundle.

    Never mutates ``bundle``. Pure/deterministic — no LLM call. Returns both
    the legacy 4-page-template fields (``financial_availability``,
    ``stat_tiles``, ``confidence_rows``) and the Capa A fields for the
    current 3-section landscape template (``metadata``, ``financials``
    — including its per-row ``growth``/``growth_kind`` and
    ``growth_col_label`` — ``key_metrics``, ``rule_of_x``, ``mps``). The
    financial snapshot bar chart and CAGR circles (round 3, A4) were dropped
    in favor of the financial table's own growth column (A3) and the
    Rule-of-X band (A5); there is no replacement field for them.

    ``mps_runs`` is MPSAgent output(s) (plan §4/§8), not part of the
    canonical bundle — it lives in its own Delta table (§9) and is supplied
    by the caller. ``None``/``[]`` renders the MPS section's degraded
    skeleton (7 rows, no scores) rather than omitting it.
    """
    financial_table = _financial_table(bundle)
    stat_tiles = _stat_tiles(bundle, financial_table)
    return {
        "financial_availability": _financial_availability(bundle),
        "stat_tiles": stat_tiles,
        "confidence_rows": _confidence_rows(bundle),
        "risks": _enriched_risks(bundle),
        "diligence_questions": _deduped_diligence_questions(bundle),
        "metadata": _metadata(bundle),
        "financials": financial_table,
        "key_metrics": stat_tiles,
        "rule_of_x": _rule_of_x(financial_table),
        "mps": _mps_table(mps_runs or []),
    }
