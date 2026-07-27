"""Pipeline provenance builder and emitter — M-RE2 T2."""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from eval.retrieval.errors import ProvenanceEmitError
from eval.retrieval.models import ProvenanceChunk, ProvenanceRecord, RetrievalIntent
from eval.retrieval.store import (
    DeltaEvalStore,
    EvalStore,
    SqliteEvalStore,
    retry_on_delta_conflict,
)

logger = logging.getLogger(__name__)

MODE_ALIASES = {
    "vector": "semantic",
    "keyword_fallback": "keyword",
}


def default_sqlite_path() -> Path:
    return Path(__file__).resolve().parents[2] / "eval" / "retrieval" / ".local" / "re2_store.sqlite"


def normalize_mode(mode: str | None) -> str:
    if mode is None:
        return "semantic"
    return MODE_ALIASES.get(mode, mode)


def _provenance_required() -> bool:
    return os.environ.get("RE2_PROVENANCE_REQUIRED", "0") == "1"


def _active_spark() -> Any | None:
    try:
        from pyspark.sql import SparkSession
    except ImportError:
        return None
    return SparkSession.getActiveSession()


def resolve_store() -> EvalStore:
    """Resolve EvalStore backend per D5 — sqlite default without Spark (local harness only)."""
    backend = os.environ.get("RE2_STORE_BACKEND", "").strip().lower()
    if backend == "sqlite":
        return SqliteEvalStore(default_sqlite_path())

    spark = _active_spark()
    on_cluster = os.environ.get("DATABRICKS_RUNTIME_VERSION") is not None

    if backend == "delta":
        if spark is None:
            raise ProvenanceEmitError(
                "RE2_STORE_BACKEND=delta requires an active SparkSession"
            )
        catalog = os.environ.get("RE2_CATALOG", "uc13")
        return DeltaEvalStore(spark, catalog=catalog)

    if spark is not None:
        catalog = os.environ.get("RE2_CATALOG", "uc13")
        return DeltaEvalStore(spark, catalog=catalog)

    if on_cluster:
        raise ProvenanceEmitError(
            "Delta provenance store required on Databricks cluster "
            "(pass spark= to open_agent_run, or set RE2_STORE_BACKEND=sqlite "
            "for local harness only)"
        )

    return SqliteEvalStore(default_sqlite_path())


def _chunk_id_from_row(chunk: Any) -> str:
    if isinstance(chunk, Mapping):
        return str(chunk["chunk_id"])
    return str(chunk.chunk_id)


def _row_attr(chunk: Any, name: str, default: Any = "") -> Any:
    if isinstance(chunk, Mapping):
        return chunk.get(name, default)
    return getattr(chunk, name, default)


def _build_provenance_chunks(route_result: Any) -> list[ProvenanceChunk]:
    chunks: list[ProvenanceChunk] = []
    scores = list(route_result.scores or [])
    for rank, chunk in enumerate(route_result.chunks, start=1):
        score = scores[rank - 1] if rank - 1 < len(scores) else 0.0
        tier = _row_attr(chunk, "priority_tier", 99)
        chunks.append(
            ProvenanceChunk(
                chunk_id=_chunk_id_from_row(chunk),
                rank=rank,
                sim_score=0.0 if route_result.mode == "keyword" else float(score),
                merge_score=float(score),
                tier=int(tier) if tier is not None else 99,
                section_header=str(_row_attr(chunk, "section_header", "")),
                file_name=str(_row_attr(chunk, "file_name", "")),
                source_type=str(_row_attr(chunk, "source_type", "text")),
            )
        )
    return chunks


def build_provenance_record(
    intent: RetrievalIntent,
    *,
    company_name: str,
    route_result: Any,
    run_id: str,
) -> ProvenanceRecord:
    return ProvenanceRecord(
        intent_id=intent.intent_id,
        company_name=company_name,
        query=intent.query,
        mode=normalize_mode(route_result.mode),
        chunks=_build_provenance_chunks(route_result),
        run_id=run_id,
    )


