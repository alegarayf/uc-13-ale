"""Cycle 4 P1 — overlay_block_fields counts schema siblings (Clearsulting KPI)."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_G1_SCORER_PATH = _REPO_ROOT / "eval" / "program" / "g1_score_all_agents.py"

if not _G1_SCORER_PATH.is_file():
    pytest.skip(
        "eval/program/g1_score_all_agents.py absent — KPI overlay block tests skipped",
        allow_module_level=True,
    )


def _load_module_ast() -> ast.Module:
    return ast.parse(_G1_SCORER_PATH.read_text(encoding="utf-8"))


def _load_score_kpi_callable() -> dict:
    tree = _load_module_ast()
    needed_names = {
        "jl",
        "nonempty",
        "count_pass",
        "score_kpi",
        "_OVERLAY_TO_KPI_COLUMN",
        "_OVERLAY_BLOCK_FIELDS",
    }
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in needed_names:
            nodes.append(node)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id in needed_names:
                nodes.append(node)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in needed_names:
                    nodes.append(node)
                    break
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace: dict = {"json": json}
    exec(  # noqa: S102
        compile(module, filename=str(_G1_SCORER_PATH), mode="exec"), namespace
    )
    missing = {"score_kpi", "_OVERLAY_TO_KPI_COLUMN", "_OVERLAY_BLOCK_FIELDS"} - namespace.keys()
    if missing:
        raise AssertionError(f"score_kpi() isolation namespace missing: {missing}")
    return namespace


def _clearsulting_like_block(*, with_siblings: bool) -> dict:
    """Live Clearsulting tech_services_kpis_json shape: 2/9 subset keys populated."""
    block: dict = {
        "utilization_rate_pct": None,
        "utilization_period": None,
        "average_bill_rate_dollars": 179,
        "contractor_pct_of_workforce": None,
        "delivery_geography_note": "Primarily US-based delivery",
        "average_acv_dollars": None,
        "bookings_stated": None,
        "backlog_months_of_revenue": None,
        "pipeline_coverage_months": None,
        "source_doc": "KPI_Summary.xlsx",
    }
    if with_siblings:
        block["bill_rates_by_role"] = [{"role": "Senior Consultant", "bill_rate_dollars": 225}]
        block["gross_margin_by_segment"] = [{"segment_label": "Advisory", "gm_pct": 42}]
        block["delivery_capacity_note"] = "279 billable FTE as of Dec 2024"
        block["bench_note"] = "Bench managed via internal rotation"
    return block


def test_overlay_block_fields_passes_with_populated_schema_siblings() -> None:
    """Clearsulting live row: 2 subset keys + 4 siblings -> pop 6 >= 5 -> pass."""
    ns = _load_score_kpi_callable()
    score_kpi = ns["score_kpi"]
    d = {
        "overlay_confirmed": "tech_services",
        "tech_services_kpis_json": json.dumps(_clearsulting_like_block(with_siblings=True)),
        "missing_kpis_json": json.dumps([{}] * 5),
    }
    passes, verdicts = score_kpi(d)
    assert verdicts["overlay_block_fields"] == "pass"
    assert passes == 3


def test_overlay_block_fields_stays_partial_without_schema_siblings() -> None:
    """Falsifier: only 2/9 subset keys populated, no siblings -> partial."""
    ns = _load_score_kpi_callable()
    score_kpi = ns["score_kpi"]
    d = {
        "overlay_confirmed": "tech_services",
        "tech_services_kpis_json": json.dumps(_clearsulting_like_block(with_siblings=False)),
        "missing_kpis_json": json.dumps([{}] * 5),
    }
    _, verdicts = score_kpi(d)
    assert verdicts["overlay_block_fields"] == "partial"
