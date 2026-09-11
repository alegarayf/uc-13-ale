"""Elder Care-only leftover-zero overrides (cycle 36 / P2).

Shared BMA detect_cim / legal contracts registry strings stay
byte-identical (D11). Clearsulting / GKF / SPG keep those strings.
Elder Care gets CIM_vF section tokens + top_k raise, and
HIPAA / BAA / Non-Compete / Non-Disclosure / Jotform / dropbox.
CS q4, CS location, CS named-zero, CS leftover, and GKF location
branches stay intact.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from eval.retrieval.harness import (
    CS_ACCOUNT_SIZE_FILE_NAME_FILTER,
    CS_ACCOUNT_SIZE_INTENT_ID,
    CS_ACCOUNT_SIZE_QUERY,
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
    EC_CIM_PRESENCE_FILE_NAME_FILTER,
    EC_CIM_PRESENCE_INTENT_ID,
    EC_CIM_PRESENCE_QUERY,
    EC_CIM_PRESENCE_TOP_K,
    EC_CONTRACTS_FILE_NAME_FILTER,
    EC_CONTRACTS_INTENT_ID,
    EC_CONTRACTS_QUERY,
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

SHARED_CIM_QUERY = (
    "confidential information memorandum offering memorandum investment overview "
    "executive summary business overview financial highlights deal overview "
    "transaction overview management presentation"
)
SHARED_CIM_FILE_NAME_FILTER = [
    "CIM",
    "OM",
    "Offering",
    "Memorandum",
    "Investment",
    "Overview",
    "Presentation",
]
SHARED_CIM_WORKSTREAM_FILTER = ["BUSINESS_MODEL"]
SHARED_CIM_TOP_K = 3

SHARED_CONTRACTS_QUERY = (
    "material customer contract MSA master service agreement statement of work "
    "change of control termination vendor supplier platform reseller channel "
    "staffing agreement lease sublease asset purchase marketing contract"
)
SHARED_CONTRACTS_FILE_NAME_FILTER = [
    "Contract",
    "MSA",
    "Agreement",
    "SOW",
    "Customer",
    "Client",
    "Vendor",
    "Supplier",
    "SA",
    "Lease",
    "Sublease",
    "Staffing",
    "Purchase",
    "Temp",
    "Marketing",
    "Engagement",
]
SHARED_CONTRACTS_WORKSTREAM_FILTER = ["LEGAL"]

LEFTOVER_SPECS = (
    (
        EC_CIM_PRESENCE_INTENT_ID,
        SHARED_CIM_QUERY,
        SHARED_CIM_FILE_NAME_FILTER,
        SHARED_CIM_WORKSTREAM_FILTER,
        EC_CIM_PRESENCE_QUERY,
        EC_CIM_PRESENCE_FILE_NAME_FILTER,
        SHARED_CIM_WORKSTREAM_FILTER,
    ),
    (
        EC_CONTRACTS_INTENT_ID,
        SHARED_CONTRACTS_QUERY,
        SHARED_CONTRACTS_FILE_NAME_FILTER,
        SHARED_CONTRACTS_WORKSTREAM_FILTER,
        EC_CONTRACTS_QUERY,
        EC_CONTRACTS_FILE_NAME_FILTER,
        SHARED_CONTRACTS_WORKSTREAM_FILTER,
    ),
)
CIM_FORBIDDEN_ONLY_TOKENS = {"OM", "Offering", "Memorandum"}
CONTRACTS_FORBIDDEN_ONLY_TOKENS = {"Contract", "MSA", "SOW"}


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
        _ec_query,
        _ec_filter,
        _ec_ws,
    ) in LEFTOVER_SPECS:
        assert live[intent_id].query == shared_query
        assert committed[intent_id]["query"] == shared_query
        assert list(live[intent_id].workstream_filter) == shared_ws
        assert list(committed[intent_id]["workstream_filter"]) == shared_ws
        assert list(live[intent_id].file_name_filter) == shared_filter
        assert list(committed[intent_id]["file_name_filter"]) == shared_filter
    assert live[EC_CIM_PRESENCE_INTENT_ID].top_k == SHARED_CIM_TOP_K
    assert committed[EC_CIM_PRESENCE_INTENT_ID]["top_k"] == SHARED_CIM_TOP_K


def test_elder_care_leftovers_get_live_token_overrides():
    live = _by_id()
    for (
        intent_id,
        shared_query,
        shared_filter,
        shared_ws,
        ec_query,
        ec_filter,
        ec_ws,
    ) in LEFTOVER_SPECS:
        intent = live[intent_id]
        overridden = apply_company_intent_overrides(intent, company_name="Elder Care")
        assert overridden.query == ec_query
        assert list(overridden.file_name_filter) == list(ec_filter)
        assert list(overridden.workstream_filter) == list(ec_ws)
        assert intent.query == shared_query
        assert list(intent.workstream_filter) == shared_ws
        assert list(intent.file_name_filter) == shared_filter
    cim = apply_company_intent_overrides(
        live[EC_CIM_PRESENCE_INTENT_ID], company_name="Elder Care"
    )
    assert "Proposed Transaction Overview" in cim.query
    assert "Key Investment Considerations" in cim.query
    assert "CIM_vF" in cim.file_name_filter
    assert "CIM" in cim.file_name_filter
    assert cim.top_k == EC_CIM_PRESENCE_TOP_K
    assert cim.top_k > SHARED_CIM_TOP_K
    assert not CIM_FORBIDDEN_ONLY_TOKENS.issubset(set(cim.file_name_filter))
    assert CIM_FORBIDDEN_ONLY_TOKENS.isdisjoint(cim.file_name_filter)
    contracts = apply_company_intent_overrides(
        live[EC_CONTRACTS_INTENT_ID], company_name="Elder Care"
    )
    for token in (
        "HIPAA",
        "BAA",
        "Non-Compete",
        "Non-Disclosure",
        "Jotform",
        "dropbox",
    ):
        assert token in contracts.file_name_filter
        assert token in contracts.query or token.lower() in contracts.query.lower()
    assert CONTRACTS_FORBIDDEN_ONLY_TOKENS.isdisjoint(contracts.file_name_filter)
    assert list(contracts.workstream_filter) == SHARED_CONTRACTS_WORKSTREAM_FILTER


def test_clearsulting_gkf_spg_leftovers_keep_shared_registry_query():
    live = _by_id()
    for company in ("Clearsulting", "GKF", "SPG"):
        for (
            intent_id,
            shared_query,
            shared_filter,
            shared_ws,
            _ec_query,
            _ec_filter,
            _ec_ws,
        ) in LEFTOVER_SPECS:
            intent = live[intent_id]
            resolved = apply_company_intent_overrides(intent, company_name=company)
            assert resolved.query == shared_query
            assert resolved is intent
            assert list(resolved.workstream_filter) == shared_ws
            assert resolved.top_k == intent.top_k
            kwargs = build_search_kwargs(intent, company_name=company, spark=object())
            assert kwargs["query"] == shared_query
            assert kwargs["workstream_filter"] == shared_ws
            assert kwargs["file_name_filter"] == shared_filter
            assert kwargs["top_k"] == intent.top_k
            fallback = _fallback_kwargs_from_intent(
                intent, company_name=company, spark=object()
            )
            assert fallback["query"] == shared_query
            assert fallback["workstream_filter"] == shared_ws
            assert fallback["file_name_filter"] == shared_filter
            assert fallback["top_k"] == intent.top_k


def test_clearsulting_and_gkf_landed_overrides_stay_intact():
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
    acct = apply_company_intent_overrides(
        live[CS_ACCOUNT_SIZE_INTENT_ID], company_name="Clearsulting"
    )
    assert acct.query == CS_ACCOUNT_SIZE_QUERY
    assert list(acct.file_name_filter) == list(CS_ACCOUNT_SIZE_FILE_NAME_FILTER)
    dash = apply_company_intent_overrides(
        live[CS_KPI_DASHBOARD_INTENT_ID], company_name="Clearsulting"
    )
    assert dash.query == CS_KPI_DASHBOARD_QUERY
    assert list(dash.file_name_filter) == list(CS_KPI_DASHBOARD_FILE_NAME_FILTER)
    gkf = apply_company_intent_overrides(
        live[GKF_LOCATION_INTENT_ID], company_name="GKF"
    )
    assert gkf.query == GKF_LOCATION_QUERY
    assert list(gkf.file_name_filter) == list(GKF_LOCATION_FILE_NAME_FILTER)


def test_build_search_kwargs_applies_ec_leftover_overrides():
    live = _by_id()
    cim = live[EC_CIM_PRESENCE_INTENT_ID]
    kwargs = build_search_kwargs(cim, company_name="Elder Care", spark=object())
    assert kwargs["query"] == EC_CIM_PRESENCE_QUERY
    assert kwargs["file_name_filter"] == list(EC_CIM_PRESENCE_FILE_NAME_FILTER)
    assert kwargs["top_k"] == EC_CIM_PRESENCE_TOP_K
    fallback = _fallback_kwargs_from_intent(
        cim, company_name="Elder Care", spark=object()
    )
    assert fallback["query"] == EC_CIM_PRESENCE_QUERY
    assert fallback["file_name_filter"] == list(EC_CIM_PRESENCE_FILE_NAME_FILTER)
    assert fallback["top_k"] == EC_CIM_PRESENCE_TOP_K
    contracts = live[EC_CONTRACTS_INTENT_ID]
    kwargs = build_search_kwargs(contracts, company_name="Elder Care", spark=object())
    assert kwargs["query"] == EC_CONTRACTS_QUERY
    assert kwargs["file_name_filter"] == list(EC_CONTRACTS_FILE_NAME_FILTER)
    fallback = _fallback_kwargs_from_intent(
        contracts, company_name="Elder Care", spark=object()
    )
    assert fallback["query"] == EC_CONTRACTS_QUERY
    assert fallback["file_name_filter"] == list(EC_CONTRACTS_FILE_NAME_FILTER)


@patch("agents.shared.fallback.semantic_search_with_fallback")
@patch("agents.shared.retrieval.semantic_search")
def test_dispatch_ec_cim_sends_override_query(mock_semantic, mock_fallback):
    mock_fallback.return_value = (MagicMock(chunks=["hit"], mode="semantic"), False)
    live = _by_id()
    dispatch_retrieval(
        live[EC_CIM_PRESENCE_INTENT_ID],
        company_name="Elder Care",
        spark=MagicMock(),
    )
    assert mock_fallback.call_args.kwargs["query"] == EC_CIM_PRESENCE_QUERY
    assert mock_fallback.call_args.kwargs["file_name_filter"] == list(
        EC_CIM_PRESENCE_FILE_NAME_FILTER
    )
    assert mock_fallback.call_args.kwargs["top_k"] == EC_CIM_PRESENCE_TOP_K
    mock_semantic.assert_not_called()


@patch("agents.shared.fallback.semantic_search_with_fallback")
@patch("agents.shared.retrieval.semantic_search")
def test_dispatch_ec_contracts_sends_override_query(mock_semantic, mock_fallback):
    mock_fallback.return_value = (MagicMock(chunks=["hit"], mode="semantic"), False)
    live = _by_id()
    dispatch_retrieval(
        live[EC_CONTRACTS_INTENT_ID],
        company_name="Elder Care",
        spark=MagicMock(),
    )
    assert mock_fallback.call_args.kwargs["query"] == EC_CONTRACTS_QUERY
    assert mock_fallback.call_args.kwargs["file_name_filter"] == list(
        EC_CONTRACTS_FILE_NAME_FILTER
    )
    mock_semantic.assert_not_called()


@patch("agents.shared.fallback.semantic_search_with_fallback")
@patch("agents.shared.retrieval.semantic_search")
def test_dispatch_gkf_cim_keeps_shared_query(mock_semantic, mock_fallback):
    mock_fallback.return_value = (MagicMock(chunks=["hit"], mode="semantic"), False)
    live = _by_id()
    dispatch_retrieval(
        live[EC_CIM_PRESENCE_INTENT_ID],
        company_name="GKF",
        spark=MagicMock(),
    )
    assert mock_fallback.call_args.kwargs["query"] == SHARED_CIM_QUERY
    assert mock_fallback.call_args.kwargs["file_name_filter"] == SHARED_CIM_FILE_NAME_FILTER
    assert mock_fallback.call_args.kwargs["top_k"] == SHARED_CIM_TOP_K
    mock_semantic.assert_not_called()
