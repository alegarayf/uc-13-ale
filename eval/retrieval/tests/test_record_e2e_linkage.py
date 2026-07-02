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
                "--e2e-snapshot-table",
                "uc13_ale.analysis.financial_trends_eval_snapshot",
            ]
        )


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
                "--e2e-snapshot-table",
                "uc13_ale.analysis.financial_trends_eval_snapshot",
                "--sqlite-path",
                str(tmp_path / "unused.sqlite"),
            ]
        )
        == 1
    )
