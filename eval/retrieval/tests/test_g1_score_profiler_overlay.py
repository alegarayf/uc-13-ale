"""Hermetic tests for score_profiler() industry_overlay verdict (cycle-1 P3)."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_G1_SCORER_PATH = _REPO_ROOT / "eval" / "program" / "g1_score_all_agents.py"

if not _G1_SCORER_PATH.is_file():
    pytest.skip(
        "eval/program/g1_score_all_agents.py absent — profiler overlay tests skipped",
        allow_module_level=True,
    )


def _load_module_ast() -> ast.Module:
    return ast.parse(_G1_SCORER_PATH.read_text(encoding="utf-8"))


def _score_profiler_source(tree: ast.Module) -> str:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "score_profiler":
            return ast.get_source_segment(
                _G1_SCORER_PATH.read_text(encoding="utf-8"), node
            ) or ""
    raise AssertionError("score_profiler() not found in g1_score_all_agents.py")


def _load_score_profiler_callable() -> dict:
    """Compile score_profiler() plus module-level deps without live Databricks."""
    tree = _load_module_ast()
    needed_names = {
        "jl",
        "nonempty",
        "count_pass",
        "score_profiler",
        "_OVERLAY_TO_KPI_COLUMN",
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
    exec(  # noqa: S102 — isolated AST subset, not attacker-controlled input
        compile(module, filename=str(_G1_SCORER_PATH), mode="exec"), namespace
    )
    missing = {"score_profiler", "_OVERLAY_TO_KPI_COLUMN"} - namespace.keys()
    if missing:
        raise AssertionError(f"score_profiler() isolation namespace missing: {missing}")
    return namespace


def _minimal_profiler_row(industry_overlay: str | None) -> dict:
    return {
        "industry_overlay": industry_overlay,
        "revenue_model": "hybrid",
        "business_description": "digital finance consultancy",
        "deal_type": "growth_equity",
        "banked": "true",
        "vertical_subsector": "IT_services",
        "data_room_gaps": json.dumps([]),
    }


def test_score_profiler_uses_overlay_mapping_not_hardcoded_healthcare() -> None:
    body = _score_profiler_source(_load_module_ast())
    assert "_OVERLAY_TO_KPI_COLUMN" in body
    assert '== "healthcare_services"' not in body


def test_score_profiler_industry_overlay_passes_for_all_five_valid_overlays() -> None:
    ns = _load_score_profiler_callable()
    score_profiler = ns["score_profiler"]
    for overlay in (
        "tech_services",
        "healthcare_services",
        "b2b_saas",
        "industrial",
        "consumer",
    ):
        _, verdicts = score_profiler(_minimal_profiler_row(overlay))
        assert verdicts["industry_overlay"] == "pass", f"overlay={overlay!r} should pass"


def test_score_profiler_industry_overlay_stays_partial_for_unknown_and_none() -> None:
    ns = _load_score_profiler_callable()
    score_profiler = ns["score_profiler"]
    for overlay in ("unknown", "", None):
        _, verdicts = score_profiler(_minimal_profiler_row(overlay))
        assert verdicts["industry_overlay"] == "partial", f"overlay={overlay!r} should partial"


def test_score_profiler_tech_services_clearsulting_row_scores_six_of_seven() -> None:
    """Clearsulting live row: tech_services overlay + NULL gaps -> 6/7 (was 5/7)."""
    ns = _load_score_profiler_callable()
    score_profiler = ns["score_profiler"]
    row = _minimal_profiler_row("tech_services")
    row["data_room_gaps"] = None
    passes, verdicts = score_profiler(row)
    assert verdicts["industry_overlay"] == "pass"
    assert verdicts["data_room_gaps"] == "partial"
    assert passes == 6
