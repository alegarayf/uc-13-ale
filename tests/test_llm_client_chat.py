"""Hermetic tests for llm_client.chat() and its two backend routes.

Derived from spec.md ASDK-01/ASDK-04 and the edge cases for stop_reason
handling (T9 "Done when"). No fallback logic yet -- that's T10. Responses are
built as real anthropic.types.Message instances (not approximated dicts) so
the attribute access in _call_anthropic (response.stop_reason,
response.content[i].type, response.stop_details.category) is exercised
against the actual SDK shape.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

import anthropic  # noqa: E402

from agents.shared import llm_client  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_client_caches():
    llm_client._client_state["client"] = None
    llm_client._databricks_client_state["client"] = None
    yield
    llm_client._client_state["client"] = None
    llm_client._databricks_client_state["client"] = None


def _message(
    *,
    text: str | None = "hello",
    stop_reason: str = "end_turn",
    stop_details=None,
    input_tokens: int = 10,
    output_tokens: int = 5,
):
    content = [anthropic.types.TextBlock(type="text", text=text)] if text is not None else []
    return anthropic.types.Message(
        id="msg_test",
        type="message",
        role="assistant",
        model="claude-sonnet-4-6",
        content=content,
        stop_reason=stop_reason,
        stop_sequence=None,
        stop_details=stop_details,
        usage=anthropic.types.Usage(input_tokens=input_tokens, output_tokens=output_tokens),
    )


@pytest.fixture
def _anthropic_client(monkeypatch):
    """Stub the Anthropic client's messages.create, bypassing credential setup."""
    client = MagicMock(name="anthropic_client")
    monkeypatch.setattr(llm_client, "_get_anthropic_client", lambda: client)
    monkeypatch.setenv("LLM_BACKEND", "anthropic")
    return client


@pytest.fixture
def _databricks_client(monkeypatch):
    client = MagicMock(name="deploy_client")
    monkeypatch.setattr(llm_client, "_get_databricks_client", lambda: client)
    monkeypatch.setenv("LLM_BACKEND", "databricks")
    return client


# --- ASDK-01 AC1: chat() returns (text, usage) for both backends -----------


def test_chat_anthropic_backend_returns_text_and_normalized_usage(_anthropic_client):
    _anthropic_client.messages.create.return_value = _message(text="the answer")
    text, usage = llm_client.chat(
        system_prompt="be terse",
        user_content="what is 2+2",
        endpoint="databricks-claude-sonnet-4-6",
        max_tokens=100,
    )
    assert text == "the answer"
    assert usage == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


def test_chat_databricks_backend_returns_text_and_passthrough_usage(_databricks_client):
    _databricks_client.predict.return_value = {
        "choices": [{"message": {"content": "the answer"}}],
        "usage": {"prompt_tokens": 8, "completion_tokens": 3, "total_tokens": 11},
    }
    text, usage = llm_client.chat(
        system_prompt="be terse",
        user_content="what is 2+2",
        endpoint="databricks-claude-sonnet-4-6",
        max_tokens=100,
    )
    assert text == "the answer"
    assert usage == {"prompt_tokens": 8, "completion_tokens": 3, "total_tokens": 11}


# --- ASDK-04: max_tokens and temperature pass through unmodified -----------


def test_chat_anthropic_passes_max_tokens_and_temperature_exactly(_anthropic_client):
    _anthropic_client.messages.create.return_value = _message()
    llm_client.chat(
        system_prompt=None,
        user_content="x",
        endpoint="databricks-claude-haiku-4-5",
        max_tokens=8_192,
        temperature=0.1,
    )
    kwargs = _anthropic_client.messages.create.call_args.kwargs
    assert kwargs["max_tokens"] == 8_192
    # temperature travels via extra_body, not a direct kwarg -- anthropic 1.x
    # removed it from messages.create()'s typed signature (T23 finding,
    # 2026-09-02); see test_llm_client_real_sdk_call_shape.py for the
    # real-SDK regression test.
    assert kwargs["extra_body"] == {"temperature": 0.1}
    assert kwargs["model"] == "claude-haiku-4-5"


def test_chat_databricks_passes_max_tokens_and_temperature_exactly(_databricks_client):
    _databricks_client.predict.return_value = {
        "choices": [{"message": {"content": "x"}}],
        "usage": {},
    }
    llm_client.chat(
        system_prompt=None,
        user_content="x",
        endpoint="databricks-claude-sonnet-4-6",
        max_tokens=16_000,
        temperature=0.1,
    )
    inputs = _databricks_client.predict.call_args.kwargs["inputs"]
    assert inputs["max_tokens"] == 16_000
    assert inputs["temperature"] == 0.1


# --- system_prompt=None: no system role sent (document_classifier / profiler shape) --


def test_chat_anthropic_omits_system_when_none(_anthropic_client):
    _anthropic_client.messages.create.return_value = _message()
    llm_client.chat(
        system_prompt=None, user_content="x", endpoint="databricks-claude-sonnet-4-6",
        max_tokens=10,
    )
    assert "system" not in _anthropic_client.messages.create.call_args.kwargs


def test_chat_databricks_omits_system_role_when_none(_databricks_client):
    _databricks_client.predict.return_value = {
        "choices": [{"message": {"content": "x"}}], "usage": {},
    }
    llm_client.chat(
        system_prompt=None, user_content="x", endpoint="databricks-claude-sonnet-4-6",
        max_tokens=10,
    )
    messages = _databricks_client.predict.call_args.kwargs["inputs"]["messages"]
    assert [m["role"] for m in messages] == ["user"]


# --- stop_reason == "max_tokens": partial text returned, no raise ----------


def test_chat_anthropic_max_tokens_stop_reason_returns_partial_text(_anthropic_client):
    _anthropic_client.messages.create.return_value = _message(
        text='{"partial": "json cut off', stop_reason="max_tokens"
    )
    text, _ = llm_client.chat(
        system_prompt=None, user_content="x", endpoint="databricks-claude-sonnet-4-6",
        max_tokens=10,
    )
    assert text == '{"partial": "json cut off'


# --- stop_reason == "refusal": raises naming the category ------------------


def test_chat_anthropic_refusal_raises_naming_category(_anthropic_client):
    details = anthropic.types.RefusalStopDetails(type="refusal", category="cyber")
    _anthropic_client.messages.create.return_value = _message(
        text=None, stop_reason="refusal", stop_details=details
    )
    with pytest.raises(RuntimeError, match="cyber"):
        llm_client.chat(
            system_prompt=None, user_content="x", endpoint="databricks-claude-sonnet-4-6",
            max_tokens=10,
        )


# --- no text block in response: returns "" and warns, doesn't raise --------


def test_chat_anthropic_no_text_block_returns_empty_string(_anthropic_client, capsys):
    _anthropic_client.messages.create.return_value = _message(text=None)
    text, _ = llm_client.chat(
        system_prompt=None, user_content="x", endpoint="databricks-claude-sonnet-4-6",
        max_tokens=10,
    )
    assert text == ""
    assert "no text block" in capsys.readouterr().out
