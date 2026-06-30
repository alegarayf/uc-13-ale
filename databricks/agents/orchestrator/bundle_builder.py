"""UC13 Orchestrator — deterministic BundleBuilder pipeline (M2 B2+B3)."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import yaml

from agents.orchestrator.confidence import ConfidenceEngine
from agents.orchestrator.constants import (
    AGENT_DELTA_TABLE_SUFFIXES,
    AGENTS_PRESENT_KEYS,
    FILL_STATE_RULES,
    TLDR_REQUIRED_FIELDS,
)
from agents.orchestrator.field_mapping import apply_field_mappings
from agents.orchestrator.formatters import format_diligence_entry, normalize_gap
from agents.orchestrator.paths import company_safe, reports_volume_dir
from agents.orchestrator.validate import BundleValidationError, validate_bundle

if TYPE_CHECKING:
    from pyspark.sql import SparkSession

_BUNDLE_BUILDER_VERSION = "0.2.0-m2"
_SEVERITY_ORDER = {"Red": 0, "Yellow": 1, "Green": 2}
_FLAG_TO_RISK = {"Red": "critical", "Yellow": "material", "Green": "track"}


def _parse_json_column(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, (list, dict)):
        return raw
    if isinstance(raw, str):
        return json.loads(raw or "null")
    return raw


def _normalize_utc(dt: Any) -> datetime | None:
    if dt is None:
        return None
    if hasattr(dt, "to_pydatetime"):
        dt = dt.to_pydatetime()
    if not isinstance(dt, datetime):
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def merge_risks_from_flags(snapshots: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Project Delta flags to ``risks[]`` per §5.6.1; sort Red→Yellow→Green; top 8."""
    projected: list[dict[str, Any]] = []
    for agent_key, snap in snapshots.items():
        flags = snap.get("delta_row", {}).get("flags") or []
        if not isinstance(flags, list):
            continue
        for flag in flags:
            if not isinstance(flag, dict):
                continue
            metric = flag.get("metric") or ""
            note = flag.get("note") or ""
            value = flag.get("value") or ""
            source_doc = flag.get("source_doc") or ""
            evidence = f"{value} ({source_doc})".strip(" ()") if value or source_doc else ""
            projected.append(
                {
                    "risk": metric or note or "Flag",
                    "severity": _FLAG_TO_RISK.get(flag.get("severity", "Green"), "track"),
                    "evidence": evidence,
                    "mitigant_or_question": note or flag.get("threshold") or "",
                    "source_agent": agent_key,
                    "confidence": flag.get("confidence") or "medium",
                    "fill_state": "filled_cited",
                }
            )
    severity_rank = {"critical": 0, "material": 1, "track": 2}
    projected.sort(
        key=lambda r: (
            severity_rank.get(r.get("severity", "track"), 9),
            r.get("risk") or "",
            r.get("mitigant_or_question") or "",
        )
    )
    return projected[:8]


def _get_by_path(obj: dict, path: str) -> Any:
    if path.endswith("[]"):
        key = path[:-2]
        parts = key.split(".")
        cur: Any = obj
        for part in parts:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(part)
        return cur
    if path.endswith(".*"):
        prefix = path[:-2]
        parts = prefix.split(".")
        cur: Any = obj
        for part in parts:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(part)
        if not isinstance(cur, dict):
            return cur
        return cur
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _is_field_empty(bundle: dict, path: str) -> bool:
    if path.endswith("[]"):
        val = _get_by_path(bundle, path)
        return not val
    if path.endswith(".*"):
        block = _get_by_path(bundle, path)
        if not isinstance(block, dict):
            return True
        return not any(v not in (None, "", [], {}) for v in block.values())
    val = _get_by_path(bundle, path)
    if val is None:
        return True
    if isinstance(val, str):
        return not val.strip()
    if isinstance(val, (list, dict)):
        return len(val) == 0
    return False


def collect_synthesis_gaps(bundle: dict) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    for field_path in TLDR_REQUIRED_FIELDS:
        if _is_field_empty(bundle, field_path):
            gaps.append(
                {
                    "field_path": field_path,
                    "reason": "Required TL;DR field empty after populate",
                    "owner": "orchestrator",
                }
            )
    return gaps


