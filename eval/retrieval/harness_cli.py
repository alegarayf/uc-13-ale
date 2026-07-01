"""Harness CLI — spec §2 CLI surface (T8)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from eval.retrieval.harness import EvalHarness, default_sqlite_path
from eval.retrieval.store import DeltaEvalStore, SqliteEvalStore


def _build_store(backend: str, *, catalog: str, sqlite_path: Path | None) -> object:
    if backend == "sqlite":
        path = sqlite_path or default_sqlite_path()
        return SqliteEvalStore(path)
    if backend == "delta":
        from pyspark.sql import SparkSession

        spark = SparkSession.getActiveSession()
        if spark is None:
            raise RuntimeError(
                "Active SparkSession required for --store-backend delta"
            )
        return DeltaEvalStore(spark, catalog=catalog, sqlite_path=sqlite_path)
    raise ValueError(f"unsupported store backend: {backend}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eval.retrieval.harness_cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Execute a harness run")
    run_parser.add_argument(
        "--store-backend",
        choices=("sqlite", "delta"),
        required=True,
    )
    run_parser.add_argument(
        "--run-type",
        choices=("baseline", "enhancement", "ablation", "ci_fixture"),
        required=True,
    )
    run_parser.add_argument("--company-name", required=True)
    run_parser.add_argument("--catalog", required=True)
    run_parser.add_argument("--baseline-ref-run-id")
    run_parser.add_argument("--sqlite-path", type=Path)
    run_parser.add_argument("--registry-path", type=Path)
    run_parser.add_argument("--gold-path", type=Path)
    run_parser.add_argument("--reports-dir", type=Path)
    run_parser.add_argument(
        "--affected-intents",
        nargs="+",
        help="Explicit intent scope (required for enhancement)",
    )

    validate_parser = subparsers.add_parser(
        "validate-baseline",
        help="Preflight baseline_ref validation",
    )
    validate_parser.add_argument("--store-backend", choices=("sqlite", "delta"), required=True)
    validate_parser.add_argument("--baseline-ref-run-id", required=True)
    validate_parser.add_argument("--current-run-id", required=True)
    validate_parser.add_argument("--catalog", required=True)
    validate_parser.add_argument("--sqlite-path", type=Path)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    harness_kwargs: dict = {}
    if getattr(args, "registry_path", None) is not None:
        harness_kwargs["registry_path"] = args.registry_path
    if getattr(args, "gold_path", None) is not None:
        harness_kwargs["gold_path"] = args.gold_path
    if getattr(args, "reports_dir", None) is not None:
        harness_kwargs["reports_dir"] = args.reports_dir
    harness = EvalHarness(**harness_kwargs)

    if args.command == "run":
        store = _build_store(
            args.store_backend,
            catalog=args.catalog,
            sqlite_path=getattr(args, "sqlite_path", None),
        )
        try:
            report = harness.run(
                run_type=args.run_type,
                company_name=args.company_name,
                catalog=args.catalog,
                store=store,
                store_backend=args.store_backend,
                baseline_ref_run_id=args.baseline_ref_run_id,
                affected_intents=args.affected_intents,
            )
        finally:
            close = getattr(store, "close", None)
            if callable(close):
                close()
        print(report.manifest.run_id)
        return 0

    if args.command == "validate-baseline":
        store = _build_store(
            args.store_backend,
            catalog=args.catalog,
            sqlite_path=args.sqlite_path,
        )
        try:
            current = store.get_run(args.current_run_id)
            harness.validate_baseline_ref(
                store,
                args.baseline_ref_run_id,
                gated_intents=current.manifest.gated_intents,
                current_manifest=current.manifest,
            )
        finally:
            close = getattr(store, "close", None)
            if callable(close):
                close()
        print("baseline_ref validation passed")
        return 0

    parser.error(f"unknown command: {args.command}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
