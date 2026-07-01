"""SqliteEvalStore round-trip tests — spec §5.12.9."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from eval.retrieval.errors import (
    IncompleteResultsError,
    RunCompleteError,
    RunNotFoundError,
    StoreError,
    SyncError,
)
from eval.retrieval.models import (
    HarnessDelta,
    HarnessResult,
    HarnessRun,
    IntentGateSummary,
    ProvenanceChunk,
    ProvenanceRecord,
)
from eval.retrieval.store import EvalStore, SqliteEvalStore, derive_agent_id


@pytest.fixture
def store(tmp_path) -> SqliteEvalStore:
    db = SqliteEvalStore(tmp_path / "re2_store.sqlite")
    yield db
    db.close()


def _sample_manifest(*, run_id: str = "baseline_test_20260701") -> HarnessRun:
    return HarnessRun(
        run_id=run_id,
        run_type="baseline",
        company_name="Elder Care",
        catalog="uc13_ale",
        ingestion_snapshot="uc13_ale:35034:2026-06-25",
        registry_hash="a" * 64,
        gold_snapshot="b" * 64,
        affected_intents=[
            "fta.opex.q1_financial_statements",
            "kpi.revenue",
        ],
        gated_intents=["fta.opex.q1_financial_statements"],
        store_backend="sqlite",
        harness_status="incomplete",
        intent_count=2,
        created_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
    )


def _sample_results() -> list[HarnessResult]:
    return [
        HarnessResult(
            intent_id="fta.opex.q1_financial_statements",
            eval_status="evaluated",
            eval_k=10,
            effective_k=3,
            recall_at_10=1.0,
            precision_at_10=0.9,
            mrr=1.0,
            result_count=3,
            mode="semantic",
        ),
        HarnessResult(
            intent_id="kpi.revenue",
            eval_status="skipped_bootstrap_failed",
            result_count=0,
        ),
    ]


def _sample_provenance() -> list[ProvenanceRecord]:
    return [
        ProvenanceRecord(
            intent_id="fta.opex.q1_financial_statements",
            company_name="Elder Care",
            query="operating expenses",
            mode="semantic",
            chunks=[
                ProvenanceChunk(
                    chunk_id="chunk-001",
                    rank=1,
                    sim_score=0.91,
                    merge_score=0.82,
                    tier=1,
                    section_header="Financial Overview",
                    file_name="CIM.pdf",
                    source_type="text",
                ),
                ProvenanceChunk(
                    chunk_id="chunk-002",
                    rank=2,
                    sim_score=0.88,
                    merge_score=0.79,
                    tier=2,
                    section_header="OPEX",
                    file_name="CIM.pdf",
                    source_type="text",
                ),
            ],
            run_id="baseline_test_20260701",
        )
    ]


def test_sqlite_round_trip_insert_append_finalize_get(store: SqliteEvalStore):
    manifest = _sample_manifest()
    store.insert_run(manifest)
    store.append_results(manifest.run_id, _sample_results())
    store.append_provenance(manifest.run_id, _sample_provenance())
    finalized = store.finalize_run(
        manifest.run_id,
        gate_pass=True,
        fallback_rate=0.0,
        empty_rate=0.5,
    )

    assert finalized.harness_status == "complete"
    assert finalized.gate_pass is True
    assert finalized.fallback_rate == 0.0
    assert finalized.empty_rate == 0.5
    assert finalized.completed_at is not None

    report = store.get_run(manifest.run_id)
    assert report.manifest.run_id == manifest.run_id
    assert len(report.results) == 2
    assert report.results[0].intent_id == "fta.opex.q1_financial_statements"
    assert report.results[1].eval_status == "skipped_bootstrap_failed"


def test_append_results_upserts_on_run_id_intent_id(store: SqliteEvalStore):
    manifest = _sample_manifest()
    store.insert_run(manifest)
    results = _sample_results()
    store.append_results(manifest.run_id, results)
    updated = results[0].model_copy(update={"recall_at_10": 0.25})
    store.append_results(manifest.run_id, [updated])

    report = store.get_run(manifest.run_id)
    evaluated = next(
        row for row in report.results if row.intent_id == updated.intent_id
    )
    assert evaluated.recall_at_10 == 0.25


def test_append_provenance_upserts_on_run_intent_chunk_rank(store: SqliteEvalStore):
    manifest = _sample_manifest()
    store.insert_run(manifest)
    store.append_results(manifest.run_id, _sample_results())
    store.append_provenance(manifest.run_id, _sample_provenance())

    rows = store._conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM retrieval_provenance
        WHERE run_id = ? AND intent_id = ? AND chunk_id = ? AND rank = ?
        """,
        (
            manifest.run_id,
            "fta.opex.q1_financial_statements",
            "chunk-001",
            1,
        ),
    ).fetchone()
    assert rows["c"] == 1

    revised = _sample_provenance()
    revised[0].chunks[0] = revised[0].chunks[0].model_copy(update={"sim_score": 0.42})
    store.append_provenance(manifest.run_id, revised)

    score_row = store._conn.execute(
        """
        SELECT sim_score
        FROM retrieval_provenance
        WHERE run_id = ? AND intent_id = ? AND chunk_id = ? AND rank = ?
        """,
        (
            manifest.run_id,
            "fta.opex.q1_financial_statements",
            "chunk-001",
            1,
        ),
    ).fetchone()
    assert score_row["sim_score"] == pytest.approx(0.42)

    count_row = store._conn.execute(
        "SELECT COUNT(*) AS c FROM retrieval_provenance WHERE run_id = ?",
        (manifest.run_id,),
    ).fetchone()
    assert count_row["c"] == 2


