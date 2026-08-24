"""Unit tests for FTA revenue_sub_agent row dedupe and source_location fill."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

from agents.subagents.workstream.financial.revenue_sub_agent import (  # noqa: E402
    _CUSTOMER_DEDUPE_KEY,
    _SEGMENT_DEDUPE_KEY,
    _USER_PROMPT,
    _apply_revenue_list_contracts,
    dedupe_rows_by_key,
    RevenueSubAgent,
)


def test_dedupe_rows_by_key_preserves_first_occurrence():
    first = {
        "segment": "Westchester",
        "period": "2023A",
        "revenue_dollars": "7,042",
        "source_doc": "CIM.pdf",
    }
    duplicate = {
        "segment": "Westchester",
        "period": "2023A",
        "revenue_dollars": "7,042",
        "source_doc": "other.xlsx",
    }
    other = {
        "segment": "Long Island",
        "period": "2023A",
        "revenue_dollars": "229",
        "source_doc": "CIM.pdf",
    }
    out = dedupe_rows_by_key(
        [first, other, duplicate],
        ("segment", "period", "revenue_dollars"),
    )
    assert out == [first, other]


def test_dedupe_rows_by_key_retains_rows_missing_any_key_field():
    """C3 safety: missing key fields must not collapse, even when other fields match.

    If this used ``row.get(field)`` and treated a missing key as None, the two
    incomplete Westchester rows would collapse. They must both be retained.
    """
    incomplete_a = {"segment": "Westchester", "period": "2023A", "source_doc": "A"}
    incomplete_b = {"segment": "Westchester", "period": "2023A", "source_doc": "B"}
    complete = {
        "segment": "Westchester",
        "period": "2023A",
        "revenue_dollars": "7,042",
        "source_doc": "CIM.pdf",
    }
    out = dedupe_rows_by_key(
        [incomplete_a, incomplete_b, complete],
        ("segment", "period", "revenue_dollars"),
    )
    assert out == [incomplete_a, incomplete_b, complete]


def test_dedupe_rows_by_key_collapses_present_none_values():
    """A present key with JSON-null is not 'missing'; identical None tuples collapse."""
    a = {"segment": None, "period": "2023A", "revenue_dollars": "1"}
    b = {"segment": None, "period": "2023A", "revenue_dollars": "1"}
    out = dedupe_rows_by_key([a, b], ("segment", "period", "revenue_dollars"))
    assert out == [a]


def test_dedupe_rows_by_key_retains_unhashable_key_values():
    """C3 Landed (R9): a present unhashable key field must retain the row, not raise.

    Audit F-7 / A-8: ``{"segment": ["NYC","LI"], ...}`` raised
    ``TypeError: unhashable type: 'list'`` at ``seen.add(key)`` and aborted
    ``RevenueSubAgent.run``. If this guard is removed, this test fails with
    that TypeError. Hashable-but-wrong values (e.g. an int where a string is
    expected) still participate in dedupe — only the TypeError path is amended.
    """
    list_valued = {
        "segment": ["NYC", "LI"],
        "period": "2023A",
        "revenue_dollars": "1",
    }
    dict_valued = {
        "segment": {"name": "NYC"},
        "period": "2023A",
        "revenue_dollars": "1",
    }
    list_valued_dup = {
        "segment": ["NYC", "LI"],
        "period": "2023A",
        "revenue_dollars": "1",
        "source_doc": "other.xlsx",
    }
    numeric_a = {"segment": 1, "period": "2023A", "revenue_dollars": "1"}
    numeric_b = {"segment": 1, "period": "2023A", "revenue_dollars": "1"}
    out = dedupe_rows_by_key(
        [list_valued, dict_valued, list_valued_dup, numeric_a, numeric_b],
        ("segment", "period", "revenue_dollars"),
    )
    assert out == [list_valued, dict_valued, list_valued_dup, numeric_a]


def test_apply_contracts_fills_omitted_source_location_without_dropping():
    parsed = _apply_revenue_list_contracts(
        {
            "revenue_by_segment": [
                {
                    "segment": "NYC",
                    "period": "2023A",
                    "revenue_dollars": "1,525",
                    "source_doc": "CIM.pdf",
                }
            ],
            "revenue_by_customer": [
                {
                    "customer_name": "Customer [1]",
                    "period": "2023A",
                    "revenue_dollars": "100",
                    "source_doc": "CIM.pdf",
                    "source_location": "Page 12",
                }
            ],
        }
    )
    assert parsed["revenue_by_segment"][0]["source_location"] is None
    assert parsed["revenue_by_customer"][0]["source_location"] == "Page 12"


def test_prompt_schema_includes_source_location_on_segment_and_customer():
    segment_block = _USER_PROMPT.split('"revenue_by_segment"')[1].split(
        '"revenue_by_customer"'
    )[0]
    customer_block = _USER_PROMPT.split('"revenue_by_customer"')[1]
    assert "source_location" in segment_block
    assert "source_location" in customer_block


def test_landed_dedupe_keys_match_prompt_schema_fields():
    assert _SEGMENT_DEDUPE_KEY == ("segment", "period", "revenue_dollars")
    assert _CUSTOMER_DEDUPE_KEY == ("customer_name", "period", "revenue_dollars")


def test_run_applies_contracts_immediately_after_json_parse():
    src = inspect.getsource(RevenueSubAgent.run)
    assert "parsed = _apply_revenue_list_contracts(_wa._parse_json_response(raw))" in src


def test_run_dedupes_segment_rows_and_fills_source_location():
    duplicate_payload = {
        "revenue_by_segment": [
            {
                "segment": "Westchester",
                "period": "2023A",
                "revenue_dollars": "7,042",
                "source_doc": "CIM.pdf",
            },
            {
                "segment": "Westchester",
                "period": "2023A",
                "revenue_dollars": "7,042",
                "source_doc": "CIM.pdf",
            },
        ],
        "revenue_by_customer": [
            {
                "customer_name": "Customer [1]",
                "period": "2023A",
                "revenue_dollars": "100",
                "source_doc": "CIM.pdf",
            }
        ],
    }
    fake_wa = SimpleNamespace(
        _call_llm=lambda *a, **k: "{}",
        _parse_json_response=lambda raw: duplicate_payload,
        _data_room_gaps=[],
    )
    agent = RevenueSubAgent()
    with patch.object(RevenueSubAgent, "_retrieve", return_value=[]), patch.object(
        RevenueSubAgent, "_make_base", return_value=fake_wa
    ), patch(
        "agents.subagents.workstream.financial.revenue_sub_agent.build_focused_context",
        return_value=("", "stats"),
    ):
        result = agent.run("Elder Care", spark=None, llm_endpoint="x", company_profile={})

    segments = result["extracted"]["revenue_by_segment"]
    customers = result["extracted"]["revenue_by_customer"]
    assert len(segments) == 1
    assert segments[0]["source_location"] is None
    assert len(customers) == 1
    assert customers[0]["source_location"] is None
