"""Deterministic-rule fixtures for KPIAgent._apply_kpi_flags (M0 T5).

Owned rules (Program Gate G2 — do not duplicate in M1/M2 checklists):
- Tech overlay: contractor % of workforce >50% → Yellow
- Tech overlay: delivery-geography concentration language (india / single geography /
  heavily concentrated / primarily ) → Yellow
- Tech overlay: average ACV <$100,000 → Yellow
- Tech overlay: utilization <65% → Red; 65–75% → Yellow; ≥75% → no flag
- Tech overlay: min(pipeline_coverage_months, backlog_months_of_revenue) <6 months → Yellow
- Healthcare overlay: staff turnover >30% → Red
- Healthcare overlay: missing utilization_or_productivity_note → Yellow
- Healthcare overlay: each compliance_incidents entry → Red
- Healthcare overlay: site_level_visibility false/partial → Yellow
- Overlay branching: apply_tech when "tech" in overlay or overlay is None; apply_healthcare
  when "healthcare" in overlay or overlay is None
- missing_kpis entries → data_room_gaps

Decision C scope boundary: overlay is passed as a fixture-constructed literal to
_apply_kpi_flags(extracted, overlay). This file does not exercise run()'s Spark-backed
company-profile SQL lookup that resolves overlay in production.
"""

from __future__ import annotations

import pytest

from agents.workstreams.kpi_agent import KPIAgent


def _flag_by_metric(agent: KPIAgent, metric: str) -> dict | None:
    for flag in agent._flags_as_dicts():
        if flag["metric"] == metric:
            return flag
    return None


def _minimal_tech(**overrides) -> dict:
    tech = {
        "contractor_pct_of_workforce": "40%",
        "delivery_geography_note": "Distributed US delivery",
        "average_acv_dollars": "150000",
        "utilization_rate_pct": "80%",
        "pipeline_coverage_months": "8",
        "backlog_months_of_revenue": "8",
        "source_doc": "kpi.pdf",
    }
    tech.update(overrides)
    return {"tech_services_kpis": tech, "healthcare_kpis": {}}


def _minimal_health(**overrides) -> dict:
    health = {
        "turnover_rate_pct": "20%",
        "utilization_or_productivity_note": "Census at 85%",
        "compliance_incidents": [],
        "site_level_visibility": "true",
        "source_doc": "ops.pdf",
    }
    health.update(overrides)
    return {"tech_services_kpis": {}, "healthcare_kpis": health}


def test_contractor_pct_above_50_yellow_tech_overlay():
    agent = KPIAgent()
    agent._apply_kpi_flags(
        _minimal_tech(contractor_pct_of_workforce="55%"),
        overlay="tech_services",
    )
    flag = _flag_by_metric(agent, "contractor_pct_of_workforce")
    assert flag is not None
    assert flag["severity"] == "Yellow"


@pytest.mark.parametrize(
    "geo_note",
    [
        "Delivery primarily in India",
        "Single geography concentration in Midwest",
        "Workforce heavily concentrated in one state",
        "Team is primarily remote in Texas",
    ],
)
def test_delivery_geography_concentration_yellow(geo_note: str):
    agent = KPIAgent()
    agent._apply_kpi_flags(
        _minimal_tech(delivery_geography_note=geo_note),
        overlay="tech_services",
    )
    flag = _flag_by_metric(agent, "delivery_geography_concentration")
    assert flag is not None
    assert flag["severity"] == "Yellow"


def test_average_acv_below_100k_yellow_tech_overlay():
    agent = KPIAgent()
    agent._apply_kpi_flags(
        _minimal_tech(average_acv_dollars="75000"),
        overlay="tech_services",
    )
    flag = _flag_by_metric(agent, "average_acv_dollars")
    assert flag is not None
    assert flag["severity"] == "Yellow"


@pytest.mark.parametrize(
    "utilization,expected_severity",
    [
        ("60%", "Red"),
        ("70%", "Yellow"),
        ("80%", None),
    ],
)
def test_utilization_rate_thresholds(utilization: str, expected_severity: str | None):
    agent = KPIAgent()
    agent._apply_kpi_flags(
        _minimal_tech(utilization_rate_pct=utilization),
        overlay="tech_services",
    )
    flag = _flag_by_metric(agent, "utilization_rate_pct")
    if expected_severity is None:
        assert flag is None
    else:
        assert flag is not None
        assert flag["severity"] == expected_severity


