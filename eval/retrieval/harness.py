"""EvalHarness runner — spec §5.12.1 / §5.12.8 / §5.12.9."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eval.retrieval.errors import (
    BaselineInvalidError,
    CoverageError,
    GoldSnapshotMismatchError,
    IngestionSnapshotMismatchError,
    PreconditionError,
    RegistryHashMismatchError,
)
from eval.retrieval.gold.bootstrap import (
    load_gold_labels,
    load_registry,
    validate_ingestion_snapshot_consistency,
)
from eval.retrieval.models import (
    GoldLabel,
    HarnessDelta,
    HarnessReport,
    HarnessResult,
    HarnessRun,
    IntentGateSummary,
    ProvenanceChunk,
    ProvenanceRecord,
    RetrievalIntent,
)
from eval.retrieval.scope_resolver import gate_eligible_intent_ids
from eval.retrieval.store import EvalStore, SqliteEvalStore, derive_agent_id

logger = logging.getLogger(__name__)

MODE_ALIASES = {
    "vector": "semantic",
    "keyword_fallback": "keyword",
}

GATE_METRICS = ("recall_at_10", "precision_at_10", "basis_conflict_at_10")
AUDIT_METRICS = ("mrr",)

HIGHER_IS_BETTER = frozenset({"recall_at_10", "precision_at_10", "mrr"})
LOWER_IS_BETTER = frozenset({"basis_conflict_at_10"})


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_registry_path() -> Path:
    return _repo_root() / "eval" / "retrieval" / "intent_registry.yaml"


def default_gold_path(company_slug: str = "elder_care") -> Path:
    return _repo_root() / "eval" / "retrieval" / "gold_labels" / f"{company_slug}.yaml"


def default_reports_dir() -> Path:
    return _repo_root() / "eval" / "retrieval" / "reports"


def default_sqlite_path() -> Path:
    return _repo_root() / "eval" / "retrieval" / ".local" / "re2_store.sqlite"


def normalize_mode(mode: str | None) -> str:
    if mode is None:
        return "semantic"
    return MODE_ALIASES.get(mode, mode)


def compute_registry_hash(registry_path: Path) -> str:
    return hashlib.sha256(registry_path.read_bytes()).hexdigest()


def _canonical_gold_row(label: GoldLabel) -> dict[str, Any]:
    negatives = sorted(label.negative_chunk_ids or [])
    return {
        "intent_id": label.intent_id,
        "positive_chunk_ids": sorted(label.positive_chunk_ids),
        "negative_chunk_ids": negatives,
        "gold_status": label.gold_status,
        "ingestion_snapshot": label.ingestion_snapshot,
    }


def compute_gold_snapshot(labels: Sequence[GoldLabel]) -> str:
    """Canonical JSON SHA-256 per spec §5.8."""
    rows = sorted(
        (_canonical_gold_row(label) for label in labels),
        key=lambda row: row["intent_id"],
    )
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _chunk_id_from_row(chunk: Any) -> str:
    if isinstance(chunk, Mapping):
        return str(chunk["chunk_id"])
    return str(chunk.chunk_id)


def _row_attr(chunk: Any, name: str, default: Any = "") -> Any:
    if isinstance(chunk, Mapping):
        return chunk.get(name, default)
    return getattr(chunk, name, default)


def uses_fallback_wrapper(intent: RetrievalIntent) -> bool:
    if intent.invocation_path == "with_fallback":
        return True
    if intent.min_results is not None:
        return True
    return bool(intent.file_name_filter)


def build_search_kwargs(
    intent: RetrievalIntent,
    *,
    company_name: str,
    spark: Any,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "query": intent.query,
        "spark": spark,
        "company_name": company_name,
        "top_k": intent.top_k,
        "workstream_filter": intent.workstream_filter,
        "file_name_filter": intent.file_name_filter,
        "catalog": intent.catalog,
    }
    if intent.min_chunk_length is not None:
        kwargs["min_chunk_length"] = intent.min_chunk_length
    if intent.tier_filter is not None:
        kwargs["tier_filter"] = intent.tier_filter
    if intent.source_type_priority is not None:
        kwargs["source_type_priority"] = intent.source_type_priority
    if intent.source_type_filter is not None:
        kwargs["source_type_filter"] = intent.source_type_filter
    return kwargs


def dispatch_retrieval(
    intent: RetrievalIntent,
    *,
    company_name: str,
    spark: Any,
) -> Any:
    """Production-faithful retrieval dispatch — imports migrated semantic_search."""
    from agents.shared.retrieval import semantic_search

    kwargs = build_search_kwargs(intent, company_name=company_name, spark=spark)
    result = semantic_search(**kwargs)
    if uses_fallback_wrapper(intent):
        min_results = intent.min_results if intent.min_results is not None else 3
        if len(result.chunks) < min_results and intent.file_name_filter:
            result = semantic_search(**{**kwargs, "file_name_filter": None})
    return result


def compute_mrr(positive_ids: set[str], ranked_ids: Sequence[str]) -> float:
    for index, chunk_id in enumerate(ranked_ids, start=1):
        if chunk_id in positive_ids:
            return 1.0 / index
    return 0.0


def compute_metrics(
    intent: RetrievalIntent,
    gold: GoldLabel,
    route_result: Any,
) -> HarnessResult:
    """Metric math per spec §5.8."""
    if gold.gold_status == "bootstrap_failed" or not gold.positive_chunk_ids:
        return HarnessResult(
            intent_id=intent.intent_id,
            eval_status="skipped_bootstrap_failed",
            result_count=0,
        )

    ranked_ids = [_chunk_id_from_row(chunk) for chunk in route_result.chunks]
    result_count = len(ranked_ids)
    eval_k = min(10, intent.top_k)
    effective_k = min(eval_k, result_count)
    positives = set(gold.positive_chunk_ids)
    negatives = set(gold.negative_chunk_ids or [])

    top_eval = ranked_ids[:eval_k]
    top_effective = ranked_ids[:effective_k]

    recall = len(positives & set(top_eval)) / len(positives) if positives else 0.0
    if result_count == 0:
        recall = 0.0

    precision_at_10 = None
    if negatives and result_count > 0:
        conflict_count = len(negatives & set(top_effective))
        precision_at_10 = (effective_k - conflict_count) / effective_k

    basis_conflict_at_10 = None
    if (
        gold.negative_method == "basis_rule"
        and negatives
        and result_count > 0
    ):
        basis_conflict_at_10 = len(negatives & set(top_effective)) / effective_k

    negatives_in_top_3 = len(negatives & set(ranked_ids[:3])) if negatives else None

    return HarnessResult(
        intent_id=intent.intent_id,
        eval_status="evaluated",
        eval_k=eval_k,
        effective_k=effective_k,
        recall_at_10=recall,
        precision_at_10=precision_at_10,
        basis_conflict_at_10=basis_conflict_at_10,
        mrr=compute_mrr(positives, ranked_ids),
        result_count=result_count,
        mode=normalize_mode(route_result.mode),
        negatives_in_top_3=negatives_in_top_3,
    )


def metric_gate_pass(metric: str, before: float, after: float) -> bool:
    if metric in LOWER_IS_BETTER:
        return after <= before
    if metric in HIGHER_IS_BETTER:
        return after >= before
    raise ValueError(f"unknown gate metric: {metric}")


def _metric_value(result: HarnessResult, metric: str) -> float | None:
    return getattr(result, metric)


def build_harness_deltas(
    *,
    run_id: str,
    baseline_ref_run_id: str,
    intent_id: str,
    baseline: HarnessResult,
    current: HarnessResult,
    in_gated_scope: bool,
) -> list[HarnessDelta]:
    deltas: list[HarnessDelta] = []
    for metric in (*GATE_METRICS, *AUDIT_METRICS):
        before = _metric_value(baseline, metric)
        after = _metric_value(current, metric)
        if before is None or after is None:
            continue
        delta = after - before
        deltas.append(
            HarnessDelta(
                run_id=run_id,
                baseline_ref_run_id=baseline_ref_run_id,
                intent_id=intent_id,
                metric=metric,  # type: ignore[arg-type]
                before=before,
                after=after,
                delta=delta,
                gate_pass=metric_gate_pass(metric, before, after),
                in_gated_scope=in_gated_scope,
            )
        )
    return deltas


def build_intent_gate_summary(
    intent_id: str,
    *,
    baseline: HarnessResult | None,
    current: HarnessResult,
    deltas: Sequence[HarnessDelta],
    in_gated_scope: bool,
) -> IntentGateSummary:
    if current.eval_status == "skipped_bootstrap_failed":
        return IntentGateSummary(
            intent_id=intent_id,
            intent_gate_pass=True,
            in_gated_scope=False,
            eval_status="skipped_bootstrap_failed",
        )

    gate_deltas = [
        row
        for row in deltas
        if row.metric in GATE_METRICS and row.in_gated_scope
    ]
    intent_gate_pass = all(row.gate_pass for row in gate_deltas) if gate_deltas else True

    metric_results = {
        row.metric: {
            "before": row.before,
            "after": row.after,
            "delta": row.delta,
            "gate_pass": row.gate_pass,
        }
        for row in deltas
    }

    return IntentGateSummary(
        intent_id=intent_id,
        intent_gate_pass=intent_gate_pass,
        in_gated_scope=in_gated_scope,
        eval_status=current.eval_status,
        metric_results=metric_results or None,
    )


def compare_results(
    *,
    run_id: str,
    baseline_ref_run_id: str,
    gated_intents: Sequence[str],
    baseline_results: Mapping[str, HarnessResult],
    current_results: Mapping[str, HarnessResult],
) -> tuple[list[HarnessDelta], list[IntentGateSummary]]:
    """Pure compare aggregation — golden gate tests target this function."""
    deltas: list[HarnessDelta] = []
    intent_gates: list[IntentGateSummary] = []

    for intent_id in sorted(gated_intents):
        current = current_results[intent_id]
        baseline = baseline_results[intent_id]
        in_scope = True
        intent_deltas = build_harness_deltas(
            run_id=run_id,
            baseline_ref_run_id=baseline_ref_run_id,
            intent_id=intent_id,
            baseline=baseline,
            current=current,
            in_gated_scope=in_scope,
        )
        deltas.extend(intent_deltas)
        intent_gates.append(
            build_intent_gate_summary(
                intent_id,
                baseline=baseline,
                current=current,
                deltas=intent_deltas,
                in_gated_scope=in_scope,
            )
        )

    for intent_id, current in sorted(current_results.items()):
        if intent_id in gated_intents:
            continue
        if current.eval_status != "skipped_bootstrap_failed":
            continue
        intent_gates.append(
            IntentGateSummary(
                intent_id=intent_id,
                intent_gate_pass=True,
                in_gated_scope=False,
                eval_status="skipped_bootstrap_failed",
            )
        )

    return deltas, intent_gates


def rollup_by_agent(
    results: Sequence[HarnessResult],
) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[HarnessResult]] = {}
    for result in results:
        if result.eval_status != "evaluated":
            continue
        agent_id = derive_agent_id(result.intent_id)
        buckets.setdefault(agent_id, []).append(result)

    rollup: dict[str, dict[str, Any]] = {}
    for agent_id, rows in sorted(buckets.items()):
        recall_vals = [row.recall_at_10 for row in rows if row.recall_at_10 is not None]
        precision_vals = [
            row.precision_at_10 for row in rows if row.precision_at_10 is not None
        ]
        basis_vals = [
            row.basis_conflict_at_10
            for row in rows
            if row.basis_conflict_at_10 is not None
        ]
        evaluated = len(rows)
        fallback = sum(1 for row in rows if row.mode == "keyword")
        empty = sum(1 for row in rows if row.result_count == 0)
        rollup[agent_id] = {
            "intent_count": evaluated,
            "recall_at_10_avg": sum(recall_vals) / len(recall_vals) if recall_vals else None,
            "precision_at_10_avg": (
                sum(precision_vals) / len(precision_vals) if precision_vals else None
            ),
            "basis_conflict_at_10_avg": (
                sum(basis_vals) / len(basis_vals) if basis_vals else None
            ),
            "fallback_rate": fallback / evaluated if evaluated else None,
            "empty_rate": empty / evaluated if evaluated else None,
        }
    return rollup


def build_provenance_record(
    intent: RetrievalIntent,
    *,
    company_name: str,
    route_result: Any,
    run_id: str,
) -> ProvenanceRecord:
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
    return ProvenanceRecord(
        intent_id=intent.intent_id,
        company_name=company_name,
        query=intent.query,
        mode=normalize_mode(route_result.mode),
        chunks=chunks,
        run_id=run_id,
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _git_sha() -> str | None:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=_repo_root(),
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except (OSError, subprocess.CalledProcessError):
        return None


def _write_report_atomic(path: Path, report: HarnessReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    payload = report.model_dump(mode="json")
    temp_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temp_path.replace(path)


class EvalHarness:
    """Offline harness runner with store dual-write."""

    def __init__(
        self,
        *,
        registry_path: Path | None = None,
        gold_path: Path | None = None,
        reports_dir: Path | None = None,
        retrieval_dispatch: Callable[..., Any] | None = None,
    ) -> None:
        self.registry_path = registry_path or default_registry_path()
        self.gold_path = gold_path or default_gold_path()
        self.reports_dir = reports_dir or default_reports_dir()
        self._retrieval_dispatch = retrieval_dispatch or dispatch_retrieval

    def _load_intent_map(self) -> dict[str, RetrievalIntent]:
        intents = load_registry(self.registry_path)
        return {intent.intent_id: intent for intent in intents}

    def _load_gold_map(
        self,
        *,
        company_name: str,
        catalog: str,
    ) -> dict[str, GoldLabel]:
        labels = [
            label
            for label in load_gold_labels(self.gold_path)
            if label.company_name == company_name and label.catalog == catalog
        ]
        return {label.intent_id: label for label in labels}

    def _resolve_scope(
        self,
        *,
        run_type: str,
        registry_map: Mapping[str, RetrievalIntent],
        gold_map: Mapping[str, GoldLabel],
        company_name: str,
        catalog: str,
        affected_intents: Sequence[str] | None,
        gated_intents: Sequence[str] | None,
    ) -> tuple[list[str], list[str]]:
        if affected_intents is None:
            if run_type == "enhancement":
                raise PreconditionError(
                    "run_type enhancement requires explicit affected_intents"
                )
            affected = sorted(registry_map.keys())
        else:
            affected = sorted(affected_intents)

        if gated_intents is None:
            eligible = set(
                gate_eligible_intent_ids(
                    gold_map.values(),
                    company_name=company_name,
                    catalog=catalog,
                )
            )
            gated = sorted(intent_id for intent_id in affected if intent_id in eligible)
        else:
            gated = sorted(gated_intents)

        return affected, gated

    def validate_baseline_ref(
        self,
        store: EvalStore,
        baseline_run_id: str,
        *,
        gated_intents: Sequence[str],
        current_manifest: HarnessRun,
    ) -> None:
        """Preflight baseline checks — spec §5.12.8 steps 2–6."""
        baseline_report = store.get_run(baseline_run_id)
        baseline = baseline_report.manifest

        if baseline.harness_status != "complete":
            raise BaselineInvalidError(
                f"baseline run not complete: {baseline_run_id} ({baseline.harness_status})"
            )
        if baseline.run_type != "baseline":
            raise BaselineInvalidError(
                f"baseline_ref_run_id must reference run_type baseline, got {baseline.run_type}"
            )

        baseline_by_intent = {row.intent_id: row for row in baseline_report.results}
        missing = [
            intent_id
            for intent_id in gated_intents
            if baseline_by_intent.get(intent_id) is None
            or baseline_by_intent[intent_id].eval_status != "evaluated"
        ]
        if missing:
            raise CoverageError(
                f"baseline missing evaluated rows for gated intents: {missing}"
            )

        if baseline.gold_snapshot != current_manifest.gold_snapshot:
            raise GoldSnapshotMismatchError(
                "gold_snapshot mismatch between baseline and current manifest"
            )
        if baseline.registry_hash != current_manifest.registry_hash:
            raise RegistryHashMismatchError(
                "registry_hash mismatch between baseline and current manifest"
            )
        if baseline.ingestion_snapshot != current_manifest.ingestion_snapshot:
            raise IngestionSnapshotMismatchError(
                "ingestion_snapshot mismatch between baseline and current manifest"
            )

    def compare(
        self,
        store: EvalStore,
        baseline_run_id: str,
        current_run_id: str,
        *,
        gated_intents: Sequence[str] | None = None,
    ) -> tuple[list[HarnessDelta], list[IntentGateSummary]]:
        current_report = store.get_run(current_run_id)
        current_manifest = current_report.manifest
        scope = (
            list(gated_intents)
            if gated_intents is not None
            else list(current_manifest.gated_intents)
        )

        self.validate_baseline_ref(
            store,
            baseline_run_id,
            gated_intents=scope,
            current_manifest=current_manifest,
        )

        baseline_report = store.get_run(baseline_run_id)
        baseline_by_intent = {row.intent_id: row for row in baseline_report.results}
        current_by_intent = {row.intent_id: row for row in current_report.results}

        return compare_results(
            run_id=current_run_id,
            baseline_ref_run_id=baseline_run_id,
            gated_intents=scope,
            baseline_results=baseline_by_intent,
            current_results=current_by_intent,
        )

    def run(
        self,
        *,
        run_type: str,
        company_name: str,
        catalog: str,
        store: EvalStore,
        store_backend: str,
        baseline_ref_run_id: str | None = None,
        affected_intents: Sequence[str] | None = None,
        gated_intents: Sequence[str] | None = None,
        ablation_config: dict[str, Any] | None = None,
        spark: Any | None = None,
        run_id: str | None = None,
        skip_retrieval: bool = False,
    ) -> HarnessReport:
        registry_map = self._load_intent_map()
        gold_labels = [
            label
            for label in load_gold_labels(self.gold_path)
            if label.company_name == company_name and label.catalog == catalog
        ]
        if not gold_labels:
            raise PreconditionError(
                f"no gold labels for company_name={company_name!r} catalog={catalog!r}"
            )

        ingestion_snapshot = validate_ingestion_snapshot_consistency(gold_labels)
        registry_hash = compute_registry_hash(self.registry_path)
        gold_snapshot = compute_gold_snapshot(gold_labels)
        gold_map = {label.intent_id: label for label in gold_labels}

        resolved_affected, resolved_gated = self._resolve_scope(
            run_type=run_type,
            registry_map=registry_map,
            gold_map=gold_map,
            company_name=company_name,
            catalog=catalog,
            affected_intents=affected_intents,
            gated_intents=gated_intents,
        )

        for intent_id in resolved_affected:
            if intent_id not in registry_map:
                raise PreconditionError(f"unknown intent_id in scope: {intent_id}")
            if intent_id not in gold_map:
                raise PreconditionError(f"missing gold label for intent_id: {intent_id}")

        if run_type in {"enhancement", "ablation"} and not baseline_ref_run_id:
            baseline_ref_run_id = store.get_latest_baseline(company_name, catalog)
            if baseline_ref_run_id is None:
                raise BaselineInvalidError("no complete baseline run found for tenant")

        manifest = HarnessRun(
            run_id=run_id or f"{run_type}_{uuid.uuid4().hex[:12]}",
            run_type=run_type,  # type: ignore[arg-type]
            company_name=company_name,
            catalog=catalog,
            ingestion_snapshot=ingestion_snapshot,
            registry_hash=registry_hash,
            gold_snapshot=gold_snapshot,
            git_sha=_git_sha(),
            git_branch=os.environ.get("GIT_BRANCH"),
            affected_intents=resolved_affected,
            gated_intents=resolved_gated,
            ablation_config=ablation_config,
            baseline_ref_run_id=baseline_ref_run_id,
            store_backend=store_backend,  # type: ignore[arg-type]
            harness_status="incomplete",
            intent_count=len(resolved_affected),
            created_at=_utc_now(),
        )

        if baseline_ref_run_id and run_type in {"enhancement", "ablation"}:
            self.validate_baseline_ref(
                store,
                baseline_ref_run_id,
                gated_intents=resolved_gated,
                current_manifest=manifest,
            )

        store.insert_run(manifest)
        results: list[HarnessResult] = []
        provenance_records: list[ProvenanceRecord] = []

        active_spark = spark
        if not skip_retrieval and active_spark is None:
            try:
                from pyspark.sql import SparkSession

                active_spark = SparkSession.getActiveSession()
            except ImportError:
                active_spark = None
            if active_spark is None:
                raise PreconditionError(
                    "SparkSession required for live retrieval dispatch"
                )

        for intent_id in resolved_affected:
            intent = registry_map[intent_id]
            gold = gold_map[intent_id]
            if gold.gold_status == "bootstrap_failed" or not gold.positive_chunk_ids:
                result_count = 0
                if not skip_retrieval:
                    route_result = self._retrieval_dispatch(
                        intent,
                        company_name=company_name,
                        spark=active_spark,
                    )
                    result_count = len(route_result.chunks)
                    provenance_records.append(
                        build_provenance_record(
                            intent,
                            company_name=company_name,
                            route_result=route_result,
                            run_id=manifest.run_id,
                        )
                    )
                result = HarnessResult(
                    intent_id=intent_id,
                    eval_status="skipped_bootstrap_failed",
                    result_count=result_count,
                )
                results.append(result)
                logger.info(
                    "intent_id=%s mode=skipped result_count=%s eval_status=skipped_bootstrap_failed",
                    intent_id,
                    result_count,
                )
                continue

            if skip_retrieval:
                raise PreconditionError("skip_retrieval set but intent is gate-eligible")

            route_result = self._retrieval_dispatch(
                intent,
                company_name=company_name,
                spark=active_spark,
            )
            result = compute_metrics(intent, gold, route_result)
            results.append(result)
            provenance_records.append(
                build_provenance_record(
                    intent,
                    company_name=company_name,
                    route_result=route_result,
                    run_id=manifest.run_id,
                )
            )
            logger.info(
                "intent_id=%s mode=%s result_count=%s eval_status=%s",
                intent_id,
                result.mode,
                result.result_count,
                result.eval_status,
            )

        store.append_results(manifest.run_id, results)
        if provenance_records:
            store.append_provenance(manifest.run_id, provenance_records)

        deltas: list[HarnessDelta] | None = None
        intent_gates: list[IntentGateSummary] | None = None
        gate_pass: bool | None = None

        if run_type in {"enhancement", "ablation"} and baseline_ref_run_id:
            deltas, intent_gates = self.compare(
                store,
                baseline_ref_run_id,
                manifest.run_id,
                gated_intents=resolved_gated,
            )
            store.append_deltas(manifest.run_id, deltas)
            evaluated_gates = [
                gate
                for gate in intent_gates
                if gate.in_gated_scope and gate.eval_status == "evaluated"
            ]
            gate_pass = (
                all(gate.intent_gate_pass for gate in evaluated_gates)
                if evaluated_gates
                else None
            )

        agent_rollup = rollup_by_agent(results)
        evaluated_rows = [row for row in results if row.eval_status == "evaluated"]
        fallback_rate = None
        empty_rate = None
        if evaluated_rows:
            fallback_rate = sum(
                1 for row in evaluated_rows if row.mode == "keyword"
            ) / len(evaluated_rows)
            empty_rate = sum(
                1 for row in evaluated_rows if row.result_count == 0
            ) / len(evaluated_rows)

        report = HarnessReport(
            manifest=manifest,
            results=results,
            intent_gates=intent_gates,
            rollup_by_agent=agent_rollup,
            deltas=deltas,
            provenance_sample=provenance_records[:5] or None,
        )

        _write_report_atomic(self.reports_dir / f"{manifest.run_id}.json", report)

        if isinstance(store, SqliteEvalStore):
            store.set_report_extras(
                manifest.run_id,
                intent_gates=intent_gates,
                rollup_by_agent=agent_rollup,
                provenance_sample=report.provenance_sample,
            )

        finalized = store.finalize_run(
            manifest.run_id,
            gate_pass=gate_pass,
            fallback_rate=fallback_rate,
            empty_rate=empty_rate,
        )
        report.manifest = finalized
        return report
