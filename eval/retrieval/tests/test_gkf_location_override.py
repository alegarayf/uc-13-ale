"""GKF-only location override (cycle 28 / Arm A).

Shared registry healthcare/org location query must stay byte-identical (D11).
Clearsulting keeps its Memorandum override; SPG keeps the shared string.
GKF gets the Ajax CIM corp-org / leadership / DMV neighborhood.
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
    GKF_LOCATION_FILE_NAME_FILTER,
    GKF_LOCATION_INTENT_ID,
    GKF_LOCATION_QUERY,
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


def _by_id():
    extractor = IntentRegistryExtractor(REPO_ROOT)
    return {intent.intent_id: intent for intent in extractor.extract()}


def _committed_by_id():
    rows = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    return {row["intent_id"]: row for row in rows}


def test_shared_location_registry_query_stays_healthcare_org_tail():
    live = _by_id()
    committed = _committed_by_id()
    assert live[GKF_LOCATION_INTENT_ID].query == SHARED_LOCATION_QUERY
    assert committed[GKF_LOCATION_INTENT_ID]["query"] == SHARED_LOCATION_QUERY
    assert list(live[GKF_LOCATION_INTENT_ID].file_name_filter) == SHARED_LOCATION_FILE_NAME_FILTER
    assert list(committed[GKF_LOCATION_INTENT_ID]["file_name_filter"]) == SHARED_LOCATION_FILE_NAME_FILTER
    assert "Ellicott City" in live[GKF_LOCATION_INTENT_ID].query
    assert "Shared Practices Dashboard" in live[GKF_LOCATION_INTENT_ID].query
    assert "Memorandum" not in live[GKF_LOCATION_INTENT_ID].file_name_filter


def test_gkf_location_gets_ajax_cim_override():
    live = _by_id()
    intent = live[GKF_LOCATION_INTENT_ID]
    overridden = apply_company_intent_overrides(intent, company_name="GKF")
    assert overridden.query == GKF_LOCATION_QUERY
    assert list(overridden.file_name_filter) == list(GKF_LOCATION_FILE_NAME_FILTER)
    assert "Memorandum" not in overridden.file_name_filter
    assert "Ellicott City" not in overridden.query
    assert "Shared Practices Dashboard" not in overridden.query
    assert "healthcare" not in overridden.query.lower()
    assert "Mike Pesi" in overridden.query
    assert "DMV" in overridden.query
    assert "Corporate Organization Current State" in overridden.query
    assert "CIM" in overridden.file_name_filter
    assert "Ajax" in overridden.file_name_filter
    assert "Rallyday" in overridden.file_name_filter
    assert intent.query == SHARED_LOCATION_QUERY
    assert list(intent.file_name_filter) == SHARED_LOCATION_FILE_NAME_FILTER


def test_clearsulting_and_spg_location_do_not_get_gkf_override():
    live = _by_id()
    intent = live[GKF_LOCATION_INTENT_ID]
    cs = apply_company_intent_overrides(intent, company_name="Clearsulting")
    assert cs.query == CS_LOCATION_QUERY
    assert list(cs.file_name_filter) == list(CS_LOCATION_FILE_NAME_FILTER)
    assert "Memorandum" in cs.file_name_filter
    assert cs.query != GKF_LOCATION_QUERY
    for company in ("SPG", "Elder Care"):
        resolved = apply_company_intent_overrides(intent, company_name=company)
        assert resolved.query == SHARED_LOCATION_QUERY
        assert resolved is intent


def test_gkf_does_not_mutate_cs_q4_fallback():
    live = _by_id()
    intent = live[CS_Q4_FALLBACK_INTENT_ID]
    gkf = apply_company_intent_overrides(intent, company_name="GKF")
    assert gkf is intent
    cs = apply_company_intent_overrides(intent, company_name="Clearsulting")
    assert cs.query == CS_Q4_FALLBACK_QUERY
    assert list(cs.file_name_filter) == list(CS_Q4_FALLBACK_FILE_NAME_FILTER)


def test_build_search_kwargs_applies_gkf_location_override():
    live = _by_id()
    intent = live[GKF_LOCATION_INTENT_ID]
    kwargs = build_search_kwargs(intent, company_name="GKF", spark=object())
    assert kwargs["query"] == GKF_LOCATION_QUERY
    assert kwargs["file_name_filter"] == list(GKF_LOCATION_FILE_NAME_FILTER)
    fallback = _fallback_kwargs_from_intent(intent, company_name="GKF", spark=object())
    assert fallback["query"] == GKF_LOCATION_QUERY
    assert fallback["file_name_filter"] == list(GKF_LOCATION_FILE_NAME_FILTER)


@patch("agents.shared.fallback.semantic_search_with_fallback")
@patch("agents.shared.retrieval.semantic_search")
def test_dispatch_gkf_location_sends_override_query(mock_semantic, mock_fallback):
    mock_fallback.return_value = (MagicMock(chunks=[], mode="semantic"), False)
    live = _by_id()
    dispatch_retrieval(
        live[GKF_LOCATION_INTENT_ID],
        company_name="GKF",
        spark=MagicMock(),
    )
    assert mock_fallback.call_args.kwargs["query"] == GKF_LOCATION_QUERY
    assert mock_fallback.call_args.kwargs["file_name_filter"] == list(
        GKF_LOCATION_FILE_NAME_FILTER
    )
    mock_semantic.assert_not_called()


@patch("agents.shared.fallback.semantic_search_with_fallback")
@patch("agents.shared.retrieval.semantic_search")
def test_dispatch_clearsulting_location_still_sends_memorandum(mock_semantic, mock_fallback):
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
