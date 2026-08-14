"""Tests for GoldLabel aggregate exclusion machinery — Contract T3-a/b/c, T13."""

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
    load_gold_labels,
    load_kpi_claim_intent_map,
    write_gold_labels,
)
from eval.retrieval.harness import compute_metrics, default_gold_path
from eval.retrieval.models import EXCLUDE_REASON_VOCABULARY, GoldLabel, RetrievalIntent
from eval.retrieval.scope_resolver import is_gate_eligible

REPO_ROOT = Path(__file__).resolve().parents[3]
GOLD_EXCLUSIONS_PATH = (
    REPO_ROOT / "eval" / "retrieval" / "gold" / "gold_exclusions.yaml"
)
KPI_MAP_PATH = REPO_ROOT / "eval" / "retrieval" / "gold" / "kpi_claim_intent_map.yaml"
ELDER_CARE_GOLD_PATH = default_gold_path("elder_care")
CLEARSULTING_GOLD_PATH = default_gold_path("clearsulting")

ELDER_CARE_LAUNCH_EXCLUDED_KPI = frozenset(
    {
        "kpi.retrieve_healthcare_labor_market",
        "kpi.retrieve_bill_rates_and_margins",
        "kpi.retrieve_headcount_attrition",
        "kpi.retrieve_pipeline_backlog",
    }
)
BENCH_AND_CAPACITY = "kpi.retrieve_bench_and_capacity"
RESTORED_NO_CITATION_KPI = frozenset(
    {
        "kpi.retrieve_bill_rates_and_margins",
        "kpi.retrieve_headcount_attrition",
        "kpi.retrieve_pipeline_backlog",
    }
)


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


def _claim_resolved_kpi_for_company(gold_path: Path) -> set[str]:
    """KPI intents this company's committed gold treats as claim-resolved (not excluded)."""
    labels = load_gold_labels(gold_path)
    return {
        label.intent_id
        for label in labels
        if label.intent_id.startswith("kpi.")
        and not label.aggregate_exclude
        and label.gold_status in {"ready", "partial"}
    }


def _assert_per_company_exclusion_invariant(
    *,
    exclusions_path: Path,
    company_slug: str,
    gold_path: Path,
    launch_excluded_kpi: frozenset[str] | None = None,
) -> None:
    exclusions = load_gold_exclusions(exclusions_path, company_slug=company_slug)
    excluded_kpi = {
        intent_id for intent_id in exclusions if intent_id.startswith("kpi.")
    }
    claim_resolved = _claim_resolved_kpi_for_company(gold_path)
    assert excluded_kpi.isdisjoint(claim_resolved), (
        f"{company_slug}: excluded KPI intents overlap claim-resolved gold rows: "
        f"{sorted(excluded_kpi & claim_resolved)}"
    )
    if launch_excluded_kpi is not None:
        _, intent_block = load_kpi_claim_intent_map(KPI_MAP_PATH)
        unmappable_kpi = {
            intent_id
            for intent_id, meta in intent_block.items()
            if isinstance(meta, dict) and meta.get("role") == "unmappable"
        }
        assert excluded_kpi == launch_excluded_kpi
        assert "kpi.retrieve_healthcare_labor_market" in excluded_kpi
        assert unmappable_kpi <= {BENCH_AND_CAPACITY, "kpi.retrieve_healthcare_labor_market"}
        assert "kpi.retrieve_healthcare_labor_market" in unmappable_kpi


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


def test_load_gold_exclusions_requires_company_slug():
    with pytest.raises(TypeError):
        load_gold_exclusions(GOLD_EXCLUSIONS_PATH)  # type: ignore[call-arg]


def test_unknown_company_returns_empty_exclusions():
    assert load_gold_exclusions(GOLD_EXCLUSIONS_PATH, company_slug="acme_corp") == {}


def test_committed_exclusions_artifact_validates():
    payload = yaml.safe_load(GOLD_EXCLUSIONS_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload.get("companies"), dict)
    elder = load_gold_exclusions(GOLD_EXCLUSIONS_PATH, company_slug="elder_care")
    assert len(elder) == 5
    assert all(reason == "no_citation_source" for reason in elder.values())
    assert load_gold_exclusions(GOLD_EXCLUSIONS_PATH, company_slug="clearsulting") == {}


