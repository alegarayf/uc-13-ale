"""Per-company attestation queries for Program Gate G5 (spec §15) and vision-share companion.

G5-gated attestation: ``doc_status`` status histogram + non-COMPLETE error detail.
Informational companion: ``chunks`` source_type composition (vision vs text/table).

Not imported by production code. Callable from a notebook cell or ``main()``.
"""

from __future__ import annotations

import argparse
import os
from typing import Any

_DEFAULT_CATALOG = "uc13_ale"
_DEFAULT_SCHEMA = "ingestion"
_DEFAULT_COMPANY = "Elder Care"

_TERMINAL_FAILURE_STATUSES = frozenset({"FAILED", "ZERO_CHUNKS"})
_TERMINAL_STATUSES = frozenset({"COMPLETE"}) | _TERMINAL_FAILURE_STATUSES


def _escape_sql_literal(value: str) -> str:
    return value.replace("'", "''")


def _attestation_status_sql(catalog: str, schema: str, company_name: str) -> str:
    company_literal = _escape_sql_literal(company_name)
    table = f"{catalog}.{schema}.doc_status"
    return f"""
        SELECT status, COUNT(*) AS cnt
        FROM {table}
        WHERE company_name = '{company_literal}'
        GROUP BY status
        ORDER BY status
    """


def _attestation_error_sql(catalog: str, schema: str, company_name: str) -> str:
    company_literal = _escape_sql_literal(company_name)
    table = f"{catalog}.{schema}.doc_status"
    return f"""
        SELECT status, error, COUNT(*) AS cnt
        FROM {table}
        WHERE company_name = '{company_literal}'
          AND status != 'COMPLETE'
        GROUP BY status, error
        ORDER BY status, error
    """


def _vision_share_sql(catalog: str, schema: str, company_name: str) -> str:
    company_literal = _escape_sql_literal(company_name)
    table = f"{catalog}.{schema}.chunks"
    return f"""
        SELECT source_type, COUNT(*) AS cnt
        FROM {table}
        WHERE company_name = '{company_literal}'
        GROUP BY source_type
        ORDER BY source_type
    """


def run_attestation_query(
    spark: Any,
    catalog: str,
    schema: str,
    company_name: str,
) -> dict[str, Any]:
    """G5-gated attestation: status histogram + non-COMPLETE error detail."""
    status_sql = _attestation_status_sql(catalog, schema, company_name)
    status_rows = spark.sql(status_sql).collect()

    status_counts: dict[str, int] = {}
    for row in status_rows:
        status_counts[str(row["status"])] = int(row["cnt"])

    error_sql = _attestation_error_sql(catalog, schema, company_name)
    error_rows = spark.sql(error_sql).collect()

    failed_details: list[dict[str, Any]] = []
    for row in error_rows:
        failed_details.append(
            {
                "status": str(row["status"]),
                "error": row["error"],
                "count": int(row["cnt"]),
            }
        )

    total = sum(status_counts.values())
    return {
        "status_counts": status_counts,
        "total": total,
        "failed_details": failed_details,
    }


def run_vision_share_query(
    spark: Any,
    catalog: str,
    schema: str,
    company_name: str,
) -> dict[str, Any]:
    """Informational companion: corpus-level chunk source_type composition."""
    sql = _vision_share_sql(catalog, schema, company_name)
    rows = spark.sql(sql).collect()

    source_type_counts: dict[str, int] = {}
    for row in rows:
        source_type_counts[str(row["source_type"])] = int(row["cnt"])

    return {
        "source_type_counts": source_type_counts,
        "total_chunks": sum(source_type_counts.values()),
    }


