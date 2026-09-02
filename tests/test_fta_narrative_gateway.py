"""Hermetic test for generate_financial_assessment's LLM gateway delegation.

Derived from spec.md ASDK-09 (T15 "Done when"). Neither the narrative nor the
extraction call in this module accumulated tokens even before the migration
-- that pre-existing behavior is preserved, not changed.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

from agents.workstreams import financial_trends_agent  # noqa: E402


@patch("agents.shared.llm_client.chat")
def test_generate_financial_assessment_delegates_with_exact_arguments(mock_chat):
    mock_chat.return_value = ("## Financial Narrative\nSome markdown.", {})

    result = financial_trends_agent.generate_financial_assessment(
        result={},
        spark=None,
        llm_endpoint="databricks-claude-sonnet-4-6",
        write_to_volume=False,
    )

    assert "## Financial Narrative" in result
    assert mock_chat.call_count == 1
    kwargs = mock_chat.call_args.kwargs
    assert kwargs["endpoint"] == "databricks-claude-sonnet-4-6"
    assert kwargs["max_tokens"] == 2000
    assert kwargs["temperature"] == 0.1
    assert isinstance(kwargs["system_prompt"], str) and kwargs["system_prompt"]
    assert isinstance(kwargs["user_content"], str) and kwargs["user_content"]


@patch("agents.shared.llm_client.chat")
def test_generate_financial_assessment_does_not_construct_a_deploy_client(mock_chat):
    mock_chat.return_value = ("narrative text", {})
    with patch("mlflow.deployments.get_deploy_client") as mock_get_deploy:
        financial_trends_agent.generate_financial_assessment(
            result={},
            spark=None,
            llm_endpoint="databricks-claude-sonnet-4-6",
            write_to_volume=False,
        )
        mock_get_deploy.assert_not_called()
