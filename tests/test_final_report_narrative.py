"""Unit tests for agents.exec_summary.final_report_narrative — the six
"Analyst take" boxes plus the structured recommendation (T11, plan §3.5).

Modelled on tests/test_rainmaker_narrative.py and
tests/test_kpi_narrative_gateway.py's gateway-mocking pattern. No network:
``agents.shared.llm_client.chat`` is patched everywhere.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

from agents.exec_summary.final_report_narrative import (  # noqa: E402
    _SYSTEM_PROMPT,
    build_final_report_narrative_digest,
    synthesize_final_report_narrative,
)


def _bundle(**overrides) -> dict:
    base = {
        "meta": {"vertical_overlay": "tech_services", "company_name": "Acme"},
        "company_framing": {
            "overview_bullets": ["Founded 2020", "Remote team"],
            "revenue_model": {"tag": "subscription", "quality_flag": "durable", "note": "Recurring."},
            "business_description": "Sells widgets to other businesses.",
            "sale_process": "Run by Acme Bank as sell-side advisor.",
            "key_partners": [{"name": "BigCo", "relationship_type": "channel", "description": "Reseller"}],
        },
        "revenue_quality": {
            "scale_narrative": "Scale narrative.",
            "concentration": "Top 10 = 40%.",
            "retention_notes": "NRR 110%.",
            "concentration_summary": {"top1_pct": "12%", "top5_pct": "40%"},
            "retention": {"nrr_pct": "110%", "grr_pct": "95%"},
            "top_customers": [{"customer_name": "BigCo", "revenue_pct_yr1": "12%"}],
        },
        "kpi_dashboard": [{"display_name": "ARR", "stated_value": "$5M"}],
        "qoe": {
            "addback_pct_of_ebitda": "20%",
            "addbacks": [{"label": "Owner comp", "amount": "$1.0"}],
            "flags": [{"description": "One-time synergy included"}],
        },
        "financials": {
            "table_rows": [
                {"year": "2024A", "revenue": "$5.0", "ebitda": "$1.0", "gross_margin_pct": "80%", "ebitda_margin_pct": "20%"}
            ],
            "observations": ["Revenue grew 20% YoY."],
        },
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Digest builder — no LLM
# ---------------------------------------------------------------------------


def test_digest_covers_all_six_sections():
    digest = build_final_report_narrative_digest(_bundle())
    assert {"business", "financial", "customer", "kpi", "quality", "forecast"} <= set(digest.keys())


def test_digest_carries_the_gaps_that_need_a_reason():
    """The appendix's "Why it matters" column was blank on every row of every
    report. Gaps whose sentence already contains the reason are split out
    upstream; only the bare ones are sent to the model."""
    digest = build_final_report_narrative_digest({
        "data_room_gaps": [
            {"item": "Top Customer Contracts", "why": None},
            {"item": "Already explained", "why": "Needed to price churn."},
        ],
    })
    assert digest["gaps_needing_reason"] == [{"i": 0, "item": "Top Customer Contracts"}]


def test_digest_business_section_carries_f6_fields():
    digest = build_final_report_narrative_digest(_bundle())
    assert digest["business"]["sale_process"]
    assert digest["business"]["key_partners"] == ["BigCo"]


def test_digest_financial_section_uses_pnl_table_not_raw_percent_strings():
    digest = build_final_report_narrative_digest(_bundle())
    assert digest["financial"]["periods"] == ["2024A"]
    assert digest["financial"]["latest_revenue"]


def test_digest_empty_qoe_yields_empty_quality_section():
    bundle = _bundle(qoe={})
    digest = build_final_report_narrative_digest(bundle)
    assert digest["quality"]["addbacks"] == []
    assert digest["quality"]["flags"] == []
    assert digest["quality"]["addback_pct_of_ebitda"] is None


def test_digest_forecast_falls_back_to_history_when_no_forecast_rows():
    digest = build_final_report_narrative_digest(_bundle())
    assert "history" in digest["forecast"]
    assert digest["forecast"]["history"][0]["year"] == "2024A"


def test_digest_forecast_uses_forecast_rows_when_present():
    bundle = _bundle()
    bundle["financials"]["forecast_rows"] = [{"year": "2025P", "revenue": "6.0"}]
    digest = build_final_report_narrative_digest(bundle)
    assert "forecast_rows" in digest["forecast"]
    assert "history" not in digest["forecast"]


# ---------------------------------------------------------------------------
# The bounded LLM call — one call, pinned kwargs, three failure paths
# ---------------------------------------------------------------------------

_VALID_RESPONSE = json.dumps(
    {
        "business_take": "Recurring revenue from BigCo partnership; sale run by Acme Bank.",
        "financial_take": "Revenue of $5.0 with 20% EBITDA margin in 2024A.",
        "customer_take": "Top customer concentration at 12%, NRR 110%.",
        "kpi_take": "ARR of $5M against sector screens.",
        "quality_take": "Addbacks are 20% of EBITDA, led by owner comp.",
        "forecast_take": None,
        "recommendation": {
            "verdict": "Proceed",
            "rationale": "Durable recurring revenue with manageable concentration.",
            "conditions": ["Validate NRR", "Confirm addback support"],
            "tone": "pass",
        },
    }
)


@patch("agents.shared.llm_client.chat")
def test_synthesize_calls_gateway_exactly_once_with_pinned_kwargs(mock_chat):
    mock_chat.return_value = (_VALID_RESPONSE, {})
    result = synthesize_final_report_narrative(_bundle(), llm_endpoint="databricks-claude-sonnet-4-6")

    assert mock_chat.call_count == 1
    kwargs = mock_chat.call_args.kwargs
    assert kwargs["endpoint"] == "databricks-claude-sonnet-4-6"
    assert kwargs["max_tokens"] == 3_000
    assert kwargs["temperature"] == 0.0
    assert isinstance(kwargs["system_prompt"], str) and kwargs["system_prompt"]
    assert isinstance(kwargs["user_content"], str) and kwargs["user_content"]

    assert result["final_narrative_status"] == "success"
    assert result["business_take"]
    assert result["forecast_take"] is None
    assert result["recommendation"]["verdict"] == "Proceed"
    assert result["recommendation"]["tone"] == "pass"


@patch("agents.shared.llm_client.chat")
def test_synthesize_does_not_construct_a_deploy_client(mock_chat):
    mock_chat.return_value = (_VALID_RESPONSE, {})
    with patch("mlflow.deployments.get_deploy_client") as mock_get_deploy:
        synthesize_final_report_narrative(_bundle(), llm_endpoint="databricks-claude-sonnet-4-6")
        mock_get_deploy.assert_not_called()


@patch("agents.shared.llm_client.chat")
def test_synthesize_degrades_when_gateway_raises(mock_chat):
    mock_chat.side_effect = TimeoutError("simulated timeout")
    result = synthesize_final_report_narrative(_bundle(), llm_endpoint="databricks-claude-sonnet-4-6")

    assert result["final_narrative_status"] == "degraded"
    assert result["business_take"] is None
    assert result["recommendation"] is None


@patch("agents.shared.llm_client.chat")
def test_synthesize_degrades_on_malformed_json(mock_chat):
    mock_chat.return_value = ("not valid json{{{", {})
    result = synthesize_final_report_narrative(_bundle(), llm_endpoint="databricks-claude-sonnet-4-6")

    assert result["final_narrative_status"] == "degraded"
    assert all(result[key] is None for key in ("business_take", "financial_take", "customer_take"))


@patch("agents.shared.llm_client.chat")
def test_synthesize_degrades_on_valid_json_wrong_schema(mock_chat):
    mock_chat.return_value = (json.dumps(["not", "a", "dict"]), {})
    result = synthesize_final_report_narrative(_bundle(), llm_endpoint="databricks-claude-sonnet-4-6")

    assert result["final_narrative_status"] == "degraded"
    assert result["recommendation"] is None


@patch("agents.shared.llm_client.chat")
def test_unknown_keys_in_response_are_dropped(mock_chat):
    payload = json.loads(_VALID_RESPONSE)
    payload["not_a_real_key"] = "should be dropped"
    mock_chat.return_value = (json.dumps(payload), {})

    result = synthesize_final_report_narrative(_bundle(), llm_endpoint="databricks-claude-sonnet-4-6")

    assert "not_a_real_key" not in result


@patch("agents.shared.llm_client.chat")
def test_a_take_returned_as_a_dict_is_coerced_to_none(mock_chat):
    payload = json.loads(_VALID_RESPONSE)
    payload["business_take"] = {"unexpected": "shape"}
    mock_chat.return_value = (json.dumps(payload), {})

    result = synthesize_final_report_narrative(_bundle(), llm_endpoint="databricks-claude-sonnet-4-6")

    assert result["business_take"] is None


@patch("agents.shared.llm_client.chat")
def test_a_take_returned_as_a_list_is_coerced_to_none(mock_chat):
    payload = json.loads(_VALID_RESPONSE)
    payload["kpi_take"] = ["not", "a", "string"]
    mock_chat.return_value = (json.dumps(payload), {})

    result = synthesize_final_report_narrative(_bundle(), llm_endpoint="databricks-claude-sonnet-4-6")

    assert result["kpi_take"] is None


@patch("agents.shared.llm_client.chat")
def test_conditions_longer_than_three_still_renders_as_string_list(mock_chat):
    payload = json.loads(_VALID_RESPONSE)
    payload["recommendation"]["conditions"] = ["A", "B", "C", "D", "E"]
    mock_chat.return_value = (json.dumps(payload), {})

    result = synthesize_final_report_narrative(_bundle(), llm_endpoint="databricks-claude-sonnet-4-6")

    assert result["recommendation"]["conditions"] == ["A", "B", "C", "D", "E"]
    assert all(isinstance(c, str) for c in result["recommendation"]["conditions"])


@patch("agents.shared.llm_client.chat")
def test_empty_digest_section_none_take_is_preserved_not_defaulted(mock_chat):
    """A bundle with no qoe produces an empty 'quality' digest section; when
    the model (correctly) returns null for quality_take, that None must
    survive validation rather than being defaulted to a string."""
    bundle = _bundle(qoe={})
    digest = build_final_report_narrative_digest(bundle)
    assert digest["quality"] == {"addback_pct_of_ebitda": None, "addbacks": [], "flags": []}

    payload = json.loads(_VALID_RESPONSE)
    payload["quality_take"] = None
    mock_chat.return_value = (json.dumps(payload), {})

    result = synthesize_final_report_narrative(bundle, llm_endpoint="databricks-claude-sonnet-4-6")
    assert result["quality_take"] is None


# ---------------------------------------------------------------------------
# Prompt discipline — the two forbidding lines the close-out must quote
# ---------------------------------------------------------------------------


def test_prompt_forbids_inventing_a_figure():
    assert "Never invent a figure" in _SYSTEM_PROMPT


def test_prompt_forbids_a_take_over_an_empty_section():
    assert "Do NOT produce a take for a section whose digest is empty" in _SYSTEM_PROMPT


def test_prompt_forbids_mentioning_the_mps():
    assert "Minimum Pursuit Score" in _SYSTEM_PROMPT


def test_gap_reasons_are_keyed_by_the_index_the_model_echoes():
    """Keyed by echoed index, not by position in the reply: a model that
    drops or reorders an entry must not attach a reason to a gap it was not
    written for."""
    from agents.exec_summary.final_report_narrative import _coerce_gap_reasons

    out = _coerce_gap_reasons([{"i": 3, "why": "Needed to confirm the base."},
                               {"i": 0, "why": "Needed to price churn."}])
    assert out == {3: "Needed to confirm the base.", 0: "Needed to price churn."}


def test_gap_reasons_drop_malformed_entries_rather_than_the_whole_list():
    from agents.exec_summary.final_report_narrative import _coerce_gap_reasons

    out = _coerce_gap_reasons([
        {"i": 0, "why": "Good."}, {"i": "one", "why": "Bad index."},
        {"i": 2, "why": ""}, {"i": True, "why": "Bool is not an index."}, "not a dict",
    ])
    assert out == {0: "Good."}


def test_gap_reasons_tolerate_a_non_list_reply():
    from agents.exec_summary.final_report_narrative import _coerce_gap_reasons

    assert _coerce_gap_reasons(None) == {}
    assert _coerce_gap_reasons("nope") == {}
