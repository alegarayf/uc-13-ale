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
    chunks = [
        SimpleNamespace(chunk_id=f"doc_{i}", file_name=f"doc_{i}.pdf")
        for i in range(chunk_count)
    ]
    return RouteResult(chunks=chunks, mode="semantic", scores=[0.9] * chunk_count)


def _chunk(*, chunk_id: str, file_name: str, source_type: str = "table"):
    return SimpleNamespace(
        chunk_id=chunk_id,
        file_name=file_name,
        source_type=source_type,
        priority_tier=2,
    )


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
def test_unions_unfiltered_at_min_results_boundary(mock_search):
    mock_search.side_effect = [_route_result(3), _route_result(5)]
    result, used_fallback = semantic_search_with_fallback(
        company_name="Elder Care",
        spark=MagicMock(),
        query="q",
        workstream_filter=["LEGAL"],
        top_k=5,
        file_name_filter=["Handbook"],
        min_results=3,
    )
    assert used_fallback is True
    assert mock_search.call_count == 2
    assert mock_search.call_args_list[1].kwargs["file_name_filter"] is None
    assert len(result.chunks) == 5


@patch("agents.shared.fallback.semantic_search")
def test_unions_unfiltered_gold_when_filtered_spreadsheet_meets_min_results(mock_search):
    """q4-style: filtered Revenue/Client spreadsheet fills min_results; CIM gold
    only appears on the unfiltered retry and must survive the top_k cap after union.
    """
    spreadsheet = [
        _chunk(chunk_id=f"xlsx-{i}", file_name="Revenue by Client.xlsx")
        for i in range(6)
    ]
    gold_ids = ["cim-gold-a", "cim-gold-b", "cim-gold-c"]
    unfiltered = [
        _chunk(chunk_id="other-1", file_name="Pipeline.xlsx"),
        _chunk(chunk_id="cim-gold-a", file_name="Confidential Information Memorandum.pdf"),
        _chunk(chunk_id="cim-gold-b", file_name="Confidential Information Memorandum.pdf"),
        _chunk(chunk_id="cim-gold-c", file_name="Confidential Information Memorandum.pdf"),
        _chunk(chunk_id="other-2", file_name="Utilization.xlsx"),
        _chunk(chunk_id="other-3", file_name="Pipeline.xlsx"),
    ]
    mock_search.side_effect = [
        RouteResult(
            chunks=spreadsheet,
            mode="semantic",
            scores=[0.62, 0.61, 0.60, 0.59, 0.58, 0.57],
        ),
        RouteResult(
            chunks=unfiltered,
            mode="semantic",
            scores=[0.70, 0.85, 0.84, 0.83, 0.55, 0.54],
        ),
    ]
    result, used_fallback = semantic_search_with_fallback(
        company_name="Clearsulting",
        spark=MagicMock(),
        query="customer concentration revenue by client",
        workstream_filter=["FINANCIAL", "BUSINESS_MODEL", "CUSTOMER_QUALITY"],
        top_k=6,
        file_name_filter=["Revenue", "Client"],
        min_results=2,
        source_type_priority=True,
    )
    assert used_fallback is True
    assert mock_search.call_count == 2
    assert mock_search.call_args_list[0].kwargs["file_name_filter"] == ["Revenue", "Client"]
    assert mock_search.call_args_list[1].kwargs["file_name_filter"] is None
    returned_ids = [c.chunk_id for c in result.chunks]
    assert len(result.chunks) == 6
    gold_in_top_k = [gid for gid in gold_ids if gid in returned_ids]
    assert len(gold_in_top_k) >= 2, returned_ids


@patch("agents.shared.fallback.semantic_search")
def test_no_retry_when_empty_and_no_filters(mock_search):
    mock_search.return_value = _route_result(0)
    _, used_fallback = semantic_search_with_fallback(
        company_name="Elder Care",
        spark=MagicMock(),
        query="q",
        workstream_filter=[],
        top_k=5,
        file_name_filter=None,
        min_results=3,
    )
    assert used_fallback is False
    assert mock_search.call_count == 1


@patch("agents.shared.fallback.semantic_search")
def test_empty_path_drops_workstream_filter_and_admits_gold(mock_search):
    """CQA-style: workstream filter returns 0; gold is BUSINESS_MODEL-only."""
    gold = _chunk(
        chunk_id="cim-gold-account",
        file_name="Confidential Information Memorandum.pdf",
        source_type="text",
    )
    neighbor = _chunk(chunk_id="other-1", file_name="Databook.xlsx")
    mock_search.side_effect = [
        RouteResult(chunks=[], mode="empty", scores=[]),
        RouteResult(chunks=[gold, neighbor], mode="semantic", scores=[0.88, 0.70]),
    ]
    result, used_fallback = semantic_search_with_fallback(
        company_name="GKF",
        spark=MagicMock(),
        query="average account size ACV",
        workstream_filter=["CUSTOMER", "KPI_OPS", "FINANCIAL", "QUALITY_EARNINGS"],
        top_k=6,
        file_name_filter=None,
        min_results=3,
    )
    assert used_fallback is True
    assert mock_search.call_count == 2
    assert mock_search.call_args_list[0].kwargs["workstream_filter"] == [
        "CUSTOMER",
        "KPI_OPS",
        "FINANCIAL",
        "QUALITY_EARNINGS",
    ]
    assert mock_search.call_args_list[1].kwargs["file_name_filter"] is None
    assert mock_search.call_args_list[1].kwargs["workstream_filter"] is None
    returned_ids = [c.chunk_id for c in result.chunks]
    assert "cim-gold-account" in returned_ids


@patch("agents.shared.fallback.semantic_search")
def test_empty_path_drops_filename_and_workstream_when_filtered_zero(mock_search):
    """q4-style: filename+workstream filter returns 0; Databook gold only on unfiltered retry."""
    gold = _chunk(
        chunk_id="databook-gold",
        file_name="FDD Databook.xlsx",
        source_type="table",
    )
    mock_search.side_effect = [
        RouteResult(chunks=[], mode="empty", scores=[]),
        RouteResult(chunks=[gold], mode="semantic", scores=[0.81]),
    ]
    result, used_fallback = semantic_search_with_fallback(
        company_name="GKF",
        spark=MagicMock(),
        query="top customers revenue by customer",
        workstream_filter=["FINANCIAL", "BUSINESS_MODEL", "CUSTOMER_QUALITY"],
        top_k=6,
        file_name_filter=["Customer", "QuickBooks", "Revenue"],
        min_results=2,
        source_type_priority=True,
    )
    assert used_fallback is True
    assert mock_search.call_count == 2
    assert mock_search.call_args_list[1].kwargs["file_name_filter"] is None
    assert mock_search.call_args_list[1].kwargs["workstream_filter"] is None
    assert [c.chunk_id for c in result.chunks] == ["databook-gold"]


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
