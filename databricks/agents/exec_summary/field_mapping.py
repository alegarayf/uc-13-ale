"""UC13 Orchestrator — Appendix B data-driven field mapping (M2 B1)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from agents.exec_summary.formatters import format_kpi_value

# Appendix B TL;DR rows — data-driven mapping registry (§5.11).
# Stage-3+ rows (risks, gaps, confidence) are listed for coverage; applied elsewhere.


@dataclass(frozen=True)
class FieldMapping:
    bundle_path: str
    agent: str | None
    yaml_json_path: str | None
    transform: str
    required_for_tldr: bool


FIELD_MAPPINGS: list[FieldMapping] = [
    FieldMapping(
        "meta.company_name",
        "param",
        None,
        "meta_company_name",
        True,
    ),
    FieldMapping(
        "meta.vertical_overlay",
        "profiler",
        "industry_overlay",
        "profile_field",
        True,
    ),
    FieldMapping(
        "executive.in_one_line",
        "business_model",
        "executive_summary",
        "executive_in_one_line",
        True,
    ),
    FieldMapping(
        "headline_metrics.ltm_revenue",
        "financial_trends",
        "revenue_trend",
        "headline_ltm_revenue",
        True,
    ),
    FieldMapping(
        "headline_metrics.ltm_ebitda_margin_pct",
        "financial_trends",
        "ebitda",
        "headline_ltm_ebitda_margin",
        True,
    ),
    FieldMapping(
        "headline_metrics.revenue_cagr",
        "financial_trends",
        "revenue_trend",
        "headline_revenue_cagr",
        True,
    ),
    FieldMapping(
        "company_framing.revenue_model.quality_flag",
        "business_model",
        "revenue_model.durability_rating",
        "bma_quality_flag",
        True,
    ),
    FieldMapping(
        "financials.table_rows",
        "financial_trends",
        "revenue_trend,ebitda,gross_margin",
        "fta_table_rows",
        True,
    ),
    FieldMapping(
        "revenue_quality.concentration",
        "customer_quality",
        "customer_concentration",
        "cqa_concentration",
        True,
    ),
    FieldMapping(
        "kpi_dashboard[]",
        "kpi",
        "overlay_kpis",
        "kpi_dashboard_rows",
        True,
    ),
    FieldMapping(
        "legal.assessed_count",
        "legal",
        "delta:unable_to_assess_json",
        "legal_assessed_count",
        True,
    ),
    FieldMapping(
        "risks[]",
        "all",
        "delta:flags",
        "merge_risks_from_flags",
        True,
    ),
    FieldMapping(
        "diligence_questions[]",
        "legal",
        "delta:recommended_diligence_json",
        "build_diligence_questions",
        True,
    ),
    FieldMapping(
        "data_room_gaps[]",
        "all",
        "delta:data_room_gaps",
        "merge_data_room_gaps",
        True,
    ),
    FieldMapping(
        "confidence_by_area",
        "confidence_engine",
        None,
        "confidence_engine",
        True,
    ),
    FieldMapping(
        "company_framing.thesis.bullets",
        None,
        None,
        "not_attempted",
        True,
    ),
    FieldMapping(
        "headline_metrics.*",
        None,
        None,
        "not_attempted",
        True,
    ),
]

_SEVERITY_ORDER = {"Red": 0, "Yellow": 1, "Green": 2}


def _parse_json_column(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, (list, dict)):
        return raw
    if isinstance(raw, str):
        return json.loads(raw or "null")
    return raw


def _flag_sort_key(flag: dict) -> tuple:
    sev = _SEVERITY_ORDER.get(flag.get("severity", "Green"), 9)
    return (sev, flag.get("metric") or "", flag.get("note") or "")


# EBITDA version preference when a period has more than one version record
# (mirrors the 3-version cap documented for EbitdaSubAgent).
#
# RETAINED, but its role changed: since the reported/PF-adjusted split it is no
# longer a single collapse order for "the" EBITDA figure. It survives as the
# *non-PF* fallback order consulted by ``_reported_ebitda_by_period`` only —
# an explicit ``reported`` record always wins that column outright, and
# ``pf_adjusted`` is excluded from it entirely so the two series can never
# carry the same record. ``_pf_adjusted_ebitda_by_period`` does not consult it
# at all. The tuple keeps ``pf_adjusted`` at index 0 so
# ``_ebitda_version_rank`` still reports a stable rank for every known version.
_EBITDA_VERSION_PRIORITY = ("pf_adjusted", "clinic_level_adjusted", "reported")


def _has_numeric_signal(record: dict, *field_names: str) -> bool:
    """True when at least one of the named fields carries a real value.

    General-purpose filter, not tied to any specific label or sentinel
    string: the extraction sub-agents occasionally append a non-data record
    to one of these arrays instead of using the dedicated
    discrepancy-flagging path (e.g. a "period": "DISCREPANCY_FLAG" note with
    every numeric field null) — this is what catches that, for any company,
    without matching on the exact text of the note.
    """
    return any(record.get(f) not in (None, "", "null") for f in field_names)


def _ebitda_version_rank(record: dict) -> int:
    version = str(record.get("version") or "").strip().lower()
    try:
        return _EBITDA_VERSION_PRIORITY.index(version)
    except ValueError:
        return len(_EBITDA_VERSION_PRIORITY)


def _reported_ebitda_by_period(ebitda_rows: list) -> dict[str, dict]:
    """The *reported* EBITDA record per period — one half of the two disjoint
    EBITDA series the bundle now carries.

    Supersedes the former ``_canonical_ebitda_by_period``, which collapsed
    every version FTA emits for a period into a single "best available"
    record, preferring ``pf_adjusted``. That collapse made the earnings-quality
    gap — the whole point of the reported-vs-adjusted comparison — render as
    zero, because one figure was shown under both the "Reported EBITDA" and
    "Adjusted EBITDA" labels.

    Selection (never falls back to ``pf_adjusted``, so this series and
    ``_pf_adjusted_ebitda_by_period`` can never carry the same record):

    1. An explicit ``version == "reported"`` record always wins.
    2. Otherwise the best available **non-PF** record by
       ``_EBITDA_VERSION_PRIORITY`` — ``clinic_level_adjusted``, then an
       unversioned / unknown-version record. Keeping unversioned records
       eligible matters: a weak extraction that tags no version at all would
       otherwise empty this column entirely under a strict
       ``version == "reported"`` filter.
    3. A period whose only record is ``pf_adjusted`` is absent from this map,
       so its reported cell renders empty. Empty is the honest state — this
       mapper never invents a missing dollar figure.

    Both of the guards the collapse carried survive here and in the PF
    function: the ``_has_numeric_signal`` non-data-record filter, and the
    period/label derivation with an empty-period skip.
    """

    def rank(record: dict) -> int:
        if str(record.get("version") or "").strip().lower() == "reported":
            # An explicitly reported record outranks every fallback candidate.
            return -1
        return _ebitda_version_rank(record)

    by_period: dict[str, dict] = {}
    for r in ebitda_rows:
        if not isinstance(r, dict):
            continue
        if str(r.get("version") or "").strip().lower() == "pf_adjusted":
            continue
        if not _has_numeric_signal(r, "ebitda_dollars", "ebitda_margin_pct"):
            continue
        period = str(r.get("period", r.get("label", "")))
        if not period:
            continue
        existing = by_period.get(period)
        if existing is None or rank(r) < rank(existing):
            by_period[period] = r
    return by_period


def _pf_adjusted_ebitda_by_period(ebitda_rows: list) -> dict[str, dict]:
    """The ``pf_adjusted`` EBITDA record per period — the other half of the
    two disjoint series.

    ``version == "pf_adjusted"`` **only**: no fallback of any kind, so this
    column is never a copy of the reported figure and never silently picks up
    a ``clinic_level_adjusted`` or unversioned record. Absent ⇒ the period is
    missing from this map and the adjusted cell renders empty. Duplicate PF
    records for one period keep the first seen, matching the
    ``revenue_trend``/gross-margin duplicate rules elsewhere in this module.
    """
    by_period: dict[str, dict] = {}
    for r in ebitda_rows:
        if not isinstance(r, dict):
            continue
        if str(r.get("version") or "").strip().lower() != "pf_adjusted":
            continue
        if not _has_numeric_signal(r, "ebitda_dollars", "ebitda_margin_pct"):
            continue
        period = str(r.get("period", r.get("label", "")))
        if not period or period in by_period:
            continue
        by_period[period] = r
    return by_period


def _is_segment_qualified_label(label: str) -> bool:
    """True for a segment/location breakdown label like "Gross Profit
    (Westchester)" as opposed to the plain company-wide "Gross Profit".
    Keys off the label's SHAPE (a parenthetical qualifier), never a specific
    city/segment name, so this generalizes to any company's geography or
    service-line breakdown."""
    return "(" in (label or "")


def _canonical_gross_margin_by_period(gross_margin_rows: list) -> dict[str, dict]:
    """One gross_margin record per period, preferring the plain company-wide
    label over any segment/location-qualified one.

    ``gross_margin`` has no dedicated segment array the way ``revenue_by_segment``
    does, so a sub-agent extracting a multi-location P&L sometimes appends
    each location's Gross Profit to this same array under a suffixed label
    ("Gross Profit (Westchester)", "Gross Profit (Long Island)", ...). A plain
    last-record-wins pick then silently replaces the consolidated company
    figure with whichever location happens to be extracted last — confirmed
    on a real run: Elder Care's rendered 2023A/TTM Aug-24 gross margin was
    New Jersey's sub-total (45.6%), not the company's (43.6%/43.4%), because
    "Gross Profit (New Jersey)" was the last entry for those periods.
    """
    by_period: dict[str, dict] = {}
    for r in gross_margin_rows:
        if not isinstance(r, dict):
            continue
        if not _has_numeric_signal(r, "gm_dollars_stated", "gm_pct_stated"):
            continue
        period = str(r.get("period") or "")
        if not period:
            continue
        existing = by_period.get(period)
        if existing is None:
            by_period[period] = r
            continue
        existing_is_segment = _is_segment_qualified_label(str(existing.get("label") or ""))
        candidate_is_segment = _is_segment_qualified_label(str(r.get("label") or ""))
        if existing_is_segment and not candidate_is_segment:
            # The consolidated (unqualified) label always wins over a
            # segment/location breakdown, regardless of array order.
            by_period[period] = r
        # Otherwise keep the existing record: it's already unqualified (a
        # segment breakdown must never overwrite it), or both share the same
        # qualified/unqualified status (keep first-seen — stable, and matches
        # revenue_trend's own "keep the first" duplicate-period rule below).
    return by_period


def _periods_with_real_data(
    revenue_trend: list, gm_by_period: dict, ebitda_by_period: dict,
) -> set[str]:
    """Periods with at least one real numeric value in revenue, gross
    margin, or EBITDA — a period sparse in one array but populated in
    another (e.g. no revenue_stated but a real gm_pct_stated) is still real
    and must not be dropped. ``gm_by_period``/``ebitda_by_period`` are
    already filtered to real data by their own canonical-selection
    functions, so their keys alone cover those two sources; only
    ``revenue_trend`` needs an explicit check here.
    """
    valid: set[str] = set(gm_by_period) | set(ebitda_by_period)
    for rev in revenue_trend:
        if not isinstance(rev, dict):
            continue
        if not _has_numeric_signal(rev, "revenue_stated", "revenue", "value", "yoy_growth_pct"):
            continue
        period = str(rev.get("period") or rev.get("label") or "")
        if period:
            valid.add(period)
    return valid


def _fta_table_rows(fta_yaml: dict | None) -> list[dict[str, str]]:
    if not fta_yaml:
        return []
    revenue_trend = fta_yaml.get("revenue_trend") or []
    ebitda_rows = fta_yaml.get("ebitda") or []
    gross_margin = fta_yaml.get("gross_margin") or []
    reported_ebitda_by_period = _reported_ebitda_by_period(ebitda_rows)
    pf_ebitda_by_period = _pf_adjusted_ebitda_by_period(ebitda_rows)
    gm_by_period = _canonical_gross_margin_by_period(gross_margin)
    # A period with real data ANYWHERE across the three sources is genuine.
    # Filters out a non-data record a sub-agent sometimes appends inline
    # instead of using the dedicated discrepancy-flagging path (e.g. a
    # "period": "DISCREPANCY_FLAG" note, every numeric field null, with no
    # companion entry in gross_margin/ebitda either) — without this, it
    # becomes a phantom empty column in both the P&L table and the
    # Financial Snapshot chart.
    # Period genuineness must consider BOTH EBITDA series. Passing only the
    # reported map is the natural-looking refactor and it silently deletes
    # rows: a period whose only EBITDA record is pf_adjusted would be judged
    # unreal and vanish from the table entirely.
    real_periods = _periods_with_real_data(
        revenue_trend,
        gm_by_period,
        {**reported_ebitda_by_period, **pf_ebitda_by_period},
    )
    rows: list[dict[str, str]] = []
    seen_periods: set[str] = set()
    for rev in revenue_trend:
        if not isinstance(rev, dict):
            continue
        period = str(rev.get("period") or rev.get("label") or "")
        if not period or period in seen_periods or period not in real_periods:
            # Fix B0 — revenue_trend can carry duplicate records for the same
            # period (e.g. from multiple source documents); keep the first.
            continue
        seen_periods.add(period)
        ebitda = reported_ebitda_by_period.get(period, {})
        adjusted_ebitda = pf_ebitda_by_period.get(period, {})
        gm = gm_by_period.get(period, {})
        rows.append(
            {
                "year": period,
                "revenue": str(
                    rev.get("revenue_stated") or rev.get("revenue") or rev.get("value") or ""
                ),
                "gross_profit": str(
                    gm.get("gm_dollars_stated") or gm.get("gross_profit") or ""
                ),
                "gross_margin_pct": str(
                    gm.get("gm_pct_stated") or gm.get("gross_margin_pct") or ""
                ),
                "ebitda": str(
                    ebitda.get("ebitda_dollars") or ebitda.get("ebitda") or ebitda.get("value") or ""
                ),
                "ebitda_margin_pct": str(
                    ebitda.get("ebitda_margin_pct") or ebitda.get("margin_pct") or ""
                ),
                # Same extraction idiom against the pf_adjusted record. Empty
                # when FTA extracted no pf_adjusted version for this period —
                # never a copy of the reported figure.
                "adjusted_ebitda": str(
                    adjusted_ebitda.get("ebitda_dollars")
                    or adjusted_ebitda.get("ebitda")
                    or adjusted_ebitda.get("value")
                    or ""
                ),
                "adjusted_ebitda_margin_pct": str(
                    adjusted_ebitda.get("ebitda_margin_pct")
                    or adjusted_ebitda.get("margin_pct")
                    or ""
                ),
            }
        )
    return rows


def _headline_from_fta(fta_yaml: dict | None) -> dict[str, str | None]:
    empty = {
        "ltm_revenue": "",
        "ltm_ebitda": "",
        "ltm_ebitda_margin_pct": "",
        "ltm_adjusted_ebitda": "",
        "revenue_cagr": "",
        "enterprise_value_indicated": None,
        "rule_of_40": None,
    }
    if not fta_yaml:
        return empty
    revenue_trend = fta_yaml.get("revenue_trend") or []
    ebitda_rows = fta_yaml.get("ebitda") or []
    if revenue_trend:
        latest = revenue_trend[-1] if isinstance(revenue_trend[-1], dict) else {}
        empty["ltm_revenue"] = str(
            latest.get("revenue_stated") or latest.get("revenue") or latest.get("value") or ""
        )
        yoy_values = [
            r.get("yoy_growth_pct")
            for r in revenue_trend
            if isinstance(r, dict) and r.get("yoy_growth_pct")
        ]
        if yoy_values:
            empty["revenue_cagr"] = str(yoy_values[-1])
    if ebitda_rows:
        last_raw = ebitda_rows[-1] if isinstance(ebitda_rows[-1], dict) else {}
        last_period = str(last_raw.get("period", ""))
        # Same latest-period derivation as before; what changed is that the
        # period now resolves against TWO disjoint series. ltm_ebitda is the
        # reported figure, ltm_adjusted_ebitda the pf_adjusted one, for that
        # same period — so the headline can no longer show one number under
        # both meanings.
        latest_e = _reported_ebitda_by_period(ebitda_rows).get(last_period)
        latest_pf = _pf_adjusted_ebitda_by_period(ebitda_rows).get(last_period)
        if (
            latest_e is None
            and latest_pf is None
            and str(last_raw.get("version") or "").strip().lower() != "pf_adjusted"
        ):
            # Retained legacy fallback for a last record neither map keyed
            # (e.g. a label-derived period). Deliberately NOT applied to a
            # pf_adjusted record: that would put the adjusted figure back
            # under the reported label, which is the defect this split fixes.
            latest_e = last_raw
        if latest_e:
            empty["ltm_ebitda"] = str(
                latest_e.get("ebitda_dollars")
                or latest_e.get("ebitda")
                or latest_e.get("value")
                or ""
            )
            empty["ltm_ebitda_margin_pct"] = str(
                latest_e.get("ebitda_margin_pct") or latest_e.get("margin_pct") or ""
            )
        if latest_pf:
            empty["ltm_adjusted_ebitda"] = str(
                latest_pf.get("ebitda_dollars")
                or latest_pf.get("ebitda")
                or latest_pf.get("value")
                or ""
            )
    return empty


def _workforce_notes_from_bma(bma_yaml: dict) -> str | None:
    """Stage-6 read-only context from BMA workforce_capacity (aggregate + per-function)."""
    wfc = bma_yaml.get("workforce_capacity") or {}
    if not isinstance(wfc, dict):
        return None

    parts: list[str] = []

    wf_model = wfc.get("workforce_model") or {}
    if isinstance(wf_model, dict):
        offshore_hc = str(wf_model.get("offshore_or_contract_headcount") or "").strip()
        offshore_pct = str(wf_model.get("offshore_pct_of_total") or "").strip()
        if offshore_hc or offshore_pct:
            agg: list[str] = []
            if offshore_hc:
                agg.append(f"offshore/contract headcount {offshore_hc}")
            if offshore_pct:
                agg.append(f"offshore {offshore_pct} of total")
            parts.append("Aggregate workforce model: " + ", ".join(agg) + ".")

    hbf = wfc.get("headcount_by_function") or []
    if isinstance(hbf, list):
        by_function: list[str] = []
        for row in hbf:
            if not isinstance(row, dict):
                continue
            func = str(row.get("function") or "").strip()
            headcount = str(row.get("headcount") or "").strip()
            location_type = str(row.get("location_type") or "").strip()
            if not func and not location_type:
                continue
            label = func or "Unknown function"
            if headcount and location_type:
                by_function.append(f"{label} {headcount} {location_type}")
            elif location_type:
                by_function.append(f"{label} ({location_type})")
            elif headcount:
                by_function.append(f"{label} {headcount}")
        if by_function:
            parts.append("Headcount by function: " + "; ".join(by_function) + ".")

    if not parts:
        return None
    return " ".join(parts)


# BMA ``key_dependencies[].dependency_type`` values that describe a commercial
# relationship the investment team would want named (a BlackLine/Workiva-style
# partnership), as opposed to an internal dependency on a person, a team, a
# geography or a single customer. The agent's own vocabulary — not a
# per-company literal, so this generalizes across verticals.
_PARTNER_DEPENDENCY_TYPES = frozenset({"partner", "platform", "channel", "vendor"})
_KEY_PARTNER_CAP = 6


def _key_partners_from_bma(bma_yaml: dict) -> list[dict[str, str]]:
    """Named partner/platform/channel relationships already extracted by the
    Business Model agent. Deduped by name (case-insensitive), capped — never
    a new extraction, just a field the bundle was dropping on the floor."""
    partners: list[dict[str, str]] = []
    seen: set[str] = set()
    for dependency in bma_yaml.get("key_dependencies") or []:
        if not isinstance(dependency, dict):
            continue
        if str(dependency.get("dependency_type") or "").strip().lower() not in _PARTNER_DEPENDENCY_TYPES:
            continue
        name = str(dependency.get("name") or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        partner = {
            "name": name,
            "relationship_type": str(dependency.get("dependency_type") or "").strip(),
        }
        description = str(dependency.get("description") or "").strip()
        if description:
            partner["description"] = description
        partners.append(partner)
        if len(partners) >= _KEY_PARTNER_CAP:
            break
    return partners


def _sale_process_from_profile(profile: dict[str, Any]) -> str | None:
    """How the company reached the market. Prefers the profiler's own
    ``sale_process`` (which names the sell-side advisor when the CIM does);
    falls back to its banked flag, which at least says whether this is a
    banker-run process at all."""
    stated = str(profile.get("sale_process") or "").strip()
    if stated and stated.lower() not in ("null", "none", "unknown"):
        return stated
    if profile.get("banked") is True:
        note = str(profile.get("banked_note") or "").strip()
        return f"Banker-run process; advisor not named in the data room. {note}".strip()
    return None


def _company_framing_from_bma(
    bma_yaml: dict | None, profile: dict[str, Any] | None = None
) -> dict[str, Any]:
    profile = profile or {}
    business_description = str(profile.get("business_description") or "").strip() or None
    sale_process = _sale_process_from_profile(profile)

    empty_framing: dict[str, Any] = {
        "overview_bullets": [],
        "revenue_model": {"tag": "", "quality_flag": "", "note": ""},
        "recent_changes": [],
        "thesis": {"bullets": [], "value_creation_levers": []},
        "business_description": business_description,
        "sale_process": sale_process,
        "key_partners": [],
    }
    if not bma_yaml:
        return empty_framing
    rev = bma_yaml.get("revenue_model") or {}
    exec_summary = bma_yaml.get("executive_summary") or ""
    bullets = [exec_summary] if exec_summary else []
    products = bma_yaml.get("products_and_services") or []
    if isinstance(products, list):
        bullets.extend(
            str(p.get("name") or p) for p in products[:3] if isinstance(p, dict)
        )
    framing: dict[str, Any] = {
        "overview_bullets": bullets[:5],
        "revenue_model": {
            "tag": str(rev.get("tag") or ""),
            "quality_flag": str(rev.get("durability_rating") or rev.get("quality_flag") or ""),
            "note": str(rev.get("note") or ""),
        },
        "recent_changes": bma_yaml.get("recent_model_changes") or [],
        "thesis": {"bullets": [], "value_creation_levers": []},
        "business_description": business_description,
        "sale_process": sale_process,
        "key_partners": _key_partners_from_bma(bma_yaml),
    }
    workforce_notes = _workforce_notes_from_bma(bma_yaml)
    if workforce_notes:
        framing["workforce_notes"] = workforce_notes
    return framing


def _concentration_note_from_cqa(cqa_yaml: dict) -> str:
    """``customer_quality_agent`` writes its report as ``concentration_summary``
    (top1_pct/top3_pct/top5_pct/top10_pct + source_doc) — not
    ``customer_concentration``/``concentration``/``summary``/``top_customer_pct``,
    which is what this used to look for and is why it always came back empty."""
    conc = cqa_yaml.get("concentration_summary") or {}
    if not isinstance(conc, dict):
        return str(conc) if conc else ""
    parts = []
    for key, label in (
        ("top1_pct", "Top 1"), ("top3_pct", "Top 3"), ("top5_pct", "Top 5"), ("top10_pct", "Top 10"),
    ):
        value = conc.get(key)
        if value not in (None, ""):
            parts.append(f"{label}: {value}%")
    return ", ".join(parts) + " of revenue" if parts else ""


def _retention_note_from_cqa(cqa_yaml: dict) -> str:
    """Combines ``retention`` (nrr_pct/grr_pct/logo_churn_rate_annual_pct —
    the SaaS-shaped fields) and ``customer_tenure`` (average_tenure_years /
    tenure_distribution_note — what a non-subscription business like a home
    care platform actually reports) into one note. Whichever the agent
    populated for THIS company's data room is what shows up; nothing here is
    vertical-specific."""
    parts: list[str] = []
    retention = cqa_yaml.get("retention") or {}
    if isinstance(retention, dict):
        if retention.get("nrr_pct") not in (None, ""):
            parts.append(f"NRR {retention['nrr_pct']}%")
        if retention.get("grr_pct") not in (None, ""):
            parts.append(f"GRR {retention['grr_pct']}%")
        if retention.get("logo_churn_rate_annual_pct") not in (None, ""):
            parts.append(f"Annual logo churn {retention['logo_churn_rate_annual_pct']}%")
    tenure = cqa_yaml.get("customer_tenure") or {}
    if isinstance(tenure, dict):
        if tenure.get("average_tenure_years") not in (None, ""):
            parts.append(f"Average tenure {tenure['average_tenure_years']} years")
        if tenure.get("tenure_distribution_note"):
            parts.append(str(tenure["tenure_distribution_note"]))
    return " ".join(parts)


def _end_market_mix_note_from_cqa(cqa_yaml: dict) -> str:
    """``payor_mix`` (who pays — Medicare/Medicaid/Commercial/private-pay/etc.)
    is the closest end-market-style split CQA extracts today. Left blank when
    the agent found nothing here — the KPI-based fallback below covers most
    of the real gap this leaves; this never fabricates a mix that wasn't
    extracted."""
    payor_mix = cqa_yaml.get("payor_mix") or []
    if not isinstance(payor_mix, list):
        return ""
    parts = [
        f"{row.get('payor_category')}: {row['pct_of_revenue']}%"
        for row in payor_mix
        if isinstance(row, dict) and row.get("payor_category") and row.get("pct_of_revenue") not in (None, "")
    ]
    return ", ".join(parts)


# kpi_agent writes ONE of these overlay blocks per company (whichever overlay
# was confirmed) — same detection order _kpi_rows_from_yaml already uses.
# Each overlay's own schema already carries a market/geography/channel-style
# field and, for some overlays, a concentration-style field — this just wires
# those into revenue_quality as a fallback when CQA itself found nothing,
# instead of adding a new field or a new extraction path. A blank overlay or
# an overlay with no such field (b2b_saas, industrial — neither schema has
# a geography/channel concept) stays blank; genuinely nothing to report.
_KPI_OVERLAY_BLOCKS: tuple[str, ...] = (
    "healthcare_kpis", "tech_services_kpis", "saas_kpis", "industrial_kpis", "consumer_kpis",
)
_KPI_END_MARKET_MIX_FIELD: dict[str, str] = {
    "healthcare_kpis": "census_or_patient_panel",   # e.g. "1,186 clients ... NYC: 331, Westchester: 259, ..."
    "tech_services_kpis": "delivery_geography_note",
    "consumer_kpis": "channel_mix_note",
}
_KPI_CONCENTRATION_FIELD: dict[str, str] = {
    "healthcare_kpis": "referral_source_breakdown",
    "consumer_kpis": "platform_concentration_note",
}


# The confirmed-overlay names that reach us (company_profile.industry_overlay,
# kpi.overlay_confirmed) are not the block names — "healthcare_services" is the
# block "healthcare_kpis". Mapped explicitly rather than by string surgery so an
# unrecognised overlay falls through to the content-based pick below instead of
# silently resolving to a block that does not exist.
_OVERLAY_TO_KPI_BLOCK: dict[str, str] = {
    "healthcare": "healthcare_kpis",
    "healthcare_services": "healthcare_kpis",
    "tech_services": "tech_services_kpis",
    "b2b_saas": "saas_kpis",
    "saas": "saas_kpis",
    "industrial": "industrial_kpis",
    "consumer": "consumer_kpis",
}


def _block_content_score(blob: Any) -> int:
    """How many fields the agent actually filled in this overlay block.

    ``kpi_agent`` writes ALL five overlay blocks on every run and populates
    only the confirmed one — the other four are full-length records of nulls.
    A plain truthiness test therefore matches the first block in declaration
    order rather than the company's real overlay, which is why a tech-services
    company rendered a 706-character all-null healthcare stub instead of its
    own 12KB of KPIs. Counting filled fields is what distinguishes them.
    """
    if not isinstance(blob, dict):
        return 0
    return sum(
        1
        for key, value in blob.items()
        if key != "source_doc" and value not in (None, "", "null", [], {}, "false")
    )


def _kpi_overlay_block(
    kpi_yaml: dict, overlay_hint: str = "",
) -> tuple[str, dict] | tuple[None, None]:
    """Pick the overlay block this company's KPIs actually live in.

    Preference order: the confirmed overlay when we were given one and it
    carries content, then whichever block has the most filled fields. Falling
    back on content rather than on declaration order means a company whose
    profile overlay is missing or unrecognised still gets its own KPIs.
    """
    hinted = _OVERLAY_TO_KPI_BLOCK.get(str(overlay_hint or "").strip().lower())
    if hinted and _block_content_score(kpi_yaml.get(hinted)):
        return hinted, kpi_yaml.get(hinted) or {}
    best_key, best_score = None, 0
    for key in _KPI_OVERLAY_BLOCKS:
        score = _block_content_score(kpi_yaml.get(key))
        if score > best_score:
            best_key, best_score = key, score
    if best_key is None:
        return None, None
    return best_key, kpi_yaml.get(best_key) or {}


def _note_from_kpi_field(
    kpi_yaml: dict | None, field_by_overlay: dict[str, str], overlay_hint: str = "",
) -> str:
    if not kpi_yaml:
        return ""
    overlay_key, blob = _kpi_overlay_block(kpi_yaml, overlay_hint)
    if not overlay_key:
        return ""
    field = field_by_overlay.get(overlay_key)
    if not field:
        return ""  # this overlay's schema has no analog field — genuinely nothing to report
    value = blob.get(field)
    return str(value) if value not in (None, "", "null") else ""


def _revenue_quality_from_agents(
    bma_yaml: dict | None,
    cqa_yaml: dict | None,
    kpi_yaml: dict | None = None,
    overlay_hint: str = "",
    fta_yaml: dict | None = None,
) -> dict[str, Any]:
    concentration = ""
    retention_notes = ""
    end_market_mix = ""
    if cqa_yaml:
        concentration = _concentration_note_from_cqa(cqa_yaml)
        retention_notes = _retention_note_from_cqa(cqa_yaml)
        end_market_mix = _end_market_mix_note_from_cqa(cqa_yaml)
    # KPI fallback: only when CQA's own field came back blank for THIS
    # company (a real gap or an overlay CQA doesn't cover well), never a
    # second opinion overriding a value CQA already gave.
    if not concentration:
        concentration = _note_from_kpi_field(kpi_yaml, _KPI_CONCENTRATION_FIELD, overlay_hint)
    if not end_market_mix:
        end_market_mix = _note_from_kpi_field(kpi_yaml, _KPI_END_MARKET_MIX_FIELD, overlay_hint)
    scale = ""
    if bma_yaml and bma_yaml.get("executive_summary"):
        scale = str(bma_yaml["executive_summary"])[:500]
    return {
        "scale_narrative": scale,
        "concentration": concentration,
        "end_market_mix": end_market_mix,
        "retention_notes": retention_notes,
        # Structured passthrough. The prose notes above summarise these for the
        # one-pager; the final report's charts and tiles read the structured
        # shapes directly (final_report_view._top_customers / _retention_rows /
        # _customer_tiles), and until this passthrough existed they read keys
        # this mapper never produced — so every company rendered "not
        # extracted" over a populated CQA row. Field names are CQA's own; the
        # view was already written against them.
        **_with_derived_shares(_cqa_structured_passthrough(cqa_yaml), fta_yaml),
    }


def _with_derived_shares(passthrough: dict[str, Any], fta_yaml: dict | None) -> dict[str, Any]:
    """Enrich the passed-through client list with computed shares, if any."""
    customers = passthrough.get("top_customers")
    if not customers:
        return passthrough
    enriched, note = _derive_customer_shares(customers, fta_yaml)
    out = {**passthrough, "top_customers": enriched}
    if note:
        out["concentration_basis_note"] = note
    return out


_CQA_PASSTHROUGH_KEYS: tuple[tuple[str, str, type], ...] = (
    ("top_customers", "top_customers", list),
    ("concentration_summary", "concentration_summary", dict),
    ("retention", "retention", dict),
    ("customer_tenure", "customer_tenure", dict),
)


def _cqa_structured_passthrough(cqa_yaml: dict | None) -> dict[str, Any]:
    """Copy CQA's structured blocks onto ``revenue_quality`` under their own
    names, keeping only values of the shape the view expects.

    Deliberately a copy, not a transform: every consumer downstream already
    speaks CQA's field vocabulary, so reshaping here would create a second
    schema to keep in sync. A block the agent left null stays absent rather
    than becoming an empty dict, so ``or {}`` guards downstream still read as
    "the agent found nothing" instead of "the agent returned a blank record".
    """
    if not isinstance(cqa_yaml, dict):
        return {}
    out: dict[str, Any] = {}
    for dest, src, kind in _CQA_PASSTHROUGH_KEYS:
        value = cqa_yaml.get(src)
        if isinstance(value, kind) and value:
            out[dest] = value
    return out


_PERIOD_YEAR4_RE = re.compile(r"(?:19|20)\d{2}")
# Not \b-delimited: "FY23" has no word boundary between "Y" and "2".
_PERIOD_YEAR2_RE = re.compile(r"(?<!\d)(\d{2})(?!\d)")


def period_sort_key(period: Any) -> tuple[int, int]:
    """Order period labels chronologically across the shapes the agents emit.

    Extraction labels are not uniform — the same run yields "2020A", "FY23",
    "2025B", "TTM Aug-24", "2027PP". Sorting them as plain strings puts "TTM
    Aug-24" after "2024A" but before "2020A", which is how a trailing period
    ended up drawn between historical years. Two-digit years are read as
    20xx; a label with no year at all sorts last, since in practice that is a
    projection or a note rather than a dated actual.
    """
    text = str(period or "")
    match = _PERIOD_YEAR4_RE.search(text)
    if match:
        return (0, int(match.group(0)))
    # Two-digit years are everywhere in these labels ("FY23", "TTM Aug-24")
    # and are the reason a trailing period sorted after every projection.
    match = _PERIOD_YEAR2_RE.search(text)
    if match:
        return (0, 2000 + int(match.group(1)))
    return (1, 0)


def _latest_by_segment(rows: list) -> list[dict]:
    """Collapse FTA's segment × period records to one row per segment.

    ``revenue_by_segment`` carries a record per segment per period (Elder
    Care: five locations × five periods). ``_performance_by`` renders one row
    per segment, so the most recent period is what it should show. Ties and
    unparseable labels fall back to document order, which is the agents'
    chronological emission order.
    """
    latest: dict[str, tuple[tuple[int, int], int, dict]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        name = str(row.get("segment") or row.get("name") or "").strip()
        if not name:
            continue
        rank = (period_sort_key(row.get("period")), index)
        current = latest.get(name)
        if current is None or rank > (current[0], current[1]):
            latest[name] = (rank[0], index, row)
    return [entry[2] for entry in latest.values()]


def _segment_performance_from_fta(fta_yaml: dict | None) -> list[dict[str, Any]]:
    """Map ``revenue_by_segment`` onto the shape ``_performance_by`` reads.

    The final report's segment section reads ``financials.segment_performance``
    and this mapper only ever wrote ``financials.geographic_mix``, so the
    section rendered "not extracted" for every company — including Elder Care,
    whose agent had extracted five locations across five periods with dollar
    revenue on each. A segment carrying neither a dollar figure nor a share is
    dropped rather than rendered as a bar of unknown height: GKF's single
    segment row has both null, and an empty section is the honest output there.
    """
    raw = (fta_yaml or {}).get("revenue_by_segment") or []
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for row in _latest_by_segment(raw):
        revenue = row.get("revenue_dollars")
        share = row.get("revenue_pct")
        if revenue in (None, "", "null") and share in (None, "", "null"):
            continue
        out.append(
            {
                "name": str(row.get("segment") or row.get("name") or ""),
                "revenue": revenue,
                "share_pct": share,
                "gross_margin_pct": row.get("gross_margin_pct"),
                "growth_pct": row.get("growth_pct"),
                "period": row.get("period"),
            }
        )
    return out


_MAGNITUDE_WORDS: tuple[tuple[str, float], ...] = (
    ("billion", 1_000_000_000.0),
    ("bn", 1_000_000_000.0),
    ("million", 1_000_000.0),
    ("mm", 1_000_000.0),
    ("thousand", 1_000.0),
    ("k", 1_000.0),
)
_NUMBER_RE = re.compile(r"-?\d[\d,]*\.?\d*")


def money_to_dollars(value: Any) -> float | None:
    """Absolute dollars from a money string, honouring a SPELLED-OUT magnitude.

    Distinct from ``final_report_view.parse_money``, which returns the figure
    in whatever unit the chart axis is already working in and only knows the
    ``k``/``bn`` suffixes. Extraction writes magnitude as a word at least as
    often — "$59,699 thousand" alongside a per-client "$10,917,799" — and
    comparing those two as bare numbers is off by 1000x. That is the same
    class of error as a chart labelling $40,251 thousand as "40251.4bn": a
    magnitude carried in text and dropped by the parser.

    A bare number is returned at face value; the caller is responsible for
    deciding whether an unqualified figure is safe to compare.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = _NUMBER_RE.search(text)
    if not match:
        return None
    try:
        number = float(match.group(0).replace(",", ""))
    except ValueError:
        return None
    low = text.lower()
    for word, factor in _MAGNITUDE_WORDS:
        if re.search(rf"\d\s*{re.escape(word)}\b", low):
            return number * factor
    return number


