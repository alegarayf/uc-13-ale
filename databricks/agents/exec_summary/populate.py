"""UC13 Orchestrator — M1 demo populate path (LLM synthesis + ``demo_mode: true``).

For production bundles use :class:`~agents.orchestrator.bundle_builder.BundleBuilder`
(``BundleBuilder.build()``) — deterministic stages 0–8 with ``demo_mode: false``.
This module preserves the notebook render fallback when a demo bundle is needed.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from pyspark.sql import SparkSession

from agents.orchestrator.bundle_builder import (
    GapAggregator,
    apply_fill_state,
    collect_synthesis_gaps,
    freshness,
    merge_risks_from_flags,
    write_bundle_yaml,
)
from agents.orchestrator.confidence import ConfidenceEngine
from agents.orchestrator.constants import AGENT_DELTA_TABLE_SUFFIXES, AGENTS_PRESENT_KEYS
from agents.orchestrator.ingest import ingest_snapshots
from agents.orchestrator.paths import company_safe, reports_volume_dir
from agents.orchestrator.validate import BundleValidationError, validate_bundle
from agents.shared.agent_base import WorkstreamAgent

_gap_aggregator = GapAggregator()
_confidence_engine = ConfidenceEngine()

_SEVERITY_ORDER = {"Red": 0, "Yellow": 1, "Green": 2}
_CONF_ORDER = ["high", "medium", "low"]

_DEMO_DISCLAIMER = (
    "Preliminary demo synthesis for diligence orientation only. "
    "Not investment advice or a recommendation to buy, sell, or hold."
)

_LLM_SYSTEM_PROMPT = """You are the UC13 orchestrator synthesis agent (M1 demo).
Populate orchestrator bundle fields from workstream agent snapshots provided in the user message.
Return ONLY valid JSON (no markdown fences) with these optional top-level keys:
  executive, headline_metrics, company_framing, financials, revenue_quality, qoe
