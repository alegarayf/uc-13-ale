"""DocWorker status transitions and interrupted-state redo (M4 T2).

Covers claim→clean→parse→chunks→embed→complete/fail transitions,
_upsert_failed (FAILED(reason) writes), and _delete_stale_corpus
(delete-by-doc_id idempotent redo for STALE/RETRY reprocessing).
"""

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
        "FloatType",
        "ArrayType",
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
from doc_worker import DocWorker  # noqa: E402
from parse_manifest import ManifestItem  # noqa: E402
from status_store import (  # noqa: E402
    COMPLETE,
    EMBEDDING,
    FAILED,
    PARSING,
    ZERO_CHUNKS,
)

_CATALOG = "uc13_ale"
_SCHEMA = "ingestion"
_COMPANY = "Elder Care"
_RUN_ID = "run-test-1"
_DOC_ID = "abc123def456"


def _make_spark_mock() -> MagicMock:
    spark = MagicMock()
    sql_result = MagicMock()
    sql_result.collect.return_value = []
    spark.sql.return_value = sql_result

    df = MagicMock()
    write_chain = df.write.mode.return_value.option.return_value
    write_chain.saveAsTable = MagicMock()
    spark.createDataFrame.return_value = df
    return spark


def _make_worker(spark: MagicMock | None = None) -> DocWorker:
    spark = spark or _make_spark_mock()
    worker = DocWorker(
        spark=spark,
        catalog=_CATALOG,
        schema=_SCHEMA,
        company=_COMPANY,
        run_id=_RUN_ID,
    )
    worker._status_store = MagicMock()
    return worker


def _make_item(
    *,
    classification: str = "NEW",
    file_name: str = "report.csv",
    doc_id: str = _DOC_ID,
    source_size: int = 500,
) -> ManifestItem:
    return ManifestItem(
        doc_id=doc_id,
        file_name=file_name,
        relative_path=file_name,
        full_path=f"/Volumes/{_CATALOG}/{_SCHEMA}/raw_files/{_COMPANY}/{file_name}",
        source_mtime=1000,
        source_size=source_size,
        classification=classification,
        coverage_injected=False,
    )


def _sample_chunk(doc_id: str = _DOC_ID, file_name: str = "report.csv") -> ip.Chunk:
    return ip.Chunk(
        chunk_id="chunk-1",
        doc_id=doc_id,
        file_name=file_name,
        file_type="csv",
        relative_path=file_name,
        chunk_index=0,
        chunk_text="x" * 200,
        source_type="text",
    )


def _delete_sql_calls(spark: MagicMock) -> list[str]:
    return [
        call.args[0]
        for call in spark.sql.call_args_list
        if call.args and "DELETE FROM" in call.args[0]
    ]


def _status_sequence(worker: DocWorker) -> list[str]:
    return [
        call.kwargs["status"]
        for call in worker._status_store.upsert.call_args_list
    ]


def test_process_success_transitions_parsing_embedding_complete() -> None:
    worker = _make_worker()
    with patch.object(worker, "_compute_content_hash", return_value="content-hash"):
        with patch("ingestion_parser.parse_file", return_value=[_sample_chunk()]):
            with patch(
                "ingestion_parser.get_embeddings_batch",
                return_value=[[0.1, 0.2]],
            ):
                worker.process(_make_item())

    assert _status_sequence(worker) == [PARSING, EMBEDDING, COMPLETE]
    complete_call = worker._status_store.upsert.call_args_list[-1]
    assert complete_call.kwargs["chunk_count"] == 1
    assert complete_call.kwargs["content_hash"] == "content-hash"


def test_upsert_failed_writes_failed_status_with_reason_prefix() -> None:
    worker = _make_worker()
    item = _make_item()
    worker._upsert_failed(item, "PARSE_EXCEPTION", "parse blew up")

    worker._status_store.upsert.assert_called_once()
    call = worker._status_store.upsert.call_args
    assert call.kwargs["status"] == FAILED
    assert call.kwargs["error"] == "PARSE_EXCEPTION: parse blew up"
    assert call.kwargs["doc_id"] == _DOC_ID


def test_unsupported_extension_claim_then_failed() -> None:
    worker = _make_worker()
    worker.process(_make_item(file_name="notes.txt"))

    assert _status_sequence(worker) == [PARSING, FAILED]
    failed_call = worker._status_store.upsert.call_args_list[-1]
    assert "UNSUPPORTED_EXTENSION" in failed_call.kwargs["error"]


