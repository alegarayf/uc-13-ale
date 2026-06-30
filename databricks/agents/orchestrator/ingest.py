"""UC13 Orchestrator — Delta + Volume YAML snapshot ingest (M1).

Callers should pass ``company_name`` and ``catalog`` from the same sources as
workstream agents (``get_param`` / notebook widgets mirrored to ``os.environ``):

- ``sp_company_name`` — target company (e.g. ``Elder Care``)
- ``catalog`` — Unity Catalog name (e.g. ``uc13_ale``; default in agents varies)
"""

from __future__ import annotations

import json
import os
from typing import Any

import yaml
from pyspark.sql import SparkSession

from agents.orchestrator.constants import AGENT_DELTA_TABLE_SUFFIXES, AGENTS_PRESENT_KEYS
from agents.orchestrator.paths import reports_volume_dir

_AGENT_YAML_FILES: dict[str, str] = {
    "business_model": "business_model_report.yaml",
    "financial_trends": "financial_trends_report.yaml",
    "customer_quality": "customer_quality_report.yaml",
    "kpi": "kpi_report.yaml",
    "legal": "legal_report.yaml",
    "quality_of_earnings": "quality_of_earnings_report.yaml",
}


def _parse_flags(raw: Any) -> list:
    """Parse Delta ``flags`` JSON column; never read flags from Volume YAML."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        return json.loads(raw or "[]")
    return []


def _row_to_dict(row) -> dict[str, Any]:
    data = row.asDict(recursive=True)
    data["flags"] = _parse_flags(data.get("flags"))
    return data


def _latest_delta_row(spark: SparkSession, table: str, company_name: str) -> dict[str, Any] | None:
    try:
        rows = (
            spark.sql(
                f"""
                SELECT *
                FROM {table}
                WHERE company_name = '{company_name}'
                ORDER BY created_at DESC
                LIMIT 1
                """
            ).collect()
        )
    except Exception:
        return None
    if not rows:
        return None
    return _row_to_dict(rows[0])


def _load_yaml(path: str) -> dict[str, Any] | None:
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError:
        print(f"[orchestrator] yaml parse failed: {path}")
        return None
    if data is None:
        return {}
    if not isinstance(data, dict):
        print(f"[orchestrator] yaml parse failed: {path}")
        return None
    return data


def _resolve_report_path(agent_key: str, delta_row: dict[str, Any], vol_dir: str) -> str | None:
    yaml_name = _AGENT_YAML_FILES[agent_key]
    volume_path = f"{vol_dir}/{yaml_name}"

    if agent_key == "legal":
        return volume_path

    delta_path = delta_row.get("report_path")
    if delta_path:
        return delta_path

    if agent_key == "kpi":
        return volume_path

    return volume_path


def ingest_snapshots(
    company_name: str,
    catalog: str,
    spark: SparkSession | None = None,
) -> dict[str, dict[str, Any]]:
    """Read latest Delta row + Volume YAML per workstream agent.

    Returns ``{agent_key: {delta_row, yaml_dict, report_path}}`` for agents with
    a Delta row. Agents with a missing table or no row are omitted. Flags are
    taken from the Delta ``flags`` column only (never from YAML).
    """
    if spark is None:
        spark = SparkSession.getActiveSession()
    if spark is None:
        raise RuntimeError("No active Spark session.")

    vol_dir = reports_volume_dir(catalog, company_name)
    snapshots: dict[str, dict[str, Any]] = {}

    for agent_key in AGENTS_PRESENT_KEYS:
        table = f"{catalog}.analysis.{AGENT_DELTA_TABLE_SUFFIXES[agent_key]}"
        delta_row = _latest_delta_row(spark, table, company_name)
        if delta_row is None:
            continue

        yaml_path = f"{vol_dir}/{_AGENT_YAML_FILES[agent_key]}"
        yaml_dict = _load_yaml(yaml_path)
        report_path = _resolve_report_path(agent_key, delta_row, vol_dir)

        snapshots[agent_key] = {
            "delta_row": delta_row,
            "yaml_dict": yaml_dict,
            "report_path": report_path,
        }

        print(
            f"[orchestrator] ingest {agent_key}: "
            f"delta={'yes' if delta_row else 'no'} "
            f"yaml={'yes' if yaml_dict else 'no'}"
        )

    return snapshots
