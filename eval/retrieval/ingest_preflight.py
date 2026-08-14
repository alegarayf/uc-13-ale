"""Two-backend ingest preflight — spec §8.4 item 34 / M4 T5."""

from __future__ import annotations

import argparse
import sys
from typing import Any, Literal, Protocol

from eval.retrieval.companies import canonical_company_slug
from eval.retrieval.errors import EvalError
from eval.retrieval.trust_statement import IngestProbeResult

__all__ = ["IngestPreflightError", "IngestProbeResult", "run_ingest_preflight"]

_DEFAULT_CATALOG = "uc13_ale"
_DEFAULT_SCHEMA = "ingestion"
_BACKENDS = frozenset({"sql_chunk_count", "doc_status"})


class IngestPreflightError(EvalError):
    """Programmer error: unknown backend or wrong injection for the chosen backend."""


class SqlExecutor(Protocol):
    def __call__(self, sql: str) -> list[list[str | None]]: ...


def _escape_sql_literal(value: str) -> str:
    return value.replace("'", "''")


def _ingest_probe_sql(catalog: str, company_display: str) -> str:
    company_literal = _escape_sql_literal(company_display)
    return f"""
WITH ingested AS (
  SELECT DISTINCT c.doc_id
  FROM {catalog}.ingestion.chunks c
  WHERE c.company_name = '{company_literal}'
)
SELECT
  (SELECT COUNT(DISTINCT doc_id) FROM {catalog}.classification.doc_relevance
   WHERE company_name = '{company_literal}' AND should_parse = true) AS denominator,
  (SELECT COUNT(1) FROM ingested i
   WHERE i.doc_id IN (
     SELECT doc_id FROM {catalog}.classification.doc_relevance
     WHERE company_name = '{company_literal}' AND should_parse = true
   )) AS ingested_count
"""


def _ingest_per_doc_type_sql(catalog: str, company_display: str) -> str:
    company_literal = _escape_sql_literal(company_display)
    return f"""
WITH expected AS (
  SELECT doc_id, explode(workstream) AS doc_type
  FROM {catalog}.classification.doc_relevance
  WHERE company_name = '{company_literal}' AND should_parse = true
),
ingested AS (
  SELECT DISTINCT c.doc_id
  FROM {catalog}.ingestion.chunks c
  WHERE c.company_name = '{company_literal}'
)
SELECT e.doc_type,
       COUNT(DISTINCT e.doc_id) AS expected,
       COUNT(DISTINCT CASE WHEN i.doc_id IS NOT NULL THEN e.doc_id END) AS ingested
FROM expected e
LEFT JOIN ingested i ON e.doc_id = i.doc_id
GROUP BY e.doc_type
ORDER BY e.doc_type
"""


def _doc_status_sql(catalog: str, schema: str, company_display: str) -> str:
    company_literal = _escape_sql_literal(company_display)
    table = f"{catalog}.{schema}.doc_status"
    return f"""
        SELECT status, COUNT(*) AS cnt
        FROM {table}
        WHERE company_name = '{company_literal}'
        GROUP BY status
        ORDER BY status
    """


def _run_sql_chunk_count_backend(
    execute_sql: SqlExecutor,
    *,
    company_slug: str,
    catalog: str,
    company_display: str,
) -> IngestProbeResult:
    """§8.4 sql_chunk_count backend; never raises across the boundary."""
    try:
        count_rows = execute_sql(_ingest_probe_sql(catalog, company_display))
        if not count_rows or len(count_rows[0]) < 2:
            return IngestProbeResult(
                company=company_slug,
                catalog=catalog,
                backend="sql_chunk_count",
                status="probe_failed",
            )
        denominator = int(count_rows[0][0] or 0)
        ingested_count = int(count_rows[0][1] or 0)
        if denominator <= 0:
            return IngestProbeResult(
                company=company_slug,
                catalog=catalog,
                backend="sql_chunk_count",
                status="denominator_undefined",
            )
        per_doc_type: dict[str, dict[str, int]] = {}
        breakdown_rows = execute_sql(_ingest_per_doc_type_sql(catalog, company_display))
        for row in breakdown_rows:
            if len(row) < 3 or row[0] is None:
                continue
            per_doc_type[str(row[0])] = {
                "expected": int(row[1] or 0),
                "ingested": int(row[2] or 0),
            }
        completeness = ingested_count / denominator
        return IngestProbeResult(
            company=company_slug,
            catalog=catalog,
            backend="sql_chunk_count",
            status="measured",
            completeness=completeness,
            denominator=denominator,
            per_doc_type=per_doc_type,
        )
    except Exception:  # noqa: BLE001 - §8.4 boundary contract
        return IngestProbeResult(
            company=company_slug,
            catalog=catalog,
            backend="sql_chunk_count",
            status="probe_failed",
        )


