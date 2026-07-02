"""Unit tests for retrieval.py merge rank, score extraction, and SQL escaping."""

from __future__ import annotations

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
    _default_catalog,
    _escape_sql_literal,
    _extract_score_map,
    _hydrate_chunks_sql,
    _index_name_for_catalog,
    _keyword_fallback_sql,
    _merge_score,
    _query_vector_index,
    _sort_by_merge_rank,
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


def _row(*, chunk_id: str, priority_tier: int = 2, source_type: str = "text"):
    return SimpleNamespace(
        chunk_id=chunk_id,
        file_name=f"{chunk_id}.pdf",
        chunk_text="A" * 120,
        section_header="Revenue",
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
    # 0.95 * 0.4 = 0.38 beats 0.3 * 1.0 = 0.30
    assert [c.chunk_id for c in ranked] == ["strong_t3", "weak_t1"]


def test_merge_rank_falls_back_to_tier_when_no_scores():
    chunks = [_row(chunk_id="b", priority_tier=2), _row(chunk_id="a", priority_tier=1)]
    ranked = _sort_by_merge_rank(chunks, {})
    assert [c.chunk_id for c in ranked] == ["a", "b"]


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

    # c1: tier 1, sim 0.30 -> merge 0.30.  c2: tier 3, sim 0.95 -> merge 0.38.
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
