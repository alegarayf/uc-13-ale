"""Unit tests for ingestion_parser index-sync fail-closed behavior (M-PHV1 T2)."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = _REPO_ROOT / "databricks" / "jobs" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# Stub pyspark / mlflow before pipeline entrypoints import them inside main()/ingest_missing().
if "pyspark" not in sys.modules:
    _pyspark_mod = types.ModuleType("pyspark")
    _sql_mod = types.ModuleType("pyspark.sql")
    _types_mod = types.ModuleType("pyspark.sql.types")

    class _SparkSession:
        @staticmethod
        def getActiveSession():
            return None

    class _StubSparkType:
        def __init__(self, *args, **kwargs):
            pass

    _sql_mod.SparkSession = _SparkSession
    _sql_mod.Row = lambda **kwargs: SimpleNamespace(**kwargs)
    for _name in (
        "StructType",
        "StructField",
        "StringType",
        "IntegerType",
        "BooleanType",
        "ArrayType",
        "FloatType",
        "TimestampType",
    ):
        setattr(_types_mod, _name, _StubSparkType)

    _pyspark_mod.sql = _sql_mod
    sys.modules["pyspark"] = _pyspark_mod
    sys.modules["pyspark.sql"] = _sql_mod
    sys.modules["pyspark.sql.types"] = _types_mod

if "mlflow" not in sys.modules:
    _mlflow_mod = types.ModuleType("mlflow")
    _deployments_mod = types.ModuleType("mlflow.deployments")
    _deployments_mod.get_deploy_client = MagicMock(return_value=MagicMock())
    _mlflow_mod.deployments = _deployments_mod
    sys.modules["mlflow"] = _mlflow_mod
    sys.modules["mlflow.deployments"] = _deployments_mod

import ingestion_parser as ip  # noqa: E402
import ensure_coverage as ec  # noqa: E402


def _sample_chunk() -> ip.Chunk:
    return ip.Chunk(
        chunk_id="chunk-1",
        doc_id="doc-1",
        file_name="doc.pdf",
        file_type="pdf",
        relative_path="doc.pdf",
        chunk_index=0,
        chunk_text="Sample chunk text for embedding.",
    )


def _make_spark_mock(*, total_emb: int = 100) -> MagicMock:
    spark = MagicMock()
    count_result = MagicMock()
    count_result.collect.return_value = [{"n": total_emb}]
    spark.sql.return_value = count_result

    df = MagicMock()
    df.count.return_value = 1
    write_chain = df.write.format.return_value.mode.return_value.option.return_value
    write_chain.saveAsTable = MagicMock()
    df.write.mode.return_value.option.return_value.saveAsTable = MagicMock()
    spark.createDataFrame.return_value = df
    return spark


def _configure_workspace_client(
    mock_ws_cls: MagicMock,
    *,
    pipeline_state: str,
    indexed_rows: int,
    pipeline_id: str = "pipe-1",
) -> MagicMock:
    ws = MagicMock()
    mock_ws_cls.return_value = ws
    ws.vector_search_indexes.sync_index = MagicMock()

    get_index_calls = {"n": 0}

    def get_index(**_kwargs):
        get_index_calls["n"] += 1
        idx = MagicMock()
        if get_index_calls["n"] == 1:
            idx.delta_sync_index_spec.pipeline_id = pipeline_id
        else:
            idx.delta_sync_index_spec = None
        idx.status.indexed_row_count = indexed_rows
        return idx

    ws.vector_search_indexes.get_index.side_effect = get_index

    update = MagicMock()
    update.state.value = pipeline_state
    pipeline = MagicMock()
    pipeline.latest_updates = [update]
    ws.pipelines.get.return_value = pipeline
    return ws


def _get_param_side_effect(key: str, default=None):
    params = {
        "sp_company_name": "TestCo",
        "catalog": "uc13",
        "schema": "ingestion",
        "embedding_endpoint": "databricks-bge-large-en",
        "vision_endpoint": "",
        "parse_priority_tiers": "all",
    }
    return params.get(key, default)


def _mock_main_spark(*, total_emb: int = 1) -> MagicMock:
    spark = MagicMock()
    approved_row = SimpleNamespace(
        file_name="doc.pdf",
        folder_path="",
        workstream=["FINANCIAL"],
        priority_tier=1,
    )

    def sql_side_effect(query: str):
        result = MagicMock()
        if "COUNT(*)" in query:
            result.collect.return_value = [{"n": total_emb}]
        elif "doc_relevance" in query:
            result.collect.return_value = [approved_row]
        else:
            result.collect.return_value = []
        return result

    spark.sql.side_effect = sql_side_effect

    df = MagicMock()
    df.count.return_value = 1
    df.write.mode.return_value.option.return_value.saveAsTable = MagicMock()
    spark.createDataFrame.return_value = df
    return spark


@patch("time.sleep")
@patch("databricks.sdk.WorkspaceClient")
def test_workspace_client_patch_intercepts_construction(mock_ws_cls, _mock_sleep):
    """Smoke: patching databricks.sdk.WorkspaceClient intercepts function-local import."""
    _configure_workspace_client(mock_ws_cls, pipeline_state="FAILED", indexed_rows=0)

    spark = _make_spark_mock(total_emb=100)
    with pytest.raises(ip.IndexSyncError):
        ip._wait_for_index_sync(
            spark=spark,
            catalog="uc13",
            schema="ingestion",
            index_suffix="embeddings_index",
            table_embeddings="uc13.ingestion.embeddings",
        )

    mock_ws_cls.assert_called_once()


@pytest.mark.parametrize("terminal_state", ["FAILED", "CANCELED"])
@patch("time.sleep")
@patch("databricks.sdk.WorkspaceClient")
def test_wait_for_index_sync_raises_on_terminal_state(
    mock_ws_cls, _mock_sleep, terminal_state, capsys
):
    _configure_workspace_client(
        mock_ws_cls, pipeline_state=terminal_state, indexed_rows=0
    )
    spark = _make_spark_mock(total_emb=100)

    with pytest.raises(ip.IndexSyncError) as exc_info:
        ip._wait_for_index_sync(
            spark=spark,
            catalog="uc13",
            schema="ingestion",
            index_suffix="embeddings_index",
            table_embeddings="uc13.ingestion.embeddings",
        )

    captured = capsys.readouterr().out
    assert "✗ Sync failed — halting" in captured
    assert terminal_state in str(exc_info.value)
    assert "indexed=0/100" in str(exc_info.value)


@patch("time.sleep")
@patch("databricks.sdk.WorkspaceClient")
def test_wait_for_index_sync_raises_on_timeout(mock_ws_cls, _mock_sleep, capsys):
    _configure_workspace_client(mock_ws_cls, pipeline_state="RUNNING", indexed_rows=0)
    spark = _make_spark_mock(total_emb=100)

    with pytest.raises(ip.IndexSyncError) as exc_info:
        ip._wait_for_index_sync(
            spark=spark,
            catalog="uc13",
            schema="ingestion",
            index_suffix="embeddings_index",
            table_embeddings="uc13.ingestion.embeddings",
            poll_interval=30,
            max_wait_seconds=60,
        )

    captured = capsys.readouterr().out
    assert "✗ Sync failed — halting" in captured
    msg = str(exc_info.value)
    assert "max_wait_seconds=60" in msg
    assert "pipeline state=RUNNING" in msg
    assert "indexed=0/100" in msg


@patch("time.sleep")
@patch("databricks.sdk.WorkspaceClient")
def test_wait_for_index_sync_wraps_generic_exception(
    mock_ws_cls, _mock_sleep, capsys
):
    ws = MagicMock()
    mock_ws_cls.return_value = ws
    ws.vector_search_indexes.sync_index.side_effect = RuntimeError("boom")
    spark = _make_spark_mock(total_emb=100)

    with pytest.raises(ip.IndexSyncError) as exc_info:
        ip._wait_for_index_sync(
            spark=spark,
            catalog="uc13",
            schema="ingestion",
            index_suffix="embeddings_index",
            table_embeddings="uc13.ingestion.embeddings",
        )

    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert "boom" in str(exc_info.value.__cause__)
    captured = capsys.readouterr().out
    assert "✗ Sync failed — halting" in captured


@patch("time.sleep")
@patch("databricks.sdk.WorkspaceClient")
def test_wait_for_index_sync_success_path(mock_ws_cls, _mock_sleep, capsys):
    _configure_workspace_client(
        mock_ws_cls, pipeline_state="COMPLETED", indexed_rows=100
    )
    spark = _make_spark_mock(total_emb=100)

    ip._wait_for_index_sync(
        spark=spark,
        catalog="uc13",
        schema="ingestion",
        index_suffix="embeddings_index",
        table_embeddings="uc13.ingestion.embeddings",
    )

    captured = capsys.readouterr().out
    assert "✓ Index ready" in captured


@pytest.mark.parametrize("terminal_state", ["FAILED", "CANCELED"])
@patch("time.sleep")
@patch("databricks.sdk.WorkspaceClient")
@patch("ingestion_parser.get_embeddings_batch", return_value=[[0.1] * 8])
@patch("ingestion_parser.parse_file")
@patch("ingestion_parser.get_param", side_effect=_get_param_side_effect)
@patch("ingestion_parser.find_repo_root", return_value=str(_REPO_ROOT))
@patch("pyspark.sql.SparkSession.getActiveSession")
@patch("os.path.exists", return_value=True)
def test_main_propagates_index_sync_error(
    _mock_exists,
    mock_get_active_session,
    _mock_find_repo_root,
    _mock_get_param,
    mock_parse_file,
    _mock_embeddings,
    mock_ws_cls,
    _mock_sleep,
    terminal_state,
):
    mock_get_active_session.return_value = _mock_main_spark(total_emb=1)
    mock_parse_file.return_value = [_sample_chunk()]
    _configure_workspace_client(
        mock_ws_cls, pipeline_state=terminal_state, indexed_rows=0
    )

    with pytest.raises(ip.IndexSyncError) as exc_info:
        ip.main()

    assert terminal_state in str(exc_info.value)


@pytest.mark.parametrize("terminal_state", ["FAILED", "CANCELED"])
@patch("time.sleep")
@patch("databricks.sdk.WorkspaceClient")
@patch("ingestion_parser.get_embeddings_batch", return_value=[[0.1] * 8])
@patch("ingestion_parser.parse_file")
@patch("ensure_coverage.get_unprocessed_files")
@patch("os.path.exists", return_value=True)
def test_ingest_missing_propagates_index_sync_error(
    _mock_exists,
    mock_get_unprocessed,
    mock_parse_file,
    _mock_embeddings,
    mock_ws_cls,
    _mock_sleep,
    terminal_state,
):
    mock_get_unprocessed.return_value = [
        {
            "file_name": "doc.pdf",
            "folder_path": "",
            "workstream": ["FINANCIAL"],
            "priority_tier": 1,
        }
    ]
    mock_parse_file.return_value = [_sample_chunk()]
    spark = _mock_main_spark(total_emb=1)
    _configure_workspace_client(
        mock_ws_cls, pipeline_state=terminal_state, indexed_rows=0
    )

    with pytest.raises(ip.IndexSyncError) as exc_info:
        ec.ingest_missing(
            company_name="TestCo",
            catalog="uc13",
            tiers=[1, 2],
            spark=spark,
        )

    assert terminal_state in str(exc_info.value)
