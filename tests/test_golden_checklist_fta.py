"""Structural contract tests for the canonical FTA golden checklist (M1 item 18)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
FTA_CHECKLIST_PATH = _ROOT / "eval" / "FTA" / "golden_checklist_elder_care.md"

# Literal pin — must match score_fta() keys in .dev/g1_score_all_agents.py (no gitignored import).
FTA_FIELD_IDS: tuple[str, ...] = (
    "1_revenue_trend",
    "2_revenue_cagr_yoy",
    "3_gross_margin",
    "4_ebitda_reported",
    "5_ebitda_pf_margin",
    "6_ebitda_bridge",
    "7_addback_pct",
    "8_working_capital",
    "9_opex_breakdown",
    "10_revenue_by_segment",
    "11_projected_financials",
    "12_executive_summary",
    "13_threshold_flags",
    "14_discrepancies",
    "15_data_room_gaps",
    "16_citation_revenue",
    "17_citation_ebitda",
    "18_runtime",
)

FTA_COVERAGE: list[dict[str, str]] = [
    {"item_id": "1_revenue_trend", "display_name": "Revenue trend (3yr)"},
    {"item_id": "2_revenue_cagr_yoy", "display_name": "Revenue CAGR / YoY"},
    {"item_id": "3_gross_margin", "display_name": "Gross margin (3yr)"},
    {"item_id": "4_ebitda_reported", "display_name": "EBITDA reported"},
    {"item_id": "5_ebitda_pf_margin", "display_name": "EBITDA PF adjusted margin"},
    {"item_id": "6_ebitda_bridge", "display_name": "EBITDA bridge (addbacks)"},
    {"item_id": "7_addback_pct", "display_name": "Addback total / addback_pct_of_ebitda"},
    {"item_id": "8_working_capital", "display_name": "Working capital trend"},
    {"item_id": "9_opex_breakdown", "display_name": "OPEX breakdown"},
    {"item_id": "10_revenue_by_segment", "display_name": "Revenue by segment present"},
    {"item_id": "11_projected_financials", "display_name": "Projected financials"},
    {"item_id": "12_executive_summary", "display_name": "Executive summary"},
    {"item_id": "13_threshold_flags", "display_name": "Threshold flags"},
    {"item_id": "14_discrepancies", "display_name": "Discrepancies"},
    {"item_id": "15_data_room_gaps", "display_name": "Data room gaps count"},
    {"item_id": "16_citation_revenue", "display_name": "Citation on revenue"},
    {"item_id": "17_citation_ebitda", "display_name": "Citation on EBITDA"},
    {"item_id": "18_runtime", "display_name": "FTA runtime"},
]

VERDICT_ENUM = frozenset({"pass", "partial", "miss"})
ROW_COUNT = len(FTA_FIELD_IDS)


def _parse_checklist_rows(text: str) -> list[dict[str, str]]:
    section = text.split(f"## Checklist ({ROW_COUNT} rows)", 1)[-1]
    lines = [ln.strip() for ln in section.splitlines() if ln.strip().startswith("|")]
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


def test_fta_field_ids_exactly_eighteen() -> None:
    assert len(FTA_FIELD_IDS) == 18
    assert len(set(FTA_FIELD_IDS)) == 18


def test_fta_coverage_matches_literal_field_ids() -> None:
    assert tuple(row["item_id"] for row in FTA_COVERAGE) == FTA_FIELD_IDS


def test_fta_checklist_tracked_path_exists() -> None:
    assert FTA_CHECKLIST_PATH.is_file(), f"missing canonical checklist: {FTA_CHECKLIST_PATH}"


def test_fta_checklist_row_count() -> None:
    text = FTA_CHECKLIST_PATH.read_text(encoding="utf-8")
    rows = _parse_checklist_rows(text)
    assert len(rows) == ROW_COUNT


def test_fta_checklist_item_ids_match_literal_pin() -> None:
    text = FTA_CHECKLIST_PATH.read_text(encoding="utf-8")
    rows = _parse_checklist_rows(text)
    assert tuple(r["item_id"] for r in rows) == FTA_FIELD_IDS


def test_fta_checklist_display_names_match_coverage() -> None:
    text = FTA_CHECKLIST_PATH.read_text(encoding="utf-8")
    rows = _parse_checklist_rows(text)
    display_by_id = {row["item_id"]: row["display_name"] for row in FTA_COVERAGE}
    for row in rows:
        assert row["display_name"] == display_by_id[row["item_id"]]


def test_fta_checklist_verdicts_in_enum() -> None:
    text = FTA_CHECKLIST_PATH.read_text(encoding="utf-8")
    rows = _parse_checklist_rows(text)
    for row in rows:
        assert row["verdict"] in VERDICT_ENUM, (
            f"invalid verdict for {row['item_id']}: {row['verdict']!r}"
        )


def test_fta_checklist_summary_counts_match_row_verdicts() -> None:
    text = FTA_CHECKLIST_PATH.read_text(encoding="utf-8")
    rows = _parse_checklist_rows(text)
    tallies = {v: sum(1 for r in rows if r["verdict"] == v) for v in VERDICT_ENUM}
    summary = text.split("**Summary:**", 1)[-1]
    for verdict, count in tallies.items():
        assert f"{count} `{verdict}`" in summary, (
            f"summary missing tally for {verdict}={count}"
        )


def test_fta_checklist_floor_prose_present() -> None:
    text = FTA_CHECKLIST_PATH.read_text(encoding="utf-8")
    assert "≥ **16/18**" in text or ">=16/18" in text
    assert "score_fta()" in text


def test_fta_checklist_mutation_missing_field_id_fails(tmp_path: Path) -> None:
    """Falsifier: dropping one field id from a copied checklist must fail item-id pin."""
    text = FTA_CHECKLIST_PATH.read_text(encoding="utf-8")
    mutated = text.replace("| 18_runtime |", "| 18_runtime_removed |", 1)
    bad_path = tmp_path / "bad_fta_checklist.md"
    bad_path.write_text(mutated, encoding="utf-8")
    rows = _parse_checklist_rows(bad_path.read_text(encoding="utf-8"))
    assert tuple(r["item_id"] for r in rows) != FTA_FIELD_IDS