def test_append_deltas_upserts_on_run_intent_metric(store: SqliteEvalStore):
    manifest = _sample_manifest(run_id="enh_001")
    manifest = manifest.model_copy(
        update={
            "run_type": "enhancement",
            "baseline_ref_run_id": "baseline_test_20260701",
        }
    )
    store.insert_run(manifest)
    store.append_results(manifest.run_id, [_sample_results()[0]])
    delta = HarnessDelta(
        run_id=manifest.run_id,
        baseline_ref_run_id="baseline_test_20260701",
        intent_id="fta.opex.q1_financial_statements",
        metric="recall_at_10",
        before=0.4,
        after=0.5,
        delta=0.1,
        gate_pass=True,
        in_gated_scope=True,
    )
    store.append_deltas(manifest.run_id, [delta])
    store.append_deltas(
        manifest.run_id,
        [delta.model_copy(update={"after": 0.6, "delta": 0.2, "gate_pass": False})],
    )

    report = store.get_run(manifest.run_id)
    assert report.deltas is not None
    assert len(report.deltas) == 1
    assert report.deltas[0].after == 0.6
    assert report.deltas[0].gate_pass is False


def test_finalize_run_raises_incomplete_results_error(store: SqliteEvalStore):
    manifest = _sample_manifest()
    store.insert_run(manifest)
    store.append_results(manifest.run_id, [_sample_results()[0]])

    with pytest.raises(IncompleteResultsError):
        store.finalize_run(manifest.run_id, gate_pass=True, fallback_rate=0.0)


def test_insert_run_rejects_complete_duplicate(store: SqliteEvalStore):
    manifest = _sample_manifest()
    store.insert_run(manifest)
    store.append_results(manifest.run_id, _sample_results())
    store.finalize_run(manifest.run_id, gate_pass=True, fallback_rate=0.0)

    with pytest.raises(StoreError):
        store.insert_run(manifest.model_copy(update={"harness_status": "incomplete"}))


def test_append_results_on_complete_run_raises(store: SqliteEvalStore):
    manifest = _sample_manifest()
    store.insert_run(manifest)
    store.append_results(manifest.run_id, _sample_results())
    store.finalize_run(manifest.run_id, gate_pass=True, fallback_rate=0.0)

    with pytest.raises(RunCompleteError):
        store.append_results(manifest.run_id, _sample_results())


def test_get_run_not_found(store: SqliteEvalStore):
    with pytest.raises(RunNotFoundError):
        store.get_run("missing-run")


