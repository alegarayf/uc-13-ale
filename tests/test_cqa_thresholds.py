"""Deterministic threshold fixtures for CustomerQualityAgent._apply_customer_flags.

Owned rules (Program Gate G2 — do not duplicate in M1/M2 checklists):
  - Top-customer concentration: >25% Red (tech services); >20% Red (healthcare services)
  - NRR: <90% Red (tech services)
  - GRR: <80% Red (tech services)
  - NRR < GRR inconsistency → data-room gap (not a flag)
  - Average ACV: <$100,000 Yellow (tech services)
  - Government payor concentration (Medicare/Medicaid/VA/Managed Care sum): >50% Yellow (healthcare)
  - Missing required inputs → data-room gap per threshold field
  - overlay=None evaluates both tech and healthcare branches

Testability: Decision B — instantiate CustomerQualityAgent() directly and call
_apply_customer_flags; assert via _flags_as_dicts() / _data_room_gaps. No Spark/LLM
mocking. See .dev/decision-logs/M0-T3-fixture-testability-seam.md.
"""

from __future__ import annotations

import pytest

from agents.workstreams.customer_quality_agent import CustomerQualityAgent


@pytest.fixture
def agent() -> CustomerQualityAgent:
    return CustomerQualityAgent()


def _flag_metrics(agent: CustomerQualityAgent) -> set[str]:
    return {f["metric"] for f in agent._flags_as_dicts()}


def _flags_for_metric(agent: CustomerQualityAgent, metric: str) -> list[dict]:
    return [f for f in agent._flags_as_dicts() if f["metric"] == metric]


def _has_gap_substring(agent: CustomerQualityAgent, text: str) -> bool:
    return any(text in gap for gap in agent._data_room_gaps)


def _base_extracted() -> dict:
    """Minimal extracted dict with all thresholds in the no-flag zone."""
    return {
        "top_customers": [
            {"customer_name": "Acme", "revenue_pct_yr1": "10%", "source_doc": "rev.pdf"},
        ],
        "retention": {
            "nrr_pct": "95%",
            "grr_pct": "90%",
            "source_doc": "retention.pdf",
        },
        "average_account_size": {"acv_dollars": "$150,000", "source_doc": "acv.pdf"},
        "payor_mix": [
            {"payor_category": "Commercial", "pct_of_revenue": "80%"},
        ],
    }


def test_top_customer_concentration_tech_red(agent: CustomerQualityAgent):
    extracted = _base_extracted()
    extracted["top_customers"] = [
        {"customer_name": "BigCo", "revenue_pct_yr1": "30%", "source_doc": "rev.pdf"},
    ]
    agent._apply_customer_flags(extracted, "tech_services")
    flags = _flags_for_metric(agent, "top_customer_concentration")
    assert len(flags) == 1
    assert flags[0]["severity"] == "Red"
    assert ">25%" in flags[0]["threshold"]


def test_top_customer_concentration_healthcare_red(agent: CustomerQualityAgent):
    extracted = _base_extracted()
    extracted["top_customers"] = [
        {"customer_name": "Referral", "revenue_pct_yr1": "25%", "source_doc": "ref.pdf"},
    ]
    agent._apply_customer_flags(extracted, "healthcare_services")
    flags = _flags_for_metric(agent, "top_customer_concentration")
    assert len(flags) == 1
    assert flags[0]["severity"] == "Red"
    assert ">20%" in flags[0]["threshold"]


def test_top_customer_concentration_at_threshold_no_flag(agent: CustomerQualityAgent):
    """Boundary: exactly 25% tech / 20% healthcare must not trigger Red."""
    extracted = _base_extracted()
    extracted["top_customers"] = [
        {"customer_name": "Edge", "revenue_pct_yr1": "25%", "source_doc": "rev.pdf"},
    ]
    agent._apply_customer_flags(extracted, "tech_services")
    assert "top_customer_concentration" not in _flag_metrics(agent)

    agent2 = CustomerQualityAgent()
    extracted["top_customers"][0]["revenue_pct_yr1"] = "20%"
    agent2._apply_customer_flags(extracted, "healthcare_services")
    assert "top_customer_concentration" not in _flag_metrics(agent2)


def test_nrr_below_90_tech_red(agent: CustomerQualityAgent):
    extracted = _base_extracted()
    extracted["retention"]["nrr_pct"] = "85%"
    agent._apply_customer_flags(extracted, "tech_services")
    flags = _flags_for_metric(agent, "nrr_pct")
    assert len(flags) == 1
    assert flags[0]["severity"] == "Red"


