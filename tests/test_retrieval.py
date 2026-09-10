"""Unit tests for retrieval.py merge rank, score extraction, and SQL escaping."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

# M-RE2 T3: semantic_search lazy-imports eval.retrieval.provenance on every
# return path (no-op when no agent run is open), so the repo root must be
# importable for the existing suite as well as the provenance tests below.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Stub Databricks SDK / MLflow before importing retrieval.py.
if "databricks" not in sys.modules:
    databricks_mod = types.ModuleType("databricks")
    sdk_mod = types.ModuleType("databricks.sdk")
    sdk_mod.WorkspaceClient = MagicMock
    databricks_mod.sdk = sdk_mod
    sys.modules["databricks"] = databricks_mod
    sys.modules["databricks.sdk"] = sdk_mod

if "mlflow" not in sys.modules:
    mlflow_mod = types.ModuleType("mlflow")
    deployments_mod = types.ModuleType("mlflow.deployments")
    deployments_mod.get_deploy_client = MagicMock
    mlflow_mod.deployments = deployments_mod
    sys.modules["mlflow"] = mlflow_mod
    sys.modules["mlflow.deployments"] = deployments_mod

from agents.shared.retrieval import (  # noqa: E402
    _DASHBOARD_SECTION_BONUS,
    _SECTION_TIEBREAK_BONUS,
    _TIER_BONUS,
    _build_vs_filters_dict,
    _default_catalog,
    _escape_sql_literal,
    _extract_score_map,
    _hydrate_chunks_sql,
    _index_name_for_catalog,
    _keyword_fallback_sql,
    _merge_score,
    _query_vector_index,
    _section_tiebreak,
    _sort_by_merge_rank,
    _sort_by_sim_only,
    _sort_by_tier_only,
    _tier_weight,
    semantic_search,
)
from agents.shared._types import RouteResult  # noqa: E402
from agents.shared.run_context import (  # noqa: E402
    RunContextError,
    close_agent_run,
    open_agent_run,
    set_pipeline_thread,
)
from eval.retrieval.provenance import ProvenanceEmitter  # noqa: E402
from eval.retrieval.store import SqliteEvalStore  # noqa: E402


def _row(
    *,
    chunk_id: str,
    priority_tier: int = 2,
    source_type: str = "text",
    section_header: str = "Revenue",
    chunk_text: str | None = None,
    file_name: str | None = None,
):
    return SimpleNamespace(
        chunk_id=chunk_id,
        file_name=file_name if file_name is not None else f"{chunk_id}.pdf",
        chunk_text=("A" * 120) if chunk_text is None else chunk_text,
        section_header=section_header,
        page_start=1,
        source_type=source_type,
        workstream=["FINANCIAL"],
        priority_tier=priority_tier,
    )


def test_escape_sql_literal_doubles_single_quotes():
    assert _escape_sql_literal("O'Brien") == "O''Brien"


def test_index_name_for_catalog():
    assert _index_name_for_catalog("uc13_ale") == "uc13_ale.ingestion.embeddings_index"


def test_default_catalog_reads_env(monkeypatch):
    monkeypatch.setenv("catalog", "uc13_ale")
    assert _default_catalog() == "uc13_ale"
    monkeypatch.delenv("catalog")
    assert _default_catalog() == "uc13"


def test_extract_score_map_uses_trailing_score_column():
    data_array = [
        ["c1", "d1", "f1.pdf", 0.92],
        ["c2", "d2", "f2.pdf", 0.41],
    ]
    assert _extract_score_map(data_array) == {"c1": 0.92, "c2": 0.41}


def test_tier_weight_defaults_for_none_and_unknown():
    assert _tier_weight(None) == 0.3
    assert _tier_weight(99) == 0.3
    assert _tier_weight(1) == 1.0


def test_merge_rank_prefers_strong_semantic_match_over_weak_tier_one():
    chunks = [_row(chunk_id="weak_t1", priority_tier=1), _row(chunk_id="strong_t3", priority_tier=3)]
    score_map = {"weak_t1": 0.3, "strong_t3": 0.95}
    ranked = _sort_by_merge_rank(chunks, score_map)
    # 0.95 + 0.05*0.4 = 0.97 beats 0.3 + 0.05*1.0 = 0.35
    assert [c.chunk_id for c in ranked] == ["strong_t3", "weak_t1"]


def test_merge_rank_keeps_highest_sim_tier2_ahead_of_near_neighbor_tier1():
    """Elder Care F1: citation_backfill gold can be the best VS hit (CIM vision,
    tier 2) but sit below top_k after multiplicative sim×tier against slightly
    weaker tier-1 spreadsheet neighbors.

    Live probe on fta.opex.q3_projected_financials (uc13_ale, Elder Care):
    gold 2d238ee0 sim=0.691 / tier=2 ranked 19 of 23 after sim×tier; top_k=8.
    """
    gold = _row(chunk_id="gold_cim", priority_tier=2, source_type="vision")
    neighbors = [
        _row(chunk_id=f"t1_{i}", priority_tier=1, source_type="text")
        for i in range(8)
    ]
    score_map = {"gold_cim": 0.6910852}
    for i in range(8):
        score_map[f"t1_{i}"] = 0.6583611 - i * 0.001
    ranked = _sort_by_merge_rank([*neighbors, gold], score_map)
    top8 = [c.chunk_id for c in ranked[:8]]
    assert "gold_cim" in top8
    assert ranked[0].chunk_id == "gold_cim"
    assert _merge_score(gold, score_map) == pytest.approx(
        0.6910852 + _TIER_BONUS * _tier_weight(2)
    )


def test_merge_rank_falls_back_to_tier_when_no_scores():
    chunks = [_row(chunk_id="b", priority_tier=2), _row(chunk_id="a", priority_tier=1)]
    ranked = _sort_by_merge_rank(chunks, {})
    assert [c.chunk_id for c in ranked] == ["a", "b"]


def test_section_tiebreak_promotes_near_tied_service_overview_over_growth():
    """Clearsulting P2: gold Kyriba (vision, headed as a client but body is
    Core Services) and Other Service Lines sit 0.001–0.003 below the rank-10
    Overview of Growth Opportunity cutoff. ``_TYPE_ORDER`` cannot help
    (vision vs vision; text would lose). A 0.004 current-state bonus must
    lift both into eval_k=10 without inverting a 0.03 sim lead.
    """
    growth_cutoff = _row(
        chunk_id="31b3d603",
        priority_tier=1,
        source_type="vision",
        section_header="Overview of Growth Opportunity",
        chunk_text="Growth Opportunities: Account Ownership | SAP Partnership | Geo. Expansion",
    )
    kyriba = _row(
        chunk_id="7b76f634",
        priority_tier=1,
        source_type="vision",
        section_header="Kyriba",
        chunk_text="# Core Services\n**1 - Financial Close** FY24 Revenue: $26M",
    )
    osl = _row(
        chunk_id="ce839bfb",
        priority_tier=1,
        source_type="text",
        section_header="Other Service Lines",
        chunk_text="Clearsulting services focus on business process first",
    )
    neighbors = [
        _row(
            chunk_id=f"growth_{i}",
            priority_tier=1,
            source_type="vision",
            section_header="Overview of Growth Opportunity",
            chunk_text="Growth Opportunities: Account Ownership | SAP Partnership",
        )
        for i in range(8)
    ]
    # Live pin band: cutoff sim 0.5999, Kyriba 0.5988, OSL 0.5974 (all tier 1).
    score_map = {
        "31b3d603": 0.5998854,
        "7b76f634": 0.598755,
        "ce839bfb": 0.5973552,
    }
    for i, n in enumerate(neighbors):
        score_map[n.chunk_id] = 0.61234723 - i * 0.0015
    ranked = _sort_by_merge_rank([*neighbors, growth_cutoff, kyriba, osl], score_map)
    top10 = [c.chunk_id for c in ranked[:10]]
    assert "7b76f634" in top10
    assert "ce839bfb" in top10
    assert _section_tiebreak(kyriba) == _SECTION_TIEBREAK_BONUS
    assert _section_tiebreak(osl) == _SECTION_TIEBREAK_BONUS
    assert _section_tiebreak(growth_cutoff) == 0.0
    # Bonus is smaller than the 0.03 sim-lead floor.
    assert _SECTION_TIEBREAK_BONUS < 0.03
    assert _SECTION_TIEBREAK_BONUS > 0.0026


def test_section_tiebreak_does_not_invert_003_similarity_lead():
    """Merge-decisions: a section bump must not invert a ≥~0.03 sim lead."""
    growth_lead = _row(
        chunk_id="growth_lead",
        priority_tier=1,
        source_type="vision",
        section_header="Overview of Growth Opportunity",
        chunk_text="Growth Opportunities: Account Ownership",
    )
    services = _row(
        chunk_id="services",
        priority_tier=1,
        source_type="text",
        section_header="Other Service Lines",
        chunk_text="# Core Services",
    )
    score_map = {"growth_lead": 0.63, "services": 0.60}
    ranked = _sort_by_merge_rank([services, growth_lead], score_map)
    assert [c.chunk_id for c in ranked] == ["growth_lead", "services"]


def test_dashboard_section_tiebreak_promotes_gold_across_0006_gap():
    """SPG F1: gold 84311b20 sits ~0.006 below rank-10. CS/GKF 0.004 is too
    small; a 0.010 dashboard-specific bonus must land it in top-10. A 0.004
    bump would leave it at ranks 11–14.
    """
    gold = _row(
        chunk_id="84311b20",
        priority_tier=2,
        source_type="text",
        section_header="new patient visits distribution",
        chunk_text="Shared Practices Dashboard new patient visits distribution",
        file_name="Shared Practices Dashboard.xlsx",
    )
    neighbors = [
        _row(
            chunk_id=f"assets_{i}",
            priority_tier=2,
            source_type="table",
            section_header="Assets",
            chunk_text="Projection Model PL database — Summary",
            file_name="Financial Statement.xlsx",
        )
        for i in range(10)
    ]
    # Live estimate: gold merge ~0.6544 vs rank-10 cutoff ~0.6608 (gap 0.006).
    score_map = {"84311b20": 0.6544}
    for i, n in enumerate(neighbors):
        score_map[n.chunk_id] = 0.6717 - i * 0.0012  # rank-10 ≈ 0.6609
    ranked = _sort_by_merge_rank([*neighbors, gold], score_map)
    top10 = [c.chunk_id for c in ranked[:10]]
    assert "84311b20" in top10
    assert _section_tiebreak(gold) == pytest.approx(_DASHBOARD_SECTION_BONUS)
    assert _DASHBOARD_SECTION_BONUS == pytest.approx(0.010)
    assert _DASHBOARD_SECTION_BONUS < 0.03
    # 0.004 would not close a 0.006 gap against the rank-10 cutoff.
    gold_with_cs_only = 0.6544 + _SECTION_TIEBREAK_BONUS
    rank10_sim = min(score_map[n.chunk_id] for n in neighbors)
    assert gold_with_cs_only < rank10_sim
    assert 0.6544 + _DASHBOARD_SECTION_BONUS > rank10_sim


def test_section_tiebreaks_are_independent_and_company_specific():
    """New regexes must not fire on each other's (or CS's) language."""
    kyriba = _row(
        chunk_id="7b76f634",
        priority_tier=1,
        source_type="vision",
        section_header="Kyriba",
        chunk_text="# Core Services\n**1 - Financial Close** FY24 Revenue: $26M",
    )
    osl = _row(
        chunk_id="ce839bfb",
        priority_tier=1,
        source_type="text",
        section_header="Other Service Lines",
        chunk_text="Clearsulting services focus on business process first",
    )
    dashboard = _row(
        chunk_id="spg_dash",
        section_header="new patient visits distribution",
        chunk_text="network visits by location",
        file_name="Shared Practices Dashboard.xlsx",
    )
    generic_visits = _row(
        chunk_id="generic_visits",
        section_header="Patient visits",
        chunk_text="visits and network volume",
    )
    assert _section_tiebreak(kyriba) == pytest.approx(_SECTION_TIEBREAK_BONUS)
    assert _section_tiebreak(osl) == pytest.approx(_SECTION_TIEBREAK_BONUS)
    assert _section_tiebreak(dashboard) == pytest.approx(_DASHBOARD_SECTION_BONUS)
    assert _section_tiebreak(generic_visits) == 0.0


def test_dashboard_bonus_does_not_invert_003_similarity_lead():
    """SPG's larger 0.010 bump is still below the 0.03 sim-lead floor."""
    lead = _row(
        chunk_id="assets_lead",
        priority_tier=2,
        section_header="Assets",
        chunk_text="Projection Model",
    )
    dashboard = _row(
        chunk_id="84311b20",
        priority_tier=2,
        section_header="new patient visits distribution",
        chunk_text="Shared Practices Dashboard",
    )
    score_map = {"assets_lead": 0.63, "84311b20": 0.60}
    ranked = _sort_by_merge_rank([dashboard, lead], score_map)
    assert [c.chunk_id for c in ranked] == ["assets_lead", "84311b20"]


