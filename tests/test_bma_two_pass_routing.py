"""C37 hermetic falsifiers: context-size-gated BMA two-pass routing.

Mocks ``_call_llm``. Does not import live Spark/warehouse.
"""

from __future__ import annotations

import json

from agents.workstreams.business_model_agent import (
    _C39_COMMERCIAL_BREVITY,
    _C40_ORGANIZATIONAL_BREVITY,
    _COMMERCIAL_FIELD_KEYS,
    _ORGANIZATIONAL_FIELD_KEYS,
    _SYSTEM_PROMPT,
    _TWO_PASS_CONTEXT_CHARS,
    _USER_PROMPT_TEMPLATE,
    _should_use_two_pass,
    BusinessModelAgent,
)


def _agent_with_mock_llm(side_effect):
    agent = BusinessModelAgent()
    calls: list[tuple] = []

    def fake_llm(system_prompt, user_prompt, endpoint, max_tokens=12_000):
        calls.append(
            {
                "system": system_prompt,
                "user": user_prompt,
                "endpoint": endpoint,
                "max_tokens": max_tokens,
            }
        )
        return side_effect(len(calls), system_prompt, user_prompt, endpoint, max_tokens)

    agent._call_llm = fake_llm
    return agent, calls


def test_bma_two_pass_routing_below_threshold_uses_single_call() -> None:
    text = "x" * _TWO_PASS_CONTEXT_CHARS
    assert _should_use_two_pass(text) is False

    def replies(_n, _sys, _user, _ep, _tok):
        return json.dumps({"executive_summary": "single"})

    agent, calls = _agent_with_mock_llm(replies)
    extracted = agent._extract_structured(
        combined_chunk_text=text,
        company_profile_json='{"overlay":"healthcare"}',
        deal_type_context="DEAL TYPE: test",
        endpoint="databricks-claude-sonnet-4-6",
    )
    assert len(calls) == 1
    assert calls[0]["max_tokens"] == 8_000
    assert calls[0]["system"] is _SYSTEM_PROMPT
    assert text in calls[0]["user"]
    assert extracted["executive_summary"] == "single"
    assert "C37_FIELD_GROUP=" not in calls[0]["user"]


def test_bma_two_pass_routing_above_threshold_uses_two_calls() -> None:
    text = "y" * (_TWO_PASS_CONTEXT_CHARS + 1)
    assert _should_use_two_pass(text) is True

    def replies(_n, _sys, _user, _ep, _tok):
        return "{}"

    agent, calls = _agent_with_mock_llm(replies)
    agent._extract_structured(
        combined_chunk_text=text,
        company_profile_json="{}",
        deal_type_context="DEAL TYPE: test",
        endpoint="ep",
    )
    assert len(calls) == 2
    assert all(c["max_tokens"] == 8_000 for c in calls)
    assert all(c["system"] == _SYSTEM_PROMPT for c in calls)
    groups = {c["user"] for c in calls}
    assert any("C37_FIELD_GROUP=commercial" in u for u in groups)
    assert any("C37_FIELD_GROUP=organizational" in u for u in groups)


