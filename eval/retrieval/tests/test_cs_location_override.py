"""Clearsulting-only location override (cycle 27 / P1).

Shared GKF/SPG healthcare/org location query must stay byte-identical (D11).
GKF and SPG keep that string; Clearsulting gets the Memorandum office neighborhood.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from eval.retrieval.harness import (
    CS_LOCATION_FILE_NAME_FILTER,
    CS_LOCATION_INTENT_ID,
    CS_LOCATION_QUERY,
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
SHARED_LOCATION_QUERY = (
    "clients served active accounts customers by location by market by segment "
    "billed hours per client revenue per customer revenue per account utilization "
    "per customer sessions per user visits per patient customer count trend quarterly "
    "growth by location by geography length of stay customer tenure distribution cohort "
    "by duration revenue per location revenue by market adjusted revenue by geography "
    "revenue CAGR financial highlights headline metrics acquisition pipeline same store "
    "revenue organic growth by market revenue goal by location Shared Practices "
    "Dashboard new patient visits distribution within my network locations Corporate "
    "Organization Current State leadership team DMV Mike Pesi CEO Ross Flax Ellicott "
    "City Academic Director Teachers and Staff"
)
SHARED_LOCATION_FILE_NAME_FILTER = [
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
REGISTRY_PATH = REPO_ROOT / "eval" / "retrieval" / "intent_registry.yaml"
PEOPLE_AND_ORG_INTENT_ID = "bma.retrieve_people_and_org"


def _by_id():
    extractor = IntentRegistryExtractor(REPO_ROOT)
    return {intent.intent_id: intent for intent in extractor.extract()}


def _committed_by_id():
    rows = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    return {row["intent_id"]: row for row in rows}


def test_shared_location_registry_query_stays_healthcare_org_tail():
    live = _by_id()
    committed = _committed_by_id()
    assert live[CS_LOCATION_INTENT_ID].query == SHARED_LOCATION_QUERY
    assert committed[CS_LOCATION_INTENT_ID]["query"] == SHARED_LOCATION_QUERY
    assert list(live[CS_LOCATION_INTENT_ID].file_name_filter) == SHARED_LOCATION_FILE_NAME_FILTER
    assert list(committed[CS_LOCATION_INTENT_ID]["file_name_filter"]) == SHARED_LOCATION_FILE_NAME_FILTER
    assert "Mike Pesi" in live[CS_LOCATION_INTENT_ID].query
    assert "Shared Practices Dashboard" in live[CS_LOCATION_INTENT_ID].query
    assert "Ellicott City" in live[CS_LOCATION_INTENT_ID].query


def test_clearsulting_location_gets_memorandum_override():
    live = _by_id()
    intent = live[CS_LOCATION_INTENT_ID]
    overridden = apply_company_intent_overrides(intent, company_name="Clearsulting")
    assert overridden.query == CS_LOCATION_QUERY
    assert list(overridden.file_name_filter) == list(CS_LOCATION_FILE_NAME_FILTER)
    assert "Memorandum" in overridden.file_name_filter
    assert "Revenue" not in overridden.file_name_filter
    assert "Ellicott City" not in overridden.query
    assert "Mike Pesi" not in overridden.query
    assert "Shared Practices Dashboard" not in overridden.query
    assert intent.query == SHARED_LOCATION_QUERY
    assert list(intent.file_name_filter) == SHARED_LOCATION_FILE_NAME_FILTER


def test_gkf_and_spg_location_keep_shared_registry_query():
    live = _by_id()
    intent = live[CS_LOCATION_INTENT_ID]
    for company in ("GKF", "SPG", "Elder Care"):
        resolved = apply_company_intent_overrides(intent, company_name=company)
        assert resolved.query == SHARED_LOCATION_QUERY
        assert resolved is intent
        kwargs = build_search_kwargs(intent, company_name=company, spark=object())
        assert kwargs["query"] == SHARED_LOCATION_QUERY
        assert kwargs["file_name_filter"] == SHARED_LOCATION_FILE_NAME_FILTER
        fallback = _fallback_kwargs_from_intent(intent, company_name=company, spark=object())
        assert fallback["query"] == SHARED_LOCATION_QUERY
        assert fallback["file_name_filter"] == SHARED_LOCATION_FILE_NAME_FILTER


def test_clearsulting_people_and_org_is_not_overridden():
    live = _by_id()
    intent = live[PEOPLE_AND_ORG_INTENT_ID]
    resolved = apply_company_intent_overrides(intent, company_name="Clearsulting")
    assert resolved is intent
    assert resolved.query == intent.query


def test_clearsulting_q4_fallback_override_stays_intact():
    live = _by_id()
    intent = live[CS_Q4_FALLBACK_INTENT_ID]
    overridden = apply_company_intent_overrides(intent, company_name="Clearsulting")
    assert overridden.query == CS_Q4_FALLBACK_QUERY
    assert list(overridden.file_name_filter) == list(CS_Q4_FALLBACK_FILE_NAME_FILTER)


def test_build_search_kwargs_applies_cs_location_override():
    live = _by_id()
    intent = live[CS_LOCATION_INTENT_ID]
    kwargs = build_search_kwargs(intent, company_name="Clearsulting", spark=object())
    assert kwargs["query"] == CS_LOCATION_QUERY
    assert kwargs["file_name_filter"] == list(CS_LOCATION_FILE_NAME_FILTER)
    fallback = _fallback_kwargs_from_intent(
        intent, company_name="Clearsulting", spark=object()
    )
    assert fallback["query"] == CS_LOCATION_QUERY
    assert fallback["file_name_filter"] == list(CS_LOCATION_FILE_NAME_FILTER)


@patch("agents.shared.fallback.semantic_search_with_fallback")
@patch("agents.shared.retrieval.semantic_search")
def test_dispatch_cs_location_sends_override_query(mock_semantic, mock_fallback):
    mock_fallback.return_value = (MagicMock(chunks=[], mode="semantic"), False)
    live = _by_id()
    dispatch_retrieval(
        live[CS_LOCATION_INTENT_ID],
        company_name="Clearsulting",
        spark=MagicMock(),
    )
    assert mock_fallback.call_args.kwargs["query"] == CS_LOCATION_QUERY
    assert mock_fallback.call_args.kwargs["file_name_filter"] == list(
        CS_LOCATION_FILE_NAME_FILTER
    )
    mock_semantic.assert_not_called()


@patch("agents.shared.fallback.semantic_search_with_fallback")
@patch("agents.shared.retrieval.semantic_search")
def test_dispatch_gkf_location_sends_shared_healthcare_query(mock_semantic, mock_fallback):
    mock_fallback.return_value = (MagicMock(chunks=[], mode="semantic"), False)
    live = _by_id()
    dispatch_retrieval(
        live[CS_LOCATION_INTENT_ID],
        company_name="GKF",
        spark=MagicMock(),
    )
    assert mock_fallback.call_args.kwargs["query"] == SHARED_LOCATION_QUERY
    assert mock_fallback.call_args.kwargs["file_name_filter"] == SHARED_LOCATION_FILE_NAME_FILTER
    mock_semantic.assert_not_called()
