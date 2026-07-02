"""Apply uc13.ops DDL on a Databricks cluster — plan §2 CLI / D7-A."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any


def _spark_type_to_ddl(spark_type: Any) -> str:
    """Map a pyspark DataType to Delta SQL column-type syntax for ALTER TABLE."""
    from pyspark.sql.types import (
        ArrayType,
        BooleanType,
        DoubleType,
        IntegerType,
        StringType,
        TimestampType,
    )

    if isinstance(spark_type, ArrayType):
        return f"ARRAY<{_spark_type_to_ddl(spark_type.elementType)}>"
    simple = {
        StringType: "STRING",
        BooleanType: "BOOLEAN",
        DoubleType: "DOUBLE",
        IntegerType: "INT",
        TimestampType: "TIMESTAMP",
    }
    for cls, ddl in simple.items():
        if isinstance(spark_type, cls):
            return ddl
    raise ValueError(f"unsupported type for additive column migration: {spark_type}")


def reconcile_additive_columns(spark: Any, table_fqn: str, target_schema: Any) -> list[str]:
    """Add columns present in ``target_schema`` but missing on the live Delta table.

    ``CREATE TABLE IF NOT EXISTS`` is a no-op once a table exists, so schema
    additions landed by later subtasks (e.g. ``pipeline_thread_id`` in M-RE2 T1)
    never reach tables created by an earlier DDL apply. This closes that gap
    without dropping or rewriting existing rows.
    """
    from pyspark.sql.utils import AnalysisException

    try:
        live_fields = {f.name for f in spark.table(table_fqn).schema.fields}
    except AnalysisException:
        return []

    added: list[str] = []
    for field in target_schema.fields:
        if field.name in live_fields:
            continue
        ddl_type = _spark_type_to_ddl(field.dataType)
        spark.sql(f"ALTER TABLE {table_fqn} ADD COLUMNS ({field.name} {ddl_type})")
        added.append(field.name)
    return added


def _strip_leading_sql_comments(block: str) -> str:
    """Drop full-line ``--`` comments; keep executable SQL in the block."""
    lines = [
        line
        for line in block.splitlines()
        if line.strip() and not line.strip().startswith("--")
    ]
    return "\n".join(lines).strip()


def _load_statements(sql_path: Path, catalog: str) -> list[str]:
    text = sql_path.read_text(encoding="utf-8")
    text = text.replace("{catalog}", catalog)
    statements: list[str] = []
    for raw in re.split(r";\s*\n", text):
        statement = _strip_leading_sql_comments(raw.strip())
        if statement:
            statements.append(statement)
    return statements


def apply_ops_ddl(catalog: str = "uc13", *, sql_path: Path | None = None) -> int:
    try:
        from pyspark.sql import SparkSession
    except ImportError as exc:
        raise RuntimeError("apply_ops_ddl requires a Databricks/PySpark runtime") from exc

    spark = SparkSession.builder.getOrCreate()
    ddl_path = sql_path or Path(__file__).with_name("apply_ops_ddl.sql")
    statements = _load_statements(ddl_path, catalog)
    for statement in statements:
        print(f"[apply_ops_ddl] executing: {statement.splitlines()[0]}")
        spark.sql(statement)
    print(f"[apply_ops_ddl] applied {len(statements)} statements to {catalog}.ops")

    from eval.retrieval import store as _eval_store

    _eval_store._delta_types()  # populates module-level _DELTA_*_SCHEMA globals
    for table_name, schema in (
        ("retrieval_harness_runs", _eval_store._DELTA_RUNS_SCHEMA),
        ("retrieval_provenance", _eval_store._DELTA_PROVENANCE_SCHEMA),
    ):
        added = reconcile_additive_columns(spark, f"{catalog}.ops.{table_name}", schema)
        if added:
            print(f"[apply_ops_ddl] additive migration on {table_name}: added {added}")

    return len(statements)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply uc13.ops RE² DDL (Appendix I)")
    parser.add_argument(
        "--catalog",
        default="uc13",
        help="Unity Catalog name (default: uc13)",
    )
    parser.add_argument(
        "--sql-path",
        type=Path,
        default=None,
        help="Optional override for apply_ops_ddl.sql",
    )
    args = parser.parse_args(argv)
    try:
        apply_ops_ddl(args.catalog, sql_path=args.sql_path)
    except RuntimeError as exc:
        print(f"[apply_ops_ddl] ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