_DOLLAR_FIGURE_RE = re.compile(r"\$\s*(-?\d[\d,]*\.?\d*)")


def _first_dollar_figure(value: Any) -> float | None:
    """First $-prefixed figure in a multi-period client revenue string.

    CQA writes these as "2024: $10,917,799; 2023: $11,589,127" — most recent
    first, each amount preceded by its period. Taking the leading number
    outright picks up the YEAR (2024), which then divides into company
    revenue as a plausible-looking near-zero share. Anchoring on the dollar
    sign is what distinguishes the amount from the label around it.
    """
    if value is None:
        return None
    match = _DOLLAR_FIGURE_RE.search(str(value))
    if not match:
        return money_to_dollars(value)
    return money_to_dollars(match.group(0) + _magnitude_tail(str(value), match.end()))


def _magnitude_tail(text: str, start: int) -> str:
    """The magnitude word immediately following a figure, if any, so
    "$59,699 thousand" keeps its scale when the figure is extracted alone."""
    tail = text[start : start + 12].lower()
    for word, _factor in _MAGNITUDE_WORDS:
        if tail.strip().startswith(word):
            return " " + word
    return ""


def _derive_customer_shares(
    top_customers: list, fta_yaml: dict | None,
) -> tuple[list, str]:
    """Fill each client's revenue share from dollars when the agent gave none.

    CQA extracts named clients with dollar revenue far more often than it
    extracts a concentration percentage — Clearsulting's every ``top*_pct``
    came back null while ten clients carried real dollars. The share is
    arithmetic the report can do itself, so the concentration chart does not
    have to render "not extracted" over data that is present.

    Deliberately conservative about units: both sides are resolved to
    absolute dollars, and a result outside 0-100% is discarded rather than
    published. An implicit-magnitude mismatch (a company total stated in
    thousands against per-client raw dollars) shows up exactly there, and a
    diligence report is the wrong place to publish a confidently wrong 18,288%.
    """
    totals, fallback_total = _company_revenue_by_year(fta_yaml)
    if not (totals or fallback_total) or not isinstance(top_customers, list):
        return top_customers, ""
    enriched, derived_any = [], False
    for customer in top_customers:
        if not isinstance(customer, dict):
            continue
        if customer.get("revenue_pct_yr1") not in (None, "", "null"):
            enriched.append(customer)
            continue
        raw = customer.get("revenue_dollars")
        amount = _first_dollar_figure(raw)
        total = _matching_total(totals, fallback_total, raw)
        if amount is None or not total:
            enriched.append(customer)
            continue
        share = 100.0 * amount / total
        if not 0.0 < share <= 100.0:
            enriched.append(customer)
            continue
        enriched.append({**customer, "revenue_pct_yr1": f"{share:.1f}%", "share_is_derived": True})
        derived_any = True
    note = (
        "Shares computed from extracted client revenue against company revenue; "
        "the data room stated no concentration percentages."
        if derived_any
        else ""
    )
    return enriched, note


