"""Clearsulting-only named-zero overrides (cycle 29 / P1).

Shared BMA visibility / FTA q5 / KPI bench registry strings stay
byte-identical (D11). GKF / SPG / Elder Care keep those strings.
Clearsulting gets Memorandum (visibility/q5) and Employee/Attrition (bench).
CS q4, CS location, and GKF location branches stay intact.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from eval.retrieval.harness import (
    CS_BENCH_FILE_NAME_FILTER,
    CS_BENCH_INTENT_ID,
    CS_BENCH_QUERY,
    CS_LOCATION_FILE_NAME_FILTER,
    CS_LOCATION_INTENT_ID,
    CS_LOCATION_QUERY,
    CS_Q4_FALLBACK_FILE_NAME_FILTER,
    CS_Q4_FALLBACK_INTENT_ID,
    CS_Q4_FALLBACK_QUERY,
    CS_Q5_FILE_NAME_FILTER,
    CS_Q5_INTENT_ID,
    CS_Q5_QUERY,
    CS_VISIBILITY_FILE_NAME_FILTER,
    CS_VISIBILITY_INTENT_ID,
    CS_VISIBILITY_QUERY,
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
REGISTRY_PATH = REPO_ROOT / "eval" / "retrieval" / "intent_registry.yaml"

SHARED_VISIBILITY_QUERY = (
    "Clear Strategic Roadmap of Growth Opportunities Project Ajax revenue target "
    "86.6 million 2030 24 schools historical projected revenue PF Adj EBITDA School "
    "Financial Performance BALANCE SHEET SUMMARY"
)
SHARED_VISIBILITY_FILE_NAME_FILTER = [
    "CIM",
    "Pipeline",
    "Backlog",
    "Contract",
    "Revenue",
    "KPI",
    "Metrics",
    "Overview",
    "Model",
]
SHARED_Q5_QUERY = (
    "total income total revenue net revenue gross revenue QuickBooks P&L annual "
    "income statement 2020 2021 2022 2023 revenue expenses total sales income from "
    "operations total operating revenue"
)
SHARED_Q5_FILE_NAME_FILTER = [
    "QuickBooks",
    "QBO",
    "2020",
    "2021",
    "2022",
    "2023",
    "2024",
    "P&L",
    "Income",
    "Profit",
    "Annual",
    "Financial",
]
SHARED_BENCH_QUERY = (
    "bench size bench cost unassigned headcount non-billable available capacity "
    "delivery capacity sales pipeline coverage capacity planning staffing plan "
    "billable vs non-billable overhead headcount average sales cycle pipeline "
    "conversion"
)
SHARED_BENCH_FILE_NAME_FILTER = [
    "Bench",
    "Capacity",
    "Staffing",
    "Pipeline",
    "Workforce",
    "Headcount",
    "KPI",
    "Operations",
    "GTM",
    "Sales",
]
NAMED_ZERO_SPECS = (
    (
        CS_VISIBILITY_INTENT_ID,
        SHARED_VISIBILITY_QUERY,
        SHARED_VISIBILITY_FILE_NAME_FILTER,
        CS_VISIBILITY_QUERY,
        CS_VISIBILITY_FILE_NAME_FILTER,
    ),
    (
        CS_Q5_INTENT_ID,
        SHARED_Q5_QUERY,
        SHARED_Q5_FILE_NAME_FILTER,
        CS_Q5_QUERY,
        CS_Q5_FILE_NAME_FILTER,
    ),
    (
        CS_BENCH_INTENT_ID,
        SHARED_BENCH_QUERY,
        SHARED_BENCH_FILE_NAME_FILTER,
        CS_BENCH_QUERY,
        CS_BENCH_FILE_NAME_FILTER,
    ),
)
FORBIDDEN_FILTER_TOKENS = {"CIM", "QuickBooks", "QBO", "P&L", "Pipeline"}


def _by_id():
    extractor = IntentRegistryExtractor(REPO_ROOT)
    return {intent.intent_id: intent for intent in extractor.extract()}


def _committed_by_id():
    rows = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    return {row["intent_id"]: row for row in rows}


def test_shared_named_zero_registry_queries_stay_byte_identical():
    live = _by_id()
    committed = _committed_by_id()
    for intent_id, shared_query, shared_filter, _cs_query, _cs_filter in NAMED_ZERO_SPECS:
        assert live[intent_id].query == shared_query
        assert committed[intent_id]["query"] == shared_query
        assert list(live[intent_id].file_name_filter) == shared_filter
        assert list(committed[intent_id]["file_name_filter"]) == shared_filter


def test_clearsulting_named_zeros_get_live_token_overrides():
    live = _by_id()
    for intent_id, shared_query, shared_filter, cs_query, cs_filter in NAMED_ZERO_SPECS:
        intent = live[intent_id]
        overridden = apply_company_intent_overrides(intent, company_name="Clearsulting")
        assert overridden.query == cs_query
        assert list(overridden.file_name_filter) == list(cs_filter)
        assert not FORBIDDEN_FILTER_TOKENS.intersection(overridden.file_name_filter)
        assert intent.query == shared_query
        assert list(intent.file_name_filter) == shared_filter
    vis = apply_company_intent_overrides(
        live[CS_VISIBILITY_INTENT_ID], company_name="Clearsulting"
    )
    assert "Memorandum" in vis.file_name_filter
    q5 = apply_company_intent_overrides(live[CS_Q5_INTENT_ID], company_name="Clearsulting")
    assert "Memorandum" in q5.file_name_filter
    assert "Financial" in q5.file_name_filter
    bench = apply_company_intent_overrides(
        live[CS_BENCH_INTENT_ID], company_name="Clearsulting"
    )
    assert "Employee" in bench.file_name_filter
    assert "Attrition" in bench.file_name_filter


def test_gkf_spg_elder_care_named_zeros_keep_shared_registry_query():
    live = _by_id()
    for company in ("GKF", "SPG", "Elder Care"):
        for intent_id, shared_query, shared_filter, _cs_query, _cs_filter in NAMED_ZERO_SPECS:
            intent = live[intent_id]
            resolved = apply_company_intent_overrides(intent, company_name=company)
            assert resolved.query == shared_query
            assert resolved is intent
            kwargs = build_search_kwargs(intent, company_name=company, spark=object())
            assert kwargs["query"] == shared_query
            assert kwargs["file_name_filter"] == shared_filter
            fallback = _fallback_kwargs_from_intent(
                intent, company_name=company, spark=object()
            )
            assert fallback["query"] == shared_query
            assert fallback["file_name_filter"] == shared_filter


def test_clearsulting_q4_and_location_overrides_stay_intact():
    live = _by_id()
    q4 = apply_company_intent_overrides(
        live[CS_Q4_FALLBACK_INTENT_ID], company_name="Clearsulting"
    )
    assert q4.query == CS_Q4_FALLBACK_QUERY
    assert list(q4.file_name_filter) == list(CS_Q4_FALLBACK_FILE_NAME_FILTER)
    loc = apply_company_intent_overrides(
        live[CS_LOCATION_INTENT_ID], company_name="Clearsulting"
    )
    assert loc.query == CS_LOCATION_QUERY
    assert list(loc.file_name_filter) == list(CS_LOCATION_FILE_NAME_FILTER)


def test_gkf_location_override_stays_intact():
    live = _by_id()
    gkf = apply_company_intent_overrides(
        live[GKF_LOCATION_INTENT_ID], company_name="GKF"
    )
    assert gkf.query == GKF_LOCATION_QUERY
    assert list(gkf.file_name_filter) == list(GKF_LOCATION_FILE_NAME_FILTER)
    cs = apply_company_intent_overrides(
        live[GKF_LOCATION_INTENT_ID], company_name="Clearsulting"
    )
    assert cs.query == CS_LOCATION_QUERY
    assert cs.query != GKF_LOCATION_QUERY


def test_build_search_kwargs_applies_cs_named_zero_overrides():
    live = _by_id()
    for intent_id, _shared_query, _shared_filter, cs_query, cs_filter in NAMED_ZERO_SPECS:
        intent = live[intent_id]
        kwargs = build_search_kwargs(intent, company_name="Clearsulting", spark=object())
        assert kwargs["query"] == cs_query
        assert kwargs["file_name_filter"] == list(cs_filter)
        fallback = _fallback_kwargs_from_intent(
            intent, company_name="Clearsulting", spark=object()
        )
        assert fallback["query"] == cs_query
        assert fallback["file_name_filter"] == list(cs_filter)


@patch("agents.shared.fallback.semantic_search_with_fallback")
@patch("agents.shared.retrieval.semantic_search")
def test_dispatch_cs_named_zeros_sends_override_queries(mock_semantic, mock_fallback):
    mock_fallback.return_value = (MagicMock(chunks=[], mode="semantic"), False)
    live = _by_id()
    for intent_id, _shared_query, _shared_filter, cs_query, cs_filter in NAMED_ZERO_SPECS:
        mock_fallback.reset_mock()
        mock_semantic.reset_mock()
        dispatch_retrieval(
            live[intent_id],
            company_name="Clearsulting",
            spark=MagicMock(),
        )
        assert mock_fallback.call_args.kwargs["query"] == cs_query
        assert mock_fallback.call_args.kwargs["file_name_filter"] == list(cs_filter)
        mock_semantic.assert_not_called()


@patch("agents.shared.fallback.semantic_search_with_fallback")
@patch("agents.shared.retrieval.semantic_search")
def test_dispatch_gkf_visibility_keeps_shared_ajax_query(mock_semantic, mock_fallback):
    mock_fallback.return_value = (MagicMock(chunks=[], mode="semantic"), False)
    live = _by_id()
    dispatch_retrieval(
        live[CS_VISIBILITY_INTENT_ID],
        company_name="GKF",
        spark=MagicMock(),
    )
    assert mock_fallback.call_args.kwargs["query"] == SHARED_VISIBILITY_QUERY
    assert mock_fallback.call_args.kwargs["file_name_filter"] == SHARED_VISIBILITY_FILE_NAME_FILTER
    mock_semantic.assert_not_called()