def test_overview_regex_skips_growth_levers_body_only():
    """CS F1: body-only 'Complementary Service Lines' on Growth Levers must
    not take the 0.004 bonus. Kyriba ``# Core Services`` and Other Service
    Lines ``section_header`` must still fire. Do not weaken the existing
    overview near-tie test.
    """
    growth_levers = _row(
        chunk_id="db736e70",
        priority_tier=1,
        source_type="vision",
        section_header="Growth Levers",
        chunk_text=(
            "# Growth Levers (Left Column)\n"
            "Account Farming | Land & Expand | Strategic Partnerships\n"
            "Evolving Technologies | Cost Efficiencies | Complementary Service Lines\n"
            "Value-at-Risk Contracts | AMS New Venture | Digital Asset Revenue\n"
        ),
    )
    kyriba = _row(
        chunk_id="7b76f634",
        priority_tier=1,
        source_type="vision",
        section_header="Kyriba",
        chunk_text="# Core Services\n**1 - Financial Close** FY24 Revenue: $26M",
    )
    osl = _row(
        chunk_id="ce839bfb",
        priority_tier=1,
        source_type="text",
        section_header="Other Service Lines",
        chunk_text="Clearsulting services focus on business process first",
    )
    assert _section_tiebreak(growth_levers) == 0.0
    assert _section_tiebreak(kyriba) == _SECTION_TIEBREAK_BONUS
    assert _section_tiebreak(osl) == _SECTION_TIEBREAK_BONUS


