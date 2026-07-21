"""Deterministic fixture for BusinessModelAgent revenue-durability flag math.

Owned rule surface (Program Gate G2 — M1/M2 must not re-test these branches):
  - ``BusinessModelAgent._apply_revenue_durability_flag`` threshold logic:
    parsed recurring-% bands (≥70% Green, 40–70% Yellow, <40% Red);
    tag-only fallback for RECURRING_TAGS, REPEAT_TAGS, PROJECT_TAGS,
    ``hybrid``, and unrecognized/empty tags;
    ``flag_confidence`` (high / medium / low) from parsed-% vs tag-only branches.
"""

from __future__ import annotations

import pytest

from agents.workstreams.business_model_agent import BusinessModelAgent

_SOURCE_DOC = "uc13.classification.company_profile"


@pytest.fixture
def agent() -> BusinessModelAgent:
    return BusinessModelAgent()


@pytest.mark.parametrize(
    "pct_split,expected_severity",
    [
        ("75% recurring, 25% project", "Green"),
        ("70% recurring", "Green"),
        ("55% recurring", "Yellow"),
        ("40% recurring", "Yellow"),
        ("39% recurring", "Red"),
        ("10% recurring", "Red"),
    ],
)
def test_revenue_durability_parsed_pct_thresholds(agent, pct_split, expected_severity):
    severity, flag_confidence, _rule = agent._apply_revenue_durability_flag(
        "hybrid", pct_split, _SOURCE_DOC
    )
    assert severity == expected_severity
    assert flag_confidence == "high"


@pytest.mark.parametrize(
    "tag,expected_severity",
    [
        ("pure_recurring", "Green"),
        ("usage_based", "Green"),
        ("licensing", "Green"),
        ("repeat_services", "Yellow"),
        ("project_based", "Red"),
        ("transactional", "Red"),
        ("hybrid", "Yellow"),
    ],
)
def test_revenue_durability_tag_only_fallback(agent, tag, expected_severity):
    severity, flag_confidence, _rule = agent._apply_revenue_durability_flag(
        tag, None, _SOURCE_DOC
    )
    assert severity == expected_severity
    assert flag_confidence == "medium"


@pytest.mark.parametrize(
    "tag",
    [None, "", "unknown_model", "  "],
)
def test_revenue_durability_unrecognized_or_empty_tag_is_yellow_low_confidence(
    agent, tag
):
    severity, flag_confidence, rule = agent._apply_revenue_durability_flag(
        tag, None, _SOURCE_DOC
    )
    assert severity == "Yellow"
    assert flag_confidence == "low"
    assert "unclear or not extractable" in rule


def test_revenue_durability_parsed_pct_overrides_tag(agent):
    """When both a parseable % and a tag are present, threshold uses the %."""
    severity, flag_confidence, _rule = agent._apply_revenue_durability_flag(
        "project_based",
        "80% recurring",
        _SOURCE_DOC,
    )
    assert severity == "Green"
    assert flag_confidence == "high"


def test_revenue_durability_first_number_proxy_without_directional_label(agent):
    """Split strings without recurring/contracted/subscription use the first % as proxy."""
    severity, flag_confidence, _rule = agent._apply_revenue_durability_flag(
        None,
        "65% project, 35% other",
        _SOURCE_DOC,
    )
    assert severity == "Yellow"
    assert flag_confidence == "high"
