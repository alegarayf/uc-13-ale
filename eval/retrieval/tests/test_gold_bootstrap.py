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
GOLD_COUNTS_PATH = REPO_ROOT / "eval" / "retrieval" / "fixtures" / "gold_positive_counts.yaml"
INGESTION_SNAPSHOT = "uc13_ale:35104:2026-07-30"


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
        "COUNT(*) AS chunk_count": [{"chunk_count": 35104}],
        "analysis.financial_trends": [
            {
                "citations": (
                    '[{"document": "2024 Elder Care - CIM_vF.pdf", '
                    '"location": "p. 49 Historical P&L Summary"}]'
                ),
                "created_at": "2026-07-02T00:00:00Z",
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
                "created_at": "2026-07-02T00:00:00Z",
            }
        ],
        "Guided Living - Asset Purchase Agreement": [{"chunk_id": "chunk_legal001"}],
        "q3_projected_financials": [{"chunk_id": "chunk_proj001"}],
    }


def test_format_ingestion_snapshot_normative():
    assert (
        format_ingestion_snapshot("uc13_ale", 35104, date(2026, 7, 30))
        == INGESTION_SNAPSHOT
    )


def test_compute_ingestion_snapshot_single_value(mock_spark_handlers):
    spark = MockSpark(mock_spark_handlers)
    bootstrap = GoldLabelBootstrap(
        spark,
        ingestion_date=date(2026, 7, 30),
    )
    assert bootstrap.compute_ingestion_snapshot() == INGESTION_SNAPSHOT


def test_bootstrap_pass1_citation_backfill(mock_spark_handlers):
    spark = MockSpark(mock_spark_handlers)
    bootstrap = GoldLabelBootstrap(
        spark,
        ingestion_date=date(2026, 7, 30),
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
        ingestion_date=date(2026, 7, 30),
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
            "created_at": "2026-07-02T00:00:00Z",
        }
    ]
    handlers["p. 49"] = [{"chunk_id": "chunk_hist001"}]
    handlers["p. 52"] = [{"chunk_id": "chunk_proj001"}]
    spark = MockSpark(handlers)
    bootstrap = GoldLabelBootstrap(
        spark,
        ingestion_date=date(2026, 7, 30),
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
        ingestion_date=date(2026, 7, 30),
    )
    intent = _sample_intent(
        "profiler.industry_overlay",
        agent_id="profiler",
        workstream_filter=None,
    )
    label = bootstrap.bootstrap([intent])[0]
    assert label.gold_status == "bootstrap_failed"
    assert label.positive_chunk_ids == []
    assert label.ingestion_snapshot == "uc13_ale:1:2026-07-30"


