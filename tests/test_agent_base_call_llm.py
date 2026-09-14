"""Hermetic tests for WorkstreamAgent._call_llm's delegation to the LLM gateway.

Derived from spec.md ASDK-09 (T13 "Done when"). _call_llm() must keep its
public signature and default max_tokens=12_000 while its body now delegates
to llm_client.chat() instead of building its own mlflow.deployments client.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

from agents.shared.agent_base import WorkstreamAgent  # noqa: E402


@patch("agents.shared.agent_base.llm_client.chat")
def test_call_llm_delegates_to_gateway_with_exact_arguments(mock_chat):
    mock_chat.return_value = ("the answer", {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7})

    result = WorkstreamAgent()._call_llm(
        system_prompt="be terse",
        user_prompt="what is 2+2",
        endpoint="databricks-claude-sonnet-4-6",
        max_tokens=16_000,
    )

    assert result == "the answer"
    mock_chat.assert_called_once_with(
        system_prompt="be terse",
        user_content="what is 2+2",
        endpoint="databricks-claude-sonnet-4-6",
        max_tokens=16_000,
        temperature=0.0,
    )


@patch("agents.shared.agent_base.llm_client.chat")
def test_call_llm_default_max_tokens_is_12000(mock_chat):
    mock_chat.return_value = ("x", {})
    WorkstreamAgent()._call_llm(
        system_prompt="s", user_prompt="u", endpoint="databricks-claude-sonnet-4-6",
    )
    assert mock_chat.call_args.kwargs["max_tokens"] == 12_000


@patch("agents.shared.agent_base.llm_client.chat")
def test_call_llm_accumulates_the_usage_gateway_returned(mock_chat):
    usage = {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7}
    mock_chat.return_value = ("x", usage)
    from agents.shared import agent_base

    agent_base.reset_token_counter()
    WorkstreamAgent()._call_llm(
        system_prompt="s", user_prompt="u", endpoint="databricks-claude-sonnet-4-6",
    )
    assert agent_base.get_token_breakdown()["databricks-claude-sonnet-4-6"] == usage
    agent_base.reset_token_counter()
