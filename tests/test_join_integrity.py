"""R-08 join-integrity preflight — CI regression guard for chunks ↔ doc_relevance join."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agents.shared.retrieval import _hydrate_chunks_sql, _keyword_fallback_sql

_REPO_ROOT = Path(__file__).resolve().parents[1]
_BOOTSTRAP = _REPO_ROOT / "eval" / "retrieval" / "gold" / "bootstrap.py"

_EXPECTED_JOIN_ON = "c.file_name = r.filename"
_EXPECTED_JOIN_AND = "c.company_name = r.company_name"
_EXPECTED_DOC_ID_JOIN = "c.doc_id = r.doc_id"


@dataclass(frozen=True)
class ChunkRow:
    chunk_id: str
    file_name: str
    company_name: str


@dataclass(frozen=True)
class DocRelevanceRow:
    filename: str
    company_name: str


@dataclass(frozen=True)
class ChunkRowByDocId:
    chunk_id: str
    doc_id: str


@dataclass(frozen=True)
class DocRelevanceRowByDocId:
    doc_id: str


def _joined_chunk_ids(
    chunks: list[ChunkRow],
    relevance: list[DocRelevanceRow],
) -> set[str]:
    """Inner-join semantics matching _hydrate_chunks_sql and gold/bootstrap.py."""
    relevance_keys = {(row.filename, row.company_name) for row in relevance}
    return {
        chunk.chunk_id
        for chunk in chunks
        if (chunk.file_name, chunk.company_name) in relevance_keys
    }


def _orphan_chunk_ids(
    chunks: list[ChunkRow],
    relevance: list[DocRelevanceRow],
) -> set[str]:
    joined = _joined_chunk_ids(chunks, relevance)
    return {chunk.chunk_id for chunk in chunks} - joined


def _joined_chunk_ids_by_doc_id(
    chunks: list[ChunkRowByDocId],
    relevance: list[DocRelevanceRowByDocId],
) -> set[str]:
    """Inner-join semantics matching _hydrate_chunks_sql after M3 doc_id migration."""
    relevance_doc_ids = {row.doc_id for row in relevance}
    return {
        chunk.chunk_id
        for chunk in chunks
        if chunk.doc_id in relevance_doc_ids
    }


def _orphan_chunk_ids_by_doc_id(
    chunks: list[ChunkRowByDocId],
    relevance: list[DocRelevanceRowByDocId],
) -> set[str]:
    joined = _joined_chunk_ids_by_doc_id(chunks, relevance)
    return {chunk.chunk_id for chunk in chunks} - joined


def detect_join_integrity_violations(
    chunks: list[ChunkRow],
    relevance: list[DocRelevanceRow],
) -> dict[str, int | list[str]]:
    """Surface orphan chunks that an inner join would drop from hydrate/bootstrap paths."""
    orphans = sorted(_orphan_chunk_ids(chunks, relevance))
    joined = _joined_chunk_ids(chunks, relevance)
    return {
        "orphan_count": len(orphans),
        "orphan_chunk_ids": orphans,
        "joined_count": len(joined),
        "total_chunks": len(chunks),
    }


def test_hydrate_sql_join_predicate_unchanged() -> None:
    sql = _hydrate_chunks_sql(["probe-id"], "Elder Care", "uc13_ale")
    assert _EXPECTED_DOC_ID_JOIN in sql
    assert _EXPECTED_JOIN_ON not in sql
    assert _EXPECTED_JOIN_AND not in sql


def test_keyword_fallback_sql_join_predicate_migrated() -> None:
    sql = _keyword_fallback_sql(["revenue"], "Elder Care", 10, "uc13_ale")
    assert _EXPECTED_DOC_ID_JOIN in sql
    assert _EXPECTED_JOIN_ON not in sql
    assert _EXPECTED_JOIN_AND not in sql


def test_bootstrap_join_predicate_unchanged() -> None:
    text = _BOOTSTRAP.read_text(encoding="utf-8")
    assert _EXPECTED_JOIN_ON in text
    assert _EXPECTED_JOIN_AND in text


def test_orphan_chunks_detected_not_silently_dropped() -> None:
    chunks = [
        ChunkRow("matched-a", "report.pdf", "Elder Care"),
        ChunkRow("matched-b", "report.pdf", "Elder Care"),
        ChunkRow("orphan-missing-file", "missing.pdf", "Elder Care"),
        ChunkRow("orphan-wrong-company", "report.pdf", "Other Co"),
    ]
    relevance = [DocRelevanceRow("report.pdf", "Elder Care")]

    report = detect_join_integrity_violations(chunks, relevance)

    assert report["joined_count"] == 2
    assert report["orphan_count"] == 2
    assert set(report["orphan_chunk_ids"]) == {
        "orphan-missing-file",
        "orphan-wrong-company",
    }


def test_orphan_chunks_detected_by_doc_id_key() -> None:
    shared_doc_id = "uc13_ale.ingestion.Elder Care.folder/report.pdf"
    chunks = [
        ChunkRowByDocId("matched-a", shared_doc_id),
        ChunkRowByDocId("matched-b", shared_doc_id),
        ChunkRowByDocId("orphan-unknown-doc", "uc13_ale.ingestion.Elder Care.folder/missing.pdf"),
        ChunkRowByDocId("orphan-null-doc", ""),
    ]
    relevance = [DocRelevanceRowByDocId(shared_doc_id)]

    orphans = sorted(_orphan_chunk_ids_by_doc_id(chunks, relevance))

    assert orphans == ["orphan-null-doc", "orphan-unknown-doc"]


def test_non_orphan_chunks_join_successfully() -> None:
    chunks = [
        ChunkRow("c1", "cim.pdf", "Elder Care"),
        ChunkRow("c2", "tax-return.pdf", "Elder Care"),
    ]
    relevance = [
        DocRelevanceRow("cim.pdf", "Elder Care"),
        DocRelevanceRow("tax-return.pdf", "Elder Care"),
    ]

    report = detect_join_integrity_violations(chunks, relevance)

    assert report["orphan_count"] == 0
    assert report["orphan_chunk_ids"] == []
    assert report["joined_count"] == 2
    assert report["total_chunks"] == 2


def test_all_chunks_orphan_when_relevance_empty() -> None:
    """Falsifier: empty doc_relevance must not look like a clean join (zero orphans)."""
    chunks = [
        ChunkRow("only-one", "unmapped.pdf", "Elder Care"),
        ChunkRow("only-two", "also-unmapped.pdf", "Elder Care"),
    ]

    report = detect_join_integrity_violations(chunks, [])

    assert report["orphan_count"] == 2
    assert report["joined_count"] == 0
    assert set(report["orphan_chunk_ids"]) == {"only-one", "only-two"}