def format_attestation_phv_line(result: dict[str, Any]) -> str:
    """PHV target shape: *\"N approved, M complete, K failed with reason X.\"*

    Any row in a non-terminal status (``PENDING``/``PARSING``/``EMBEDDING``, or an
    unrecognized status) is counted into "approved" but has not reached a terminal,
    explained state — which is exactly what G5 attests to. Such rows get their own
    trailing clause so a stranded document can never read as a rounding difference
    between the approved and complete counts.
    """
    total = int(result["total"])
    status_counts = result["status_counts"]
    complete = int(status_counts.get("COMPLETE", 0))
    failed_count = sum(
        int(status_counts.get(status, 0)) for status in _TERMINAL_FAILURE_STATUSES
    )

    line = f"{total} approved, {complete} complete"

    if failed_count:
        reason_parts: list[str] = []
        for detail in result.get("failed_details", []):
            if detail["status"] not in _TERMINAL_FAILURE_STATUSES:
                continue
            label = detail["error"] if detail["error"] else detail["status"]
            reason_parts.append(f"{label} ({detail['count']})")

        reason_str = ", ".join(reason_parts) if reason_parts else "unknown"
        line += f", {failed_count} failed with reason {reason_str}"

    in_flight = {
        status: int(count)
        for status, count in status_counts.items()
        if status not in _TERMINAL_STATUSES and int(count)
    }
    if in_flight:
        detail_str = ", ".join(
            f"{status} ({in_flight[status]})" for status in sorted(in_flight)
        )
        line += f", {sum(in_flight.values())} not terminal: {detail_str}"

    return line


def print_attestation_report(
    company_name: str,
    attestation: dict[str, Any],
    vision_share: dict[str, Any] | None = None,
) -> None:
    """Pretty-print G5 attestation and optional vision-share companion."""
    print(f"\n{'═' * 62}")
    print(f"  Attestation Report — {company_name}")
    print(f"{'═' * 62}")
    print(f"  {format_attestation_phv_line(attestation)}")

    if vision_share is not None:
        print("")
        print("  Chunks by source_type:")
        for source_type in sorted(vision_share["source_type_counts"]):
            count = vision_share["source_type_counts"][source_type]
            print(f"    {source_type}: {count}")
        print(f"  Total chunks: {vision_share['total_chunks']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eval.retrieval.measure_attestation",
        description="Per-company doc_status attestation (G5) + chunks vision-share companion.",
    )
    parser.add_argument(
        "--catalog",
        default=_DEFAULT_CATALOG,
        help=f"Unity Catalog name (default: {_DEFAULT_CATALOG})",
    )
    parser.add_argument(
        "--schema",
        default=_DEFAULT_SCHEMA,
        help=f"Ingestion schema for doc_status/chunks (default: {_DEFAULT_SCHEMA})",
    )
    parser.add_argument(
        "--company",
        default=_DEFAULT_COMPANY,
        help=f"Company name filter (default: {_DEFAULT_COMPANY})",
    )
    return parser


def main(
    *,
    spark: Any | None = None,
    catalog: str | None = None,
    schema: str | None = None,
    company_name: str | None = None,
    include_vision_share: bool = True,
) -> dict[str, dict[str, Any]]:
    """Notebook-callable entry: print attestation + optional vision-share for one company."""
    if spark is None:
        from pyspark.sql import SparkSession

        spark = SparkSession.getActiveSession()
        if spark is None:
            spark = SparkSession.builder.getOrCreate()

    catalog = catalog or os.environ.get("catalog", _DEFAULT_CATALOG)
    schema = schema or os.environ.get("schema", _DEFAULT_SCHEMA)
    company_name = company_name or os.environ.get("sp_company_name", _DEFAULT_COMPANY)

    attestation = run_attestation_query(spark, catalog, schema, company_name)
    vision_share = None
    if include_vision_share:
        vision_share = run_vision_share_query(spark, catalog, schema, company_name)

    print_attestation_report(company_name, attestation, vision_share)
    output: dict[str, dict[str, Any]] = {"attestation": attestation}
    if vision_share is not None:
        output["vision_share"] = vision_share
    return output


def _cli_main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    main(
        catalog=args.catalog,
        schema=args.schema,
        company_name=args.company,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
