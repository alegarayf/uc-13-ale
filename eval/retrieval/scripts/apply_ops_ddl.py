"""Apply uc13.ops DDL on a Databricks cluster — plan §2 CLI / D7-A."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def _load_statements(sql_path: Path, catalog: str) -> list[str]:
    text = sql_path.read_text(encoding="utf-8")
    text = text.replace("{catalog}", catalog)
    statements = [
        statement.strip()
        for statement in re.split(r";\s*\n", text)
        if statement.strip() and not statement.strip().startswith("--")
    ]
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
