"""Unit tests for orchestrator formatters (KPI value formatting — T12)."""

from __future__ import annotations

from agents.exec_summary import formatters as fmt
from agents.exec_summary.field_mapping import _kpi_rows_from_yaml


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


def test_split_gap_rationale_separates_the_reason_the_agent_wrote():
    from agents.exec_summary.formatters import split_gap_rationale

    item, why = split_gap_rationale(
        "Top customer revenue % not stated — required for concentration threshold evaluation"
    )
    assert item == "Top customer revenue % not stated"
    assert why == "Required for concentration threshold evaluation"


def test_split_gap_rationale_rejects_a_status_code_as_a_reason():
    """The legal agent ends gaps with "— corpus_absent". It clears any length
    floor and would print a retrieval code into a column read as analysis."""
    from agents.exec_summary.formatters import split_gap_rationale

    text = "ip: no IP Assignment / OSS Policy in corpus — corpus_absent"
    assert split_gap_rationale(text) == (text, None)


def test_split_gap_rationale_leaves_a_chain_of_clauses_whole():
    """Two separators means a trace, not a request-and-reason pair; cutting at
    the first dash would present an internal pass name as the item."""
    from agents.exec_summary.formatters import split_gap_rationale

    text = "t4c: no documents retrieved for pass — request Top Customer Contracts — no_chunks_retrieved"
    assert split_gap_rationale(text) == (text, None)


def test_split_gap_rationale_leaves_a_plain_request_alone():
    from agents.exec_summary.formatters import split_gap_rationale

    assert split_gap_rationale("Top Customer Contracts / MSAs / SOWs") == (
        "Top Customer Contracts / MSAs / SOWs", None,
    )


def test_is_operator_gap_catches_a_bare_schema_field_path():
    """The two that reached a delivered report: a bundle field reported empty
    reads as pipeline internals in a table a deal team reads as "what we are
    asking the seller for"."""
    from agents.exec_summary.formatters import is_operator_gap

    assert is_operator_gap("people_and_org.ownership is empty")
    assert is_operator_gap("customer_operational_metrics is empty")
    assert is_operator_gap("revenue_by_segment not populated")


def test_is_operator_gap_leaves_a_real_document_request_alone():
    from agents.exec_summary.formatters import is_operator_gap

    assert not is_operator_gap("Top Customer Contracts / MSAs / SOWs")
    assert not is_operator_gap("Change-of-control consent terms not determinable")
    assert not is_operator_gap("Missing KPI [Waitlist Length by School]: What is the count?")
    assert not is_operator_gap("Termination-for-convenience terms not determinable")
