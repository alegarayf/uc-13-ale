"""UC13 Orchestrator — Appendix B data-driven field mapping (M2 B1)."""

from __future__ import annotations

import json
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
# (mirrors the 3-version cap documented for EbitdaSubAgent — pf_adjusted is
# the most decision-useful figure, reported is the fallback of last resort).
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


def _canonical_ebitda_by_period(ebitda_rows: list) -> dict[str, dict]:
    """One EBITDA record per period, preferring pf_adjusted > clinic_level_adjusted
    > reported > anything else (fix B0 — FTA can emit multiple EBITDA versions
    for the same period, which previously produced duplicate table rows)."""
    by_period: dict[str, dict] = {}
    for r in ebitda_rows:
        if not isinstance(r, dict):
            continue
        if not _has_numeric_signal(r, "ebitda_dollars", "ebitda_margin_pct"):
            continue
        period = str(r.get("period", r.get("label", "")))
        if not period:
            continue
        existing = by_period.get(period)
        if existing is None or _ebitda_version_rank(r) < _ebitda_version_rank(existing):
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
    ebitda_by_period = _canonical_ebitda_by_period(ebitda_rows)
    gm_by_period = _canonical_gross_margin_by_period(gross_margin)
    # A period with real data ANYWHERE across the three sources is genuine.
    # Filters out a non-data record a sub-agent sometimes appends inline
    # instead of using the dedicated discrepancy-flagging path (e.g. a
    # "period": "DISCREPANCY_FLAG" note, every numeric field null, with no
    # companion entry in gross_margin/ebitda either) — without this, it
    # becomes a phantom empty column in both the P&L table and the
    # Financial Snapshot chart.
    real_periods = _periods_with_real_data(revenue_trend, gm_by_period, ebitda_by_period)
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
        ebitda = ebitda_by_period.get(period, {})
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
            }
        )
    return rows


def _headline_from_fta(fta_yaml: dict | None) -> dict[str, str | None]:
    empty = {
        "ltm_revenue": "",
        "ltm_ebitda": "",
        "ltm_ebitda_margin_pct": "",
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
        latest_e = _canonical_ebitda_by_period(ebitda_rows).get(last_period, last_raw)
        empty["ltm_ebitda"] = str(
            latest_e.get("ebitda_dollars") or latest_e.get("ebitda") or latest_e.get("value") or ""
        )
        empty["ltm_ebitda_margin_pct"] = str(
            latest_e.get("ebitda_margin_pct") or latest_e.get("margin_pct") or ""
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


def _kpi_overlay_block(kpi_yaml: dict) -> tuple[str, dict] | tuple[None, None]:
    for key in _KPI_OVERLAY_BLOCKS:
        blob = kpi_yaml.get(key)
        if blob:
            return key, blob if isinstance(blob, dict) else {}
    return None, None


def _note_from_kpi_field(kpi_yaml: dict | None, field_by_overlay: dict[str, str]) -> str:
    if not kpi_yaml:
        return ""
    overlay_key, blob = _kpi_overlay_block(kpi_yaml)
    if not overlay_key:
        return ""
    field = field_by_overlay.get(overlay_key)
    if not field:
        return ""  # this overlay's schema has no analog field — genuinely nothing to report
    value = blob.get(field)
    return str(value) if value not in (None, "", "null") else ""


def _revenue_quality_from_agents(
    bma_yaml: dict | None, cqa_yaml: dict | None, kpi_yaml: dict | None = None,
) -> dict[str, str]:
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
        concentration = _note_from_kpi_field(kpi_yaml, _KPI_CONCENTRATION_FIELD)
    if not end_market_mix:
        end_market_mix = _note_from_kpi_field(kpi_yaml, _KPI_END_MARKET_MIX_FIELD)
    scale = ""
    if bma_yaml and bma_yaml.get("executive_summary"):
        scale = str(bma_yaml["executive_summary"])[:500]
    return {
        "scale_narrative": scale,
        "concentration": concentration,
        "end_market_mix": end_market_mix,
        "retention_notes": retention_notes,
    }


def _qoe_from_snapshots(qoe_snap: dict | None, fta_yaml: dict | None) -> dict[str, Any]:
    delta = (qoe_snap or {}).get("delta_row") or {}
    addback_pct = delta.get("addback_pct_of_ebitda")
    if addback_pct is None and fta_yaml:
        addback_pct = (fta_yaml.get("addback_schedule") or {}).get("addback_pct_of_ebitda")
    flags = delta.get("flags") or []
    if isinstance(flags, str):
        flags = json.loads(flags or "[]")
    return {
        "addback_pct_of_ebitda": str(addback_pct or ""),
        "tier_summary": str(delta.get("tier_summary") or delta.get("executive_summary") or ""),
        "flags": flags if isinstance(flags, list) else [],
    }


def _kpi_rows_from_yaml(kpi_yaml: dict | None) -> list[dict[str, Any]]:
    if not kpi_yaml:
        return []
    overlay_key = None
    for key in (
        "healthcare_kpis",
        "tech_services_kpis",
        "saas_kpis",
        "industrial_kpis",
        "consumer_kpis",
    ):
        if kpi_yaml.get(key):
            overlay_key = key
            break
    if not overlay_key:
        return []
    blob = kpi_yaml.get(overlay_key) or {}
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
                "stated_value": format_kpi_value(stated),
                "threshold": "",
                "flag": "N/A",
                "confidence": "low",
                "fill_state": "gap_correct",
            }
        )
    return rows[:12]


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
        },
        "revenue_quality": _revenue_quality_from_agents(bma_yaml, cqa_yaml, kpi_yaml),
        "kpi_dashboard": _kpi_rows_from_yaml(kpi_yaml),
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