def test_overview_scope_returns_model_changes_gold_to_eval_k():
    """CS F1 live band: Growth Levers raw sim 0.64120 + 0.004 sat at rank 8
    and evicted gold f044f447 (0.64321) to rank 11. After scoping, gold
    must sit at rank ≤10 and Growth Levers must not keep the bonus.
    """
    growth_levers = _row(
        chunk_id="db736e70",
        priority_tier=1,
        source_type="vision",
        section_header="Growth Levers",
        chunk_text=(
            "# Growth Levers (Left Column)\n"
            "Evolving Technologies | Cost Efficiencies | Complementary Service Lines\n"
        ),
    )
    gold = _row(
        chunk_id="f044f447",
        priority_tier=1,
        source_type="vision",
        section_header="Shift Towards Fixed-Fee + Hybrid Models (% of Total Revenue)(1)",
        chunk_text="Notable Expansion in Fixed-Fee Models.",
    )
    neighbors = [
        _row(
            chunk_id=f"nb_{i}",
            priority_tier=1,
            source_type="vision",
            section_header="Key Drivers & Opportunities:",
            chunk_text="Account Ownership | SAP Partnership",
        )
        for i in range(7)
    ]
    overview = _row(
        chunk_id="4e680732",
        priority_tier=1,
        section_header="Overview",
        chunk_text="Situation overview without service-line heading",
    )
    offerings = _row(
        chunk_id="5c225664",
        priority_tier=1,
        section_header="Offerings",
        chunk_text="Offerings slide without a service-line heading",
    )
    score_map = {
        "db736e70": 0.64120363,
        "f044f447": 0.64320515,
        "4e680732": 0.64418360,
        "5c225664": 0.64386927,
    }
    for i, n in enumerate(neighbors):
        score_map[n.chunk_id] = 0.6585744 - i * 0.0015
    ranked = _sort_by_merge_rank(
        [*neighbors, overview, offerings, growth_levers, gold], score_map
    )
    top10 = [c.chunk_id for c in ranked[:10]]
    assert "f044f447" in top10
    assert _section_tiebreak(growth_levers) == 0.0
    assert ranked.index(gold) < ranked.index(growth_levers)


