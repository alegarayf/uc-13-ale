"""Structural contract tests for golden checklist eval artifacts (M1 HUB / G3)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from agents.workstreams.business_model_agent import (
    GOLDEN_CHECKLIST_COVERAGE as BMA_GOLDEN_CHECKLIST_COVERAGE,
)
from agents.workstreams.customer_quality_agent import (
    GOLDEN_CHECKLIST_COVERAGE as CQA_GOLDEN_CHECKLIST_COVERAGE,
)
from agents.workstreams.kpi_agent import GOLDEN_CHECKLIST_COVERAGE as KPI_GOLDEN_CHECKLIST_COVERAGE
from agents.workstreams.legal_contracts_agent import STAKEHOLDER_COVERAGE_REQUIREMENTS
from agents.workstreams.quality_of_earnings_agent import (
    GOLDEN_CHECKLIST_COVERAGE as QOE_GOLDEN_CHECKLIST_COVERAGE,
)
from jobs.scripts.company_profiler import (
    GOLDEN_CHECKLIST_COVERAGE as PROFILER_GOLDEN_CHECKLIST_COVERAGE,
)

_ROOT = Path(__file__).resolve().parents[1]

CHECKLIST_CASES: list[tuple[str, Path, list[dict]]] = [
    ("bma", _ROOT / "eval" / "BMA" / "golden_checklist_elder_care.md", BMA_GOLDEN_CHECKLIST_COVERAGE),
    ("cqa", _ROOT / "eval" / "CQA" / "golden_checklist_elder_care.md", CQA_GOLDEN_CHECKLIST_COVERAGE),
    ("kpi", _ROOT / "eval" / "KPI" / "golden_checklist_elder_care.md", KPI_GOLDEN_CHECKLIST_COVERAGE),
    (
        "profiler",
        _ROOT / "eval" / "PROFILER" / "golden_checklist_elder_care.md",
        PROFILER_GOLDEN_CHECKLIST_COVERAGE,
    ),
    ("legal", _ROOT / "eval" / "LCA" / "golden_checklist_elder_care.md", STAKEHOLDER_COVERAGE_REQUIREMENTS),
    ("qoe", _ROOT / "eval" / "QOE" / "golden_checklist_elder_care.md", QOE_GOLDEN_CHECKLIST_COVERAGE),
]

VERDICT_ENUM = frozenset({"pass", "partial", "gap-correct", "n/a"})

_CASE_IDS = [case[0] for case in CHECKLIST_CASES]


def _parse_checklist_rows(text: str, row_count: int) -> list[dict[str, str]]:
    """Extract data rows from the checklist markdown table (after ## Checklist header)."""
    section = text.split(f"## Checklist ({row_count} rows)", 1)[-1]
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


def test_checklist_cases_includes_qoe_after_m2_t2():
    """Falsifier: M2-T2 appends one CHECKLIST_CASES row — QoE is now registered."""
    assert any(agent_id == "qoe" for agent_id, _, _ in CHECKLIST_CASES)


@pytest.mark.parametrize("agent_id,checklist_path,coverage_constant", CHECKLIST_CASES, ids=_CASE_IDS)
def test_golden_checklist_tracked_path_exists(
    agent_id: str, checklist_path: Path, coverage_constant: list[dict]
):
    assert checklist_path.is_file(), (
        f"{agent_id}: tracked checklist missing (Decision D — fail hard): {checklist_path}"
    )


@pytest.mark.parametrize("agent_id,checklist_path,coverage_constant", CHECKLIST_CASES, ids=_CASE_IDS)
def test_golden_checklist_row_count_matches_coverage_constant(
    agent_id: str, checklist_path: Path, coverage_constant: list[dict]
):
    text = checklist_path.read_text(encoding="utf-8")
    rows = _parse_checklist_rows(text, len(coverage_constant))
    assert len(rows) == len(coverage_constant)


@pytest.mark.parametrize("agent_id,checklist_path,coverage_constant", CHECKLIST_CASES, ids=_CASE_IDS)
def test_golden_checklist_item_ids_match_coverage_constant(
    agent_id: str, checklist_path: Path, coverage_constant: list[dict]
):
    text = checklist_path.read_text(encoding="utf-8")
    rows = _parse_checklist_rows(text, len(coverage_constant))
    expected_item_ids = tuple(req["item_id"] for req in coverage_constant)
    assert tuple(r["item_id"] for r in rows) == expected_item_ids


@pytest.mark.parametrize("agent_id,checklist_path,coverage_constant", CHECKLIST_CASES, ids=_CASE_IDS)
def test_golden_checklist_display_names_match_constant(
    agent_id: str, checklist_path: Path, coverage_constant: list[dict]
):
    text = checklist_path.read_text(encoding="utf-8")
    rows = _parse_checklist_rows(text, len(coverage_constant))
    display_by_id = {req["item_id"]: req["display_name"] for req in coverage_constant}
    for row in rows:
        item_id = row["item_id"]
        assert row["display_name"] == display_by_id[item_id]


@pytest.mark.parametrize("agent_id,checklist_path,coverage_constant", CHECKLIST_CASES, ids=_CASE_IDS)
def test_golden_checklist_verdicts_in_enum(
    agent_id: str, checklist_path: Path, coverage_constant: list[dict]
):
    text = checklist_path.read_text(encoding="utf-8")
    rows = _parse_checklist_rows(text, len(coverage_constant))
    for row in rows:
        assert row["verdict"] in VERDICT_ENUM, (
            f"invalid verdict for {row['item_id']}: {row['verdict']!r}"
        )


@pytest.mark.parametrize("agent_id,checklist_path,coverage_constant", CHECKLIST_CASES, ids=_CASE_IDS)
def test_golden_checklist_summary_counts_match_row_verdicts(
    agent_id: str, checklist_path: Path, coverage_constant: list[dict]
):
    """Falsifier: summary line must not drift from per-row verdict tallies."""
    text = checklist_path.read_text(encoding="utf-8")
    rows = _parse_checklist_rows(text, len(coverage_constant))
    tallies = {v: sum(1 for r in rows if r["verdict"] == v) for v in VERDICT_ENUM}
    summary = text.split("**Summary:**", 1)[-1]
    for verdict, count in tallies.items():
        assert f"{count} `{verdict}`" in summary, (
            f"summary missing tally for {verdict}={count}"
        )
