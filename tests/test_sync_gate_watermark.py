"""SyncGate watermark contract tests (M2).

T1: StatusStore catalog-wide predicate/candidate reads.
T2: sync_state watermark read/advance.
T3: SyncGate decision block, _parse_bool, __main__ guard.
T6 extends with additional SyncGate paths.
"""

from __future__ import annotations

import sys
import types
import uuid
from datetime import datetime, timezone
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
        "StringType",
        "StructField",
        "StructType",
        "TimestampType",
        "IntegerType",
        "LongType",
        "BooleanType",
    ):
        setattr(_types_mod, _name, _StubSparkType)

    _pyspark_mod.sql = _sql_mod
    sys.modules["pyspark"] = _pyspark_mod
    sys.modules["pyspark.sql"] = _sql_mod
    sys.modules["pyspark.sql.types"] = _types_mod

from status_store import COMPLETE, StatusStore  # noqa: E402
import sync_state  # noqa: E402
import ingestion_parser as ip  # noqa: E402

_SCHEMA = "ingestion"
_CATALOG = "uc13"
_TS_1 = datetime(2026, 8, 4, 12, 0, 0, tzinfo=timezone.utc)
_TS_2 = datetime(2026, 8, 4, 18, 0, 0, tzinfo=timezone.utc)
_RUN_1 = "run-abc"
_RUN_2 = "run-def"


def _assert_catalog_wide_sql(sql: str) -> None:
    normalized = " ".join(sql.split())
    assert "company_name =" not in normalized.lower()
    assert f"status = '{COMPLETE}'" in normalized


def _make_status_store(*, sql_handler) -> StatusStore:
    spark = MagicMock()
    spark.sql.side_effect = sql_handler
    return StatusStore(spark, "uc13_ale", _SCHEMA)


def test_catalog_wide_predicate_no_company_filter() -> None:
    """Company A dormant + company B recent COMPLETE: predicate is catalog-wide."""
    captured: list[str] = []
    watermark = datetime(2025, 1, 1, 0, 0, 0)

    def sql_handler(query: str):
        captured.append(query)
        _assert_catalog_wide_sql(query)
        if "LIMIT 1" in query:
            return MagicMock(collect=lambda: [SimpleNamespace(n=1)])
        pytest.fail("unexpected SQL in predicate test")

    store = _make_status_store(sql_handler=sql_handler)
    since_result = store.has_newer_complete_than(watermark)
    cold_start_result = store.has_newer_complete_than(None)

    assert since_result is True
    assert cold_start_result is True
    assert len(captured) == 2
    for sql in captured:
        _assert_catalog_wide_sql(sql)


def test_catalog_wide_candidate_no_company_filter() -> None:
    """MAX(updated_at) must reflect company B's recent COMPLETE, not company A's stale row."""
    captured: list[str] = []
    recent_updated_at = datetime(2026, 6, 15, 9, 30, 0)

    def sql_handler(query: str):
        captured.append(query)
        _assert_catalog_wide_sql(query)
        assert "MAX(updated_at)" in query
        return MagicMock(
            collect=lambda: [SimpleNamespace(max_updated_at=recent_updated_at)]
        )

    store = _make_status_store(sql_handler=sql_handler)
    result = store.max_complete_updated_at()

    assert result == recent_updated_at
    assert len(captured) == 1
    _assert_catalog_wide_sql(captured[0])


class _InMemorySyncStateSpark:
    """Minimal Spark stub: one MERGE-keyed row per catalog_scope."""

    def __init__(self) -> None:
        self._rows: dict[str, dict] = {}
        self._pending_row: dict | None = None
        self.sql_calls: list[str] = []

    def createDataFrame(self, rows, schema=None):
        self._pending_row = rows[0]
        frame = MagicMock()
        frame.createOrReplaceTempView = MagicMock()
        return frame

    def sql(self, query: str):
        self.sql_calls.append(query)
        result = MagicMock()
        if query.strip().upper().startswith("SELECT"):
            escaped = _CATALOG.replace("'", "''")
            marker = f"catalog_scope = '{escaped}'"
            if marker not in query:
                result.collect.return_value = []
                return result
            stored = self._rows.get(_CATALOG)
            if stored is None:
                result.collect.return_value = []
            else:
                result.collect.return_value = [
                    SimpleNamespace(
                        last_successful_sync=stored["last_successful_sync"],
                        run_id=stored["run_id"],
                    )
                ]
            return result

        if "MERGE INTO" in query.upper():
            assert self._pending_row is not None
            key = self._pending_row["catalog_scope"]
            self._rows[key] = dict(self._pending_row)
            assert "ON target.catalog_scope = source.catalog_scope" in query
        return result


