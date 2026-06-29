"""UC13 Orchestrator — LLM populate, confidence, fill_state, validate, persist (M1)."""

from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

import yaml
from pyspark.sql import SparkSession

from agents.orchestrator.constants import AGENTS_PRESENT_KEYS, FILL_STATE_RULES, TLDR_REQUIRED_FIELDS
from agents.orchestrator.ingest import ingest_snapshots
from agents.orchestrator.paths import company_safe, reports_volume_dir
from agents.orchestrator.validate import BundleValidationError, validate_bundle
from agents.shared.agent_base import WorkstreamAgent

_AGENT_TABLES: dict[str, str] = {
    "business_model": "business_model",
    "financial_trends": "financial_trends",
    "customer_quality": "customer_quality",
    "kpi": "kpi",
    "legal": "legal",
    "quality_of_earnings": "quality_of_earnings",
}

_SEVERITY_ORDER = {"Red": 0, "Yellow": 1, "Green": 2}
_FLAG_TO_RISK = {"Red": "critical", "Yellow": "material", "Green": "track"}
_CONF_ORDER = ["high", "medium", "low"]

_DEMO_DISCLAIMER = (
    "Preliminary demo synthesis for diligence orientation only. "
    "Not investment advice or a recommendation to buy, sell, or hold."
)

_LLM_SYSTEM_PROMPT = """You are the UC13 orchestrator synthesis agent (M1 demo).
Populate orchestrator bundle fields from workstream agent snapshots provided in the user message.
Return ONLY valid JSON (no markdown fences) with these top-level keys when you can support them
from the agent data:
  executive, headline_metrics, company_framing, financials, revenue_quality,
  kpi_dashboard, qoe, diligence_questions
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


def _normalize_gap(text: str) -> str:
    lowered = text.lower()
    lowered = re.sub(r"[^\w\s]", "", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def _flag_sort_key(flag: dict) -> tuple:
    sev = _SEVERITY_ORDER.get(flag.get("severity", "Green"), 9)
    return (sev, flag.get("metric") or "", flag.get("note") or "")


def merge_risks_from_flags(snapshots: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Project Delta flags to ``risks[]`` per §5.6.1; sort Red→Yellow→Green; top 8."""
    projected: list[dict[str, Any]] = []
    for agent_key, snap in snapshots.items():
        flags = snap.get("delta_row", {}).get("flags") or []
        if not isinstance(flags, list):
            continue
        for flag in flags:
            if not isinstance(flag, dict):
                continue
            metric = flag.get("metric") or ""
            note = flag.get("note") or ""
            value = flag.get("value") or ""
            source_doc = flag.get("source_doc") or ""
            evidence = f"{value} ({source_doc})".strip(" ()") if value or source_doc else ""
            projected.append(
                {
                    "risk": metric or note or "Flag",
                    "severity": _FLAG_TO_RISK.get(flag.get("severity", "Green"), "track"),
                    "evidence": evidence,
                    "mitigant_or_question": note or flag.get("threshold") or "",
                    "source_agent": agent_key,
                    "confidence": flag.get("confidence") or "medium",
                    "fill_state": "filled_cited",
                }
            )
    severity_rank = {"critical": 0, "material": 1, "track": 2}
    projected.sort(
        key=lambda r: (
            severity_rank.get(r.get("severity", "track"), 9),
            r.get("risk") or "",
            r.get("mitigant_or_question") or "",
        )
    )
    return projected[:8]


def _gap_count_for_agent(bundle: dict, agent_key: str) -> int:
    return sum(
        1
        for row in bundle.get("data_room_gaps") or []
        if row.get("source_agent") == agent_key
    )


def _kpi_na_ratio(rows: list[dict]) -> float:
    if not rows:
        return 1.0
    na = sum(1 for r in rows if r.get("flag") == "N/A")
    return na / len(rows)


