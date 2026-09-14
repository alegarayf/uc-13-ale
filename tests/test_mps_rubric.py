"""Contract tests for the MPS rubric YAML and its loader/validator.

`docs/checklist/checklist_template.md` (source of the verbatim §A.2 category
definitions) is gitignored and untracked — see docs/plans/mps_score/tasks/
00_common.md. These tests therefore only assert what is checkable from the
tracked `mps_rubric.yaml` itself; the checklist-vs-YAML verbatim diff stays a
manual PR-checklist step (docs/plans/mps_score/mps_score_1st_draft.md §11,
test 6).
"""

from __future__ import annotations

import copy

import pytest
import yaml

from agents.exec_summary.mps_rubric import RubricError, _RUBRIC_PATH, load_rubric

_EXPECTED_KEYS_IN_ORDER = [
    "magical_business_model",
    "growth_mindset",
    "growth_characteristics",
    "manageable_systemic_risk",
    "untapped_growth_opportunities",
    "transformational_equity",
    "financeable",
]

_ALLOWED_EVIDENCE_BASIS = {"document_derived", "judgment_over_context", "contact_dependent"}


@pytest.fixture()
def rubric() -> dict:
    return load_rubric()


def _raw_rubric() -> dict:
    with open(_RUBRIC_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# --- test 5: exactly 7 categories, keys and order stable -------------------


def test_exactly_seven_categories(rubric):
    assert len(rubric["categories"]) == 7


def test_category_keys_and_order_are_stable(rubric):
    keys = [c["key"] for c in rubric["categories"]]
    assert keys == _EXPECTED_KEYS_IN_ORDER


# --- test 6: definitions are verbatim, checked only via tracked files ------


def test_all_seven_definitions_present_and_non_empty(rubric):
    for category in rubric["categories"]:
        assert isinstance(category["definition"], str)
        assert category["definition"].strip()


def test_definitions_are_long_enough_to_rule_out_paraphrase(rubric):
    # The real §A.2 definitions are long. This does not prove verbatim
    # copying, but it catches a lazy one-line paraphrase.
    for category in rubric["categories"]:
        definition = " ".join(category["definition"].split())
        assert len(definition) >= 150, (
            f"{category['key']}: definition is {len(definition)} chars, "
            "shorter than the real §A.2 text — check for paraphrasing"
        )


def test_definitions_are_written_as_questions(rubric):
    # Every §A.2 definition is written as one or more questions. Two of the
    # seven (manageable_systemic_risk, untapped_growth_opportunities) contain
    # exactly one question mark and do not end in "?" in the real checklist
    # text — so this only requires at least one question mark, not "ends in
    # ? or has >= 2", which the real text does not uniformly satisfy.
    for category in rubric["categories"]:
        definition = category["definition"]
        assert definition.count("?") >= 1, (
            f"{category['key']}: definition has no question mark, "
            "but every §A.2 definition is phrased as a question"
        )


# --- test 7: anchors, evidence_basis, sub_axes exclusivity ------------------


def test_anchors_present_for_1_3_5(rubric):
    for category in rubric["categories"]:
        anchors = category["anchors"]
        for anchor_key in ("1", "3", "5"):
            assert anchor_key in anchors
            assert isinstance(anchors[anchor_key], str)
            assert anchors[anchor_key].strip()


def test_evidence_basis_in_allowed_set(rubric):
    for category in rubric["categories"]:
        assert category["evidence_basis"] in _ALLOWED_EVIDENCE_BASIS


def test_manageable_systemic_risk_is_the_only_category_with_sub_axes(rubric):
    for category in rubric["categories"]:
        sub_axes = category["required_commentary"]["sub_axes"]
        if category["key"] == "manageable_systemic_risk":
            assert len(sub_axes) > 0
        else:
            assert sub_axes == []


# --- loader/validator behavior ----------------------------------------------


def test_load_rubric_reads_threshold_and_scale_from_file(rubric):
    assert rubric["threshold"] == 15
    assert rubric["scale"] == {"min": 1, "max": 5}
    assert rubric["rubric_version"] == "0.1.0-poc"


def test_load_rubric_missing_file_raises_rubric_error(tmp_path):
    with pytest.raises(RubricError):
        load_rubric(tmp_path / "does_not_exist.yaml")


def test_load_rubric_invalid_yaml_raises_rubric_error(tmp_path):
    bad_file = tmp_path / "bad.yaml"
    bad_file.write_text("categories: [this is not: valid: yaml", encoding="utf-8")
    with pytest.raises(RubricError):
        load_rubric(bad_file)


@pytest.mark.parametrize(
    "mutation",
    [
        "drop_category",
        "bad_evidence_basis",
        "missing_anchor",
        "missing_threshold",
        "duplicate_key",
    ],
)
def test_load_rubric_rejects_malformed_structures(tmp_path, mutation):
    raw = copy.deepcopy(_raw_rubric())

    if mutation == "drop_category":
        raw["categories"].pop()
    elif mutation == "bad_evidence_basis":
        raw["categories"][0]["evidence_basis"] = "made_up_value"
    elif mutation == "missing_anchor":
        del raw["categories"][0]["anchors"]["3"]
    elif mutation == "missing_threshold":
        del raw["threshold"]
    elif mutation == "duplicate_key":
        raw["categories"][1]["key"] = raw["categories"][0]["key"]

    bad_file = tmp_path / "mutated.yaml"
    bad_file.write_text(yaml.safe_dump(raw), encoding="utf-8")

    with pytest.raises(RubricError):
        load_rubric(bad_file)