class ProvenanceEmitter:
    """Append per-retrieval provenance rows for open pipeline agent runs."""

    _intents_by_run: dict[str, set[str]] = {}
    _logged_runs: set[str] = set()

    @classmethod
    def emit(
        cls,
        *,
        route_result: Any,
        company_name: str,
        query: str,
        intent_id: str | None = None,
    ) -> None:
        from agents.shared.run_context import (
            _ACTIVE_STORE,
            get_agent_run_id,
            get_current_agent_id,
            get_pipeline_thread,
        )

        agent_run_id = get_agent_run_id()
        if agent_run_id is None:
            if _provenance_required():
                raise ProvenanceEmitError(
                    "provenance emit requires an open agent run "
                    "(RE2_PROVENANCE_REQUIRED=1)"
                )
            return

        store = _ACTIVE_STORE.get()
        if store is None:
            if _provenance_required():
                raise ProvenanceEmitError(
                    "provenance store unavailable for open agent run "
                    "(RE2_PROVENANCE_REQUIRED=1)"
                )
            return

        agent_id = get_current_agent_id() or "unknown"
        resolved_intent_id = intent_id or f"unknown.{agent_id}"

        record = ProvenanceRecord(
            intent_id=resolved_intent_id,
            company_name=company_name,
            query=query,
            mode=normalize_mode(route_result.mode),
            chunks=_build_provenance_chunks(route_result),
            run_id=agent_run_id,
        )

        for chunk in record.chunks:
            logger.debug(
                "provenance upsert run_id=%s intent_id=%s chunk_id=%s rank=%s",
                agent_run_id,
                resolved_intent_id,
                chunk.chunk_id,
                chunk.rank,
            )

        store.append_provenance(agent_run_id, [record])

        intent_set = cls._intents_by_run.setdefault(agent_run_id, set())
        intent_set.add(resolved_intent_id)
        if agent_run_id not in cls._logged_runs:
            logger.info(
                "provenance agent_run_id=%s pipeline_thread_id=%s intent_count=%s",
                agent_run_id,
                get_pipeline_thread(),
                len(intent_set),
            )
            cls._logged_runs.add(agent_run_id)

    @classmethod
    def patch_context_allocations(
        cls,
        intent_id: str,
        allocations: list[Any],
    ) -> None:
        """Upsert ``chars_allocated`` / ``context_section`` on existing provenance rows."""
        from agents.shared.run_context import (
            _ACTIVE_STORE,
            get_agent_run_id,
        )
        from eval.retrieval.store import DeltaEvalStore, SqliteEvalStore

        agent_run_id = get_agent_run_id()
        if agent_run_id is None:
            if _provenance_required():
                raise ProvenanceEmitError(
                    "provenance patch requires an open agent run "
                    "(RE2_PROVENANCE_REQUIRED=1)"
                )
            return

        store = _ACTIVE_STORE.get()
        if store is None:
            if _provenance_required():
                raise ProvenanceEmitError(
                    "provenance store unavailable for open agent run "
                    "(RE2_PROVENANCE_REQUIRED=1)"
                )
            return

        if not allocations:
            return

        patch_rows: list[tuple[int, str, str]] = []
        for alloc in allocations:
            chunk_id = _chunk_id_from_row(alloc.chunk)
            patch_rows.append(
                (alloc.chars_allocated, alloc.context_section, chunk_id)
            )
            logger.debug(
                "provenance patch run_id=%s intent_id=%s chunk_id=%s chars=%s",
                agent_run_id,
                intent_id,
                chunk_id,
                alloc.chars_allocated,
            )

        if isinstance(store, SqliteEvalStore):
            for chars_allocated, context_section, chunk_id in patch_rows:
                store._conn.execute(
                    """
                    UPDATE retrieval_provenance
                    SET chars_allocated = ?, context_section = ?
                    WHERE run_id = ? AND intent_id = ? AND chunk_id = ?
                    """,
                    (
                        chars_allocated,
                        context_section,
                        agent_run_id,
                        intent_id,
                        chunk_id,
                    ),
                )
            store._conn.commit()
            return

        if isinstance(store, DeltaEvalStore):
            # Batched into ONE MERGE per call (was: one UPDATE per chunk in a loop).
            # OPEX can allocate 10-20+ chunks per intent; per-chunk UPDATEs were the
            # dominant source of concurrent Delta transactions racing against
            # Revenue/EBITDA's MERGE calls on the same table (M-RE2 T4 follow-on).
            from pyspark.sql.types import IntegerType, StringType, StructField, StructType

            patch_schema = StructType(
                [
                    StructField("chunk_id", StringType(), False),
                    StructField("chars_allocated", IntegerType(), True),
                    StructField("context_section", StringType(), True),
                ]
            )
            patch_frame = store.spark.createDataFrame(
                [
                    {
                        "chunk_id": chunk_id,
                        "chars_allocated": int(chars_allocated),
                        "context_section": context_section,
                    }
                    for chars_allocated, context_section, chunk_id in patch_rows
                ],
                schema=patch_schema,
            )
            temp_view = f"provenance_patch_{uuid.uuid4().hex}"
            patch_frame.createOrReplaceTempView(temp_view)

            def _run_merge() -> None:
                store.spark.sql(
                    f"""
                    MERGE INTO {store._table('retrieval_provenance')} AS target
                    USING {temp_view} AS source
                    ON target.run_id = '{agent_run_id}'
                      AND target.intent_id = '{intent_id}'
                      AND target.chunk_id = source.chunk_id
                    WHEN MATCHED THEN UPDATE SET
                        chars_allocated = source.chars_allocated,
                        context_section = source.context_section
                    """
                )

            with store._provenance_write_lock:
                retry_on_delta_conflict(_run_merge)
            return

        if _provenance_required():
            raise ProvenanceEmitError(
                f"unsupported store type for provenance patch: {type(store).__name__}"
            )
