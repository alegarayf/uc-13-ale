"""Structural contract for M-PHV2 exit-gate checklist — T8."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CHECKLIST = (
    _REPO_ROOT
    / ".dev"
    / "plans"
    / "uc13-m-phv2-validation-expansion"
    / "exit-gate-checklist.md"
)

pytestmark = pytest.mark.skipif(
    not _CHECKLIST.exists(),
    reason=f"gitignored exit-gate checklist not present in this checkout: {_CHECKLIST}",
)


def _checklist_text() -> str:
    return _CHECKLIST.read_text(encoding="utf-8")


def test_exit_gate_checklist_template_framing() -> None:
    text = _checklist_text()
    assert "Template — awaiting operator cluster evidence" in text
    assert "pending operator evidence" in text


def test_four_charter_exit_gates_present_with_pending_status() -> None:
    text = _checklist_text()
    assert "### Gate 1 — Scorecard index committed" in text
    assert "### Gate 2 — FTA ≥16/18 and Legal ≥7/11 no-regression" in text
    assert "### Gate 3 — Second-company FTA run logged" in text
    assert "### Gate 4 — Full notebook E2E log" in text
    gate_blocks = re.split(r"(?=### Gate [1-4])", text)
    gate_blocks = [b for b in gate_blocks if b.startswith("### Gate")]
    assert len(gate_blocks) == 4
    for block in gate_blocks:
        assert "**`pending operator evidence`**" in block


def test_upstream_authority_pointers() -> None:
    text = _checklist_text()
    assert ".dev/scorecards/INDEX.md" in text
    assert "## PHV validation" in text
    assert "### Second company selection & run" in text
    assert "### record_e2e_linkage invocations" in text
    assert "TEMPLATE_m-phv2-full-e2e-run.md" in text
    assert "## R-02 manual A/B" in text


def test_changelog_entry_template_present_not_live_edit() -> None:
    text = _checklist_text()
    assert "## uc13-m-phv2-validation-expansion — <YYYY-MM-DD>" in text
    assert "Item 17 — FTA `record_e2e_linkage`" in text
    assert "Do not edit `CHANGELOG.MD` until real cluster evidence exists" in text


def test_no_false_pass_gate_closure_claims() -> None:
    """Falsifier: checklist must not assert gates passed without operator evidence."""
    text = _checklist_text()
    assert not re.search(
        r"\*\*Gate status\*\* \| \*\*`PASS`\*\*",
        text,
    ), "Gate status must not be PASS in the template"
    assert "Do not treat this file as" in text and "M-PHV2 done" in text