def test_hydrate_sql_escapes_company_name_and_has_no_order_by():
    sql = _hydrate_chunks_sql(["c1"], "Acme's Corp", "uc13_ale")
    assert "ORDER BY" not in sql.upper()
    assert "Acme''s Corp" in sql
    assert "c.chunk_id IN ('c1')" in sql
    assert "uc13_ale.ingestion.chunks" in sql
    assert "uc13_ale.classification.doc_relevance" in sql


def test_keyword_fallback_sql_escapes_keywords():
    sql = _keyword_fallback_sql(["rev'enue"], "Co", 30, "uc13_ale")
    assert "rev''enue" in sql
    assert "LIMIT 30" in sql
    assert "uc13_ale.ingestion.chunks" in sql


def test_query_vector_index_retries_without_filters_on_sdk_error():
    w = MagicMock()
    w.vector_search_indexes.query_index.side_effect = [
        RuntimeError("filters_json unsupported"),
        MagicMock(result=MagicMock(data_array=[["c1", "d1", "f.pdf", 0.8]])),
    ]
    result = _query_vector_index(
        w,
        index_name="uc13.ingestion.embeddings_index",
        query_embedding=[0.1, 0.2],
        fetch_k=9,
        company_name="Acme",
    )
    assert result.result.data_array[0][0] == "c1"
    assert w.vector_search_indexes.query_index.call_count == 2
    first_call = w.vector_search_indexes.query_index.call_args_list[0]
    assert "filters_json" in first_call.kwargs


def test_build_vs_filters_dict_merges_company_workstream_and_tier():
    filters = _build_vs_filters_dict(
        company_name="Elder Care",
        vs_metadata_filters=True,
        workstream_filter=["FINANCIAL", "BUSINESS_MODEL"],
        tier_filter=2,
    )
    assert filters == {
        "company_name": "Elder Care",
        "workstream": ["FINANCIAL", "BUSINESS_MODEL"],
        "priority_tier <=": 2,
    }


def test_build_vs_filters_dict_omits_metadata_when_flag_false():
    filters = _build_vs_filters_dict(
        company_name="Elder Care",
        vs_metadata_filters=False,
        workstream_filter=["FINANCIAL"],
        tier_filter=2,
    )
    assert filters == {"company_name": "Elder Care"}


def test_query_vector_index_includes_metadata_filters_when_flag_true():
    w = MagicMock()
    w.vector_search_indexes.query_index.return_value = MagicMock(
        result=MagicMock(data_array=[["c1", "d1", "f.pdf", 0.8]])
    )
    _query_vector_index(
        w,
        index_name="uc13.ingestion.embeddings_index",
        query_embedding=[0.1, 0.2],
        fetch_k=9,
        company_name="Elder Care",
        vs_metadata_filters=True,
        workstream_filter=["FINANCIAL"],
        tier_filter=2,
    )
    filters_json = w.vector_search_indexes.query_index.call_args.kwargs["filters_json"]
    parsed = json.loads(filters_json)
    assert parsed == {
        "company_name": "Elder Care",
        "workstream": ["FINANCIAL"],
        "priority_tier <=": 2,
    }


def test_query_vector_index_omits_metadata_predicates_when_flag_false():
    w = MagicMock()
    w.vector_search_indexes.query_index.return_value = MagicMock(
        result=MagicMock(data_array=[["c1", "d1", "f.pdf", 0.8]])
    )
    _query_vector_index(
        w,
        index_name="uc13.ingestion.embeddings_index",
        query_embedding=[0.1, 0.2],
        fetch_k=9,
        company_name="Elder Care",
        vs_metadata_filters=False,
        workstream_filter=["FINANCIAL"],
        tier_filter=2,
    )
    filters_json = w.vector_search_indexes.query_index.call_args.kwargs["filters_json"]
    assert json.loads(filters_json) == {"company_name": "Elder Care"}


def test_query_vector_index_metadata_only_without_company_name():
    """Adversarial: workstream/tier pushdown without tenant filter (T1 passed)."""
    w = MagicMock()
    w.vector_search_indexes.query_index.return_value = MagicMock(
        result=MagicMock(data_array=[["c1", "d1", "f.pdf", 0.8]])
    )
    _query_vector_index(
        w,
        index_name="uc13.ingestion.embeddings_index",
        query_embedding=[0.1, 0.2],
        fetch_k=9,
        company_name=None,
        vs_metadata_filters=True,
        workstream_filter=["LEGAL"],
        tier_filter=1,
    )
    filters_json = w.vector_search_indexes.query_index.call_args.kwargs["filters_json"]
    assert json.loads(filters_json) == {
        "workstream": ["LEGAL"],
        "priority_tier <=": 1,
    }


@patch("agents.shared.retrieval.WorkspaceClient")
@patch("agents.shared.retrieval.mlflow.deployments.get_deploy_client")
def test_semantic_search_vs_metadata_filters_wires_filters_json(
    mock_get_deploy_client,
    mock_workspace_client,
    monkeypatch,
):
    monkeypatch.setenv("catalog", "uc13_ale")
    mock_client = MagicMock()
    mock_get_deploy_client.return_value = mock_client
    mock_client.predict.return_value = {"data": [{"embedding": [0.1, 0.2]}]}

    vs_result = MagicMock()
    vs_result.result.data_array = [["c1", "d1", "CIM.pdf", 0.95]]
    mock_w = MagicMock()
    mock_w.vector_search_indexes.query_index.return_value = vs_result
    mock_workspace_client.return_value = mock_w

    hydrated = _row(chunk_id="c1", priority_tier=1)
    spark = MagicMock()
    spark.sql.return_value.collect.return_value = [hydrated]

    semantic_search(
        "revenue trends",
        spark,
        top_k=5,
        company_name="Elder Care",
        workstream_filter=["FINANCIAL"],
        tier_filter=2,
        vs_metadata_filters=True,
        min_chunk_length=50,
    )

    filters_json = mock_w.vector_search_indexes.query_index.call_args.kwargs["filters_json"]
    assert json.loads(filters_json) == {
        "company_name": "Elder Care",
        "workstream": ["FINANCIAL"],
        "priority_tier <=": 2,
    }