def test_pipeline_backlog_coverage_below_6_months_yellow():
    agent = KPIAgent()
    agent._apply_kpi_flags(
        _minimal_tech(pipeline_coverage_months="4", backlog_months_of_revenue="10"),
        overlay="tech_services",
    )
    flag = _flag_by_metric(agent, "pipeline_backlog_coverage_months")
    assert flag is not None
    assert flag["severity"] == "Yellow"


def test_staff_turnover_above_30_red_healthcare_overlay():
    agent = KPIAgent()
    agent._apply_kpi_flags(
        _minimal_health(turnover_rate_pct="35%"),
        overlay="healthcare_services",
    )
    flag = _flag_by_metric(agent, "turnover_rate_pct")
    assert flag is not None
    assert flag["severity"] == "Red"


def test_missing_utilization_productivity_note_yellow_healthcare():
    agent = KPIAgent()
    agent._apply_kpi_flags(
        _minimal_health(utilization_or_productivity_note=""),
        overlay="healthcare_services",
    )
    flag = _flag_by_metric(agent, "utilization_or_productivity_data")
    assert flag is not None
    assert flag["severity"] == "Yellow"


def test_compliance_incidents_red_per_incident():
    agent = KPIAgent()
    agent._apply_kpi_flags(
        _minimal_health(
            compliance_incidents=[
                {"type": "survey", "description": "Adverse survey finding", "source_doc": "a.pdf"},
                {"type": "billing", "description": "Coding audit issue", "source_doc": "b.pdf"},
            ]
        ),
        overlay="healthcare_services",
    )
    flags = agent._flags_as_dicts()
    compliance_flags = [f for f in flags if f["metric"].startswith("compliance_incident_")]
    assert len(compliance_flags) == 2
    assert all(f["severity"] == "Red" for f in compliance_flags)


@pytest.mark.parametrize("site_visibility", ["false", "partial"])
def test_site_level_visibility_false_or_partial_yellow(site_visibility: str):
    agent = KPIAgent()
    agent._apply_kpi_flags(
        _minimal_health(site_level_visibility=site_visibility),
        overlay="healthcare_services",
    )
    flag = _flag_by_metric(agent, "site_level_visibility")
    assert flag is not None
    assert flag["severity"] == "Yellow"


def test_overlay_none_applies_both_tech_and_healthcare_branches():
    agent = KPIAgent()
    extracted = {
        "tech_services_kpis": {
            "contractor_pct_of_workforce": "55%",
            "delivery_geography_note": "US only",
            "average_acv_dollars": "150000",
            "utilization_rate_pct": "80%",
            "pipeline_coverage_months": "8",
            "backlog_months_of_revenue": "8",
            "source_doc": "kpi.pdf",
        },
        "healthcare_kpis": {
            "turnover_rate_pct": "35%",
            "utilization_or_productivity_note": "Present",
            "compliance_incidents": [],
            "site_level_visibility": "true",
            "source_doc": "ops.pdf",
        },
    }
    agent._apply_kpi_flags(extracted, overlay=None)
    assert _flag_by_metric(agent, "contractor_pct_of_workforce") is not None
    assert _flag_by_metric(agent, "turnover_rate_pct") is not None


def test_overlay_tech_only_skips_healthcare_flags():
    agent = KPIAgent()
    agent._apply_kpi_flags(
        _minimal_health(turnover_rate_pct="35%"),
        overlay="tech_services",
    )
    assert _flag_by_metric(agent, "turnover_rate_pct") is None


def test_overlay_healthcare_only_skips_tech_flags():
    agent = KPIAgent()
    agent._apply_kpi_flags(
        _minimal_tech(contractor_pct_of_workforce="55%"),
        overlay="healthcare_services",
    )
    assert _flag_by_metric(agent, "contractor_pct_of_workforce") is None


def test_missing_kpis_add_data_room_gaps():
    agent = KPIAgent()
    extracted = _minimal_tech()
    extracted["missing_kpis"] = [
        {
            "kpi_name": "bill_rate",
            "management_question": "What is the average bill rate?",
        }
    ]
    agent._apply_kpi_flags(extracted, overlay="tech_services")
    assert any("Missing KPI [bill_rate]" in gap for gap in agent._data_room_gaps)


def test_pipeline_only_coverage_uses_single_value():
    """Adversarial falsifier: coverage must use pipeline alone when backlog is absent."""
    agent = KPIAgent()
    agent._apply_kpi_flags(
        _minimal_tech(
            pipeline_coverage_months="3",
            backlog_months_of_revenue=None,
        ),
        overlay="tech_services",
    )
    flag = _flag_by_metric(agent, "pipeline_backlog_coverage_months")
    assert flag is not None
    assert flag["severity"] == "Yellow"
