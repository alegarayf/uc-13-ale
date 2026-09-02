"""Hermetic test for generate_kpi_assessment's LLM gateway delegation.

Derived from spec.md ASDK-09 (T18 "Done when"). Same shape as CQA/QoE: the
narrative is split into sections via _extract_section() on numbered ###
headers, so a mocked narrative renders the template defaults -- what T18 must
prove is the call into the gateway itself. KPIAgentEndpoint is untouched.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

from agents.shared import agent_base  # noqa: E402
from agents.workstreams import kpi_agent  # noqa: E402


@patch("agents.shared.llm_client.chat")
def test_generate_kpi_assessment_delegates_with_exact_arguments(mock_chat):
    mock_chat.return_value = ("### 1. Utilization & Delivery Efficiency\nSome markdown.", {})

    result = kpi_agent.generate_kpi_assessment(
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
def test_generate_kpi_assessment_does_not_construct_a_deploy_client(mock_chat):
    mock_chat.return_value = ("narrative text", {})
    with patch("mlflow.deployments.get_deploy_client") as mock_get_deploy:
        kpi_agent.generate_kpi_assessment(
            result={},
            spark=None,
            llm_endpoint="databricks-claude-sonnet-4-6",
            write_to_volume=False,
        )
        mock_get_deploy.assert_not_called()


@patch("agents.shared.llm_client.chat")
def test_generate_kpi_assessment_accumulates_the_usage_gateway_returned(mock_chat):
    usage = {"prompt_tokens": 7, "completion_tokens": 5, "total_tokens": 12}
    mock_chat.return_value = ("narrative", usage)
    agent_base.reset_token_counter()

    kpi_agent.generate_kpi_assessment(
        result={},
        spark=None,
        llm_endpoint="databricks-claude-sonnet-4-6",
        write_to_volume=False,
    )

    assert agent_base.get_token_breakdown()["databricks-claude-sonnet-4-6"] == usage
    agent_base.reset_token_counter()


def test_kpi_agent_endpoint_class_is_untouched():
    """KPIAgentEndpoint delegates run() to KPIAgent() -- not this narrative
    function -- and must not be modified by this migration."""
    endpoint_cls = kpi_agent.KPIAgentEndpoint
    assert endpoint_cls.agent_name == "kpi"
    assert "run" in vars(endpoint_cls)