@patch("agents.shared.retrieval.WorkspaceClient")
@patch("agents.shared.retrieval.mlflow.deployments.get_deploy_client")
def test_semantic_search_returns_route_result(
    mock_get_deploy_client,
    mock_workspace_client,
    monkeypatch,
):
    monkeypatch.setenv("catalog", "uc13_ale")
    mock_client = MagicMock()
    mock_get_deploy_client.return_value = mock_client
    mock_client.predict.return_value = {"data": [{"embedding": [0.1, 0.2]}]}

    vs_result = MagicMock()
    vs_result.result.data_array = [["c1", "d1", "CIM.pdf", 0.95]]
    mock_w = MagicMock()
    mock_w.vector_search_indexes.query_index.return_value = vs_result
    mock_workspace_client.return_value = mock_w

    hydrated = _row(chunk_id="c1", priority_tier=1)
    spark = MagicMock()
    spark.sql.return_value.collect.return_value = [hydrated]

    result = semantic_search(
        "revenue trends",
        spark,
        top_k=5,
        company_name="Acme",
        min_chunk_length=50,
    )

    assert isinstance(result, RouteResult)
    assert result.mode == "semantic"
    assert len(result.chunks) == 1
    assert result.chunks[0].chunk_id == "c1"
    assert result.chunks[0].priority_tier == 1
    assert hasattr(result.chunks[0], "source_type")
    assert len(result.scores) == 1
    assert result.scores[0] == pytest.approx(_merge_score(hydrated, {"c1": 0.95}))
    assert all(s is not None for s in result.scores)
    query_call = mock_w.vector_search_indexes.query_index.call_args
    assert query_call.kwargs["index_name"] == "uc13_ale.ingestion.embeddings_index"


@patch("agents.shared.retrieval.WorkspaceClient")
@patch("agents.shared.retrieval.mlflow.deployments.get_deploy_client")
def test_semantic_search_keyword_fallback_emits_zero_scores(
    mock_get_deploy_client,
    mock_workspace_client,
    monkeypatch,
):
    monkeypatch.setenv("catalog", "uc13_ale")
    mock_client = MagicMock()
    mock_get_deploy_client.return_value = mock_client
    mock_client.predict.return_value = {"data": [{"embedding": [0.1, 0.2]}]}

    mock_w = MagicMock()
    mock_w.vector_search_indexes.query_index.side_effect = RuntimeError("VS down")
    mock_workspace_client.return_value = mock_w

    rows = [_row(chunk_id="k1"), _row(chunk_id="k2")]
    spark = MagicMock()
    spark.sql.return_value.collect.return_value = rows

    result = semantic_search("revenue trends", spark, top_k=5, min_chunk_length=50)

    assert result.mode == "keyword"
    assert len(result.chunks) == 2
    assert result.scores == [0.0, 0.0]


@patch("agents.shared.retrieval.WorkspaceClient")
@patch("agents.shared.retrieval.mlflow.deployments.get_deploy_client")
def test_semantic_search_empty_after_filters_emits_empty_mode(
    mock_get_deploy_client,
    mock_workspace_client,
    monkeypatch,
):
    monkeypatch.setenv("catalog", "uc13_ale")
    mock_client = MagicMock()
    mock_get_deploy_client.return_value = mock_client
    mock_client.predict.return_value = {"data": [{"embedding": [0.1, 0.2]}]}

    vs_result = MagicMock()
    vs_result.result.data_array = [["c1", "d1", "CIM.pdf", 0.95]]
    mock_w = MagicMock()
    mock_w.vector_search_indexes.query_index.return_value = vs_result
    mock_workspace_client.return_value = mock_w

    short_text = _row(chunk_id="c1")
    short_text.chunk_text = "short"
    spark = MagicMock()
    spark.sql.return_value.collect.return_value = [short_text]

    result = semantic_search(
        "revenue trends",
        spark,
        top_k=5,
        min_chunk_length=500,
    )

    assert result.mode == "empty"
    assert result.chunks == []
    assert result.scores == []


@patch("agents.shared.retrieval.WorkspaceClient")
@patch("agents.shared.retrieval.mlflow.deployments.get_deploy_client")
def test_semantic_search_keyword_fallback_empty_after_filters_is_empty_mode(
    mock_get_deploy_client,
    mock_workspace_client,
    monkeypatch,
):
    """Keyword path with zero surviving chunks must use empty mode, not keyword + []."""
    monkeypatch.setenv("catalog", "uc13_ale")
    mock_client = MagicMock()
    mock_get_deploy_client.return_value = mock_client
    mock_client.predict.return_value = {"data": [{"embedding": [0.1, 0.2]}]}

    mock_w = MagicMock()
    mock_w.vector_search_indexes.query_index.side_effect = RuntimeError("VS down")
    mock_workspace_client.return_value = mock_w

    short = _row(chunk_id="k1")
    short.chunk_text = "x"
    spark = MagicMock()
    spark.sql.return_value.collect.return_value = [short]

    result = semantic_search("revenue trends", spark, top_k=5, min_chunk_length=500)

    assert result.mode == "empty"
    assert result.chunks == []
    assert result.scores == []