def test_elder_care_exclusion_population_is_five_intents():
    exclusions = load_gold_exclusions(GOLD_EXCLUSIONS_PATH, company_slug="elder_care")
    assert len(exclusions) == 5
    assert "profiler.company_size_indicators" in exclusions
    assert RESTORED_NO_CITATION_KPI <= set(exclusions)


def test_exclusions_are_company_scoped_and_do_not_leak_across_companies():
    elder = load_gold_exclusions(GOLD_EXCLUSIONS_PATH, company_slug="elder_care")
    pilot = load_gold_exclusions(GOLD_EXCLUSIONS_PATH, company_slug="clearsulting")
    assert len(elder) == 5
    assert pilot == {}
    assert "kpi.retrieve_bill_rates_and_margins" in elder
    assert "kpi.retrieve_bill_rates_and_margins" not in pilot


def test_gold_exclusions_totality_and_disjointness():
    _assert_per_company_exclusion_invariant(
        exclusions_path=GOLD_EXCLUSIONS_PATH,
        company_slug="elder_care",
        gold_path=ELDER_CARE_GOLD_PATH,
        launch_excluded_kpi=ELDER_CARE_LAUNCH_EXCLUDED_KPI,
    )
    _assert_per_company_exclusion_invariant(
        exclusions_path=GOLD_EXCLUSIONS_PATH,
        company_slug="clearsulting",
        gold_path=CLEARSULTING_GOLD_PATH,
    )
    claim_map, intent_block = load_kpi_claim_intent_map(KPI_MAP_PATH)
    claim_mapped = set(claim_map.values())
    elder_excluded_kpi = {
        intent_id
        for intent_id in load_gold_exclusions(
            GOLD_EXCLUSIONS_PATH, company_slug="elder_care"
        )
        if intent_id.startswith("kpi.")
    }
    assert BENCH_AND_CAPACITY in claim_mapped
    assert BENCH_AND_CAPACITY in intent_block
    assert not elder_excluded_kpi.isdisjoint(claim_mapped)


def test_per_company_invariant_fails_on_within_company_contradiction(tmp_path):
    payload = {
        "companies": {
            "elder_care": {
                "excluded": [
                    {
                        "intent_id": "kpi.retrieve_healthcare_ops",
                        "exclude_reason": "no_citation_source",
                    }
                ]
            }
        }
    }
    path = tmp_path / "gold_exclusions.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(AssertionError, match="overlap claim-resolved"):
        _assert_per_company_exclusion_invariant(
            exclusions_path=path,
            company_slug="elder_care",
            gold_path=ELDER_CARE_GOLD_PATH,
        )


def test_clearsulting_claim_targets_do_not_shrink_elder_care_exclusions():
    elder = load_gold_exclusions(GOLD_EXCLUSIONS_PATH, company_slug="elder_care")
    assert RESTORED_NO_CITATION_KPI <= set(elder)
    claim_map, _ = load_kpi_claim_intent_map(KPI_MAP_PATH)
    for intent_id in RESTORED_NO_CITATION_KPI:
        assert intent_id in set(claim_map.values())


def test_restored_elder_care_rows_still_skip_metrics():
    labels = {
        row.intent_id: row
        for row in load_gold_labels(ELDER_CARE_GOLD_PATH)
        if row.intent_id in RESTORED_NO_CITATION_KPI
    }
    for intent_id in RESTORED_NO_CITATION_KPI:
        label = labels[intent_id]
        assert label.aggregate_exclude is True
        assert label.exclude_reason == "no_citation_source"
        assert label.gold_status == "bootstrap_failed"
        assert label.positive_chunk_ids == []
        result = compute_metrics(_sample_intent(intent_id), label, SimpleNamespace(chunks=[]))
        assert result.eval_status == "skipped_bootstrap_failed"


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
        "companies": {
            "elder_care": {
                "excluded": [
                    {
                        "intent_id": "profiler.company_size_indicators",
                        "exclude_reason": "no_citation_source",
                    }
                ]
            }
        }
    }
    path = tmp_path / "gold_exclusions.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    assert load_gold_exclusions(path, company_slug="elder_care") == {
        "profiler.company_size_indicators": "no_citation_source"
    }