def _company_revenue_by_year(fta_yaml: dict | None) -> tuple[dict[int, float], float | None]:
    """Company revenue in absolute dollars, keyed by year, plus an overall
    fallback for rows whose period could not be read."""
    by_year: dict[int, float] = {}
    largest: float | None = None
    for row in (fta_yaml or {}).get("revenue_trend") or []:
        if not isinstance(row, dict):
            continue
        amount = money_to_dollars(row.get("revenue_stated"))
        if not amount:
            continue
        largest = amount if largest is None else max(largest, amount)
        kind, year = period_sort_key(row.get("period"))
        if kind == 0:
            by_year[year] = max(by_year.get(year, 0.0), amount)
    return by_year, largest


def _matching_total(
    totals: dict[int, float], fallback: float | None, client_revenue: Any,
) -> float | None:
    """Company revenue for the same year as the client figure being divided.

    CQA's per-client string names its period ("2024: $10,917,799"), and the
    company's own trend carries several. Dividing a 2024 client figure by TTM25
    company revenue silently understates every share — the numerator and the
    denominator have to describe the same window. Falls back to the most recent
    year only when the client figure names no period of its own.
    """
    kind, year = period_sort_key(str(client_revenue or ""))
    if kind == 0 and year in totals:
        return totals[year]
    return totals[max(totals)] if totals else fallback