def test_watermark_read_no_row_returns_none() -> None:
    spark = MagicMock()
    spark.sql.return_value.collect.return_value = []

    assert sync_state.read_watermark(spark, _CATALOG, _SCHEMA) == (None, None)

    sql = spark.sql.call_args[0][0]
    assert f"{_CATALOG}.{_SCHEMA}.sync_state" in sql
    assert "catalog_scope = 'uc13'" in sql


def test_watermark_advance_persists_and_is_idempotent() -> None:
    spark = _InMemorySyncStateSpark()

    sync_state.advance_watermark(spark, _CATALOG, _SCHEMA, _TS_1, _RUN_1)
    assert spark._pending_row["catalog_scope"] == _CATALOG
    assert len(spark._rows) == 1
    ts_after_first, run_after_first = sync_state.read_watermark(spark, _CATALOG, _SCHEMA)
    assert ts_after_first == _TS_1
    assert run_after_first == _RUN_1

    sync_state.advance_watermark(spark, _CATALOG, _SCHEMA, _TS_2, _RUN_2)
    assert len(spark._rows) == 1
    ts_after_second, run_after_second = sync_state.read_watermark(spark, _CATALOG, _SCHEMA)
    assert ts_after_second == _TS_2
    assert run_after_second == _RUN_2

    merge_sql = [q for q in spark.sql_calls if "MERGE INTO" in q.upper()]
    assert len(merge_sql) == 2


def test_advance_watermark_propagates_sql_failure() -> None:
    spark = MagicMock()
    spark.createDataFrame.return_value.createOrReplaceTempView = MagicMock()
    spark.sql.side_effect = RuntimeError("simulated MERGE failure")

    with pytest.raises(RuntimeError, match="simulated MERGE failure"):
        sync_state.advance_watermark(
            spark, _CATALOG, _SCHEMA, _TS_1, f"run-{uuid.uuid4().hex}"
        )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("true", True),
        ("TRUE", True),
        ("1", True),
        ("yes", True),
        ("Yes", True),
        ("false", False),
        ("0", False),
        ("no", False),
        ("", False),
        ("maybe", False),
    ],
)
def test_parse_bool_round_trip(raw: str, expected: bool) -> None:
    assert ip._parse_bool(raw) is expected


def test_dunder_main_wraps_fatal_exception_in_sys_exit_1(capsys) -> None:
    with patch("ingestion_parser.main", side_effect=RuntimeError("boom")):
        with pytest.raises(SystemExit) as exc_info:
            ip._run_as_script()
        assert exc_info.value.code == 1
    captured = capsys.readouterr().out
    assert "✗ Fatal error — halting" in captured
    assert "boom" in captured


def test_run_as_script_wraps_index_sync_error_in_sys_exit_1(capsys) -> None:
    with patch(
        "ingestion_parser.main",
        side_effect=ip.IndexSyncError("pipeline state=FAILED indexed=0/100"),
    ):
        with pytest.raises(SystemExit) as exc_info:
            ip._run_as_script()
        assert exc_info.value.code == 1
    captured = capsys.readouterr().out
    assert "✗ Fatal error — halting" in captured
    assert "FAILED" in captured


class _ProductionSparkStub:
    """Non-mock Spark so SyncGate watermark logic is exercised."""

    __module__ = "pyspark.sql.session"

    def __init__(self, *, has_newer: bool, max_updated_at: datetime | None) -> None:
        self._has_newer = has_newer
        self._max_updated_at = max_updated_at

    def sql(self, query: str):
        result = MagicMock()
        if "LIMIT 1" in query:
            if self._has_newer:
                result.collect.return_value = [SimpleNamespace(n=1)]
            else:
                result.collect.return_value = []
        elif "MAX(updated_at)" in query:
            result.collect.return_value = [
                SimpleNamespace(max_updated_at=self._max_updated_at)
            ]
        else:
            result.collect.return_value = []
        return result

    def createDataFrame(self, rows, schema=None):
        frame = MagicMock()
        frame.createOrReplaceTempView = MagicMock()
        return frame


def _get_param_side_effect(overrides: dict[str, str]):
    base = {
        "sp_company_name": "TestCo",
        "catalog": _CATALOG,
        "schema": _SCHEMA,
        "embedding_endpoint": "databricks-bge-large-en",
        "vision_endpoint": "",
        "parse_priority_tiers": "all",
        "force": "none",
        "coverage_per_workstream": "3",
        "skip_sync": "false",
        "sync_only": "false",
    }
    base.update(overrides)

    def _side_effect(key: str, default=None):
        return base.get(key, default)

    return _side_effect


