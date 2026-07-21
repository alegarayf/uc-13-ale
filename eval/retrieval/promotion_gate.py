"""Checklist-regression promotion gate — M3 eval harness."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from eval.retrieval.errors import InvalidWaiverIdError, StoreError
from eval.retrieval.scripts.record_e2e_linkage import record_e2e_linkage
from eval.retrieval.store import EvalStore

_WAIVER_ID_PATTERN = re.compile(r"^W\d+$")


@dataclass(frozen=True)
class PromotionResult:
    """Typed outcome of the checklist-regression promotion gate (Decision M3-C)."""

    status: Literal[
        "baseline_bootstrap",
        "promoted",
        "promotion_blocked",
        "promotion_waived",
    ]
    candidate_score: int
    candidate_total: int
    prior_run_id: str | None
    prior_score: int | None
    waiver_id: str | None


def _validate_waiver_id(waiver_id: str | None) -> None:
    """Raise InvalidWaiverIdError when waiver_id is present but malformed."""
    if waiver_id is None:
        return
    if not _WAIVER_ID_PATTERN.match(waiver_id):
        raise InvalidWaiverIdError(f"invalid waiver_id format: {waiver_id!r}")


def evaluate_promotion(
    store: EvalStore,
    run_id: str,
    *,
    e2e_agent_id: str,
    company_name: str,
    catalog: str,
    candidate_score: int,
    candidate_total: int,
    e2e_snapshot_table: str,
    waiver_id: str | None = None,
) -> PromotionResult:
    """Evaluate checklist-regression promotion per spec §5 state machine (H1-R)."""
    _validate_waiver_id(waiver_id)

    prior = store.select_prior_e2e_baseline(
        e2e_agent_id,
        company_name,
        catalog=catalog,
        exclude_run_id=run_id,
    )

    if prior is None:
        record_e2e_linkage(
            run_id,
            e2e_agent_id=e2e_agent_id,
            e2e_checklist_score=candidate_score,
            e2e_checklist_total=candidate_total,
            e2e_snapshot_table=e2e_snapshot_table,
            store=store,
        )
        return PromotionResult(
            status="baseline_bootstrap",
            candidate_score=candidate_score,
            candidate_total=candidate_total,
            prior_run_id=None,
            prior_score=None,
            waiver_id=waiver_id,
        )

    prior_score = prior.e2e_checklist_score
    if prior_score is None:
        raise StoreError(
            f"prior baseline run {prior.run_id!r} has null e2e_checklist_score "
            "despite select_prior_e2e_baseline predicate"
        )

    if candidate_score >= prior_score:
        record_e2e_linkage(
            run_id,
            e2e_agent_id=e2e_agent_id,
            e2e_checklist_score=candidate_score,
            e2e_checklist_total=candidate_total,
            e2e_snapshot_table=e2e_snapshot_table,
            store=store,
        )
        return PromotionResult(
            status="promoted",
            candidate_score=candidate_score,
            candidate_total=candidate_total,
            prior_run_id=prior.run_id,
            prior_score=prior_score,
            waiver_id=waiver_id,
        )

    if waiver_id is not None:
        record_e2e_linkage(
            run_id,
            e2e_agent_id=e2e_agent_id,
            e2e_checklist_score=candidate_score,
            e2e_checklist_total=candidate_total,
            e2e_snapshot_table=e2e_snapshot_table,
            store=store,
        )
        return PromotionResult(
            status="promotion_waived",
            candidate_score=candidate_score,
            candidate_total=candidate_total,
            prior_run_id=prior.run_id,
            prior_score=prior_score,
            waiver_id=waiver_id,
        )

    return PromotionResult(
        status="promotion_blocked",
        candidate_score=candidate_score,
        candidate_total=candidate_total,
        prior_run_id=prior.run_id,
        prior_score=prior_score,
        waiver_id=waiver_id,
    )
