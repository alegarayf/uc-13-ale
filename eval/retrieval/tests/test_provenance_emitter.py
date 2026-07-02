"""Provenance builder, resolve_store, and emitter tests — M-RE2 T2."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
for _path in (_REPO_ROOT / "databricks", _REPO_ROOT):
    _entry = str(_path)
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from agents.shared.run_context import (
    RunContextError,
    close_agent_run,
    open_agent_run,
    set_pipeline_thread,
)
from eval.retrieval.errors import ProvenanceEmitError
from eval.retrieval.models import RetrievalIntent
from eval.retrieval.provenance import (
    MODE_ALIASES,
    ProvenanceEmitter,
    build_provenance_record,
    normalize_mode,
    resolve_store,
)
from eval.retrieval.store import SqliteEvalStore


@pytest.fixture
def store(tmp_path) -> SqliteEvalStore:
    db = SqliteEvalStore(tmp_path / "re2_store.sqlite")
    yield db
    db.close()


@pytest.fixture(autouse=True)
def _reset_emitter_state():
    ProvenanceEmitter._intents_by_run.clear()
    ProvenanceEmitter._logged_runs.clear()
    yield
    try:
        close_agent_run()
    except RunContextError:
        pass


@pytest.fixture(autouse=True)
def _clear_provenance_env(monkeypatch):
    monkeypatch.delenv("RE2_PROVENANCE_REQUIRED", raising=False)
    monkeypatch.delenv("RE2_STORE_BACKEND", raising=False)


@dataclass
class _FakeChunk:
    chunk_id: str
    file_name: str = "CIM.pdf"
    section_header: str = "Overview"
    priority_tier: int = 1
    source_type: str = "text"


@dataclass
class _FakeRouteResult:
    chunks: list
    mode: str
    scores: list[float]


def _sample_intent() -> RetrievalIntent:
    return RetrievalIntent(
        intent_id="fta.opex.q1_financial_statements",
        agent_id="fta",
        source_file="opex_sub_agent.py",
        catalog="uc13_ale",
        query="operating expenses",
        top_k=5,
        invocation_path="direct",
    )


def test_normalize_mode_aliases():
    assert normalize_mode("vector") == "semantic"
    assert normalize_mode("keyword_fallback") == "keyword"
    assert normalize_mode(None) == "semantic"
    assert MODE_ALIASES["vector"] == "semantic"


def test_build_provenance_record_keyword_zeroes_sim_score():
    intent = _sample_intent()
    route = _FakeRouteResult(
        chunks=[_FakeChunk("chunk-001")],
        mode="keyword",
        scores=[0.42],
    )
    record = build_provenance_record(
        intent,
        company_name="Elder Care",
        route_result=route,
        run_id="baseline_test",
    )
    assert record.mode == "keyword"
    assert record.chunks[0].sim_score == 0.0
    assert record.chunks[0].merge_score == 0.42


def test_resolve_store_returns_sqlite_without_spark(monkeypatch, tmp_path):
    monkeypatch.setenv("RE2_STORE_BACKEND", "sqlite")
    monkeypatch.setattr(
        "eval.retrieval.provenance.default_sqlite_path",
        lambda: tmp_path / "re2_store.sqlite",
    )
    resolved = resolve_store()
    assert isinstance(resolved, SqliteEvalStore)
    resolved.close()


def test_emit_noop_without_open_agent_run():
    route = _FakeRouteResult(chunks=[], mode="semantic", scores=[])
    ProvenanceEmitter.emit(
        route_result=route,
        company_name="Elder Care",
        query="test",
        intent_id="fta.opex.q1_financial_statements",
    )


def test_emit_raises_when_required_without_open_run(monkeypatch):
    monkeypatch.setenv("RE2_PROVENANCE_REQUIRED", "1")
    route = _FakeRouteResult(chunks=[], mode="semantic", scores=[])
    with pytest.raises(ProvenanceEmitError, match="open agent run"):
        ProvenanceEmitter.emit(
            route_result=route,
            company_name="Elder Care",
            query="test",
        )


def _provenance_intent_ids(store: SqliteEvalStore, run_id: str) -> list[str]:
    rows = store._conn.execute(
        "SELECT intent_id FROM retrieval_provenance WHERE run_id = ? ORDER BY intent_id",
        (run_id,),
    ).fetchall()
    return [row["intent_id"] for row in rows]


def test_emit_appends_provenance_on_open_agent_run(store: SqliteEvalStore):
    set_pipeline_thread("thread-emit-001")
    run_id = open_agent_run(
        "fta",
        company_name="Elder Care",
        catalog="uc13_ale",
        affected_intents=["fta.opex.q1_financial_statements"],
        store=store,
    )
    route = _FakeRouteResult(
        chunks=[_FakeChunk("chunk-abc")],
        mode="semantic",
        scores=[0.88],
    )
    ProvenanceEmitter.emit(
        route_result=route,
        company_name="Elder Care",
        query="operating expenses",
        intent_id="fta.opex.q1_financial_statements",
    )

    assert _provenance_intent_ids(store, run_id) == [
        "fta.opex.q1_financial_statements"
    ]
    chunk_rows = store._conn.execute(
        """
        SELECT chunk_id FROM retrieval_provenance
        WHERE run_id = ? AND intent_id = ?
        """,
        (run_id, "fta.opex.q1_financial_statements"),
    ).fetchall()
    assert chunk_rows[0]["chunk_id"] == "chunk-abc"
    close_agent_run()


def test_emit_intent_id_fallback_unknown_agent(store: SqliteEvalStore):
    set_pipeline_thread("thread-fallback")
    run_id = open_agent_run(
        "bma",
        company_name="Elder Care",
        catalog="uc13_ale",
        affected_intents=["bma.business_model"],
        store=store,
    )
    route = _FakeRouteResult(
        chunks=[_FakeChunk("chunk-bma")],
        mode="semantic",
        scores=[0.5],
    )
    ProvenanceEmitter.emit(
        route_result=route,
        company_name="Elder Care",
        query="business model",
        intent_id=None,
    )

    assert _provenance_intent_ids(store, run_id) == ["unknown.bma"]
    close_agent_run()


def test_patch_context_allocations_updates_existing_rows(store: SqliteEvalStore):
    set_pipeline_thread("thread-patch")
    run_id = open_agent_run(
        "fta",
        company_name="Elder Care",
        catalog="uc13_ale",
        affected_intents=["fta.opex.q1_financial_statements"],
        store=store,
    )
    chunk = _FakeChunk("chunk-patch-001")
    route = _FakeRouteResult(chunks=[chunk], mode="semantic", scores=[0.75])
    ProvenanceEmitter.emit(
        route_result=route,
        company_name="Elder Care",
        query="operating expenses",
        intent_id="fta.opex.q1_financial_statements",
    )

    allocation = SimpleNamespace(
        chunk=chunk,
        chars_allocated=512,
        context_section="=== Historical / reported P&L sources ===",
    )
    ProvenanceEmitter.patch_context_allocations(
        "fta.opex.q1_financial_statements",
        [allocation],
    )

    row = store._conn.execute(
        """
        SELECT chars_allocated, context_section
        FROM retrieval_provenance
        WHERE run_id = ? AND intent_id = ? AND chunk_id = ?
        """,
        (run_id, "fta.opex.q1_financial_statements", "chunk-patch-001"),
    ).fetchone()
    assert row["chars_allocated"] == 512
    assert row["context_section"] == "=== Historical / reported P&L sources ==="
    close_agent_run()


def test_resolve_store_delta_without_spark_raises_when_required(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("RE2_STORE_BACKEND", "delta")
    monkeypatch.setenv("RE2_PROVENANCE_REQUIRED", "1")
    monkeypatch.setattr("eval.retrieval.provenance._active_spark", lambda: None)
    with pytest.raises(ProvenanceEmitError, match="SparkSession"):
        resolve_store()
