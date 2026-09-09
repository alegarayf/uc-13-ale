"""Hermetic falsifiers for score_cqa() payor_mix / customer_tenure gap-correct."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_G1_SCORER_PATH = _REPO_ROOT / "eval" / "program" / "g1_score_all_agents.py"

if not _G1_SCORER_PATH.is_file():
    pytest.skip(
        "eval/program/g1_score_all_agents.py absent — score_cqa guard skipped",
        allow_module_level=True,
    )


def _load_module_ast() -> ast.Module:
    return ast.parse(_G1_SCORER_PATH.read_text(encoding="utf-8"))


def _load_score_cqa_callable() -> dict:
    tree = _load_module_ast()
    needed_names = {
        "jl",
        "nonempty",
        "count_pass",
        "score_cqa",
        "_NOT_FOUND_SOURCE_MARKERS",
        "_payor_row_source_na",
        "_payor_list_explicitly_na",
        "_customer_tenure_null",
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
    missing = {"score_cqa", "jl", "nonempty", "count_pass"} - namespace.keys()
    if missing:
        raise AssertionError(f"score_cqa() isolation namespace missing: {missing}")
    return namespace


def _baseline_cqa() -> dict[str, str]:
    return {
        "top_customers_json": json.dumps([{"name": "Client 1"}]),
        "retention_json": json.dumps({"nrr_pct": "73%"}),
        "customer_tenure_json": json.dumps({}),
        "payor_mix_json": json.dumps([]),
        "discrepancies_json": json.dumps([{"metric": "a"}, {"metric": "b"}, {"metric": "c"}]),
        "data_room_gaps": json.dumps(["gap"]),
    }


@pytest.fixture(scope="module")
def score_cqa_ns() -> dict:
    return _load_score_cqa_callable()


@pytest.fixture(scope="module")
def score_cqa(score_cqa_ns: dict):
    return score_cqa_ns["score_cqa"]


def test_payor_mix_gap_correct_when_all_rows_not_found(score_cqa) -> None:
    """Clearsulting consultancy: healthcare scaffold with explicit not-found sources."""
    payor = [
        {
            "payor_category": cat,
            "pct_of_revenue": None,
            "source_doc": "Not found in retrieved context",
        }
        for cat in ("Medicare", "Medicaid", "Commercial")
    ]
    d = {**_baseline_cqa(), "payor_mix_json": json.dumps(payor)}
    _, verdicts = score_cqa(d)
    assert verdicts["payor_mix"] == "gap-correct"


def test_payor_mix_gap_correct_for_single_na_category(score_cqa) -> None:
    d = {
        **_baseline_cqa(),
        "payor_mix_json": json.dumps(
            [{"payor_category": "N/A", "pct_of_revenue": None, "source_doc": None}]
        ),
    }
    _, verdicts = score_cqa(d)
    assert verdicts["payor_mix"] == "gap-correct"


def test_payor_mix_stays_partial_for_unsourced_scaffold(score_cqa) -> None:
    """Falsifier: populated categories without values or explicit N/A stay partial."""
    payor = [
        {"payor_category": "Medicare", "pct_of_revenue": None, "source_doc": None},
        {"payor_category": "Commercial", "pct_of_revenue": None, "source_doc": None},
    ]
    d = {**_baseline_cqa(), "payor_mix_json": json.dumps(payor)}
    _, verdicts = score_cqa(d)
    assert verdicts["payor_mix"] == "partial"


def test_payor_mix_pass_when_any_pct_populated(score_cqa) -> None:
    payor = [
        {"payor_category": "Private Pay", "pct_of_revenue": "64%", "source_doc": "cim.pdf"},
        {"payor_category": "Medicare", "pct_of_revenue": None, "source_doc": None},
    ]
    d = {**_baseline_cqa(), "payor_mix_json": json.dumps(payor)}
    _, verdicts = score_cqa(d)
    assert verdicts["payor_mix"] == "pass"


def test_customer_tenure_gap_correct_when_null_with_discrepancies(score_cqa) -> None:
    d = {
        **_baseline_cqa(),
        "customer_tenure_json": json.dumps(
            {
                "average_tenure_years": None,
                "tenure_distribution_note": None,
                "source_doc": None,
            }
        ),
    }
    _, verdicts = score_cqa(d)
    assert verdicts["customer_tenure"] == "gap-correct"


def test_customer_tenure_stays_partial_without_discrepancies(score_cqa) -> None:
    d = {
        **_baseline_cqa(),
        "customer_tenure_json": json.dumps({}),
        "discrepancies_json": json.dumps([]),
    }
    _, verdicts = score_cqa(d)
    assert verdicts["customer_tenure"] == "partial"
