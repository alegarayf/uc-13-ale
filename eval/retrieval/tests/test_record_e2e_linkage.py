"""record_e2e_linkage CLI contract tests — M-RE2 T9."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from eval.retrieval.errors import RunNotFoundError
from eval.retrieval.models import HarnessRun
from eval.retrieval.scripts import record_e2e_linkage as linkage_module
from eval.retrieval.store import SqliteEvalStore


@pytest.fixture
def store(tmp_path) -> SqliteEvalStore:
    db = SqliteEvalStore(tmp_path / "re2_store.sqlite")
    yield db
    db.close()


def _pipeline_manifest(*, run_id: str = "pipeline_fta_001") -> HarnessRun:
    return HarnessRun(
        run_id=run_id,
        run_type="pipeline",
        pipeline_thread_id="thread-abc",
        company_name="Elder Care",
        catalog="uc13_ale",
        ingestion_snapshot="uc13_ale:35034:2026-07-02",
        registry_hash="a" * 64,
        gold_snapshot="b" * 64,
        affected_intents=["fta.opex.q1_financial_statements"],
        gated_intents=[],
        store_backend="sqlite",
        harness_status="incomplete",
        intent_count=1,
        created_at=datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc),
    )


def test_build_parser_parses_checklist_score_as_int():
    parser = linkage_module.build_parser()
    args = parser.parse_args(
        [
            "--run-id",
            "abc123",
            "--e2e-agent-id",
            "fta",
            "--e2e-checklist-score",
            "17",
            "--e2e-checklist-total",
            "18",
            "--e2e-snapshot-table",
            "uc13_ale.analysis.financial_trends_eval_snapshot",
        ]
    )
    assert args.e2e_checklist_score == 17
    assert isinstance(args.e2e_checklist_score, int)
    assert args.catalog == "uc13_ale"


def test_build_parser_rejects_non_integer_checklist_score():
    parser = linkage_module.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "--run-id",
                "abc123",
                "--e2e-agent-id",
                "fta",
                "--e2e-checklist-score",
                "sixteen",
                "--e2e-checklist-total",
                "18",
                "--e2e-snapshot-table",
                "uc13_ale.analysis.financial_trends_eval_snapshot",
            ]
        )


def test_build_parser_requires_e2e_checklist_total():
    parser = linkage_module.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "--run-id",
                "abc123",
                "--e2e-agent-id",
                "fta",
                "--e2e-checklist-score",
                "17",
                "--e2e-snapshot-table",
                "uc13_ale.analysis.financial_trends_eval_snapshot",
            ]
        )


def test_build_parser_rejects_unknown_e2e_agent_id():
    parser = linkage_module.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "--run-id",
                "abc123",
                "--e2e-agent-id",
                "bogus",
                "--e2e-checklist-score",
                "17",
                "--e2e-checklist-total",
                "18",
                "--e2e-snapshot-table",
                "uc13_ale.analysis.financial_trends_eval_snapshot",
            ]
        )


@pytest.mark.parametrize(
    "agent_id",
    ("fta", "legal", "bma", "cqa", "kpi", "qoe", "profiler"),
)
def test_build_parser_accepts_allowlisted_e2e_agent_ids(agent_id: str):
    parser = linkage_module.build_parser()
    args = parser.parse_args(
        [
            "--run-id",
            "abc123",
            "--e2e-agent-id",
            agent_id,
            "--e2e-checklist-score",
            "10",
            "--e2e-checklist-total",
            "18",
            "--e2e-snapshot-table",
            "uc13_ale.analysis.financial_trends_eval_snapshot",
        ]
    )
    assert args.e2e_agent_id == agent_id


def test_record_e2e_linkage_updates_sqlite_manifest(store: SqliteEvalStore):
    manifest = _pipeline_manifest()
    store.insert_run(manifest)
    store.finalize_run(manifest.run_id, gate_pass=None, fallback_rate=0.25)

    updated = linkage_module.record_e2e_linkage(
        manifest.run_id,
        e2e_agent_id="fta",
        e2e_checklist_score=17,
        e2e_checklist_total=18,
        e2e_snapshot_table="uc13_ale.analysis.financial_trends_eval_snapshot",
        store=store,
    )

    assert updated.e2e_agent_id == "fta"
    assert updated.e2e_checklist_score == 17
    assert updated.e2e_checklist_total == 18
    assert (
        updated.e2e_snapshot_table
        == "uc13_ale.analysis.financial_trends_eval_snapshot"
    )

    report = store.get_run(manifest.run_id)
    assert report.manifest.e2e_checklist_score == 17


def test_record_e2e_linkage_raises_when_run_missing(store: SqliteEvalStore):
    with pytest.raises(RunNotFoundError):
        linkage_module.record_e2e_linkage(
            "missing_run",
            e2e_agent_id="fta",
            e2e_checklist_score=16,
            e2e_checklist_total=18,
            e2e_snapshot_table="uc13_ale.analysis.financial_trends_eval_snapshot",
            store=store,
        )


def test_main_returns_nonzero_on_missing_run(store, monkeypatch, tmp_path):
    monkeypatch.setattr(
        linkage_module,
        "_build_store",
        lambda *_args, **_kwargs: store,
    )
    assert (
        linkage_module.main(
            [
                "--run-id",
                "missing_run",
                "--e2e-agent-id",
                "fta",
                "--e2e-checklist-score",
                "16",
                "--e2e-checklist-total",
                "18",
                "--e2e-snapshot-table",
                "uc13_ale.analysis.financial_trends_eval_snapshot",
                "--sqlite-path",
                str(tmp_path / "unused.sqlite"),
            ]
        )
        == 1
    )


def test_record_e2e_linkage_delta_dual_writes_manifest_and_history(monkeypatch):
    calls: list[tuple[str, dict | None]] = []

    class _Row:
        def __init__(self, data: dict) -> None:
            self._data = data

        def asDict(self, recursive: bool = False) -> dict:
            return dict(self._data)

    class _FakeSpark:
        def sql(self, statement: str, args: dict | None = None) -> "_FakeSpark":
            calls.append((statement, args))
            return self

        def collect(self) -> list[_Row]:
            return [
                _Row(
                    {
                        "run_id": "pipeline_bma_001",
                        "run_type": "pipeline",
                        "pipeline_thread_id": "thread-abc",
                        "company_name": "Elder Care",
                        "catalog": "uc13_ale",
                        "ingestion_snapshot": "uc13_ale:55812:2026-08-11",
                        "registry_hash": "a" * 64,
                        "gold_snapshot": "b" * 64,
                        "affected_intents": ["bma.market_position"],
                        "gated_intents": [],
                        "store_backend": "delta",
                        "harness_status": "complete",
                        "intent_count": 1,
                        "e2e_agent_id": "bma",
                        "e2e_snapshot_table": "uc13_ale.analysis.business_model",
                        "e2e_checklist_score": 7,
                        "e2e_checklist_total": 7,
                        "created_at": datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc),
                        "completed_at": datetime(2026, 8, 11, 12, 5, tzinfo=timezone.utc),
                    }
                )
            ]

    manifest_row = {
        "run_id": "pipeline_bma_001",
        "run_type": "pipeline",
        "pipeline_thread_id": "thread-abc",
        "company_name": "Elder Care",
        "catalog": "uc13_ale",
        "ingestion_snapshot": "uc13_ale:55812:2026-08-11",
        "registry_hash": "a" * 64,
        "gold_snapshot": "b" * 64,
        "affected_intents": ["bma.market_position"],
        "gated_intents": [],
        "store_backend": "delta",
        "harness_status": "complete",
        "intent_count": 1,
        "e2e_agent_id": "bma",
        "e2e_snapshot_table": "uc13_ale.analysis.business_model",
        "e2e_checklist_score": 7,
        "e2e_checklist_total": 7,
        "created_at": datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc),
        "completed_at": datetime(2026, 8, 11, 12, 5, tzinfo=timezone.utc),
    }

    fake_store = object.__new__(linkage_module.DeltaEvalStore)
    fake_store.spark = _FakeSpark()
    fake_store.catalog = "uc13_ale"
    monkeypatch.setattr(
        fake_store,
        "get_run",
        lambda _run_id: None,
    )
    monkeypatch.setattr(
        fake_store,
        "_fetch_manifest_row",
        lambda _run_id: dict(manifest_row),
    )
    monkeypatch.setattr(fake_store, "_table", lambda name: f"uc13_ale.ops.{name}")
    monkeypatch.setattr(
        linkage_module.DeltaEvalStore,
        "_manifest_from_row",
        lambda _self, row: HarnessRun(
            run_id=row["run_id"],
            run_type=row["run_type"],
            pipeline_thread_id=row.get("pipeline_thread_id"),
            company_name=row["company_name"],
            catalog=row["catalog"],
            ingestion_snapshot=row["ingestion_snapshot"],
            registry_hash=row["registry_hash"],
            gold_snapshot=row["gold_snapshot"],
            affected_intents=list(row["affected_intents"]),
            gated_intents=list(row.get("gated_intents") or []),
            store_backend=row["store_backend"],
            harness_status=row["harness_status"],
            intent_count=int(row["intent_count"]),
            e2e_agent_id=row.get("e2e_agent_id"),
            e2e_snapshot_table=row.get("e2e_snapshot_table"),
            e2e_checklist_score=row.get("e2e_checklist_score"),
            e2e_checklist_total=row.get("e2e_checklist_total"),
            created_at=row["created_at"],
            completed_at=row.get("completed_at"),
        ),
    )

    updated = linkage_module.record_e2e_linkage(
        "pipeline_bma_001",
        e2e_agent_id="bma",
        e2e_checklist_score=7,
        e2e_checklist_total=7,
        e2e_snapshot_table="uc13_ale.analysis.business_model",
        store=fake_store,
    )

    assert updated.e2e_agent_id == "bma"
    assert len(calls) == 2
    update_sql, update_args = calls[0]
    insert_sql, insert_args = calls[1]
    assert "UPDATE uc13_ale.ops.retrieval_harness_runs" in update_sql
    assert update_args is not None and update_args["e2e_agent_id"] == "bma"
    assert "INSERT INTO uc13_ale.ops.e2e_linkage" in insert_sql
    assert insert_args is not None and insert_args["run_id"] == "pipeline_bma_001"


def test_backfill_e2e_linkage_sql_is_idempotent_by_run_and_agent():
    sql = linkage_module._backfill_e2e_linkage_sql("uc13_ale")
    assert "INSERT INTO uc13_ale.ops.e2e_linkage" in sql
    assert "NOT EXISTS" in sql
    assert "e.run_id = r.run_id" in sql
    assert "e.e2e_agent_id = r.e2e_agent_id" in sql
