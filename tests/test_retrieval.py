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
def test_semantic_search_returns_list_and_preserves_row_fields(
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

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].chunk_id == "c1"
    assert result[0].priority_tier == 1
    assert hasattr(result[0], "source_type")
    query_call = mock_w.vector_search_indexes.query_index.call_args
    assert query_call.kwargs["index_name"] == "uc13_ale.ingestion.embeddings_index"
