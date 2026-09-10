"""Clearsulting-only q4 fallback override (cycle 26 / P1).

Shared Ajax/tuition registry query must stay byte-identical (D11).
GKF and SPG keep that string; Clearsulting gets the primary-q4 CIM neighborhood.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from eval.retrieval.harness import (
    CS_Q4_FALLBACK_FILE_NAME_FILTER,
    CS_Q4_FALLBACK_INTENT_ID,
    CS_Q4_FALLBACK_QUERY,
    _fallback_kwargs_from_intent,
    apply_company_intent_overrides,
    build_search_kwargs,
    dispatch_retrieval,
)
from eval.retrieval.registry_extractor import IntentRegistryExtractor

REPO_ROOT = Path(__file__).resolve().parents[3]
SHARED_Q4_QUERY = (
    "Project Ajax Financial Due Diligence Databook Location Analysis Revenue "
    "Detail Combined FY23 tuition by school enrollment"
)
REGISTRY_PATH = REPO_ROOT / "eval" / "retrieval" / "intent_registry.yaml"
PRIMARY_Q4_INTENT_ID = "fta.revenue.q4_customer_concentration"


def _by_id():
    extractor = IntentRegistryExtractor(REPO_ROOT)
    return {intent.intent_id: intent for intent in extractor.extract()}


def _committed_by_id():
    rows = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    return {row["intent_id"]: row for row in rows}


def test_shared_q4_fallback_registry_query_stays_ajax_tuition():
    live = _by_id()
    committed = _committed_by_id()
    assert live[CS_Q4_FALLBACK_INTENT_ID].query == SHARED_Q4_QUERY
    assert committed[CS_Q4_FALLBACK_INTENT_ID]["query"] == SHARED_Q4_QUERY


def test_clearsulting_q4_fallback_gets_primary_cim_override():
    live = _by_id()
    intent = live[CS_Q4_FALLBACK_INTENT_ID]
    overridden = apply_company_intent_overrides(intent, company_name="Clearsulting")
    assert overridden.query == CS_Q4_FALLBACK_QUERY
    assert list(overridden.file_name_filter) == list(CS_Q4_FALLBACK_FILE_NAME_FILTER)
    assert intent.query == SHARED_Q4_QUERY


def test_gkf_and_spg_q4_fallback_keep_shared_registry_query():
    live = _by_id()
    intent = live[CS_Q4_FALLBACK_INTENT_ID]
    for company in ("GKF", "SPG", "Elder Care"):
        resolved = apply_company_intent_overrides(intent, company_name=company)
        assert resolved.query == SHARED_Q4_QUERY
        assert resolved is intent
        kwargs = build_search_kwargs(intent, company_name=company, spark=object())
        assert kwargs["query"] == SHARED_Q4_QUERY
        fallback = _fallback_kwargs_from_intent(intent, company_name=company, spark=object())
        assert fallback["query"] == SHARED_Q4_QUERY


def test_clearsulting_primary_q4_is_not_overridden():
    live = _by_id()
    intent = live[PRIMARY_Q4_INTENT_ID]
    resolved = apply_company_intent_overrides(intent, company_name="Clearsulting")
    assert resolved is intent
    assert resolved.query == intent.query


def test_build_search_kwargs_applies_cs_override():
    live = _by_id()
    intent = live[CS_Q4_FALLBACK_INTENT_ID]
    kwargs = build_search_kwargs(intent, company_name="Clearsulting", spark=object())
    assert kwargs["query"] == CS_Q4_FALLBACK_QUERY
    assert kwargs["file_name_filter"] == list(CS_Q4_FALLBACK_FILE_NAME_FILTER)
    fallback = _fallback_kwargs_from_intent(
        intent, company_name="Clearsulting", spark=object()
    )
    assert fallback["query"] == CS_Q4_FALLBACK_QUERY
    assert fallback["file_name_filter"] == list(CS_Q4_FALLBACK_FILE_NAME_FILTER)


@patch("agents.shared.fallback.semantic_search_with_fallback")
@patch("agents.shared.retrieval.semantic_search")
def test_dispatch_cs_q4_fallback_sends_override_query(mock_semantic, mock_fallback):
    mock_fallback.return_value = (MagicMock(chunks=[], mode="semantic"), False)
    live = _by_id()
    dispatch_retrieval(
        live[CS_Q4_FALLBACK_INTENT_ID],
        company_name="Clearsulting",
        spark=MagicMock(),
    )
    assert mock_fallback.call_args.kwargs["query"] == CS_Q4_FALLBACK_QUERY
    assert mock_fallback.call_args.kwargs["file_name_filter"] == list(
        CS_Q4_FALLBACK_FILE_NAME_FILTER
    )
    mock_semantic.assert_not_called()


@patch("agents.shared.fallback.semantic_search_with_fallback")
@patch("agents.shared.retrieval.semantic_search")
def test_dispatch_gkf_q4_fallback_sends_shared_ajax_query(mock_semantic, mock_fallback):
    mock_fallback.return_value = (MagicMock(chunks=[], mode="semantic"), False)
    live = _by_id()
    dispatch_retrieval(
        live[CS_Q4_FALLBACK_INTENT_ID],
        company_name="GKF",
        spark=MagicMock(),
    )
    assert mock_fallback.call_args.kwargs["query"] == SHARED_Q4_QUERY
    mock_semantic.assert_not_called()
