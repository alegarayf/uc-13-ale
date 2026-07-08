"""Structural contract for M-PHV2 exit-gate checklist — T8/T10 closure."""

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
_ELDER_CARE_E2E = (
    _REPO_ROOT
    / ".dev"
    / "attestations"
    / "m-phv2-full-e2e-run-elder-care-2026-07-08.md"
)
_CLEARSULTING_E2E = (
    _REPO_ROOT
    / ".dev"
    / "attestations"
    / "m-phv2-full-e2e-run-clearsulting-2026-07-07.md"
)

pytestmark = pytest.mark.skipif(
    not _CHECKLIST.exists(),
    reason=f"gitignored exit-gate checklist not present in this checkout: {_CHECKLIST}",
)


def _checklist_text() -> str:
    return _CHECKLIST.read_text(encoding="utf-8")


def _gate_blocks(text: str) -> list[str]:
    blocks = re.split(r"(?=### Gate [1-4])", text)
    return [b for b in blocks if b.startswith("### Gate")]


def test_exit_gate_checklist_closure_framing() -> None:
    text = _checklist_text()
    assert "Closure assembly" in text or "Gates 1–4 **PASS**" in text
    assert "Template — awaiting operator cluster evidence" not in text


def test_four_charter_exit_gates_present_with_pass_status() -> None:
    text = _checklist_text()
    assert "### Gate 1 — Scorecard index committed" in text
    assert "### Gate 2 — FTA ≥16/18 and Legal ≥7/11 no-regression" in text
    assert "### Gate 3 — Second-company FTA run logged" in text
    assert "### Gate 4 — Full notebook E2E log" in text
    gate_blocks = _gate_blocks(text)
    assert len(gate_blocks) == 4
    for block in gate_blocks:
        assert "**`PASS`**" in block, f"Gate block missing PASS status: {block[:80]}"


def test_upstream_authority_pointers() -> None:
    text = _checklist_text()
    assert ".dev/scorecards/INDEX.md" in text
    assert "## PHV validation" in text
    assert "### Second company selection & run" in text
    assert "### record_e2e_linkage invocations" in text
    assert "TEMPLATE_m-phv2-full-e2e-run.md" in text
    assert "## R-02 manual A/B" in text


def test_gate_four_cites_e2e_attestation_paths() -> None:
    """Falsifier: Gate 4 PASS must cite filled attestation files, not template only."""
    text = _checklist_text()
    gate_four = _gate_blocks(text)[3]
    assert "m-phv2-full-e2e-run-elder-care-2026-07-08.md" in gate_four
    assert "m-phv2-full-e2e-run-clearsulting-2026-07-07.md" in gate_four
    if _ELDER_CARE_E2E.exists():
        assert _ELDER_CARE_E2E.is_file()
    if _CLEARSULTING_E2E.exists():
        assert _CLEARSULTING_E2E.is_file()


def test_item_sixteen_deferred_item_seventeen_pass() -> None:
    text = _checklist_text()
    assert "Deferred to M-PHV4" in text
    assert re.search(r"17.*PASS", text, re.DOTALL), "item 17 should be PASS"


def test_pass_gates_cite_concrete_artifacts() -> None:
    """Falsifier: no gate PASS row without artifact path or run_id in same block."""
    text = _checklist_text()
    for block in _gate_blocks(text):
        assert "**`PASS`**" in block
        has_pointer = bool(
            re.search(
                r"(\.dev/|run_id|`[0-9a-f]{8,})",
                block,
                re.IGNORECASE,
            )
        )
        assert has_pointer, f"PASS gate lacks artifact pointer: {block[:120]}"
