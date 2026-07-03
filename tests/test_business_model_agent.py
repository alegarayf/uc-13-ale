"""Behavioral and static contract tests for BusinessModelAgent fallback wrapper (T3 / Flag 6)."""

from __future__ import annotations

import ast
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

if "databricks" not in sys.modules:
    databricks_mod = types.ModuleType("databricks")
    sdk_mod = types.ModuleType("databricks.sdk")
    sdk_mod.WorkspaceClient = MagicMock
    databricks_mod.sdk = sdk_mod
    sys.modules["databricks"] = databricks_mod
    sys.modules["databricks.sdk"] = sdk_mod

if "mlflow" not in sys.modules:
    mlflow_mod = types.ModuleType("mlflow")
    deployments_mod = types.ModuleType("mlflow.deployments")
    deployments_mod.get_deploy_client = MagicMock
    mlflow_mod.deployments = deployments_mod
    sys.modules["mlflow"] = mlflow_mod
    sys.modules["mlflow.deployments"] = deployments_mod

from agents.shared._types import RouteResult  # noqa: E402
from agents.workstreams.business_model_agent import BusinessModelAgent  # noqa: E402

_AGENT_PATH = _DATABRICKS_ROOT / "agents" / "workstreams" / "business_model_agent.py"
_AGENT_SOURCE = _AGENT_PATH.read_text(encoding="utf-8")


def _method_body_source(class_name: str, name: str) -> str:
    tree = ast.parse(_AGENT_SOURCE)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(_AGENT_SOURCE, method) or ""


def test_bma_wrapper_delegates_to_shared_fallback_with_alias():
    body = _method_body_source("BusinessModelAgent", "_semantic_search_with_fallback")
    assert "from agents.shared.fallback import semantic_search_with_fallback as _shared_fallback_search" in body
    assert "_shared_fallback_search(" in body
    assert "semantic_search(" not in body


@patch("agents.shared.fallback.semantic_search")
def test_bma_wrapper_retries_and_appends_trace_on_fallback(mock_search):
    mock_search.side_effect = [
        RouteResult(chunks=[SimpleNamespace(file_name="a.pdf")], mode="semantic", scores=[0.9]),
        RouteResult(
            chunks=[
                SimpleNamespace(file_name=f"doc_{i}.pdf")
                for i in range(4)
            ],
            mode="semantic",
            scores=[0.8] * 4,
        ),
    ]

    agent = BusinessModelAgent.__new__(BusinessModelAgent)
    base = SimpleNamespace(_trace=[])
    agent._base = base
    agent._company_name = "Elder Care"

    result = agent._semantic_search_with_fallback(
        spark=MagicMock(),
        query="business overview",
        workstream_filter=["BUSINESS_MODEL"],
        top_k=10,
        file_name_filter=["CIM"],
        min_results=3,
    )

    assert len(result.chunks) == 4
    assert mock_search.call_count == 2
    assert len(base._trace) == 1
    assert base._trace[0]["tool"] == "retrieval_fallback"
