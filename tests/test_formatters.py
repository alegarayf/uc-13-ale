"""Unit tests for orchestrator formatters (KPI value formatting — T12)."""

from __future__ import annotations

from agents.orchestrator import formatters as fmt
from agents.orchestrator.field_mapping import _kpi_rows_from_yaml


def test_format_kpi_value_scalar_unchanged():
    assert fmt.format_kpi_value("73 active caregivers") == "73 active caregivers"
    assert fmt.format_kpi_value(42) == "42"
    assert fmt.format_kpi_value(True) == "true"


def test_format_kpi_value_dict_prefers_description():
    incident = {
        "type": "adverse_survey",
        "description": "CMS survey cited staffing deficiencies in Q3 2023.",
        "status": "closed",
        "source_doc": "survey.pdf",
    }
    assert fmt.format_kpi_value(incident) == "CMS survey cited staffing deficiencies in Q3 2023."


def test_format_kpi_value_dict_falls_back_to_type_and_status():
    incident = {"type": "licensing", "status": "open", "source_doc": "license.pdf"}
    assert fmt.format_kpi_value(incident) == "licensing (open)"


def test_format_kpi_value_list_of_incidents_joins_readable_text():
    incidents = [
        {
            "type": "adverse_survey",
            "description": "CMS survey cited staffing deficiencies.",
            "status": "closed",
        },
        {
            "type": "licensing",
            "description": "State license renewal pending documentation.",
            "status": "open",
        },
    ]
    result = fmt.format_kpi_value(incidents)
    assert "CMS survey cited staffing deficiencies." in result
    assert "State license renewal pending documentation." in result
    assert ";" in result
    assert not result.startswith("[")


def test_format_kpi_value_never_returns_dict_repr():
    stated = {"type": "adverse_survey", "status": "open"}
    result = fmt.format_kpi_value(stated)
    assert not result.startswith("{")
    assert "dict" not in result


def test_kpi_rows_from_yaml_formats_compliance_incidents():
    kpi_yaml = {
        "healthcare_kpis": {
            "caregiver_headcount": "73 active caregivers",
            "compliance_incidents": [
                {
                    "type": "adverse_survey",
                    "description": "CMS survey cited staffing deficiencies.",
                    "status": "closed",
                    "source_doc": "survey.pdf",
                }
            ],
            "source_doc": "cim.pdf",
        }
    }
    rows = _kpi_rows_from_yaml(kpi_yaml)
    by_metric = {row["metric_id"]: row["stated_value"] for row in rows}
    assert by_metric["caregiver_headcount"] == "73 active caregivers"
    assert "CMS survey cited staffing deficiencies." in by_metric["compliance_incidents"]
    assert "{" not in by_metric["compliance_incidents"]
