"""Read-only epoch-pin + gold-drift preflight — M1 W3 T2."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from eval.retrieval.companies import resolve_company_slug
from eval.retrieval.errors import PreconditionError, RunNotFoundError
from eval.retrieval.gold.bootstrap import load_gold_labels
from eval.retrieval.harness import (
    compute_gold_snapshot,
    compute_registry_hash,
    default_gold_path,
    default_registry_path,
)
from eval.retrieval.models import HarnessReport, HarnessRun
from eval.retrieval.store import EvalStore

DEFAULT_CATALOG = "uc13_ale"

PINNED_EPOCH_BASELINES: dict[str, str] = {
    "Elder Care": "baseline_2fa3a9056bd0",
    "Clearsulting": "baseline_488f70f13570",
    "GKF": "baseline_7510d1d14449",
    "SPG": "baseline_3992534e412f",
}

_MANIFEST_COLUMNS: tuple[str, ...] = (
    "run_id",
    "run_type",
    "pipeline_thread_id",
    "company_name",
    "catalog",
    "ingestion_snapshot",
    "registry_hash",
    "gold_snapshot",
    "git_sha",
    "git_branch",
    "pr_url",
    "hypothesis",
    "affected_intents",
    "gated_intents",
    "ablation_config",
    "ablation_arm",
    "baseline_ref_run_id",
    "store_backend",
    "harness_status",
    "intent_count",
    "gate_pass",
    "fallback_rate",
    "empty_rate",
    "e2e_agent_id",
    "e2e_snapshot_table",
    "e2e_checklist_score",
    "e2e_checklist_total",
    "created_at",
    "completed_at",
)


@dataclass(frozen=True)
class EpochPinCheck:
    company_name: str
    baseline_run_id: str
    harness_status: str
    run_type: str
    baseline_valid: bool
    gold_snapshot_match: bool
    registry_hash_match: bool
    current_gold_snapshot: str
    current_registry_hash: str
    stored_gold_snapshot: str | None
    stored_registry_hash: str | None


def _escape_sql_literal(value: str) -> str:
    return value.replace("'", "''")


def _parse_json_value(raw: Any) -> Any:
    if raw is None or raw == "":
        return None
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    return raw


def _parse_string_list(raw: Any) -> list[str]:
    parsed = _parse_json_value(raw)
    if parsed is None:
        return []
    if isinstance(parsed, list):
        return [str(item) for item in parsed]
    raise ValueError(f"expected list, got {type(parsed).__name__}")


def _parse_datetime(raw: Any) -> datetime | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        return raw
    text = str(raw)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def _manifest_from_warehouse_row(row: Mapping[str, Any]) -> HarnessRun:
    gate_pass = row.get("gate_pass")
    return HarnessRun(
        run_id=str(row["run_id"]),
        run_type=row["run_type"],  # type: ignore[arg-type]
        pipeline_thread_id=row.get("pipeline_thread_id") or None,
        company_name=str(row["company_name"]),
        catalog=str(row["catalog"]),
        ingestion_snapshot=str(row["ingestion_snapshot"]),
        registry_hash=str(row["registry_hash"]),
        gold_snapshot=str(row["gold_snapshot"]),
        git_sha=row.get("git_sha") or None,
        git_branch=row.get("git_branch") or None,
        pr_url=row.get("pr_url") or None,
        hypothesis=row.get("hypothesis") or None,
        affected_intents=_parse_string_list(row.get("affected_intents")),
        gated_intents=_parse_string_list(row.get("gated_intents")),
        ablation_config=_parse_json_value(row.get("ablation_config")),
        ablation_arm=row.get("ablation_arm") or None,
        baseline_ref_run_id=row.get("baseline_ref_run_id") or None,
        store_backend=row["store_backend"],  # type: ignore[arg-type]
        harness_status=row["harness_status"],  # type: ignore[arg-type]
        intent_count=int(row["intent_count"]),
        gate_pass=None if gate_pass in (None, "") else bool(gate_pass),
        fallback_rate=float(row["fallback_rate"])
        if row.get("fallback_rate") not in (None, "")
        else None,
        empty_rate=float(row["empty_rate"])
        if row.get("empty_rate") not in (None, "")
        else None,
        e2e_agent_id=row.get("e2e_agent_id") or None,
        e2e_snapshot_table=row.get("e2e_snapshot_table") or None,
        e2e_checklist_score=int(row["e2e_checklist_score"])
        if row.get("e2e_checklist_score") not in (None, "")
        else None,
        e2e_checklist_total=int(row["e2e_checklist_total"])
        if row.get("e2e_checklist_total") not in (None, "")
        else None,
        created_at=_parse_datetime(row["created_at"]) or datetime.fromtimestamp(0),
        completed_at=_parse_datetime(row.get("completed_at")),
    )


def _compute_current_pins(
    *,
    company_name: str,
    catalog: str,
    registry_path: Path,
    gold_path: Path,
) -> tuple[str, str]:
    gold_labels = [
        label
        for label in load_gold_labels(gold_path)
        if label.company_name == company_name and label.catalog == catalog
    ]
    if not gold_labels:
        raise PreconditionError(
            f"no gold labels for company_name={company_name!r} catalog={catalog!r}"
        )
    return (
        compute_gold_snapshot(gold_labels),
        compute_registry_hash(registry_path),
    )


def _baseline_valid(manifest: HarnessRun) -> bool:
    return manifest.run_type == "baseline" and manifest.harness_status == "complete"


def _check_one_company(
    store: EvalStore,
    *,
    company_name: str,
    baseline_run_id: str,
    catalog: str,
    registry_path: Path,
    gold_path: Path,
) -> EpochPinCheck:
    current_gold_snapshot, current_registry_hash = _compute_current_pins(
        company_name=company_name,
        catalog=catalog,
        registry_path=registry_path,
        gold_path=gold_path,
    )

    try:
        manifest = store.get_run(baseline_run_id).manifest
    except RunNotFoundError:
        return EpochPinCheck(
            company_name=company_name,
            baseline_run_id=baseline_run_id,
            harness_status="not_found",
            run_type="",
            baseline_valid=False,
            gold_snapshot_match=False,
            registry_hash_match=False,
            current_gold_snapshot=current_gold_snapshot,
            current_registry_hash=current_registry_hash,
            stored_gold_snapshot=None,
            stored_registry_hash=None,
        )

    return EpochPinCheck(
        company_name=company_name,
        baseline_run_id=baseline_run_id,
        harness_status=manifest.harness_status,
        run_type=manifest.run_type,
        baseline_valid=_baseline_valid(manifest),
        gold_snapshot_match=manifest.gold_snapshot == current_gold_snapshot,
        registry_hash_match=manifest.registry_hash == current_registry_hash,
        current_gold_snapshot=current_gold_snapshot,
        current_registry_hash=current_registry_hash,
        stored_gold_snapshot=manifest.gold_snapshot,
        stored_registry_hash=manifest.registry_hash,
    )


def check_epoch_pins(
    store: EvalStore,
    *,
    catalog: str = DEFAULT_CATALOG,
    pins: Mapping[str, str] | None = None,
    registry_path: Path | None = None,
    gold_path_for_company: Callable[[str], Path] | None = None,
) -> list[EpochPinCheck]:
    """Compare pinned baseline manifests in ops against current gold/registry hashes."""
    resolved_pins = dict(pins or PINNED_EPOCH_BASELINES)
    registry = registry_path or default_registry_path()
    gold_path_fn = gold_path_for_company or (
        lambda company: default_gold_path(resolve_company_slug(company))
    )

    return [
        _check_one_company(
            store,
            company_name=company_name,
            baseline_run_id=baseline_run_id,
            catalog=catalog,
            registry_path=registry,
            gold_path=gold_path_fn(company_name),
        )
        for company_name, baseline_run_id in resolved_pins.items()
    ]


def format_epoch_pin_line(result: EpochPinCheck) -> str:
    return (
        f"company={result.company_name} "
        f"baseline_run_id={result.baseline_run_id} "
        f"harness_status={result.harness_status} "
        f"gold_snapshot_match={result.gold_snapshot_match} "
        f"registry_hash_match={result.registry_hash_match}"
    )


def print_epoch_pin_report(results: Sequence[EpochPinCheck]) -> None:
    for result in results:
        print(format_epoch_pin_line(result))


class WarehouseEvalStore:
    """Minimal EvalStore adapter for read-only manifest lookup via warehouse SQL."""

    def __init__(
        self,
        execute_sql: Callable[[str], list[list[str | None]]],
        *,
        catalog: str,
    ) -> None:
        self._execute_sql = execute_sql
        self.catalog = catalog

    def get_run(self, run_id: str) -> HarnessReport:
        columns = ", ".join(_MANIFEST_COLUMNS)
        escaped_run_id = _escape_sql_literal(run_id)
        sql = f"""
            SELECT {columns}
            FROM {self.catalog}.ops.retrieval_harness_runs
            WHERE run_id = '{escaped_run_id}'
        """
        rows = self._execute_sql(sql)
        if not rows:
            raise RunNotFoundError(f"run_id not found: {run_id}")
        row_dict = {
            column: rows[0][index]
            for index, column in enumerate(_MANIFEST_COLUMNS)
        }
        manifest = _manifest_from_warehouse_row(row_dict)
        return HarnessReport(manifest=manifest, results=[], deltas=None)


def databricks_sql_executor(catalog: str) -> Callable[[str], list[list[str | None]]]:
    """Build a live warehouse SQL executor (not for pytest)."""

    def _execute(sql: str) -> list[list[str | None]]:
        from dotenv import load_dotenv

        load_dotenv()
        from databricks.sdk import WorkspaceClient

        w = WorkspaceClient(
            host=os.environ["DATABRICKS_SERVER_HOSTNAME"],
            token=os.environ["DATABRICKS_TOKEN"],
        )
        wh = os.environ["DATABRICKS_HTTP_PATH"].rstrip("/").split("/")[-1]
        stmt = w.statement_execution.execute_statement(
            warehouse_id=wh,
            statement=sql,
            wait_timeout="50s",
        )
        if stmt.status.state.value != "SUCCEEDED":
            raise RuntimeError(f"warehouse SQL failed: {stmt.status.state.value}")
        if not stmt.result or not stmt.result.data_array:
            return []
        return stmt.result.data_array

    return _execute


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eval.retrieval.scripts.preflight_epoch_pins",
        description=(
            "Read-only preflight: verify D4 pinned baseline run_ids in ops and "
            "compare gold_snapshot/registry_hash against committed gold files."
        ),
    )
    parser.add_argument(
        "--catalog",
        default=DEFAULT_CATALOG,
        help=f"Unity Catalog (default: {DEFAULT_CATALOG})",
    )
    parser.add_argument(
        "--registry-path",
        type=Path,
        default=None,
        help="intent_registry.yaml path (default: eval/retrieval/intent_registry.yaml)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        store = WarehouseEvalStore(
            databricks_sql_executor(args.catalog),
            catalog=args.catalog,
        )
        results = check_epoch_pins(
            store,
            catalog=args.catalog,
            registry_path=args.registry_path,
        )
    except (PreconditionError, RuntimeError) as exc:
        print(f"[preflight_epoch_pins] ERROR: {exc}", file=sys.stderr)
        return 1

    print_epoch_pin_report(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
