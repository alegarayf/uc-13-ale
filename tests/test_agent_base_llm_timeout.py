"""Hermetic tests for WorkstreamAgent._get_llm_client HTTP timeout pin (C33).

Does not import the gitignored fair-experiment driver. Mocks
``mlflow.deployments.get_deploy_client``; no live Spark/warehouse.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

_fake_mlflow = sys.modules.get("mlflow")
if _fake_mlflow is not None and not hasattr(_fake_mlflow, "__path__"):
    for _mod_name in [n for n in sys.modules if n == "mlflow" or n.startswith("mlflow.")]:
        del sys.modules[_mod_name]

from agents.shared.agent_base import WorkstreamAgent  # noqa: E402

_TIMEOUT_KEYS = ("MLFLOW_HTTP_REQUEST_TIMEOUT", "DATABRICKS_HTTP_TIMEOUT")


@pytest.fixture
def _clean_timeout_env(monkeypatch):
    for key in _TIMEOUT_KEYS:
        monkeypatch.delenv(key, raising=False)


@patch("agents.shared.agent_base.mlflow.deployments.get_deploy_client")
def test_get_llm_client_sets_http_timeouts_to_1800(mock_get, _clean_timeout_env):
    mock_get.return_value = MagicMock(name="deploy_client")
    WorkstreamAgent()._get_llm_client()
    assert os.environ["MLFLOW_HTTP_REQUEST_TIMEOUT"] == "1800"
    assert os.environ["DATABRICKS_HTTP_TIMEOUT"] == "1800"
    mock_get.assert_called_once_with("databricks")


@patch("agents.shared.agent_base.mlflow.deployments.get_deploy_client")
def test_get_llm_client_overrides_preset_600(mock_get, monkeypatch):
    mock_get.return_value = MagicMock(name="deploy_client")
    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_TIMEOUT", "600")
    monkeypatch.setenv("DATABRICKS_HTTP_TIMEOUT", "600")
    WorkstreamAgent()._get_llm_client()
    assert os.environ["MLFLOW_HTTP_REQUEST_TIMEOUT"] == "1800"
    assert os.environ["DATABRICKS_HTTP_TIMEOUT"] == "1800"
    mock_get.assert_called_once_with("databricks")