def test_all_labels_share_single_ingestion_snapshot(mock_spark_handlers):
    spark = MockSpark(mock_spark_handlers)
    bootstrap = GoldLabelBootstrap(
        spark,
        ingestion_date=date(2026, 7, 30),
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


def test_committed_gold_positive_counts_match_manifest():
    """Pin per-intent positive counts and gold_method — update manifest on intentional rebootstrap."""
    assert GOLD_COUNTS_PATH.exists(), "gold_positive_counts.yaml manifest required"
    labels = load_gold_labels(GOLD_PATH)
    manifest = yaml.safe_load(GOLD_COUNTS_PATH.read_text(encoding="utf-8"))
    assert manifest["ingestion_snapshot"] == INGESTION_SNAPSHOT
    assert manifest["row_count"] == len(labels)
    actual_total = sum(len(label.positive_chunk_ids) for label in labels)
    assert manifest["total_positive_chunk_ids"] == actual_total
    for label in labels:
        expected = manifest["intents"][label.intent_id]
        assert expected["gold_status"] == label.gold_status
        assert expected["gold_method"] == label.gold_method
        assert expected["positive_count"] == len(label.positive_chunk_ids)


def test_committed_elder_care_yaml_matches_fixture_shape():
    labels = load_gold_labels(GOLD_PATH)
    opex_q3 = next(
        label for label in labels if label.intent_id == "fta.opex.q3_projected_financials"
    )
    assert opex_q3.gold_status == "ready"
    assert opex_q3.gold_method in {"citation_backfill", "section_range", "filename_closure"}
    assert opex_q3.positive_chunk_ids


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


def _fta_q1_q3_handlers(**extra: list[dict]) -> dict[str, list[dict]]:
    """Handlers for q1 zero-out scenarios with cross-intent sibling pair."""
    handlers: dict[str, list[dict]] = {
        "COUNT(*) AS chunk_count": [{"chunk_count": 35104}],
        "analysis.financial_trends": [
            {
                "citations": (
                    '[{"document": "2024 Elder Care - CIM_vF.pdf", '
                    '"location": "p. 49 Historical P&L Summary"}, '
                    '{"document": "2024 Elder Care - CIM_vF.pdf", '
                    '"location": "p. 52 Projected financials"}]'
                ),
                "created_at": "2026-07-02T00:00:00Z",
            }
        ],
        "p. 49": [{"chunk_id": "chunk_cite001"}],
        "p. 52": [{"chunk_id": "chunk_cite001"}],
        "section_header ILIKE '%Projection%'": [{"chunk_id": "chunk_basis_neg"}],
        "section_header ILIKE '%Tax Return%'": [{"chunk_id": "chunk_tax001"}],
    }
    handlers.update(extra)
    return handlers


def _assert_no_empty_ready_partial(labels: list[GoldLabel]) -> None:
    for label in labels:
        if label.gold_status in {"ready", "partial"}:
            assert label.positive_chunk_ids, (
                f"{label.intent_id} emitted {label.gold_status!r} with empty positives"
            )


def test_pass2_zero_out_reengages_section_range_fallback():
    handlers = _fta_q1_q3_handlers(
        **{
            "page_start BETWEEN 45 AND 50": [
                {"chunk_id": "chunk_sec001"},
                {"chunk_id": "chunk_sec002"},
            ],
        }
    )
    spark = MockSpark(handlers)
    bootstrap = GoldLabelBootstrap(spark, ingestion_date=date(2026, 7, 30))
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

    assert q1_label.gold_status == "ready"
    assert q1_label.gold_method == "section_range"
    assert q1_label.confidence == "high"
    assert set(q1_label.positive_chunk_ids) == {"chunk_sec001", "chunk_sec002"}
    assert "Pass 1 citation_backfill zeroed by pass-2 negatives" in (q1_label.notes or "")
    assert "fallback section_range engaged" in (q1_label.notes or "")
    negative_ids = set(q1_label.negative_chunk_ids or [])
    assert negative_ids.isdisjoint(q1_label.positive_chunk_ids)
    _assert_no_empty_ready_partial(list(labels.values()))


def test_pass2_zero_out_falls_through_to_filename_closure():
    handlers = _fta_q1_q3_handlers(
        **{
            "page_start BETWEEN 45 AND 50": [{"chunk_id": "chunk_cite001"}],
            "classification.doc_relevance": [{"chunk_id": "chunk_file001"}],
        }
    )
    spark = MockSpark(handlers)
    bootstrap = GoldLabelBootstrap(spark, ingestion_date=date(2026, 7, 30))
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
    q1_label = bootstrap.bootstrap([q1, q3])[0]

    assert q1_label.gold_status == "partial"
    assert q1_label.gold_method == "filename_closure"
    assert q1_label.confidence == "medium"
    assert q1_label.positive_chunk_ids == ["chunk_file001"]
    negative_ids = set(q1_label.negative_chunk_ids or [])
    assert "chunk_file001" not in negative_ids
    _assert_no_empty_ready_partial([q1_label])


def test_pass2_zero_out_fail_closed_when_no_fallback_survivors():
    handlers = _fta_q1_q3_handlers(
        **{
            "page_start BETWEEN 45 AND 50": [{"chunk_id": "chunk_cite001"}],
            "classification.doc_relevance": [{"chunk_id": "chunk_cite001"}],
        }
    )
    spark = MockSpark(handlers)
    bootstrap = GoldLabelBootstrap(spark, ingestion_date=date(2026, 7, 30))
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
    q1_label = bootstrap.bootstrap([q1, q3])[0]

    assert q1_label.gold_status == "bootstrap_failed"
    assert q1_label.positive_chunk_ids == []
    assert "Pass 2 zeroed all pass-1 citation_backfill positives" in (q1_label.notes or "")
    _assert_no_empty_ready_partial([q1_label])


def test_pass2_partial_strip_does_not_reengage_fallback():
    """Surviving pass-1 positives must not trigger pass-2 fallback re-engagement."""
    handlers = {
        "COUNT(*) AS chunk_count": [{"chunk_count": 35104}],
        "analysis.financial_trends": [
            {
                "citations": (
                    '[{"document": "2024 Elder Care - CIM_vF.pdf", '
                    '"location": "p. 49 Historical P&L Summary"}, '
                    '{"document": "2024 Elder Care - CIM_vF.pdf", '
                    '"location": "p. 50 EBITDA Adjustment"}]'
                ),
                "created_at": "2026-07-02T00:00:00Z",
            }
        ],
        "page_start = 49": [{"chunk_id": "chunk_a"}],
        "page_start = 50": [{"chunk_id": "chunk_b"}],
        "section_header ILIKE '%Projection%'": [{"chunk_id": "chunk_a"}],
        "section_header ILIKE '%Tax Return%'": [{"chunk_id": "chunk_tax001"}],
    }
    spark = MockSpark(handlers)
    bootstrap = GoldLabelBootstrap(spark, ingestion_date=date(2026, 7, 30))
    q1 = _sample_intent(
        "fta.opex.q1_financial_statements",
        agent_id="fta.opex",
        workstream_filter=["FINANCIAL"],
    )
    q1_label = bootstrap.bootstrap([q1])[0]

    assert q1_label.gold_status == "ready"
    assert q1_label.gold_method == "citation_backfill"
    assert q1_label.positive_chunk_ids == ["chunk_b"]
    assert q1_label.notes is None
    _assert_no_empty_ready_partial([q1_label])
