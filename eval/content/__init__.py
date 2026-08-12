"""Content-eval machinery (S2 judge calibration, agreement predicates)."""

from eval.content.agreement import (
    compute_metrics,
    spans_agree,
    values_agree,
    verdicts_agree,
)
from eval.content.s2_writer import S2ScoreRow, S2Writer

__all__ = [
    "S2ScoreRow",
    "S2Writer",
    "compute_metrics",
    "spans_agree",
    "values_agree",
    "verdicts_agree",
]
