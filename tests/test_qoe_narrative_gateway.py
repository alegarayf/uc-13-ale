"""Hermetic test for generate_qoe_assessment's LLM gateway delegation.

Derived from spec.md ASDK-09 (T17 "Done when"). Same shape as CQA (T16): the
narrative is split into sections via _extract_section() on the function's own
expected ### headers, so a mocked narrative renders the template defaults --
what T17 must prove is the call into the gateway itself.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

from agents.shared import agent_base  # noqa: E402
from agents.workstreams import quality_of_earnings_agent  # noqa: E402


@patch("agents.shared.llm_client.chat")
def test_generate_qoe_assessment_delegates_with_exact_arguments(mock_chat):
    mock_chat.return_value = ("### Some Section\nSome markdown.", {})

    result = quality_of_earnings_agent.generate_qoe_assessment(
        result={},
        spark=None,
        llm_endpoint="databricks-claude-sonnet-4-6",
        write_to_volume=False,
    )

    assert isinstance(result, str) and result
    assert mock_chat.call_count == 1
    kwargs = mock_chat.call_args.kwargs
    assert kwargs["endpoint"] == "databricks-claude-sonnet-4-6"
    assert kwargs["max_tokens"] == 3_000
    assert kwargs["temperature"] == 0.0
    assert isinstance(kwargs["system_prompt"], str) and kwargs["system_prompt"]
    assert isinstance(kwargs["user_content"], str) and kwargs["user_content"]


@patch("agents.shared.llm_client.chat")
def test_generate_qoe_assessment_does_not_construct_a_deploy_client(mock_chat):
    mock_chat.return_value = ("narrative text", {})
    with patch("mlflow.deployments.get_deploy_client") as mock_get_deploy:
        quality_of_earnings_agent.generate_qoe_assessment(
            result={},
            spark=None,
            llm_endpoint="databricks-claude-sonnet-4-6",
            write_to_volume=False,
        )
        mock_get_deploy.assert_not_called()


@patch("agents.shared.llm_client.chat")
def test_generate_qoe_assessment_accumulates_the_usage_gateway_returned(mock_chat):
    usage = {"prompt_tokens": 9, "completion_tokens": 6, "total_tokens": 15}
    mock_chat.return_value = ("narrative", usage)
    agent_base.reset_token_counter()

    quality_of_earnings_agent.generate_qoe_assessment(
        result={},
        spark=None,
        llm_endpoint="databricks-claude-sonnet-4-6",
        write_to_volume=False,
    )

    assert agent_base.get_token_breakdown()["databricks-claude-sonnet-4-6"] == usage
    agent_base.reset_token_counter()
