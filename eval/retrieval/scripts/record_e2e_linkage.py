"""Link FTA E2E checklist scores to pipeline HarnessRun manifests — M-RE2 T9 / D13."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from eval.retrieval.errors import RunNotFoundError, StoreError
from eval.retrieval.harness import default_sqlite_path
from eval.retrieval.models import HarnessRun
from eval.retrieval.store import DeltaEvalStore, EvalStore, SqliteEvalStore


def _e2e_linkage_table(catalog: str) -> str:
    return f"{catalog}.ops.e2e_linkage"


def _backfill_e2e_linkage_sql(catalog: str) -> str:
    """Idempotent INSERT … SELECT from run history (warehouse-executed)."""
    runs = f"{catalog}.ops.retrieval_harness_runs"
    linkage = _e2e_linkage_table(catalog)
    return f"""
        INSERT INTO {linkage} (
            run_id,
            e2e_agent_id,
            e2e_snapshot_table,
            e2e_checklist_score,
            e2e_checklist_total,
            linked_at
        )
        SELECT
            r.run_id,
            r.e2e_agent_id,
            r.e2e_snapshot_table,
            r.e2e_checklist_score,
            r.e2e_checklist_total,
            COALESCE(r.completed_at, r.created_at) AS linked_at
        FROM {runs} r
        WHERE r.e2e_agent_id IS NOT NULL
          AND r.e2e_snapshot_table IS NOT NULL
          AND r.e2e_checklist_score IS NOT NULL
          AND r.e2e_checklist_total IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM {linkage} e
              WHERE e.run_id = r.run_id
                AND e.e2e_agent_id = r.e2e_agent_id
          )
    """


def backfill_e2e_linkage(store: DeltaEvalStore) -> int:
    """Backfill append-only linkage rows from ``retrieval_harness_runs`` history."""
    before = store.spark.sql(
        f"SELECT COUNT(*) AS n FROM {_e2e_linkage_table(store.catalog)}"
    ).collect()[0]["n"]
    store.spark.sql(_backfill_e2e_linkage_sql(store.catalog))
    after = store.spark.sql(
        f"SELECT COUNT(*) AS n FROM {_e2e_linkage_table(store.catalog)}"
    ).collect()[0]["n"]
    return int(after) - int(before)


def _apply_e2e_linkage(
    store: EvalStore,
    run_id: str,
    *,
    e2e_agent_id: str,
    e2e_checklist_score: int,
    e2e_checklist_total: int,
    e2e_snapshot_table: str,
) -> HarnessRun:
    """Persist optional HarnessRun.e2e_* fields on an existing manifest."""
    store.get_run(run_id)

    if isinstance(store, SqliteEvalStore):
        store._get_manifest_row(run_id)
        store._conn.execute(
            """
            UPDATE retrieval_harness_runs
            SET e2e_agent_id = ?,
                e2e_snapshot_table = ?,
                e2e_checklist_score = ?,
                e2e_checklist_total = ?
            WHERE run_id = ?
            """,
            (
                e2e_agent_id,
                e2e_snapshot_table,
                e2e_checklist_score,
                e2e_checklist_total,
                run_id,
            ),
        )
        store._conn.commit()
        return store._row_to_manifest(store._get_manifest_row(run_id))

    if isinstance(store, DeltaEvalStore):
        store._fetch_manifest_row(run_id)
        store.spark.sql(
            f"""
            UPDATE {store._table('retrieval_harness_runs')}
            SET e2e_agent_id = :e2e_agent_id,
                e2e_snapshot_table = :e2e_snapshot_table,
                e2e_checklist_score = :e2e_checklist_score,
                e2e_checklist_total = :e2e_checklist_total
            WHERE run_id = :run_id
            """,
            args={
                "run_id": run_id,
                "e2e_agent_id": e2e_agent_id,
                "e2e_snapshot_table": e2e_snapshot_table,
                "e2e_checklist_score": e2e_checklist_score,
                "e2e_checklist_total": e2e_checklist_total,
            },
        )
        store.spark.sql(
            f"""
            INSERT INTO {_e2e_linkage_table(store.catalog)} (
                run_id,
                e2e_agent_id,
                e2e_snapshot_table,
                e2e_checklist_score,
                e2e_checklist_total,
                linked_at
            )
            VALUES (
                :run_id,
                :e2e_agent_id,
                :e2e_snapshot_table,
                :e2e_checklist_score,
                :e2e_checklist_total,
                current_timestamp()
            )
            """,
            args={
                "run_id": run_id,
                "e2e_agent_id": e2e_agent_id,
                "e2e_snapshot_table": e2e_snapshot_table,
                "e2e_checklist_score": e2e_checklist_score,
                "e2e_checklist_total": e2e_checklist_total,
            },
        )
        return store._manifest_from_row(store._fetch_manifest_row(run_id))

    raise StoreError(f"unsupported store type for e2e linkage: {type(store).__name__}")


def record_e2e_linkage(
    run_id: str,
    *,
    e2e_agent_id: str,
    e2e_checklist_score: int,
    e2e_checklist_total: int,
    e2e_snapshot_table: str,
    store: EvalStore,
) -> HarnessRun:
    return _apply_e2e_linkage(
        store,
        run_id,
        e2e_agent_id=e2e_agent_id,
        e2e_checklist_score=e2e_checklist_score,
        e2e_checklist_total=e2e_checklist_total,
        e2e_snapshot_table=e2e_snapshot_table,
    )


def _build_store(
    backend: str,
    *,
    catalog: str,
    sqlite_path: Path | None,
) -> EvalStore:
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
    raise ValueError(f"unsupported store backend: {backend!r}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eval.retrieval.scripts.record_e2e_linkage",
        description="Link FTA E2E checklist score to a pipeline HarnessRun manifest",
    )
    parser.add_argument("--run-id", required=True, help="FTA agent_run_id from close_agent_run")
    parser.add_argument(
        "--e2e-agent-id",
        required=True,
        choices=("fta", "legal", "bma", "cqa", "kpi", "qoe", "profiler"),
        help="Agent partition id (e.g. fta)",
    )
    parser.add_argument(
        "--e2e-checklist-score",
        type=int,
        required=True,
        help="18-field checklist pass count from Cell 12 Elder Care re-score",
    )
    parser.add_argument(
        "--e2e-checklist-total",
        type=int,
        required=True,
        help="Checklist denominator",
    )
    parser.add_argument(
        "--e2e-snapshot-table",
        required=True,
        help="FQN of eval snapshot table (e.g. uc13_ale.analysis.financial_trends_eval_snapshot)",
    )
    parser.add_argument(
        "--store-backend",
        choices=("sqlite", "delta"),
        default="sqlite",
        help="EvalStore backend (default: sqlite)",
    )
    parser.add_argument(
        "--catalog",
        default="uc13_ale",
        help="Unity Catalog for uc13.ops tables when using delta (default: uc13_ale)",
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
        store = _build_store(
            args.store_backend,
            catalog=args.catalog,
            sqlite_path=args.sqlite_path,
        )
        manifest = record_e2e_linkage(
            args.run_id,
            e2e_agent_id=args.e2e_agent_id,
            e2e_checklist_score=args.e2e_checklist_score,
            e2e_checklist_total=args.e2e_checklist_total,
            e2e_snapshot_table=args.e2e_snapshot_table,
            store=store,
        )
    except (RuntimeError, RunNotFoundError, StoreError, ValueError) as exc:
        print(f"[record_e2e_linkage] ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        if "store" in locals() and isinstance(store, SqliteEvalStore):
            store.close()

    print(
        f"[record_e2e_linkage] linked run_id={manifest.run_id} "
        f"e2e_score={manifest.e2e_checklist_score}/{manifest.e2e_checklist_total} "
        f"snapshot={manifest.e2e_snapshot_table!r}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
