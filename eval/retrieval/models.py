"""Pydantic v2 models for the UC13 RE² eval program — spec §5.8."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class RetrievalIntent(BaseModel):
    """Registry record — one semantic_search call site."""

    model_config = ConfigDict(extra="forbid")

    intent_id: str
    agent_id: str
    source_file: str
    catalog: str
    query: str
    workstream_filter: list[str] | None = None
    file_name_filter: list[str] | None = None
    top_k: int
    min_chunk_length: int | None = None
    min_results: int | None = None
    source_type_priority: bool | None = None
    source_type_filter: list[str] | None = None
    tier_filter: int | None = None
    retrieval_mode: str | None = None
    invocation_path: Literal["direct", "with_fallback"]
    extraction_confidence: Literal["static", "manual"] | None = None


class GoldLabel(BaseModel):
    """Per-intent, per-company gold labels."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    intent_id: str
    company_name: str
    catalog: str
    gold_status: Literal["ready", "bootstrap_failed", "partial"]
    positive_chunk_ids: list[str] = Field(
        validation_alias=AliasChoices("positive_chunk_ids", "gold_chunk_ids"),
    )
    negative_chunk_ids: list[str] | None = None
    negative_rule: str | None = None
    negative_method: (
        Literal[
            "section_rule",
            "basis_rule",
            "bad_run_replay",
            "cross_intent_positive",
            "manual_audit",
        ]
        | None
    ) = None
    gold_method: Literal[
        "citation_backfill",
        "section_range",
        "filename_closure",
        "provenance_replay",
        "manual_audit",
    ]
    ingestion_snapshot: str
    confidence: Literal["high", "medium", "low"]
    negative_confidence: Literal["high", "medium", "low"] | None = None
    notes: str | None = None


class FixtureChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    file_name: str
    section_header: str
    page_start: int
    source_type: str
    priority_tier: int
    chunk_text_preview: str


class EvalFixtureSlice(BaseModel):
    """CI frozen organic data slice."""

    model_config = ConfigDict(extra="forbid")

    catalog: str
    company_name: str
    ingestion_snapshot: str
    chunks: list[FixtureChunk]
    intents: list[GoldLabel]
    mock_vs_scores: dict[str, Any] | None = None


class ProvenanceChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    rank: int
    sim_score: float
    merge_score: float
    tier: int
    section_header: str
    file_name: str
    source_type: str


class ProvenanceRecord(BaseModel):
    """Per retrieval call provenance row."""

    model_config = ConfigDict(extra="forbid")

    intent_id: str
    company_name: str
    query: str
    mode: str
    chunks: list[ProvenanceChunk]
    chars_allocated: int | None = None
    context_section: str | None = None
    run_id: str | None = None


class HarnessResult(BaseModel):
    """Per-intent harness metrics."""

    model_config = ConfigDict(extra="forbid")

    intent_id: str
    eval_status: Literal["evaluated", "skipped_bootstrap_failed"]
    eval_k: int | None = None
    effective_k: int | None = None
    recall_at_10: float | None = None
    precision_at_10: float | None = None
    basis_conflict_at_10: float | None = None
    mrr: float | None = None
    result_count: int
    mode: str | None = None
    negatives_in_top_3: int | None = None
    ablation_arm: str | None = None


class HarnessRun(BaseModel):
    """Run manifest — attribution root."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    run_type: Literal["baseline", "enhancement", "ablation", "ci_fixture"]
    company_name: str
    catalog: str
    ingestion_snapshot: str
    registry_hash: str
    gold_snapshot: str
    git_sha: str | None = None
    git_branch: str | None = None
    pr_url: str | None = None
    hypothesis: str | None = None
    affected_intents: list[str]
    gated_intents: list[str]
    ablation_config: dict[str, Any] | None = None
    ablation_arm: str | None = None
    baseline_ref_run_id: str | None = None
    store_backend: Literal["delta", "sqlite"]
    harness_status: Literal["complete", "incomplete", "invalid"]
    intent_count: int
    gate_pass: bool | None = None
    fallback_rate: float | None = None
    empty_rate: float | None = None
    e2e_agent_id: str | None = None
    e2e_snapshot_table: str | None = None
    e2e_checklist_score: int | None = None
    e2e_checklist_total: int | None = None
    created_at: datetime
    completed_at: datetime | None = None


class IntentGateSummary(BaseModel):
    """Per-intent gate rollup for PR merge approval."""

    model_config = ConfigDict(extra="forbid")

    intent_id: str
    intent_gate_pass: bool
    in_gated_scope: bool
    eval_status: Literal["evaluated", "skipped_bootstrap_failed"]
    metric_results: dict[str, Any] | None = None


class HarnessDelta(BaseModel):
    """Per-intent metric delta vs baseline."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    baseline_ref_run_id: str
    intent_id: str
    metric: Literal[
        "recall_at_10",
        "precision_at_10",
        "basis_conflict_at_10",
        "mrr",
    ]
    before: float
    after: float
    delta: float
    gate_pass: bool
    in_gated_scope: bool


class HarnessReport(BaseModel):
    """Top-level harness report envelope."""

    model_config = ConfigDict(extra="forbid")

    manifest: HarnessRun
    results: list[HarnessResult]
    intent_gates: list[IntentGateSummary] | None = None
    rollup_by_agent: dict[str, Any] | None = None
    deltas: list[HarnessDelta] | None = None
    provenance_sample: list[ProvenanceRecord] | None = None
    report_md_path: str | None = None
