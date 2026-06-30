"""Unit tests for ConfidenceEngine (M2 T2)."""

from __future__ import annotations

from agents.orchestrator.confidence import ConfidenceEngine


def test_compute_by_area_missing_agent_is_low() -> None:
    engine = ConfidenceEngine()
    areas = engine.compute_by_area({}, {})
    assert areas["business_model"] == "low"
    assert areas["forecast_support"] == "low"
    assert len(areas) == 7


def test_compute_by_area_legal_uses_section_confidence() -> None:
    engine = ConfidenceEngine()
    snapshots = {
        "legal": {"delta_row": {"section_confidence": "high"}, "yaml_dict": {}},
    }
    areas = engine.compute_by_area({}, snapshots)
    assert areas["legal"] == "high"


def test_compute_by_area_fta_high_when_three_years_cited() -> None:
    engine = ConfidenceEngine()
    snapshots = {
        "financial_trends": {
            "delta_row": {},
            "yaml_dict": {
                "revenue_trend": [
                    {"period": "2022"},
                    {"period": "2023"},
                    {"period": "2024"},
                ],
            },
        },
    }
    areas = engine.compute_by_area({}, snapshots)
    assert areas["financial_trends"] == "high"


def test_compute_by_area_bma_bank_no_cim_reduces_one_notch() -> None:
    engine = ConfidenceEngine()
    bundle = {"meta": {"deal_type": "banked buyout"}}
    snapshots = {
        "business_model": {"delta_row": {"cim_detected": False}, "yaml_dict": {}},
    }
    areas = engine.compute_by_area(bundle, snapshots)
    assert areas["business_model"] == "low"


def test_compute_overall_medium_low_when_spread_ge_two() -> None:
    engine = ConfidenceEngine()
    by_area = {
        "business_model": "high",
        "financial_trends": "medium",
        "customer_quality": "low",
        "kpi": "medium",
        "legal": "medium",
        "quality_of_earnings": "medium",
        "forecast_support": "low",
    }
    assert engine.compute_overall(by_area, []) == "medium_low"


def test_compute_overall_critical_risk_floors_low() -> None:
    engine = ConfidenceEngine()
    by_area = {
        "business_model": "high",
        "financial_trends": "high",
        "customer_quality": "high",
        "kpi": "high",
        "legal": "high",
        "quality_of_earnings": "high",
        "forecast_support": "low",
    }
    risks = [{"severity": "critical", "risk": "Revenue concentration"}]
    assert engine.compute_overall(by_area, risks) == "low"


def test_compute_overall_excludes_forecast_support() -> None:
    engine = ConfidenceEngine()
    by_area = {
        "business_model": "high",
        "financial_trends": "high",
        "customer_quality": "high",
        "kpi": "high",
        "legal": "high",
        "quality_of_earnings": "high",
        "forecast_support": "low",
    }
    assert engine.compute_overall(by_area, []) == "high"
