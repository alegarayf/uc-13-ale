"""Pure-arithmetic calibration tests for MPS scoring — no LLM, no Spark.

These are the highest-value tests in the whole feature (docs/plans/mps_score/
mps_score_1st_draft.md §11): the multiplicative product/1000 formula makes a
single hedged "3" fail an otherwise-strong deal, and makes a single "1" fail
to veto a deal surrounded by 5s. Both are load-bearing, surprising properties
of the spec, not implementation bugs — the tests document them rather than
hide them.
"""

from __future__ import annotations

import pytest

from agents.exec_summary.mps_rubric import load_rubric, mps_total, mps_verdict

_THRESHOLD = load_rubric()["threshold"]


# --- test 1: Elder Care golden columns (F-1) --------------------------------

_ELDER_CARE_COLUMNS = {
    "3/4 First Look": ([4, 5, 5, 4, 5, 3, 4], 24.0),
    "3/18 Initial LOI": ([4, 5, 5, 3, 5, 4, 4], 24.0),
    "5/20 Second LOI": ([4, 5, 5, 4, 5, 4, 4], 32.0),
    "7/25 Deal Close": ([4, 5, 5, 4, 5, 4, 4], 32.0),
}


@pytest.mark.parametrize("stage", list(_ELDER_CARE_COLUMNS))
def test_elder_care_golden_columns(stage):
    scores, expected_total = _ELDER_CARE_COLUMNS[stage]
    assert mps_total(scores) == expected_total


def test_elder_care_columns_all_pass_threshold():
    for scores, _ in _ELDER_CARE_COLUMNS.values():
        total = mps_total(scores)
        assert mps_verdict(total, _THRESHOLD) == "above threshold"


# --- test 2: F-2 sensitivity table ------------------------------------------

_SENSITIVITY_TABLE = [
    ("all 5s", [5] * 7, 78.125, "above threshold"),
    ("six 5s + one 4", [5, 5, 5, 5, 5, 5, 4], 62.5, "above threshold"),
    ("Elder Care 5/20 and 7/25", [4, 5, 5, 4, 5, 4, 4], 32.0, "above threshold"),
    ("Elder Care 3/4 and 3/18", [4, 5, 5, 4, 5, 3, 4], 24.0, "above threshold"),
    ("all 4s", [4] * 7, 16.384, "above threshold"),
    ("six 4s + one 3", [4, 4, 4, 4, 4, 4, 3], 12.288, "below threshold — requires explicit override rationale to advance"),
    ("five 4s + two 3s", [4, 4, 4, 4, 4, 3, 3], 9.216, "below threshold — requires explicit override rationale to advance"),
    ("six 4s + one 2", [4, 4, 4, 4, 4, 4, 2], 8.192, "below threshold — requires explicit override rationale to advance"),
    ("all 3s", [3] * 7, 2.187, "below threshold — requires explicit override rationale to advance"),
    (
        "six 5s + one 1 — a fatal category does not veto",
        [5, 5, 5, 5, 5, 5, 1],
        15.625,
        "above threshold",
    ),
]


@pytest.mark.parametrize(
    "label,scores,expected_total,expected_verdict",
    _SENSITIVITY_TABLE,
    ids=[row[0] for row in _SENSITIVITY_TABLE],
)
def test_f2_sensitivity_table(label, scores, expected_total, expected_verdict):
    total = mps_total(scores)
    assert total == pytest.approx(expected_total)
    assert mps_verdict(total, _THRESHOLD) == expected_verdict


def test_six_5s_plus_one_1_documents_the_no_veto_surprise():
    # Named explicitly per §11 test 2: a single "1" among six "5"s still
    # clears the threshold (15.625 >= 15). This is the spec's arithmetic as
    # written (F-2), not a bug to be silently patched with a hard floor.
    total = mps_total([5, 5, 5, 5, 5, 5, 1])
    assert total == pytest.approx(15.625)
    assert total >= _THRESHOLD
    assert mps_verdict(total, _THRESHOLD) == "above threshold"


# --- test 3: None in any position -> total is None, no substituted default -


@pytest.mark.parametrize("none_index", range(7))
def test_none_in_any_position_makes_total_none(none_index):
    scores = [4, 4, 4, 4, 4, 4, 4]
    scores[none_index] = None
    assert mps_total(scores) is None


def test_all_none_is_none():
    assert mps_total([None] * 7) is None


def test_mps_verdict_is_none_when_total_is_none():
    assert mps_verdict(None, _THRESHOLD) is None


def test_wrong_category_count_is_none():
    assert mps_total([4, 4, 4, 4, 4, 4]) is None
    assert mps_total([4, 4, 4, 4, 4, 4, 4, 4]) is None


# --- test 4: threshold and category order come from the rubric file --------


def test_threshold_is_read_from_rubric_not_hardcoded():
    rubric = load_rubric()
    assert rubric["threshold"] == _THRESHOLD
    # Verdict flips exactly at the loaded threshold, whatever its value is.
    just_below = rubric["threshold"] - 0.001
    just_at = rubric["threshold"]
    assert mps_verdict(just_below, rubric["threshold"]) != "above threshold"
    assert mps_verdict(just_at, rubric["threshold"]) == "above threshold"


def test_category_count_matches_rubric_category_count():
    rubric = load_rubric()
    assert len(rubric["categories"]) == 7
    # mps_total's fixed-length contract must match the rubric's actual count.
    assert mps_total([3] * len(rubric["categories"])) is not None
