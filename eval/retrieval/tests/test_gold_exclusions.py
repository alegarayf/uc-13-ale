"""Tests for GoldLabel aggregate exclusion machinery — Contract T3-a/b/c."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from eval.retrieval.errors import PreconditionError
from eval.retrieval.gold.bootstrap import (
    GoldLabelBootstrap,
    load_gold_exclusions,
    load_kpi_claim_intent_map,
    write_gold_labels,
)
from eval.retrieval.harness import compute_metrics
from eval.retrieval.models import EXCLUDE_REASON_VOCABULARY, GoldLabel, RetrievalIntent
from eval.retrieval.scope_resolver import is_gate_eligible

REPO_ROOT = Path(__file__).resolve().parents[3]
GOLD_EXCLUSIONS_PATH = (
    REPO_ROOT / "eval" / "retrieval" / "gold" / "gold_exclusions.yaml"
)
KPI_MAP_PATH = REPO_ROOT / "eval" / "retrieval" / "gold" / "kpi_claim_intent_map.yaml"

LAUNCH_EXCLUDED_KPI = frozenset(
    {
        "kpi.retrieve_healthcare_labor_market",
    }
)
BENCH_AND_CAPACITY = "kpi.retrieve_bench_and_capacity"


class MockSpark:
    def __init__(self, handlers: dict[str, list[dict]] | None = None) -> None:
        self.handlers = handlers or {"COUNT(*) AS chunk_count": [{"chunk_count": 1}]}
        self.queries: list[str] = []

    def sql(self, query: str) -> "MockDataFrame":
        self.queries.append(query)
        normalized = " ".join(query.split())
        for pattern, rows in self.handlers.items():
            if pattern in normalized:
                return MockDataFrame(rows)
        return MockDataFrame([])


class MockDataFrame:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = [SimpleNamespace(**row) for row in rows]

    def collect(self) -> list[SimpleNamespace]:
        return self._rows


def _sample_intent(intent_id: str) -> RetrievalIntent:
    agent_id = intent_id.split(".")[0]
    return RetrievalIntent.model_validate(
        {
            "intent_id": intent_id,
            "agent_id": agent_id,
            "source_file": "databricks/agents/workstreams/example.py",
            "catalog": "uc13_ale",
            "query": "sample query",
            "top_k": 10,
            "invocation_path": "direct",
        }
    )


def test_gold_label_aggregate_exclude_requires_exclude_reason():
    with pytest.raises(ValueError, match="aggregate_exclude and exclude_reason"):
        GoldLabel(
            intent_id="kpi.retrieve_pipeline_backlog",
            company_name="Elder Care",
            catalog="uc13_ale",
            gold_status="bootstrap_failed",
            positive_chunk_ids=[],
            gold_method="citation_backfill",
            ingestion_snapshot="uc13_ale:1:2026-08-11",
            confidence="low",
            aggregate_exclude=True,
        )


def test_gold_label_exclude_reason_requires_aggregate_exclude():
    with pytest.raises(ValueError, match="aggregate_exclude and exclude_reason"):
        GoldLabel(
            intent_id="kpi.retrieve_pipeline_backlog",
            company_name="Elder Care",
            catalog="uc13_ale",
            gold_status="bootstrap_failed",
            positive_chunk_ids=[],
            gold_method="citation_backfill",
            ingestion_snapshot="uc13_ale:1:2026-08-11",
            confidence="low",
            exclude_reason="no_citation_source",
        )


def test_write_gold_labels_rejects_out_of_vocabulary_exclude_reason(tmp_path):
    label = GoldLabel(
        intent_id="kpi.retrieve_pipeline_backlog",
        company_name="Elder Care",
        catalog="uc13_ale",
        gold_status="bootstrap_failed",
        positive_chunk_ids=[],
        gold_method="citation_backfill",
        ingestion_snapshot="uc13_ale:1:2026-08-11",
        confidence="low",
        aggregate_exclude=True,
        exclude_reason="unknown_reason",
    )
    with pytest.raises(PreconditionError, match="not in closed vocabulary"):
        write_gold_labels(tmp_path / "gold.yaml", [label])


def test_gold_exclusions_population_is_two_intents():
    exclusions = load_gold_exclusions(GOLD_EXCLUSIONS_PATH)
    assert len(exclusions) == 2
    assert "profiler.company_size_indicators" in exclusions
    assert all(reason == "no_citation_source" for reason in exclusions.values())


def test_gold_exclusions_totality_and_disjointness():
    claim_map, intent_block = load_kpi_claim_intent_map(KPI_MAP_PATH)
    exclusions = load_gold_exclusions(GOLD_EXCLUSIONS_PATH)
    claim_mapped = set(claim_map.values())
    excluded_kpi = {intent_id for intent_id in exclusions if intent_id.startswith("kpi.")}

    unmappable_kpi = {
        intent_id
        for intent_id, meta in intent_block.items()
        if isinstance(meta, dict) and meta.get("role") == "unmappable"
    }

    assert excluded_kpi == LAUNCH_EXCLUDED_KPI
    assert excluded_kpi.isdisjoint(claim_mapped)
    assert BENCH_AND_CAPACITY in claim_mapped
    assert BENCH_AND_CAPACITY not in exclusions
    assert excluded_kpi == unmappable_kpi


def test_bootstrap_short_circuits_excluded_intent():
    spark = MockSpark()
    bootstrap = GoldLabelBootstrap(spark, ingestion_date=date(2026, 8, 11))
    label = bootstrap.bootstrap([_sample_intent("profiler.company_size_indicators")])[0]

    assert label.gold_status == "bootstrap_failed"
    assert label.positive_chunk_ids == []
    assert label.aggregate_exclude is True
    assert label.exclude_reason == "no_citation_source"
    assert label.exclude_reason in EXCLUDE_REASON_VOCABULARY
    assert "aggregate_exclude" in (label.notes or "")


def test_is_gate_eligible_false_for_aggregate_exclude_even_when_ready():
    label = GoldLabel(
        intent_id="kpi.retrieve_pipeline_backlog",
        company_name="Elder Care",
        catalog="uc13_ale",
        gold_status="ready",
        positive_chunk_ids=["chunk-001"],
        gold_method="citation_backfill",
        ingestion_snapshot="uc13_ale:1:2026-08-11",
        confidence="high",
        aggregate_exclude=True,
        exclude_reason="no_citation_source",
    )
    assert is_gate_eligible(label) is False


def test_compute_metrics_skips_aggregate_exclude_despite_ready_positives():
    intent = _sample_intent("kpi.retrieve_pipeline_backlog")
    gold = GoldLabel(
        intent_id=intent.intent_id,
        company_name="Elder Care",
        catalog="uc13_ale",
        gold_status="ready",
        positive_chunk_ids=["chunk-001"],
        gold_method="citation_backfill",
        ingestion_snapshot="uc13_ale:1:2026-08-11",
        confidence="high",
        aggregate_exclude=True,
        exclude_reason="no_citation_source",
    )
    route_result = SimpleNamespace(chunks=[SimpleNamespace(chunk_id="chunk-001")])
    result = compute_metrics(intent, gold, route_result)
    assert result.eval_status == "skipped_bootstrap_failed"


def test_bootstrap_exclusion_does_not_query_analysis_tables():
    spark = MockSpark()
    bootstrap = GoldLabelBootstrap(spark, ingestion_date=date(2026, 8, 11))
    bootstrap.bootstrap([_sample_intent("kpi.retrieve_healthcare_labor_market")])
    assert not any("analysis." in query for query in spark.queries)


def test_load_gold_exclusions_custom_path(tmp_path):
    payload = {
        "excluded": [
            {
                "intent_id": "profiler.company_size_indicators",
                "exclude_reason": "no_citation_source",
            }
        ]
    }
    path = tmp_path / "gold_exclusions.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    assert load_gold_exclusions(path) == {
        "profiler.company_size_indicators": "no_citation_source"
    }
