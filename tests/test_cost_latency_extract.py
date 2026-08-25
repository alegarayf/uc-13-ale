"""Hermetic arithmetic pins for T5 cost/latency extract (C5 / C18).

On a clone without ``.dev/analysis/cim-vs-vdr/run_fair_experiment_arm.py``, tests
skip (same path-exists guard as ``test_run_fair_experiment_arm``).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DRIVER_PATH = REPO_ROOT / ".dev" / "analysis" / "cim-vs-vdr" / "run_fair_experiment_arm.py"

if not DRIVER_PATH.is_file():
    pytest.skip(
        "gitignored driver missing — skip on clones without .dev/analysis/",
        allow_module_level=True,
    )

_spec = importlib.util.spec_from_file_location("run_fair_experiment_arm", DRIVER_PATH)
assert _spec and _spec.loader
rfe = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("run_fair_experiment_arm", rfe)
_spec.loader.exec_module(rfe)

# C40 Wave 0 run-card token_breakdown (jobs 727024842940292 / 606810294015422).
# Fixtures, not live warehouse reads — C16.
C40_BREAKDOWN_A = {
    "databricks-bge-large-en": {
        "prompt_tokens": 1983,
        "completion_tokens": 0,
        "total_tokens": 1983,
    },
    "databricks-claude-sonnet-4-6": {
        "prompt_tokens": 533594,
        "completion_tokens": 78602,
        "total_tokens": 612196,
    },
}
C40_BREAKDOWN_B = {
    "databricks-bge-large-en": {
        "prompt_tokens": 2075,
        "completion_tokens": 0,
        "total_tokens": 2075,
    },
    "databricks-claude-sonnet-4-6": {
        "prompt_tokens": 184053,
        "completion_tokens": 64144,
        "total_tokens": 248197,
    },
}
C40_TOTALS_A = {"prompt_tokens": 535577, "completion_tokens": 78602, "total_tokens": 614179}
C40_TOTALS_B = {"prompt_tokens": 186128, "completion_tokens": 64144, "total_tokens": 250272}


def _halt_if_breakdown_missing(token_totals: dict, token_breakdown: dict) -> None:
    if token_totals.get("total_tokens", 0) > 0 and not token_breakdown:
        raise ValueError("token_breakdown missing or empty when total_tokens > 0")


def test_c40_estimated_cost_matches_endpoint_pricing() -> None:
    assert rfe.estimate_cost_usd(C40_BREAKDOWN_A) == 2.78
    assert rfe.estimate_cost_usd(C40_BREAKDOWN_B) == 1.5145


def test_delta_is_a_minus_b_not_b_minus_a() -> None:
    cost_a = rfe.estimate_cost_usd(C40_BREAKDOWN_A)
    cost_b = rfe.estimate_cost_usd(C40_BREAKDOWN_B)
    assert round(cost_a - cost_b, 4) == 1.2655
    assert C40_TOTALS_A["total_tokens"] - C40_TOTALS_B["total_tokens"] == 363907
    assert C40_TOTALS_A["prompt_tokens"] - C40_TOTALS_B["prompt_tokens"] == 349449
    assert C40_TOTALS_A["completion_tokens"] - C40_TOTALS_B["completion_tokens"] == 14458


def test_halt_when_breakdown_empty_and_totals_nonzero() -> None:
    with pytest.raises(ValueError, match="token_breakdown"):
        _halt_if_breakdown_missing(C40_TOTALS_A, {})
    _halt_if_breakdown_missing(C40_TOTALS_A, C40_BREAKDOWN_A)