def _run_doc_status_backend(
    spark: Any,
    *,
    company_slug: str,
    catalog: str,
    company_display: str,
    schema: str = _DEFAULT_SCHEMA,
) -> IngestProbeResult:
    """§8.4 doc_status backend; denominator undefined until sibling lands expected count."""
    try:
        spark.sql(_doc_status_sql(catalog, schema, company_display)).collect()
        return IngestProbeResult(
            company=company_slug,
            catalog=catalog,
            backend="doc_status",
            status="denominator_undefined",
        )
    except Exception:  # noqa: BLE001 - §8.4 boundary contract
        return IngestProbeResult(
            company=company_slug,
            catalog=catalog,
            backend="doc_status",
            status="probe_failed",
        )


def run_ingest_preflight(
    *,
    backend: Literal["sql_chunk_count", "doc_status"],
    company_slug: str,
    catalog: str,
    company_display: str,
    execute_sql: SqlExecutor | None = None,
    spark: Any | None = None,
    schema: str = _DEFAULT_SCHEMA,
) -> IngestProbeResult:
    """Run one §8.4 ingest preflight backend; probe outcomes never raise."""
    if backend not in _BACKENDS:
        raise IngestPreflightError(f"unknown ingest preflight backend: {backend!r}")

    if backend == "sql_chunk_count":
        if execute_sql is None:
            raise IngestPreflightError("sql_chunk_count backend requires execute_sql")
        if spark is not None:
            raise IngestPreflightError("sql_chunk_count backend must not receive spark")
        return _run_sql_chunk_count_backend(
            execute_sql,
            company_slug=company_slug,
            catalog=catalog,
            company_display=company_display,
        )

    if execute_sql is not None:
        raise IngestPreflightError("doc_status backend must not receive execute_sql")
    if spark is None:
        raise IngestPreflightError("doc_status backend requires spark")
    return _run_doc_status_backend(
        spark,
        company_slug=company_slug,
        catalog=catalog,
        company_display=company_display,
        schema=schema,
    )


def format_preflight_summary(result: IngestProbeResult) -> str:
    parts = [
        f"ingest_preflight: {result.company} @ {result.catalog}",
        f"backend={result.backend}",
        f"status={result.status}",
    ]
    if result.completeness is not None:
        parts.append(f"completeness={result.completeness:.4f}")
    if result.denominator is not None:
        parts.append(f"denominator={result.denominator}")
    return " ".join(parts)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eval.retrieval.ingest_preflight",
        description="Per-company ingest preflight probe (§8.4 sql_chunk_count or doc_status).",
    )
    parser.add_argument(
        "--company",
        required=True,
        help='Company display name (e.g. "Elder Care")',
    )
    parser.add_argument(
        "--catalog",
        default=_DEFAULT_CATALOG,
        help=f"Unity Catalog name (default: {_DEFAULT_CATALOG})",
    )
    parser.add_argument(
        "--backend",
        required=True,
        choices=sorted(_BACKENDS),
        help="Preflight backend to run",
    )
    return parser


def _live_execute_sql(catalog: str) -> SqlExecutor:
    from eval.retrieval.trust_statement import databricks_sql_executor

    return databricks_sql_executor(catalog)


def _live_spark() -> Any:
    from pyspark.sql import SparkSession

    spark = SparkSession.getActiveSession()
    if spark is None:
        spark = SparkSession.builder.getOrCreate()
    return spark


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        company_slug = canonical_company_slug(args.company)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    try:
        if args.backend == "sql_chunk_count":
            result = run_ingest_preflight(
                backend="sql_chunk_count",
                company_slug=company_slug,
                catalog=args.catalog,
                company_display=args.company,
                execute_sql=_live_execute_sql(args.catalog),
            )
        else:
            result = run_ingest_preflight(
                backend="doc_status",
                company_slug=company_slug,
                catalog=args.catalog,
                company_display=args.company,
                spark=_live_spark(),
            )
    except IngestPreflightError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(format_preflight_summary(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
