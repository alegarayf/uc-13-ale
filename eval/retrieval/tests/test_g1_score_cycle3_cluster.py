"""Cycle 3 P1 — hermetic guards for four G1 scorer predicate fixes."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_G1_SCORER_PATH = _REPO_ROOT / "eval" / "program" / "g1_score_all_agents.py"

if not _G1_SCORER_PATH.is_file():
    pytest.skip(
        "eval/program/g1_score_all_agents.py absent — cycle-3 cluster guard skipped",
        allow_module_level=True,
    )


def _load_module_ast() -> ast.Module:
    return ast.parse(_G1_SCORER_PATH.read_text(encoding="utf-8"))


def _compile_functions(*names: str) -> dict:
    tree = _load_module_ast()
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            nodes.append(node)
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace: dict = {"json": json, "re": __import__("re")}
    exec(  # noqa: S102
        compile(module, filename=str(_G1_SCORER_PATH), mode="exec"), namespace
    )
    missing = set(names) - namespace.keys()
    if missing:
        raise AssertionError(f"isolation namespace missing: {missing}")
    return namespace


@pytest.fixture(scope="module")
def g1_ns() -> dict:
    return _compile_functions(
        "jl",
        "count_pass",
        "score_legal",
        "score_qoe",
        "score_fta",
        "_revenue_period_is_projection",
    )


def test_restrictive_passes_on_sourced_employment_non_compete(g1_ns: dict) -> None:
    score_legal = g1_ns["score_legal"]
    payload = {
        "contract_register_json": "[]",
        "vendor_register_json": "[]",
        "platform_dependency_register_json": "[]",
        "employment_register_json": json.dumps(
            [
                {
                    "agreement_class": "employee",
                    "source_doc": "Non-Compete Agreement.docx",
                    "non_compete": {"present": "true"},
                    "non_solicit": {"present": "not_found"},
                }
            ]
        ),
        "litigation_register_json": "[]",
        "privacy_security_register_json": "[]",
        "ip_register_json": "[]",
        "insurance_register_json": "[]",
    }
    points, verdicts = score_legal(payload)
    assert verdicts["restrictive"] == "pass"
    assert points >= 1


def test_restrictive_stays_gap_correct_without_employment_covenant(g1_ns: dict) -> None:
    """Falsifier: contract-only not_found + empty employment must not flip."""
    score_legal = g1_ns["score_legal"]
    payload = {
        "contract_register_json": json.dumps(
            [{"restrictive_covenants": {"present": "not_found"}}]
        ),
        "vendor_register_json": "[]",
        "platform_dependency_register_json": "[]",
        "employment_register_json": json.dumps(
            [
                {
                    "agreement_class": "employee",
                    "source_doc": "Offer Letter.pdf",
                    "non_compete": {"present": "not_found"},
                    "non_solicit": {"present": "not_found"},
                }
            ]
        ),
        "litigation_register_json": "[]",
        "privacy_security_register_json": "[]",
        "ip_register_json": "[]",
        "insurance_register_json": "[]",
    }
    _, verdicts = score_legal(payload)
    assert verdicts["restrictive"] == "gap-correct"


def test_qofe_report_present_true_is_pass(g1_ns: dict) -> None:
    score_qoe = g1_ns["score_qoe"]
    base = {
        "revenue_quality_flags_json": json.dumps([{}, {}, {}]),
        "ebitda_scenarios_json": json.dumps({"reported_ebitda": 1}),
        "pre_qofe_scope_items_json": json.dumps([{}] * 5),
        "addback_ledger_json": json.dumps([{"tier_classification": "Tier 4"}]),
        "data_room_gaps": json.dumps([]),
        "tier4_addback_count": 1,
    }
    _, verdicts = score_qoe({**base, "qofe_report_present": "true"})
    assert verdicts["qofe_report_present"] == "pass"


def test_tier_classification_fidelity_counts_tier4_rows_not_ledger_length(
    g1_ns: dict,
) -> None:
    score_qoe = g1_ns["score_qoe"]
    ledger = [
        {"tier_classification": "Tier 4"},
        {"tier_classification": "Tier 4"},
        {"tier_classification": "Tier 1"},
    ]
    payload = {
        "revenue_quality_flags_json": json.dumps([{}, {}, {}]),
        "ebitda_scenarios_json": json.dumps({"reported_ebitda": 1}),
        "pre_qofe_scope_items_json": json.dumps([{}] * 5),
        "qofe_report_present": "false",
        "addback_ledger_json": json.dumps(ledger),
        "data_room_gaps": json.dumps([]),
        "tier4_addback_count": 2,
    }
    _, verdicts = score_qoe(payload)
    assert verdicts["tier_classification_fidelity"] == "pass"


def test_revenue_period_is_projection_distinguishes_actuals_from_estimates(
    g1_ns: dict,
) -> None:
    fn = g1_ns["_revenue_period_is_projection"]
    assert fn("2024") is False
    assert fn("2024A") is False
    assert fn("2024E") is True
    assert fn("2025P") is True
    assert fn("TTM25") is False


def test_projected_financials_miss_on_historical_2024_only(g1_ns: dict) -> None:
    score_fta = g1_ns["score_fta"]
    payload = {
        "revenue_trend_json": json.dumps(
            [
                {"period": "2022", "source_doc": "pl.xlsx"},
                {"period": "2023", "source_doc": "pl.xlsx"},
                {"period": "2024", "source_doc": "pl.xlsx"},
            ]
        ),
        "gross_margin_json": json.dumps([{}] * 5),
        "ebitda_json": json.dumps([{}] * 5),
        "working_capital_json": json.dumps({"dso_days": 30}),
        "opex_breakdown_json": json.dumps([{}, {}, {}]),
        "revenue_by_segment_json": json.dumps([{}] * 10),
        "addback_schedule_json": json.dumps([{}] * 10),
        "budget_vs_actual_json": "[]",
        "flags": json.dumps([{}, {}]),
        "data_room_gaps": json.dumps(["gap"]),
        "citations": "[]",
        "executive_summary": "x" * 200,
        "addback_pct_of_ebitda": 0.1,
    }
    _, verdicts = score_fta(payload)
    assert verdicts["11_projected_financials"] == "miss"


def test_projected_financials_partial_when_projection_period_present(g1_ns: dict) -> None:
    score_fta = g1_ns["score_fta"]
    payload = {
        "revenue_trend_json": json.dumps(
            [
                {"period": "2023A", "source_doc": "pl.xlsx"},
                {"period": "2024E", "source_doc": "model.xlsx"},
            ]
        ),
        "gross_margin_json": json.dumps([{}] * 5),
        "ebitda_json": json.dumps([{}] * 5),
        "working_capital_json": json.dumps({"dso_days": 30}),
        "opex_breakdown_json": json.dumps([{}, {}, {}]),
        "revenue_by_segment_json": json.dumps([{}] * 10),
        "addback_schedule_json": json.dumps([{}] * 10),
        "budget_vs_actual_json": "[]",
        "flags": json.dumps([{}, {}]),
        "data_room_gaps": json.dumps(["gap"]),
        "citations": "[]",
        "executive_summary": "x" * 200,
        "addback_pct_of_ebitda": 0.1,
    }
    _, verdicts = score_fta(payload)
    assert verdicts["11_projected_financials"] == "partial"