@patch("sync_state.advance_watermark")
@patch("sync_state.read_watermark", return_value=(_TS_1, _RUN_1))
@patch("ingestion_parser._wait_for_index_sync")
@patch("sync_state.ensure_sync_state")
@patch("status_store.ensure_doc_status")
@patch("ingestion_parser.get_param", side_effect=_get_param_side_effect({}))
@patch("ingestion_parser.find_repo_root", return_value=str(_REPO_ROOT))
@patch("pyspark.sql.SparkSession.getActiveSession")
@patch("parse_manifest.ParseManifest")
def test_main_watermark_skip_and_sync_paths(
    mock_manifest_cls,
    mock_get_active_session,
    _mock_find_repo_root,
    _mock_get_param,
    _mock_ensure_doc_status,
    _mock_ensure_sync_state,
    mock_wait_for_sync,
    mock_read_watermark,
    mock_advance_watermark,
    capsys,
) -> None:
    mock_manifest_cls.return_value.build.return_value = []

    spark = _ProductionSparkStub(has_newer=False, max_updated_at=_TS_2)
    mock_get_active_session.return_value = spark

    ip.main()

    captured = capsys.readouterr().out
    assert "no COMPLETE docs newer than watermark" in captured
    mock_wait_for_sync.assert_not_called()
    mock_advance_watermark.assert_not_called()

    mock_wait_for_sync.reset_mock()
    mock_advance_watermark.reset_mock()
    mock_read_watermark.return_value = (_TS_1, _RUN_1)

    spark_sync = _ProductionSparkStub(has_newer=True, max_updated_at=_TS_2)
    mock_get_active_session.return_value = spark_sync

    ip.main()

    captured = capsys.readouterr().out
    mock_wait_for_sync.assert_called_once()
    mock_advance_watermark.assert_called_once_with(
        spark_sync, _CATALOG, _SCHEMA, _TS_2, mock_advance_watermark.call_args[0][4]
    )
    assert "watermark advanced" in captured

    mock_wait_for_sync.reset_mock()
    mock_advance_watermark.reset_mock()

    with patch(
        "ingestion_parser.get_param",
        side_effect=_get_param_side_effect({"skip_sync": "true"}),
    ):
        ip.main()

    captured = capsys.readouterr().out
    assert "skip_sync set" in captured
    mock_wait_for_sync.assert_not_called()

    mock_wait_for_sync.reset_mock()
    mock_advance_watermark.reset_mock()
    mock_read_watermark.return_value = (_TS_1, _RUN_1)

    with patch(
        "ingestion_parser.get_param",
        side_effect=_get_param_side_effect({"sync_only": "true"}),
    ):
        ip.main()

    captured = capsys.readouterr().out
    assert "Sync Only" in captured
    assert "sync_only set" in captured
    mock_wait_for_sync.assert_called_once()
    mock_advance_watermark.assert_called_once()


@patch("sync_state.advance_watermark")
@patch("sync_state.read_watermark", return_value=(_TS_1, _RUN_1))
@patch("ingestion_parser._wait_for_index_sync")
@patch("sync_state.ensure_sync_state")
@patch("status_store.ensure_doc_status")
@patch("ingestion_parser.get_param", side_effect=_get_param_side_effect({}))
@patch("ingestion_parser.find_repo_root", return_value=str(_REPO_ROOT))
@patch("pyspark.sql.SparkSession.getActiveSession")
@patch("parse_manifest.ParseManifest")
def test_two_consecutive_no_change_runs_skip_sync_without_advancing_watermark(
    mock_manifest_cls,
    mock_get_active_session,
    _mock_find_repo_root,
    _mock_get_param,
    _mock_ensure_doc_status,
    _mock_ensure_sync_state,
    mock_wait_for_sync,
    _mock_read_watermark,
    mock_advance_watermark,
    capsys,
) -> None:
    """Runnable falsifier: back-to-back no-change runs must not trigger sync or advance."""
    mock_manifest_cls.return_value.build.return_value = []
    spark = _ProductionSparkStub(has_newer=False, max_updated_at=_TS_2)
    mock_get_active_session.return_value = spark

    ip.main()
    first_out = capsys.readouterr().out
    ip.main()
    second_out = capsys.readouterr().out

    for captured in (first_out, second_out):
        assert "no COMPLETE docs newer than watermark" in captured
    mock_wait_for_sync.assert_not_called()
    mock_advance_watermark.assert_not_called()


