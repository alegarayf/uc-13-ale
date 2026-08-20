"""Hermetic tests for §8.7 agreement predicates (C4)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from eval.content.agreement import (
    CLAIM_VERDICTS,
    DEGENERATE_FLOOR_MARGIN,
    MAX_MAJORITY_CLASS_FRACTION,
    MIN_DISTINCT_EXPECTED_CHUNK_IDS,
    MIN_SAMPLE_COUNT,
    SampleComposition,
    ThresholdResult,
    compute_metrics,
    compute_sample_composition,
    evaluate_thresholds,
    normalize_unit_magnitude,
    spans_agree,
    values_agree,
    verdicts_agree,
)


# HALT-28: 8-of-32 FTA percentages fail exact equality under IEEE-754 doubles.
HALT_28_PERCENTAGES = [
    "0.9",
    "19.4",
    "19.9",
    "33.4",
    "41.7",
    "42.1",
    "44.3",
    "47.1",
]


@pytest.mark.parametrize("pct", HALT_28_PERCENTAGES)
def test_halt_28_percent_to_ratio_exact_decimal(pct: str) -> None:
    """percent→ratio normalization must be exact under Decimal, not float."""
    expected_ratio = Decimal(pct) / Decimal(100)
    op = normalize_unit_magnitude(pct, "percent")
    ju = normalize_unit_magnitude(str(expected_ratio), "ratio")
    assert op is not None and ju is not None
    assert op == ju
    # Demonstrate float path would disagree for representative case.
    if pct == "19.4":
        float_ratio = 19.4 / 100.0
        assert float(Decimal(str(float_ratio))) != expected_ratio


def test_values_agree_percent_vs_ratio_halting_case() -> None:
    op = {"magnitude": "19.4", "unit": "percent"}
    ju = {"magnitude": "0.194", "unit": "ratio"}
    assert values_agree(op, ju)


def test_values_agree_usd_k_normalization() -> None:
    op = {"magnitude": "2104", "unit": "USD_k"}
    ju = {"magnitude": "2104000", "unit": "USD"}
    assert values_agree(op, ju)


def test_values_agree_one_null_disagrees() -> None:
    op = {"magnitude": "1", "unit": "ratio"}
    assert not values_agree(op, None)
    assert not values_agree(None, op)


def test_values_agree_unresolvable_unit_disagrees() -> None:
    op = {"magnitude": "1", "unit": "ratio"}
    ju = {"magnitude": "1", "unit": "widgets"}
    assert not values_agree(op, ju)


def test_both_null_value_pair_agrees_in_predicate() -> None:
    assert values_agree(None, None)


def test_spans_agree_chunk_only_operator_unlabelled_locator() -> None:
    op = {"chunk_id": "abc", "locator": None}
    ju = {"chunk_id": "abc", "locator": {"kind": "section", "value": "Foo"}}
    assert spans_agree(op, ju)


def test_spans_agree_operator_labelled_judge_null_disagrees() -> None:
    op = {
        "chunk_id": "abc",
        "locator": {"kind": "section", "value": "Historical P&L Summary"},
    }
    ju = {"chunk_id": "abc", "locator": None}
    assert not spans_agree(op, ju)


def test_spans_agree_one_null_span_disagrees() -> None:
    op = {"chunk_id": "abc", "locator": None}
    assert not spans_agree(op, None)
    assert not spans_agree(None, op)


def test_spans_agree_section_case_insensitive() -> None:
    op = {
        "chunk_id": "abc",
        "locator": {"kind": "section", "value": "Historical P&L Summary"},
    }
    ju = {
        "chunk_id": "abc",
        "locator": {"kind": "section", "value": "historical  p&l   summary"},
    }
    assert spans_agree(op, ju)


def test_verdicts_agree_equality() -> None:
    assert verdicts_agree("supported", "supported")
    assert not verdicts_agree("supported", "contradicted")


def test_both_null_excluded_from_numeric_populations() -> None:
    sample = {
        "claims": [
            {
                "claim_id": "both-null",
                "expected_span": None,
                "expected_value": None,
                "verdict": "unsupported",
            },
            {
                "claim_id": "resolved",
                "expected_span": {"chunk_id": "c1", "locator": None},
                "expected_value": {"magnitude": "1", "unit": "ratio"},
                "verdict": "supported",
            },
        ]
    }
    judge_outputs = [
        {"extracted_value": None, "cited_span": None},
        {
            "extracted_value": {"magnitude": "1", "unit": "ratio"},
            "cited_span": {"chunk_id": "c1", "locator": None},
        },
    ]
    figures = compute_metrics(sample, judge_outputs, surface="fta_numeric")
    assert figures["resolved_value_fraction"] == 0.5
    assert figures["resolved_span_fraction"] == 0.5
    assert figures["value_agreement"] == 1.0
    assert figures["span_agreement"] == 1.0


def test_compute_metrics_non_numeric() -> None:
    sample = {
        "claims": [
            {"claim_id": "a", "verdict": "supported"},
            {"claim_id": "b", "verdict": "contradicted"},
        ]
    }
    judge_outputs = [
        {"verdict": "supported"},
        {"verdict": "supported"},
    ]
    figures = compute_metrics(sample, judge_outputs, surface="exec_summary")
    assert figures == {"verdict_agreement": 0.5}


def test_metrics_return_separate_halves_never_combined() -> None:
    sample = {
        "claims": [
            {
                "claim_id": "x",
                "expected_span": {
                    "chunk_id": "c1",
                    "locator": {"kind": "section", "value": "A"},
                },
                "expected_value": {"magnitude": "1", "unit": "ratio"},
            }
        ]
    }
    judge_outputs = [
        {
            "extracted_value": {"magnitude": "1", "unit": "ratio"},
            "cited_span": {
                "chunk_id": "wrong",
                "locator": {"kind": "section", "value": "A"},
            },
        }
    ]
    figures = compute_metrics(sample, judge_outputs, surface="fta_numeric")
    assert "value_agreement" in figures
    assert "span_agreement" in figures
    assert "combined" not in figures
    assert figures["value_agreement"] == 1.0
    assert figures["span_agreement"] == 0.0


def test_s70_null_value_non_null_span_in_span_population() -> None:
    sample = {
        "claims": [
            {
                "claim_id": "s70",
                "expected_span": {"chunk_id": "c1", "locator": None},
                "expected_value": None,
            }
        ]
    }
    judge_outputs = [{"extracted_value": None, "cited_span": {"chunk_id": "c1", "locator": None}}]
    figures = compute_metrics(sample, judge_outputs, surface="fta_numeric")
    assert figures["resolved_span_fraction"] == 1.0
    assert "resolved_value_fraction" in figures
    assert figures.get("value_agreement") is None


def test_empty_resolved_value_population_fails_threshold() -> None:
    sample = {
        "claims": [
            {
                "claim_id": "n",
                "expected_span": None,
                "expected_value": None,
            }
        ]
    }
    judge_outputs = [{"extracted_value": None, "cited_span": None}]
    figures = compute_metrics(sample, judge_outputs, surface="fta_numeric")
    result = evaluate_thresholds("fta_numeric", figures)
    assert not result.passed
    assert any("value resolved population empty" in r for r in result.failure_reasons)
    assert any("span resolved population empty" in r for r in result.failure_reasons)


def test_evaluate_thresholds_non_numeric_pass_and_fail() -> None:
    passed_result = evaluate_thresholds(
        "exec_summary",
        {"verdict_agreement": 0.85},
        sample_composition=_composition_passing_pins(),
    )
    assert passed_result.passed
    failed_result = evaluate_thresholds(
        "exec_summary",
        {"verdict_agreement": 0.75},
        sample_composition=_composition_passing_pins(),
    )
    assert not failed_result.passed
    assert any("verdict_agreement" in r for r in failed_result.failure_reasons)


def test_evaluate_thresholds_numeric_value_pass_and_fail() -> None:
    """C5 pins value_threshold at 0.90 — bracket with literals, not imported defaults."""
    figures = {
        "resolved_value_fraction": 1.0,
        "resolved_span_fraction": 1.0,
        "value_agreement": 0.95,
        "span_agreement": 1.0,
    }
    passed_result = evaluate_thresholds(
        "fta_numeric",
        figures,
        sample_composition=_composition_passing_pins(),
    )
    assert passed_result.passed
    figures_fail = dict(figures, value_agreement=0.85)
    failed_result = evaluate_thresholds(
        "fta_numeric",
        figures_fail,
        sample_composition=_composition_passing_pins(),
    )
    assert not failed_result.passed
    assert any("value_agreement" in r for r in failed_result.failure_reasons)


def test_evaluate_thresholds_numeric_span_pass_and_fail() -> None:
    """C5 pins span_threshold at 0.80 — bracket with literals, not imported defaults."""
    figures = {
        "resolved_value_fraction": 1.0,
        "resolved_span_fraction": 1.0,
        "value_agreement": 1.0,
        "span_agreement": 0.85,
    }
    passed_result = evaluate_thresholds(
        "fta_numeric",
        figures,
        sample_composition=_composition_passing_pins(),
    )
    assert passed_result.passed
    figures_fail = dict(figures, span_agreement=0.75)
    failed_result = evaluate_thresholds(
        "fta_numeric",
        figures_fail,
        sample_composition=_composition_passing_pins(),
    )
    assert not failed_result.passed
    assert any("span_agreement" in r for r in failed_result.failure_reasons)


def test_locator_labelled_fraction() -> None:
    sample = {
        "claims": [
            {
                "claim_id": "a",
                "expected_span": {
                    "chunk_id": "c1",
                    "locator": {"kind": "section", "value": "X"},
                },
                "expected_value": {"magnitude": "1", "unit": "count"},
            },
            {
                "claim_id": "b",
                "expected_span": {"chunk_id": "c2", "locator": None},
                "expected_value": {"magnitude": "2", "unit": "count"},
            },
        ]
    }
    judge_outputs = [
        {"extracted_value": {"magnitude": "1", "unit": "count"}, "cited_span": {}},
        {"extracted_value": {"magnitude": "2", "unit": "count"}, "cited_span": {}},
    ]
    figures = compute_metrics(sample, judge_outputs, surface="fta_numeric")
    assert figures["locator_labelled_fraction"] == 0.5


def _composition_passing_pins() -> SampleComposition:
    """N=25, majority 15/25 = 0.60, 8 chunks — P1–P4 pass on verdict; P1/P3 on numeric."""
    return SampleComposition(
        retained_count=25,
        verdict_counts={"supported": 15, "unsupported": 5, "contradicted": 5},
        distinct_expected_chunk_ids=8,
    )


def _numeric_pass_figures() -> dict[str, float]:
    return {
        "resolved_value_fraction": 1.0,
        "resolved_span_fraction": 1.0,
        "value_agreement": 1.0,
        "span_agreement": 1.0,
    }


def _pin_ids_from(entries: list[str]) -> set[str]:
    found: set[str] = set()
    for entry in entries:
        prefix = entry.split(":", 1)[0]
        if prefix in {"P1", "P2", "P3", "P4"}:
            found.add(prefix)
    return found


def _assert_channels_disjoint(result: ThresholdResult) -> None:
    assert _pin_ids_from(result.failure_reasons).isdisjoint(
        _pin_ids_from(result.unevaluated_pins)
    )


def test_evaluate_thresholds_constant_supported_fails_p4() -> None:
    composition = _composition_passing_pins()
    baseline = 15 / 25
    result = evaluate_thresholds(
        "exec_summary",
        {"verdict_agreement": baseline},
        sample_composition=composition,
    )
    assert not result.passed
    assert any(r.startswith("P4:") for r in result.failure_reasons)
    _assert_channels_disjoint(result)


def test_evaluate_thresholds_p4_margin_boundary() -> None:
    composition = _composition_passing_pins()
    baseline = 15 / 25
    fail_result = evaluate_thresholds(
        "exec_summary",
        {"verdict_agreement": baseline + 0.09},
        sample_composition=composition,
    )
    assert any(r.startswith("P4:") for r in fail_result.failure_reasons)
    pass_result = evaluate_thresholds(
        "exec_summary",
        {"verdict_agreement": baseline + 0.10},
        sample_composition=composition,
    )
    assert not any(r.startswith("P4:") for r in pass_result.failure_reasons)
    _assert_channels_disjoint(fail_result)
    _assert_channels_disjoint(pass_result)


def test_evaluate_thresholds_current_sample_fails_p2_and_p4() -> None:
    composition = SampleComposition(
        retained_count=28,
        verdict_counts={"supported": 26, "unsupported": 1, "contradicted": 1},
        distinct_expected_chunk_ids=0,
    )
    result = evaluate_thresholds(
        "exec_summary",
        {"verdict_agreement": 0.857},
        sample_composition=composition,
    )
    assert not result.passed
    assert any(r.startswith("P2:") for r in result.failure_reasons)
    assert any(r.startswith("P4:") for r in result.failure_reasons)
    _assert_channels_disjoint(result)


def test_evaluate_thresholds_numeric_pins_skipped_not_defaulted() -> None:
    composition = SampleComposition(
        retained_count=25,
        verdict_counts={"supported": 25},
        distinct_expected_chunk_ids=8,
    )
    result = evaluate_thresholds(
        "fta_numeric",
        _numeric_pass_figures(),
        sample_composition=composition,
    )
    assert result.passed
    unevaluated = " ".join(result.unevaluated_pins)
    assert "P2:" in unevaluated
    assert "P4:" in unevaluated
    assert "inapplicable" in unevaluated
    assert "P2" not in _pin_ids_from(result.failure_reasons)
    assert "P4" not in _pin_ids_from(result.failure_reasons)
    _assert_channels_disjoint(result)


def test_evaluate_thresholds_composition_provided_can_pass() -> None:
    result = evaluate_thresholds(
        "exec_summary",
        {"verdict_agreement": 0.85},
        sample_composition=_composition_passing_pins(),
    )
    assert result.passed
    assert result.unevaluated_pins == []
    _assert_channels_disjoint(result)


def test_evaluate_thresholds_omitted_composition_fail_closed_verdict() -> None:
    result = evaluate_thresholds("exec_summary", {"verdict_agreement": 1.0})
    assert not result.passed
    assert _pin_ids_from(result.unevaluated_pins) == {"P1", "P2", "P3", "P4"}
    assert all("omitted" in entry for entry in result.unevaluated_pins)
    _assert_channels_disjoint(result)


def test_evaluate_thresholds_omitted_composition_fail_closed_numeric() -> None:
    result = evaluate_thresholds("fta_numeric", _numeric_pass_figures())
    assert not result.passed
    assert _pin_ids_from(result.unevaluated_pins) == {"P1", "P2", "P3", "P4"}
    assert all("omitted" in entry for entry in result.unevaluated_pins)
    _assert_channels_disjoint(result)


def test_pin_constants_point_literals() -> None:
    assert MIN_SAMPLE_COUNT == 25
    assert MAX_MAJORITY_CLASS_FRACTION == 0.60
    assert MIN_DISTINCT_EXPECTED_CHUNK_IDS == 8
    assert DEGENERATE_FLOOR_MARGIN == 0.10


def test_evaluate_thresholds_p1_boundary() -> None:
    n25 = _composition_passing_pins()
    n24 = SampleComposition(
        retained_count=24,
        verdict_counts={"supported": 14, "unsupported": 5, "contradicted": 5},
        distinct_expected_chunk_ids=8,
    )
    pass_result = evaluate_thresholds(
        "exec_summary", {"verdict_agreement": 0.85}, sample_composition=n25
    )
    fail_result = evaluate_thresholds(
        "exec_summary", {"verdict_agreement": 0.85}, sample_composition=n24
    )
    assert pass_result.passed
    assert not fail_result.passed
    assert any(r.startswith("P1:") for r in fail_result.failure_reasons)
    _assert_channels_disjoint(pass_result)
    _assert_channels_disjoint(fail_result)


def test_evaluate_thresholds_p2_boundary() -> None:
    at_pin = _composition_passing_pins()
    just_above = SampleComposition(
        retained_count=25,
        verdict_counts={"supported": 16, "unsupported": 5, "contradicted": 4},
        distinct_expected_chunk_ids=8,
    )
    pass_result = evaluate_thresholds(
        "exec_summary", {"verdict_agreement": 0.85}, sample_composition=at_pin
    )
    fail_result = evaluate_thresholds(
        "exec_summary", {"verdict_agreement": 0.85}, sample_composition=just_above
    )
    assert pass_result.passed
    assert not fail_result.passed
    assert any(r.startswith("P2:") for r in fail_result.failure_reasons)
    _assert_channels_disjoint(pass_result)
    _assert_channels_disjoint(fail_result)


def test_evaluate_thresholds_p3_boundary() -> None:
    eight = _composition_passing_pins()
    seven = SampleComposition(
        retained_count=25,
        verdict_counts={"supported": 15, "unsupported": 5, "contradicted": 5},
        distinct_expected_chunk_ids=7,
    )
    pass_result = evaluate_thresholds(
        "exec_summary", {"verdict_agreement": 0.85}, sample_composition=eight
    )
    fail_result = evaluate_thresholds(
        "exec_summary", {"verdict_agreement": 0.85}, sample_composition=seven
    )
    assert pass_result.passed
    assert not fail_result.passed
    assert any(r.startswith("P3:") for r in fail_result.failure_reasons)
    _assert_channels_disjoint(pass_result)
    _assert_channels_disjoint(fail_result)


def test_evaluate_thresholds_channel_disjointness_matrix() -> None:
    cases = [
        evaluate_thresholds("exec_summary", {"verdict_agreement": 1.0}),
        evaluate_thresholds("fta_numeric", _numeric_pass_figures()),
        evaluate_thresholds(
            "fta_numeric",
            _numeric_pass_figures(),
            sample_composition=_composition_passing_pins(),
        ),
        evaluate_thresholds(
            "exec_summary",
            {"verdict_agreement": 0.857},
            sample_composition=SampleComposition(
                retained_count=28,
                verdict_counts={"supported": 26, "unsupported": 1, "contradicted": 1},
                distinct_expected_chunk_ids=0,
            ),
        ),
        evaluate_thresholds(
            "exec_summary",
            {"verdict_agreement": 0.85},
            sample_composition=_composition_passing_pins(),
        ),
    ]
    for result in cases:
        _assert_channels_disjoint(result)


def test_compute_sample_composition_round_trip() -> None:
    sample = {
        "claims": [
            {"verdict": "supported", "expected_span": {"chunk_id": "c1"}},
            {"verdict": "supported", "expected_span": {"chunk_id": "c1"}},
            {"verdict": "unsupported", "expected_span": None},
            {"verdict": "contradicted", "expected_span": {"chunk_id": "c2"}},
            {"verdict": "supported"},
        ]
    }
    composition = compute_sample_composition(sample)
    assert composition.retained_count == 5
    assert set(composition.verdict_counts) <= CLAIM_VERDICTS
    assert sum(composition.verdict_counts.values()) == composition.retained_count
    assert composition.verdict_counts["supported"] == 3
    assert composition.verdict_counts["unsupported"] == 1
    assert composition.verdict_counts["contradicted"] == 1
    assert composition.distinct_expected_chunk_ids == 2


def test_compute_sample_composition_empty_claims() -> None:
    empty = compute_sample_composition({"claims": []})
    assert empty.retained_count == 0
    missing = compute_sample_composition({})
    assert missing.retained_count == 0


def test_evaluate_thresholds_degenerate_composition_does_not_raise() -> None:
    result = evaluate_thresholds(
        "exec_summary",
        {"verdict_agreement": 1.0},
        sample_composition=SampleComposition(
            retained_count=0, verdict_counts={}, distinct_expected_chunk_ids=0
        ),
    )
    assert not result.passed
    _assert_channels_disjoint(result)