# ---------------------------------------------------------------------------
# M-RE2 T3 — provenance emit hook on semantic_search
# ---------------------------------------------------------------------------


@pytest.fixture
def re2_store(tmp_path) -> SqliteEvalStore:
    db = SqliteEvalStore(tmp_path / "re2_store.sqlite")
    yield db
    db.close()


@pytest.fixture(autouse=True)
def _reset_run_context():
    ProvenanceEmitter._intents_by_run.clear()
    ProvenanceEmitter._logged_runs.clear()
    yield
    try:
        close_agent_run()
    except RunContextError:
        pass


@pytest.fixture(autouse=True)
def _clear_provenance_env(monkeypatch):
    monkeypatch.delenv("RE2_PROVENANCE_REQUIRED", raising=False)


def _provenance_rows(store: SqliteEvalStore, run_id: str) -> list:
    return store._conn.execute(
        "SELECT intent_id, chunk_id, rank, mode "
        "FROM retrieval_provenance WHERE run_id = ? ORDER BY rank",
        (run_id,),
    ).fetchall()


@patch("agents.shared.retrieval.WorkspaceClient")
@patch("agents.shared.retrieval.mlflow.deployments.get_deploy_client")
def test_semantic_search_emits_provenance_when_run_open(
    mock_get_deploy_client,
    mock_workspace_client,
    monkeypatch,
    re2_store,
):
    monkeypatch.setenv("catalog", "uc13_ale")
    mock_client = MagicMock()
    mock_get_deploy_client.return_value = mock_client
    mock_client.predict.return_value = {"data": [{"embedding": [0.1, 0.2]}]}

    vs_result = MagicMock()
    vs_result.result.data_array = [["c1", "d1", "CIM.pdf", 0.95]]
    mock_w = MagicMock()
    mock_w.vector_search_indexes.query_index.return_value = vs_result
    mock_workspace_client.return_value = mock_w

    hydrated = _row(chunk_id="c1", priority_tier=1)
    spark = MagicMock()
    spark.sql.return_value.collect.return_value = [hydrated]

    set_pipeline_thread("thread-t3-001")
    run_id = open_agent_run(
        "fta",
        company_name="Elder Care",
        catalog="uc13_ale",
        affected_intents=["fta.opex.q1_financial_statements"],
        store=re2_store,
    )

    result = semantic_search(
        "revenue trends",
        spark,
        top_k=5,
        company_name="Elder Care",
        min_chunk_length=50,
        intent_id="fta.opex.q1_financial_statements",
    )

    assert result.mode == "semantic"
    rows = _provenance_rows(re2_store, run_id)
    assert len(rows) == 1
    assert rows[0]["intent_id"] == "fta.opex.q1_financial_statements"
    assert rows[0]["chunk_id"] == "c1"
    assert rows[0]["mode"] == "semantic"
    close_agent_run()


@patch("agents.shared.retrieval.WorkspaceClient")
@patch("agents.shared.retrieval.mlflow.deployments.get_deploy_client")
def test_semantic_search_provenance_noop_without_open_run(
    mock_get_deploy_client,
    mock_workspace_client,
    monkeypatch,
    re2_store,
):
    """Kill criterion: emit must no-op silently when no agent run is open."""
    monkeypatch.setenv("catalog", "uc13_ale")
    mock_client = MagicMock()
    mock_get_deploy_client.return_value = mock_client
    mock_client.predict.return_value = {"data": [{"embedding": [0.1, 0.2]}]}

    vs_result = MagicMock()
    vs_result.result.data_array = [["c1", "d1", "CIM.pdf", 0.95]]
    mock_w = MagicMock()
    mock_w.vector_search_indexes.query_index.return_value = vs_result
    mock_workspace_client.return_value = mock_w

    hydrated = _row(chunk_id="c1", priority_tier=1)
    spark = MagicMock()
    spark.sql.return_value.collect.return_value = [hydrated]

    # No open_agent_run — emit must not raise and must not write any rows.
    result = semantic_search(
        "revenue trends",
        spark,
        top_k=5,
        company_name="Elder Care",
        min_chunk_length=50,
        intent_id="fta.opex.q1_financial_statements",
    )

    assert result.mode == "semantic"
    # re2_store has no manifest; querying it for provenance yields no rows.
    rows = re2_store._conn.execute(
        "SELECT intent_id FROM retrieval_provenance"
    ).fetchall()
    assert rows == []


