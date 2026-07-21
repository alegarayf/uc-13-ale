"""Promotion gate tests — M3 spec §5 / Program Gate G3."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from eval.retrieval.errors import InvalidWaiverIdError
from eval.retrieval.models import HarnessRun
from eval.retrieval.promotion_gate import (
    PromotionResult,
    _validate_waiver_id,
    evaluate_promotion,
)
from eval.retrieval.store import SqliteEvalStore

_COMPANY = "Elder Care"
_CATALOG = "uc13_ale"
_AGENT = "fta"
_SNAPSHOT = "uc13_ale.analysis.financial_trends_eval_snapshot"


@pytest.fixture
def store(tmp_path) -> SqliteEvalStore:
    db = SqliteEvalStore(tmp_path / "re2_store.sqlite")
    yield db
    db.close()


def _sample_pipeline_manifest(
    *,
    run_id: str,
    e2e_agent_id: str = _AGENT,
    catalog: str = _CATALOG,
) -> HarnessRun:
    return HarnessRun(
        run_id=run_id,
        run_type="pipeline",
        company_name=_COMPANY,
        catalog=catalog,
        ingestion_snapshot="uc13_ale:35034:2026-06-25",
        registry_hash="a" * 64,
        gold_snapshot="b" * 64,
        affected_intents=[],
        gated_intents=[],
        store_backend="sqlite",
        harness_status="incomplete",
        intent_count=0,
        e2e_agent_id=e2e_agent_id,
        created_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
    )


def _insert_finalized_candidate(store: SqliteEvalStore, run_id: str) -> str:
    manifest = _sample_pipeline_manifest(run_id=run_id)
    store.insert_run(manifest)
    store.finalize_run(manifest.run_id, gate_pass=None, fallback_rate=None)
    return run_id


def _finalize_pipeline_with_e2e_score(
    store: SqliteEvalStore,
    manifest: HarnessRun,
    *,
    score: int,
    total: int,
    completed_at: datetime,
) -> None:
    store.insert_run(manifest)
    store.finalize_run(manifest.run_id, gate_pass=None, fallback_rate=None)
    store._conn.execute(
        """
        UPDATE retrieval_harness_runs
        SET e2e_checklist_score = ?,
            e2e_checklist_total = ?,
            completed_at = ?
        WHERE run_id = ?
        """,
        (
            score,
            total,
            completed_at.astimezone(timezone.utc).isoformat(),
            manifest.run_id,
        ),
    )
    store._conn.commit()


def _evaluate(
    store: SqliteEvalStore,
    run_id: str,
    *,
    score: int,
    total: int = 18,
    waiver_id: str | None = None,
) -> PromotionResult:
    return evaluate_promotion(
        store,
        run_id,
        e2e_agent_id=_AGENT,
        company_name=_COMPANY,
        catalog=_CATALOG,
        candidate_score=score,
        candidate_total=total,
        e2e_snapshot_table=_SNAPSHOT,
        waiver_id=waiver_id,
    )


def test_evaluate_promotion_baseline_bootstrap_when_no_prior_exists(
    store: SqliteEvalStore,
):
    run_id = _insert_finalized_candidate(store, "bootstrap_candidate")

    result = _evaluate(store, run_id, score=12, total=18)

    assert result.status == "baseline_bootstrap"
    assert result.prior_run_id is None
    assert result.prior_score is None
    manifest = store.get_run(run_id).manifest
    assert manifest.e2e_checklist_score == 12
    assert manifest.e2e_checklist_total == 18


def test_evaluate_promotion_selects_most_recent_prior_baseline(
    store: SqliteEvalStore,
):
    older = _sample_pipeline_manifest(run_id="prior_older")
    _finalize_pipeline_with_e2e_score(
        store,
        older,
        score=8,
        total=18,
        completed_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
    )
    newer = _sample_pipeline_manifest(run_id="prior_newer")
    _finalize_pipeline_with_e2e_score(
        store,
        newer,
        score=12,
        total=18,
        completed_at=datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc),
    )
    _insert_finalized_candidate(store, "tie_candidate")

    result = _evaluate(store, "tie_candidate", score=12)

    assert result.status == "promoted"
    assert result.prior_run_id == "prior_newer"
    assert result.prior_score == 12


def test_evaluate_promotion_blocks_on_regression_without_waiver(
    store: SqliteEvalStore,
):
    prior = _sample_pipeline_manifest(run_id="prior_baseline")
    _finalize_pipeline_with_e2e_score(
        store,
        prior,
        score=10,
        total=18,
        completed_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
    )
    _insert_finalized_candidate(store, "blocked_candidate")

    result = _evaluate(store, "blocked_candidate", score=7)

    assert result.status == "promotion_blocked"
    assert result.prior_run_id == "prior_baseline"
    assert result.prior_score == 10
    blocked = store.get_run("blocked_candidate").manifest
    assert blocked.e2e_checklist_score is None
    assert blocked.e2e_checklist_total is None


def test_evaluate_promotion_promotes_on_tie(store: SqliteEvalStore):
    prior = _sample_pipeline_manifest(run_id="prior_for_tie")
    _finalize_pipeline_with_e2e_score(
        store,
        prior,
        score=14,
        total=18,
        completed_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
    )
    _insert_finalized_candidate(store, "tie_run")

    result = _evaluate(store, "tie_run", score=14)

    assert result.status == "promoted"
    assert result.prior_score == 14
    manifest = store.get_run("tie_run").manifest
    assert manifest.e2e_checklist_score == 14


def test_evaluate_promotion_promotes_on_improvement(store: SqliteEvalStore):
    prior = _sample_pipeline_manifest(run_id="prior_for_improve")
    _finalize_pipeline_with_e2e_score(
        store,
        prior,
        score=11,
        total=18,
        completed_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
    )
    _insert_finalized_candidate(store, "improved_run")

    result = _evaluate(store, "improved_run", score=15)

    assert result.status == "promoted"
    assert result.prior_score == 11
    manifest = store.get_run("improved_run").manifest
    assert manifest.e2e_checklist_score == 15


def test_evaluate_promotion_waives_regression_with_valid_waiver(
    store: SqliteEvalStore,
):
    prior = _sample_pipeline_manifest(run_id="prior_for_waiver")
    _finalize_pipeline_with_e2e_score(
        store,
        prior,
        score=16,
        total=18,
        completed_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
    )
    _insert_finalized_candidate(store, "waived_run")

    result = _evaluate(store, "waived_run", score=13, waiver_id="W3")

    assert result.status == "promotion_waived"
    assert result.waiver_id == "W3"
    assert result.prior_score == 16
    manifest = store.get_run("waived_run").manifest
    assert manifest.e2e_checklist_score == 13


@pytest.mark.parametrize(
    "invalid_waiver",
    ["W-1", "waiver-1", "1", ""],
)
def test_evaluate_promotion_raises_invalid_waiver_id_error(
    store: SqliteEvalStore,
    invalid_waiver: str,
):
    prior = _sample_pipeline_manifest(run_id="prior_for_invalid_waiver")
    _finalize_pipeline_with_e2e_score(
        store,
        prior,
        score=12,
        total=18,
        completed_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
    )
    _insert_finalized_candidate(store, "invalid_waiver_run")

    with pytest.raises(InvalidWaiverIdError):
        _evaluate(store, "invalid_waiver_run", score=9, waiver_id=invalid_waiver)

    manifest = store.get_run("invalid_waiver_run").manifest
    assert manifest.e2e_checklist_score is None


def test_validate_waiver_id_accepts_valid_format():
    _validate_waiver_id(None)
    _validate_waiver_id("W1")
    _validate_waiver_id("W12")


def test_validate_waiver_id_rejects_malformed_ids():
    with pytest.raises(InvalidWaiverIdError):
        _validate_waiver_id("waiver1")


def test_evaluate_promotion_compares_raw_score_not_ratio(store: SqliteEvalStore):
    """Non-default total proves comparison is on score, not score/total ratio."""
    prior = _sample_pipeline_manifest(run_id="prior_qoe_total5")
    _finalize_pipeline_with_e2e_score(
        store,
        prior,
        score=3,
        total=5,
        completed_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
    )
    _insert_finalized_candidate(store, "ratio_trap_candidate")

    # Raw score 4 > 3 promotes; ratio 4/18 < 3/5 would block if ratio were used.
    result = _evaluate(store, "ratio_trap_candidate", score=4, total=18)

    assert result.status == "promoted"
    assert result.prior_score == 3
    manifest = store.get_run("ratio_trap_candidate").manifest
    assert manifest.e2e_checklist_score == 4
    assert manifest.e2e_checklist_total == 18


def test_evaluate_promotion_h1r_blocked_run_never_becomes_next_baseline(
    store: SqliteEvalStore,
):
    prior = _sample_pipeline_manifest(run_id="prior_promoted_baseline")
    _finalize_pipeline_with_e2e_score(
        store,
        prior,
        score=10,
        total=18,
        completed_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
    )
    _insert_finalized_candidate(store, "h1r_blocked_run")

    blocked = _evaluate(store, "h1r_blocked_run", score=5)
    assert blocked.status == "promotion_blocked"

    blocked_manifest = store.get_run("h1r_blocked_run").manifest
    assert blocked_manifest.e2e_checklist_score is None

    baseline = store.select_prior_e2e_baseline(
        _AGENT,
        _COMPANY,
        catalog=_CATALOG,
    )
    assert baseline is not None
    assert baseline.run_id == "prior_promoted_baseline"
    assert baseline.run_id != "h1r_blocked_run"
    assert baseline.e2e_checklist_score == 10