def _reduce_confidence(level: str) -> str:
    if level not in _CONF_ORDER:
        return "low"
    idx = _CONF_ORDER.index(level)
    return _CONF_ORDER[min(idx + 1, len(_CONF_ORDER) - 1)]


def compute_confidence(bundle: dict, snapshots: dict[str, dict[str, Any]]) -> dict[str, str]:
    """Inline §5.12 rules; sets ``confidence_by_area`` values (not overall)."""
    areas: dict[str, str] = {}

    for agent_key in (
        "business_model",
        "financial_trends",
        "customer_quality",
        "kpi",
        "legal",
        "quality_of_earnings",
    ):
        if agent_key not in snapshots:
            areas[agent_key] = "low"
            continue

        level = "medium"
        snap = snapshots[agent_key]
        delta_row = snap.get("delta_row") or {}
        yaml_dict = snap.get("yaml_dict") or {}

        if agent_key == "legal":
            section = delta_row.get("section_confidence")
            areas[agent_key] = section if section in _CONF_ORDER else "medium"
            continue

        if agent_key == "kpi":
            rows = bundle.get("kpi_dashboard") or []
            if _kpi_na_ratio(rows) > 0.5:
                level = "low"
            areas[agent_key] = level
            continue

        if agent_key == "customer_quality":
            cqa_yaml = yaml_dict
            customers = (
                (cqa_yaml.get("customer_concentration") or {}).get("top_customers")
                if isinstance(cqa_yaml.get("customer_concentration"), dict)
                else None
            )
            if not customers:
                customers = cqa_yaml.get("top_customers")
            if not customers:
                level = "low"
            areas[agent_key] = level
            continue

        if agent_key == "financial_trends":
            revenue_trend = yaml_dict.get("revenue_trend") or []
            cited_years = len(
                [r for r in revenue_trend if isinstance(r, dict) and r.get("period")]
            )
            areas[agent_key] = "high" if cited_years >= 3 else "medium"
            continue

        if agent_key == "business_model":
            cim = delta_row.get("cim_detected")
            if cim is False:
                deal = (bundle.get("meta") or {}).get("deal_type") or ""
                if "bank" in str(deal).lower():
                    level = _reduce_confidence(level)
            areas[agent_key] = level
            continue

        if agent_key == "quality_of_earnings":
            areas[agent_key] = "medium"
            continue

        areas[agent_key] = level

    if _gap_count_for_agent(bundle, "business_model") >= 3:
        areas["business_model"] = _reduce_confidence(areas.get("business_model", "medium"))
    for key in list(areas):
        if _gap_count_for_agent(bundle, key) >= 3 and areas[key] == "high":
            areas[key] = "medium"

    areas["forecast_support"] = "low"
    return areas


def _overall_confidence(
    confidence_by_area: dict[str, str],
    risks: list[dict],
    *,
    include_forecast: bool = False,
) -> str:
    keys = list(confidence_by_area.keys())
    if not include_forecast:
        keys = [k for k in keys if k != "forecast_support"]
    values = [confidence_by_area[k] for k in keys if k in confidence_by_area]
    if not values:
        return "low"
    overall = _CONF_ORDER[max(_CONF_ORDER.index(v) for v in values if v in _CONF_ORDER)]
    if any(r.get("severity") == "critical" for r in risks):
        overall = "low"
    return overall


def _get_by_path(obj: dict, path: str) -> Any:
    if path.endswith("[]"):
        key = path[:-2]
        parts = key.split(".")
        cur: Any = obj
        for part in parts:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(part)
        return cur
    if path.endswith(".*"):
        prefix = path[:-2]
        parts = prefix.split(".")
        cur: Any = obj
        for part in parts:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(part)
        if not isinstance(cur, dict):
            return cur
        return cur
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _is_field_empty(bundle: dict, path: str) -> bool:
    if path.endswith("[]"):
        val = _get_by_path(bundle, path)
        return not val
    if path.endswith(".*"):
        block = _get_by_path(bundle, path)
        if not isinstance(block, dict):
            return True
        return not any(v not in (None, "", [], {}) for v in block.values())
    val = _get_by_path(bundle, path)
    if val is None:
        return True
    if isinstance(val, str):
        return not val.strip()
    if isinstance(val, (list, dict)):
        return len(val) == 0
    return False


