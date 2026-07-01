"""EvalStore protocol and backends — spec §5.12.9."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from eval.retrieval.errors import (
    IncompleteResultsError,
    RunCompleteError,
    RunNotFoundError,
    StoreError,
    SyncError,
)
from eval.retrieval.models import (
    HarnessDelta,
    HarnessReport,
    HarnessResult,
    HarnessRun,
    IntentGateSummary,
    ProvenanceChunk,
    ProvenanceRecord,
)

logger = logging.getLogger(__name__)

_LIST_RUNS_MAX_LIMIT = 500


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _dt_to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _iso_to_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _json_dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _json_loads(value: str | None) -> Any:
    if value is None:
        return None
    return json.loads(value)


def derive_agent_id(intent_id: str) -> str:
    """Derive registry agent_id partition from intent_id when not stored explicitly."""
    parts = intent_id.split(".")
    if len(parts) >= 2 and parts[0] == "fta":
        return f"{parts[0]}.{parts[1]}"
    return parts[0]


@runtime_checkable
class EvalStore(Protocol):
    """Storage abstraction for harness manifests, results, deltas, and provenance."""

    def insert_run(self, manifest: HarnessRun) -> str:
        ...

    def append_results(self, run_id: str, results: list[HarnessResult]) -> int:
        ...

    def append_provenance(self, run_id: str, records: list[ProvenanceRecord]) -> int:
        ...

    def append_deltas(self, run_id: str, deltas: list[HarnessDelta]) -> int:
        ...

    def finalize_run(
        self,
        run_id: str,
        *,
        gate_pass: bool | None,
        fallback_rate: float | None,
        empty_rate: float | None = None,
    ) -> HarnessRun:
        ...

    def get_run(self, run_id: str) -> HarnessReport:
        ...

    def list_runs(
        self,
        *,
        company_name: str,
        catalog: str,
        run_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[HarnessRun]:
        ...

    def delete_run(self, run_id: str) -> None:
        ...

    def get_latest_baseline(self, company_name: str, catalog: str) -> str | None:
        ...

    def promote_sqlite_run(self, run_id: str) -> None:
        ...


class _StoreBase:
    def _validate_incomplete_manifest(self, manifest: HarnessRun) -> None:
        if manifest.harness_status != "incomplete":
            raise StoreError(
                f"insert_run requires harness_status='incomplete', got {manifest.harness_status!r}"
            )

    def _validate_result_count(self, manifest: HarnessRun, result_count: int) -> None:
        if result_count != manifest.intent_count:
            raise IncompleteResultsError(
                f"finalize_run expected {manifest.intent_count} results, found {result_count}"
            )


class SqliteEvalStore(_StoreBase):
    """Local SQLite mirror of uc13.ops tables — spec Appendix I."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._ensure_schema()

    def close(self) -> None:
        self._conn.close()

    def _ensure_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS retrieval_harness_runs (
                run_id TEXT PRIMARY KEY,
                run_type TEXT NOT NULL,
                company_name TEXT NOT NULL,
                catalog TEXT NOT NULL,
                ingestion_snapshot TEXT NOT NULL,
                registry_hash TEXT NOT NULL,
                gold_snapshot TEXT NOT NULL,
                git_sha TEXT,
                git_branch TEXT,
                pr_url TEXT,
                hypothesis TEXT,
                affected_intents_json TEXT NOT NULL,
                gated_intents_json TEXT NOT NULL,
                ablation_config_json TEXT,
                ablation_arm TEXT,
                baseline_ref_run_id TEXT,
                store_backend TEXT NOT NULL,
                harness_status TEXT NOT NULL,
                intent_count INTEGER NOT NULL,
                gate_pass INTEGER,
                fallback_rate REAL,
                empty_rate REAL,
                e2e_agent_id TEXT,
                e2e_snapshot_table TEXT,
                e2e_checklist_score INTEGER,
                e2e_checklist_total INTEGER,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                intent_gates_json TEXT,
                rollup_by_agent_json TEXT,
                provenance_sample_json TEXT
            );

            CREATE TABLE IF NOT EXISTS retrieval_harness_results (
                run_id TEXT NOT NULL,
                intent_id TEXT NOT NULL,
                agent_id TEXT,
                eval_status TEXT NOT NULL,
                eval_k INTEGER,
                effective_k INTEGER,
                recall_at_10 REAL,
                precision_at_10 REAL,
                basis_conflict_at_10 REAL,
                mrr REAL,
                result_count INTEGER NOT NULL,
                mode TEXT,
                negatives_in_top_3 INTEGER,
                ablation_arm TEXT,
                PRIMARY KEY (run_id, intent_id),
                FOREIGN KEY (run_id) REFERENCES retrieval_harness_runs(run_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS retrieval_harness_deltas (
                run_id TEXT NOT NULL,
                baseline_ref_run_id TEXT NOT NULL,
                intent_id TEXT NOT NULL,
                metric TEXT NOT NULL,
                before_value REAL NOT NULL,
                after_value REAL NOT NULL,
                delta_value REAL NOT NULL,
                gate_pass INTEGER NOT NULL,
                in_gated_scope INTEGER NOT NULL,
                PRIMARY KEY (run_id, intent_id, metric),
                FOREIGN KEY (run_id) REFERENCES retrieval_harness_runs(run_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS retrieval_provenance (
                run_id TEXT NOT NULL,
                intent_id TEXT NOT NULL,
                company_name TEXT NOT NULL,
                catalog TEXT NOT NULL,
                query TEXT NOT NULL,
                mode TEXT NOT NULL,
                chunk_id TEXT NOT NULL,
                rank INTEGER NOT NULL,
                sim_score REAL NOT NULL,
                merge_score REAL NOT NULL,
                tier INTEGER NOT NULL,
                section_header TEXT NOT NULL,
                file_name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                chars_allocated INTEGER,
                context_section TEXT,
                created_at TEXT NOT NULL,
                PRIMARY KEY (run_id, intent_id, chunk_id, rank),
                FOREIGN KEY (run_id) REFERENCES retrieval_harness_runs(run_id) ON DELETE CASCADE
            );
            """
        )
        self._conn.commit()

    def _get_manifest_row(self, run_id: str) -> sqlite3.Row:
        row = self._conn.execute(
            "SELECT * FROM retrieval_harness_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            raise RunNotFoundError(f"run_id not found: {run_id}")
        return row

    def _row_to_manifest(self, row: sqlite3.Row) -> HarnessRun:
        gate_pass = row["gate_pass"]
        return HarnessRun(
            run_id=row["run_id"],
            run_type=row["run_type"],
            company_name=row["company_name"],
            catalog=row["catalog"],
            ingestion_snapshot=row["ingestion_snapshot"],
            registry_hash=row["registry_hash"],
            gold_snapshot=row["gold_snapshot"],
            git_sha=row["git_sha"],
            git_branch=row["git_branch"],
            pr_url=row["pr_url"],
            hypothesis=row["hypothesis"],
            affected_intents=_json_loads(row["affected_intents_json"]),
            gated_intents=_json_loads(row["gated_intents_json"]),
            ablation_config=_json_loads(row["ablation_config_json"]),
            ablation_arm=row["ablation_arm"],
            baseline_ref_run_id=row["baseline_ref_run_id"],
            store_backend=row["store_backend"],
            harness_status=row["harness_status"],
            intent_count=row["intent_count"],
            gate_pass=None if gate_pass is None else bool(gate_pass),
            fallback_rate=row["fallback_rate"],
            empty_rate=row["empty_rate"],
            e2e_agent_id=row["e2e_agent_id"],
            e2e_snapshot_table=row["e2e_snapshot_table"],
            e2e_checklist_score=row["e2e_checklist_score"],
            e2e_checklist_total=row["e2e_checklist_total"],
            created_at=_iso_to_dt(row["created_at"]),
            completed_at=_iso_to_dt(row["completed_at"]),
        )

    def _ensure_not_complete(self, run_id: str) -> HarnessRun:
        manifest = self._row_to_manifest(self._get_manifest_row(run_id))
        if manifest.harness_status == "complete":
            raise RunCompleteError(f"run_id already finalized: {run_id}")
        return manifest

    def insert_run(self, manifest: HarnessRun) -> str:
        self._validate_incomplete_manifest(manifest)
        existing = self._conn.execute(
            "SELECT harness_status FROM retrieval_harness_runs WHERE run_id = ?",
            (manifest.run_id,),
        ).fetchone()
        if existing is not None:
            if existing["harness_status"] == "complete":
                raise StoreError(f"run_id exists with complete status: {manifest.run_id}")
            raise StoreError(f"run_id already exists: {manifest.run_id}")

        self._conn.execute(
            """
            INSERT INTO retrieval_harness_runs (
                run_id, run_type, company_name, catalog, ingestion_snapshot,
                registry_hash, gold_snapshot, git_sha, git_branch, pr_url, hypothesis,
                affected_intents_json, gated_intents_json, ablation_config_json, ablation_arm,
                baseline_ref_run_id, store_backend, harness_status, intent_count,
                gate_pass, fallback_rate, empty_rate, e2e_agent_id, e2e_snapshot_table,
                e2e_checklist_score, e2e_checklist_total, created_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                manifest.run_id,
                manifest.run_type,
                manifest.company_name,
                manifest.catalog,
                manifest.ingestion_snapshot,
                manifest.registry_hash,
                manifest.gold_snapshot,
                manifest.git_sha,
                manifest.git_branch,
                manifest.pr_url,
                manifest.hypothesis,
                _json_dumps(manifest.affected_intents),
                _json_dumps(manifest.gated_intents),
                _json_dumps(manifest.ablation_config),
                manifest.ablation_arm,
                manifest.baseline_ref_run_id,
                manifest.store_backend,
                manifest.harness_status,
                manifest.intent_count,
                None if manifest.gate_pass is None else int(manifest.gate_pass),
                manifest.fallback_rate,
                manifest.empty_rate,
                manifest.e2e_agent_id,
                manifest.e2e_snapshot_table,
                manifest.e2e_checklist_score,
                manifest.e2e_checklist_total,
                _dt_to_iso(manifest.created_at),
                _dt_to_iso(manifest.completed_at),
            ),
        )
        self._conn.commit()
        logger.debug("insert_run upsert key run_id=%s", manifest.run_id)
        return manifest.run_id

    def append_results(self, run_id: str, results: list[HarnessResult]) -> int:
        self._ensure_not_complete(run_id)
        for result in results:
            logger.debug(
                "append_results upsert (%s, %s)",
                run_id,
                result.intent_id,
            )
            self._conn.execute(
                """
                INSERT INTO retrieval_harness_results (
                    run_id, intent_id, agent_id, eval_status, eval_k, effective_k,
                    recall_at_10, precision_at_10, basis_conflict_at_10, mrr,
                    result_count, mode, negatives_in_top_3, ablation_arm
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, intent_id) DO UPDATE SET
                    agent_id = excluded.agent_id,
                    eval_status = excluded.eval_status,
                    eval_k = excluded.eval_k,
                    effective_k = excluded.effective_k,
                    recall_at_10 = excluded.recall_at_10,
                    precision_at_10 = excluded.precision_at_10,
                    basis_conflict_at_10 = excluded.basis_conflict_at_10,
                    mrr = excluded.mrr,
                    result_count = excluded.result_count,
                    mode = excluded.mode,
                    negatives_in_top_3 = excluded.negatives_in_top_3,
                    ablation_arm = excluded.ablation_arm
                """,
                (
                    run_id,
                    result.intent_id,
                    derive_agent_id(result.intent_id),
                    result.eval_status,
                    result.eval_k,
                    result.effective_k,
                    result.recall_at_10,
                    result.precision_at_10,
                    result.basis_conflict_at_10,
                    result.mrr,
                    result.result_count,
                    result.mode,
                    result.negatives_in_top_3,
                    result.ablation_arm,
                ),
            )
        self._conn.commit()
        return len(results)

    def append_provenance(self, run_id: str, records: list[ProvenanceRecord]) -> int:
        manifest = self._ensure_not_complete(run_id)
        written = 0
        created_at = _dt_to_iso(_utc_now())
        for record in records:
            for chunk in record.chunks:
                logger.debug(
                    "append_provenance upsert (%s, %s, %s, %s)",
                    run_id,
                    record.intent_id,
                    chunk.chunk_id,
                    chunk.rank,
                )
                self._conn.execute(
                    """
                    INSERT INTO retrieval_provenance (
                        run_id, intent_id, company_name, catalog, query, mode,
                        chunk_id, rank, sim_score, merge_score, tier,
                        section_header, file_name, source_type,
                        chars_allocated, context_section, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id, intent_id, chunk_id, rank) DO UPDATE SET
                        company_name = excluded.company_name,
                        catalog = excluded.catalog,
                        query = excluded.query,
                        mode = excluded.mode,
                        sim_score = excluded.sim_score,
                        merge_score = excluded.merge_score,
                        tier = excluded.tier,
                        section_header = excluded.section_header,
                        file_name = excluded.file_name,
                        source_type = excluded.source_type,
                        chars_allocated = excluded.chars_allocated,
                        context_section = excluded.context_section,
                        created_at = excluded.created_at
                    """,
                    (
                        run_id,
                        record.intent_id,
                        record.company_name,
                        manifest.catalog,
                        record.query,
                        record.mode,
                        chunk.chunk_id,
                        chunk.rank,
                        chunk.sim_score,
                        chunk.merge_score,
                        chunk.tier,
                        chunk.section_header,
                        chunk.file_name,
                        chunk.source_type,
                        record.chars_allocated,
                        record.context_section,
                        created_at,
                    ),
                )
                written += 1
        self._conn.commit()
        return written

    def append_deltas(self, run_id: str, deltas: list[HarnessDelta]) -> int:
        self._ensure_not_complete(run_id)
        for delta in deltas:
            logger.debug(
                "append_deltas upsert (%s, %s, %s)",
                run_id,
                delta.intent_id,
                delta.metric,
            )
            self._conn.execute(
                """
                INSERT INTO retrieval_harness_deltas (
                    run_id, baseline_ref_run_id, intent_id, metric,
                    before_value, after_value, delta_value, gate_pass, in_gated_scope
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, intent_id, metric) DO UPDATE SET
                    baseline_ref_run_id = excluded.baseline_ref_run_id,
                    before_value = excluded.before_value,
                    after_value = excluded.after_value,
                    delta_value = excluded.delta_value,
                    gate_pass = excluded.gate_pass,
                    in_gated_scope = excluded.in_gated_scope
                """,
                (
                    run_id,
                    delta.baseline_ref_run_id,
                    delta.intent_id,
                    delta.metric,
                    delta.before,
                    delta.after,
                    delta.delta,
                    int(delta.gate_pass),
                    int(delta.in_gated_scope),
                ),
            )
        self._conn.commit()
        return len(deltas)

    def set_report_extras(
        self,
        run_id: str,
        *,
        intent_gates: list[IntentGateSummary] | None = None,
        rollup_by_agent: dict[str, Any] | None = None,
        provenance_sample: list[ProvenanceRecord] | None = None,
    ) -> None:
        """Persist JSON-only HarnessReport fields not mirrored in normalized tables."""
        self._get_manifest_row(run_id)
        self._conn.execute(
            """
            UPDATE retrieval_harness_runs
            SET intent_gates_json = COALESCE(?, intent_gates_json),
                rollup_by_agent_json = COALESCE(?, rollup_by_agent_json),
                provenance_sample_json = COALESCE(?, provenance_sample_json)
            WHERE run_id = ?
            """,
            (
                _json_dumps(
                    [item.model_dump(mode="json") for item in intent_gates]
                    if intent_gates is not None
                    else None
                ),
                _json_dumps(rollup_by_agent),
                _json_dumps(
                    [item.model_dump(mode="json") for item in provenance_sample]
                    if provenance_sample is not None
                    else None
                ),
                run_id,
            ),
        )
        self._conn.commit()

    def finalize_run(
        self,
        run_id: str,
        *,
        gate_pass: bool | None,
        fallback_rate: float | None,
        empty_rate: float | None = None,
    ) -> HarnessRun:
        manifest = self._ensure_not_complete(run_id)
        result_count = self._conn.execute(
            "SELECT COUNT(*) AS c FROM retrieval_harness_results WHERE run_id = ?",
            (run_id,),
        ).fetchone()["c"]
        self._validate_result_count(manifest, result_count)

        completed_at = _utc_now()
        self._conn.execute(
            """
            UPDATE retrieval_harness_runs
            SET harness_status = 'complete',
                completed_at = ?,
                gate_pass = ?,
                fallback_rate = ?,
                empty_rate = COALESCE(?, empty_rate)
            WHERE run_id = ?
            """,
            (
                _dt_to_iso(completed_at),
                None if gate_pass is None else int(gate_pass),
                fallback_rate,
                empty_rate,
                run_id,
            ),
        )
        self._conn.commit()
        return self._row_to_manifest(self._get_manifest_row(run_id))

    def get_run(self, run_id: str) -> HarnessReport:
        row = self._get_manifest_row(run_id)
        manifest = self._row_to_manifest(row)
        results = [
            HarnessResult(
                intent_id=result_row["intent_id"],
                eval_status=result_row["eval_status"],
                eval_k=result_row["eval_k"],
                effective_k=result_row["effective_k"],
                recall_at_10=result_row["recall_at_10"],
                precision_at_10=result_row["precision_at_10"],
                basis_conflict_at_10=result_row["basis_conflict_at_10"],
                mrr=result_row["mrr"],
                result_count=result_row["result_count"],
                mode=result_row["mode"],
                negatives_in_top_3=result_row["negatives_in_top_3"],
                ablation_arm=result_row["ablation_arm"],
            )
            for result_row in self._conn.execute(
                """
                SELECT * FROM retrieval_harness_results
                WHERE run_id = ?
                ORDER BY intent_id
                """,
                (run_id,),
            )
        ]
        deltas = [
            HarnessDelta(
                run_id=delta_row["run_id"],
                baseline_ref_run_id=delta_row["baseline_ref_run_id"],
                intent_id=delta_row["intent_id"],
                metric=delta_row["metric"],
                before=delta_row["before_value"],
                after=delta_row["after_value"],
                delta=delta_row["delta_value"],
                gate_pass=bool(delta_row["gate_pass"]),
                in_gated_scope=bool(delta_row["in_gated_scope"]),
            )
            for delta_row in self._conn.execute(
                """
                SELECT * FROM retrieval_harness_deltas
                WHERE run_id = ?
                ORDER BY intent_id, metric
                """,
                (run_id,),
            )
        ]
        intent_gates_raw = _json_loads(row["intent_gates_json"])
        intent_gates = (
            [IntentGateSummary.model_validate(item) for item in intent_gates_raw]
            if intent_gates_raw
            else None
        )
        provenance_sample_raw = _json_loads(row["provenance_sample_json"])
        provenance_sample = (
            [ProvenanceRecord.model_validate(item) for item in provenance_sample_raw]
            if provenance_sample_raw
            else None
        )
        return HarnessReport(
            manifest=manifest,
            results=results,
            intent_gates=intent_gates,
            rollup_by_agent=_json_loads(row["rollup_by_agent_json"]),
            deltas=deltas or None,
            provenance_sample=provenance_sample,
        )

    def list_runs(
        self,
        *,
        company_name: str,
        catalog: str,
        run_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[HarnessRun]:
        limit = min(max(limit, 0), _LIST_RUNS_MAX_LIMIT)
        query = """
            SELECT * FROM retrieval_harness_runs
            WHERE company_name = ? AND catalog = ?
        """
        params: list[Any] = [company_name, catalog]
        if run_type is not None:
            query += " AND run_type = ?"
            params.append(run_type)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_manifest(row) for row in rows]

    def delete_run(self, run_id: str) -> None:
        self._get_manifest_row(run_id)
        self._conn.execute(
            "DELETE FROM retrieval_harness_deltas WHERE run_id = ?",
            (run_id,),
        )
        self._conn.execute(
            "DELETE FROM retrieval_harness_results WHERE run_id = ?",
            (run_id,),
        )
        self._conn.execute(
            "DELETE FROM retrieval_provenance WHERE run_id = ?",
            (run_id,),
        )
        self._conn.execute(
            "DELETE FROM retrieval_harness_runs WHERE run_id = ?",
            (run_id,),
        )
        self._conn.commit()

    def get_latest_baseline(self, company_name: str, catalog: str) -> str | None:
        row = self._conn.execute(
            """
            SELECT run_id
            FROM retrieval_harness_runs
            WHERE company_name = ? AND catalog = ?
              AND run_type = 'baseline'
              AND harness_status = 'complete'
            ORDER BY completed_at DESC
            LIMIT 1
            """,
            (company_name, catalog),
        ).fetchone()
        return None if row is None else row["run_id"]

    def promote_sqlite_run(self, run_id: str) -> None:
        raise SyncError("promote_sqlite_run requires DeltaEvalStore target backend")


class DeltaEvalStore(_StoreBase):
    """Databricks Delta backend for uc13.ops — DDL via apply_ops_ddl."""

    def __init__(
        self,
        spark: Any,
        *,
        catalog: str = "uc13",
        sqlite_path: str | Path | None = None,
    ) -> None:
        self.spark = spark
        self.catalog = catalog
        self.ops = f"{catalog}.ops"
        self.sqlite_path = Path(sqlite_path) if sqlite_path is not None else None

    def _table(self, name: str) -> str:
        return f"{self.ops}.{name}"

    def _fetch_manifest_row(self, run_id: str) -> dict[str, Any]:
        rows = (
            self.spark.sql(
                f"SELECT * FROM {self._table('retrieval_harness_runs')} WHERE run_id = :run_id",
                args={"run_id": run_id},
            )
            .collect()
        )
        if not rows:
            raise RunNotFoundError(f"run_id not found: {run_id}")
        return rows[0].asDict(recursive=True)

    def _manifest_from_row(self, row: dict[str, Any]) -> HarnessRun:
        return HarnessRun(
            run_id=row["run_id"],
            run_type=row["run_type"],
            company_name=row["company_name"],
            catalog=row["catalog"],
            ingestion_snapshot=row["ingestion_snapshot"],
            registry_hash=row["registry_hash"],
            gold_snapshot=row["gold_snapshot"],
            git_sha=row.get("git_sha"),
            git_branch=row.get("git_branch"),
            pr_url=row.get("pr_url"),
            hypothesis=row.get("hypothesis"),
            affected_intents=list(row["affected_intents"]),
            gated_intents=list(row["gated_intents"]),
            ablation_config=_json_loads(row["ablation_config"])
            if isinstance(row.get("ablation_config"), str)
            else row.get("ablation_config"),
            ablation_arm=row.get("ablation_arm"),
            baseline_ref_run_id=row.get("baseline_ref_run_id"),
            store_backend=row["store_backend"],
            harness_status=row["harness_status"],
            intent_count=int(row["intent_count"]),
            gate_pass=row.get("gate_pass"),
            fallback_rate=row.get("fallback_rate"),
            empty_rate=row.get("empty_rate"),
            e2e_agent_id=row.get("e2e_agent_id"),
            e2e_snapshot_table=row.get("e2e_snapshot_table"),
            e2e_checklist_score=row.get("e2e_checklist_score"),
            e2e_checklist_total=row.get("e2e_checklist_total"),
            created_at=row["created_at"],
            completed_at=row.get("completed_at"),
        )

    def _ensure_not_complete(self, run_id: str) -> HarnessRun:
        manifest = self._manifest_from_row(self._fetch_manifest_row(run_id))
        if manifest.harness_status == "complete":
            raise RunCompleteError(f"run_id already finalized: {run_id}")
        return manifest

    def insert_run(self, manifest: HarnessRun) -> str:
        self._validate_incomplete_manifest(manifest)
        existing = self.spark.sql(
            f"""
            SELECT harness_status
            FROM {self._table('retrieval_harness_runs')}
            WHERE run_id = :run_id
            """,
            args={"run_id": manifest.run_id},
        ).collect()
        if existing:
            if existing[0]["harness_status"] == "complete":
                raise StoreError(
                    f"run_id exists with complete status: {manifest.run_id}"
                )
            raise StoreError(f"run_id already exists: {manifest.run_id}")

        payload = manifest.model_dump(mode="json")
        payload["ablation_config"] = _json_dumps(manifest.ablation_config)
        payload["affected_intents"] = manifest.affected_intents
        payload["gated_intents"] = manifest.gated_intents
        frame = self.spark.createDataFrame([payload])
        frame.write.format("delta").mode("append").saveAsTable(
            self._table("retrieval_harness_runs")
        )
        logger.debug("insert_run upsert key run_id=%s", manifest.run_id)
        return manifest.run_id

    def append_results(self, run_id: str, results: list[HarnessResult]) -> int:
        self._ensure_not_complete(run_id)
        if not results:
            return 0
        rows = []
        for result in results:
            row = result.model_dump(mode="json")
            row["run_id"] = run_id
            row["agent_id"] = derive_agent_id(result.intent_id)
            rows.append(row)
            logger.debug(
                "append_results upsert (%s, %s)",
                run_id,
                result.intent_id,
            )
        frame = self.spark.createDataFrame(rows)
        frame.createOrReplaceTempView("incoming_results")
        self.spark.sql(
            f"""
            MERGE INTO {self._table('retrieval_harness_results')} AS target
            USING incoming_results AS source
            ON target.run_id = source.run_id AND target.intent_id = source.intent_id
            WHEN MATCHED THEN UPDATE SET *
            WHEN NOT MATCHED THEN INSERT *
            """
        )
        return len(results)

    def append_provenance(self, run_id: str, records: list[ProvenanceRecord]) -> int:
        manifest = self._ensure_not_complete(run_id)
        rows: list[dict[str, Any]] = []
        created_at = _utc_now()
        for record in records:
            for chunk in record.chunks:
                rows.append(
                    {
                        "run_id": run_id,
                        "intent_id": record.intent_id,
                        "company_name": record.company_name,
                        "catalog": manifest.catalog,
                        "query": record.query,
                        "mode": record.mode,
                        "chunk_id": chunk.chunk_id,
                        "rank": chunk.rank,
                        "sim_score": chunk.sim_score,
                        "merge_score": chunk.merge_score,
                        "tier": chunk.tier,
                        "section_header": chunk.section_header,
                        "file_name": chunk.file_name,
                        "source_type": chunk.source_type,
                        "chars_allocated": record.chars_allocated,
                        "context_section": record.context_section,
                        "created_at": created_at,
                    }
                )
                logger.debug(
                    "append_provenance upsert (%s, %s, %s, %s)",
                    run_id,
                    record.intent_id,
                    chunk.chunk_id,
                    chunk.rank,
                )
        if not rows:
            return 0
        frame = self.spark.createDataFrame(rows)
        frame.createOrReplaceTempView("incoming_provenance")
        self.spark.sql(
            f"""
            MERGE INTO {self._table('retrieval_provenance')} AS target
            USING incoming_provenance AS source
            ON target.run_id = source.run_id
              AND target.intent_id = source.intent_id
              AND target.chunk_id = source.chunk_id
              AND target.rank = source.rank
            WHEN MATCHED THEN UPDATE SET *
            WHEN NOT MATCHED THEN INSERT *
            """
        )
        return len(rows)

    def append_deltas(self, run_id: str, deltas: list[HarnessDelta]) -> int:
        self._ensure_not_complete(run_id)
        if not deltas:
            return 0
        rows = []
        for delta in deltas:
            rows.append(
                {
                    "run_id": delta.run_id,
                    "baseline_ref_run_id": delta.baseline_ref_run_id,
                    "intent_id": delta.intent_id,
                    "metric": delta.metric,
                    "before": delta.before,
                    "after": delta.after,
                    "delta": delta.delta,
                    "gate_pass": delta.gate_pass,
                    "in_gated_scope": delta.in_gated_scope,
                }
            )
            logger.debug(
                "append_deltas upsert (%s, %s, %s)",
                run_id,
                delta.intent_id,
                delta.metric,
            )
        frame = self.spark.createDataFrame(rows)
        frame.createOrReplaceTempView("incoming_deltas")
        self.spark.sql(
            f"""
            MERGE INTO {self._table('retrieval_harness_deltas')} AS target
            USING incoming_deltas AS source
            ON target.run_id = source.run_id
              AND target.intent_id = source.intent_id
              AND target.metric = source.metric
            WHEN MATCHED THEN UPDATE SET *
            WHEN NOT MATCHED THEN INSERT *
            """
        )
        return len(deltas)

    def finalize_run(
        self,
        run_id: str,
        *,
        gate_pass: bool | None,
        fallback_rate: float | None,
        empty_rate: float | None = None,
    ) -> HarnessRun:
        manifest = self._ensure_not_complete(run_id)
        result_count = self.spark.sql(
            f"""
            SELECT COUNT(*) AS c
            FROM {self._table('retrieval_harness_results')}
            WHERE run_id = :run_id
            """,
            args={"run_id": run_id},
        ).collect()[0]["c"]
        self._validate_result_count(manifest, int(result_count))

        completed_at = _utc_now()
        self.spark.sql(
            f"""
            UPDATE {self._table('retrieval_harness_runs')}
            SET harness_status = 'complete',
                completed_at = :completed_at,
                gate_pass = :gate_pass,
                fallback_rate = :fallback_rate,
                empty_rate = COALESCE(:empty_rate, empty_rate)
            WHERE run_id = :run_id
            """,
            args={
                "run_id": run_id,
                "completed_at": completed_at,
                "gate_pass": gate_pass,
                "fallback_rate": fallback_rate,
                "empty_rate": empty_rate,
            },
        )
        return self._manifest_from_row(self._fetch_manifest_row(run_id))

    def get_run(self, run_id: str) -> HarnessReport:
        manifest = self._manifest_from_row(self._fetch_manifest_row(run_id))
        results = [
            HarnessResult.model_validate(row.asDict(recursive=True))
            for row in self.spark.sql(
                f"""
                SELECT intent_id, eval_status, eval_k, effective_k, recall_at_10,
                       precision_at_10, basis_conflict_at_10, mrr, result_count,
                       mode, negatives_in_top_3, ablation_arm
                FROM {self._table('retrieval_harness_results')}
                WHERE run_id = :run_id
                ORDER BY intent_id
                """,
                args={"run_id": run_id},
            ).collect()
        ]
        deltas = [
            HarnessDelta.model_validate(row.asDict(recursive=True))
            for row in self.spark.sql(
                f"""
                SELECT run_id, baseline_ref_run_id, intent_id, metric,
                       before, after, delta, gate_pass, in_gated_scope
                FROM {self._table('retrieval_harness_deltas')}
                WHERE run_id = :run_id
                ORDER BY intent_id, metric
                """,
                args={"run_id": run_id},
            ).collect()
        ]
        return HarnessReport(
            manifest=manifest,
            results=results,
            deltas=deltas or None,
        )

    def list_runs(
        self,
        *,
        company_name: str,
        catalog: str,
        run_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[HarnessRun]:
        limit = min(max(limit, 0), _LIST_RUNS_MAX_LIMIT)
        type_filter = "AND run_type = :run_type" if run_type is not None else ""
        rows = self.spark.sql(
            f"""
            SELECT *
            FROM {self._table('retrieval_harness_runs')}
            WHERE company_name = :company_name AND catalog = :catalog
            {type_filter}
            ORDER BY created_at DESC
            LIMIT {limit} OFFSET {offset}
            """,
            args={
                "company_name": company_name,
                "catalog": catalog,
                "run_type": run_type,
            },
        ).collect()
        return [self._manifest_from_row(row.asDict(recursive=True)) for row in rows]

    def delete_run(self, run_id: str) -> None:
        self._fetch_manifest_row(run_id)
        for table in (
            "retrieval_harness_deltas",
            "retrieval_harness_results",
            "retrieval_provenance",
            "retrieval_harness_runs",
        ):
            self.spark.sql(
                f"DELETE FROM {self._table(table)} WHERE run_id = :run_id",
                args={"run_id": run_id},
            )

    def get_latest_baseline(self, company_name: str, catalog: str) -> str | None:
        rows = self.spark.sql(
            f"""
            SELECT run_id
            FROM {self._table('retrieval_harness_latest_baseline')}
            WHERE company_name = :company_name AND catalog = :catalog
            LIMIT 1
            """,
            args={"company_name": company_name, "catalog": catalog},
        ).collect()
        return None if not rows else rows[0]["run_id"]

    def promote_sqlite_run(self, run_id: str) -> None:
        if self.sqlite_path is None:
            raise SyncError("sqlite_path required for promote_sqlite_run")
        source = SqliteEvalStore(self.sqlite_path)
        try:
            report = source.get_run(run_id)
        except RunNotFoundError as exc:
            raise SyncError(f"sqlite source missing run_id: {run_id}") from exc
        finally:
            source.close()

        if report.manifest.harness_status != "complete":
            raise SyncError(f"sqlite run incomplete: {run_id}")

        existing = self.spark.sql(
            f"""
            SELECT harness_status
            FROM {self._table('retrieval_harness_runs')}
            WHERE run_id = :run_id
            """,
            args={"run_id": run_id},
        ).collect()
        if existing and existing[0]["harness_status"] == "complete":
            logger.debug("promote_sqlite_run skip existing complete run_id=%s", run_id)
            return

        delta_manifest = report.manifest.model_copy(update={"store_backend": "delta"})
        self.insert_run(delta_manifest)
        self.append_results(run_id, report.results)
        if report.deltas:
            self.append_deltas(run_id, report.deltas)
        finalized = self.finalize_run(
            run_id,
            gate_pass=delta_manifest.gate_pass,
            fallback_rate=delta_manifest.fallback_rate,
            empty_rate=delta_manifest.empty_rate,
        )
        if finalized.harness_status != "complete":
            raise SyncError(f"promotion failed for run_id: {run_id}")
