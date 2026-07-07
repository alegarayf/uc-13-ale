"""Structural contract for M-PHV2 second-company README subsection — T5."""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_README = _REPO_ROOT / "eval" / "retrieval" / "README.md"
_TEMPLATE = (
    _REPO_ROOT / ".dev" / "scorecards" / "templates" / "second_company_header_template.md"
)
_HEADING = "### Second company selection & run"
_PHV_HEADING = "## PHV validation"
_R02_HEADING = "## R-02 manual A/B"
_SPEC_SELECTION_VERBATIM = (
    "Operator chooses from available SharePoint companies with non-trivial data room"
)
_CHARTER_CONSTRAINT = "must differ from Elder Care"

pytestmark_template = pytest.mark.skipif(
    not _TEMPLATE.exists(),
    reason=f"gitignored scorecard template not present in this checkout: {_TEMPLATE}",
)


def _phv_section() -> str:
    text = _README.read_text(encoding="utf-8")
    phv_start = text.index(_PHV_HEADING)
    r02_start = text.index(_R02_HEADING)
    return text[phv_start:r02_start]


def test_readme_contains_second_company_subsection_heading_verbatim() -> None:
    assert _HEADING in _README.read_text(encoding="utf-8")


def test_second_company_subsection_is_markdown_level3_under_phv_validation() -> None:
    """Falsifier: heading present only inside a code block would satisfy substring check."""
    section = _phv_section()
    assert _HEADING in section
    for line in section.splitlines():
        if line.strip() == _HEADING:
            return
    raise AssertionError(f"No bare markdown level-3 line {_HEADING!r} in PHV validation block")


def test_second_company_subsection_precedes_r02_manual_ab() -> None:
    text = _README.read_text(encoding="utf-8")
    second_idx = text.index(_HEADING)
    r02_idx = text.index(_R02_HEADING)
    assert second_idx < r02_idx, "T5 subsection must live under PHV validation before R-02 manual A/B"


def test_second_company_documents_frozen_selection_criteria() -> None:
    section = _phv_section()
    assert _SPEC_SELECTION_VERBATIM in section
    assert _CHARTER_CONSTRAINT in section


def test_second_company_documents_clearsulting_non_substitution_note() -> None:
    section = _phv_section()
    assert "m-phv1-clearsulting-2026-07-07.md" in section
    assert "not** a substitute for M-PHV2" in section
    assert "incomplete agent matrix" in section


def test_second_company_does_not_preselect_operator_company() -> None:
    """Falsifier: runbook names a specific second company instead of placeholder fields."""
    section = _phv_section()
    assert "**Selected company**" in section
    assert "**_(operator:" in section
    forbidden = (
        "**Selected company** | Clearsulting",
        "**Selected company:** Clearsulting",
        "Second company: Clearsulting",
        "second company is Clearsulting",
    )
    for phrase in forbidden:
        assert phrase not in section, f"runbook must not pre-select company: {phrase!r}"


def test_second_company_documents_parser_fta_minimum_and_header_template() -> None:
    section = _phv_section()
    assert "parser + FTA" in section
    assert "second_company_header_template.md" in section
    assert "company name" in section.lower()
    assert "catalog" in section.lower()


@pytestmark_template
def test_second_company_header_template_exists_on_disk() -> None:
    assert _TEMPLATE.is_file()


@pytestmark_template
def test_second_company_header_template_records_company_and_catalog() -> None:
    text = _TEMPLATE.read_text(encoding="utf-8")
    assert _SPEC_SELECTION_VERBATIM in text
    assert _CHARTER_CONSTRAINT in text
    assert "**Selected company**" in text
    assert "**Catalog**" in text
