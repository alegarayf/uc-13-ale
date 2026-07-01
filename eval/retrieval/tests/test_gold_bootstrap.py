"""Tests for GoldLabelBootstrap — spec §5.12.2 with mocked Spark."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from eval.retrieval.errors import PreconditionError
from eval.retrieval.gold.bootstrap import (
    BASIS_NEGATIVE_SECTION_PATTERNS,
    GoldLabelBootstrap,
    format_ingestion_snapshot,
    load_gold_labels,
    load_registry,
    validate_ingestion_snapshot_consistency,
    write_gold_labels,
)
from eval.retrieval.models import GoldLabel, RetrievalIntent

REPO_ROOT = Path(__file__).resolve().parents[3]
REGISTRY_PATH = REPO_ROOT / "eval" / "retrieval" / "intent_registry.yaml"
GOLD_PATH = REPO_ROOT / "eval" / "retrieval" / "gold_labels" / "elder_care.yaml"
INGESTION_SNAPSHOT = "uc13_ale:35034:2026-06-25"


class MockSpark:
    """Query-keyed Spark stub for offline bootstrap tests."""

    def __init__(self, handlers: dict[str, list[dict]]) -> None:
        self.handlers = handlers
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


def _sample_intent(intent_id: str, **overrides) -> RetrievalIntent:
    base = {
        "intent_id": intent_id,
        "agent_id": intent_id.split(".")[0],
        "source_file": "databricks/agents/workstreams/example.py",
        "catalog": "uc13_ale",
        "query": "sample query",
        "top_k": 10,
        "invocation_path": "direct",
    }
    base.update(overrides)
    return RetrievalIntent.model_validate(base)


@pytest.fixture
def mock_spark_handlers() -> dict[str, list[dict]]:
    return {
        "COUNT(*) AS chunk_count": [{"chunk_count": 35034}],
        "analysis.financial_trends": [
            {
                "citations": (
                    '[{"document": "2024 Elder Care - CIM_vF.pdf", '
                    '"location": "p. 49 Historical P&L Summary"}]'
                ),
                "created_at": "2026-06-25T00:00:00Z",
            }
        ],
        "page_start = 49": [{"chunk_id": "chunk_abc123"}],
        "section_header ILIKE '%Projection%'": [{"chunk_id": "chunk_xyz789"}],
        "section_header ILIKE '%Tax Return%'": [{"chunk_id": "chunk_tax001"}],
        "page_start BETWEEN 45 AND 50": [{"chunk_id": "chunk_section001"}],
        "analysis.legal": [
            {
                "citations": (
                    '[{"document": "Guided Living - Asset Purchase Agreement.pdf", '
                    '"location": "Section 4 Representations"}]'
                ),
                "created_at": "2026-06-25T00:00:00Z",
            }
        ],
        "Guided Living - Asset Purchase Agreement": [{"chunk_id": "chunk_legal001"}],
        "q3_projected_financials": [{"chunk_id": "chunk_proj001"}],
    }


def test_format_ingestion_snapshot_normative():
    assert (
        format_ingestion_snapshot("uc13_ale", 35034, date(2026, 6, 25))
        == INGESTION_SNAPSHOT
    )


def test_compute_ingestion_snapshot_single_value(mock_spark_handlers):
    spark = MockSpark(mock_spark_handlers)
    bootstrap = GoldLabelBootstrap(
        spark,
        ingestion_date=date(2026, 6, 25),
    )
    assert bootstrap.compute_ingestion_snapshot() == INGESTION_SNAPSHOT


def test_bootstrap_pass1_citation_backfill(mock_spark_handlers):
    spark = MockSpark(mock_spark_handlers)
    bootstrap = GoldLabelBootstrap(
        spark,
        ingestion_date=date(2026, 6, 25),
    )
    intent = _sample_intent(
        "fta.opex.q1_financial_statements",
        agent_id="fta.opex",
        workstream_filter=["FINANCIAL"],
    )
    labels = bootstrap.bootstrap([intent])
    assert len(labels) == 1
    label = labels[0]
    assert label.gold_status == "ready"
    assert label.gold_method == "citation_backfill"
    assert "chunk_abc123" in label.positive_chunk_ids
    assert label.ingestion_snapshot == INGESTION_SNAPSHOT


def test_bootstrap_pass2_basis_rule(mock_spark_handlers):
    spark = MockSpark(mock_spark_handlers)
    bootstrap = GoldLabelBootstrap(
        spark,
        ingestion_date=date(2026, 6, 25),
    )
    intent = _sample_intent(
        "fta.opex.q1_financial_statements",
        agent_id="fta.opex",
        workstream_filter=["FINANCIAL"],
    )
    label = bootstrap.bootstrap([intent])[0]
    assert label.negative_method in {"basis_rule", "cross_intent_positive"}
    assert label.negative_chunk_ids
    assert "chunk_xyz789" in label.negative_chunk_ids


def test_bootstrap_pass2_cross_intent_positive(mock_spark_handlers):
    handlers = dict(mock_spark_handlers)
    handlers["analysis.financial_trends"] = [
        {
            "citations": (
                '[{"document": "2024 Elder Care - CIM_vF.pdf", '
                '"location": "p. 49 Historical P&L Summary"}, '
                '{"document": "2024 Elder Care - CIM_vF.pdf", '
                '"location": "p. 52 Projected financials"}]'
            ),
            "created_at": "2026-06-25T00:00:00Z",
        }
    ]
    handlers["p. 49"] = [{"chunk_id": "chunk_hist001"}]
    handlers["p. 52"] = [{"chunk_id": "chunk_proj001"}]
    spark = MockSpark(handlers)
    bootstrap = GoldLabelBootstrap(
        spark,
        ingestion_date=date(2026, 6, 25),
    )
    q1 = _sample_intent(
        "fta.opex.q1_financial_statements",
        agent_id="fta.opex",
        workstream_filter=["FINANCIAL"],
    )
    q3 = _sample_intent(
        "fta.opex.q3_projected_financials",
        agent_id="fta.opex",
        workstream_filter=["FINANCIAL"],
    )
    labels = {row.intent_id: row for row in bootstrap.bootstrap([q1, q3])}
    q1_label = labels["fta.opex.q1_financial_statements"]
    assert q1_label.negative_method == "cross_intent_positive"
    assert "chunk_proj001" in (q1_label.negative_chunk_ids or [])


def test_bootstrap_failed_when_no_positives(mock_spark_handlers):
    spark = MockSpark({"COUNT(*) AS chunk_count": [{"chunk_count": 1}]})
    bootstrap = GoldLabelBootstrap(
        spark,
        ingestion_date=date(2026, 6, 25),
    )
    intent = _sample_intent(
        "profiler.industry_overlay",
        agent_id="profiler",
        workstream_filter=None,
    )
    label = bootstrap.bootstrap([intent])[0]
    assert label.gold_status == "bootstrap_failed"
    assert label.positive_chunk_ids == []
    assert label.ingestion_snapshot == "uc13_ale:1:2026-06-25"


def test_all_labels_share_single_ingestion_snapshot(mock_spark_handlers):
    spark = MockSpark(mock_spark_handlers)
    bootstrap = GoldLabelBootstrap(
        spark,
        ingestion_date=date(2026, 6, 25),
    )
    intents = load_registry(REGISTRY_PATH)[:5]
    labels = bootstrap.bootstrap(intents)
    snapshots = {label.ingestion_snapshot for label in labels}
    assert len(snapshots) == 1
    assert None not in snapshots
    assert "" not in snapshots


def test_validate_ingestion_snapshot_consistency_rejects_multi_value():
    labels = [
        GoldLabel(
            intent_id="a",
            company_name="Elder Care",
            catalog="uc13_ale",
            gold_status="ready",
            positive_chunk_ids=["c1"],
            gold_method="manual_audit",
            ingestion_snapshot="uc13_ale:1:2026-06-25",
            confidence="high",
        ),
        GoldLabel(
            intent_id="b",
            company_name="Elder Care",
            catalog="uc13_ale",
            gold_status="ready",
            positive_chunk_ids=["c2"],
            gold_method="manual_audit",
            ingestion_snapshot="uc13_ale:2:2026-06-25",
            confidence="high",
        ),
    ]
    with pytest.raises(PreconditionError, match="disagree on ingestion_snapshot"):
        validate_ingestion_snapshot_consistency(labels)


def test_write_gold_labels_rejects_multi_snapshot(tmp_path):
    labels = [
        GoldLabel(
            intent_id="a",
            company_name="Elder Care",
            catalog="uc13_ale",
            gold_status="ready",
            positive_chunk_ids=["c1"],
            gold_method="manual_audit",
            ingestion_snapshot="uc13_ale:1:2026-06-25",
            confidence="high",
        ),
        GoldLabel(
            intent_id="b",
            company_name="Elder Care",
            catalog="uc13_ale",
            gold_status="ready",
            positive_chunk_ids=["c2"],
            gold_method="manual_audit",
            ingestion_snapshot="uc13_ale:2:2026-06-25",
            confidence="high",
        ),
    ]
    with pytest.raises(PreconditionError, match="multiple ingestion_snapshot"):
        write_gold_labels(tmp_path / "gold.yaml", labels)


def test_basis_negative_patterns_pinned_in_module():
    assert "%Projection%" in BASIS_NEGATIVE_SECTION_PATTERNS
    assert "%Pro Forma Income%" in BASIS_NEGATIVE_SECTION_PATTERNS


def test_committed_elder_care_yaml_validates_and_covers_registry():
    assert GOLD_PATH.exists(), "elder_care.yaml must be committed for T6"
    labels = load_gold_labels(GOLD_PATH)
    registry_ids = {intent.intent_id for intent in load_registry(REGISTRY_PATH)}
    label_ids = {label.intent_id for label in labels}
    assert label_ids == registry_ids
    snapshot = validate_ingestion_snapshot_consistency(labels)
    assert snapshot == INGESTION_SNAPSHOT
    for label in labels:
        GoldLabel.model_validate(label.model_dump(mode="json"))


def test_committed_elder_care_yaml_matches_fixture_shape():
    labels = load_gold_labels(GOLD_PATH)
    opex_q1 = next(
        label for label in labels if label.intent_id == "fta.opex.q1_financial_statements"
    )
    assert opex_q1.gold_status == "ready"
    assert opex_q1.gold_method in {"citation_backfill", "section_range"}
    assert opex_q1.positive_chunk_ids
    assert opex_q1.negative_chunk_ids
    assert opex_q1.negative_method in {"basis_rule", "cross_intent_positive", "section_rule"}


def test_generate_skeleton_gold_yaml_from_registry(tmp_path):
    """Offline skeleton writer used to seed committed elder_care.yaml."""
    intents = load_registry(REGISTRY_PATH)
    labels = [
        GoldLabel(
            intent_id=intent.intent_id,
            company_name="Elder Care",
            catalog="uc13_ale",
            gold_status="bootstrap_failed",
            positive_chunk_ids=[],
            gold_method="citation_backfill",
            ingestion_snapshot=INGESTION_SNAPSHOT,
            confidence="low",
            notes="Awaiting cluster bootstrap after Cell 7",
        )
        for intent in intents
    ]
    labels[labels.index(next(l for l in labels if l.intent_id == "fta.opex.q1_financial_statements"))] = GoldLabel(
        intent_id="fta.opex.q1_financial_statements",
        company_name="Elder Care",
        catalog="uc13_ale",
        gold_status="ready",
        positive_chunk_ids=["chunk_abc123", "chunk_abc124"],
        negative_chunk_ids=["chunk_xyz789"],
        negative_method="basis_rule",
        negative_rule=(
            "section_header ILIKE '%Projection%' OR '%Pro Forma Income%' on CIM"
        ),
        gold_method="section_range",
        ingestion_snapshot=INGESTION_SNAPSHOT,
        confidence="high",
        negative_confidence="medium",
    )
    out = tmp_path / "elder_care.yaml"
    write_gold_labels(out, labels)
    loaded = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert len(loaded) == len(intents)
    assert all(row["ingestion_snapshot"] == INGESTION_SNAPSHOT for row in loaded)
