"""Static contract tests for M3 D2 presentation summary (T6)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SUMMARY = _REPO_ROOT / ".dev" / "legal_agent" / "eval" / "presentation_summary_elder_care.md"
_NORMATIVE = (
    _REPO_ROOT / ".dev" / "legal_agent" / "baselines" / "_latest_Elder_Care_legal_report.yaml"
)
_POC_DELTA = _REPO_ROOT / ".dev" / "legal_agent" / "eval" / "poc_delta_elder_care.md"

# .dev/ is gitignored repo-wide (Option C pin protocol) — these operator-produced
# evidence artifacts are local, not tracked in git, and may legitimately be absent
# on a fresh checkout or a different machine. Skip rather than fail when any is
# missing so this module's contract still holds wherever the evidence exists.
_MISSING = [p for p in (_SUMMARY, _NORMATIVE, _POC_DELTA) if not p.exists()]
pytestmark = pytest.mark.skipif(
    bool(_MISSING),
    reason="gitignored evidence fixture(s) not present in this checkout: "
    + ", ".join(str(p) for p in _MISSING),
)


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
