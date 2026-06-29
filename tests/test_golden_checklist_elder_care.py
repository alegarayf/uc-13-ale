"""Structural contract tests for golden checklist eval artifact (T5 / G3)."""

from __future__ import annotations

import re
from pathlib import Path

from agents.workstreams.legal_contracts_agent import STAKEHOLDER_COVERAGE_REQUIREMENTS

_ROOT = Path(__file__).resolve().parents[1]
_CHECKLIST_PATH = _ROOT / ".dev" / "legal_agent" / "eval" / "golden_checklist_elder_care.md"

VERDICT_ENUM = frozenset({"pass", "partial", "gap-correct", "n/a"})
_EXPECTED_ITEM_IDS = tuple(req["item_id"] for req in STAKEHOLDER_COVERAGE_REQUIREMENTS)
_DISPLAY_BY_ID = {req["item_id"]: req["display_name"] for req in STAKEHOLDER_COVERAGE_REQUIREMENTS}


def _parse_checklist_rows(text: str) -> list[dict[str, str]]:
    """Extract data rows from the checklist markdown table (after ## Checklist header)."""
    section = text.split("## Checklist (11 rows)", 1)[-1]
    lines = [ln.strip() for ln in section.splitlines() if ln.strip().startswith("|")]
    # header, separator, then data rows
    data_lines = [ln for ln in lines[2:] if not re.match(r"^\|\s*-+\s*\|", ln)]
    rows: list[dict[str, str]] = []
    for ln in data_lines:
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if len(cells) < 3:
            continue
        rows.append({
            "item_id": cells[0],
            "display_name": cells[1],
            "verdict": cells[2],
            "notes": cells[3] if len(cells) > 3 else "",
        })
    return rows


def test_golden_checklist_has_eleven_rows():
    text = _CHECKLIST_PATH.read_text(encoding="utf-8")
    rows = _parse_checklist_rows(text)
    assert len(rows) == 11


def test_golden_checklist_item_ids_match_stakeholder_requirements():
    text = _CHECKLIST_PATH.read_text(encoding="utf-8")
    rows = _parse_checklist_rows(text)
    assert tuple(r["item_id"] for r in rows) == _EXPECTED_ITEM_IDS


def test_golden_checklist_display_names_match_constant():
    text = _CHECKLIST_PATH.read_text(encoding="utf-8")
    rows = _parse_checklist_rows(text)
    for row in rows:
        assert row["display_name"] == _DISPLAY_BY_ID[row["item_id"]]


def test_golden_checklist_verdicts_in_enum():
    text = _CHECKLIST_PATH.read_text(encoding="utf-8")
    rows = _parse_checklist_rows(text)
    for row in rows:
        assert row["verdict"] in VERDICT_ENUM, (
            f"invalid verdict for {row['item_id']}: {row['verdict']!r}"
        )


def test_golden_checklist_summary_counts_match_row_verdicts():
    """Falsifier: summary line must not drift from per-row verdict tallies."""
    text = _CHECKLIST_PATH.read_text(encoding="utf-8")
    rows = _parse_checklist_rows(text)
    tallies = {v: sum(1 for r in rows if r["verdict"] == v) for v in VERDICT_ENUM}
    summary = text.split("**Summary:**", 1)[-1]
    for verdict, count in tallies.items():
        assert f"{count} `{verdict}`" in summary, (
            f"summary missing tally for {verdict}={count}"
        )