def _collect_synthesis_gaps(bundle: dict) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    for field_path in TLDR_REQUIRED_FIELDS:
        if _is_field_empty(bundle, field_path):
            gaps.append(
                {
                    "field_path": field_path,
                    "reason": "Required TL;DR field empty after populate",
                    "owner": "orchestrator",
                }
            )
    return gaps


def apply_fill_state(bundle: dict) -> dict:
    """Deterministic §5.6 stage 6b post-pass using ``FILL_STATE_RULES``."""
    result = deepcopy(bundle)

    def _assign_list(rule_path: str, items: list | None, default: str) -> None:
        if not items:
            return
        for item in items:
            if isinstance(item, dict) and "fill_state" in item:
                if _is_field_empty({"x": item}, "x.item") and "item" in item:
                    item["fill_state"] = "gap_correct" if default == "gap_correct" else "not_attempted"
                elif not item.get("fill_state"):
                    item["fill_state"] = default

    for path, typical in FILL_STATE_RULES.items():
        if path.endswith("[]"):
            key_parts = path[:-2].split(".")
            cur: Any = result
            for part in key_parts:
                cur = cur.get(part) if isinstance(cur, dict) else None
            if isinstance(cur, list):
                _assign_list(path, cur, typical)
        elif path.endswith(".*"):
            block = _get_by_path(result, path)
            if isinstance(block, dict):
                for sub_key, sub_val in block.items():
                    if sub_val in (None, "", []):
                        continue
        # Scalar / object paths: fill_state lives on child rows only in M1 schema.

    for row in result.get("kpi_dashboard") or []:
        if not isinstance(row, dict):
            continue
        if row.get("flag") == "N/A":
            row["fill_state"] = "gap_correct"
        elif not row.get("fill_state"):
            row["fill_state"] = FILL_STATE_RULES.get("kpi_dashboard[]", "filled_cited")

    for row in result.get("risks") or []:
        if isinstance(row, dict) and not row.get("fill_state"):
            row["fill_state"] = FILL_STATE_RULES.get("risks[]", "filled_synthesized")

    for row in result.get("diligence_questions") or []:
        if isinstance(row, dict) and not row.get("fill_state"):
            row["fill_state"] = FILL_STATE_RULES.get("diligence_questions[]", "filled_synthesized")

    for row in result.get("data_room_gaps") or []:
        if isinstance(row, dict) and not row.get("fill_state"):
            row["fill_state"] = FILL_STATE_RULES.get("data_room_gaps[]", "filled_cited")

    return result


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


def _merge_data_room_gaps(snapshots: dict) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    rows: list[dict[str, Any]] = []
    for agent_key, snap in snapshots.items():
        delta_row = snap.get("delta_row") or {}
        for gap_text in delta_row.get("data_room_gaps") or []:
            norm = _normalize_gap(str(gap_text))
            dedupe_key = (norm, agent_key)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            rows.append(
                {
                    "item": str(gap_text),
                    "priority": "medium",
                    "source_agent": agent_key,
                    "fill_state": "filled_cited",
                }
            )
        if agent_key == "legal":
            unable = _parse_json_column(delta_row.get("unable_to_assess_json")) or []
            for item in unable if isinstance(unable, list) else []:
                norm = _normalize_gap(str(item))
                dedupe_key = (norm, agent_key)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                rows.append(
                    {
                        "item": str(item),
                        "priority": "high",
                        "source_agent": agent_key,
                        "fill_state": "gap_correct",
                    }
                )
    return rows


