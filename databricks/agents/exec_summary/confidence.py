"""UC13 Orchestrator — ConfidenceEngine per spec §5.12."""

from __future__ import annotations

from typing import Any

_CONF_ORDER = ["high", "medium", "low"]

_AREA_KEYS = (
    "business_model",
    "financial_trends",
    "customer_quality",
    "kpi",
    "legal",
    "quality_of_earnings",
)


def _reduce_confidence(level: str) -> str:
    if level not in _CONF_ORDER:
        return "low"
    idx = _CONF_ORDER.index(level)
    return _CONF_ORDER[min(idx + 1, len(_CONF_ORDER) - 1)]


def _gap_count_for_agent(bundle: dict, agent_key: str) -> int:
    return sum(
        1
        for row in bundle.get("data_room_gaps") or []
        if isinstance(row, dict) and row.get("source_agent") == agent_key
    )


def _kpi_na_ratio(rows: list) -> float:
    dict_rows = [r for r in rows if isinstance(r, dict)]
    if not dict_rows:
        return 1.0
    na = sum(1 for r in dict_rows if r.get("flag") == "N/A")
    return na / len(dict_rows)


class ConfidenceEngine:
    """Deterministic per-area and overall confidence (§5.12)."""

    def compute_by_area(
        self,
        bundle: dict,
        snapshots: dict[str, dict[str, Any]],
    ) -> dict[str, str]:
        """Seven keys incl. ``forecast_support``; does not set overall."""
        areas: dict[str, str] = {}

        for agent_key in _AREA_KEYS:
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
                    meta = bundle.get("meta")
                    deal = meta.get("deal_type") if isinstance(meta, dict) else ""
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

    def compute_overall(
        self,
        by_area: dict[str, str],
        risks: list,
    ) -> str:
        """Min-area-wins + Red-flag floor + spread ≥ 2 steps → ``medium_low`` (§5.12)."""
        keys = [k for k in by_area if k != "forecast_support"]
        values = [by_area[k] for k in keys if k in by_area and by_area[k] in _CONF_ORDER]
        if not values:
            return "low"

        indices = [_CONF_ORDER.index(v) for v in values]
        worst_idx = max(indices)
        best_idx = min(indices)
        spread = worst_idx - best_idx
        overall = _CONF_ORDER[worst_idx]

        if any(isinstance(r, dict) and r.get("severity") == "critical" for r in risks):
            return "low"

        if spread >= 2:
            return "medium_low"

        return overall
