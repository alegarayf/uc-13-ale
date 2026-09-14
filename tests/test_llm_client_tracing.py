"""Hermetic tests for llm_client's MLflow instrumentation.

Derived from spec.md ASDK-10 (T11 "Done when"), amended in Design after two
confirmed findings (design.md R-1; ASDK-13 egress gate, 2026-09-01): MLflow's
autolog is tested only against anthropic 0.55.0-0.107.1, and this project runs
1.3.0 -- outside that range in this real environment, not hypothetically. So
manual spans are the PRIMARY mechanism; autolog is opportunistic enrichment.
Both branches (in-range and out-of-range) are tested regardless, since a
future MLflow release could widen the tested range.
"""

from __future__ import annotations

import sys
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


def _message(text="hi"):
    return anthropic.types.Message(
        id="msg_test", type="message", role="assistant", model="claude-sonnet-4-6",
        content=[anthropic.types.TextBlock(type="text", text=text)],
        stop_reason="end_turn", stop_sequence=None,
        usage=anthropic.types.Usage(input_tokens=4, output_tokens=2),
    )


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    llm_client._client_state["client"] = None
    llm_client._databricks_client_state["client"] = None
    llm_client._autolog_state["attempted"] = False
    llm_client.reset_fallback_count()
    monkeypatch.setenv("LLM_BACKEND", "anthropic")
    yield
    llm_client._client_state["client"] = None
    llm_client._databricks_client_state["client"] = None
    llm_client._autolog_state["attempted"] = False
    llm_client.reset_fallback_count()


@pytest.fixture
def _anthropic_client(monkeypatch):
    client = MagicMock(name="anthropic_client")
    client.messages.create.return_value = _message()
    monkeypatch.setattr(llm_client, "_get_anthropic_client", lambda: client)
    return client


class _FakeSpan:
    def __init__(self):
        self.attributes: dict = {}

    def set_attributes(self, attrs):
        self.attributes.update(attrs)


class _FakeSpanCM:
    """Mimics the object mlflow.start_span() returns: a context manager whose
    __enter__ yields a span-like object recording set_attributes calls."""

    def __init__(self):
        self.span = _FakeSpan()
        self.exit_args = None

    def __enter__(self):
        return self.span

    def __exit__(self, exc_type, exc, tb):
        self.exit_args = (exc_type, exc, tb)
        return False


@pytest.fixture
def _fake_span(monkeypatch):
    fake_cm = _FakeSpanCM()
    fake_mlflow = MagicMock()
    fake_mlflow.start_span.return_value = fake_cm
    monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow)
    return fake_cm


def _call_chat(**overrides):
    kwargs = dict(
        system_prompt=None, user_content="x",
        endpoint="databricks-claude-sonnet-4-6", max_tokens=10,
    )
    kwargs.update(overrides)
    return llm_client.chat(**kwargs)


# --- ASDK-10 AC1: span attributes on success --------------------------------


def test_span_records_model_backend_and_tokens_on_success(_anthropic_client, _fake_span):
    _call_chat()
    attrs = _fake_span.span.attributes
    assert attrs["llm.endpoint_alias"] == "databricks-claude-sonnet-4-6"
    assert attrs["llm.backend"] == "anthropic"
    assert attrs["llm.fallback_used"] is False
    assert attrs["llm.max_tokens"] == 10
    assert attrs["llm.prompt_tokens"] == 4
    assert attrs["llm.completion_tokens"] == 2


