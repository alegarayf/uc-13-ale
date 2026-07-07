"""Structural contract for M-PHV2 scorecard index schema — T4."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_INDEX_PATH = _REPO_ROOT / ".dev" / "scorecards" / "INDEX.md"

_FROZEN_HEADER = (
    "| Agent | Run Date | Company | Catalog | Score | Floor | Verdict | "
    "Scorecard File | Notes |"
)
_FROZEN_COLUMNS = (
    "Agent",
    "Run Date",
    "Company",
    "Catalog",
    "Score",
    "Floor",
    "Verdict",
    "Scorecard File",
    "Notes",
)

pytestmark = pytest.mark.skipif(
    not _INDEX_PATH.exists(),
    reason=f"gitignored scorecard index not present in this checkout: {_INDEX_PATH}",
)


def _index_text() -> str:
    return _INDEX_PATH.read_text(encoding="utf-8")


def _parse_index_table(text: str) -> tuple[list[str], list[list[str]]]:
    """Return (header_cells, data_rows) from the first markdown table in INDEX.md."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("|")]
    assert lines, "INDEX.md must contain a markdown table"
    header_cells = [c.strip() for c in lines[0].strip("|").split("|")]
    # separator line at index 1
    data_rows: list[list[str]] = []
    for ln in lines[2:]:
        if re.match(r"^\|\s*-+\s*\|", ln):
            continue
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if len(cells) == len(header_cells):
            data_rows.append(cells)
    return header_cells, data_rows


def test_index_header_matches_frozen_schema() -> None:
    text = _index_text()
    assert _FROZEN_HEADER in text
    header_cells, _ = _parse_index_table(text)
    assert header_cells == list(_FROZEN_COLUMNS)


def test_every_scorecard_file_cell_resolves_on_disk() -> None:
    """Falsifier: INDEX row points at a path that does not exist relative to repo root."""
    _, data_rows = _parse_index_table(_index_text())
    scorecard_col = _FROZEN_COLUMNS.index("Scorecard File")
    assert data_rows, "INDEX.md must have at least one data row"
    for row in data_rows:
        raw = row[scorecard_col].strip("`").strip()
        resolved = (_REPO_ROOT / raw).resolve()
        assert resolved.exists(), f"Scorecard File path missing on disk: {raw}"


def test_index_has_no_duplicate_scorecard_paths() -> None:
    """Falsifier: two rows reference the same file without operator intent to alias."""
    _, data_rows = _parse_index_table(_index_text())
    scorecard_col = _FROZEN_COLUMNS.index("Scorecard File")
    paths = [row[scorecard_col].strip("`").strip() for row in data_rows]
    assert len(paths) == len(set(paths)), f"duplicate Scorecard File entries: {paths}"