@patch("agents.shared.retrieval.WorkspaceClient")
@patch("agents.shared.retrieval.mlflow.deployments.get_deploy_client")
def test_semantic_search_provenance_emits_after_merge_rank_and_cap(
    mock_get_deploy_client,
    mock_workspace_client,
    monkeypatch,
    re2_store,
):
    """Adversarial micro-pass: emit must run AFTER merge-rank + top_k cap.

    Falsifies two failure modes at once: (a) emit before the top_k cap would
    surface both chunks instead of one; (b) emit before merge-rank would
    surface c1 (data_array order) instead of the higher merge-score c2.
    """
    monkeypatch.setenv("catalog", "uc13_ale")
    mock_client = MagicMock()
    mock_get_deploy_client.return_value = mock_client
    mock_client.predict.return_value = {"data": [{"embedding": [0.1, 0.2]}]}

    # c1: tier 1, sim 0.30 -> merge 0.35.  c2: tier 3, sim 0.95 -> merge 0.97.
    vs_result = MagicMock()
    vs_result.result.data_array = [
        ["c1", "d1", "CIM.pdf", 0.30],
        ["c2", "d2", "P&L.pdf", 0.95],
    ]
    mock_w = MagicMock()
    mock_w.vector_search_indexes.query_index.return_value = vs_result
    mock_workspace_client.return_value = mock_w

    hydrated_c1 = _row(chunk_id="c1", priority_tier=1)
    hydrated_c2 = _row(chunk_id="c2", priority_tier=3)
    spark = MagicMock()
    spark.sql.return_value.collect.return_value = [hydrated_c1, hydrated_c2]

    set_pipeline_thread("thread-t3-cap")
    run_id = open_agent_run(
        "fta",
        company_name="Elder Care",
        catalog="uc13_ale",
        affected_intents=["fta.opex.q1_financial_statements"],
        store=re2_store,
    )

    result = semantic_search(
        "revenue trends",
        spark,
        top_k=1,
        company_name="Elder Care",
        min_chunk_length=50,
        intent_id="fta.opex.q1_financial_statements",
    )

    assert len(result.chunks) == 1
    assert result.chunks[0].chunk_id == "c2"
    rows = _provenance_rows(re2_store, run_id)
    assert len(rows) == 1, "emit must reflect the top_k cap, not pre-cap chunks"
    assert rows[0]["chunk_id"] == "c2", "emit must reflect merge-rank order"
    assert rows[0]["rank"] == 1
    close_agent_run()


@patch("agents.shared.retrieval.WorkspaceClient")
@patch("agents.shared.retrieval.mlflow.deployments.get_deploy_client")
def test_semantic_search_provenance_intent_id_fallback(
    mock_get_deploy_client,
    mock_workspace_client,
    monkeypatch,
    re2_store,
):
    """intent_id None on a non-FTA run falls back to unknown.{agent_id}."""
    monkeypatch.setenv("catalog", "uc13_ale")
    mock_client = MagicMock()
    mock_get_deploy_client.return_value = mock_client
    mock_client.predict.return_value = {"data": [{"embedding": [0.1, 0.2]}]}

    vs_result = MagicMock()
    vs_result.result.data_array = [["c1", "d1", "CIM.pdf", 0.95]]
    mock_w = MagicMock()
    mock_w.vector_search_indexes.query_index.return_value = vs_result
    mock_workspace_client.return_value = mock_w

    hydrated = _row(chunk_id="c1", priority_tier=1)
    spark = MagicMock()
    spark.sql.return_value.collect.return_value = [hydrated]

    set_pipeline_thread("thread-t3-fallback")
    run_id = open_agent_run(
        "bma",
        company_name="Elder Care",
        catalog="uc13_ale",
        affected_intents=["bma.business_model"],
        store=re2_store,
    )

    semantic_search(
        "business model",
        spark,
        top_k=5,
        company_name="Elder Care",
        min_chunk_length=50,
        intent_id=None,
    )

    rows = _provenance_rows(re2_store, run_id)
    assert len(rows) == 1
    assert rows[0]["intent_id"] == "unknown.bma"
    close_agent_run()


def _setup_vs_hydrate_mocks(
    mock_get_deploy_client,
    mock_workspace_client,
    monkeypatch,
    *,
    data_array: list,
    hydrated_rows: list,
) -> MagicMock:
    """Configure shared VS+hydrate mocks for merge_rank_mode ordering tests."""
    monkeypatch.setenv("catalog", "uc13_ale")
    mock_client = MagicMock()
    mock_get_deploy_client.return_value = mock_client
    mock_client.predict.return_value = {"data": [{"embedding": [0.1, 0.2]}]}

    vs_result = MagicMock()
    vs_result.result.data_array = data_array
    mock_w = MagicMock()
    mock_w.vector_search_indexes.query_index.return_value = vs_result
    mock_workspace_client.return_value = mock_w

    spark = MagicMock()
    spark.sql.return_value.collect.return_value = hydrated_rows
    return spark


@patch("agents.shared.retrieval.WorkspaceClient")
@patch("agents.shared.retrieval.mlflow.deployments.get_deploy_client")
def test_semantic_search_source_type_priority_keeps_best_sim_gold_in_top_k(
    mock_get_deploy_client,
    mock_workspace_client,
    monkeypatch,
):
    """Harness-faithful F1 path: source_type_priority + top_k=8 must keep the
    highest-sim tier-2 gold chunk after post-filter ranking.
    """
    gold = _row(chunk_id="gold_cim", priority_tier=2, source_type="vision")
    neighbors = [
        _row(chunk_id=f"t1_{i}", priority_tier=1, source_type="text")
        for i in range(8)
    ]
    data_array = [["gold_cim", "d0", "CIM.pdf", 0.6910852]]
    data_array.extend(
        [f"t1_{i}", f"d{i+1}", f"Model_{i}.xlsx", 0.6583611 - i * 0.001]
        for i in range(8)
    )
    spark = _setup_vs_hydrate_mocks(
        mock_get_deploy_client,
        mock_workspace_client,
        monkeypatch,
        data_array=data_array,
        hydrated_rows=[gold, *neighbors],
    )

    result = semantic_search(
        "projected revenue forecast",
        spark,
        top_k=8,
        company_name="Elder Care",
        min_chunk_length=50,
        source_type_priority=True,
    )

    assert len(result.chunks) == 8
    assert "gold_cim" in [c.chunk_id for c in result.chunks]
    assert result.chunks[0].chunk_id == "gold_cim"


