"""Hermetic tests for company_profiler.call_llm's conditional gateway dispatch.

Derived from spec.md ASDK-09 (T20 "Done when") and the T20 finding: llm_endpoint
is runtime-parametrized and legitimately resolves to Llama (standalone Phase
1-2 job, uc13_ingestion_pipeline.yml default) or Claude (Phase 1-5,
run_full_pipeline.py default). call_llm() must route to the gateway ONLY for
a known Claude alias, and keep using the raw deploy client for anything else
-- an unconditional dispatch would raise ValueError on the Llama path.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

from jobs.scripts import company_profiler  # noqa: E402


@patch("agents.shared.llm_client.chat")
def test_claude_endpoint_routes_through_the_gateway(mock_chat):
    mock_chat.return_value = ("profile json", {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2})
    raw_client = MagicMock()

    result = company_profiler.call_llm(raw_client, "databricks-claude-sonnet-4-6", "prompt text")

    assert result == "profile json"
    mock_chat.assert_called_once_with(
        system_prompt=None,
        user_content="prompt text",
        endpoint="databricks-claude-sonnet-4-6",
        max_tokens=1500,
        temperature=0.0,
    )
    raw_client.predict.assert_not_called()


@patch("agents.shared.llm_client.chat")
def test_llama_endpoint_bypasses_the_gateway_entirely(mock_chat):
    """The T20 finding: this must NOT raise ValueError from resolve_model()
    on the standalone Phase 1-2 job's default endpoint."""
    raw_client = MagicMock()
    raw_client.predict.return_value = {
        "choices": [{"message": {"content": "profile json"}}],
        "usage": {},
    }

    result = company_profiler.call_llm(
        raw_client, "databricks-meta-llama-3-3-70b-instruct", "prompt text"
    )

    assert result == "profile json"
    mock_chat.assert_not_called()
    raw_client.predict.assert_called_once()
    inputs = raw_client.predict.call_args.kwargs["inputs"]
    assert inputs["max_tokens"] == 1500
    assert inputs["temperature"] == 0.0
    assert inputs["messages"] == [{"role": "user", "content": "prompt text"}]


@patch("agents.shared.llm_client.chat")
def test_unknown_endpoint_also_bypasses_the_gateway(mock_chat):
    """Any endpoint outside _MODEL_MAP takes the raw-client path, not just
    the one Llama alias currently in use -- future-proofs the guard."""
    raw_client = MagicMock()
    raw_client.predict.return_value = {
        "choices": [{"message": {"content": "x"}}], "usage": {},
    }
    company_profiler.call_llm(raw_client, "databricks-some-future-model", "p")
    mock_chat.assert_not_called()
    raw_client.predict.assert_called_once()
