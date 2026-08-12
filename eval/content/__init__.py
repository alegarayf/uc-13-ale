"""Content-eval machinery (S2 judge calibration, agreement predicates)."""

from eval.content.agreement import (
    compute_metrics,
    spans_agree,
    values_agree,
    verdicts_agree,
)
from eval.content.s2_writer import S2ScoreRow, S2Writer
from eval.content.spot_check import (
    SpotCheckConfig,
    prepare_spot_check,
    write_spot_check_results,
)

__all__ = [
    "S2ScoreRow",
    "S2Writer",
    "SpotCheckConfig",
    "compute_metrics",
    "prepare_spot_check",
    "spans_agree",
    "values_agree",
    "verdicts_agree",
    "write_spot_check_results",
]
