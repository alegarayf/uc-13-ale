"""Lock cqa.retrieve_account_size workstream_filter to Projection Model gold.

Cycle 9 / P2: destack moved Elder Care account_size gold onto
Elder Care Projection Model_vUPLOAD.xlsx (FINANCIAL + QUALITY_EARNINGS).
The producer still filtered CUSTOMER + KPI_OPS only, so 0/22 gold could
enter the candidate set (baseline_e828d3409c9c mode=empty).
"""

from __future__ import annotations

import ast
from pathlib import Path

import yaml

from eval.retrieval.registry_extractor import IntentRegistryExtractor

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENT_PATH = REPO_ROOT / "databricks" / "agents" / "workstreams" / "customer_quality_agent.py"
REGISTRY_PATH = REPO_ROOT / "eval" / "retrieval" / "intent_registry.yaml"
INTENT_ID = "cqa.retrieve_account_size"
EXPECTED_FILTER = ["CUSTOMER", "KPI_OPS", "FINANCIAL", "QUALITY_EARNINGS"]


def _agent_account_size_filter() -> list[str]:
    tree = ast.parse(AGENT_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name != "_tool_retrieve_account_size":
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            for keyword in child.keywords:
                if keyword.arg == "workstream_filter":
                    return ast.literal_eval(keyword.value)
    raise AssertionError("_tool_retrieve_account_size workstream_filter not found")


def _committed_account_size_filter() -> list[str]:
    rows = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    by_id = {row["intent_id"]: row for row in rows}
    return list(by_id[INTENT_ID]["workstream_filter"])


def _live_account_size_filter() -> list[str]:
    extractor = IntentRegistryExtractor(REPO_ROOT)
    live = {intent.intent_id: intent for intent in extractor.extract()}
    return list(live[INTENT_ID].workstream_filter)


def test_account_size_filter_admits_financial_and_quality_earnings():
    assert _agent_account_size_filter() == EXPECTED_FILTER
    assert _committed_account_size_filter() == EXPECTED_FILTER
    assert _live_account_size_filter() == EXPECTED_FILTER


def test_account_size_agent_and_registry_filter_stay_in_lockstep():
    assert _agent_account_size_filter() == _committed_account_size_filter()
    assert _committed_account_size_filter() == _live_account_size_filter()
