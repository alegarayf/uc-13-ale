"""Checklist-regression promotion gate — M3 eval harness."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from eval.retrieval.errors import InvalidWaiverIdError

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
