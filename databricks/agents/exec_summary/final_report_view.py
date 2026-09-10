"""final_report_view.py — deterministic projection for final_report.html.j2.

PROPOSAL / v0.1. Sibling of ``rainmaker_view.py``, same contract and same
discipline:

  * Pure and deterministic. No LLM call, no Spark read, never mutates
    ``bundle``. Narrative prose still comes from the narrative layer and is
    passed in, not generated here.
  * Every chart arrives at the template pre-scaled. ``*_pct`` fields are
    0-100 relative to that chart's own maximum, so ``final_report.html.j2``
    only ever multiplies a percentage by a fixed geometry constant.
  * Never fabricates. A figure the agents did not extract stays ``None`` all
    the way to the page, where it renders as "not extracted". A ``None`` bar
    is omitted, never drawn at zero — a zero bar is a claim.
  * Caps live here, not in the template. The report's readability is a
    function of these constants.

The threshold screens in ``_SCREENS`` are Austin's directional first-pass
numbers (tech services / healthcare services). They are screens, not rules:
the output labels a metric "below screen" and never "unacceptable".
"""

from __future__ import annotations

import re
from typing import Any

from agents.exec_summary.formatters import (
    format_dollars,
    is_operator_gap,
    has_explicit_magnitude,
    money_to_dollars,
    period_sort_key,
)
from agents.exec_summary.rainmaker_view import (
    _financial_periods,
    format_period_money,
    _normalize_period_units,
    _parse_percent as _rainmaker_parse_percent,
    _unit_label as _rainmaker_unit_label,
)

# --- Caps: the length budget of the report -------------------------------
CAP_TILES = 6
CAP_THESIS = 3
CAP_WATCHOUTS = 3
CAP_BULLETS = 4
CAP_SEGMENTS = 6
CAP_TOP_CUSTOMERS = 5
CAP_KPIS = 8
CAP_RISKS = 8
CAP_QUESTIONS = 8
CAP_GAPS = 10

# A KPI cell is a summary line, not the underlying schedule. Clearsulting's
# bill_rates_by_role held 7,315 characters — every practice at every level —
# which rendered as a page and a half of prose and displaced the sections
# after it.
CAP_KPI_NOTE_CHARS = 240
CAP_KPI_OTHER = 8

KPI_KIND_NOTE = "note"
KPI_KIND_BREAKDOWN = "breakdown"

MPS_MAX_SCORE = 5

# --- Rallyday first-pass screens -----------------------------------------
# (metric_key, display, threshold, direction, sector) — direction "min" means
# a value below the threshold is flagged; "max" means above it is flagged.
_SCREENS: tuple[dict[str, Any], ...] = (
    {"key": "nrr_pct", "name": "Net revenue retention", "threshold": 90, "dir": "min", "sector": "tech_services"},
    {"key": "grr_pct", "name": "Gross revenue retention", "threshold": 85, "dir": "min", "sector": "tech_services"},
    {"key": "gross_margin_pct", "name": "Gross margin", "threshold": 40, "dir": "min", "sector": "tech_services"},
    {"key": "top1_pct", "name": "Top customer concentration", "threshold": 25, "dir": "max", "sector": "tech_services"},
    {"key": "organic_growth_pct", "name": "Organic revenue growth", "threshold": 10, "dir": "min", "sector": "tech_services"},
    {"key": "ebitda_margin_pct", "name": "EBITDA margin", "threshold": 10, "dir": "min", "sector": "tech_services"},
    {"key": "avg_account_size", "name": "Average account size", "threshold": 100, "dir": "min", "sector": "tech_services"},
    {"key": "revenue_growth_pct", "name": "Revenue growth", "threshold": 5, "dir": "min", "sector": "healthcare_services"},
    {"key": "ebitda_margin_pct", "name": "EBITDA margin", "threshold": 10, "dir": "min", "sector": "healthcare_services"},
    {"key": "gross_margin_pct", "name": "Gross margin", "threshold": 30, "dir": "min", "sector": "healthcare_services"},
    {"key": "top1_pct", "name": "Top referral source / customer", "threshold": 20, "dir": "max", "sector": "healthcare_services"},
    {"key": "government_payor_pct", "name": "Government payor share", "threshold": 50, "dir": "max", "sector": "healthcare_services"},
    {"key": "employee_turnover_pct", "name": "Employee turnover", "threshold": 30, "dir": "max", "sector": "healthcare_services"},
    {"key": "utilization_pct", "name": "Utilization", "threshold": 70, "dir": "min", "sector": "healthcare_services"},
)

# Three vocabularies reach this module and all three must map. The agents
# write Red/Yellow/Green; bundle_builder._FLAG_TO_RISK translates those to
# critical/material/track before a risk reaches the bundle; some rows carry
# high/medium/low directly. Knowing only two of the three is why the risk
# page counted 0 high, 0 medium and 0 low above a table of rows chipped
# CRITICAL — every one of them classified "neutral" and fell into no bucket.
# rainmaker_view already speaks critical/material/track; this is the final
# report catching up to the same vocabulary.
_SEVERITY_CLASS = {
    "high": "high", "red": "high", "critical": "high",
    "medium": "medium", "yellow": "medium", "material": "medium",
    "low": "low", "green": "low", "track": "low",
}
_SEVERITY_LABEL = {
    "high": "High", "red": "High", "critical": "Critical",
    "medium": "Medium", "yellow": "Medium", "material": "Material",
    "low": "Low", "green": "Low", "track": "Track",
}

# forecast_agent applies its credibility rubric deterministically as
# Supported/Plausible/Stretch (forecast_agent.py:632-707); the template's
# severity classes speak high/medium/low. An unrecognised rating degrades to
# "neutral", never "high" — an unrecognised rating is not evidence of risk.
_ASSUMPTION_SUPPORT_CLASS = {"supported": "low", "plausible": "medium", "stretch": "high"}
_ASSUMPTION_SUPPORT_LABEL = {"supported": "Supported", "plausible": "Plausible", "stretch": "Stretch"}

_MONEY_STRIP = re.compile(r"[^0-9.\-]")


# =========================================================================
# Numeric helpers. ``parse_percent`` delegates to
# ``agents.exec_summary.rainmaker_view._parse_percent`` — proven equivalent
# (tests/test_final_report_numeric_parity.py). ``parse_money`` stays inline:
# it disagrees with ``rainmaker_view._parse_money`` on magnitude suffixes
# (``"2k"``, ``"1.5bn"``, ``"1.5b"`` — this module's version applies the
# suffix multiplier, rainmaker_view's does not), so delegating would move
# every suffixed figure on the page. Divergence recorded in
# ../../../docs/plans/final_report/final_report_plan.md §9.
# =========================================================================

