"""Join-orphan rate measurement for Program Gate G4 (R-08 before/after falsifier).

Computes orphan chunk count/rate against live ``ingestion.chunks`` and
``classification.doc_relevance`` in two modes:

- ``file_name`` — pre-migration inner-join semantics
  (``chunks.file_name = doc_relevance.filename`` + ``company_name``)
- ``doc_id`` — post-migration inner-join semantics (``chunks.doc_id = doc_relevance.doc_id``)

Not imported by production code. Callable from a notebook cell or ``main()``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

JoinKey = Literal["file_name", "doc_id"]

_DEFAULT_CATALOG = "uc13_ale"
_DEFAULT_SCHEMA = "ingestion"
_DEFAULT_COMPANY = "Elder Care"


def _escape_sql_literal(value: str) -> str:
    return value.replace("'", "''")


@dataclass(frozen=True)
class ChunkRow:
    chunk_id: str
    file_name: str
    company_name: str
    doc_id: str


@dataclass(frozen=True)
class DocRelevanceRow:
    filename: str
    company_name: str
    doc_id: str


def _joined_chunk_ids(
    chunks: list[ChunkRow],
    relevance: list[DocRelevanceRow],
    key: JoinKey,
) -> set[str]:
    if key == "file_name":
        relevance_keys = {(row.filename, row.company_name) for row in relevance}
        return {
            chunk.chunk_id
            for chunk in chunks
            if (chunk.file_name, chunk.company_name) in relevance_keys
        }
    relevance_keys = {row.doc_id for row in relevance}
    return {chunk.chunk_id for chunk in chunks if chunk.doc_id in relevance_keys}


def _orphan_chunk_ids(
    chunks: list[ChunkRow],
    relevance: list[DocRelevanceRow],
    key: JoinKey,
) -> set[str]:
    joined = _joined_chunk_ids(chunks, relevance, key)
    return {chunk.chunk_id for chunk in chunks} - joined


def compute_orphan_stats(
    chunks: list[ChunkRow],
    relevance: list[DocRelevanceRow],
    company_name: str,
    key: JoinKey,
) -> dict[str, int | float | str]:
    """Spark-free orphan stats for a single company (unit-test seam)."""
    if key not in ("file_name", "doc_id"):
        raise ValueError(f"invalid join key: {key!r} — expected 'file_name' or 'doc_id'")

    company_chunks = [chunk for chunk in chunks if chunk.company_name == company_name]
    orphans = _orphan_chunk_ids(company_chunks, relevance, key)
    total = len(company_chunks)
    orphan_count = len(orphans)
    orphan_rate = (orphan_count / total) if total else 0.0
    return {
        "total_chunks": total,
        "orphan_count": orphan_count,
        "orphan_rate": orphan_rate,
        "key": key,
    }


def _orphan_count_sql(
    catalog: str,
    schema: str,
    company_name: str,
    key: JoinKey,
) -> str:
    company_literal = _escape_sql_literal(company_name)
    chunks_table = f"{catalog}.{schema}.chunks"
    relevance_table = f"{catalog}.classification.doc_relevance"

    if key == "file_name":
        join_predicate = (
            "c.file_name = r.filename AND c.company_name = r.company_name"
        )
        null_check = "r.filename IS NULL"
    else:
        join_predicate = "c.doc_id = r.doc_id"
        null_check = "r.doc_id IS NULL"

    return f"""
        SELECT
            COUNT(*) AS total_chunks,
            SUM(CASE WHEN {null_check} THEN 1 ELSE 0 END) AS orphan_count
        FROM {chunks_table} c
        LEFT JOIN {relevance_table} r
            ON {join_predicate}
        WHERE c.company_name = '{company_literal}'
    """


def measure_orphan_rate(
    spark: Any,
    catalog: str,
    schema: str,
    company_name: str,
    key: JoinKey,
) -> dict[str, int | float | str]:
    """Measure join-orphan rate for one company against live Delta tables."""
    if key not in ("file_name", "doc_id"):
        raise ValueError(f"invalid join key: {key!r} — expected 'file_name' or 'doc_id'")

    sql = _orphan_count_sql(catalog, schema, company_name, key)
    row = spark.sql(sql).collect()[0]
    total_chunks = int(row["total_chunks"])
    orphan_count = int(row["orphan_count"])
    orphan_rate = (orphan_count / total_chunks) if total_chunks else 0.0
    return {
        "total_chunks": total_chunks,
        "orphan_count": orphan_count,
        "orphan_rate": orphan_rate,
        "key": key,
    }


def print_orphan_report(label: str, result: dict[str, int | float | str]) -> None:
    """Pretty-print one orphan-rate measurement."""
    print(f"\n{'═' * 62}")
    print(f"  Join Orphan Report — {label}  (key={result['key']})")
    print(f"{'═' * 62}")
    print(f"  Total chunks : {result['total_chunks']}")
    print(f"  Orphan count : {result['orphan_count']}")
    print(f"  Orphan rate  : {result['orphan_rate']:.4%}")


def main(
    *,
    spark: Any | None = None,
    catalog: str | None = None,
    schema: str | None = None,
    company_name: str | None = None,
) -> dict[str, dict[str, int | float | str]]:
    """Notebook-callable entry: print before/after orphan rates for one company."""
    if spark is None:
        from pyspark.sql import SparkSession

        spark = SparkSession.getActiveSession()
        if spark is None:
            spark = SparkSession.builder.getOrCreate()

    catalog = catalog or os.environ.get("catalog", _DEFAULT_CATALOG)
    schema = schema or os.environ.get("schema", _DEFAULT_SCHEMA)
    company_name = company_name or os.environ.get("sp_company_name", _DEFAULT_COMPANY)

    before = measure_orphan_rate(spark, catalog, schema, company_name, "file_name")
    after = measure_orphan_rate(spark, catalog, schema, company_name, "doc_id")

    print_orphan_report("before (file_name key)", before)
    print_orphan_report("after (doc_id key)", after)

    return {"before": before, "after": after}