def test_file_not_found_upserts_failed() -> None:
    worker = _make_worker()
    with patch.object(
        worker,
        "_compute_content_hash",
        side_effect=FileNotFoundError("no such file"),
    ):
        worker.process(_make_item())

    assert _status_sequence(worker) == [PARSING, FAILED]
    assert "FILE_NOT_FOUND" in worker._status_store.upsert.call_args_list[-1].kwargs["error"]


def test_parse_exception_upserts_failed() -> None:
    worker = _make_worker()
    with patch.object(worker, "_compute_content_hash", return_value="hash"):
        with patch(
            "ingestion_parser.parse_file",
            side_effect=RuntimeError("parse failed"),
        ):
            worker.process(_make_item())

    assert _status_sequence(worker) == [PARSING, FAILED]
    assert "PARSE_EXCEPTION" in worker._status_store.upsert.call_args_list[-1].kwargs["error"]


def test_zero_chunks_upserts_zero_chunks_status() -> None:
    worker = _make_worker()
    with patch.object(worker, "_compute_content_hash", return_value="hash"):
        with patch("ingestion_parser.parse_file", return_value=[]):
            worker.process(_make_item(source_size=0))

    assert _status_sequence(worker) == [PARSING, ZERO_CHUNKS]
    zero_call = worker._status_store.upsert.call_args_list[-1]
    assert "EMPTY_EXTRACTION" in zero_call.kwargs["error"]


def test_embed_exception_upserts_failed() -> None:
    worker = _make_worker()
    with patch.object(worker, "_compute_content_hash", return_value="hash"):
        with patch("ingestion_parser.parse_file", return_value=[_sample_chunk()]):
            with patch.object(
                worker,
                "_append_chunks",
                side_effect=RuntimeError("chunk write failed"),
            ):
                worker.process(_make_item())

    assert _status_sequence(worker) == [PARSING, FAILED]
    assert "EMBED_EXCEPTION" in worker._status_store.upsert.call_args_list[-1].kwargs["error"]


def test_delete_stale_corpus_deletes_chunks_and_embeddings_by_doc_id() -> None:
    spark = _make_spark_mock()
    worker = _make_worker(spark)
    worker._delete_stale_corpus(_DOC_ID)

    delete_calls = _delete_sql_calls(spark)
    assert len(delete_calls) == 2
    assert f"{_CATALOG}.{_SCHEMA}.chunks" in delete_calls[0]
    assert f"{_CATALOG}.{_SCHEMA}.embeddings" in delete_calls[1]
    assert _DOC_ID in delete_calls[0]
    assert _COMPANY in delete_calls[0]


def test_delete_stale_corpus_repeat_is_idempotent() -> None:
    spark = _make_spark_mock()
    worker = _make_worker(spark)
    worker._delete_stale_corpus(_DOC_ID)
    worker._delete_stale_corpus(_DOC_ID)

    assert len(_delete_sql_calls(spark)) == 4


@pytest.mark.parametrize("classification", ["STALE", "RETRY"])
def test_stale_or_retry_deletes_corpus_before_reprocessing(classification: str) -> None:
    spark = _make_spark_mock()
    worker = _make_worker(spark)
    with patch.object(worker, "_compute_content_hash", return_value="hash"):
        with patch("ingestion_parser.parse_file", return_value=[_sample_chunk()]):
            with patch(
                "ingestion_parser.get_embeddings_batch",
                return_value=[[0.1]],
            ):
                worker.process(_make_item(classification=classification))

    delete_calls = _delete_sql_calls(spark)
    assert len(delete_calls) == 2
    assert _status_sequence(worker) == [PARSING, EMBEDDING, COMPLETE]


def test_new_classification_skips_stale_corpus_delete() -> None:
    spark = _make_spark_mock()
    worker = _make_worker(spark)
    with patch.object(worker, "_compute_content_hash", return_value="hash"):
        with patch("ingestion_parser.parse_file", return_value=[_sample_chunk()]):
            with patch(
                "ingestion_parser.get_embeddings_batch",
                return_value=[[0.1]],
            ):
                worker.process(_make_item(classification="NEW"))

    assert _delete_sql_calls(spark) == []


def test_delete_stale_corpus_escapes_sql_literals_in_doc_id() -> None:
    """Falsifier: doc_id containing a single quote must not break DELETE SQL."""
    spark = _make_spark_mock()
    worker = _make_worker(spark)
    doc_id = "abc'OR'1=1"
    worker._delete_stale_corpus(doc_id)

    delete_sql = _delete_sql_calls(spark)[0]
    assert "abc''OR''1=1" in delete_sql
