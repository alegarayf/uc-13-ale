"""Hermetic tests for agent_base's token summary + llm_client backend/fallback reporting.

Derived from spec.md ASDK-11 AC2/AC3 and ASDK-06 AC6 (T12 "Done when"). Real
counters are exercised end-to-end (accumulate_tokens + llm_client's fallback
counter and per-endpoint backend record), not mocked, since the whole point
of this task is that the two modules' state stays consistent.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

from agents.shared import agent_base, llm_client  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_all_counters():
    agent_base.reset_token_counter()
    yield
    agent_base.reset_token_counter()


# --- ASDK-11 AC2: breakdown keys stay Databricks-style aliases -------------


def test_breakdown_keys_are_stable_databricks_style_aliases():
    agent_base.accumulate_tokens(
        {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        endpoint="databricks-claude-sonnet-4-6",
    )
    assert set(agent_base.get_token_breakdown()) == {"databricks-claude-sonnet-4-6"}


# --- ASDK-11 AC3: print_token_summary reports backend per endpoint --------


def test_summary_reports_backend_that_actually_served_the_endpoint(capsys):
    agent_base.accumulate_tokens(
        {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        endpoint="databricks-claude-sonnet-4-6",
    )
    llm_client._record_endpoint_backend("databricks-claude-sonnet-4-6", "anthropic")

    agent_base.print_token_summary()

    out = capsys.readouterr().out
    assert "databricks-claude-sonnet-4-6" in out
    assert "backend           : anthropic" in out


def test_summary_reports_databricks_backend_after_a_fallback(capsys):
    """The critical case this task exists for: LLM_BACKEND never changes
    mid-run, so an endpoint that degraded must still be reported as
    'databricks', not 'anthropic'."""
    agent_base.accumulate_tokens(
        {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        endpoint="databricks-claude-haiku-4-5",
    )
    llm_client._record_endpoint_backend("databricks-claude-haiku-4-5", "databricks")

    agent_base.print_token_summary()

    out = capsys.readouterr().out
    assert "backend           : databricks" in out


def test_embeddings_endpoint_defaults_to_databricks_backend(capsys):
    """databricks-bge-large-en never routes through llm_client -- it must
    still get a sensible backend label, not a KeyError or blank."""
    agent_base.accumulate_tokens(
        {"prompt_tokens": 20, "completion_tokens": 0, "total_tokens": 20},
        endpoint="databricks-bge-large-en",
    )
    agent_base.print_token_summary()
    out = capsys.readouterr().out
    assert "backend           : databricks" in out


def test_summary_reports_fallback_count(capsys):
    llm_client._record_fallback("databricks-claude-sonnet-4-6", RuntimeError("boom"))
    llm_client._record_fallback("databricks-claude-sonnet-4-6", RuntimeError("boom"))
    agent_base.print_token_summary()
    out = capsys.readouterr().out
    assert "LLM fallbacks : 2" in out


def test_summary_reports_zero_fallbacks_when_none_occurred(capsys):
    agent_base.print_token_summary()
    out = capsys.readouterr().out
    assert "LLM fallbacks : 0" in out


# --- ASDK-06 AC6 / reset wiring: reset_token_counter also resets llm_client ---


def test_reset_token_counter_also_resets_llm_client_fallback_count():
    llm_client._record_fallback("databricks-claude-sonnet-4-6", RuntimeError("boom"))
    assert llm_client.get_fallback_count() == 1
    agent_base.reset_token_counter()
    assert llm_client.get_fallback_count() == 0


def test_reset_token_counter_also_resets_endpoint_backends():
    llm_client._record_endpoint_backend("databricks-claude-sonnet-4-6", "anthropic")
    assert llm_client.get_endpoint_backends() == {"databricks-claude-sonnet-4-6": "anthropic"}
    agent_base.reset_token_counter()
    assert llm_client.get_endpoint_backends() == {}


# --- Pricing table: first-party Anthropic rates ----------------------------


def test_haiku_pricing_matches_anthropic_first_party_rate():
    pricing = agent_base._ENDPOINT_PRICING["databricks-claude-haiku-4-5"]
    assert pricing == {"input": 1.00, "output": 5.00}


def test_sonnet_pricing_matches_anthropic_first_party_rate():
    pricing = agent_base._ENDPOINT_PRICING["databricks-claude-sonnet-4-6"]
    assert pricing == {"input": 3.00, "output": 15.00}
