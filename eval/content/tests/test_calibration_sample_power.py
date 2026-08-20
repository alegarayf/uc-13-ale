"""Hermetic pins for the rebalanced exec_summary calibration sample (T2 / M3)."""

from __future__ import annotations

from pathlib import Path

import yaml

from eval.content.agreement import compute_sample_composition, evaluate_thresholds

REPO = Path(__file__).resolve().parents[3]
SAMPLE = REPO / "eval/content/calibration_samples/calibration_sample_exec_summary.yaml"

_NO_RELABEL_IDS = (
    "exec.claim.003",
    "exec.claim.004",
    "exec.claim.017",
    "exec.claim.019",
    "exec.claim.025",
    "exec.claim.026",
)


def _load_sample() -> dict:
    return yaml.safe_load(SAMPLE.read_text(encoding="utf-8"))


def _composition():
    return compute_sample_composition(_load_sample())


def _perfect_judge_result():
    return evaluate_thresholds(
        "exec_summary",
        {"verdict_agreement": 1.0},
        sample_composition=_composition(),
    )


def test_exec_summary_sample_composition_pins() -> None:
    composition = _composition()
    assert composition.retained_count == 28
    assert composition.verdict_counts == {
        "supported": 26,
        "unsupported": 1,
        "contradicted": 1,
    }
    assert composition.distinct_expected_chunk_ids == 13


def test_exec_summary_sample_p1_and_p3_pass_with_perfect_judge() -> None:
    result = _perfect_judge_result()
    assert not any(r.startswith("P1:") for r in result.failure_reasons)
    assert not any(r.startswith("P3:") for r in result.failure_reasons)
    unevaluated = " ".join(result.unevaluated_pins)
    assert "P1:" not in unevaluated
    assert "P3:" not in unevaluated


def test_exec_summary_sample_honest_instrument_fails_p2() -> None:
    """W3 waives the P2 checkpoint, not the code.

    Owning fix: m3-exec-summary-discriminative-probe-build.
    """
    result = _perfect_judge_result()
    assert result.passed is False
    assert any(r.startswith("P2:") for r in result.failure_reasons)


def test_exec_summary_sample_chunk_ids_labelled_except_027() -> None:
    unlabeled = []
    for claim in _load_sample()["claims"]:
        chunk_id = (claim.get("expected_span") or {}).get("chunk_id")
        if chunk_id is None:
            unlabeled.append(claim["claim_id"])
    assert unlabeled == ["exec.claim.027"]


def test_exec_summary_sample_expected_span_has_chunk_id_only() -> None:
    """Backfill locators stay in the backfill; sample spans carry chunk_id only."""
    for claim in _load_sample()["claims"]:
        span = claim.get("expected_span")
        if span is None:
            continue
        assert set(span.keys()) == {"chunk_id"}
        assert span["chunk_id"]


def test_exec_summary_sample_no_relabel_claims_stay_supported() -> None:
    by_id = {c["claim_id"]: c for c in _load_sample()["claims"]}
    for cid in _NO_RELABEL_IDS:
        assert by_id[cid]["verdict"] == "supported"
