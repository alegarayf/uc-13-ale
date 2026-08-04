"""M0 manifest dry-run checkpoint — S0 state ensure + S1 read-only work list (no corpus writes)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from parse_manifest import ManifestSummary, ParseManifest
from status_store import PARSER_VERSION, ensure_doc_status
from sync_state import ensure_sync_state


def _get_dbutils():
    """Return the Databricks dbutils object from any execution context.

    Works whether the code runs directly in a notebook cell or is called from
    an imported module (where dbutils is not a direct global but is reachable
    via the IPython user namespace injected by Databricks).
    """
    try:
        return dbutils  # noqa: F821
    except NameError:
        pass
    try:
        import IPython
        user_ns = IPython.get_ipython().user_ns
        if "dbutils" in user_ns:
            return user_ns["dbutils"]
    except Exception:
        pass
    return None


def get_param(key: str, default: str = None) -> str:
    _dbutils = _get_dbutils()
    if _dbutils is not None:
        try:
            value = _dbutils.widgets.get(key)
            if value:
                return value
        except Exception:
            pass
    value = os.environ.get(key, default)
    if value is None:
        raise RuntimeError(
            f"Parameter '{key}' not found. "
            "On Databricks: add it as a job task parameter. "
            "Locally: add it to your .env file or export it as an env var."
        )
    return value


def get_current_path():
    try:
        notebook_path = (
            dbutils.notebook.entry_point  # noqa: F821
            .getDbutils()
            .notebook()
            .getContext()
            .notebookPath()
            .get()
        )
        return Path("/Workspace") / notebook_path.lstrip("/")
    except Exception:
        return Path(os.getcwd())


def find_repo_root(marker="agents"):
    current_path = get_current_path()
    if current_path.is_file():
        current_path = current_path.parent
    for path in [current_path, *current_path.parents]:
        if (path / marker).exists():
            return str(path)
    raise RuntimeError(f"Could not find a parent directory containing '{marker}'")


def _parse_tiers(parse_tiers_raw: str) -> tuple[list[int] | None, str]:
    """Return (tiers for ParseManifest.build, human tier label)."""
    raw = parse_tiers_raw.strip().lower()
    if raw == "all":
        return None, "all tiers"
    tiers = [int(t.strip()) for t in raw.split(",") if t.strip().isdigit()]
    if not tiers:
        raise RuntimeError(
            f"Invalid parse_priority_tiers '{parse_tiers_raw}': "
            "expected 'all' or comma-separated tier integers (e.g. '1,2')."
        )
    return tiers, f"tier(s) {', '.join(str(t) for t in tiers)}"


def format_run_summary(
    *,
    company_name: str,
    volume_path: str,
    tier_label: str,
    summary: ManifestSummary,
) -> list[str]:
    """Pure formatter: identical lines for identical summary inputs (idempotency falsifier)."""
    lines = [
        f"\n=== UC13 Phase 2b — Manifest Dry-Run ({company_name}) ===",
        f"Volume     : {volume_path}",
        f"Tiers      : {tier_label}",
        "",
        f"NEW   : {summary.classification_counts['NEW']}",
        f"STALE : {summary.classification_counts['STALE']}",
        f"RETRY : {summary.classification_counts['RETRY']}",
        f"SKIP  : {summary.classification_counts['SKIP']}",
        "",
        f"Coverage injected : {summary.coverage_injected_count}",
    ]

    for workstream, approved_count in sorted(summary.zero_coverable_residuals):
        lines.append(
            f"workstream {workstream}: {approved_count} approved, 0 coverable"
        )

    if summary.absent_on_volume:
        lines.append("")
        lines.append(f"Absent on volume ({len(summary.absent_on_volume)}):")
        for file_name in sorted(summary.absent_on_volume):
            lines.append(f"  - {file_name}")

    if summary.disallowed_extensions:
        lines.append("")
        lines.append(
            f"Disallowed extension ({len(summary.disallowed_extensions)}):"
        )
        for file_name in sorted(summary.disallowed_extensions):
            lines.append(f"  - {file_name}")

    return lines


def run_manifest_dry_run(
    spark,
    *,
    company_name: str,
    catalog: str,
    schema: str,
    tiers: list[int] | None,
    tier_label: str,
    coverage_per_workstream: int,
) -> dict[str, Any]:
    """S0 ensure state tables + S1 build manifest. Read-only — no status transitions."""
    volume_path = f"/Volumes/{catalog}/{schema}/raw_files/{company_name}"

    ensure_doc_status(spark, catalog, schema)
    ensure_sync_state(spark, catalog, schema)

    manifest = ParseManifest(spark, catalog, schema, company_name)
    work_list = manifest.build(
        tiers,
        coverage_per_workstream,
        force_all=False,
        force_doc_ids=None,
    )
    summary = manifest.last_summary
    if summary is None:
        raise RuntimeError("ParseManifest.build did not populate last_summary")

    return {
        "company_name": company_name,
        "catalog": catalog,
        "schema": schema,
        "tier_label": tier_label,
        "volume_path": volume_path,
        "parser_version": PARSER_VERSION,
        "classification_counts": dict(summary.classification_counts),
        "coverage_injected_count": summary.coverage_injected_count,
        "zero_coverable_residuals": list(summary.zero_coverable_residuals),
        "absent_on_volume": sorted(summary.absent_on_volume),
        "disallowed_extensions": sorted(summary.disallowed_extensions),
        "work_list_size": len(work_list),
        "summary_lines": format_run_summary(
            company_name=company_name,
            volume_path=volume_path,
            tier_label=tier_label,
            summary=summary,
        ),
    }


def main() -> None:
    repo_root = find_repo_root()
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    print("repo_root:", repo_root)

    company_name = get_param("sp_company_name")
    catalog = get_param("catalog", default="uc13")
    schema = get_param("schema", default="ingestion")
    parse_tiers_raw = get_param("parse_priority_tiers", default="1,2")
    coverage_per_workstream = int(
        get_param("coverage_per_workstream", default="3")
    )

    tiers, tier_label = _parse_tiers(parse_tiers_raw)

    from pyspark.sql import SparkSession as _SparkSession

    _spark = _SparkSession.getActiveSession()
    if _spark is None:
        raise RuntimeError(
            "No active Spark session. This script must run on a Databricks cluster."
        )

    result = run_manifest_dry_run(
        _spark,
        company_name=company_name,
        catalog=catalog,
        schema=schema,
        tiers=tiers,
        tier_label=tier_label,
        coverage_per_workstream=coverage_per_workstream,
    )
    for line in result["summary_lines"]:
        print(line)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
