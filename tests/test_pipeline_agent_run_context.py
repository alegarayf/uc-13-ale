"""M-RE2 T4 guards: pipeline run_context wiring on workstream agents and FTA intents."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

WORKSTREAM_MAINS = [
    ("databricks/agents/workstreams/financial_trends_agent.py", "fta"),
    ("databricks/agents/workstreams/business_model_agent.py", "bma"),
    ("databricks/agents/workstreams/legal_contracts_agent.py", "legal"),
    ("databricks/agents/workstreams/customer_quality_agent.py", "cqa"),
    ("databricks/agents/workstreams/kpi_agent.py", "kpi"),
    ("databricks/agents/workstreams/quality_of_earnings_agent.py", "qoe"),
]

FTA_SUBAGENTS = [
    "databricks/agents/subagents/workstream/financial/opex_sub_agent.py",
    "databricks/agents/subagents/workstream/financial/revenue_sub_agent.py",
    "databricks/agents/subagents/workstream/financial/ebitda_sub_agent.py",
]

EXPECTED_FTA_INTENT_IDS = {
    "fta.opex.q1_financial_statements",
    "fta.opex.q2_working_capital",
    "fta.opex.q3_projected_financials",
    "fta.revenue.q1_financial_statements",
    "fta.revenue.q2_revenue_by_segment",
    "fta.revenue.q3_revenue_by_geography",
    "fta.revenue.q4_customer_concentration",
    "fta.revenue.q4_customer_concentration_fallback",
    "fta.revenue.q5_quickbooks_pl",
    "fta.ebitda.q1_financial_statements",
    "fta.ebitda.q2_ebitda_and_margins",
    "fta.ebitda.q3_working_capital",
    "fta.ebitda.q4_addback_schedule",
}


def _main_function(source: str) -> ast.FunctionDef:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            return node
    raise AssertionError("main() not found")


def _literal_arg(call: ast.Call, name: str) -> str | None:
    for keyword in call.keywords:
        if keyword.arg == name and isinstance(keyword.value, ast.Constant):
            value = keyword.value.value
            if isinstance(value, str):
                return value
    return None


def _find_open_agent_run(main_fn: ast.FunctionDef) -> ast.Call | None:
    for node in ast.walk(main_fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "open_agent_run":
            return node
    return None


def _has_close_in_finally(main_fn: ast.FunctionDef) -> bool:
    for node in main_fn.body:
        if not isinstance(node, ast.Try):
            continue
        if node.finalbody and any(
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Call)
            and isinstance(stmt.value.func, ast.Name)
            and stmt.value.func.id == "close_agent_run"
            for stmt in node.finalbody
        ):
            return True
    return False


@pytest.mark.parametrize("rel_path,agent_id", WORKSTREAM_MAINS)
def test_workstream_main_opens_and_closes_agent_run(rel_path: str, agent_id: str) -> None:
    path = REPO_ROOT / rel_path
    source = path.read_text(encoding="utf-8")
    main_fn = _main_function(source)

    open_call = _find_open_agent_run(main_fn)
    assert open_call is not None, f"{rel_path}: main() must call open_agent_run()"
    assert _literal_arg(open_call, "agent_id") is None  # positional first arg
    first_arg = open_call.args[0]
    assert isinstance(first_arg, ast.Constant) and first_arg.value == agent_id

    assert "load_affected_intents" in source
    assert _has_close_in_finally(main_fn), f"{rel_path}: main() must close_agent_run() in finally"


def _semantic_search_with_fallback_calls(path: Path) -> list[ast.Call]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "semantic_search_with_fallback":
            calls.append(node)
    return calls


@pytest.mark.parametrize("rel_path", FTA_SUBAGENTS)
def test_fta_subagent_retrieval_calls_pass_intent_id(rel_path: str) -> None:
    path = REPO_ROOT / rel_path
    calls = _semantic_search_with_fallback_calls(path)
    assert calls, f"{rel_path}: expected semantic_search_with_fallback calls"
    missing = [
        call.lineno
        for call in calls
        if _literal_arg(call, "intent_id") is None
    ]
    assert not missing, f"{rel_path}: calls missing intent_id at lines {missing}"


def test_fta_intent_ids_match_registry_subset() -> None:
    seen: set[str] = set()
    for rel_path in FTA_SUBAGENTS:
        path = REPO_ROOT / rel_path
        for call in _semantic_search_with_fallback_calls(path):
            intent_id = _literal_arg(call, "intent_id")
            assert intent_id is not None
            seen.add(intent_id)
    assert seen == EXPECTED_FTA_INTENT_IDS


def test_notebook_cell1_sets_pipeline_thread() -> None:
    nb_path = REPO_ROOT / "databricks" / "jobs" / "notebooks" / "test_pipeline.ipynb"
    notebook = json.loads(nb_path.read_text(encoding="utf-8"))
    config_cells = [
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
        if cell.get("cell_type") == "code"
    ]
    cell1 = next(src for src in config_cells if "Cell 1: Config" in src)
    assert "set_pipeline_thread" in cell1
    assert "uuid4" in cell1