def _as_percent_text(value: Any) -> str:
    """Render a share as a percentage, whether the source stated it as a bare
    number or already carried the sign. ``total_addbacks_pct_of_ebitda`` is a
    float column (12.2), and printing it raw produced captions reading
    "Addbacks total 12.2 of reported EBITDA"."""
    if value in (None, ""):
        return ""
    text = str(value).strip()
    if text.endswith("%"):
        return text
    try:
        return f"{float(text):g}%"
    except ValueError:
        return text


def _addbacks_from_qoe(qoe_snap: dict | None) -> list[dict[str, Any]]:
    """Map the QoE addback ledger onto the shape ``_quality`` renders.

    The final report's addback chart reads ``qoe.addbacks`` (label / amount /
    tier) and this mapper never produced the key, so the section rendered
    "Addbacks — not extracted from the data room" for every company while the
    agent had a full ledger: GKF ten Tier 4 items with amounts and rationale,
    Clearsulting eleven. The prose beside the empty chart discussed those very
    addbacks, which is how the contradiction stayed visible but unexplained.
    """
    snap = qoe_snap or {}
    ledger = (snap.get("yaml_dict") or {}).get("addback_ledger")
    if ledger is None:
        ledger = _parse_json_column((snap.get("delta_row") or {}).get("addback_ledger_json"))
    if not isinstance(ledger, list):
        return []
    out: list[dict[str, Any]] = []
    for item in ledger:
        if not isinstance(item, dict):
            continue
        amount = item.get("amount_dollars")
        if amount in (None, "", "null"):
            continue
        out.append(
            {
                "label": str(item.get("description") or item.get("label") or ""),
                "amount": amount,
                "tier": item.get("tier_classification") or item.get("tier"),
                "period": item.get("period"),
                "rationale": item.get("tier_rationale"),
            }
        )
    return out