@patch("sync_state.advance_watermark")
@patch("sync_state.read_watermark", return_value=(_TS_1, _RUN_1))
@patch("ingestion_parser._wait_for_index_sync")
@patch("sync_state.ensure_sync_state")
@patch("status_store.ensure_doc_status")
@patch("ingestion_parser.find_repo_root", return_value=str(_REPO_ROOT))
@patch("pyspark.sql.SparkSession.getActiveSession")
@patch("parse_manifest.ParseManifest")
def test_skip_sync_then_plain_run_triggers_sync(
    mock_manifest_cls,
    mock_get_active_session,
    _mock_find_repo_root,
    _mock_ensure_doc_status,
    _mock_ensure_sync_state,
    mock_wait_for_sync,
    mock_read_watermark,
    mock_advance_watermark,
    capsys,
) -> None:
    """Runnable falsifier: skip_sync run must not block a later plain run from syncing."""
    mock_manifest_cls.return_value.build.return_value = []
    spark_skip = _ProductionSparkStub(has_newer=True, max_updated_at=_TS_2)
    mock_get_active_session.return_value = spark_skip

    with patch(
        "ingestion_parser.get_param",
        side_effect=_get_param_side_effect({"skip_sync": "true"}),
    ):
        ip.main()

    skip_out = capsys.readouterr().out
    assert "skip_sync set" in skip_out
    mock_wait_for_sync.assert_not_called()
    mock_advance_watermark.assert_not_called()

    mock_wait_for_sync.reset_mock()
    mock_advance_watermark.reset_mock()
    mock_read_watermark.return_value = (_TS_1, _RUN_1)

    spark_sync = _ProductionSparkStub(has_newer=True, max_updated_at=_TS_2)
    mock_get_active_session.return_value = spark_sync

    with patch(
        "ingestion_parser.get_param",
        side_effect=_get_param_side_effect({}),
    ):
        ip.main()

    plain_out = capsys.readouterr().out
    assert "skip_sync set" not in plain_out
    mock_wait_for_sync.assert_called_once()
    mock_advance_watermark.assert_called_once()


@patch("sync_state.advance_watermark")
@patch("sync_state.read_watermark", return_value=(None, None))
@patch("ingestion_parser._wait_for_index_sync")
@patch("sync_state.ensure_sync_state")
@patch("status_store.ensure_doc_status")
@patch("ingestion_parser.get_param", side_effect=_get_param_side_effect({}))
@patch("ingestion_parser.find_repo_root", return_value=str(_REPO_ROOT))
@patch("pyspark.sql.SparkSession.getActiveSession")
@patch("parse_manifest.ParseManifest")
def test_has_newer_complete_than_none_empty_catalog_returns_false(
    mock_manifest_cls,
    mock_get_active_session,
    _mock_find_repo_root,
    _mock_get_param,
    _mock_ensure_doc_status,
    _mock_ensure_sync_state,
    mock_wait_for_sync,
    _mock_read_watermark,
    mock_advance_watermark,
    capsys,
) -> None:
    """Cold-start with zero COMPLETE rows: predicate false, sync skipped naturally."""
    mock_manifest_cls.return_value.build.return_value = []
    spark = _ProductionSparkStub(has_newer=False, max_updated_at=None)
    mock_get_active_session.return_value = spark

    ip.main()

    captured = capsys.readouterr().out
    assert "no COMPLETE docs newer than watermark" in captured
    mock_wait_for_sync.assert_not_called()
    mock_advance_watermark.assert_not_called()


@patch("sync_state.advance_watermark")
@patch("sync_state.read_watermark", return_value=(_TS_1, _RUN_1))
@patch("ingestion_parser._wait_for_index_sync")
@patch("sync_state.ensure_sync_state")
@patch("status_store.ensure_doc_status")
@patch("ingestion_parser.get_param", side_effect=_get_param_side_effect({}))
@patch("ingestion_parser.find_repo_root", return_value=str(_REPO_ROOT))
@patch("pyspark.sql.SparkSession.getActiveSession")
@patch("doc_worker.DocWorker")
@patch("parse_manifest.ParseManifest")
def test_m_phv1_success_stdout_binding_strings(
    mock_manifest_cls,
    mock_doc_worker_cls,
    mock_get_active_session,
    _mock_find_repo_root,
    _mock_get_param,
    _mock_ensure_doc_status,
    _mock_ensure_sync_state,
    mock_wait_for_sync,
    _mock_read_watermark,
    _mock_advance_watermark,
    capsys,
) -> None:
    """M-PHV1 success row: chunk/embed save lines coexist with ✓ Index ready."""
    from doc_worker import RunSummary

    mock_manifest_cls.return_value.build.return_value = [MagicMock()]
    mock_worker = MagicMock()
    mock_doc_worker_cls.return_value = mock_worker
    mock_worker.run.return_value = RunSummary(chunk_counts_by_source_type={"text": 3})

    def _print_index_ready(**_kwargs):
        print("✓ Index ready and current — uc13.ingestion.embeddings_index")

    mock_wait_for_sync.side_effect = _print_index_ready

    spark = _ProductionSparkStub(has_newer=True, max_updated_at=_TS_2)
    mock_get_active_session.return_value = spark

    ip.main()

    captured = capsys.readouterr().out
    assert "✓ Saved 3 chunks" in captured
    assert "✓ Saved 3 embeddings" in captured
    assert "✓ Index ready" in captured
    assert "watermark advanced" in captured
