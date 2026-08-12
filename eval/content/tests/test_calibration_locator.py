"""Hermetic tests for judge-side locator comparison and fail-closed parsing (T9 / F-3, F-7, F-8)."""

from __future__ import annotations

import inspect

import pytest

from eval.content.agreement import spans_agree, verdicts_agree
from eval.content.calibration import (
    apply_three_branch_locator,
    judge_claim,
    parse_numeric_judge_response,
    parse_verdict_response,
)

# Audit rev 1 §8 adversarial rows A1/A2 — chunk c1 metadata from F-3 demonstration.
_CHUNK_C1_META = {
    "chunk_id": "c1",
    "section_header": "Historical P&L Summary",
    "page_start": 50,
}
_OPERATOR_LABELLED_SPAN = {
    "chunk_id": "c1",
    "locator": {"kind": "section", "value": "Historical P&L Summary"},
}


def test_audit_a1_wrong_page_locator_disagrees() -> None:
    """Judge wrong page/999 against operator section label must disagree (F-3 / A1)."""
    judge_span = {
        "chunk_id": "c1",
        "locator": {"kind": "page", "value": "999"},
    }
    assert not spans_agree(_OPERATOR_LABELLED_SPAN, judge_span)


def test_audit_a2_judge_null_locator_disagrees() -> None:
    """Judge omits locator against operator-labelled locator must disagree (F-3 / A2)."""
    judge_span = {"chunk_id": "c1", "locator": None}
    assert not spans_agree(_OPERATOR_LABELLED_SPAN, judge_span)


def test_out_of_vocabulary_locator_kind_disagrees() -> None:
    """Judge locator kind outside page/section is a disagreement (A-C4)."""
    judge_span = {
        "chunk_id": "c1",
        "locator": {"kind": "cell", "value": "B12"},
    }
    assert not spans_agree(_OPERATOR_LABELLED_SPAN, judge_span)


def test_apply_three_branch_locator_is_operator_authoring_only() -> None:
    """HALT-33/34 helper must not be invoked on the judge path (F-3)."""
    source = inspect.getsource(judge_claim)
    assert "apply_three_branch_locator" not in source

    doc = apply_three_branch_locator.__doc__ or ""
    assert "no judge-side role" in doc.lower()


@pytest.mark.parametrize(
    ("raw", "expect_parse_failure"),
    [
        ('{"verdict": "maybe"}', True),
        ("not json at all", True),
        ('{"verdict": "supported"}', False),
    ],
)
def test_malformed_or_oov_verdict_not_coerced(
    raw: str, expect_parse_failure: bool
) -> None:
    """Out-of-vocabulary or malformed verdicts are parse failures, never coerced (F-7 / A-EE)."""
    parsed = parse_verdict_response(raw)
    assert parsed["parse_failure"] is expect_parse_failure
    if expect_parse_failure:
        assert parsed["verdict"] is None
        assert not verdicts_agree("supported", parsed["verdict"])
    else:
        assert parsed["verdict"] in {"supported", "contradicted", "unsupported"}


def test_unparseable_numeric_extraction_is_parse_failure() -> None:
    """Float magnitude in judge extraction is a parse failure, not a vocabulary coercion."""
    raw = '{"extracted_value": {"magnitude": 19.4, "unit": "percent"}, "cited_span": null}'
    parsed = parse_numeric_judge_response(raw)
    assert parsed["parse_failure"] is True


def test_repo_root_env_resolution() -> None:
    """load_dotenv must target repo root, not cwd (F-17 / A-C8)."""
    from eval.content import calibration

    root = calibration._repo_root()
    assert (root / "eval" / "content" / "calibration.py").is_file()
    source = inspect.getsource(calibration.run_calibration)
    assert "Path.cwd()" not in source
    assert "_repo_root()" in source
