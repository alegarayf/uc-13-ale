"""Additive Delta column migration tests — closes DELTA_METADATA_MISMATCH gap.

``CREATE TABLE IF NOT EXISTS`` is a no-op once a table exists on the cluster.
When a later subtask (e.g. M-RE2 T1 ``pipeline_thread_id``) widens the schema
in ``apply_ops_ddl.sql``, tables created by an earlier apply never receive the
new column and ``DeltaEvalStore.insert_run`` fails with
``DELTA_METADATA_MISMATCH`` on append. ``reconcile_additive_columns`` closes
that gap without dropping or rewriting existing rows.
"""

from __future__ import annotations

import pytest
from pyspark.sql.types import (
    ArrayType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)
from pyspark.sql.utils import AnalysisException

from eval.retrieval.scripts.apply_ops_ddl import (
    _spark_type_to_ddl,
    reconcile_additive_columns,
)


class _FakeSchema:
    def __init__(self, field_names: list[str]) -> None:
        self.fields = [type("F", (), {"name": name})() for name in field_names]


class _FakeTable:
    def __init__(self, field_names: list[str]) -> None:
        self.schema = _FakeSchema(field_names)


class _FakeSpark:
    def __init__(self, *, existing_columns: list[str] | None = None) -> None:
        self._existing_columns = existing_columns
        self.executed_sql: list[str] = []

    def table(self, fqn: str) -> _FakeTable:
        if self._existing_columns is None:
            raise AnalysisException("Table or view not found")
        return _FakeTable(self._existing_columns)

    def sql(self, statement: str) -> None:
        self.executed_sql.append(statement)


_TARGET_SCHEMA = StructType(
    [
        StructField("run_id", StringType(), False),
        StructField("pipeline_thread_id", StringType(), True),
        StructField("intent_count", IntegerType(), False),
        StructField("gated_intents", ArrayType(StringType()), False),
    ]
)


def test_spark_type_to_ddl_maps_scalar_and_array_types():
    assert _spark_type_to_ddl(StringType()) == "STRING"
    assert _spark_type_to_ddl(IntegerType()) == "INT"
    assert _spark_type_to_ddl(ArrayType(StringType())) == "ARRAY<STRING>"


def test_reconcile_adds_only_missing_columns():
    """Falsifier: must not re-add or touch columns already present on the live table."""
    spark = _FakeSpark(existing_columns=["run_id", "intent_count"])

    added = reconcile_additive_columns(spark, "uc13_ale.ops.retrieval_harness_runs", _TARGET_SCHEMA)

    assert added == ["pipeline_thread_id", "gated_intents"]
    assert spark.executed_sql == [
        "ALTER TABLE uc13_ale.ops.retrieval_harness_runs ADD COLUMNS (pipeline_thread_id STRING)",
        "ALTER TABLE uc13_ale.ops.retrieval_harness_runs ADD COLUMNS (gated_intents ARRAY<STRING>)",
    ]


def test_reconcile_is_noop_when_schema_already_current():
    spark = _FakeSpark(
        existing_columns=["run_id", "pipeline_thread_id", "intent_count", "gated_intents"]
    )

    added = reconcile_additive_columns(spark, "uc13_ale.ops.retrieval_harness_runs", _TARGET_SCHEMA)

    assert added == []
    assert spark.executed_sql == []


def test_reconcile_returns_empty_when_table_does_not_exist():
    """Table not yet created — CREATE TABLE IF NOT EXISTS in the DDL loop owns this case."""
    spark = _FakeSpark(existing_columns=None)

    added = reconcile_additive_columns(spark, "uc13_ale.ops.retrieval_harness_runs", _TARGET_SCHEMA)

    assert added == []
    assert spark.executed_sql == []


def test_apply_ops_ddl_runs_additive_migration_on_pre_existing_tables(monkeypatch, tmp_path):
    """Regression falsifier for the DELTA_METADATA_MISMATCH bug this migration closes.

    Simulates a table created before M-RE2 T1 (missing pipeline_thread_id): apply_ops_ddl
    must issue ALTER TABLE ADD COLUMNS for it, not silently no-op via CREATE TABLE IF NOT EXISTS.
    """
    from eval.retrieval import store as eval_store
    from eval.retrieval.scripts import apply_ops_ddl as ddl_module

    eval_store._delta_types()
    pre_existing_runs_columns = [
        f.name
        for f in eval_store._DELTA_RUNS_SCHEMA.fields
        if f.name != "pipeline_thread_id"
    ]

    spark = _FakeSpark(existing_columns=pre_existing_runs_columns)

    class _FakeBuilder:
        @staticmethod
        def getOrCreate():
            return spark

    class _FakeSparkSession:
        builder = _FakeBuilder()

    monkeypatch.setitem(
        __import__("sys").modules,
        "pyspark.sql",
        type("m", (), {"SparkSession": _FakeSparkSession})(),
    )

    sql_path = tmp_path / "apply_ops_ddl.sql"
    sql_path.write_text(
        "CREATE SCHEMA IF NOT EXISTS {catalog}.ops;\n"
        "CREATE TABLE IF NOT EXISTS {catalog}.ops.retrieval_harness_runs (run_id STRING);\n",
        encoding="utf-8",
    )

    ddl_module.apply_ops_ddl("uc13_ale", sql_path=sql_path)

    alter_statements = [s for s in spark.executed_sql if s.startswith("ALTER TABLE")]
    assert any("pipeline_thread_id" in s for s in alter_statements), (
        "apply_ops_ddl must additively add pipeline_thread_id to a table created "
        "before M-RE2 T1 — this is the exact DELTA_METADATA_MISMATCH regression"
    )
