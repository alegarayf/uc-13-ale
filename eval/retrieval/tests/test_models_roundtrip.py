"""Round-trip serialization tests for eval/retrieval Pydantic models — spec §5.8."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
import yaml

from eval.retrieval.models import (
    EvalFixtureSlice,
    FixtureChunk,
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


def _sample_retrieval_intent() -> RetrievalIntent:
    return RetrievalIntent(
        intent_id="fta.opex.q1_financial_statements",
        agent_id="fta.opex",
        source_file="databricks/agents/subagents/workstream/financial/opex_sub_agent.py",
        catalog="uc13_ale",
        query="operating expenses financial statements",
        workstream_filter=["FINANCIAL"],
        top_k=10,
        min_chunk_length=150,
        min_results=3,
        invocation_path="with_fallback",
        extraction_confidence="static",
    )


def _sample_gold_label() -> GoldLabel:
    return GoldLabel(
        intent_id="fta.opex.q1_financial_statements",
        company_name="Elder Care",
        catalog="uc13_ale",
        gold_status="ready",
        positive_chunk_ids=["chunk-001", "chunk-002"],
        negative_chunk_ids=["chunk-099"],
        negative_method="section_rule",
        gold_method="citation_backfill",
        ingestion_snapshot="uc13_ale:35034:2026-06-25",
        confidence="high",
        negative_confidence="medium",
    )


def _roundtrip_json(model_cls, instance):
  payload = instance.model_dump(mode="json")
  restored = model_cls.model_validate(payload)
  assert restored == instance
  return restored


def _roundtrip_yaml(model_cls, instance):
    payload = instance.model_dump(mode="json")
    yaml_text = yaml.safe_dump(payload, sort_keys=False)
    loaded = yaml.safe_load(yaml_text)
    restored = model_cls.model_validate(loaded)
    assert restored == instance
    return restored


def test_retrieval_intent_json_roundtrip():
    _roundtrip_json(RetrievalIntent, _sample_retrieval_intent())


def test_gold_label_json_roundtrip():
    _roundtrip_json(GoldLabel, _sample_gold_label())


def test_gold_label_accepts_gold_chunk_ids_alias():
    raw = {
        "intent_id": "kpi.revenue",
        "company_name": "Elder Care",
        "catalog": "uc13_ale",
        "gold_status": "ready",
        "gold_chunk_ids": ["c1"],
        "gold_method": "manual_audit",
        "ingestion_snapshot": "uc13_ale:1:2026-06-25",
        "confidence": "low",
    }
    label = GoldLabel.model_validate(raw)
    assert label.positive_chunk_ids == ["c1"]
    dumped = label.model_dump(mode="json")
    assert "positive_chunk_ids" in dumped
    assert dumped["positive_chunk_ids"] == ["c1"]


def test_harness_run_yaml_roundtrip():
    run = HarnessRun(
        run_id="baseline_abc123_20260701",
        run_type="baseline",
        company_name="Elder Care",
        catalog="uc13_ale",
        ingestion_snapshot="uc13_ale:35034:2026-06-25",
        registry_hash="a" * 64,
        gold_snapshot="b" * 64,
        affected_intents=["fta.opex.q1_financial_statements"],
        gated_intents=["fta.opex.q1_financial_statements"],
        store_backend="delta",
        harness_status="incomplete",
        intent_count=1,
        gate_pass=None,
        created_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
    )
    _roundtrip_yaml(HarnessRun, run)


def test_harness_result_and_delta_json_roundtrip():
    result = HarnessResult(
        intent_id="fta.opex.q1_financial_statements",
        eval_status="evaluated",
        eval_k=10,
        effective_k=5,
        recall_at_10=0.5,
        precision_at_10=0.8,
        mrr=0.25,
        result_count=5,
        mode="semantic",
    )
    _roundtrip_json(HarnessResult, result)

    delta = HarnessDelta(
        run_id="enh_001",
        baseline_ref_run_id="baseline_abc123_20260701",
        intent_id="fta.opex.q1_financial_statements",
        metric="recall_at_10",
        before=0.4,
        after=0.5,
        delta=0.1,
        gate_pass=True,
        in_gated_scope=True,
    )
    _roundtrip_json(HarnessDelta, delta)


def test_provenance_record_json_roundtrip():
    record = ProvenanceRecord(
        intent_id="legal.contracts",
        company_name="Elder Care",
        query="material contracts",
        mode="keyword",
        chunks=[
            ProvenanceChunk(
                chunk_id="c1",
                rank=1,
                sim_score=0.0,
                merge_score=0.7,
                tier=2,
                section_header="Contracts",
                file_name="msa.pdf",
                source_type="text",
            )
        ],
        run_id="baseline_abc123_20260701",
    )
    _roundtrip_json(ProvenanceRecord, record)


def test_harness_report_full_envelope_roundtrip():
    manifest = HarnessRun(
        run_id="baseline_abc123_20260701",
        run_type="baseline",
        company_name="Elder Care",
        catalog="uc13_ale",
        ingestion_snapshot="uc13_ale:35034:2026-06-25",
        registry_hash="a" * 64,
        gold_snapshot="b" * 64,
        affected_intents=["fta.opex.q1_financial_statements"],
        gated_intents=["fta.opex.q1_financial_statements"],
        store_backend="sqlite",
        harness_status="complete",
        intent_count=1,
        fallback_rate=0.0,
        empty_rate=0.0,
        created_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 7, 1, 12, 5, tzinfo=timezone.utc),
    )
    report = HarnessReport(
        manifest=manifest,
        results=[
            HarnessResult(
                intent_id="fta.opex.q1_financial_statements",
                eval_status="evaluated",
                eval_k=10,
                effective_k=3,
                recall_at_10=1.0,
                mrr=1.0,
                result_count=3,
                mode="semantic",
            )
        ],
        intent_gates=[
            IntentGateSummary(
                intent_id="fta.opex.q1_financial_statements",
                intent_gate_pass=True,
                in_gated_scope=True,
                eval_status="evaluated",
            )
        ],
        rollup_by_agent={
            "fta.opex": {
                "intent_count": 1,
                "recall_at_10_avg": 1.0,
            }
        },
    )
    payload = report.model_dump(mode="json")
    text = json.dumps(payload, sort_keys=True)
    restored = HarnessReport.model_validate(json.loads(text))
    assert restored == report


def test_eval_fixture_slice_yaml_roundtrip():
    fixture = EvalFixtureSlice(
        catalog="uc13_ale",
        company_name="Elder Care",
        ingestion_snapshot="uc13_ale:35034:2026-06-25",
        chunks=[
            FixtureChunk(
                chunk_id="chunk-001",
                file_name="CIM.pdf",
                section_header="Financial Overview",
                page_start=12,
                source_type="text",
                priority_tier=1,
                chunk_text_preview="Revenue grew 15% year over year.",
            )
        ],
        intents=[_sample_gold_label()],
    )
    _roundtrip_yaml(EvalFixtureSlice, fixture)


def test_models_reject_unknown_fields():
    with pytest.raises(Exception):
        RetrievalIntent.model_validate(
            {
                **_sample_retrieval_intent().model_dump(),
                "unexpected_field": True,
            }
        )
