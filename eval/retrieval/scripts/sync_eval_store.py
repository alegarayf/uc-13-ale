"""One-way sqlite → delta promotion — spec §5.12.8 / plan §2 CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from eval.retrieval.errors import SyncError
from eval.retrieval.harness import default_sqlite_path
from eval.retrieval.store import DeltaEvalStore


def sync_eval_store(
    run_id: str,
    *,
    direction: str,
    catalog: str = "uc13",
    sqlite_path: Path | None = None,
) -> None:
    if direction != "sqlite_to_delta":
        raise ValueError(f"unsupported direction: {direction!r} (v1: sqlite_to_delta only)")

    try:
        from pyspark.sql import SparkSession
    except ImportError as exc:
        raise RuntimeError(
            "sync_eval_store requires a Databricks/PySpark runtime"
        ) from exc

    spark = SparkSession.getActiveSession()
    if spark is None:
        raise RuntimeError(
            "Active SparkSession required for --direction sqlite_to_delta"
        )

    path = sqlite_path or default_sqlite_path()
    store = DeltaEvalStore(spark, catalog=catalog, sqlite_path=path)
    store.promote_sqlite_run(run_id)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eval.retrieval.scripts.sync_eval_store",
        description="Promote a completed local harness run to uc13.ops Delta tables",
    )
    parser.add_argument("--run-id", required=True, help="Harness run_id to promote")
    parser.add_argument(
        "--direction",
        choices=("sqlite_to_delta",),
        required=True,
        help="Sync direction (v1: sqlite_to_delta only)",
    )
    parser.add_argument(
        "--catalog",
        default="uc13",
        help="Unity Catalog for uc13.ops tables (default: uc13)",
    )
    parser.add_argument(
        "--sqlite-path",
        type=Path,
        default=None,
        help="Local SQLite path (default: eval/retrieval/.local/re2_store.sqlite)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        sync_eval_store(
            args.run_id,
            direction=args.direction,
            catalog=args.catalog,
            sqlite_path=args.sqlite_path,
        )
    except (RuntimeError, SyncError, ValueError) as exc:
        print(f"[sync_eval_store] ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"[sync_eval_store] promoted run_id={args.run_id} to {args.catalog}.ops")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
