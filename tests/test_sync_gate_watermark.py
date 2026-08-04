"""SyncGate watermark contract tests (M2).

T1: StatusStore catalog-wide predicate/candidate reads (this packet).
T2/T3/T6 extend this file with sync_state and SyncGate decision-block tests.
"""

from __future__ import annotations

import sys
import types
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

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

_SCHEMA = "ingestion"


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