def test_delete_run_cascade_order(store: SqliteEvalStore):
    manifest = _sample_manifest()
    store.insert_run(manifest)
    store.append_results(manifest.run_id, _sample_results())
    store.append_provenance(manifest.run_id, _sample_provenance())
    store.append_deltas(
        manifest.run_id,
        [
            HarnessDelta(
                run_id=manifest.run_id,
                baseline_ref_run_id="baseline_parent",
                intent_id="fta.opex.q1_financial_statements",
                metric="mrr",
                before=0.1,
                after=0.2,
                delta=0.1,
                gate_pass=True,
                in_gated_scope=True,
            )
        ],
    )
    store.delete_run(manifest.run_id)

    for table in (
        "retrieval_harness_deltas",
        "retrieval_harness_results",
        "retrieval_provenance",
        "retrieval_harness_runs",
    ):
        count = store._conn.execute(
            f"SELECT COUNT(*) AS c FROM {table} WHERE run_id = ?",
            (manifest.run_id,),
        ).fetchone()["c"]
        assert count == 0


def test_get_latest_baseline_returns_most_recent_complete(store: SqliteEvalStore):
    older = _sample_manifest(run_id="baseline_old")
    store.insert_run(older)
    store.append_results(older.run_id, _sample_results())
    store.finalize_run(older.run_id, gate_pass=True, fallback_rate=0.0)

    newer = _sample_manifest(run_id="baseline_new")
    newer = newer.model_copy(
        update={"created_at": datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)}
    )
    store.insert_run(newer)
    store.append_results(newer.run_id, _sample_results())
    store.finalize_run(newer.run_id, gate_pass=True, fallback_rate=0.0)

    assert store.get_latest_baseline("Elder Care", "uc13_ale") == "baseline_new"


def test_list_runs_clamps_limit_to_500(store: SqliteEvalStore):
    for idx in range(3):
        manifest = _sample_manifest(run_id=f"baseline_{idx}")
        manifest = manifest.model_copy(
            update={
                "created_at": datetime(
                    2026, 7, 1, 12, idx, tzinfo=timezone.utc
                )
            }
        )
        store.insert_run(manifest)
        store.append_results(manifest.run_id, _sample_results())
        store.finalize_run(manifest.run_id, gate_pass=True, fallback_rate=0.0)

    runs = store.list_runs(
        company_name="Elder Care",
        catalog="uc13_ale",
        run_type="baseline",
        limit=999,
    )
    assert len(runs) == 3
    assert store.list_runs(
        company_name="Elder Care",
        catalog="uc13_ale",
        limit=1,
        offset=0,
    )[0].run_id == "baseline_2"


def test_set_report_extras_round_trip(store: SqliteEvalStore):
    manifest = _sample_manifest()
    store.insert_run(manifest)
    store.append_results(manifest.run_id, _sample_results())
    store.set_report_extras(
        manifest.run_id,
        intent_gates=[
            IntentGateSummary(
                intent_id="fta.opex.q1_financial_statements",
                intent_gate_pass=True,
                in_gated_scope=True,
                eval_status="evaluated",
            )
        ],
        rollup_by_agent={"fta.opex": {"intent_count": 1}},
        provenance_sample=_sample_provenance(),
    )
    store.finalize_run(manifest.run_id, gate_pass=True, fallback_rate=0.0)

    report = store.get_run(manifest.run_id)
    assert report.intent_gates is not None
    assert report.intent_gates[0].intent_gate_pass is True
    assert report.rollup_by_agent == {"fta.opex": {"intent_count": 1}}
    assert report.provenance_sample is not None


def test_promote_sqlite_run_requires_delta_backend(store: SqliteEvalStore):
    with pytest.raises(SyncError):
        store.promote_sqlite_run("baseline_test_20260701")


def test_derive_agent_id_fta_partition():
    assert derive_agent_id("fta.opex.q1_financial_statements") == "fta.opex"
    assert derive_agent_id("kpi.revenue") == "kpi"


def test_eval_store_protocol_runtime_check(store: SqliteEvalStore):
    assert isinstance(store, EvalStore)


def test_apply_ops_ddl_sql_contains_catalog_placeholder():
    sql_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "apply_ops_ddl.sql"
    )
    text = sql_path.read_text(encoding="utf-8")
    assert "{catalog}.ops.retrieval_harness_runs" in text
    assert "retrieval_harness_latest_baseline" in text


def test_apply_ops_ddl_load_statements_includes_create_schema_after_file_comments():
    from eval.retrieval.scripts.apply_ops_ddl import _load_statements

    sql_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "apply_ops_ddl.sql"
    )
    statements = _load_statements(sql_path, "uc13_ale")
    assert statements[0].startswith("CREATE SCHEMA IF NOT EXISTS uc13_ale.ops")
    assert any("retrieval_harness_runs" in s for s in statements)