def _qoe_from_snapshots(qoe_snap: dict | None, fta_yaml: dict | None) -> dict[str, Any]:
    delta = (qoe_snap or {}).get("delta_row") or {}
    # The column is total_addbacks_pct_of_ebitda; reading the shorter name
    # always returned None and silently fell through to FTA's own figure, which
    # is how a caption came to read "Addbacks total 569.3 of reported EBITDA"
    # for a company whose QoE agent had computed no percentage at all.
    addback_pct = delta.get("total_addbacks_pct_of_ebitda")
    if addback_pct is None:
        addback_pct = delta.get("addback_pct_of_ebitda")
    if addback_pct is None and fta_yaml:
        addback_pct = (fta_yaml.get("addback_schedule") or {}).get("addback_pct_of_ebitda")
    flags = delta.get("flags") or []
    if isinstance(flags, str):
        flags = json.loads(flags or "[]")
    return {
        "addback_pct_of_ebitda": _as_percent_text(addback_pct),
        "tier_summary": str(delta.get("tier_summary") or delta.get("executive_summary") or ""),
        "flags": flags if isinstance(flags, list) else [],
        "addbacks": _addbacks_from_qoe(qoe_snap),
        "tier4_count": delta.get("tier4_addback_count"),
    }


def _kpi_rows_from_yaml(kpi_yaml: dict | None, overlay_hint: str = "") -> list[dict[str, Any]]:
    if not kpi_yaml:
        return []
    # Same selection as _note_from_kpi_field — one rule, not two. Picking the
    # first non-empty block here was why every non-healthcare company's KPI
    # page rendered from an all-null healthcare stub.
    overlay_key, blob = _kpi_overlay_block(kpi_yaml, overlay_hint)
    if not overlay_key:
        return []
    if not isinstance(blob, dict):
        return []
    rows: list[dict[str, Any]] = []
    for metric_id, stated in blob.items():
        if metric_id in ("source_doc",) or stated in (None, "", "null", []):
            continue
        rows.append(
            {
                "metric_id": metric_id,
                "display_name": metric_id.replace("_", " ").title(),
                "stated_value": _format_kpi_by_field(metric_id, stated),
                "value_kind": kpi_value_kind(metric_id, stated),
                "threshold": "",
                "flag": "N/A",
                "confidence": "low",
                "fill_state": "gap_correct",
            }
        )
    return rows[:12]


