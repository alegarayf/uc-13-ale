"""Hermetic test for generate_business_model_assessment's LLM gateway delegation.

Derived from spec.md ASDK-09 (T14 "Done when"). This narrative call site
never accumulated tokens even before the migration -- that pre-existing
behavior is preserved, not changed, per the iso-behavior migration scope.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

from agents.workstreams import business_model_agent  # noqa: E402


def _minimal_result(**overrides) -> dict:
    base = {
        "company_name": "Acme Co",
        "created_at": "2026-09-02",
        "flags": [],
        "data_room_gaps": [],
    }
    base.update(overrides)
    return base


@patch("agents.shared.llm_client.chat")
def test_generate_business_model_assessment_delegates_with_exact_arguments(mock_chat):
    mock_chat.return_value = ("## Narrative\nSome markdown.", {})

    result = business_model_agent.generate_business_model_assessment(
        result=_minimal_result(),
        spark=None,
        llm_endpoint="databricks-claude-sonnet-4-6",
        write_to_volume=False,
    )

    assert "## Narrative" in result
    assert mock_chat.call_count == 1
    kwargs = mock_chat.call_args.kwargs
    assert kwargs["endpoint"] == "databricks-claude-sonnet-4-6"
    assert kwargs["max_tokens"] == 3000
    assert kwargs["temperature"] == 0.1
    assert isinstance(kwargs["system_prompt"], str) and kwargs["system_prompt"]
    assert isinstance(kwargs["user_content"], str) and kwargs["user_content"]


@patch("agents.shared.llm_client.chat")
def test_generate_business_model_assessment_does_not_construct_a_deploy_client(mock_chat):
    """The module must no longer build its own mlflow.deployments client for
    a claude endpoint -- confirms the migration, not just the delegation."""
    mock_chat.return_value = ("narrative text", {})
    with patch("mlflow.deployments.get_deploy_client") as mock_get_deploy:
        business_model_agent.generate_business_model_assessment(
            result=_minimal_result(),
            spark=None,
            llm_endpoint="databricks-claude-sonnet-4-6",
            write_to_volume=False,
        )
        mock_get_deploy.assert_not_called()
