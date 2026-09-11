"""Clearsulting-only leftover-zero overrides (cycle 30 / P1).

Shared CQA account_size / KPI dashboard registry strings stay
byte-identical (D11). GKF / SPG / Elder Care keep those strings.
Clearsulting gets Memorandum + BUSINESS_MODEL (account_size) and
Organizational / Chart (kpi_dashboard).
CS q4, CS location, CS named-zero, and GKF location branches stay intact.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from eval.retrieval.harness import (
    CS_ACCOUNT_SIZE_FILE_NAME_FILTER,
    CS_ACCOUNT_SIZE_INTENT_ID,
    CS_ACCOUNT_SIZE_QUERY,
    CS_ACCOUNT_SIZE_WORKSTREAM_FILTER,
    CS_BENCH_FILE_NAME_FILTER,
    CS_BENCH_INTENT_ID,
    CS_BENCH_QUERY,
    CS_KPI_DASHBOARD_FILE_NAME_FILTER,
    CS_KPI_DASHBOARD_INTENT_ID,
    CS_KPI_DASHBOARD_QUERY,
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

SHARED_ACCOUNT_SIZE_QUERY = (
    "average account size ACV annual contract value revenue per customer SMB enterprise"
)
SHARED_ACCOUNT_SIZE_WORKSTREAM_FILTER = [
    "CUSTOMER",
    "KPI_OPS",
    "FINANCIAL",
    "QUALITY_EARNINGS",
]
SHARED_KPI_DASHBOARD_QUERY = (
    "GL KPI spreadsheet internal intranet utilization revenue per FTE headcount operating"
)
SHARED_KPI_DASHBOARD_FILE_NAME_FILTER = [
    "KPI",
    "Dashboard",
    "Metrics",
    "Scorecard",
    "Operating",
    "Performance",
]
SHARED_KPI_DASHBOARD_WORKSTREAM_FILTER = ["KPI_OPS"]

LEFTOVER_SPECS = (
    (
        CS_ACCOUNT_SIZE_INTENT_ID,
        SHARED_ACCOUNT_SIZE_QUERY,
        None,
        SHARED_ACCOUNT_SIZE_WORKSTREAM_FILTER,
        CS_ACCOUNT_SIZE_QUERY,
        CS_ACCOUNT_SIZE_FILE_NAME_FILTER,
        CS_ACCOUNT_SIZE_WORKSTREAM_FILTER,
    ),
    (
        CS_KPI_DASHBOARD_INTENT_ID,
        SHARED_KPI_DASHBOARD_QUERY,
        SHARED_KPI_DASHBOARD_FILE_NAME_FILTER,
        SHARED_KPI_DASHBOARD_WORKSTREAM_FILTER,
        CS_KPI_DASHBOARD_QUERY,
        CS_KPI_DASHBOARD_FILE_NAME_FILTER,
        SHARED_KPI_DASHBOARD_WORKSTREAM_FILTER,
    ),
)
ACCOUNT_SIZE_FORBIDDEN_FILTER_TOKENS = {"CIM", "Revenue", "ACV", "Account"}
KPI_DASHBOARD_FORBIDDEN_FILTER_TOKENS = {"KPI", "Dashboard", "Utilization"}


def _by_id():
    extractor = IntentRegistryExtractor(REPO_ROOT)
    return {intent.intent_id: intent for intent in extractor.extract()}


def _committed_by_id():
    rows = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    return {row["intent_id"]: row for row in rows}


def test_shared_leftover_registry_queries_stay_byte_identical():
    live = _by_id()
    committed = _committed_by_id()
    for (
        intent_id,
        shared_query,
        shared_filter,
        shared_ws,
        _cs_query,
        _cs_filter,
        _cs_ws,
    ) in LEFTOVER_SPECS:
        assert live[intent_id].query == shared_query
        assert committed[intent_id]["query"] == shared_query
        assert list(live[intent_id].workstream_filter) == shared_ws
        assert list(committed[intent_id]["workstream_filter"]) == shared_ws
        if shared_filter is None:
            assert live[intent_id].file_name_filter is None
            assert committed[intent_id].get("file_name_filter") is None
        else:
            assert list(live[intent_id].file_name_filter) == shared_filter
            assert list(committed[intent_id]["file_name_filter"]) == shared_filter


def test_clearsulting_leftovers_get_live_token_overrides():
    live = _by_id()
    for (
        intent_id,
        shared_query,
        shared_filter,
        shared_ws,
        cs_query,
        cs_filter,
        cs_ws,
    ) in LEFTOVER_SPECS:
        intent = live[intent_id]
        overridden = apply_company_intent_overrides(intent, company_name="Clearsulting")
        assert overridden.query == cs_query
        assert list(overridden.file_name_filter) == list(cs_filter)
        assert list(overridden.workstream_filter) == list(cs_ws)
        assert intent.query == shared_query
        assert list(intent.workstream_filter) == shared_ws
        if shared_filter is None:
            assert intent.file_name_filter is None
        else:
            assert list(intent.file_name_filter) == shared_filter
    acct = apply_company_intent_overrides(
        live[CS_ACCOUNT_SIZE_INTENT_ID], company_name="Clearsulting"
    )
    assert "Memorandum" in acct.file_name_filter
    assert "BUSINESS_MODEL" in acct.workstream_filter
    assert not ACCOUNT_SIZE_FORBIDDEN_FILTER_TOKENS.intersection(acct.file_name_filter)
    dash = apply_company_intent_overrides(
        live[CS_KPI_DASHBOARD_INTENT_ID], company_name="Clearsulting"
    )
    assert "Organizational" in dash.file_name_filter
    assert "Chart" in dash.file_name_filter
    assert not KPI_DASHBOARD_FORBIDDEN_FILTER_TOKENS.intersection(dash.file_name_filter)


def test_gkf_spg_elder_care_leftovers_keep_shared_registry_query():
    live = _by_id()
    for company in ("GKF", "SPG", "Elder Care"):
        for (
            intent_id,
            shared_query,
            shared_filter,
            shared_ws,
            _cs_query,
            _cs_filter,
            _cs_ws,
        ) in LEFTOVER_SPECS:
            intent = live[intent_id]
            resolved = apply_company_intent_overrides(intent, company_name=company)
            assert resolved.query == shared_query
            assert resolved is intent
            assert list(resolved.workstream_filter) == shared_ws
            kwargs = build_search_kwargs(intent, company_name=company, spark=object())
            assert kwargs["query"] == shared_query
            assert kwargs["workstream_filter"] == shared_ws
            if shared_filter is None:
                assert kwargs["file_name_filter"] is None
            else:
                assert kwargs["file_name_filter"] == shared_filter
            fallback = _fallback_kwargs_from_intent(
                intent, company_name=company, spark=object()
            )
            assert fallback["query"] == shared_query
            assert fallback["workstream_filter"] == shared_ws
            if shared_filter is None:
                assert fallback["file_name_filter"] is None
            else:
                assert fallback["file_name_filter"] == shared_filter


def test_clearsulting_q4_location_and_named_zero_overrides_stay_intact():
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
    vis = apply_company_intent_overrides(
        live[CS_VISIBILITY_INTENT_ID], company_name="Clearsulting"
    )
    assert vis.query == CS_VISIBILITY_QUERY
    assert list(vis.file_name_filter) == list(CS_VISIBILITY_FILE_NAME_FILTER)
    q5 = apply_company_intent_overrides(live[CS_Q5_INTENT_ID], company_name="Clearsulting")
    assert q5.query == CS_Q5_QUERY
    assert list(q5.file_name_filter) == list(CS_Q5_FILE_NAME_FILTER)
    bench = apply_company_intent_overrides(
        live[CS_BENCH_INTENT_ID], company_name="Clearsulting"
    )
    assert bench.query == CS_BENCH_QUERY
    assert list(bench.file_name_filter) == list(CS_BENCH_FILE_NAME_FILTER)


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


def test_build_search_kwargs_applies_cs_leftover_overrides():
    live = _by_id()
    for (
        intent_id,
        _shared_query,
        _shared_filter,
        _shared_ws,
        cs_query,
        cs_filter,
        cs_ws,
    ) in LEFTOVER_SPECS:
        intent = live[intent_id]
        kwargs = build_search_kwargs(intent, company_name="Clearsulting", spark=object())
        assert kwargs["query"] == cs_query
        assert kwargs["file_name_filter"] == list(cs_filter)
        assert kwargs["workstream_filter"] == list(cs_ws)
        fallback = _fallback_kwargs_from_intent(
            intent, company_name="Clearsulting", spark=object()
        )
        assert fallback["query"] == cs_query
        assert fallback["file_name_filter"] == list(cs_filter)
        assert fallback["workstream_filter"] == list(cs_ws)


@patch("agents.shared.fallback.semantic_search_with_fallback")
@patch("agents.shared.retrieval.semantic_search")
def test_dispatch_cs_account_size_sends_override_query(mock_semantic, mock_fallback):
    mock_semantic.return_value = MagicMock(chunks=["hit"], mode="semantic")
    live = _by_id()
    dispatch_retrieval(
        live[CS_ACCOUNT_SIZE_INTENT_ID],
        company_name="Clearsulting",
        spark=MagicMock(),
    )
    assert mock_semantic.call_args.kwargs["query"] == CS_ACCOUNT_SIZE_QUERY
    assert mock_semantic.call_args.kwargs["file_name_filter"] == list(
        CS_ACCOUNT_SIZE_FILE_NAME_FILTER
    )
    assert mock_semantic.call_args.kwargs["workstream_filter"] == list(
        CS_ACCOUNT_SIZE_WORKSTREAM_FILTER
    )
    mock_fallback.assert_not_called()


@patch("agents.shared.fallback.semantic_search_with_fallback")
@patch("agents.shared.retrieval.semantic_search")
def test_dispatch_cs_kpi_dashboard_sends_override_query(mock_semantic, mock_fallback):
    mock_fallback.return_value = (MagicMock(chunks=[], mode="semantic"), False)
    live = _by_id()
    dispatch_retrieval(
        live[CS_KPI_DASHBOARD_INTENT_ID],
        company_name="Clearsulting",
        spark=MagicMock(),
    )
    assert mock_fallback.call_args.kwargs["query"] == CS_KPI_DASHBOARD_QUERY
    assert mock_fallback.call_args.kwargs["file_name_filter"] == list(
        CS_KPI_DASHBOARD_FILE_NAME_FILTER
    )
    mock_semantic.assert_not_called()


@patch("agents.shared.fallback.semantic_search_with_fallback")
@patch("agents.shared.retrieval.semantic_search")
def test_dispatch_gkf_account_size_keeps_shared_query(mock_semantic, mock_fallback):
    mock_semantic.return_value = MagicMock(chunks=["hit"], mode="semantic")
    live = _by_id()
    dispatch_retrieval(
        live[CS_ACCOUNT_SIZE_INTENT_ID],
        company_name="GKF",
        spark=MagicMock(),
    )
    assert mock_semantic.call_args.kwargs["query"] == SHARED_ACCOUNT_SIZE_QUERY
    assert mock_semantic.call_args.kwargs["file_name_filter"] is None
    assert mock_semantic.call_args.kwargs["workstream_filter"] == (
        SHARED_ACCOUNT_SIZE_WORKSTREAM_FILTER
    )
    mock_fallback.assert_not_called()
