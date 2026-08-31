"""Hermetic pins for T8 claim re-eval helpers (C10 / C23 / C27).

On a clone without ``.dev/analysis/cim-vs-vdr/run_claim_reeval.py``, tests
skip (same path-exists guard as ``test_run_fair_experiment_arm``).
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DRIVER_PATH = REPO_ROOT / ".dev" / "analysis" / "cim-vs-vdr" / "run_claim_reeval.py"
FROZEN_CLAIMS = REPO_ROOT / "eval" / "content" / "exec_summary_rubric_claims.json"

if not DRIVER_PATH.is_file():
    pytest.skip(
        "gitignored T8 driver missing — skip on clones without .dev/analysis/",
        allow_module_level=True,
    )

_spec = importlib.util.spec_from_file_location("run_claim_reeval", DRIVER_PATH)
assert _spec and _spec.loader
reeval = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("run_claim_reeval", reeval)
_spec.loader.exec_module(reeval)


def test_flip_direction_rank_order() -> None:
    assert reeval.flip_direction("supported", "supported") == "same"
    assert reeval.flip_direction("supported", "unsupported") == "cim_only_worse"
    assert reeval.flip_direction("supported", "contradicted") == "cim_only_worse"
    assert reeval.flip_direction("unsupported", "supported") == "cim_only_better"
    assert reeval.flip_direction("contradicted", "unsupported") == "cim_only_better"
    assert reeval.flip_direction("unsupported", "contradicted") == "cim_only_worse"


def test_assert_arm_catalog_rejects_cross_contamination() -> None:
    reeval.assert_arm_catalog("A", "uc13_ale")
    reeval.assert_arm_catalog("B", "uc13_preview")
    with pytest.raises(reeval.ClaimReevalHalt, match="uc13"):
        reeval.assert_arm_catalog("A", "uc13")
    with pytest.raises(reeval.ClaimReevalHalt, match="catalog=uc13_ale"):
        reeval.assert_arm_catalog("B", "uc13_ale")
    with pytest.raises(reeval.ClaimReevalHalt, match="required"):
        reeval.assert_arm_catalog("A", "uc13_preview")


def test_require_row_count_is_exactly_53() -> None:
    reeval.require_row_count(list(range(53)), arm="A")
    with pytest.raises(reeval.ClaimReevalHalt, match="!= 53"):
        reeval.require_row_count(list(range(52)), arm="A")
    with pytest.raises(reeval.ClaimReevalHalt, match="arm B"):
        reeval.require_row_count(list(range(54)), arm="B")


def test_norm_ts_accepts_space_or_t_separator() -> None:
    assert reeval._norm_ts("2026-08-25T18:37:55.552958") == "2026-08-25 18:37:55"
    assert reeval._norm_ts("2026-08-25 18:37:55.552958") == "2026-08-25 18:37:55"
    reeval._created_at_matches_wave0(
        {"business_model": "2026-08-25 18:37:55.552958"},
        {"business_model": "2026-08-25T18:37:55.552958"},
        arm="A",
    )


def test_repo_root_finds_frozen_claims() -> None:
    assert (reeval.REPO_ROOT / "eval" / "content" / "exec_summary_rubric_claims.json").is_file()
    assert reeval.REPO_ROOT == REPO_ROOT


def test_frozen_claims_are_53_unrewritten() -> None:
    claims = reeval.load_frozen_claims(FROZEN_CLAIMS)
    raw = __import__("json").loads(FROZEN_CLAIMS.read_text(encoding="utf-8"))
    assert len(claims) == 53
    assert [c["claim_id"] for c in claims] == list(reeval.EXPECTED_CLAIM_IDS)
    for loaded, source in zip(claims, raw["claims"], strict=True):
        assert loaded["claim_text"] == source["claim_text"]


def test_script_does_not_invoke_calibration_main() -> None:
    source = DRIVER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "run_calibration":
            pytest.fail("T8 driver references run_calibration")
        if isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name in {"run", "system", "Popen"} and node.args:
                arg0 = node.args[0]
                if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                    if "eval.content.calibration" in arg0.value:
                        pytest.fail("T8 driver shells out to calibration CLI")
    assert "run_calibration(" not in source


def test_arm_b_catalog_constant_is_preview() -> None:
    assert reeval.ARM_CATALOG["B"] == "uc13_preview"
    assert reeval.ARM_CATALOG["A"] == "uc13_ale"
    source = DRIVER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name != "build_exec_dual_source_evidence":
            continue
        for kw in node.keywords:
            if kw.arg == "catalog" and isinstance(kw.value, ast.Constant):
                assert kw.value.value != "uc13_ale", (
                    "Arm-scoped build_exec_dual_source_evidence must take the "
                    "variable catalog, not a hardcoded uc13_ale"
                )