def test_bma_two_pass_merges_disjoint_field_groups() -> None:
    text = "z" * (_TWO_PASS_CONTEXT_CHARS + 1)
    commercial = {
        "executive_summary": "summary",
        "revenue_model": {"tag": "hybrid"},
        "products_services": [{"name": "Home care"}],
    }
    organizational = {
        "sales_motion": {"tag": "relationship"},
        "overlay_conflict_evidence": "none",
        "citations": [{"field": "revenue_model"}],
        "extraction_notes": "ok",
        "customer_operational_metrics": {"total_customers_or_accounts": "100"},
    }
    assert "customer_operational_metrics" not in commercial
    assert "customer_operational_metrics" in organizational
    assert "customer_operational_metrics" not in _COMMERCIAL_FIELD_KEYS
    assert "customer_operational_metrics" in _ORGANIZATIONAL_FIELD_KEYS

    def replies(n, _sys, user, _ep, _tok):
        if "C37_FIELD_GROUP=commercial" in user:
            return json.dumps(commercial)
        if "C37_FIELD_GROUP=organizational" in user:
            return json.dumps(organizational)
        raise AssertionError(f"unexpected two-pass prompt: {user[:200]}")

    agent, calls = _agent_with_mock_llm(replies)
    extracted = agent._extract_structured(
        combined_chunk_text=text,
        company_profile_json="{}",
        deal_type_context="DEAL TYPE: test",
        endpoint="ep",
    )
    assert len(calls) == 2
    assert extracted["executive_summary"] == "summary"
    assert extracted["revenue_model"]["tag"] == "hybrid"
    assert extracted["products_services"][0]["name"] == "Home care"
    assert extracted["sales_motion"]["tag"] == "relationship"
    assert extracted["overlay_conflict_evidence"] == "none"
    assert extracted["citations"][0]["field"] == "revenue_model"
    assert extracted["extraction_notes"] == "ok"
    for key in _ORGANIZATIONAL_FIELD_KEYS:
        if key in organizational:
            assert extracted[key] == organizational[key]


