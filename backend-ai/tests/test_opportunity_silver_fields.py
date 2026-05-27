import pytest

from app.opportunity_silver_fields import (
    normalize_field_name,
    normalize_rule_config,
    python_source_uses_only_allowed_fields,
)


def test_normalize_field_name_snake_case():
    assert normalize_field_name("annual_revenue") == "annual_revenue"


def test_normalize_field_name_camel_case_alias():
    assert normalize_field_name("AnnualRevenue") == "annual_revenue"


def test_normalize_field_name_rejects_unknown():
    assert normalize_field_name("slack_message") is None


def test_normalize_rule_config_drops_invalid_conditions():
    rule = normalize_rule_config(
        {
            "name": "Test",
            "conditions": [
                {"field": "annual_revenue", "operator": ">=", "value": 1},
                {"field": "slack_channel", "operator": "=", "value": "#alerts"},
            ],
        }
    )
    assert len(rule["conditions"]) == 1
    assert rule["conditions"][0]["field"] == "annual_revenue"
    assert "slack_channel" in rule["metadata"]["dropped_invalid_fields"]


def test_python_source_uses_only_allowed_fields():
    assert python_source_uses_only_allowed_fields("opportunity['AnnualRevenue']") is True
    assert python_source_uses_only_allowed_fields("opportunity['EmployeeHeadCount']") is True
    assert python_source_uses_only_allowed_fields('opportunity.get("annual_revenue")') is False
    assert python_source_uses_only_allowed_fields('opportunity.get("AnnualRevenue")') is False
    assert python_source_uses_only_allowed_fields("opportunity['SlackMessage']") is False
