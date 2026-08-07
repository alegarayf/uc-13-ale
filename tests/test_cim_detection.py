"""Unit tests for jobs/scripts/cim_detection.py — anchored to the real CIM
inventory across Elder Care / Clearsulting / GKF / SPG (plan §0.5, §4;
from_agent.md). No SharePoint/network dependency — ``connector`` is a
lightweight stand-in exposing only ``list_files()``.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "databricks" / "jobs" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from cim_detection import detect_cim, is_cim_candidate, select_cim_files  # noqa: E402


@dataclass
class _File:
    name: str
    relative_path: str
    size_bytes: int = 1_000_000


class _FakeConnector:
    def __init__(self, files: list[_File]) -> None:
        self._files = files

    def list_files(self) -> list[_File]:
        return self._files


# ---------------------------------------------------------------------------
# Real per-company file listings (names only matter; sizes reflect real order
# of magnitude so "pick the largest candidate" logic is exercised honestly).
# ---------------------------------------------------------------------------

_ELDER_CARE_FILES = [
    _File("2024 Elder Care - CIM_vF.pdf", "Example Data Room/Elder Care", 4_484_169),
    _File("Company KPI Dashboard SAMPLE.xlsx", "Example Data Room/Elder Care/KPI", 200_000),
]

_CLEARSULTING_FILES = [
    _File(
        "Project Infinity  - Confidential Information Memorandum.pdf",
        "Example Data Room/Clearsulting",
        6_792_719,
    ),
    _File(
        "Project Infinity - Draft Financial Diligence Report - August 29, 2025_redacted.pdf",
        "Example Data Room/Clearsulting/Financials",
        3_000_000,
    ),
]

_GKF_FILES = [
    _File("Project Ajax CIM vF - Rallyday Partners.pdf", "Example Data Room/GKF/CIM", 5_814_306),
    _File("Project Ajax Teaser.pdf", "Example Data Room/GKF/CIM", 900_000),
    _File("Project Ajax IOI Process Letter.pdf", "Example Data Room/GKF/CIM", 300_000),
    _File("Goddard FDD 2025.pdf", "Example Data Room/GKF/Legal", 1_200_000),
]

_SPG_FILES = [
    _File("SPG Financial Statements FY24.xlsx", "Example Data Room/SPG/Financials", 500_000),
    _File("SPG Customer Contracts.pdf", "Example Data Room/SPG/Legal", 800_000),
]

# Real production folder name (not the generic "GKF/CIM" fixture above) —
# observed live: the folder itself is named "Process, Teaser, and CIM", so
# its own name contains the "teaser" exclusion substring. Regression fixture
# for the bug where exclusion patterns matched against relative_path+name
# excluded the real CIM file too (its OWN name has no exclusion term).
_GKF_FILES_REAL_FOLDER_NAME = [
    _File(
        "Project Ajax CIM vF - Rallyday Partners.pdf",
        "Example Data Room/GKF/Process, Teaser, and CIM",
        5_814_306,
    ),
    _File(
        "Project Ajax Teaser vF.pdf",
        "Example Data Room/GKF/Process, Teaser, and CIM",
        900_000,
    ),
    _File(
        "Project Ajax IOI Process Letter_vE.pdf",
        "Example Data Room/GKF/Process, Teaser, and CIM",
        300_000,
    ),
]


def test_clearsulting_detected_by_full_name_phrase_match_no_cim_substring():
    connector = _FakeConnector(_CLEARSULTING_FILES)
    result = detect_cim("Clearsulting", connector)
    assert result == ["Project Infinity  - Confidential Information Memorandum.pdf"]


def test_elder_care_detected_by_direct_cim_name_match():
    connector = _FakeConnector(_ELDER_CARE_FILES)
    result = detect_cim("Elder Care", connector)
    assert result == ["2024 Elder Care - CIM_vF.pdf"]


def test_gkf_excludes_teaser_and_ioi_selects_real_memorandum():
    connector = _FakeConnector(_GKF_FILES)
    result = detect_cim("GKF", connector)
    assert result == ["Project Ajax CIM vF - Rallyday Partners.pdf"]
    assert "Project Ajax Teaser.pdf" not in result
    assert "Project Ajax IOI Process Letter.pdf" not in result


def test_gkf_real_folder_name_containing_teaser_still_finds_the_cim():
    """Regression: a folder literally named "Process, Teaser, and CIM" must
    not exclude the real CIM file just because "teaser" appears in the
    folder name — exclusion must be judged on the file's own name."""
    connector = _FakeConnector(_GKF_FILES_REAL_FOLDER_NAME)
    result = detect_cim("GKF", connector)
    assert result == ["Project Ajax CIM vF - Rallyday Partners.pdf"]


def test_spg_has_no_cim_returns_empty_list():
    connector = _FakeConnector(_SPG_FILES)
    result = detect_cim("SPG", connector)
    assert result == []


def test_spg_falls_back_to_special_folder_when_no_cim():
    connector = _FakeConnector(_SPG_FILES)
    result = detect_cim("SPG", connector, special_folder="Financials")
    assert result == ["SPG Financial Statements FY24.xlsx"]


def test_special_folder_ignored_when_a_real_cim_exists():
    # CIM takes priority over special_folder even if both are set (plan §4).
    connector = _FakeConnector(_ELDER_CARE_FILES)
    result = detect_cim("Elder Care", connector, special_folder="KPI")
    assert result == ["2024 Elder Care - CIM_vF.pdf"]


@pytest.mark.parametrize(
    ("name", "relative_path", "expected"),
    [
        ("2024 Elder Care - CIM_vF.pdf", "Example Data Room/Elder Care", True),
        ("Project Infinity  - Confidential Information Memorandum.pdf", "x", True),
        ("Project Ajax Teaser.pdf", "Example Data Room/GKF/CIM", False),
        ("Project Ajax IOI Process Letter.pdf", "Example Data Room/GKF/CIM", False),
        ("SPG Financial Statements FY24.xlsx", "Example Data Room/SPG/Financials", False),
        ("Mutual NDA.pdf", "Example Data Room/GKF/CIM", False),
        # Folder name itself contains "teaser" — must not exclude the CIM file.
        ("Project Ajax CIM vF - Rallyday Partners.pdf", "Example Data Room/GKF/Process, Teaser, and CIM", True),
        ("Project Ajax Teaser vF.pdf", "Example Data Room/GKF/Process, Teaser, and CIM", False),
    ],
)
def test_is_cim_candidate_matches_and_exclusions(name, relative_path, expected):
    assert is_cim_candidate(_File(name, relative_path)) is expected


def test_select_cim_files_picks_largest_when_multiple_match():
    files = [
        _File("Offering Memorandum draft.pdf", "x", size_bytes=100),
        _File("Offering Memorandum final.pdf", "x", size_bytes=9_000_000),
    ]
    result = select_cim_files(files)
    assert result[0].name == "Offering Memorandum final.pdf"
