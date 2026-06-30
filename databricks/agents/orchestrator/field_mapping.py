"""UC13 Orchestrator — Appendix B data-driven field mapping (M2 B1)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

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


def _fta_table_rows(fta_yaml: dict | None) -> list[dict[str, str]]:
    if not fta_yaml:
        return []
    revenue_trend = fta_yaml.get("revenue_trend") or []
    ebitda_rows = fta_yaml.get("ebitda") or []
    gross_margin = fta_yaml.get("gross_margin") or []
    ebitda_by_period = {
        str(r.get("period", r.get("label", ""))): r
        for r in ebitda_rows
        if isinstance(r, dict)
    }
    gm_by_period = {
        str(r.get("period", "")): r for r in gross_margin if isinstance(r, dict)
    }
    rows: list[dict[str, str]] = []
    for rev in revenue_trend:
        if not isinstance(rev, dict):
            continue
        period = str(rev.get("period") or rev.get("label") or "")
        ebitda = ebitda_by_period.get(period, {})
        gm = gm_by_period.get(period, {})
        rows.append(
            {
                "year": period,
                "revenue": str(rev.get("revenue") or rev.get("value") or ""),
                "gross_profit": str(gm.get("gross_profit") or ""),
                "gross_margin_pct": str(
                    gm.get("gm_pct_stated") or gm.get("gross_margin_pct") or ""
                ),
                "ebitda": str(ebitda.get("ebitda") or ebitda.get("value") or ""),
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
        empty["ltm_revenue"] = str(latest.get("revenue") or latest.get("value") or "")
        yoy_values = [
            r.get("yoy_growth_pct")
            for r in revenue_trend
            if isinstance(r, dict) and r.get("yoy_growth_pct")
        ]
        if yoy_values:
            empty["revenue_cagr"] = str(yoy_values[-1])
    if ebitda_rows:
        latest_e = ebitda_rows[-1] if isinstance(ebitda_rows[-1], dict) else {}
        empty["ltm_ebitda"] = str(latest_e.get("ebitda") or latest_e.get("value") or "")
        empty["ltm_ebitda_margin_pct"] = str(
            latest_e.get("ebitda_margin_pct") or latest_e.get("margin_pct") or ""
        )
    return empty


def _company_framing_from_bma(bma_yaml: dict | None) -> dict[str, Any]:
    if not bma_yaml:
        return {
            "overview_bullets": [],
            "revenue_model": {"tag": "", "quality_flag": "", "note": ""},
            "recent_changes": [],
            "thesis": {"bullets": [], "value_creation_levers": []},
        }
    rev = bma_yaml.get("revenue_model") or {}
    exec_summary = bma_yaml.get("executive_summary") or ""
    bullets = [exec_summary] if exec_summary else []
    products = bma_yaml.get("products_and_services") or []
    if isinstance(products, list):
        bullets.extend(
            str(p.get("name") or p) for p in products[:3] if isinstance(p, dict)
        )
    return {
        "overview_bullets": bullets[:5],
        "revenue_model": {
            "tag": str(rev.get("tag") or ""),
            "quality_flag": str(rev.get("durability_rating") or rev.get("quality_flag") or ""),
            "note": str(rev.get("note") or ""),
        },
        "recent_changes": bma_yaml.get("recent_model_changes") or [],
        "thesis": {"bullets": [], "value_creation_levers": []},
    }


def _revenue_quality_from_agents(
    bma_yaml: dict | None, cqa_yaml: dict | None
) -> dict[str, str]:
    concentration = ""
    if cqa_yaml:
        conc = cqa_yaml.get("customer_concentration") or cqa_yaml.get("concentration") or {}
        if isinstance(conc, dict):
            concentration = str(conc.get("summary") or conc.get("top_customer_pct") or "")
        elif conc:
            concentration = str(conc)
    scale = ""
    if bma_yaml and bma_yaml.get("executive_summary"):
        scale = str(bma_yaml["executive_summary"])[:500]
    return {
        "scale_narrative": scale,
        "concentration": concentration,
        "end_market_mix": "",
        "retention_notes": "",
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
                "stated_value": str(stated),
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
        "company_framing": _company_framing_from_bma(bma_yaml),
        "financials": {
            "table_rows": _fta_table_rows(fta_yaml),
            "observations": [],
            "geographic_mix": (fta_yaml or {}).get("revenue_by_segment") or [],
        },
        "revenue_quality": _revenue_quality_from_agents(bma_yaml, cqa_yaml),
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
