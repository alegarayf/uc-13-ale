"""Unit tests for FTA context_utils retrieval dispatch adapter."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

from agents.shared._types import RouteResult  # noqa: E402
from agents.subagents.workstream.financial.context_utils import (  # noqa: E402
    build_focused_context,
    semantic_search_with_fallback,
)


def _row(*, file_name: str = "CIM.pdf", chunk_text: str = "A" * 200, source_type: str = "text"):
    return SimpleNamespace(
        chunk_id="c1",
        file_name=file_name,
        chunk_text=chunk_text,
        section_header="Revenue",
        page_start=1,
        source_type=source_type,
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


def test_semantic_search_with_fallback_signature_has_no_retrieval_mode():
    """FTA contract: dead retrieval_mode param removed from context_utils wrapper."""
    params = inspect.signature(semantic_search_with_fallback).parameters
    assert "retrieval_mode" not in params


@patch("agents.shared.fallback.semantic_search_with_fallback")
def test_delegator_returns_tuple_route_result_and_used_fallback(mock_shared_fallback):
    rows = [_row(), _row(file_name="P&L.pdf"), _row(file_name="Model.xlsx")]
    mock_shared_fallback.return_value = (
        _route_result(rows, mode="semantic", scores=[0.9, 0.8, 0.7]),
        False,
    )

    result, used_fallback = semantic_search_with_fallback(**_call_kwargs())

    assert isinstance(result, RouteResult)
    assert result.mode == "semantic"
    assert result.chunks == rows
    assert result.scores == [0.9, 0.8, 0.7]
    assert used_fallback is False
    mock_shared_fallback.assert_called_once()


@patch("agents.shared.fallback.semantic_search_with_fallback")
def test_delegator_threads_catalog_from_default_catalog(mock_shared_fallback, monkeypatch):
    """Catalog must be threaded explicitly — fallback.py does not read os.environ."""
    monkeypatch.setenv("catalog", "uc13_custom")
    rows = [_row(), _row(), _row()]
    mock_shared_fallback.return_value = (_route_result(rows), False)

    semantic_search_with_fallback(**_call_kwargs())

    assert mock_shared_fallback.call_args.kwargs["catalog"] == "uc13_custom"


@patch("agents.shared.fallback.semantic_search_with_fallback")
def test_delegator_forwards_source_type_kwargs(mock_shared_fallback):
    rows = [_row(source_type="table")]
    mock_shared_fallback.return_value = (_route_result(rows), False)

    semantic_search_with_fallback(
        **_call_kwargs(),
        source_type_priority=True,
        source_type_filter=["table", "vision"],
    )

    call_kwargs = mock_shared_fallback.call_args.kwargs
    assert call_kwargs["source_type_priority"] is True
    assert call_kwargs["source_type_filter"] == ["table", "vision"]


@patch("agents.shared.fallback.semantic_search_with_fallback")
def test_delegator_propagates_used_fallback_flag(mock_shared_fallback):
    rows = [_row(), _row(file_name="other.pdf"), _row(file_name="misc.pdf")]
    mock_shared_fallback.return_value = (
        _route_result(rows, scores=[0.4, 0.3, 0.2]),
        True,
    )

    result, used_fallback = semantic_search_with_fallback(**_call_kwargs())

    assert result.chunks == rows
    assert used_fallback is True


@patch("agents.shared.fallback.semantic_search_with_fallback")
def test_delegator_preserves_inner_route_result_mode(mock_shared_fallback):
    """Wrapper must not overwrite inner keyword mode from shared fallback."""
    rows = [_row(), _row(file_name="P&L.pdf")]
    mock_shared_fallback.return_value = (
        _route_result(rows, mode="keyword", scores=[0.0, 0.0]),
        False,
    )

    result, _ = semantic_search_with_fallback(**_call_kwargs())

    assert result.mode == "keyword"
    assert result.scores == [0.0, 0.0]
    assert len(result.scores) == len(result.chunks)
    assert all(s is not None for s in result.scores)


def test_build_focused_context_dedupes_identical_chunk_text():
    """Context-map flag 6: build_focused_context unit coverage in context_utils tests."""
    duplicate = _row(chunk_text="identical body " * 20)
    context, stats = build_focused_context([duplicate, duplicate], max_chars=8_000)

    assert "identical body" in context
    assert "1/1 chunks" in stats


def test_build_focused_context_excludes_chunks_beyond_max_chars():
    """Falsifier: chunks exceeding max_chars must be excluded, not silently merged."""
    oversized = _row(chunk_text="x" * 500)
    context, stats = build_focused_context([oversized], max_chars=50)

    assert context == ""
    assert "1 excluded" in stats


@patch("agents.shared.fallback.semantic_search_with_fallback")
def test_delegator_propagates_intent_id_to_shared_fallback(mock_shared_fallback):
    """M-RE2 T3/D3: intent_id must flow through the wrapper to shared fallback."""
    rows = [_row(), _row(file_name="P&L.pdf"), _row(file_name="Model.xlsx")]
    mock_shared_fallback.return_value = (_route_result(rows), False)

    semantic_search_with_fallback(
        **_call_kwargs(),
        intent_id="fta.opex.q1_financial_statements",
    )

    assert mock_shared_fallback.call_args.kwargs["intent_id"] == (
        "fta.opex.q1_financial_statements"
    )


@patch("agents.shared.fallback.semantic_search_with_fallback")
def test_delegator_defaults_intent_id_none(mock_shared_fallback):
    rows = [_row(), _row(), _row()]
    mock_shared_fallback.return_value = (_route_result(rows), False)

    semantic_search_with_fallback(**_call_kwargs())

    assert mock_shared_fallback.call_args.kwargs["intent_id"] is None


@patch("agents.shared.fallback.semantic_search_with_fallback")
def test_delegator_does_not_call_retrieval_directly(mock_shared_fallback):
    """Falsifier: thin delegator must not bypass shared fallback module."""
    rows = [_row(), _row(), _row()]
    mock_shared_fallback.return_value = (_route_result(rows), False)

    with patch("agents.shared.retrieval.semantic_search") as mock_semantic_search:
        semantic_search_with_fallback(**_call_kwargs())
        mock_semantic_search.assert_not_called()

    mock_shared_fallback.assert_called_once()