# How a KPI field should be presented, decided from the field name and the
# shape of what the agent put in it. Every overlay's schema mixes three kinds
# of field in one flat block, and treating them alike is what produced a page
# of bill rates and a bar chart drawn from prose.
_KIND_BREAKDOWN = "breakdown"   # a list/dict of per-role or per-segment rows
_KIND_NOTE = "note"             # a sentence the agent wrote
_KIND_METRIC = "metric"         # a single figure

_PROSE_MIN_WORDS = 8


def kpi_value_kind(metric_id: str, stated: Any) -> str:
    """Classify a KPI field as a breakdown, a note, or a single figure.

    The distinction matters because only a single figure can honestly be
    drawn as a bar. ``bookings_stated`` is a paragraph that happens to contain
    "up over 15%"; parsed for a percentage it produced a bar filled to 15% of
    a screen it was never measured against — a number invented by the chart,
    not extracted by the agent.
    """
    if isinstance(stated, (list, dict)):
        return _KIND_BREAKDOWN
    text = str(stated or "").strip()
    if text.startswith(("[", "{")):
        return _KIND_BREAKDOWN
    if metric_id.endswith(("_note", "_stated", "_explained")):
        return _KIND_NOTE
    if len(text.split()) >= _PROSE_MIN_WORDS:
        return _KIND_NOTE
    return _KIND_METRIC


