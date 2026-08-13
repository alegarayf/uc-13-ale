"""Static contract tests for M3 D2 presentation summary (T6 / E2 migration)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_LCA = _REPO_ROOT / "eval" / "LCA"
_SUMMARY = _LCA / "presentation_summary_elder_care.md"
_NORMATIVE = _LCA / "baselines" / "_latest_Elder_Care_legal_report.yaml"
_POC_DELTA = _LCA / "poc_delta_elder_care.md"

_NORMATIVE_MISSING = not _NORMATIVE.is_file()
_skip_normative = pytest.mark.skipif(
    _NORMATIVE_MISSING,
    reason=f"tracked normative baseline fixture not present: {_NORMATIVE}",
)


def test_presentation_summary_tracked_paths_exist():
    """Falsifier: D2 contract artifacts must live under eval/LCA/, not .dev/legal_agent/."""
    for path in (_SUMMARY, _POC_DELTA):
        assert path.is_file(), f"tracked presentation fixture missing: {path}"
        assert "eval" in path.parts and "LCA" in path.parts
        assert ".dev" not in path.parts


def _summary_text() -> str:
    return _SUMMARY.read_text(encoding="utf-8")


def _normative_doc() -> dict:
    return yaml.safe_load(_NORMATIVE.read_text(encoding="utf-8"))


def test_presentation_summary_exists_with_d2_field_headings():
    text = _summary_text()
    for heading in (
        "Assessed items",
        "Section confidence",
        "Option-C flags",
        "Top gaps",
        "Corpus context",
    ):
        assert heading in text


@_skip_normative
def test_assessed_count_matches_normative_executive_summary():
    """Falsifier: D2 numerator must match T4 agent output, not a stale manual count."""
    text = _summary_text()
    doc = _normative_doc()
    summary = doc["executive_summary"]
    match = re.search(r"(\d+) of (\d+) checklist items", summary)
    assert match is not None
    assessed, total = int(match.group(1)), int(match.group(2))
    assert total == 11
    assert f"**{assessed} of {total}**" in text


@_skip_normative
def test_section_confidence_and_flag_count_match_normative_yaml():
    text = _summary_text()
    doc = _normative_doc()
    assert doc["confidence"] == "high"
    assert f"**{doc['confidence']}**" in text
    flag_count = len(doc["Flags"])
    assert flag_count == 8
    assert f"**{flag_count}**" in text


def test_run_metadata_matches_poc_delta_record():
    text = _summary_text()
    poc = _POC_DELTA.read_text(encoding="utf-8")
    sha_match = re.search(r"`([0-9a-f]{40})`", poc)
    assert sha_match is not None
    assert sha_match.group(1) in text
    assert "uc13_ale" in text
    assert "Elder Care" in text
    assert "2026-06-29" in text


def test_top_gaps_link_to_poc_delta_and_list_four_item_ids():
    text = _summary_text()
    assert "poc_delta_elder_care.md" in text
    for item_id in ("t4c", "coc", "platform", "ip"):
        assert item_id in text