Use exact field names from current_bundle_skeleton — do not invent keys.
Do not include kpi_dashboard, risks, data_room_gaps, diligence_questions, meta, legal, or provenance.
Use stated figures and agent summaries only — do not invent financial metrics.
Leave arrays empty rather than fabricating rows. preliminary_view.closing must avoid invest advice."""


class _OrchestratorLlm(WorkstreamAgent):
    agent_name = "orchestrator"


def _deep_merge(base: dict, overlay: dict) -> dict:
    for key, value in overlay.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        elif value is not None:
            base[key] = value
    return base


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


def _pick_dict(obj: Any, allowed: frozenset[str]) -> dict[str, Any]:
    if not isinstance(obj, dict):
        return {}
    return {k: v for k, v in obj.items() if k in allowed}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if isinstance(item, str) and str(item).strip()]


def _valid_financial_table_rows(rows: Any) -> list[dict[str, str]] | None:
    if not isinstance(rows, list) or not rows:
        return None
    required = (
        "year",
        "revenue",
        "gross_profit",
        "gross_margin_pct",
        "ebitda",
        "ebitda_margin_pct",
    )
    valid: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            return None
        picked = {key: str(row.get(key) or "") for key in required}
        if any(picked.values()):
            valid.append(picked)
    return valid or None


def _merge_llm_narrative(bundle: dict[str, Any], llm_result: dict[str, Any]) -> None:
    """Overlay LLM narrative fields only — never replace deterministic structural blocks."""
    if not llm_result:
        return

    executive = llm_result.get("executive")
    if isinstance(executive, dict):
        exc = _pick_dict(
            executive,
            frozenset({"in_one_line", "preliminary_view"}),
        )
        if isinstance(exc.get("in_one_line"), str) and exc["in_one_line"].strip():
            bundle["executive"]["in_one_line"] = exc["in_one_line"].strip()
        pv = exc.get("preliminary_view")
        if isinstance(pv, dict):
            pv = _pick_dict(pv, frozenset({"strengths", "concerns", "closing"}))
            for key in ("strengths", "concerns"):
                strings = _string_list(pv.get(key))
                if strings:
                    bundle["executive"]["preliminary_view"][key] = strings
            if isinstance(pv.get("closing"), str) and pv["closing"].strip():
                bundle["executive"]["preliminary_view"]["closing"] = pv["closing"].strip()

    headline = llm_result.get("headline_metrics")
    if isinstance(headline, dict):
        for key in (
            "ltm_revenue",
            "ltm_ebitda",
            "ltm_ebitda_margin_pct",
            "revenue_cagr",
            "enterprise_value_indicated",
            "rule_of_40",
        ):
            if key not in headline:
                continue
            val = headline[key]
            if val is None:
                continue
            text = str(val).strip()
            if text:
                bundle["headline_metrics"][key] = text

    framing = llm_result.get("company_framing")
    if isinstance(framing, dict):
        framing = _pick_dict(
            framing,
            frozenset({"overview_bullets", "revenue_model", "recent_changes", "thesis"}),
        )
        bullets = _string_list(framing.get("overview_bullets"))
        if bullets:
            bundle["company_framing"]["overview_bullets"] = bullets
        rev = framing.get("revenue_model")
        if isinstance(rev, dict):
            rev = _pick_dict(rev, frozenset({"tag", "quality_flag", "note"}))
            for key, val in rev.items():
                if val is not None and str(val).strip():
                    bundle["company_framing"]["revenue_model"][key] = str(val).strip()
        thesis = framing.get("thesis")
        if isinstance(thesis, dict):
            thesis = _pick_dict(thesis, frozenset({"bullets", "value_creation_levers"}))
            for key in ("bullets", "value_creation_levers"):
                strings = _string_list(thesis.get(key))
                if strings:
                    bundle["company_framing"]["thesis"][key] = strings
        if isinstance(framing.get("recent_changes"), list):
            bundle["company_framing"]["recent_changes"] = framing["recent_changes"]

    financials = llm_result.get("financials")
    if isinstance(financials, dict):
        financials = _pick_dict(
            financials,
            frozenset({"table_rows", "observations", "geographic_mix"}),
        )
        observations = _string_list(financials.get("observations"))
        if observations:
            bundle["financials"]["observations"] = observations
        table_rows = _valid_financial_table_rows(financials.get("table_rows"))
        if table_rows:
            bundle["financials"]["table_rows"] = table_rows
        if isinstance(financials.get("geographic_mix"), list):
            bundle["financials"]["geographic_mix"] = financials["geographic_mix"]

    revenue_quality = llm_result.get("revenue_quality")
    if isinstance(revenue_quality, dict):
        for key in ("scale_narrative", "concentration", "end_market_mix", "retention_notes"):
            val = revenue_quality.get(key)
            if isinstance(val, str) and val.strip():
                bundle["revenue_quality"][key] = val.strip()

    qoe = llm_result.get("qoe")
    if isinstance(qoe, dict):
        qoe = _pick_dict(qoe, frozenset({"addback_pct_of_ebitda", "tier_summary", "flags"}))
        for key in ("addback_pct_of_ebitda", "tier_summary"):
            val = qoe.get(key)
            if isinstance(val, str) and val.strip():
                bundle["qoe"][key] = val.strip()
        if isinstance(qoe.get("flags"), list):
            bundle["qoe"]["flags"] = [f for f in qoe["flags"] if isinstance(f, dict)]


def _restore_structural_fields_after_llm(bundle: dict, preserved: dict[str, Any]) -> None:
    """Always restore deterministic blocks the LLM must not overwrite."""
    bundle["meta"] = preserved["meta"]
    for key in ("legal", "data_room_gaps", "kpi_dashboard", "risks", "diligence_questions"):
        bundle[key] = preserved[key]


def _load_company_profile(
    spark: SparkSession, catalog: str, company_name: str
) -> dict[str, Any]:
    try:
        rows = (
            spark.sql(
                f"""
                SELECT *
                FROM {catalog}.classification.company_profile
                WHERE company_name = '{company_name}'
                ORDER BY created_at DESC
                LIMIT 1
                """
            ).collect()
        )
    except Exception:
        return {}
    return rows[0].asDict(recursive=True) if rows else {}


def _build_agents_present(snapshots: dict) -> dict[str, bool]:
    return {key: key in snapshots for key in AGENTS_PRESENT_KEYS}


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
    if section_conf not in _CONF_ORDER:
        section_conf = "medium"
    return {
        "assessed_count": max(0, 11 - len(unable)),
        "checklist_total": 11,
        "section_confidence": section_conf,
        "top_flags": sorted_flags[:5],
        "top_gaps": [str(g) for g in unable[:8]],
        "recommended_diligence": diligence[:8],
    }


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
                "gross_margin_pct": str(gm.get("gm_pct_stated") or gm.get("gross_margin_pct") or ""),
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


def _agent_context_payload(snapshots: dict) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, snap in snapshots.items():
        payload[key] = {
            "delta_row": {
                k: v
                for k, v in (snap.get("delta_row") or {}).items()
                if k != "flags"
            },
            "yaml_dict": snap.get("yaml_dict"),
            "report_path": snap.get("report_path"),
        }
    return payload


def _llm_populate(
    llm_endpoint: str,
    company_name: str,
    context: dict[str, Any],
    skeleton: dict[str, Any],
) -> dict[str, Any]:
    llm = _OrchestratorLlm()
    user_prompt = json.dumps(
        {
            "company_name": company_name,
            "agent_snapshots": context,
            "current_bundle_skeleton": {
                "headline_metrics": skeleton.get("headline_metrics"),
                "company_framing": skeleton.get("company_framing"),
                "financials": skeleton.get("financials"),
            },
        },
        default=str,
    )[:120_000]
    print("[orchestrator] populate: calling LLM for bundle synthesis")
    raw = llm._call_llm(_LLM_SYSTEM_PROMPT, user_prompt, llm_endpoint, max_tokens=12_000)
    return llm._parse_json_response(raw)


def populate_bundle(
    company_name: str,
    catalog: str,
    spark: SparkSession | None = None,
    llm_endpoint: str = "databricks-claude-sonnet-4-6",
) -> dict:
    """M1 demo path: ingest → LLM narrative → shared stages → validate → Volume write.

    Production bundles should use :class:`~agents.orchestrator.bundle_builder.BundleBuilder`.
    Sets ``meta.demo_mode`` to ``True`` and preserves the LLM synthesis stage.
    """
    if spark is None:
        spark = SparkSession.getActiveSession()
    if spark is None:
        raise RuntimeError("No active Spark session.")

    print("[orchestrator] populate: ingest snapshots")
    snapshots = ingest_snapshots(company_name, catalog, spark)
    profile = _load_company_profile(spark, catalog, company_name)
    generated_at = datetime.now(timezone.utc)
    agents_present = _build_agents_present(snapshots)

    bma_yaml = snapshots.get("business_model", {}).get("yaml_dict")
    fta_yaml = snapshots.get("financial_trends", {}).get("yaml_dict")
    cqa_yaml = snapshots.get("customer_quality", {}).get("yaml_dict")
    kpi_yaml = snapshots.get("kpi", {}).get("yaml_dict")
    legal_delta = snapshots.get("legal", {}).get("delta_row") or {}

    cim_detected = None
    if snapshots.get("business_model"):
        cim_detected = snapshots["business_model"]["delta_row"].get("cim_detected")

    bundle: dict[str, Any] = {
        "meta": {
            "schema_version": "0.1.0",
            "company_name": company_name,
            "company_safe": company_safe(company_name),
            "catalog": catalog,
            "vertical_overlay": str(profile.get("industry_overlay") or ""),
            "deal_type": profile.get("deal_type"),
            "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
            "status": "complete" if all(agents_present.values()) else "partial",
            "freshness": "current",
            "render_state": "bundle_only",
            "demo_mode": True,
            "disclaimer_text": _DEMO_DISCLAIMER,
            "basis_of_preparation": (
                f"Phase 3 workstream outputs + LLM synthesis (demo M1). "
                f"cim_detected={cim_detected}"
            ),
            "overall_confidence": "low",
            "agents_present": agents_present,
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
        "legal": _build_legal_block(legal_delta) if legal_delta else {
            "assessed_count": 0,
            "checklist_total": 11,
            "section_confidence": "low",
            "top_flags": [],
            "top_gaps": [],
            "recommended_diligence": [],
        },
        "risks": merge_risks_from_flags(snapshots),
        "diligence_questions": _gap_aggregator.build_diligence_questions({}, snapshots),
        "data_room_gaps": _gap_aggregator.merge_data_room_gaps(snapshots),
        "confidence_by_area": {k: "low" for k in (
            "business_model",
            "financial_trends",
            "customer_quality",
            "kpi",
            "legal",
            "quality_of_earnings",
            "forecast_support",
        )},
        "provenance": {
            "agent_report_paths": {
                k: str(snap.get("report_path") or "")
                for k, snap in snapshots.items()
            },
            "agent_delta_tables": {
                k: f"{catalog}.analysis.{AGENT_DELTA_TABLE_SUFFIXES[k]}" for k in snapshots
            },
            "bundle_builder_version": "0.1.0-m1",
            "synthesis_gaps": [],
        },
    }

    context = _agent_context_payload(snapshots)
    llm_result: dict[str, Any] = {}
    for attempt in range(2):
        try:
            llm_result = _llm_populate(llm_endpoint, company_name, context, bundle)
            break
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            print(f"[orchestrator] populate: LLM parse failed (attempt {attempt + 1}): {exc}")
            if attempt == 1:
                llm_result = {}

    if llm_result:
        preserved_structural = {
            "meta": dict(bundle["meta"]),
            "legal": deepcopy(bundle["legal"]),
            "data_room_gaps": deepcopy(bundle["data_room_gaps"]),
            "kpi_dashboard": deepcopy(bundle["kpi_dashboard"]),
            "risks": deepcopy(bundle["risks"]),
            "diligence_questions": deepcopy(bundle["diligence_questions"]),
        }
        _merge_llm_narrative(bundle, llm_result)
        _restore_structural_fields_after_llm(bundle, preserved_structural)

    print("[orchestrator] populate: compute confidence")
    bundle["confidence_by_area"] = _confidence_engine.compute_by_area(bundle, snapshots)
    bundle["meta"]["overall_confidence"] = _confidence_engine.compute_overall(
        bundle["confidence_by_area"],
        bundle.get("risks") or [],
    )
    bundle["meta"]["freshness"] = freshness(spark, catalog, company_name, generated_at)

    print("[orchestrator] populate: apply fill_state")
    bundle = apply_fill_state(bundle)
    bundle["provenance"]["synthesis_gaps"] = collect_synthesis_gaps(bundle)

    print("[orchestrator] validate: jsonschema")
    try:
        validate_bundle(bundle)
    except BundleValidationError:
        raise

    vol_dir = reports_volume_dir(catalog, company_name)
    out_path = f"{vol_dir}/orchestrator_bundle.yaml"
    print(f"[orchestrator] populate: writing {out_path}")
    write_bundle_yaml(bundle, out_path, spark, catalog)

    return bundle
