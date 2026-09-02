"""Regression test for the T23 finding: anthropic 1.x removed `temperature`
from messages.create()'s typed signature -- passing it as a direct kwarg is a
TypeError, not an API-level rejection. Every other llm_client test mocks
client.messages.create() entirely, so none of them ever exercised the SDK's
real method signature; this is the gap that let the bug reach a live job.

This test builds a REAL anthropic.Anthropic client wired to a fake HTTP
transport (httpx2.MockTransport) instead of mocking messages.create() itself.
The real Python method runs -- including its own kwarg validation -- and only
the network layer beneath it is faked. A future regression that reintroduces
an invalid kwarg (temperature or any other) raises the same real TypeError
here that it would in production, instead of being silently absorbed by a
MagicMock.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx2
import pytest

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

import anthropic  # noqa: E402

from agents.shared import llm_client  # noqa: E402


def _fake_messages_response(request: httpx2.Request) -> httpx2.Response:
    body = json.loads(request.content)
    return httpx2.Response(
        200,
        json={
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": body["model"],
            "content": [{"type": "text", "text": "real call succeeded"}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 5, "output_tokens": 3},
        },
        request=request,
    )


@pytest.fixture
def _real_client_fake_transport(monkeypatch):
    """A genuine anthropic.Anthropic instance -- messages.create() runs its
    real, version-specific kwarg validation -- backed by a mock HTTP
    transport so no network call happens."""
    transport = httpx2.MockTransport(_fake_messages_response)
    http_client = httpx2.Client(transport=transport)
    client = anthropic.Anthropic(api_key="sk-ant-test-not-real", http_client=http_client)
    monkeypatch.setattr(llm_client, "_get_anthropic_client", lambda: client)
    return client


def test_call_anthropic_temperature_survives_the_real_sdk_signature(
    _real_client_fake_transport,
):
    """The exact bug this test exists for: temperature=<float> as a direct
    kwarg to the real SDK's messages.create() raises TypeError on anthropic
    1.x. If _call_anthropic() ever regresses to passing it directly instead
    of via extra_body, this test fails with that same TypeError."""
    text, usage = llm_client._call_anthropic(
        system_prompt=None,
        user_content="hello",
        model_id="claude-sonnet-4-6",
        max_tokens=100,
        temperature=0.0,
    )
    assert text == "real call succeeded"
    assert usage == {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}


def test_temperature_reaches_the_wire_via_extra_body(_real_client_fake_transport):
    """Confirms the value isn't silently dropped when moved to extra_body --
    it must still reach the actual HTTP request body sent to the API."""
    captured = {}

    def _capturing_handler(request: httpx2.Request) -> httpx2.Response:
        captured["body"] = json.loads(request.content)
        return _fake_messages_response(request)

    _real_client_fake_transport._client = httpx2.Client(
        transport=httpx2.MockTransport(_capturing_handler)
    )

    llm_client._call_anthropic(
        system_prompt=None,
        user_content="hello",
        model_id="claude-sonnet-4-6",
        max_tokens=100,
        temperature=0.37,
    )
    assert captured["body"]["temperature"] == 0.37


def test_messages_create_signature_has_no_temperature_parameter():
    """Documents the exact SDK constraint this regression test guards against
    -- fails loudly if a future anthropic version restores temperature as a
    named parameter, which would mean extra_body is no longer necessary
    (a welcome change, but one to notice and simplify for, not silently keep
    working around)."""
    import inspect

    sig = inspect.signature(anthropic.resources.Messages.create)
    assert "temperature" not in sig.parameters
