"""Unit tests for databricks/agents/shared/run_context.py — M-RE2 T1."""

from __future__ import annotations

import contextvars
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

from agents.shared.run_context import (
    RunContextError,
    close_agent_run,
    get_agent_run_id,
    get_current_agent_id,
    get_pipeline_thread,
    load_affected_intents,
    open_agent_run,
    set_pipeline_thread,
)
from eval.retrieval.models import ProvenanceChunk, ProvenanceRecord
from eval.retrieval.store import SqliteEvalStore


@pytest.fixture
def store(tmp_path) -> SqliteEvalStore:
    db = SqliteEvalStore(tmp_path / "re2_store.sqlite")
    yield db
    db.close()


@pytest.fixture(autouse=True)
def _reset_context():
    yield
    try:
        close_agent_run()
    except RunContextError:
        pass


def _provenance_record(*, intent_id: str, mode: str) -> ProvenanceRecord:
    return ProvenanceRecord(
        intent_id=intent_id,
        company_name="Elder Care",
        query="test query",
        mode=mode,
        chunks=[
            ProvenanceChunk(
                chunk_id=f"{intent_id}-chunk",
                rank=1,
                sim_score=0.9,
                merge_score=0.9,
                tier=1,
                section_header="Section",
                file_name="CIM.pdf",
                source_type="text",
            )
        ],
    )


def test_set_and_get_pipeline_thread():
    set_pipeline_thread("thread-abc")
    assert get_pipeline_thread() == "thread-abc"


def test_open_agent_run_inserts_incomplete_pipeline_manifest(store: SqliteEvalStore):
    set_pipeline_thread("thread-001")
    run_id = open_agent_run(
        "fta",
        company_name="Elder Care",
        catalog="uc13_ale",
        affected_intents=["fta.opex.q1_financial_statements"],
        store=store,
    )

    assert run_id == get_agent_run_id()
    assert get_current_agent_id() == "fta"

    report = store.get_run(run_id)
    manifest = report.manifest
    assert manifest.run_type == "pipeline"
    assert manifest.pipeline_thread_id == "thread-001"
    assert manifest.harness_status == "incomplete"
    assert manifest.intent_count == 1
    assert manifest.ingestion_snapshot == "pipeline-run"

    close_agent_run()


def test_close_agent_run_computes_provenance_rates(store: SqliteEvalStore):
    set_pipeline_thread("thread-rates")
    run_id = open_agent_run(
        "fta",
        company_name="Elder Care",
        catalog="uc13_ale",
        affected_intents=[
            "fta.opex.q1_financial_statements",
            "fta.opex.q2_opex_detail",
            "fta.revenue.q1_revenue",
        ],
        store=store,
    )
    store.append_provenance(
        run_id,
        [
            _provenance_record(
                intent_id="fta.opex.q1_financial_statements",
                mode="semantic",
            ),
            _provenance_record(
                intent_id="fta.opex.q2_opex_detail",
                mode="keyword",
            ),
            _provenance_record(
                intent_id="fta.revenue.q1_revenue",
                mode="empty",
            ),
        ],
    )

    finalized = close_agent_run()
    assert finalized.harness_status == "complete"
    assert finalized.fallback_rate == pytest.approx(1 / 3)
    assert finalized.empty_rate == pytest.approx(1 / 3)
    assert get_agent_run_id() is None


def test_double_open_agent_run_raises(store: SqliteEvalStore):
    set_pipeline_thread("thread-double")
    open_agent_run(
        "fta",
        company_name="Elder Care",
        catalog="uc13_ale",
        affected_intents=["fta.opex.q1_financial_statements"],
        store=store,
    )
    with pytest.raises(RunContextError, match="already open"):
        open_agent_run(
            "fta",
            company_name="Elder Care",
            catalog="uc13_ale",
            affected_intents=["fta.opex.q1_financial_statements"],
            store=store,
        )
    close_agent_run()


def test_close_without_open_raises():
    with pytest.raises(RunContextError, match="no open agent run"):
        close_agent_run()


def test_pipeline_manifest_allows_finalize_without_harness_results(
    store: SqliteEvalStore,
):
    """Pipeline runs finalize on provenance only — no HarnessResult rows required."""
    set_pipeline_thread("thread-no-results")
    run_id = open_agent_run(
        "bma",
        company_name="Elder Care",
        catalog="uc13_ale",
        affected_intents=["bma.overview"],
        store=store,
    )
    finalized = close_agent_run()
    assert finalized.run_id == run_id
    assert finalized.harness_status == "complete"


def test_pipeline_manifest_accepts_env_pins(store: SqliteEvalStore, monkeypatch):
    monkeypatch.setenv("RE2_INGESTION_SNAPSHOT", "uc13_ale:99:2026-07-02")
    monkeypatch.setenv("RE2_REGISTRY_HASH", "c" * 64)
    monkeypatch.setenv("RE2_GOLD_SNAPSHOT", "d" * 64)

    set_pipeline_thread("thread-env")
    run_id = open_agent_run(
        "legal",
        company_name="Elder Care",
        catalog="uc13_ale",
        affected_intents=[],
        store=store,
    )
    manifest = store.get_run(run_id).manifest
    assert manifest.ingestion_snapshot == "uc13_ale:99:2026-07-02"
    assert manifest.registry_hash == "c" * 64
    assert manifest.gold_snapshot == "d" * 64
    close_agent_run()


