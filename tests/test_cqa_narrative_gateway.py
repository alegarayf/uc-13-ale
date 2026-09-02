"""Hermetic test for generate_customer_quality_assessment's LLM gateway delegation.

Derived from spec.md ASDK-09 (T16 "Done when"). Unlike BMA/FTA, CQA's narrative
call already accumulated tokens via agent_base.accumulate_tokens() before the
migration -- that must be preserved with the usage llm_client.chat() returns.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

from agents.shared import agent_base  # noqa: E402
from agents.workstreams import customer_quality_agent  # noqa: E402


@patch("agents.shared.llm_client.chat")
def test_generate_customer_quality_assessment_delegates_with_exact_arguments(mock_chat):
    """The final markdown is assembled by _extract_section() splitting the
    narrative on its own expected ### headers -- a mocked narrative without
    those headers renders the template's defaults, which is unrelated to this
    task. What T16 must prove is the call into the gateway itself."""
    mock_chat.return_value = ("### Some Section\nSome markdown.", {})

    result = customer_quality_agent.generate_customer_quality_assessment(
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
def test_generate_customer_quality_assessment_does_not_construct_a_deploy_client(mock_chat):
    mock_chat.return_value = ("narrative text", {})
    with patch("mlflow.deployments.get_deploy_client") as mock_get_deploy:
        customer_quality_agent.generate_customer_quality_assessment(
            result={},
            spark=None,
            llm_endpoint="databricks-claude-sonnet-4-6",
            write_to_volume=False,
        )
        mock_get_deploy.assert_not_called()


@patch("agents.shared.llm_client.chat")
def test_generate_customer_quality_assessment_accumulates_the_usage_gateway_returned(mock_chat):
    usage = {"prompt_tokens": 11, "completion_tokens": 13, "total_tokens": 24}
    mock_chat.return_value = ("narrative", usage)
    agent_base.reset_token_counter()

    customer_quality_agent.generate_customer_quality_assessment(
        result={},
        spark=None,
        llm_endpoint="databricks-claude-sonnet-4-6",
        write_to_volume=False,
    )

    assert agent_base.get_token_breakdown()["databricks-claude-sonnet-4-6"] == usage
    agent_base.reset_token_counter()