def apply_fill_state(bundle: dict) -> dict:
    """Deterministic §5.6 stage 6b post-pass using ``FILL_STATE_RULES``."""
    result = deepcopy(bundle)

    def _assign_list(rule_path: str, items: list | None, default: str) -> None:
        if not items:
            return
        for item in items:
            if isinstance(item, dict) and "fill_state" in item:
                if _is_field_empty({"x": item}, "x.item") and "item" in item:
                    item["fill_state"] = "gap_correct" if default == "gap_correct" else "not_attempted"
                elif not item.get("fill_state"):
                    item["fill_state"] = default

    for path, typical in FILL_STATE_RULES.items():
        if path.endswith("[]"):
            key_parts = path[:-2].split(".")
            cur: Any = result
            for part in key_parts:
                cur = cur.get(part) if isinstance(cur, dict) else None
            if isinstance(cur, list):
                _assign_list(path, cur, typical)

    for row in result.get("kpi_dashboard") or []:
        if not isinstance(row, dict):
            continue
        if row.get("flag") == "N/A":
            row["fill_state"] = "gap_correct"
        elif not row.get("fill_state"):
            row["fill_state"] = FILL_STATE_RULES.get("kpi_dashboard[]", "filled_cited")

    for row in result.get("risks") or []:
        if isinstance(row, dict) and not row.get("fill_state"):
            row["fill_state"] = FILL_STATE_RULES.get("risks[]", "filled_synthesized")

    for row in result.get("diligence_questions") or []:
        if isinstance(row, dict) and not row.get("fill_state"):
            row["fill_state"] = FILL_STATE_RULES.get("diligence_questions[]", "filled_synthesized")

    for row in result.get("data_room_gaps") or []:
        if isinstance(row, dict) and not row.get("fill_state"):
            row["fill_state"] = FILL_STATE_RULES.get("data_room_gaps[]", "filled_cited")

    return result


def freshness(
    spark: SparkSession,
    catalog: str,
    company_name: str,
    generated_at: datetime,
) -> str:
    """Compare bundle ``generated_at`` to latest agent Delta ``created_at`` (parameterized)."""
    from pyspark.sql.functions import col

    generated_utc = _normalize_utc(generated_at)
    latest: datetime | None = None
    for agent_key in AGENTS_PRESENT_KEYS:
        suffix = AGENT_DELTA_TABLE_SUFFIXES[agent_key]
        table = f"{catalog}.analysis.{suffix}"
        try:
            row = (
                spark.table(table)
                .filter(col("company_name") == company_name)
                .orderBy(col("created_at").desc())
                .limit(1)
                .collect()
            )
        except Exception:
            continue
        if not row:
            continue
        created = _normalize_utc(row[0]["created_at"])
        if created and (latest is None or created > latest):
            latest = created
    if latest and generated_utc and latest > generated_utc:
        return "stale"
    return "current"


def write_bundle_yaml(bundle: dict, path: str, spark: SparkSession, catalog: str) -> None:
    spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.analysis.reports")
    os.makedirs(os.path.dirname(path), exist_ok=True)

    def _str_representer(dumper, data):
        if "\n" in data:
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
        return dumper.represent_scalar("tag:yaml.org,2002:str", data)

    yaml.add_representer(str, _str_representer)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(bundle, fh, allow_unicode=True, sort_keys=False, width=120)


def _ingest_snapshots(
    company_name: str,
    catalog: str,
    spark: SparkSession,
) -> dict[str, dict[str, Any]]:
    from agents.orchestrator.ingest import ingest_snapshots

    return ingest_snapshots(company_name, catalog, spark)