def test_compute_provenance_rates_normalizes_keyword_fallback_alias(
    store: SqliteEvalStore,
):
    """keyword_fallback must count toward fallback_rate (MODE_ALIASES parity)."""
    set_pipeline_thread("thread-alias")
    run_id = open_agent_run(
        "fta",
        company_name="Elder Care",
        catalog="uc13_ale",
        affected_intents=["fta.opex.q1_financial_statements"],
        store=store,
    )
    store.append_provenance(
        run_id,
        [
            _provenance_record(
                intent_id="fta.opex.q1_financial_statements",
                mode="keyword_fallback",
            )
        ],
    )
    fallback_rate, _ = store.compute_provenance_rates(run_id)
    assert fallback_rate == pytest.approx(1.0)
    close_agent_run()


def test_load_affected_intents_resolves_registry_from_repo_root_not_databricks():
    """Falsifier: find_repo_root('agents') → databricks/ must not break registry load."""
    intents = load_affected_intents("fta")
    assert intents
    assert all(intent_id.startswith("fta.") for intent_id in intents)
    assert "fta.opex.q1_financial_statements" in intents


def test_threadpool_worker_without_copied_context_loses_agent_run_id(store):
    """Characterizes the bug: raw ThreadPoolExecutor.submit does not inherit ContextVars.

    financial_trends_agent.FinancialTrendsAgent.run() fans out to three sub-agents via
    ThreadPoolExecutor(max_workers=3). Without an explicit copied Context per submit,
    get_agent_run_id() (and therefore provenance emission) sees the default None inside
    worker threads even though open_agent_run() succeeded on the submitting thread —
    the exact cause of zero retrieval_provenance rows on an otherwise 'complete' pipeline run.
    """
    open_agent_run(
        "fta",
        company_name="Elder Care",
        catalog="uc13_ale",
        affected_intents=["fta.opex.q1_financial_statements"],
        store=store,
    )

    with ThreadPoolExecutor(max_workers=1) as pool:
        seen_in_worker = pool.submit(get_agent_run_id).result()

    assert get_agent_run_id() is not None  # still open on the main thread
    assert seen_in_worker is None  # lost without an explicit context copy
    close_agent_run()


def test_threadpool_worker_with_copied_context_preserves_agent_run_id(store):
    """Falsifier for the fix: contextvars.copy_context().run(...) must propagate agent_run_id."""
    run_id = open_agent_run(
        "fta",
        company_name="Elder Care",
        catalog="uc13_ale",
        affected_intents=["fta.opex.q1_financial_statements"],
        store=store,
    )

    with ThreadPoolExecutor(max_workers=1) as pool:
        seen_in_worker = pool.submit(contextvars.copy_context().run, get_agent_run_id).result()

    assert seen_in_worker == run_id
    close_agent_run()


def test_open_agent_run_spark_param_builds_delta_store(monkeypatch):
    """Injected spark must bind Delta store even when getActiveSession() is None."""
    from datetime import datetime, timezone

    from eval.retrieval.models import HarnessRun

    mock_spark = object()
    captured: dict[str, object] = {}

    class _FakeDelta:
        def __init__(self, spark, *, catalog: str) -> None:
            captured["spark"] = spark
            captured["catalog"] = catalog

        def insert_run(self, manifest) -> None:
            captured["manifest_catalog"] = manifest.catalog
            self._manifest = manifest

        def compute_provenance_rates(self, run_id: str):
            return 0.0, 0.0

        def finalize_run(self, run_id, **kwargs):
            m = self._manifest
            return HarnessRun(
                run_id=m.run_id,
                run_type=m.run_type,
                pipeline_thread_id=m.pipeline_thread_id,
                company_name=m.company_name,
                catalog=m.catalog,
                ingestion_snapshot=m.ingestion_snapshot,
                registry_hash=m.registry_hash,
                gold_snapshot=m.gold_snapshot,
                git_sha=m.git_sha,
                affected_intents=m.affected_intents,
                gated_intents=m.gated_intents,
                store_backend="delta",
                harness_status="complete",
                intent_count=m.intent_count,
                created_at=datetime.now(timezone.utc),
            )

    monkeypatch.setattr("agents.shared.run_context.DeltaEvalStore", _FakeDelta)
    monkeypatch.setattr("eval.retrieval.provenance._active_spark", lambda: None)

    set_pipeline_thread("thread-spark-inject")
    open_agent_run(
        "fta",
        company_name="Elder Care",
        catalog="uc13_ale",
        affected_intents=["fta.opex.q1_financial_statements"],
        spark=mock_spark,
    )

    assert captured["spark"] is mock_spark
    assert captured["catalog"] == "uc13_ale"
    assert captured["manifest_catalog"] == "uc13_ale"
    close_agent_run()


def test_open_agent_run_spark_param_from_worker_thread(monkeypatch):
    """DAG worker threads have no active Spark session; injected spark still binds Delta."""
    mock_spark = object()
    seen: dict[str, object] = {}

    class _FakeDelta:
        def __init__(self, spark, *, catalog: str) -> None:
            seen["spark"] = spark
            seen["catalog"] = catalog

        def insert_run(self, manifest) -> None:
            pass

    monkeypatch.setattr("agents.shared.run_context.DeltaEvalStore", _FakeDelta)
    monkeypatch.setattr("eval.retrieval.provenance._active_spark", lambda: None)

    def _worker() -> None:
        open_agent_run(
            "fta",
            company_name="Elder Care",
            catalog="uc13_ale",
            affected_intents=["fta.opex.q1_financial_statements"],
            spark=mock_spark,
        )

    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(_worker).result()

    assert seen["spark"] is mock_spark
    assert seen["catalog"] == "uc13_ale"
