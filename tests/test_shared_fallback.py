"""Unit tests for agents.shared.fallback — R-03 shared filename-filter retry."""

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
from agents.shared.fallback import semantic_search_with_fallback  # noqa: E402

_BMA_PATH = _DATABRICKS_ROOT / "agents" / "workstreams" / "business_model_agent.py"
_LEGAL_PATH = _DATABRICKS_ROOT / "agents" / "workstreams" / "legal_contracts_agent.py"

_RETRIEVAL_CALLS = frozenset(
    {"semantic_search", "semantic_search_with_fallback", "_semantic_search_with_fallback"}
)


def _route_result(chunk_count: int) -> RouteResult:
    chunks = [SimpleNamespace(file_name=f"doc_{i}.pdf") for i in range(chunk_count)]
    return RouteResult(chunks=chunks, mode="semantic", scores=[0.9] * chunk_count)


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _forbidden_retrieval_calls_in_wrapper(source: str, class_name: str) -> list[str]:
    """Return call-site names inside _semantic_search_with_fallback that match RETRIEVAL_CALLS."""
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    method = next(
        n for n in cls.body
        if isinstance(n, ast.FunctionDef) and n.name == "_semantic_search_with_fallback"
    )
    violations: list[str] = []
    for node in ast.walk(method):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node.func)
        if name in _RETRIEVAL_CALLS:
            violations.append(name)
    return violations


def test_agent_wrappers_use_aliased_import_not_bare_retrieval_names():
    """D4 falsifier: bare shared-function call sites would double-count registry intents."""
    bma_source = _BMA_PATH.read_text(encoding="utf-8")
    legal_source = _LEGAL_PATH.read_text(encoding="utf-8")
    assert "semantic_search_with_fallback as _shared_fallback_search" in bma_source
    assert "semantic_search_with_fallback as _shared_fallback_search" in legal_source
    assert _forbidden_retrieval_calls_in_wrapper(bma_source, "BusinessModelAgent") == []
    assert _forbidden_retrieval_calls_in_wrapper(legal_source, "LegalContractsAgent") == []


@patch("agents.shared.fallback.semantic_search")
def test_retries_without_filename_filter_when_below_min_results(mock_search):
    mock_search.side_effect = [
        _route_result(1),
        _route_result(4),
    ]
    spark = MagicMock()
    result, used_fallback = semantic_search_with_fallback(
        company_name="Elder Care",
        spark=spark,
        query="business overview",
        workstream_filter=["BUSINESS_MODEL"],
        top_k=10,
        file_name_filter=["CIM"],
        min_results=3,
    )
    assert used_fallback is True
    assert len(result.chunks) == 4
    assert mock_search.call_count == 2
    assert mock_search.call_args_list[0].kwargs["file_name_filter"] == ["CIM"]
    assert mock_search.call_args_list[1].kwargs["file_name_filter"] is None


@patch("agents.shared.fallback.semantic_search")
def test_no_retry_at_min_results_boundary(mock_search):
    mock_search.return_value = _route_result(3)
    _, used_fallback = semantic_search_with_fallback(
        company_name="Elder Care",
        spark=MagicMock(),
        query="q",
        workstream_filter=["LEGAL"],
        top_k=5,
        file_name_filter=["Handbook"],
        min_results=3,
    )
    assert used_fallback is False
    assert mock_search.call_count == 1


@patch("agents.shared.fallback.semantic_search")
def test_no_retry_when_file_name_filter_is_none(mock_search):
    mock_search.return_value = _route_result(0)
    _, used_fallback = semantic_search_with_fallback(
        company_name="Elder Care",
        spark=MagicMock(),
        query="q",
        workstream_filter=["LEGAL"],
        top_k=5,
        file_name_filter=None,
        min_results=3,
    )
    assert used_fallback is False
    assert mock_search.call_count == 1


@patch("agents.shared.fallback.semantic_search")
def test_catalog_threaded_to_both_search_calls(mock_search):
    mock_search.side_effect = [_route_result(1), _route_result(4)]
    semantic_search_with_fallback(
        company_name="Elder Care",
        spark=MagicMock(),
        query="q",
        workstream_filter=["LEGAL"],
        top_k=5,
        file_name_filter=["Handbook"],
        min_results=3,
        catalog="uc13_ale",
    )
    for call in mock_search.call_args_list:
        assert call.kwargs["catalog"] == "uc13_ale"


@patch("agents.shared.fallback.semantic_search")
def test_catalog_none_passed_through_for_bma_default_path(mock_search):
    mock_search.return_value = _route_result(5)
    semantic_search_with_fallback(
        company_name="Elder Care",
        spark=MagicMock(),
        query="q",
        workstream_filter=["BUSINESS_MODEL"],
        top_k=5,
        file_name_filter=["CIM"],
    )
    assert mock_search.call_args.kwargs["catalog"] is None
