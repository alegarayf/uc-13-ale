"""Hermetic falsifier for Elder Care F2 empty intents — production query text.

Cycle 2 / P1: CQA harness queries were extractor stubs (`query=query` Name
not resolved). legal.ip_privacy omitted the HIPAA/ND production pass.
profiler.revenue_model filename tokens missed Deel Contract gold.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from eval.retrieval.registry_extractor import IntentRegistryExtractor

REPO_ROOT = Path(__file__).resolve().parents[3]
REGISTRY_PATH = REPO_ROOT / "eval" / "retrieval" / "intent_registry.yaml"

EMPTY_INTENT_IDS = (
    "cqa.retrieve_account_size",
    "cqa.retrieve_customer_health",
    "legal.ip_privacy",
    "profiler.revenue_model",
)

CQA_STUBS = {
    "cqa.retrieve_account_size": "retrieve account size",
    "cqa.retrieve_customer_health": "retrieve customer health",
}

CQA_PRODUCTION = {
    "cqa.retrieve_account_size": (
        "average account size ACV annual contract value revenue per customer "
        "SMB enterprise"
    ),
    "cqa.retrieve_customer_health": (
        "customer health AR aging late payment overdue DSO discounts rebates "
        "concessions complaints NPS utilization declining spend collections"
    ),
}

PROFILER_PRODUCTION_QUERY = (
    "revenue model contract type recurring revenue subscription retainer"
)


def _by_id():
    extractor = IntentRegistryExtractor(REPO_ROOT)
    return {intent.intent_id: intent for intent in extractor.extract()}


def _committed_by_id():
    rows = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    return {row["intent_id"]: row for row in rows}


def test_f2_cqa_queries_are_production_text_not_stubs():
    live = _by_id()
    committed = _committed_by_id()
    for intent_id, stub in CQA_STUBS.items():
        assert live[intent_id].query != stub
        assert live[intent_id].query == CQA_PRODUCTION[intent_id]
        assert committed[intent_id]["query"] == CQA_PRODUCTION[intent_id]


def test_f2_legal_ip_privacy_emits_hipaa_nd_production_query():
    live = _by_id()
    committed = _committed_by_id()
    query = live["legal.ip_privacy"].query
    assert "retrieve" not in query.lower().split()[:1]
    assert "HIPAA confidentiality" in query
    assert "non-disclosure" in query.lower()
    assert "PHI" in query
    assert "Non-Disclosure" in live["legal.ip_privacy"].file_name_filter
    assert committed["legal.ip_privacy"]["query"] == query


def test_f2_profiler_revenue_model_matches_contract_gold_filename():
    live = _by_id()
    committed = _committed_by_id()
    intent = live["profiler.revenue_model"]
    assert intent.query == PROFILER_PRODUCTION_QUERY
    assert "Contract" in intent.file_name_filter
    assert "Memorandum" in intent.file_name_filter
    gold_name = "Deel Contract_SAMPLE.pdf"
    assert any(token.lower() in gold_name.lower() for token in intent.file_name_filter)
    assert committed["profiler.revenue_model"]["query"] == PROFILER_PRODUCTION_QUERY
    assert "Contract" in committed["profiler.revenue_model"]["file_name_filter"]


def test_f2_four_empty_intents_not_stub_strings():
    live = _by_id()
    for intent_id in EMPTY_INTENT_IDS:
        query = live[intent_id].query
        assert query not in CQA_STUBS.values()
        assert not query.startswith("retrieve ")
