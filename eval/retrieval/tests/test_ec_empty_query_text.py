"""Lockstep query-text edits for Elder Care leftover empty intents.

Cycle 10 / P2: cqa.retrieve_customer_concentration and profiler.revenue_model
stay mode=empty on baseline_70342489afec. Gold already passes
filename/workstream/tier. Query text is the remaining miss — concentration
needs billing-by-client tokens; revenue_model needs Deel/MSA contract-type
tokens (Contract filename token is already landed).
"""

from __future__ import annotations

import ast
from pathlib import Path

import yaml

from eval.retrieval.registry_extractor import IntentRegistryExtractor

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENT_PATH = REPO_ROOT / "databricks" / "agents" / "workstreams" / "customer_quality_agent.py"
PROFILER_PATH = REPO_ROOT / "databricks" / "jobs" / "scripts" / "company_profiler.py"
REGISTRY_PATH = REPO_ROOT / "eval" / "retrieval" / "intent_registry.yaml"

CONCENTRATION_INTENT = "cqa.retrieve_customer_concentration"
REVENUE_MODEL_INTENT = "profiler.revenue_model"

CONCENTRATION_QUERY = (
    "top customers revenue concentration customer list percentage revenue share "
    "billing amount summary by client Billing"
)
REVENUE_MODEL_QUERY = (
    "revenue model contract type recurring revenue subscription retainer Deel MSA"
)


def _cqa_concentration_query() -> str:
    tree = ast.parse(AGENT_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name != "_tool_retrieve_customer_concentration":
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Assign):
                continue
            for target in child.targets:
                if isinstance(target, ast.Name) and target.id == "query":
                    return ast.literal_eval(child.value)
    raise AssertionError("_tool_retrieve_customer_concentration query not found")


def _profiler_revenue_model_query() -> str:
    tree = ast.parse(PROFILER_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.AnnAssign):
            continue
        if not isinstance(node.target, ast.Name) or node.target.id != "_PROFILING_QUERIES":
            continue
        assert isinstance(node.value, ast.Dict)
        for key, val in zip(node.value.keys, node.value.values, strict=True):
            if isinstance(key, ast.Constant) and key.value == "revenue_model":
                return ast.literal_eval(val)[0]
    raise AssertionError("_PROFILING_QUERIES[revenue_model] query not found")


def _committed_query(intent_id: str) -> str:
    rows = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    by_id = {row["intent_id"]: row for row in rows}
    return str(by_id[intent_id]["query"])


def _live_query(intent_id: str) -> str:
    extractor = IntentRegistryExtractor(REPO_ROOT)
    live = {intent.intent_id: intent for intent in extractor.extract()}
    return str(live[intent_id].query)


def test_concentration_query_has_billing_by_client_tokens():
    query = _cqa_concentration_query()
    assert query == CONCENTRATION_QUERY
    assert "billing amount summary by client" in query
    assert "Billing" in query


def test_revenue_model_query_has_deel_msa_tokens():
    query = _profiler_revenue_model_query()
    assert query == REVENUE_MODEL_QUERY
    assert "Deel" in query
    assert "MSA" in query
    assert "Contract" in _committed_file_name_filter(REVENUE_MODEL_INTENT)


def test_concentration_agent_registry_extractor_lockstep():
    assert _cqa_concentration_query() == _committed_query(CONCENTRATION_INTENT)
    assert _committed_query(CONCENTRATION_INTENT) == _live_query(CONCENTRATION_INTENT)


def test_revenue_model_profiler_registry_extractor_lockstep():
    assert _profiler_revenue_model_query() == _committed_query(REVENUE_MODEL_INTENT)
    assert _committed_query(REVENUE_MODEL_INTENT) == _live_query(REVENUE_MODEL_INTENT)


def _committed_file_name_filter(intent_id: str) -> list[str]:
    rows = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    by_id = {row["intent_id"]: row for row in rows}
    return list(by_id[intent_id]["file_name_filter"])