def _format_kpi_by_field(metric_id: str, stated: Any) -> str:
    """Render a KPI figure with the unit its field name declares.

    The agents write bare numbers into fields whose names carry the unit —
    ``attrition_rate_pct`` holds 14, ``revenue_per_fte_dollars`` holds 200000
    — and the table printed them bare, so a reader saw "14" and "200000" with
    no way to know one was a percentage and the other dollars.
    """
    base = format_kpi_value(stated)
    if kpi_value_kind(metric_id, stated) != _KIND_METRIC:
        return base
    text = base.strip()
    if not text or any(ch in text for ch in "%$"):
        return text
    try:
        number = float(text.replace(",", ""))
    except ValueError:
        return text
    if metric_id.endswith("_pct"):
        return f"{number:g}%"
    if metric_id.endswith("_dollars"):
        return f"${number:,.0f}"
    return text


def _build_legal_block(delta_row: dict[str, Any]) -> dict[str, Any]:
    unable = _parse_json_column(delta_row.get("unable_to_assess_json")) or []
    if not isinstance(unable, list):
        unable = []
    flags = delta_row.get("flags") or []
    if isinstance(flags, str):
        flags = json.loads(flags or "[]")
    sorted_flags = sorted(flags, key=_flag_sort_key) if isinstance(flags, list) else []
    diligence = _parse_json_column(delta_row.get("recommended_diligence_json")) or []
    if not isinstance(diligence, list):
        diligence = []
    section_conf = delta_row.get("section_confidence") or "medium"
    if section_conf not in ("high", "medium", "low"):
        section_conf = "medium"
    return {
        "assessed_count": max(0, 11 - len(unable)),
        "checklist_total": 11,
        "section_confidence": section_conf,
        "top_flags": sorted_flags[:5],
        "top_gaps": [str(g) for g in unable[:8]],
        "recommended_diligence": diligence[:8],
    }


