"""Hermetic tests for §8.7 agreement predicates (C4)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from eval.content.agreement import (
    compute_metrics,
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
    passed, reasons = evaluate_thresholds("fta_numeric", figures)
    assert not passed
    assert any("value resolved population empty" in r for r in reasons)
    assert any("span resolved population empty" in r for r in reasons)


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