@patch("agents.shared.retrieval.WorkspaceClient")
@patch("agents.shared.retrieval.mlflow.deployments.get_deploy_client")
def test_merge_rank_mode_none_matches_sim_tier_ordering(
    mock_get_deploy_client,
    mock_workspace_client,
    monkeypatch,
):
    """Kill criterion: omitted merge_rank_mode reproduces pre-T4 default path."""
    hydrated_c1 = _row(chunk_id="c1", priority_tier=1)
    hydrated_c2 = _row(chunk_id="c2", priority_tier=3)
    spark = _setup_vs_hydrate_mocks(
        mock_get_deploy_client,
        mock_workspace_client,
        monkeypatch,
        data_array=[
            ["c1", "d1", "CIM.pdf", 0.30],
            ["c2", "d2", "P&L.pdf", 0.95],
        ],
        hydrated_rows=[hydrated_c1, hydrated_c2],
    )

    default_result = semantic_search(
        "revenue trends",
        spark,
        top_k=5,
        company_name="Elder Care",
        min_chunk_length=50,
    )
    explicit_result = semantic_search(
        "revenue trends",
        spark,
        top_k=5,
        company_name="Elder Care",
        min_chunk_length=50,
        merge_rank_mode="sim_tier",
    )

    assert [c.chunk_id for c in default_result.chunks] == [
        c.chunk_id for c in explicit_result.chunks
    ]
    assert default_result.scores == explicit_result.scores


@patch("agents.shared.retrieval.WorkspaceClient")
@patch("agents.shared.retrieval.mlflow.deployments.get_deploy_client")
def test_merge_rank_mode_sim_only_ignores_tier_weight(
    mock_get_deploy_client,
    mock_workspace_client,
    monkeypatch,
):
    hydrated_c1 = _row(chunk_id="c1", priority_tier=1)
    hydrated_c2 = _row(chunk_id="c2", priority_tier=3)
    spark = _setup_vs_hydrate_mocks(
        mock_get_deploy_client,
        mock_workspace_client,
        monkeypatch,
        data_array=[
            ["c1", "d1", "CIM.pdf", 0.30],
            ["c2", "d2", "P&L.pdf", 0.95],
        ],
        hydrated_rows=[hydrated_c1, hydrated_c2],
    )

    result = semantic_search(
        "revenue trends",
        spark,
        top_k=5,
        company_name="Elder Care",
        min_chunk_length=50,
        merge_rank_mode="sim_only",
    )

    assert [c.chunk_id for c in result.chunks] == ["c2", "c1"]
    assert result.scores == [pytest.approx(0.95), pytest.approx(0.30)]


@patch("agents.shared.retrieval.WorkspaceClient")
@patch("agents.shared.retrieval.mlflow.deployments.get_deploy_client")
def test_merge_rank_mode_tier_only_ignores_similarity(
    mock_get_deploy_client,
    mock_workspace_client,
    monkeypatch,
):
    hydrated_c1 = _row(chunk_id="c1", priority_tier=2)
    hydrated_c2 = _row(chunk_id="c2", priority_tier=1)
    spark = _setup_vs_hydrate_mocks(
        mock_get_deploy_client,
        mock_workspace_client,
        monkeypatch,
        data_array=[
            ["c1", "d1", "CIM.pdf", 0.99],
            ["c2", "d2", "P&L.pdf", 0.10],
        ],
        hydrated_rows=[hydrated_c1, hydrated_c2],
    )

    result = semantic_search(
        "revenue trends",
        spark,
        top_k=5,
        company_name="Elder Care",
        min_chunk_length=50,
        merge_rank_mode="tier_only",
    )

    assert [c.chunk_id for c in result.chunks] == ["c2", "c1"]


@patch("agents.shared.retrieval.WorkspaceClient")
@patch("agents.shared.retrieval.mlflow.deployments.get_deploy_client")
def test_merge_rank_mode_off_preserves_hydrate_sql_order(
    mock_get_deploy_client,
    mock_workspace_client,
    monkeypatch,
):
    hydrated_c1 = _row(chunk_id="c1", priority_tier=2)
    hydrated_c2 = _row(chunk_id="c2", priority_tier=1)
    spark = _setup_vs_hydrate_mocks(
        mock_get_deploy_client,
        mock_workspace_client,
        monkeypatch,
        data_array=[
            ["c1", "d1", "CIM.pdf", 0.30],
            ["c2", "d2", "P&L.pdf", 0.95],
        ],
        hydrated_rows=[hydrated_c1, hydrated_c2],
    )

    result = semantic_search(
        "revenue trends",
        spark,
        top_k=5,
        company_name="Elder Care",
        min_chunk_length=50,
        merge_rank_mode="off",
    )

    assert [c.chunk_id for c in result.chunks] == ["c1", "c2"]


def test_sort_by_sim_only_prefers_higher_raw_score():
    chunks = [_row(chunk_id="low", priority_tier=1), _row(chunk_id="high", priority_tier=3)]
    score_map = {"low": 0.95, "high": 0.20}
    ranked = _sort_by_sim_only(chunks, score_map)
    assert [c.chunk_id for c in ranked] == ["low", "high"]


def test_sort_by_tier_only_orders_ascending_tier():
    chunks = [_row(chunk_id="b", priority_tier=2), _row(chunk_id="a", priority_tier=1)]
    ranked = _sort_by_tier_only(chunks)
    assert [c.chunk_id for c in ranked] == ["a", "b"]


def test_type_order_is_canonical_across_retrieval_and_context_utils():
    """R-09: context_utils must alias retrieval._TYPE_ORDER, not a duplicate dict."""
    from agents.shared import retrieval
    from agents.subagents.workstream.financial import context_utils

    assert context_utils._TYPE_ORDER is retrieval._TYPE_ORDER
    assert context_utils._TYPE_ORDER == {"table": 0, "vision": 1, "text": 2}