def apply_field_mappings(
    snapshots: dict[str, dict[str, Any]],
    profile: dict[str, Any],
    meta: dict[str, Any],
) -> dict[str, Any]:
    """Apply Appendix B stage-2 field mappings; return partial bundle dict."""
    print("[orchestrator] build:map applying field mappings")

    bma_yaml = snapshots.get("business_model", {}).get("yaml_dict")
    fta_yaml = snapshots.get("financial_trends", {}).get("yaml_dict")
    cqa_yaml = snapshots.get("customer_quality", {}).get("yaml_dict")
    kpi_yaml = snapshots.get("kpi", {}).get("yaml_dict")
    legal_delta = snapshots.get("legal", {}).get("delta_row") or {}

    company_name = str(meta.get("company_name") or "")
    vertical_overlay = str(profile.get("industry_overlay") or "")
    # Which overlay's KPI block belongs to this company. The profile is the
    # primary signal; kpi_agent's own overlay_confirmed is the fallback for a
    # run whose profile came back without one. Empty is fine — the selection
    # falls back to whichever block the agent actually filled.
    overlay_hint = vertical_overlay or str(
        (snapshots.get("kpi", {}).get("delta_row") or {}).get("overlay_confirmed") or ""
    )

    partial: dict[str, Any] = {
        "meta": {
            "company_name": company_name,
            "vertical_overlay": vertical_overlay,
        },
        "headline_metrics": _headline_from_fta(fta_yaml),
        "executive": {
            "in_one_line": "",
            "preliminary_view": {
                "strengths": [],
                "concerns": [],
                "closing": (
                    "Additional validation required before forming an investment view."
                ),
            },
        },
        "company_framing": _company_framing_from_bma(bma_yaml, profile),
        "financials": {
            "table_rows": _fta_table_rows(fta_yaml),
            "observations": [],
            "geographic_mix": (fta_yaml or {}).get("revenue_by_segment") or [],
            "segment_performance": _segment_performance_from_fta(fta_yaml),
        },
        "revenue_quality": _revenue_quality_from_agents(
            bma_yaml, cqa_yaml, kpi_yaml, overlay_hint, fta_yaml
        ),
        "kpi_dashboard": _kpi_rows_from_yaml(kpi_yaml, overlay_hint),
        "qoe": _qoe_from_snapshots(snapshots.get("quality_of_earnings"), fta_yaml),
        "legal": _build_legal_block(legal_delta)
        if legal_delta
        else {
            "assessed_count": 0,
            "checklist_total": 11,
            "section_confidence": "low",
            "top_flags": [],
            "top_gaps": [],
            "recommended_diligence": [],
        },
    }
    return partial


def tldr_bundle_paths() -> set[str]:
    """Normalized bundle paths marked required_for_tldr in FIELD_MAPPINGS."""
    return {row.bundle_path for row in FIELD_MAPPINGS if row.required_for_tldr}
