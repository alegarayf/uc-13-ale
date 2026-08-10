"""Unit tests for join-orphan rate measurement (M3 T3)."""

from __future__ import annotations

import pytest

from eval.retrieval.measure_join_orphan_rate import (
    ChunkRow,
    DocRelevanceRow,
    compute_orphan_stats,
)


def _collision_fixture() -> tuple[list[ChunkRow], list[DocRelevanceRow]]:
    """Filename matches but doc_id diverges — R-08 collision class."""
    chunks = [
        ChunkRow("matched-file", "report.pdf", "Elder Care", "doc-correct"),
        ChunkRow("orphan-doc-id", "report.pdf", "Elder Care", "doc-wrong"),
        ChunkRow("orphan-filename", "missing.pdf", "Elder Care", "doc-unmapped"),
    ]
    relevance = [
        DocRelevanceRow("report.pdf", "Elder Care", "doc-correct"),
    ]
    return chunks, relevance


def test_file_name_and_doc_id_modes_yield_distinct_orphan_sets() -> None:
    chunks, relevance = _collision_fixture()

    file_name_result = compute_orphan_stats(
        chunks, relevance, "Elder Care", "file_name"
    )
    doc_id_result = compute_orphan_stats(chunks, relevance, "Elder Care", "doc_id")

    assert file_name_result["orphan_count"] == 1
    assert doc_id_result["orphan_count"] == 2
    assert file_name_result["orphan_rate"] != doc_id_result["orphan_rate"]
    assert file_name_result["key"] == "file_name"
    assert doc_id_result["key"] == "doc_id"


def test_non_orphan_chunks_join_under_both_keys() -> None:
    chunks = [
        ChunkRow("c1", "cim.pdf", "Elder Care", "doc-1"),
        ChunkRow("c2", "tax.pdf", "Elder Care", "doc-2"),
    ]
    relevance = [
        DocRelevanceRow("cim.pdf", "Elder Care", "doc-1"),
        DocRelevanceRow("tax.pdf", "Elder Care", "doc-2"),
    ]

    for key in ("file_name", "doc_id"):
        result = compute_orphan_stats(chunks, relevance, "Elder Care", key)
        assert result["orphan_count"] == 0
        assert result["orphan_rate"] == 0.0
        assert result["total_chunks"] == 2


def test_all_chunks_orphan_when_relevance_empty() -> None:
    chunks = [
        ChunkRow("only-one", "unmapped.pdf", "Elder Care", "doc-a"),
        ChunkRow("only-two", "also.pdf", "Elder Care", "doc-b"),
    ]

    for key in ("file_name", "doc_id"):
        result = compute_orphan_stats(chunks, [], "Elder Care", key)
        assert result["orphan_count"] == 2
        assert result["orphan_rate"] == 1.0


def test_invalid_key_raises_value_error() -> None:
    with pytest.raises(ValueError, match="invalid join key"):
        compute_orphan_stats([], [], "Elder Care", "document_id")  # type: ignore[arg-type]