class GapAggregator:
    """§5.6.2 gap merge and diligence question synthesis."""

    def merge_data_room_gaps(self, snapshots: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[str, str]] = set()
        rows: list[dict[str, Any]] = []
        for agent_key, snap in snapshots.items():
            delta_row = snap.get("delta_row") or {}
            for gap_text in delta_row.get("data_room_gaps") or []:
                norm = normalize_gap(str(gap_text))
                dedupe_key = (norm, agent_key)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                rows.append(
                    {
                        "item": str(gap_text),
                        "priority": "medium",
                        "source_agent": agent_key,
                        "fill_state": "filled_cited",
                    }
                )
            if agent_key == "legal":
                unable = _parse_json_column(delta_row.get("unable_to_assess_json")) or []
                for item in unable if isinstance(unable, list) else []:
                    norm = normalize_gap(str(item))
                    dedupe_key = (norm, agent_key)
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    rows.append(
                        {
                            "item": str(item),
                            "priority": "high",
                            "source_agent": agent_key,
                            "fill_state": "gap_correct",
                        }
                    )
        return rows

    def build_diligence_questions(
        self,
        bundle: dict,
        snapshots: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        del bundle  # M1 parity uses snapshots only; bundle reserved for gap-driven questions (T5)
        questions: list[dict[str, Any]] = []
        legal = snapshots.get("legal", {}).get("delta_row") or {}
        diligence = _parse_json_column(legal.get("recommended_diligence_json")) or []
        if isinstance(diligence, list):
            for entry in diligence[:8]:
                if not isinstance(entry, dict):
                    continue
                questions.append(
                    {
                        "category": entry.get("category") or "legal",
                        "question": format_diligence_entry(entry),
                        "priority": entry.get("priority") or "high",
                        "source_agent": "legal",
                        "fill_state": "filled_synthesized",
                    }
                )
        kpi_snap = snapshots.get("kpi", {})
        missing = (kpi_snap.get("yaml_dict") or {}).get("missing_kpis") or []
        if isinstance(missing, list):
            for item in missing[:4]:
                questions.append(
                    {
                        "category": "kpi",
                        "question": f"Provide supporting data for KPI: {item}",
                        "priority": "medium",
                        "source_agent": "kpi",
                        "fill_state": "gap_correct",
                    }
                )
        return questions[:8]


def _load_company_profile(
    spark: SparkSession, catalog: str, company_name: str
) -> dict[str, Any]:
    from pyspark.sql.functions import col

    try:
        rows = (
            spark.table(f"{catalog}.classification.company_profile")
            .filter(col("company_name") == company_name)
            .orderBy(col("created_at").desc())
            .limit(1)
            .collect()
        )
    except Exception:
        return {}
    return rows[0].asDict(recursive=True) if rows else {}


def _build_agents_present(snapshots: dict) -> dict[str, bool]:
    return {key: key in snapshots for key in AGENTS_PRESENT_KEYS}


class BundleBuilder:
    """Deterministic orchestrator bundle pipeline stages 0–8 (§5.6)."""

    def __init__(self) -> None:
        self._gap_aggregator = GapAggregator()
        self._confidence_engine = ConfidenceEngine()

    def build(
        self,
        company_name: str,
        catalog: str,
        spark: SparkSession | None = None,
        llm_endpoint: str | None = None,
    ) -> dict:
        """Ingest → map → flags → gaps → confidence → fill_state → validate → persist."""
        del llm_endpoint  # B6 polish deferred to T7

        print("[orchestrator] build:gate checking Spark session")
        if spark is None:
            from pyspark.sql import SparkSession

            spark = SparkSession.getActiveSession()
        if spark is None:
            raise RuntimeError("No active Spark session.")

        print("[orchestrator] build:ingest loading agent snapshots")
        snapshots = _ingest_snapshots(company_name, catalog, spark)
        profile = _load_company_profile(spark, catalog, company_name)
        generated_at = datetime.now(timezone.utc)
        agents_present = _build_agents_present(snapshots)

        cim_detected = None
        if snapshots.get("business_model"):
            cim_detected = snapshots["business_model"]["delta_row"].get("cim_detected")

        meta_scaffold: dict[str, Any] = {
            "company_name": company_name,
            "company_safe": company_safe(company_name),
            "catalog": catalog,
            "deal_type": profile.get("deal_type"),
            "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
            "status": "complete" if all(agents_present.values()) else "partial",
            "freshness": "current",
            "render_state": "bundle_only",
            "demo_mode": False,
            "disclaimer_text": "",
            "basis_of_preparation": (
                f"Phase 3 workstream outputs (M2 deterministic builder). "
                f"cim_detected={cim_detected}"
            ),
            "overall_confidence": "low",
            "agents_present": agents_present,
        }

        mapped = apply_field_mappings(snapshots, profile, meta_scaffold)

        bundle: dict[str, Any] = {
            "meta": {
                "schema_version": "0.1.0",
                **meta_scaffold,
                **mapped.get("meta", {}),
            },
            "headline_metrics": mapped.get("headline_metrics", {}),
            "executive": mapped.get("executive", {}),
            "company_framing": mapped.get("company_framing", {}),
            "financials": mapped.get("financials", {}),
            "revenue_quality": mapped.get("revenue_quality", {}),
            "kpi_dashboard": mapped.get("kpi_dashboard", []),
            "qoe": mapped.get("qoe", {}),
            "legal": mapped.get("legal", {}),
            "confidence_by_area": {},
            "provenance": {
                "agent_report_paths": {
                    k: str(snap.get("report_path") or "") for k, snap in snapshots.items()
                },
                "agent_delta_tables": {
                    k: f"{catalog}.analysis.{AGENT_DELTA_TABLE_SUFFIXES[k]}"
                    for k in AGENTS_PRESENT_KEYS
                },
                "bundle_builder_version": _BUNDLE_BUILDER_VERSION,
                "synthesis_gaps": [],
            },
        }

        print("[orchestrator] build:flags merging risks from agent flags")
        bundle["risks"] = merge_risks_from_flags(snapshots)

        print("[orchestrator] build:gaps aggregating data room gaps and diligence")
        bundle["data_room_gaps"] = self._gap_aggregator.merge_data_room_gaps(snapshots)
        bundle["diligence_questions"] = self._gap_aggregator.build_diligence_questions(
            bundle, snapshots
        )

        print("[orchestrator] build:confidence computing per-area and overall")
        bundle["confidence_by_area"] = self._confidence_engine.compute_by_area(
            bundle, snapshots
        )
        bundle["meta"]["overall_confidence"] = self._confidence_engine.compute_overall(
            bundle["confidence_by_area"],
            bundle.get("risks") or [],
        )
        bundle["meta"]["freshness"] = freshness(spark, catalog, company_name, generated_at)

        print("[orchestrator] build:fill_state applying fill_state rules")
        bundle = apply_fill_state(bundle)
        bundle["provenance"]["synthesis_gaps"] = collect_synthesis_gaps(bundle)

        print("[orchestrator] build:validate jsonschema")
        try:
            validate_bundle(bundle)
        except BundleValidationError:
            raise

        vol_dir = reports_volume_dir(catalog, company_name)
        out_path = f"{vol_dir}/orchestrator_bundle.yaml"
        print(f"[orchestrator] build:persist writing {out_path}")
        write_bundle_yaml(bundle, out_path, spark, catalog)

        return bundle