def _build_diligence_questions(snapshots: dict) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    legal = snapshots.get("legal", {}).get("delta_row") or {}
    diligence = _parse_json_column(legal.get("recommended_diligence_json")) or []
    if isinstance(diligence, list):
        for entry in diligence[:8]:
            if not isinstance(entry, dict):
                continue
            questions.append(
                {
                    "category": entry.get("category") or "legal",
                    "question": entry.get("question") or entry.get("item") or str(entry),
                    "priority": entry.get("priority") or "high",
                    "source_agent": "legal",
                    "fill_state": "filled_synthesized",
                }
            )
    kpi_snap = snapshots.get("kpi", {})
    missing = (kpi_snap.get("yaml_dict") or {}).get("missing_kpis") or []
    if isinstance(missing, list):
        for item in missing[:4]:
            questions.append(
                {
                    "category": "kpi",
                    "question": f"Provide supporting data for KPI: {item}",
                    "priority": "medium",
                    "source_agent": "kpi",
                    "fill_state": "gap_correct",
                }
            )
    return questions[:8]


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


def _freshness(
    spark: SparkSession,
    catalog: str,
    company_name: str,
    generated_at: datetime,
) -> str:
    latest: datetime | None = None
    for agent_key in AGENTS_PRESENT_KEYS:
        table = f"{catalog}.analysis.{_AGENT_TABLES[agent_key]}"
        try:
            row = spark.sql(
                f"""
                SELECT created_at FROM {table}
                WHERE company_name = '{company_name}'
                ORDER BY created_at DESC LIMIT 1
                """
            ).collect()
        except Exception:
            continue
        if not row:
            continue
        created = row[0]["created_at"]
        if created and (latest is None or created > latest):
            latest = created
    if latest and latest > generated_at:
        return "stale"
    return "current"


def _write_bundle_yaml(bundle: dict, path: str, spark: SparkSession, catalog: str) -> None:
    spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.analysis.reports")
    os.makedirs(os.path.dirname(path), exist_ok=True)

    def _str_representer(dumper, data):
        if "\n" in data:
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
        return dumper.represent_scalar("tag:yaml.org,2002:str", data)

    yaml.add_representer(str, _str_representer)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(bundle, fh, allow_unicode=True, sort_keys=False, width=120)


def populate_bundle(
    company_name: str,
    catalog: str,
    spark: SparkSession | None = None,
    llm_endpoint: str = "databricks-claude-sonnet-4-6",
) -> dict:
    """Ingest → LLM → merge → confidence → fill_state → validate → Volume write."""
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
        "diligence_questions": _build_diligence_questions(snapshots),
        "data_room_gaps": _merge_data_room_gaps(snapshots),
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
                k: f"{catalog}.analysis.{_AGENT_TABLES[k]}" for k in snapshots
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
        _deep_merge(bundle, llm_result)

    print("[orchestrator] populate: compute confidence")
    bundle["confidence_by_area"] = compute_confidence(bundle, snapshots)
    bundle["meta"]["overall_confidence"] = _overall_confidence(
        bundle["confidence_by_area"],
        bundle.get("risks") or [],
        include_forecast=False,
    )
    bundle["meta"]["freshness"] = _freshness(
        spark, catalog, company_name, generated_at
    )

    print("[orchestrator] populate: apply fill_state")
    bundle = apply_fill_state(bundle)
    bundle["provenance"]["synthesis_gaps"] = _collect_synthesis_gaps(bundle)

    print("[orchestrator] validate: jsonschema")
    try:
        validate_bundle(bundle)
    except BundleValidationError:
        raise

    vol_dir = reports_volume_dir(catalog, company_name)
    out_path = f"{vol_dir}/orchestrator_bundle.yaml"
    print(f"[orchestrator] populate: writing {out_path}")
    _write_bundle_yaml(bundle, out_path, spark, catalog)

    return bundle
