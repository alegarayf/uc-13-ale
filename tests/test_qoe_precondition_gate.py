"""QoE FTA-dependency precondition-gate fixture (M2-T3).

Rules covered:
  - ``_load_addback_passthrough``: H2 presence-bar — non-empty parsed
    ``addback_schedule_json`` → non-empty ``list[dict]``; absent row, SQL NULL,
    empty-array JSON (``"[]"``), or query failure → ``[]`` plus gap note.
  - Test-local ``_adjust_checklist_total``: denominator ``M = N`` when the
    precondition passes; ``M = N - tier_classification_item_count`` on failure.

Decision-D exclusion (owned by ``tests/test_qoe_tier_classification.py``):
  downstream tier-classification math and ``_apply_qofe_flags`` are out of scope.
"""

from __future__ import annotations

import json

import pytest

from agents.workstreams.quality_of_earnings_agent import QualityOfEarningsAgent

_COMPANY = "Elder Care"
_CATALOG = "uc13_ale"


class _StubSparkResult:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def collect(self) -> list[dict]:
        return self._rows


class _StubSpark:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self.sql_calls: list[str] = []

    def sql(self, query: str) -> _StubSparkResult:
        self.sql_calls.append(query)
        return _StubSparkResult(self._rows)


class _RaisingStubSpark:
    def sql(self, query: str) -> _StubSparkResult:
        raise RuntimeError("simulated spark failure")


def _agent_with_catalog() -> QualityOfEarningsAgent:
    agent = QualityOfEarningsAgent()
    agent._catalog = _CATALOG
    return agent


def _adjust_checklist_total(
    nominal_total: int,
    precondition_passed: bool,
    tier_classification_item_count: int,
) -> int:
    """Illustrative denominator adjustment for precondition-gated scoring (test-local only)."""
    if precondition_passed:
        return nominal_total
    return nominal_total - tier_classification_item_count


def test_load_addback_passthrough_returns_non_empty_list_when_schedule_present():
    schedule = [
        {
            "description": "Owner compensation normalization",
            "amount_dollars": "50000",
            "tier_classification": "Tier 2",
        },
    ]
    spark = _StubSpark([{"addback_schedule_json": json.dumps(schedule)}])
    agent = _agent_with_catalog()

    result = agent._load_addback_passthrough(_COMPANY, spark)

    assert result == schedule
    assert agent._data_room_gaps == []
    assert _CATALOG in spark.sql_calls[0]
    assert _COMPANY in spark.sql_calls[0]


@pytest.mark.parametrize(
    "spark, expect_gap",
    [
        (_StubSpark([]), True),
        (_StubSpark([{"addback_schedule_json": None}]), True),
        (_StubSpark([{"addback_schedule_json": "[]"}]), False),
        (_RaisingStubSpark(), True),
    ],
    ids=["no_row", "column_null", "empty_array_json", "query_raises"],
)
def test_load_addback_passthrough_returns_empty_list_on_presence_bar_fail(spark, expect_gap):
    agent = _agent_with_catalog()

    result = agent._load_addback_passthrough(_COMPANY, spark)

    assert result == []
    if expect_gap:
        assert len(agent._data_room_gaps) == 1
        assert "addback_schedule_json not found" in agent._data_room_gaps[0]
        assert "Financial Trends Agent" in agent._data_room_gaps[0]
    else:
        assert agent._data_room_gaps == []


def test_load_addback_passthrough_returns_empty_list_when_json_malformed():
    """Falsifier: truthy but invalid JSON must not pass the presence bar."""
    spark = _StubSpark([{"addback_schedule_json": "{not-valid-json"}])
    agent = _agent_with_catalog()

    result = agent._load_addback_passthrough(_COMPANY, spark)

    assert result == []
    assert len(agent._data_room_gaps) == 1


@pytest.mark.parametrize(
    "precondition_passed, expected_total",
    [
        (True, 6),
        (False, 5),
    ],
    ids=["pass_m_equals_n", "fail_m_excludes_tier_classification"],
)
def test_adjust_checklist_total_denominator_branches(precondition_passed, expected_total):
    nominal_total = 6
    tier_classification_item_count = 1

    assert (
        _adjust_checklist_total(
            nominal_total,
            precondition_passed,
            tier_classification_item_count,
        )
        == expected_total
    )