def test_span_never_contains_the_api_key(_anthropic_client, _fake_span, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-super-secret-value")
    _call_chat()
    assert "sk-ant-super-secret-value" not in repr(_fake_span.span.attributes)


def test_span_records_fallback_used_true_on_degradation(
    _anthropic_client, _fake_span, monkeypatch
):
    _anthropic_client.messages.create.side_effect = anthropic.APIConnectionError(
        request=_REQUEST
    )
    databricks_client = MagicMock(name="deploy_client")
    databricks_client.predict.return_value = {
        "choices": [{"message": {"content": "ok"}}], "usage": {},
    }
    monkeypatch.setattr(llm_client, "_get_databricks_client", lambda: databricks_client)
    _call_chat()
    attrs = _fake_span.span.attributes
    assert attrs["llm.fallback_used"] is True
    assert attrs["llm.backend"] == "databricks"


# --- ASDK-10 AC5: span nests under the currently active span (no new trace root) --


def test_span_opened_via_mlflow_start_span_so_it_nests_under_the_active_span(
    _anthropic_client, _fake_span
):
    """chat() must call mlflow.start_span(), not create a separate trace --
    start_span() nests under whatever span pipeline.py's agent::{key} already
    opened, by MLflow's own context-manager semantics."""
    import mlflow

    _call_chat()
    mlflow.start_span.assert_called_once_with(name="llm_client.chat")


# --- ASDK-10 AC2: MLflow unavailable -> call still completes ---------------


def test_mlflow_import_failure_still_completes_the_call(_anthropic_client, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "mlflow", None)
    text, usage = _call_chat()
    assert text == "hi"
    assert usage == {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6}
    assert "MLflow tracing unavailable" in capsys.readouterr().out


def test_start_span_raising_still_completes_the_call(_anthropic_client, monkeypatch, capsys):
    fake_mlflow = MagicMock()
    fake_mlflow.start_span.side_effect = RuntimeError("tracking store unreachable")
    monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow)
    text, _ = _call_chat()
    assert text == "hi"
    assert "MLflow tracing unavailable" in capsys.readouterr().out


def test_chat_error_still_propagates_when_span_exit_captures_it(
    _anthropic_client, _fake_span
):
    """A genuine chat failure must propagate -- tracing plumbing must never
    swallow it."""
    _anthropic_client.messages.create.side_effect = anthropic.BadRequestError(
        "bad request",
        response=httpx2.Response(400, request=_REQUEST),
        body=None,
    )
    with pytest.raises(anthropic.BadRequestError):
        _call_chat()
    assert _fake_span.exit_args[0] is anthropic.BadRequestError


# --- ASDK-10 AC3/AC4: autolog gated on installed version --------------------


@pytest.fixture
def _fake_mlflow_anthropic(_fake_span, monkeypatch):
    """`import mlflow.anthropic` needs BOTH sys.modules["mlflow.anthropic"]
    populated AND the submodule set as an attribute on the parent module
    object -- real Python's import machinery does the latter automatically
    only when it actually loads the submodule, not on a sys.modules cache
    hit, so a fake parent must have it set explicitly. Depends on _fake_span
    because that fixture is what replaces sys.modules["mlflow"]."""
    fake_submodule = MagicMock()
    monkeypatch.setitem(sys.modules, "mlflow.anthropic", fake_submodule)
    monkeypatch.setattr(sys.modules["mlflow"], "anthropic", fake_submodule, raising=False)
    return fake_submodule


def test_autolog_enabled_when_version_in_range(
    _anthropic_client, _fake_span, _fake_mlflow_anthropic, monkeypatch
):
    monkeypatch.setattr(anthropic, "__version__", "0.107.1", raising=False)
    _call_chat()
    _fake_mlflow_anthropic.autolog.assert_called_once()


def test_autolog_skipped_and_warns_when_version_out_of_range(
    _anthropic_client, _fake_span, _fake_mlflow_anthropic, monkeypatch, capsys
):
    monkeypatch.setattr(anthropic, "__version__", "1.3.0", raising=False)
    _call_chat()
    _fake_mlflow_anthropic.autolog.assert_not_called()
    assert "outside the tested range" in capsys.readouterr().out


def test_autolog_attempted_only_once_across_multiple_calls(
    _anthropic_client, _fake_span, _fake_mlflow_anthropic, monkeypatch
):
    monkeypatch.setattr(anthropic, "__version__", "0.107.1", raising=False)
    _call_chat()
    _call_chat()
    _fake_mlflow_anthropic.autolog.assert_called_once()


@pytest.mark.parametrize(
    ("version", "expected"),
    [("0.54.9", False), ("0.55.0", True), ("0.107.1", True), ("0.107.2", False), ("1.3.0", False)],
)
def test_autolog_version_supported_boundaries(version, expected):
    assert llm_client._autolog_version_supported(version) is expected
