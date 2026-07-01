"""Unit tests for FTA context_utils retrieval dispatch adapter."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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


def _route_result(
    rows: list,
    *,
    mode: str = "semantic",
    scores: list[float] | None = None,
) -> RouteResult:
    if scores is None:
        scores = [0.5] * len(rows) if rows else []
    return RouteResult(chunks=rows, mode=mode, scores=scores)


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


@patch("agents.shared.retrieval.semantic_search", create=True)
def test_semantic_mode_returns_route_result(mock_semantic_search):
    rows = [_row(), _row(file_name="P&L.pdf"), _row(file_name="Model.xlsx")]
    mock_semantic_search.return_value = _route_result(rows, mode="semantic", scores=[0.9, 0.8, 0.7])

    result = semantic_search_with_fallback(**_call_kwargs(), retrieval_mode="semantic")

    assert isinstance(result, RouteResult)
    assert result.mode == "semantic"
    assert result.chunks == rows
    assert result.scores == [0.9, 0.8, 0.7]
    mock_semantic_search.assert_called_once()


@patch("agents.shared.retrieval.semantic_search", create=True)
def test_enhanced_semantic_mode_uses_semantic_search(mock_semantic_search):
    rows = [_row(), _row(file_name="P&L.pdf"), _row(file_name="Model.xlsx")]
    mock_semantic_search.return_value = _route_result(rows)

    result = semantic_search_with_fallback(**_call_kwargs(), retrieval_mode="enhanced_semantic")

    assert isinstance(result, RouteResult)
    assert result.mode == "semantic"
    assert result.chunks == rows
    mock_semantic_search.assert_called_once()


@patch("agents.shared.retrieval.semantic_search", create=True)
def test_enhanced_semantic_and_semantic_pass_identical_semantic_search_kwargs(
    mock_semantic_search,
):
    """D7a eval guard: enhanced_semantic must not diverge from semantic at the retrieval layer."""
    rows = [_row(), _row(file_name="P&L.pdf"), _row(file_name="Model.xlsx")]
    mock_semantic_search.return_value = _route_result(rows)
    call_kwargs = _call_kwargs()

    semantic_search_with_fallback(**call_kwargs, retrieval_mode="semantic")
    semantic_calls = [call for call in mock_semantic_search.call_args_list]

    mock_semantic_search.reset_mock()
    mock_semantic_search.return_value = _route_result(rows)

    semantic_search_with_fallback(**call_kwargs, retrieval_mode="enhanced_semantic")
    enhanced_calls = [call for call in mock_semantic_search.call_args_list]

    assert len(semantic_calls) == len(enhanced_calls)
    for semantic_call, enhanced_call in zip(semantic_calls, enhanced_calls, strict=True):
        assert semantic_call == enhanced_call


@patch("agents.shared.retrieval.semantic_search", create=True)
def test_unknown_retrieval_mode_falls_back_to_semantic(mock_semantic_search):
    rows = [_row(), _row(), _row()]
    mock_semantic_search.return_value = _route_result(rows)

    result = semantic_search_with_fallback(**_call_kwargs(), retrieval_mode="invalid_mode")

    assert isinstance(result, RouteResult)
    assert result.mode == "semantic"
    mock_semantic_search.assert_called_once()


@patch("agents.shared.retrieval.semantic_search", create=True)
def test_semantic_fallback_retries_without_file_name_filter(mock_semantic_search):
    retry_rows = [_row(), _row(file_name="other.pdf"), _row(file_name="misc.pdf")]
    mock_semantic_search.side_effect = [
        _route_result([_row()]),
        _route_result(retry_rows, scores=[0.4, 0.3, 0.2]),
    ]

    result = semantic_search_with_fallback(**_call_kwargs(), retrieval_mode="semantic")

    assert result.chunks == retry_rows
    assert result.scores == [0.4, 0.3, 0.2]
    assert mock_semantic_search.call_count == 2
    second_call_kwargs = mock_semantic_search.call_args_list[1].kwargs
    assert second_call_kwargs["file_name_filter"] is None


@patch("agents.shared.retrieval.semantic_search", create=True)
def test_wrapper_propagates_keyword_mode_from_inner(mock_semantic_search):
    """D3-A kill criterion: wrapper must not overwrite inner keyword mode."""
    rows = [_row(), _row(file_name="P&L.pdf")]
    mock_semantic_search.return_value = _route_result(rows, mode="keyword", scores=[0.0, 0.0])

    result = semantic_search_with_fallback(**_call_kwargs(), retrieval_mode="semantic")

    assert result.mode == "keyword"
    assert result.scores == [0.0, 0.0]