def test_bma_two_pass_does_not_reduce_input_context() -> None:
    marker = "UNIQUE_C37_CHUNK_MARKER_" + ("Q" * 64)
    text = marker + ("w" * (_TWO_PASS_CONTEXT_CHARS + 1))
    profile = '{"industry_overlay":"healthcare","probe":"PROFILE_TOKEN_C37"}'
    deal = "DEAL TYPE: Banked — CIM detected. UNIQUE_DEAL_TOKEN_C37"

    def replies(_n, _sys, _user, _ep, _tok):
        return "{}"

    agent, calls = _agent_with_mock_llm(replies)
    agent._extract_structured(
        combined_chunk_text=text,
        company_profile_json=profile,
        deal_type_context=deal,
        endpoint="ep",
    )
    assert len(calls) == 2
    for call in calls:
        user = call["user"]
        assert text in user
        assert marker in user
        assert profile in user
        assert deal in user
        assert user.count(text) == 1
        assert text[: len(text) // 2] in user


def test_bma_two_pass_commercial_prompt_has_c39_brevity() -> None:
    """C39 guidance is on the two-pass commercial prompt only."""
    marker = "C39_BREVITY"
    assert marker in _C39_COMMERCIAL_BREVITY
    assert "products_services" in _C39_COMMERCIAL_BREVITY
    assert "people_and_org" in _C39_COMMERCIAL_BREVITY
    assert "workforce_capacity" in _C39_COMMERCIAL_BREVITY
    assert marker not in _USER_PROMPT_TEMPLATE

    def replies(_n, _sys, _user, _ep, _tok):
        return "{}"

    two_pass_text = "y" * (_TWO_PASS_CONTEXT_CHARS + 1)
    agent, calls = _agent_with_mock_llm(replies)
    agent._extract_structured(
        combined_chunk_text=two_pass_text,
        company_profile_json="{}",
        deal_type_context="DEAL TYPE: test",
        endpoint="ep",
    )
    assert len(calls) == 2
    commercial = next(c for c in calls if "C37_FIELD_GROUP=commercial" in c["user"])
    organizational = next(c for c in calls if "C37_FIELD_GROUP=organizational" in c["user"])
    assert _C39_COMMERCIAL_BREVITY in commercial["user"]
    assert marker in commercial["user"]
    assert "at most 8 items" in commercial["user"]
    assert "at most 8 key_executives" in commercial["user"]
    assert "at most 10 headcount_by_function" in commercial["user"]
    assert _C39_COMMERCIAL_BREVITY not in organizational["user"]
    assert marker not in organizational["user"]
    assert "at most 8 items" not in organizational["user"]
    assert "at most 8 key_executives" not in organizational["user"]
    assert "at most 10 headcount_by_function" not in organizational["user"]

    single_text = "x" * _TWO_PASS_CONTEXT_CHARS
    agent_single, calls_single = _agent_with_mock_llm(replies)
    agent_single._extract_structured(
        combined_chunk_text=single_text,
        company_profile_json="{}",
        deal_type_context="DEAL TYPE: test",
        endpoint="ep",
    )
    assert len(calls_single) == 1
    assert "C37_FIELD_GROUP=" not in calls_single[0]["user"]
    assert _C39_COMMERCIAL_BREVITY not in calls_single[0]["user"]
    assert marker not in calls_single[0]["user"]
    assert "at most 8 items" not in calls_single[0]["user"]
    assert "at most 8 key_executives" not in calls_single[0]["user"]
    assert "at most 10 headcount_by_function" not in calls_single[0]["user"]


def test_bma_two_pass_organizational_prompt_has_c40_brevity() -> None:
    """C40 guidance is on the two-pass organizational prompt only."""
    marker = "C40_BREVITY"
    assert marker in _C40_ORGANIZATIONAL_BREVITY
    assert "recent_model_changes" in _C40_ORGANIZATIONAL_BREVITY
    assert "key_dependencies" in _C40_ORGANIZATIONAL_BREVITY
    assert "citations" in _C40_ORGANIZATIONAL_BREVITY
    assert marker not in _USER_PROMPT_TEMPLATE
    assert marker not in _C39_COMMERCIAL_BREVITY
    assert "C39_BREVITY" not in _C40_ORGANIZATIONAL_BREVITY
    assert "at most 8 items" not in _C40_ORGANIZATIONAL_BREVITY
    assert "at most 8 key_executives" not in _C40_ORGANIZATIONAL_BREVITY
    assert "at most 10 headcount_by_function" not in _C40_ORGANIZATIONAL_BREVITY

    def replies(_n, _sys, _user, _ep, _tok):
        return "{}"

    two_pass_text = "y" * (_TWO_PASS_CONTEXT_CHARS + 1)
    agent, calls = _agent_with_mock_llm(replies)
    agent._extract_structured(
        combined_chunk_text=two_pass_text,
        company_profile_json="{}",
        deal_type_context="DEAL TYPE: test",
        endpoint="ep",
    )
    assert len(calls) == 2
    commercial = next(c for c in calls if "C37_FIELD_GROUP=commercial" in c["user"])
    organizational = next(c for c in calls if "C37_FIELD_GROUP=organizational" in c["user"])
    assert _C40_ORGANIZATIONAL_BREVITY in organizational["user"]
    assert marker in organizational["user"]
    assert "at most 10 dated events" in organizational["user"]
    assert "at most 10 named dependencies" in organizational["user"]
    assert "at most 16 rows" in organizational["user"]
    assert _C39_COMMERCIAL_BREVITY in commercial["user"]
    assert _C40_ORGANIZATIONAL_BREVITY not in commercial["user"]
    assert marker not in commercial["user"]
    assert "at most 10 dated events" not in commercial["user"]
    assert "at most 10 named dependencies" not in commercial["user"]
    assert "at most 16 rows" not in commercial["user"]

    single_text = "x" * _TWO_PASS_CONTEXT_CHARS
    agent_single, calls_single = _agent_with_mock_llm(replies)
    agent_single._extract_structured(
        combined_chunk_text=single_text,
        company_profile_json="{}",
        deal_type_context="DEAL TYPE: test",
        endpoint="ep",
    )
    assert len(calls_single) == 1
    assert "C37_FIELD_GROUP=" not in calls_single[0]["user"]
    assert _C40_ORGANIZATIONAL_BREVITY not in calls_single[0]["user"]
    assert marker not in calls_single[0]["user"]
    assert "at most 10 dated events" not in calls_single[0]["user"]
    assert "at most 10 named dependencies" not in calls_single[0]["user"]
    assert "at most 16 rows" not in calls_single[0]["user"]
