"""Lockstep query append for SPG revenue-by-location dashboard golds.

Cycle 14 / P4: gold chunk 84311b20 sits at pin rank 14 (sim 0.6588 vs
rank-10 cutoff 0.6609). Appending Shared Practices Dashboard / new-patient-
visits tokens must keep the existing production query intact.
"""

from __future__ import annotations

import ast
from pathlib import Path

import yaml

from eval.retrieval.registry_extractor import IntentRegistryExtractor

REPO_ROOT = Path(__file__).resolve().parents[3]
BMA_PATH = REPO_ROOT / "databricks" / "agents" / "workstreams" / "business_model_agent.py"
REGISTRY_PATH = REPO_ROOT / "eval" / "retrieval" / "intent_registry.yaml"

INTENT_ID = "bma.retrieve_revenue_by_location_and_metrics"
DASHBOARD_PHRASE = (
    "Shared Practices Dashboard new patient visits distribution within my network locations"
)
EXISTING_TAIL = "same store revenue organic growth by market revenue goal by location"
UNCHANGED_FILE_NAME_FILTER = [
    "CIM",
    "OM",
    "Financial",
    "Revenue",
    "Metrics",
    "Overview",
    "Summary",
    "KPI",
    "Dashboard",
]
UNCHANGED_WORKSTREAM_FILTER = ["BUSINESS_MODEL", "FINANCIAL", "KPI_OPS"]
UNCHANGED_TOP_K = 15


def _bma_tool_query() -> str:
    tree = ast.parse(BMA_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name != "_tool_retrieve_revenue_by_location_and_metrics":
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            for keyword in child.keywords:
                if keyword.arg == "query":
                    return ast.literal_eval(keyword.value)
    raise AssertionError("_tool_retrieve_revenue_by_location_and_metrics query not found")


def _committed_row() -> dict:
    rows = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    by_id = {row["intent_id"]: row for row in rows}
    return by_id[INTENT_ID]


def _live_query() -> str:
    extractor = IntentRegistryExtractor(REPO_ROOT)
    live = {intent.intent_id: intent for intent in extractor.extract()}
    return str(live[INTENT_ID].query)


def test_revenue_by_location_query_appends_dashboard_tokens():
    # Cycle-14 reconciliation: GKF (P3) additively appended org-chart tokens
    # after SPG's (P4) dashboard tokens on this same shared, non-company-scoped
    # query, so the dashboard phrase is no longer the string's tail -- assert
    # ordering relative to the original tail only, not exclusivity of what
    # comes after it. See runs/ledger.md cycle-14 process/CRITICAL entries.
    query = _bma_tool_query()
    assert EXISTING_TAIL in query
    assert DASHBOARD_PHRASE in query
    assert query.index(EXISTING_TAIL) < query.index(DASHBOARD_PHRASE)


def test_revenue_by_location_other_knobs_unchanged():
    row = _committed_row()
    assert row["file_name_filter"] == UNCHANGED_FILE_NAME_FILTER
    assert row["workstream_filter"] == UNCHANGED_WORKSTREAM_FILTER
    assert row["top_k"] == UNCHANGED_TOP_K
    assert row["invocation_path"] == "with_fallback"


def test_revenue_by_location_agent_registry_extractor_lockstep():
    agent_query = _bma_tool_query()
    committed = str(_committed_row()["query"])
    live = _live_query()
    assert agent_query == committed
    assert committed == live
    assert DASHBOARD_PHRASE in committed
    assert DASHBOARD_PHRASE in live
