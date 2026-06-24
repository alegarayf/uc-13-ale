"""Unit tests for FTA context_utils retrieval dispatch adapter."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

from agents.shared._types import RouteResult  # noqa: E402
from agents.subagents.workstream.financial.context_utils import (  # noqa: E402
    semantic_search_with_fallback,
)


def _row(*, file_name: str = "CIM.pdf", chunk_text: str = "A" * 200):
    return SimpleNamespace(
        chunk_id="c1",
        file_name=file_name,
        chunk_text=chunk_text,
        section_header="Revenue",
        page_start=1,
        source_type="text",
        workstream=["FINANCIAL"],
        priority_tier=1,
    )


def _call_kwargs():
    return dict(
        company_name="Acme Corp",
        spark=MagicMock(),
        query="revenue EBITDA",
        workstream_filter=["FINANCIAL"],
        top_k=5,
        file_name_filter=["CIM"],
        min_chunk_length=150,
        min_results=3,
    )


@patch("agents.shared.route_chunks.route_chunks")
def test_routed_mode_retries_without_file_name_filter_when_under_min_results(
    mock_route_chunks,
):
    retry_rows = [_row(), _row(file_name="other.pdf"), _row(file_name="misc.pdf")]
    mock_route_chunks.side_effect = [
        RouteResult(chunks=[_row()], mode="routed", scores=None),
        RouteResult(chunks=retry_rows, mode="routed", scores=None),
    ]

    result = semantic_search_with_fallback(**_call_kwargs(), retrieval_mode="routed")

    assert result.chunks == retry_rows
    assert mock_route_chunks.call_count == 2
    second_call_kwargs = mock_route_chunks.call_args_list[1].kwargs
    assert second_call_kwargs["file_name_filter"] is None


@patch("agents.shared.route_chunks.route_chunks")
def test_routed_mode_returns_route_result(mock_route_chunks):
    rows = [_row(), _row(file_name="P&L.pdf"), _row(file_name="Model.xlsx")]
    mock_route_chunks.return_value = RouteResult(chunks=rows, mode="routed", scores=None)

    result = semantic_search_with_fallback(**_call_kwargs(), retrieval_mode="routed")

    assert isinstance(result, RouteResult)
    assert result.mode == "routed"
    assert result.chunks == rows
    assert isinstance(result.chunks, list)
    mock_route_chunks.assert_called_once()


@patch("agents.shared.retrieval.semantic_search", create=True)
def test_semantic_mode_returns_route_result(mock_semantic_search):
    rows = [_row(), _row(file_name="P&L.pdf"), _row(file_name="Model.xlsx")]
    mock_semantic_search.return_value = rows

    result = semantic_search_with_fallback(**_call_kwargs(), retrieval_mode="semantic")

    assert isinstance(result, RouteResult)
    assert result.mode == "semantic"
    assert result.chunks == rows
    assert isinstance(result.chunks, list)
    assert result.scores is None
    mock_semantic_search.assert_called_once()


@patch("agents.shared.retrieval.semantic_search", create=True)
def test_enhanced_semantic_mode_uses_semantic_search(mock_semantic_search):
    rows = [_row(), _row(file_name="P&L.pdf"), _row(file_name="Model.xlsx")]
    mock_semantic_search.return_value = rows

    result = semantic_search_with_fallback(**_call_kwargs(), retrieval_mode="enhanced_semantic")

    assert isinstance(result, RouteResult)
    assert result.mode == "semantic"
    assert result.chunks == rows
    mock_semantic_search.assert_called_once()


@patch("agents.shared.retrieval.semantic_search", create=True)
def test_unknown_retrieval_mode_falls_back_to_semantic(mock_semantic_search):
    rows = [_row(), _row(), _row()]
    mock_semantic_search.return_value = rows

    result = semantic_search_with_fallback(**_call_kwargs(), retrieval_mode="invalid_mode")

    assert isinstance(result, RouteResult)
    assert result.mode == "semantic"
    mock_semantic_search.assert_called_once()


@patch("agents.shared.route_chunks.route_chunks")
def test_route_chunks_value_error_propagates(mock_route_chunks):
    mock_route_chunks.side_effect = ValueError("route_chunks: no results — company=Acme Corp workstream=['FINANCIAL']")

    with pytest.raises(ValueError, match="route_chunks: no results"):
        semantic_search_with_fallback(**_call_kwargs(), retrieval_mode="routed")


@patch("agents.shared.retrieval.semantic_search", create=True)
def test_semantic_fallback_retries_without_file_name_filter(mock_semantic_search):
    retry_rows = [_row(), _row(file_name="other.pdf"), _row(file_name="misc.pdf")]
    mock_semantic_search.side_effect = [[_row()], retry_rows]

    result = semantic_search_with_fallback(**_call_kwargs(), retrieval_mode="semantic")

    assert result.chunks == retry_rows
    assert mock_semantic_search.call_count == 2
    second_call_kwargs = mock_semantic_search.call_args_list[1].kwargs
    assert second_call_kwargs["file_name_filter"] is None


@patch("agents.shared.retrieval.semantic_search", create=True)
def test_routed_mode_does_not_call_semantic_search(mock_semantic_search):
    with patch(
        "agents.shared.route_chunks.route_chunks",
        return_value=RouteResult(chunks=[_row()], mode="routed", scores=None),
    ):
        semantic_search_with_fallback(**_call_kwargs(), retrieval_mode="routed")

    mock_semantic_search.assert_not_called()
