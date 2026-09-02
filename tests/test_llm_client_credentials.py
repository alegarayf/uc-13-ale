"""Hermetic tests for llm_client credential resolution and client construction.

Derived from spec.md ASDK-08 (T8 "Done when"). The real `anthropic` package is
installed in this environment, so the "package missing" case is simulated by
shadowing sys.modules["anthropic"] with None, which makes `import anthropic`
raise ImportError -- the same mechanism Python itself uses.
"""

from __future__ import annotations

import os

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

from agents.shared import llm_client  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_client_cache():
    """The client is a module-level singleton -- isolate tests from each other."""
    llm_client._client_state["client"] = None
    llm_client._databricks_client_state["client"] = None
    yield
    llm_client._client_state["client"] = None
    llm_client._databricks_client_state["client"] = None


@pytest.fixture
def _no_dbutils(monkeypatch):
    monkeypatch.setattr(llm_client, "_get_dbutils", lambda: None)


# --- credential resolution: env var fallback --------------------------------


def test_resolve_api_key_falls_back_to_env_var(monkeypatch, _no_dbutils):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-value")
    assert llm_client._resolve_api_key() == "sk-ant-test-value"


# --- credential resolution: secret scope takes precedence -------------------


def _dbutils_with_no_widgets():
    """Real dbutils raises when a widget isn't declared; MagicMock doesn't by
    default, so get_param() would wrongly treat that MagicMock as a value."""
    fake = MagicMock()
    fake.widgets.get.side_effect = Exception("InputWidgetNotDefined")
    return fake


def test_resolve_api_key_prefers_secret_scope_over_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "should-not-be-used")
    fake_dbutils = _dbutils_with_no_widgets()
    fake_dbutils.secrets.get.return_value = "sk-ant-from-scope"
    monkeypatch.setattr(llm_client, "_get_dbutils", lambda: fake_dbutils)
    assert llm_client._resolve_api_key() == "sk-ant-from-scope"
    fake_dbutils.secrets.get.assert_called_once_with("uc13", "anthropic_api_key")


def test_resolve_api_key_honors_custom_scope_param(monkeypatch):
    monkeypatch.setenv("anthropic_secret_scope", "custom_scope")
    fake_dbutils = _dbutils_with_no_widgets()
    fake_dbutils.secrets.get.return_value = "sk-ant-custom"
    monkeypatch.setattr(llm_client, "_get_dbutils", lambda: fake_dbutils)
    llm_client._resolve_api_key()
    fake_dbutils.secrets.get.assert_called_once_with("custom_scope", "anthropic_api_key")


# --- credential resolution: missing key -------------------------------------


def test_resolve_api_key_missing_raises_naming_scope_and_env_var(monkeypatch, _no_dbutils):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("anthropic_secret_scope", raising=False)
    with pytest.raises(RuntimeError) as exc_info:
        llm_client._resolve_api_key()
    message = str(exc_info.value)
    assert "uc13" in message
    assert "ANTHROPIC_API_KEY" in message


def test_resolve_api_key_missing_never_leaks_a_key_value(monkeypatch, _no_dbutils):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError) as exc_info:
        llm_client._resolve_api_key()
    assert "sk-ant" not in str(exc_info.value)


# --- client construction: missing package -----------------------------------


def test_get_client_missing_package_raises_import_error_with_install_hint(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", None)
    with pytest.raises(ImportError, match="pip install anthropic"):
        llm_client._get_anthropic_client()


# --- client construction: singleton -----------------------------------------


def test_get_client_returns_same_instance_across_calls(monkeypatch, _no_dbutils):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-value")
    first = llm_client._get_anthropic_client()
    second = llm_client._get_anthropic_client()
    assert first is second


def test_get_client_passes_timeout_and_retries(monkeypatch, _no_dbutils):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-value")
    import anthropic

    captured = {}
    original_init = anthropic.Anthropic.__init__

    def _spy_init(self, *args, **kwargs):
        captured.update(kwargs)
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(anthropic.Anthropic, "__init__", _spy_init)
    llm_client._get_anthropic_client()
    assert captured["timeout"] == 600
    assert captured["max_retries"] == 2


# --- _get_databricks_client: HTTP timeout pin (C33, ported from the retired
# WorkstreamAgent._get_llm_client when T13 migrated _call_llm to the gateway) --


@pytest.fixture
def _clean_timeout_env(monkeypatch):
    for key in ("MLFLOW_HTTP_REQUEST_TIMEOUT", "DATABRICKS_HTTP_TIMEOUT"):
        monkeypatch.delenv(key, raising=False)


def test_get_databricks_client_sets_http_timeouts_to_1800(monkeypatch, _clean_timeout_env):
    import mlflow.deployments

    mock_get = MagicMock(return_value=MagicMock(name="deploy_client"))
    monkeypatch.setattr(mlflow.deployments, "get_deploy_client", mock_get)
    llm_client._get_databricks_client()
    assert os.environ["MLFLOW_HTTP_REQUEST_TIMEOUT"] == "1800"
    assert os.environ["DATABRICKS_HTTP_TIMEOUT"] == "1800"
    mock_get.assert_called_once_with("databricks")


def test_get_databricks_client_overrides_a_preset_600(monkeypatch):
    import mlflow.deployments

    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_TIMEOUT", "600")
    monkeypatch.setenv("DATABRICKS_HTTP_TIMEOUT", "600")
    mock_get = MagicMock(return_value=MagicMock(name="deploy_client"))
    monkeypatch.setattr(mlflow.deployments, "get_deploy_client", mock_get)
    llm_client._get_databricks_client()
    assert os.environ["MLFLOW_HTTP_REQUEST_TIMEOUT"] == "1800"
    assert os.environ["DATABRICKS_HTTP_TIMEOUT"] == "1800"


def test_get_databricks_client_returns_same_instance_across_calls(monkeypatch, _clean_timeout_env):
    import mlflow.deployments

    monkeypatch.setattr(
        mlflow.deployments, "get_deploy_client", MagicMock(return_value=MagicMock())
    )
    first = llm_client._get_databricks_client()
    second = llm_client._get_databricks_client()
    assert first is second