def parse_money(value: Any) -> float | None:
    """Leading numeric value of a money string, honouring (parentheses) as
    negative and k/m/bn suffixes. Returns ``None`` for anything unparseable —
    never 0.0, because 0 is a figure and ``None`` is an absence."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"-", "—", "n/a", "N/A"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    multiplier = 1.0
    low = text.lower()
    if low.endswith(("bn", "b")):
        multiplier = 1_000.0
    elif low.endswith("k"):
        multiplier = 0.001
    cleaned = _MONEY_STRIP.sub("", text)
    if cleaned in {"", "-", "."}:
        return None
    try:
        num = float(cleaned) * multiplier
    except ValueError:
        return None
    return -num if negative else num


def parse_percent(value: Any) -> float | None:
    """Leading numeric fragment of a percent string. Tolerates the narrative
    padding agents sometimes emit, e.g. ``"42.3% (Historical) / 44.3% (Pro
    Forma — DISCREPANCY)"`` -> ``42.3``.

    Delegates to ``rainmaker_view._parse_percent`` — proven behaviourally
    equivalent on a comparison sweep (tests/test_final_report_numeric_parity.py).
    Kept as a public name here because the template and the tests use it."""
    return _rainmaker_parse_percent(value)


def scale(values: list[float | None], max_value: float | None = None) -> list[float | None]:
    """Normalise to 0-100 against the series maximum (or an explicit
    ``max_value`` when two charts must share an axis — page 4 and page 8 do).
    ``None`` in, ``None`` out."""
    present = [v for v in values if v is not None]
    if not present:
        return [None] * len(values)
    top = max_value if max_value is not None else max(present)
    if not top:
        return [None] * len(values)
    return [None if v is None else max(0.0, min(100.0, (v / top) * 100.0)) for v in values]


def severity_class(value: Any) -> str:
    return _SEVERITY_CLASS.get(str(value or "").lower(), "neutral")


def severity_label(value: Any) -> str:
    return _SEVERITY_LABEL.get(str(value or "").lower(), str(value or "—").title())


def assumption_support_class(value: Any) -> str:
    return _ASSUMPTION_SUPPORT_CLASS.get(str(value or "").lower(), "neutral")


def assumption_support_label(value: Any) -> str:
    return _ASSUMPTION_SUPPORT_LABEL.get(str(value or "").lower(), str(value or "—").title())


# Confidence runs the opposite way to severity: HIGH confidence is reassuring,
# LOW confidence is the warning. Same chip vocabulary, inverted mapping — a
# green "High" and a red "Low", never the reverse.
_CONFIDENCE_CLASS = {"high": "low", "medium": "medium", "low": "high"}


def confidence_class(value: Any) -> str:
    return _CONFIDENCE_CLASS.get(str(value or "").lower(), "neutral")


def _recommendation(narrative: dict[str, Any]) -> dict[str, Any]:
    """Adapter for ``headline.recommendation``, which the template reads as a
    dict (``rec.verdict``/``rec.rationale``/``rec.conditions``/``rec.tone``).

    Two narrative layers can populate this key: the ER's, which returns a
    plain sentence, and T11's, which returns the structured dict the template
    actually wants. A degraded T11 call plus a successful ER one means this
    key can arrive as a bare string — today that mismatch silently prints
    "Not yet concluded" over a usable sentence, because a template
    attribute read on a ``str`` finds nothing. Wrap it instead of losing it."""
    rec = narrative.get("recommendation")
    if isinstance(rec, dict):
        return rec
    if isinstance(rec, str) and rec.strip():
        return {"verdict": None, "rationale": rec, "conditions": [], "tone": None}
    # Same keys as the branches above: the template reads rec.tone on every
    # path, and returning a dict missing it makes the shape depend on which
    # narrative layer degraded.
    return {"verdict": None, "rationale": None, "conditions": [], "tone": None}


# =========================================================================
# Section builders. Each returns exactly the shape the matching page of
# final_report.html.j2 consumes. Add a section here and a page there — never
# only one of the two.
# =========================================================================

def _pnl_table(bundle: dict[str, Any]) -> dict[str, Any]:
    """The generic P&L block. Every row is optional: a row whose cells are all
    absent is dropped, so a services business, a SaaS business and an
    industrial business all render cleanly from one row set. The ``calc``
    column is CAGR where three or more periods exist, otherwise last-period
    YoY — pure arithmetic on figures the agents already extracted.

    Period order and unit handling are adopted from ``rainmaker_view`` so this
    document and the executive review, built from the same bundle, never
    disagree on either: ``_financial_periods`` dedupes by year and sorts
    chronologically by the year each label names (an unparseable label keeps
    its relative position, placed after the parseable ones — never dropped,
    never guessed at); ``_normalize_period_units`` rescales a period whose
    figures were extracted in a different unit than its neighbours."""
    ordered = ordered_financials(bundle)
    periods = [str(r.get("year") or "").strip() for r in ordered]
    currency = (bundle.get("financials") or {}).get("currency") or "$"

    specs = (
        ("Revenue", "revenue", "total", "money"),
        ("Cost of revenue", "cogs", "sub", "money"),
        ("Gross profit", "gross_profit", "", "money"),
        ("Gross margin %", "gross_margin_pct", "sub", "percent"),
        ("Operating expenses", "opex", "sub", "money"),
        ("EBITDA", "ebitda", "total", "money"),
        ("EBITDA margin %", "ebitda_margin_pct", "sub", "percent"),
        ("Adjusted EBITDA", "adjusted_ebitda", "", "money"),
        ("Adj. EBITDA margin %", "adjusted_ebitda_margin_pct", "sub", "percent"),
        ("Capital expenditure", "capex", "sub", "money"),
        ("Free cash flow", "free_cash_flow", "", "money"),
    )

    rows: list[dict[str, Any]] = []
    for label, field, emphasis, kind in specs:
        if kind == "money":
            # Same formatter the executive review uses, so the two documents
            # cannot disagree about how a figure is written — only, legitimately,
            # about which figures a run extracted.
            cells = [format_period_money(r.get(field), currency) for r in ordered]
        else:
            cells = [None if r.get(field) in (None, "") else str(r.get(field)).strip() for r in ordered]
        if not any(cells):
            continue  # self-pruning: never show an empty row
        nums = [parse_money(c) if kind == "money" else parse_percent(c) for c in cells]
        rows.append({
            "label": label,
            "cells": cells,
            "emphasis": emphasis,
            "calc": _calc_column(nums, kind, len(periods)),
            "cite": None,
        })

    # No producer populates ``financials.unit_label`` today (A-3 territory),
    # so the bundle read is a future-proofing first choice: if a producer
    # ever writes it, that value wins over the computed one. Until then this
    # always falls through to the same computation the executive review uses.
    revenue_values = [parse_money(r.get("revenue")) for r in ordered]
    computed_unit_label = _rainmaker_unit_label(bundle, revenue_values)
    return {
        "periods": periods,
        "rows": rows,
        "currency": (bundle.get("financials") or {}).get("currency") or "$",
        "unit": (bundle.get("financials") or {}).get("unit") or "",
        "unit_label": (bundle.get("financials") or {}).get("unit_label") or computed_unit_label or "as reported",
        "calc_col_label": "CAGR" if len(periods) >= 3 else "YoY",
    }


def ordered_financials(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """The financial periods every part of this report must agree on.

    ``_pnl_table`` already built its rows this way — deduped, sorted by the
    year each label names, and with a period extracted in a foreign unit
    rescaled onto the table's own. The three charts read
    ``financials.table_rows`` raw instead, and so disagreed with the table
    printed directly above them: Clearsulting's 2022 revenue arrives as
    "$40,251,450" beside three periods stated in thousands, which the table
    reconciled to $40.3M and the chart drew as a bar 707x its neighbours,
    labelled "40251.4bn", positioned after TTM25 because the agent happened
    to extract it last.

    One accessor so a fix to ordering or units reaches the whole document.
    """
    return _normalize_period_units(_financial_periods(bundle))


def financial_unit_label(bundle: dict[str, Any], ordered: list[dict[str, Any]] | None = None) -> str:
    """The unit every money figure in this report is stated in — one source,
    so the P&L header, its charts and the forecast chart cannot disagree."""
    rows = ordered_financials(bundle) if ordered is None else ordered
    values = [parse_money(r.get("revenue")) for r in rows]
    return (bundle.get("financials") or {}).get("unit_label") or _rainmaker_unit_label(bundle, values) or ""


def _calc_column(nums: list[float | None], kind: str, n_periods: int) -> str | None:
    """CAGR for money rows across 3+ periods; percentage-point delta for
    percent rows; YoY otherwise. Returns ``None`` when the inputs do not
    support the calculation — an unresolvable cell is left blank, not zeroed."""
    present = [(i, v) for i, v in enumerate(nums) if v is not None]
    if len(present) < 2:
        return None
    (i0, first), (i1, last) = present[0], present[-1]
    if kind == "percent":
        return f"{last - first:+.1f} pp"
    if first <= 0 or last <= 0:
        return None
    span = i1 - i0
    if n_periods >= 3 and span >= 2:
        return f"{(((last / first) ** (1.0 / span)) - 1) * 100:.1f}%"
    return f"{((last / first) - 1) * 100:+.1f}%"


def _trend_chart(bundle: dict[str, Any], shared_max: float | None = None) -> dict[str, Any]:
    """Revenue columns with the EBITDA-margin line overlaid.

    EBITDA is deliberately NOT a second column here. On a revenue axis an
    11% margin business draws an EBITDA bar a tenth the height of revenue,
    which reads as an error rather than as information. Reported vs adjusted
    EBITDA gets its own chart on its own axis instead (``_ebitda_chart``).
    """
    rows = ordered_financials(bundle)
    unit = financial_unit_label(bundle, rows)
    labels = [str(r.get("year") or "") for r in rows]
    rev = [parse_money(r.get("revenue")) for r in rows]
    margin = [parse_percent(r.get("ebitda_margin_pct")) for r in rows]

    axis_max = shared_max if shared_max is not None else max([v for v in rev if v is not None] or [0])
    rev_pct = scale(rev, axis_max)

    return {
        "series": [
            {
                "label": labels[i],
                "bar1_pct": rev_pct[i], "bar1_value": money_label(rev[i], unit),
                "bar2_pct": None, "bar2_value": None,
                "line_pct": None if margin[i] is None else max(0.0, min(100.0, margin[i])),
                "line_value": None if margin[i] is None else f"{margin[i]:.1f}%",
            }
            for i in range(len(rows))
        ],
        "bar1_name": "Revenue", "bar2_name": None, "line_name": "EBITDA margin %",
        "axis_max_label": money_label(axis_max, unit),
        "footnote": "Revenue columns on the left axis; margin line on a 0-100% axis.",
    }


def _ebitda_chart(bundle: dict[str, Any]) -> dict[str, Any]:
    """Reported against adjusted EBITDA, on a shared EBITDA axis. The gap
    between the two columns IS the earnings-quality question, and this is the
    only place in the report where it is visible rather than described."""
    rows = ordered_financials(bundle)
    unit = financial_unit_label(bundle, rows)
    reported = [parse_money(r.get("ebitda")) for r in rows]
    adjusted = [parse_money(r.get("adjusted_ebitda")) for r in rows]
    axis_max = max([v for v in (reported + adjusted) if v is not None] or [0])
    rep_pct = scale(reported, axis_max)
    adj_pct = scale(adjusted, axis_max)
    return {
        "series": [
            {
                "label": str(rows[i].get("year") or ""),
                "bar1_pct": rep_pct[i], "bar1_value": money_label(reported[i], unit),
                "bar2_pct": adj_pct[i], "bar2_value": money_label(adjusted[i], unit),
                "line_pct": None, "line_value": None,
            }
            for i in range(len(rows))
        ],
        "bar1_name": "Reported EBITDA", "bar2_name": "Adjusted EBITDA", "line_name": None,
        "axis_max_label": money_label(axis_max, unit),
        "footnote": "The widening gap between the two columns is the addback question.",
    }


# Ordered longest-keyword-first so "billions" is not matched by "millions".
_UNIT_KEYWORDS: tuple[tuple[str, float], ...] = (
    ("billion", 1_000_000_000.0),
    ("million", 1_000_000.0),
    ("thousand", 1_000.0),
    ("dollar", 1.0),
)


def unit_multiplier(unit_label: Any) -> float | None:
    """Dollars per stated unit, or ``None`` when the label does not name one.

    Matches on the keyword rather than the whole phrase: ``_unit_label``
    returns "in thousands", but ``financials.unit_label`` is a free-text field
    a producer may one day fill with something like "$ millions, fiscal
    years". An exact-phrase lookup would silently miss that and leave part of
    a series unscaled — which is worse than not scaling at all, because the
    bars would then be drawn on two different magnitudes at once.
    """
    low = str(unit_label or "").lower()
    for keyword, factor in _UNIT_KEYWORDS:
        if keyword in low:
            return factor
    return None


def _short(value: float | None) -> str | None:
    """Compact unitless label for a bar whose unit is unknown.

    Kept for charts that are not denominated in the P&L's unit. Deliberately
    no longer appends "bn": the figures reaching these charts are stated in
    whatever unit the table is, so dividing by 1,000 and calling the result
    billions mislabelled every money chart in the report — a P&L in thousands
    rendered $57.09M of revenue as "57.1bn". Money charts now go through
    ``money_label`` instead, which knows the table's unit.
    """
    if value is None:
        return None
    if abs(value) >= 1_000:
        return f"{value:,.0f}"
    if abs(value) >= 1:
        return f"{value:.1f}"
    return f"{value:.2f}"


def absolute_revenue(raw: Any, unit_label: str) -> float | None:
    """A money figure in absolute dollars, whichever way it states its scale.

    Two series meet on the forecast chart and they do not agree on units.
    History arrives in the P&L's implicit unit ("$21,403", thousands); the
    forecast agent's revenue build states its own ("$21,403K"). Parsed the
    same way, the plan came out 1,000x smaller than the identical historical
    figure, so every plan bar drew at zero height with its label floating
    above an empty axis.

    A figure that names its own magnitude is trusted; one that does not is
    read in the table's unit.
    """
    if has_explicit_magnitude(raw):
        return money_to_dollars(raw)
    value = parse_money(raw)
    if value is None:
        return None
    return value * (unit_multiplier(unit_label) or 1.0)


def money_label(value: float | None, unit_label: str) -> str | None:
    """Bar label in absolute money, resolved through the table's stated unit.

    ``_unit_label`` already derives whether a P&L is stated in dollars,
    thousands or millions, and the table header prints it. The charts ignored
    it and invented their own magnitude. Reading the same signal means a chart
    bar and the table cell above it describe the same quantity: 57,090 stated
    in thousands is "$57.1M" on both.

    An unrecognised or absent unit falls back to the unitless compact form
    rather than assuming dollars — assuming is how the old label went wrong.
    """
    if value is None:
        return None
    multiplier = unit_multiplier(unit_label)
    if multiplier is None:
        return _short(value)
    return format_dollars(value * multiplier)


def _axis_bars(items: list[dict[str, Any]], threshold: float | None) -> dict[str, Any]:
    """Shared normaliser for every horizontal-bar chart. The axis maximum is
    the larger of the biggest value and the threshold, with 20% headroom, so
    a chart of 6-14% values still fills the page and the threshold marker
    always lands inside the frame."""
    values = [i["value_num"] for i in items if i.get("value_num") is not None]
    axis_max = max(values + ([threshold] if threshold is not None else []) or [1]) * 1.2
    if not axis_max:
        axis_max = 1.0
    for i in items:
        i["pct"] = None if i.get("value_num") is None else (i["value_num"] / axis_max) * 100.0
    return {
        "bars": [i for i in items if i.get("pct") is not None],
        "threshold_pct": None if threshold is None else (threshold / axis_max) * 100.0,
        "threshold_label": None if threshold is None else f"{threshold:g}% screen",
    }


def _concentration(bundle: dict[str, Any], sector: str) -> dict[str, Any]:
    """Top-account bars against the sector screen (25% tech services, 20%
    healthcare services). The threshold marker is the point of this chart —
    it turns a table of percentages into a judgment a VP can read at a
    glance."""
    rq = bundle.get("revenue_quality") or {}
    customers = [c for c in (rq.get("top_customers") or []) if isinstance(c, dict)]
    threshold = 20.0 if sector == "healthcare_services" else 25.0
    # Largest share first. A concentration chart is read top-down as a
    # ranking, and the agent's extraction order is the order it happened to
    # find the clients in — Clearsulting's rendered 18.3%, 5.9%, 2.6%, 3.4%,
    # 2.4%, which reads as noise rather than as a concentration profile.
    scored = []
    for c in customers:
        pct = parse_percent(c.get("revenue_pct_yr1"))
        if pct is not None:
            scored.append((pct, c))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    items = [
        {
            "label": _trunc(c.get("customer_name") or "Account", 26),
            "value": f"{pct:.1f}%",
            "value_num": pct,
            "flag": pct > threshold,
        }
        for pct, c in scored[:CAP_TOP_CUSTOMERS]
    ]
    out = _axis_bars(items, threshold)
    out["title"] = "Concentration"
    return out


_FLAG_TEXT_KEYS = ("note", "description", "flag", "value", "text", "message")


def flag_text(flag: Any) -> str:
    """Readable sentence for an agent flag record.

    Agent flags are dicts of ``metric``/``value``/``threshold``/``severity``/
    ``note``. Reaching for ``description``/``flag`` and falling back to the
    record itself printed the Python repr of the dict into the report — the
    "{'metric': 'tier4_addback', 'value': ...}" that appears in the earnings
    quality and legal tables. ``note`` is the field the agents write a
    sentence into; the rest are labels. When a record carries none of them,
    an empty string is better than punctuation soup: the row still renders
    with its severity and metric, just without a sentence it never had.
    """
    if not isinstance(flag, dict):
        return str(flag or "")
    for key in _FLAG_TEXT_KEYS:
        value = flag.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def humanize_metric(metric: Any) -> str:
    """``coc_consent_required`` -> ``CoC consent required``.

    Agent metric ids are snake_case identifiers and were rendered verbatim
    into the risk and legal tables, where they read as code rather than as
    risks. Acronyms the deal team reads as words are restored to their
    conventional casing; everything else is sentence case.
    """
    text = str(metric or "").strip()
    if not text:
        return ""
    # Already prose: leave it exactly as written. Not all risk rows carry a
    # snake_case id — some arrive as a sentence, and running one through the
    # identifier path collapsed it, because splitting on "_" yields a single
    # word and str.capitalize() lowercases everything after the first letter.
    # "Addback quality overstates EBITDA" came out "…overstates ebitda".
    if " " in text:
        return text
    words = text.replace("-", "_").split("_")
    acronyms = {
        "coc": "CoC", "qofe": "QofE", "qoe": "QoE", "nrr": "NRR", "grr": "GRR",
        "ebitda": "EBITDA", "yoy": "YoY", "ar": "AR", "kpi": "KPI", "pct": "%",
        "ip": "IP", "hr": "HR", "it": "IT", "ttm": "TTM", "sla": "SLA",
    }
    out = []
    for index, word in enumerate(words):
        low = word.lower()
        if low in acronyms:
            out.append(acronyms[low])
        elif index == 0:
            out.append(word.capitalize())
        else:
            out.append(low)
    rendered = " ".join(w for w in out if w)
    return rendered.replace(" %", " %").strip()


def _trunc(text: Any, n: int) -> str:
    """Chart labels and narrow table cells are truncated HERE, not in the
    template, so the cap is testable and consistent across charts."""
    value = str(text or "").strip()
    return value if len(value) <= n else value[: n - 1].rstrip() + "\u2026"


def _kpi_scorecard(bundle: dict[str, Any], sector: str, narrative: dict[str, Any] | None = None) -> dict[str, Any]:
    """KPI dashboard rows rendered as bullet bars against the applicable
    screens. Rows the agents could not extract are moved to a separate
    ``not_extracted`` list with the stated reason rather than shown as a
    zero-length bar."""
    screens = {s["key"]: s for s in _SCREENS if s["sector"] == sector}
    rows, flagged, missing, others, notes = [], [], [], [], []
    for kpi in (bundle.get("kpi_dashboard") or [])[: CAP_KPIS * 2]:
        if not isinstance(kpi, dict):
            continue
        key = str(kpi.get("metric_id") or "")
        screen = screens.get(key)
        raw_value = kpi.get("stated_value")
        name = str(kpi.get("display_name") or key or "KPI")
        # A field the agent filled with a sentence or a per-role breakdown is
        # not a metric, and must never reach the bar path: parse_percent will
        # happily pull "15" out of "up over 15% from prior year" and draw a
        # bar against a screen that number was never measured against.
        kind = str(kpi.get("value_kind") or "")
        if kind in (KPI_KIND_NOTE, KPI_KIND_BREAKDOWN):
            notes.append({"name": name, "value": _trunc(raw_value, CAP_KPI_NOTE_CHARS)})
            continue
        value_num = parse_percent(raw_value)
        if value_num is None:
            missing.append({"name": name, "reason": str(kpi.get("fill_state") or "not extracted").replace("_", " ")})
            continue
        # A bullet bar is only meaningful on a 0-100 scale. Counts, dollars and
        # ratios go to a plain table rather than being drawn as if they were
        # percentages — a $40.6 revenue-per-client bar filled to 40% would be
        # a made-up claim.
        if "%" not in str(raw_value) and key not in screens:
            others.append({"name": name, "value": _trunc(raw_value, CAP_KPI_NOTE_CHARS)})
            continue
        threshold = screen["threshold"] if screen else None
        flag = bool(
            screen
            and ((screen["dir"] == "min" and value_num < threshold) or (screen["dir"] == "max" and value_num > threshold))
        )
        row = {
            "name": name,
            "value": str(kpi.get("stated_value")),
            "pct": max(0.0, min(100.0, value_num)),
            "threshold_pct": threshold,
            "threshold_label": f"vs {threshold}%" if threshold is not None else "",
            "flag": flag,
        }
        rows.append(row)
        if flag:
            flagged.append({
                "name": name, "value": row["value"],
                "threshold_label": row["threshold_label"].replace("vs ", ""),
                "note": str(kpi.get("flag_note") or "Below the first-pass screen for this sector; materiality is a deal-team call."),
                "cite": None,
            })
    return {
        "overlay_label": sector.replace("_", " ").title(),
        "rows": rows[:CAP_KPIS],
        "flagged": flagged,
        "other_metrics": (others + notes)[:CAP_KPI_OTHER],
        "not_extracted": missing[:5],
        "take": (narrative or {}).get("kpi_take"),
    }


def _risks(bundle: dict[str, Any]) -> dict[str, Any]:
    """Risk register, severity-sorted and capped. The suppressed count is
    reported rather than silently dropped — a VP needs to know the report is
    a view, not the whole register."""
    order = {"high": 0, "red": 0, "medium": 1, "yellow": 1, "low": 2, "green": 2}
    raw = [r for r in (bundle.get("risks") or []) if isinstance(r, dict)]
    raw.sort(key=lambda r: order.get(str(r.get("severity") or "").lower(), 3))
    grid = [
        {
            # Agent risk ids are snake_case metric names (coc_consent_required,
            # revenue_quality_non_recurring_in_run_rate). Rendered verbatim they
            # read as code in a document a deal team circulates, and the long
            # unbroken tokens overflowed the column.
            "risk": humanize_metric(r.get("risk")) or str(r.get("risk") or ""),
            "evidence": str(r.get("evidence") or ""),
            "mitigant": str(r.get("mitigant_or_question") or ""),
            "severity_label": severity_label(r.get("severity")),
            "severity_class": severity_class(r.get("severity")),
            "cite": None,
        }
        for r in raw[:CAP_RISKS]
    ]
    counts = []
    for level, label in (("high", "High severity"), ("medium", "Medium"), ("low", "Low")):
        n = sum(1 for r in raw if severity_class(r.get("severity")) == level)
        counts.append({"label": label, "count": n, "flag": level == "high" and n > 0})
    return {"grid": grid, "counts": counts, "suppressed": max(0, len(raw) - CAP_RISKS)}


def _reader_facing_gaps(bundle: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    """The gaps that belong in an information request, with their original
    index so a model-written reason still lands on the right row.

    Pipeline diagnostics are dropped: "people_and_org.ownership is empty"
    names a bundle field, not a document, and a deal team reads this table as
    "what we are asking the seller for". The executive review has always
    filtered them (rainmaker_view._gaps_mention); this is the final report
    doing the same. They remain in the bundle for whoever is debugging a run.
    """
    out: list[tuple[int, dict[str, Any]]] = []
    for index, gap in enumerate(bundle.get("data_room_gaps") or []):
        if not isinstance(gap, dict):
            continue
        if is_operator_gap(str(gap.get("item") or "")):
            continue
        out.append((index, gap))
        if len(out) >= CAP_GAPS:
            break
    return out


def _appendix(bundle: dict[str, Any], narrative: dict[str, Any] | None = None) -> dict[str, Any]:
    # A reason the model wrote for a gap that carried none. Keyed by the gap's
    # index so it can only ever land on the row it was written for; a gap the
    # model skipped keeps an empty cell rather than borrowing its neighbour's.
    reasons = (narrative or {}).get("gap_reasons") or {}
    gaps = [
        {
            "item": str(g.get("item") or ""),
            "why": g.get("why") or g.get("rationale") or reasons.get(index),
            "priority_label": severity_label(g.get("priority")),
            "priority_class": severity_class(g.get("priority")),
        }
        for index, g in _reader_facing_gaps(bundle)
    ]
    confidence = [
        {"area": k.replace("_", " ").title(), "level": severity_label(v), "level_class": confidence_class(v)}
        for k, v in (bundle.get("confidence_by_area") or {}).items()
    ]
    return {"gaps": gaps, "confidence": confidence, "sources": [], "manifest": (bundle.get("meta") or {}).get("manifest") or {}}


_CONTENTS = (
    {"no": '1', "title": "Business and revenue model", "question": "What is this and how does it make money?", "page": 3, "anchor": 'sec-1'},
    {"no": '2', "title": "Financial performance", "question": "Is the financial story improving, and is it real?", "page": 4, "anchor": 'sec-2'},
    {"no": '3', "title": "Customer quality and concentration", "question": "Is the revenue durable, and who could take it away?", "page": 5, "anchor": 'sec-3'},
    {"no": '4', "title": "Operating KPIs vs our screens", "question": "Where does this sit against how we screen the sector?", "page": 6, "anchor": 'sec-4'},
    {"no": '5', "title": "Quality of earnings", "question": "Is the EBITDA real?", "page": 7, "anchor": 'sec-5'},
    {"no": '6', "title": "Contract and legal risk", "question": "Anything that changes the price or the close?", "page": 7, "anchor": 'sec-6'},
    {"no": '7', "title": "Forecast and value creation", "question": "Is the plan achievable, and what would we do with it?", "page": 8, "anchor": 'sec-7'},
    {"no": '8', "title": "Risks and what to test first", "question": "What breaks the thesis, and what do we ask on Monday?", "page": 9, "anchor": 'sec-8'},
    {"no": '9', "title": "Minimum Pursuit Score", "question": "Does it clear our own screen?", "page": 10, "anchor": 'sec-9'},
    {"no": '—', "title": "Appendix", "question": "Gaps, confidence, sources, run manifest.", "page": 11, "anchor": 'sec-appendix'},
)


def final_report_view(
    bundle: dict[str, Any],
    narrative: dict[str, Any] | None = None,
    run_mode: str | None = None,
) -> dict[str, Any]:
    """Build the ``report`` context for ``final_report.html.j2``.

    ``narrative`` is the existing Capa B synthesis output (prose bullets,
    thesis, watchouts, analyst takes, recommendation).

    ``run_mode`` is a fact about which branch the caller took (``"cim_only"``
    or the full-data-room branch) and is never re-derived from
    ``bundle.meta`` — ``bundle["meta"]`` carries no ``run_mode`` key today
    (nothing in ``bundle_builder.py`` or ``field_mapping.py`` writes one), so
    without this parameter every report would read "Full data room", CIM-first
    ones included. Falls back to ``meta.get("run_mode")`` when omitted, so the
    function stays usable standalone (e.g. the stakeholder preview).

    This function deliberately knows NOTHING about the MPS. The MPS page
    renders from ``rainmaker_view._mps_table`` — the same projection the
    executive review uses — passed to the template as its own top-level
    ``mps`` key by the caller. Nothing about the score is summarised,
    previewed or restated anywhere else in the report: it appears once, on
    its own page, in the form it already has.
    """
    narrative = narrative or {}
    meta = bundle.get("meta") or {}
    effective_run_mode = run_mode if run_mode is not None else meta.get("run_mode")
    sector = str(meta.get("vertical_overlay") or "tech_services")
    headline = bundle.get("headline_metrics") or {}
    framing = bundle.get("company_framing") or {}

    return {
        "meta": {
            "company_name": str(meta.get("company_name") or "Company"),
            "sector_label": sector.replace("_", " ").title(),
            "prepared_for": "Rallyday Partners",
            "date": str(meta.get("generated_at") or "")[:10],
            "mode_label": "CIM-first" if effective_run_mode == "cim_only" else "Full data room",
            "doc_count": meta.get("doc_count"),
            "overall_confidence": severity_label(meta.get("overall_confidence")),
            "status": str(meta.get("disclaimer_text") or "").strip()
            or "Preliminary — for internal discussion only. Subject to confirmatory diligence.",
            "template_version": "final_report.html.j2 v0.1",
        },
        "contents": list(_CONTENTS),
        "headline": {
            "recommendation": _recommendation(narrative),
            "one_liner": (bundle.get("executive") or {}).get("in_one_line"),
            "tiles": _headline_tiles(headline)[:CAP_TILES],
            "thesis": (narrative.get("thesis_bullets") or (bundle.get("executive") or {}).get("thesis_bullets") or [])[:CAP_THESIS],
            "watchouts": (narrative.get("key_watchouts") or (bundle.get("executive") or {}).get("key_watchouts") or [])[:CAP_WATCHOUTS],
        },
        "business": {
            "core_business": (narrative.get("core_business") or [])[:3],
            "what_it_does": (framing.get("overview_bullets") or [])[:CAP_BULLETS],
            "how_it_makes_money": (narrative.get("business_model") or [])[:CAP_BULLETS],
            "revenue_mix": _mix(bundle, "revenue_type_mix", "Recurring vs project revenue"),
            "client_distribution": _mix(bundle, "client_distribution", "Clients by segment"),
            "performance_by": _performance_by(bundle),
            "take": narrative.get("business_take"),
        },
        "financials": {
            "table": _pnl_table(bundle),
            "trend_chart": _trend_chart(bundle),
            "ebitda_chart": _ebitda_chart(bundle),
            "observations": ((bundle.get("financials") or {}).get("observations") or [])[:CAP_BULLETS],
            "bridge": (bundle.get("financials") or {}).get("growth_bridge") or [],
            "take": narrative.get("financial_take"),
        },
        "customers": {
            "tiles": _customer_tiles(bundle),
            "concentration": _concentration(bundle, sector),
            "retention_rows": _retention_rows(bundle, sector),
            "top_customers": _top_customers(bundle),
            "take": narrative.get("customer_take"),
        },
        "kpis": _kpi_scorecard(bundle, sector, narrative),
        "quality": _quality(bundle, narrative),
        "legal": _legal(bundle),
        "forecast": _forecast(bundle, narrative),
        "risks": _risks(bundle),
        "questions": _questions(bundle),
        "appendix": _appendix(bundle, narrative),
    }


# --- Small builders -------------------------------------------------------

def _headline_tiles(h: dict[str, Any]) -> list[dict[str, Any]]:
    specs = (
        ("Revenue (LTM)", "ltm_revenue", None),
        ("Revenue CAGR", "revenue_cagr", None),
        ("EBITDA (LTM)", "ltm_ebitda", None),
        ("EBITDA margin", "ltm_ebitda_margin_pct", None),
        ("Top customer", "top1_concentration_pct", None),
        ("Indicated EV", "enterprise_value_indicated", None),
    )
    return [{"label": label, "value": h.get(field), "sub": sub, "flag": False} for label, field, sub in specs if h.get(field)]


def _mix(bundle: dict[str, Any], field: str, caption: str) -> dict[str, Any]:
    """100% stacked-bar input. Segments whose share is absent are excluded —
    a mix chart that does not sum is worse than no chart."""
    raw = (bundle.get("revenue_quality") or {}).get(field) or []
    segments = []
    for s in raw:
        if not isinstance(s, dict):
            continue
        pct = parse_percent(s.get("pct_of_revenue") or s.get("pct"))
        if pct is None:
            continue
        segments.append({"label": str(s.get("label") or s.get("category") or ""), "pct": pct, "value": f"{pct:.0f}%"})
    return {"segments": segments[:CAP_SEGMENTS], "caption": caption, "dimension": caption}


def _performance_by(bundle: dict[str, Any]) -> dict[str, Any]:
    """Revenue and gross margin by segment / service line / location. The
    dimension is whatever the agents actually populated — multi-site
    healthcare gives locations, tech services gives practice areas."""
    unit = financial_unit_label(bundle)
    raw = (bundle.get("financials") or {}).get("segment_performance") or []
    rows, revs, margins = [], [], []
    for s in raw[:CAP_SEGMENTS]:
        if not isinstance(s, dict):
            continue
        rev = parse_money(s.get("revenue"))
        gm = parse_percent(s.get("gross_margin_pct"))
        revs.append(rev)
        margins.append(gm)
        rows.append({
            "name": str(s.get("name") or ""),
            "revenue": s.get("revenue"),
            "share": s.get("share_pct"),
            "gross_margin": s.get("gross_margin_pct"),
            "growth": s.get("growth_pct"),
            "read_label": s.get("read_label") or "—",
            "read_class": severity_class(s.get("read")),
        })
    rev_pct = scale(revs)
    return {
        "dimension": (bundle.get("financials") or {}).get("segment_dimension") or "Segment",
        "rows": rows,
        "chart": {
            "series": [
                {
                    "label": rows[i]["name"][:14],
                    "bar1_pct": rev_pct[i], "bar1_value": money_label(revs[i], unit),
                    "bar2_pct": None, "bar2_value": None,
                    "line_pct": None if margins[i] is None else max(0.0, min(100.0, margins[i])),
                    "line_value": None if margins[i] is None else f"{margins[i]:.0f}%",
                }
                for i in range(len(rows))
            ],
            "bar1_name": "Revenue", "bar2_name": None, "line_name": "Gross margin %",
            "axis_max_label": money_label(max([v for v in revs if v is not None] or [0]), unit),
            "footnote": "Segment revenue as extracted; margin line on a 0-100% axis.",
        },
    }


def _customer_tiles(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    rq = bundle.get("revenue_quality") or {}
    conc = rq.get("concentration_summary") or {}
    ret = rq.get("retention") or {}
    specs = (
        ("Clients", rq.get("client_count")),
        ("Top 1", conc.get("top1_pct")),
        ("Top 5", conc.get("top5_pct")),
        ("NRR", ret.get("nrr_pct")),
        ("Avg tenure", (rq.get("customer_tenure") or {}).get("average_tenure_years")),
    )
    return [{"label": label, "value": value, "sub": None, "flag": False} for label, value in specs if value not in (None, "")]


def _retention_rows(bundle: dict[str, Any], sector: str) -> list[dict[str, Any]]:
    ret = (bundle.get("revenue_quality") or {}).get("retention") or {}
    screens = {s["key"]: s for s in _SCREENS if s["sector"] == sector}
    out = []
    for key, label in (("nrr_pct", "Net revenue retention"), ("grr_pct", "Gross revenue retention"),
                       ("logo_churn_rate_annual_pct", "Annual logo churn")):
        value = ret.get(key)
        if value in (None, ""):
            continue
        num = parse_percent(value)
        screen = screens.get(key)
        flag = bool(screen and num is not None and num < screen["threshold"])
        out.append({
            "metric": label, "value": value,
            "read_label": "Below screen" if flag else ("At screen" if screen else "No screen"),
            "read_class": "high" if flag else ("low" if screen else "neutral"),
        })
    return out


def _top_customers(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """Same ranking as the concentration chart beside it — a table that
    disagrees with the chart above it about who the largest account is makes
    the reader check both."""
    return [
        {
            "name": str(c.get("customer_name") or ""),
            "share": c.get("revenue_pct_yr1"),
            "trend": _trunc(c.get("revenue_trend_note"), 34) if c.get("revenue_trend_note") else None,
            "gross_margin": c.get("gm_pct"),
            "contract_status": c.get("contract_status"),
            "tenure": c.get("years_as_customer"),
            "cite": None,
        }
        for c in _ranked_customers(bundle)[:CAP_TOP_CUSTOMERS]
    ]


def _ranked_customers(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """Client records ordered by revenue share, largest first; those without
    a share keep their extraction order after the ranked ones."""
    raw = [c for c in ((bundle.get("revenue_quality") or {}).get("top_customers") or []) if isinstance(c, dict)]
    with_share = [(parse_percent(c.get("revenue_pct_yr1")), c) for c in raw]
    ranked = sorted(
        (pair for pair in with_share if pair[0] is not None), key=lambda p: p[0], reverse=True
    )
    return [c for _, c in ranked] + [c for pct, c in with_share if pct is None]


def _quality(bundle: dict[str, Any], narrative: dict[str, Any]) -> dict[str, Any]:
    """Reported → adjusted EBITDA as horizontal bars: the addback stack made
    visible instead of described. Bars are shares of adjusted EBITDA."""
    qoe = bundle.get("qoe") or {}
    addbacks = [a for a in (qoe.get("addbacks") or []) if isinstance(a, dict)]
    values = [parse_money(a.get("amount")) for a in addbacks]
    total = sum(v for v in values if v is not None) or None
    items = []
    for i, a in enumerate(addbacks[:6]):
        if values[i] is None or not total:
            continue
        items.append({
            "label": _trunc(a.get("label"), 26),
            "value": str(a.get("amount")),
            "value_num": values[i],
            "flag": str(a.get("tier") or "").lower() in {"tier 3", "unsupported", "high"},
        })
    return {
        "addback_bars": {**_axis_bars(items, None), "title": "Addbacks"},
        "addback_caption": f"Addbacks total {qoe.get('addback_pct_of_ebitda') or '—'} of reported EBITDA. {qoe.get('tier_summary') or ''}".strip(),
        "flags": [
            {
                "text": flag_text(f),
                "severity_label": severity_label((f or {}).get("severity") if isinstance(f, dict) else None),
                "severity_class": severity_class((f or {}).get("severity") if isinstance(f, dict) else None),
                "cite": None,
            }
            for f in (qoe.get("flags") or [])[:5]
        ],
        "take": narrative.get("quality_take"),
    }


def _legal_issue_label(flag: Any) -> str:
    """Short human label for a legal flag: the humanised metric, qualified by
    the counterparty when the agent named one."""
    if not isinstance(flag, dict):
        return _trunc(flag, 70)
    label = humanize_metric(flag.get("metric"))
    subject = str(flag.get("value") or "").strip()
    if label and subject:
        return _trunc(f"{label} — {subject}", 70)
    return _trunc(label or subject, 70)


def _legal(bundle: dict[str, Any]) -> dict[str, Any]:
    legal = bundle.get("legal") or {}
    return {
        "tiles": [
            {"label": "Checklist assessed", "value": f"{legal.get('assessed_count', '—')}/{legal.get('checklist_total', 11)}", "flag": False},
            {"label": "CoC consents", "value": legal.get("coc_consent_count") or "—", "flag": bool(legal.get("coc_consent_count"))},
            {"label": "Section confidence", "value": severity_label(legal.get("section_confidence")), "flag": False},
        ],
        "flags": [
            {
                # The issue column names WHAT the flag is about; the impact
                # column carries the sentence. Previously both reached for keys
                # the legal agent does not write ("flag"/"summary") and fell
                # back to the record, printing a dict repr into the table and
                # leaving impact as an em-dash on every row.
                "issue": _legal_issue_label(f),
                "impact": flag_text(f) or "—",
                "severity_label": severity_label((f or {}).get("severity") if isinstance(f, dict) else None),
                "severity_class": severity_class((f or {}).get("severity") if isinstance(f, dict) else None),
                "cite": None,
            }
            for f in (legal.get("top_flags") or [])[:5]
        ],
    }


def _one_scale(raws: list[Any], unit_label: str) -> list[float | None]:
    """A series of money strings resolved onto ONE magnitude.

    ``absolute_revenue`` scales a figure that names its own magnitude and
    leaves a bare one in the table's unit. That is right per figure, but when
    the unit cannot be resolved the two halves of a mixed series land on
    magnitudes 1,000x apart — a bar drawn against an axis it does not share.
    Seen with a bundle whose free-text ``unit_label`` named no unit: three
    periods stated "thousand" rendered in millions beside a bare period
    rendered in thousands, on the same axis.

    With a resolvable unit every figure is comparable. Without one, the bare
    figures are left exactly as extracted and the labelled ones are brought
    back onto their scale, so the axis is internally consistent even though
    its absolute magnitude is unknown.
    """
    multiplier = unit_multiplier(unit_label)
    if multiplier is not None:
        return [absolute_revenue(raw, unit_label) for raw in raws]
    out: list[float | None] = []
    for raw in raws:
        if has_explicit_magnitude(raw):
            dollars = money_to_dollars(raw)
            out.append(None if dollars is None else dollars / 1_000.0)
        else:
            out.append(parse_money(raw))
    return out


def _restates_history(plan_row: dict[str, Any], hist_by_year: dict, unit_label: str) -> bool:
    """True when a plan row is the same year AND the same figure as an actual.

    The forecast agent's revenue build opens with the periods it is building
    FROM, so GKF's 2023A/2024A/2025B arrived in both series and were drawn
    twice, the second time suffixed "P" as though an actual were a projection.

    Matching on the year alone would be too blunt: Clearsulting's plan carries
    a 2025E full-year estimate ($70.1M) alongside a TTM25 actual ($62.6M) —
    same year, genuinely different claims, and the reader needs both. Only a
    row that repeats a figure the history already shows is dropped.
    """
    year = period_sort_key(plan_row.get("year"))
    if year not in hist_by_year:
        return False
    actual = hist_by_year[year]
    planned = absolute_revenue(plan_row.get("revenue"), unit_label)
    if actual is None or planned is None:
        return False
    if actual == 0:
        return planned == 0
    return abs(planned - actual) / abs(actual) <= 0.01


def _forecast(bundle: dict[str, Any], narrative: dict[str, Any]) -> dict[str, Any]:
    """Plan against historical run-rate on the SAME axis maximum as page 4, so
    the step-up the plan assumes is visible rather than asserted."""
    fin = bundle.get("financials") or {}
    hist = ordered_financials(bundle)
    unit = financial_unit_label(bundle, hist)
    # The forecast agent's revenue build opens with the actual periods it is
    # building from, so a plan row often restates a year the history already
    # shows — GKF's 2023A/2024A/2025B appeared twice, the second time suffixed
    # "P" as though the actual were a projection. A restated actual is not a
    # forecast; the historical series already carries it.
    hist_by_year = {
        period_sort_key(r.get("year")): absolute_revenue(r.get("revenue"), unit) for r in hist
    }
    plan = [
        r
        for r in (fin.get("forecast_rows") or [])
        if isinstance(r, dict) and not _restates_history(r, hist_by_year, unit)
    ]
    rows = hist + plan
    revs = _one_scale([r.get("revenue") for r in rows], unit)
    margins = [parse_percent(r.get("ebitda_margin_pct")) for r in rows]
    rev_pct = scale(revs)
    footnote = "Plan periods marked P. Same axis as the historical chart on the financial performance page."
    plan_margins = margins[len(hist):]
    if plan and all(m is None for m in plan_margins):
        # Decision, plan §1.7: nothing in the pipeline projects a plan-period
        # EBITDA margin. Say so as a fact about the plan, not about our
        # tooling — extending the historical margin across the plan periods
        # would invent a management commitment that was never made.
        footnote += " The plan does not state a projected EBITDA margin."
    return {
        "chart": {
            "series": [
                {
                    "label": f"{rows[i].get('year')}{'P' if i >= len(hist) else ''}",
                    "bar1_pct": rev_pct[i], "bar1_value": format_dollars(revs[i]),
                    "bar2_pct": None, "bar2_value": None,
                    "line_pct": None if margins[i] is None else max(0.0, min(100.0, margins[i])),
                    "line_value": None if margins[i] is None else f"{margins[i]:.0f}%",
                }
                for i in range(len(rows))
            ],
            "bar1_name": "Revenue (P = plan)", "bar2_name": None, "line_name": "EBITDA margin %",
            "axis_max_label": format_dollars(max([v for v in revs if v is not None] or [0])),
            "footnote": footnote,
        },
        "assumptions": [
            {"assumption": str(a.get("assumption") or ""), "support_label": assumption_support_label(a.get("support")),
             "support_class": assumption_support_class(a.get("support")), "test": str(a.get("test") or "—")}
            for a in (fin.get("forecast_assumptions") or [])[:5] if isinstance(a, dict)
        ],
        "levers": [
            {"lever": str(l.get("lever") if isinstance(l, dict) else l), "size": (l or {}).get("size") if isinstance(l, dict) else None,
             "owner": (l or {}).get("owner") if isinstance(l, dict) else None}
            for l in ((bundle.get("company_framing") or {}).get("thesis") or {}).get("value_creation_levers", [])[:4]
        ],
        "take": narrative.get("forecast_take"),
    }


def _questions(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """Deduped, capped, and each carrying a "why it matters" line — a question
    without a reason is not usable in a management meeting."""
    out, seen = [], set()
    for q in bundle.get("diligence_questions") or []:
        if not isinstance(q, dict):
            continue
        text = str(q.get("question") or "").strip()
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        out.append({"category": str(q.get("category") or "General"), "question": text, "why": q.get("why_it_matters")})
        if len(out) >= CAP_QUESTIONS:
            break
    return out
