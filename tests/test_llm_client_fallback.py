"""Hermetic tests for llm_client's automatic Anthropic-to-Databricks fallback.

Derived from spec.md ASDK-05/ASDK-06/ASDK-07 (T10 "Done when"). Real SDK
exception instances (via httpx2.Response) drive the retryable/non-retryable
branches, same approach as test_llm_client_errors.py.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock

import httpx2
import pytest

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

import anthropic  # noqa: E402

from agents.shared import llm_client  # noqa: E402

_REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def _status_error(cls, status_code: int):
    response = httpx2.Response(status_code, request=_REQUEST)
    return cls(f"status {status_code}", response=response, body=None)


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    llm_client._client_state["client"] = None
    llm_client._databricks_client_state["client"] = None
    llm_client.reset_fallback_count()
    monkeypatch.setenv("LLM_BACKEND", "anthropic")
    yield
    llm_client._client_state["client"] = None
    llm_client._databricks_client_state["client"] = None
    llm_client.reset_fallback_count()


@pytest.fixture
def _anthropic_client(monkeypatch):
    client = MagicMock(name="anthropic_client")
    monkeypatch.setattr(llm_client, "_get_anthropic_client", lambda: client)
    return client


@pytest.fixture
def _databricks_client(monkeypatch):
    client = MagicMock(name="deploy_client")
    monkeypatch.setattr(llm_client, "_get_databricks_client", lambda: client)
    return client


def _call_chat():
    return llm_client.chat(
        system_prompt=None,
        user_content="x",
        endpoint="databricks-claude-sonnet-4-6",
        max_tokens=10,
    )


# --- ASDK-05 AC1/AC2: retryable failure degrades and logs -------------------


def test_connection_error_degrades_to_databricks_and_returns_its_result(
    _anthropic_client, _databricks_client, capsys
):
    _anthropic_client.messages.create.side_effect = anthropic.APIConnectionError(
        request=_REQUEST
    )
    _databricks_client.predict.return_value = {
        "choices": [{"message": {"content": "from databricks"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    text, usage = _call_chat()
    assert text == "from databricks"
    assert usage == {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
    out = capsys.readouterr().out
    assert "[llm_fallback]" in out
    assert "databricks-claude-sonnet-4-6" in out
    assert "APIConnectionError" in out
    assert llm_client.get_fallback_count() == 1
    # ASDK-06 AC5 on the branch that actually matters: exactly one serving call
    # when the fallback SUCCEEDS. test_fallback_attempted_exactly_once_not_looped
    # pins the same counts, but only with the serving call also failing -- so it
    # can never observe a duplicate call on the success path, because the first
    # raise short-circuits it. Without this pair of assertions a second
    # _call_databricks() after the try/except survives the whole suite.
    assert _anthropic_client.messages.create.call_count == 1
    assert _databricks_client.predict.call_count == 1


def test_5xx_status_error_also_degrades(_anthropic_client, _databricks_client):
    _anthropic_client.messages.create.side_effect = _status_error(
        anthropic.APIStatusError, 503
    )
    _databricks_client.predict.return_value = {
        "choices": [{"message": {"content": "ok"}}], "usage": {},
    }
    text, _ = _call_chat()
    assert text == "ok"
    assert llm_client.get_fallback_count() == 1


# --- ASDK-07: non-retryable failure propagates, no fallback attempted ------


def test_bad_request_error_propagates_without_calling_databricks(
    _anthropic_client, _databricks_client
):
    _anthropic_client.messages.create.side_effect = _status_error(
        anthropic.BadRequestError, 400
    )
    with pytest.raises(anthropic.BadRequestError):
        _call_chat()
    _databricks_client.predict.assert_not_called()
    assert llm_client.get_fallback_count() == 0


def test_refusal_does_not_degrade_to_databricks(_anthropic_client, _databricks_client):
    """A policy refusal is a content decision, not a backend outage -- must
    not silently re-ask the same prompt on a different model."""
    message = anthropic.types.Message(
        id="msg_test", type="message", role="assistant", model="claude-sonnet-4-6",
        content=[],
        stop_reason="refusal", stop_sequence=None,
        stop_details=anthropic.types.RefusalStopDetails(type="refusal", category="cyber"),
        usage=anthropic.types.Usage(input_tokens=1, output_tokens=0),
    )
    _anthropic_client.messages.create.return_value = message
    with pytest.raises(RuntimeError, match="cyber"):
        _call_chat()
    _databricks_client.predict.assert_not_called()
    assert llm_client.get_fallback_count() == 0


# --- ASDK-05 AC4: both backends fail -> Databricks exc raised, chained -----


def test_both_backends_failing_raises_databricks_exc_with_anthropic_chained(
    _anthropic_client, _databricks_client
):
    anthropic_exc = anthropic.APIConnectionError(request=_REQUEST)
    databricks_exc = RuntimeError("serving endpoint also down")
    _anthropic_client.messages.create.side_effect = anthropic_exc
    _databricks_client.predict.side_effect = databricks_exc

    with pytest.raises(RuntimeError, match="serving endpoint also down") as exc_info:
        _call_chat()
    assert exc_info.value.__cause__ is anthropic_exc
    assert llm_client.get_fallback_count() == 1


# --- ASDK-06 AC5: at most one fallback attempt, no retry loop --------------


def test_fallback_attempted_exactly_once_not_looped(_anthropic_client, _databricks_client):
    _anthropic_client.messages.create.side_effect = anthropic.APIConnectionError(
        request=_REQUEST
    )
    _databricks_client.predict.side_effect = anthropic.APIConnectionError(
        request=_REQUEST
    )
    with pytest.raises(anthropic.APIConnectionError):
        _call_chat()
    assert _anthropic_client.messages.create.call_count == 1
    assert _databricks_client.predict.call_count == 1
    assert llm_client.get_fallback_count() == 1


# --- ASDK-06 AC6: counter is thread-safe under concurrent fallbacks --------


def test_fallback_counter_thread_safe_under_concurrency(_anthropic_client, _databricks_client):
    _anthropic_client.messages.create.side_effect = anthropic.APIConnectionError(
        request=_REQUEST
    )
    _databricks_client.predict.return_value = {
        "choices": [{"message": {"content": "ok"}}], "usage": {},
    }

    def _worker():
        _call_chat()

    threads = [threading.Thread(target=_worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert llm_client.get_fallback_count() == 20


# --- LLM_BACKEND=databricks: no fallback machinery involved at all ---------


def test_databricks_backend_never_touches_fallback_counter(monkeypatch, _databricks_client):
    monkeypatch.setenv("LLM_BACKEND", "databricks")
    _databricks_client.predict.return_value = {
        "choices": [{"message": {"content": "ok"}}], "usage": {},
    }
    _call_chat()
    assert llm_client.get_fallback_count() == 0
