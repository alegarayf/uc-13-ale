"""Content-eval machinery (S2 judge calibration, agreement predicates)."""

from eval.content.agreement import (
    compute_metrics,
    spans_agree,
    values_agree,
    verdicts_agree,
)
from eval.content.legal_register_verifier import build_claim_rows, derive_locator, verify_legal_register
from eval.content.s2_writer import S2ScoreRow, S2Writer
from eval.content.spot_check import (
    ChunkIndex,
    SpotCheckConfig,
    prepare_spot_check,
    write_spot_check_results,
)

__all__ = [
    "ChunkIndex",
    "S2ScoreRow",
    "S2Writer",
    "SpotCheckConfig",
    "build_claim_rows",
    "derive_locator",
    "compute_metrics",
    "prepare_spot_check",
    "spans_agree",
    "values_agree",
    "verdicts_agree",
    "verify_legal_register",
    "write_spot_check_results",
]
