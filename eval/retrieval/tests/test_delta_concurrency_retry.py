"""Delta concurrent-MERGE retry tests — M-RE2 post-landing fix.

FTA's three sub-agent threads (Revenue/EBITDA/OPEX) each write provenance to the
same `retrieval_provenance` Delta table once the T4 contextvars fix let them see
the open agent run. Concurrent MERGE/UPDATE transactions on the same table can
raise ConcurrentAppendException / DELTA_CONCURRENT_APPEND_ROW_LEVEL_CHANGES even
when the row sets are logically disjoint. `retry_on_delta_conflict` retries those
conflicts with backoff and re-raises everything else immediately.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from eval.retrieval.models import HarnessRun
from eval.retrieval.store import (
    DeltaEvalStore,
    _is_delta_concurrency_conflict,
    retry_on_delta_conflict,
)


class _ConcurrentAppendException(Exception):
    """Stand-in for the real Delta/Spark-Connect exception class.

    Deliberately not named/imported from pyspark: classic PySpark, Spark Connect,
    and Databricks Runtime versions surface this conflict as different concrete
    classes. `_is_delta_concurrency_conflict` matches by name/message text, so
    this stand-in class name alone is enough to exercise the real matching logic.
    """


def _real_world_error_text() -> str:
    return (
        "[DELTA_CONCURRENT_APPEND_ROW_LEVEL_CHANGES] Transaction conflict "
        "detected. A concurrent MERGE added data to table "
        "uc13_ale.ops.retrieval_provenance committed at version 23. The "
        "concurrent operation modified the same rows that this transaction "
        "attempted to modify. Please retry the operation."
    )


def test_is_delta_concurrency_conflict_matches_real_world_message():
    exc = _ConcurrentAppendException(_real_world_error_text())
    assert _is_delta_concurrency_conflict(exc)


@pytest.mark.parametrize(
    "exc",
    [
        ValueError("some unrelated value error"),
        RuntimeError("Active SparkSession required"),
        KeyError("run_id"),
    ],
)
def test_is_delta_concurrency_conflict_does_not_match_unrelated_errors(exc):
    assert not _is_delta_concurrency_conflict(exc)


def test_retry_on_delta_conflict_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr("eval.retrieval.store.time.sleep", lambda _seconds: None)
    attempts = {"count": 0}

    def _flaky():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise _ConcurrentAppendException(_real_world_error_text())
        return "committed"

    result = retry_on_delta_conflict(_flaky, max_attempts=5, base_delay=0.01)

    assert result == "committed"
    assert attempts["count"] == 3


def test_retry_on_delta_conflict_reraises_non_conflict_immediately(monkeypatch):
    monkeypatch.setattr("eval.retrieval.store.time.sleep", lambda _seconds: pytest.fail("must not sleep"))
    attempts = {"count": 0}

    def _always_value_error():
        attempts["count"] += 1
        raise ValueError("not a Delta conflict")

    with pytest.raises(ValueError, match="not a Delta conflict"):
        retry_on_delta_conflict(_always_value_error, max_attempts=5, base_delay=0.01)

    assert attempts["count"] == 1  # no retry for non-conflict exceptions


def test_retry_on_delta_conflict_raises_last_exception_after_exhausting_attempts(monkeypatch):
    monkeypatch.setattr("eval.retrieval.store.time.sleep", lambda _seconds: None)
    attempts = {"count": 0}

    def _always_conflict():
        attempts["count"] += 1
        raise _ConcurrentAppendException(f"{_real_world_error_text()} (attempt {attempts['count']})")

    with pytest.raises(_ConcurrentAppendException, match="attempt 3"):
        retry_on_delta_conflict(_always_conflict, max_attempts=3, base_delay=0.01)

    assert attempts["count"] == 3


class _FakeFrame:
    def __init__(self, sql_log: list[str]) -> None:
        self._sql_log = sql_log
        self.created_views: list[str] = []

    def createOrReplaceTempView(self, name: str) -> None:
        self.created_views.append(name)


class _FakeSpark:
    def __init__(self) -> None:
        self.sql_log: list[str] = []
        self.created_views: list[str] = []

    def createDataFrame(self, rows, schema):  # noqa: ANN001 - test stub
        return _FakeFrame(self.sql_log)

    def sql(self, statement: str, args: dict | None = None):  # noqa: ANN001 - test stub
        self.sql_log.append(statement)

        class _EmptyResult:
            @staticmethod
            def collect():
                return []

        return _EmptyResult()


def _fake_manifest(run_id: str) -> HarnessRun:
    return HarnessRun(
        run_id=run_id,
        run_type="pipeline",
        pipeline_thread_id="thread-1",
        company_name="Elder Care",
        catalog="uc13_ale",
        ingestion_snapshot="pipeline-run",
        registry_hash="pipeline-run",
        gold_snapshot="pipeline-run",
        affected_intents=["fta.opex.q1_financial_statements"],
        gated_intents=[],
        store_backend="delta",
        harness_status="incomplete",
        intent_count=1,
        created_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
    )


def test_append_provenance_uses_unique_temp_view_per_call(monkeypatch):
    """Falsifier for a shared-name temp-view race across concurrent threads.

    A fixed temp view name ("incoming_provenance") would let a second thread's
    createOrReplaceTempView silently replace the first thread's view before its
    MERGE reads it — corrupting data without raising any exception. Each call
    must use a unique view name and reference that same name in its MERGE.
    """
    from eval.retrieval.models import ProvenanceChunk, ProvenanceRecord

    spark = _FakeSpark()
    store = DeltaEvalStore(spark, catalog="uc13_ale")
    monkeypatch.setattr(store, "_ensure_not_complete", _fake_manifest)

    def _record(run_id: str, chunk_id: str) -> ProvenanceRecord:
        return ProvenanceRecord(
            intent_id="fta.opex.q1_financial_statements",
            company_name="Elder Care",
            query="q",
            mode="semantic",
            run_id=run_id,
            chunks=[
                ProvenanceChunk(
                    chunk_id=chunk_id,
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

    store.append_provenance("run_a", [_record("run_a", "chunk-1")])
    store.append_provenance("run_a", [_record("run_a", "chunk-2")])

    merge_statements = [s for s in spark.sql_log if "MERGE INTO" in s]
    assert len(merge_statements) == 2

    view_names_used = []
    for statement in merge_statements:
        assert "incoming_provenance_" in statement, "expected a unique per-call temp view name"
        start = statement.index("USING ") + len("USING ")
        end = statement.index(" AS source")
        view_names_used.append(statement[start:end].strip())

    assert len(set(view_names_used)) == 2, "each append_provenance call must use a distinct temp view name"