def test_grr_below_80_tech_red(agent: CustomerQualityAgent):
    extracted = _base_extracted()
    extracted["retention"]["grr_pct"] = "75%"
    agent._apply_customer_flags(extracted, "tech_services")
    flags = _flags_for_metric(agent, "grr_pct")
    assert len(flags) == 1
    assert flags[0]["severity"] == "Red"


def test_nrr_below_grr_emits_gap_not_flag(agent: CustomerQualityAgent):
    extracted = _base_extracted()
    extracted["retention"]["nrr_pct"] = "85%"
    extracted["retention"]["grr_pct"] = "90%"
    agent._apply_customer_flags(extracted, "tech_services")
    assert _has_gap_substring(agent, "NRR stated lower than GRR")
    assert "nrr_pct" in _flag_metrics(agent)  # NRR <90% still flags separately


def test_average_acv_below_100k_tech_yellow(agent: CustomerQualityAgent):
    extracted = _base_extracted()
    extracted["average_account_size"] = {
        "acv_dollars": "$50,000",
        "source_doc": "acv.pdf",
    }
    agent._apply_customer_flags(extracted, "tech_services")
    flags = _flags_for_metric(agent, "average_acv_dollars")
    assert len(flags) == 1
    assert flags[0]["severity"] == "Yellow"


def test_government_payor_concentration_healthcare_yellow(agent: CustomerQualityAgent):
    extracted = _base_extracted()
    extracted["payor_mix"] = [
        {"payor_category": "Medicare", "pct_of_revenue": "35%"},
        {"payor_category": "Medicaid", "pct_of_revenue": "20%"},
    ]
    agent._apply_customer_flags(extracted, "healthcare_services")
    flags = _flags_for_metric(agent, "government_payor_concentration")
    assert len(flags) == 1
    assert flags[0]["severity"] == "Yellow"
    assert ">50%" in flags[0]["threshold"]


def test_overlay_none_evaluates_both_tech_and_healthcare_branches(agent: CustomerQualityAgent):
    extracted = _base_extracted()
    extracted["retention"]["nrr_pct"] = "85%"
    extracted["average_account_size"] = {"acv_dollars": "$50,000", "source_doc": "acv.pdf"}
    extracted["payor_mix"] = [{"payor_category": "Medicare", "pct_of_revenue": "60%"}]
    agent._apply_customer_flags(extracted, None)
    metrics = _flag_metrics(agent)
    assert "nrr_pct" in metrics
    assert "average_acv_dollars" in metrics
    assert "government_payor_concentration" in metrics


def test_healthcare_overlay_skips_tech_retention_gaps(agent: CustomerQualityAgent):
    """Healthcare-only overlay must not emit tech retention gaps for missing NRR/GRR."""
    extracted = _base_extracted()
    extracted["retention"] = {}
    agent._apply_customer_flags(extracted, "healthcare_services")
    assert not _has_gap_substring(agent, "NRR not stated")
    assert not _has_gap_substring(agent, "GRR not stated")


@pytest.mark.parametrize(
    "overlay,gap_substring",
    [
        ("tech_services", "Top customer revenue % not stated"),
        ("healthcare_services", "Top referral source/customer revenue % not stated"),
        ("tech_services", "NRR not stated"),
        ("tech_services", "GRR not stated"),
        ("tech_services", "Average account size (ACV) not stated"),
        ("healthcare_services", "Payor mix not stated"),
    ],
    ids=[
        "top_customer_pct_tech",
        "top_customer_pct_healthcare",
        "nrr_missing",
        "grr_missing",
        "acv_missing",
        "payor_mix_missing",
    ],
)
def test_missing_required_input_emits_gap(
    agent: CustomerQualityAgent, overlay: str, gap_substring: str
):
    extracted = _base_extracted()
    if "revenue % not stated" in gap_substring:
        extracted["top_customers"] = [
            {"customer_name": "X", "revenue_pct_yr1": "not stated", "source_doc": "rev.pdf"},
        ]
    elif gap_substring.startswith("NRR"):
        extracted["retention"].pop("nrr_pct", None)
    elif gap_substring.startswith("GRR"):
        extracted["retention"].pop("grr_pct", None)
    elif "ACV" in gap_substring:
        extracted["average_account_size"] = {}
    elif "Payor mix" in gap_substring:
        extracted["payor_mix"] = []
    agent._apply_customer_flags(extracted, overlay)
    assert _has_gap_substring(agent, gap_substring)
