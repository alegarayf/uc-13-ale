"""Hermetic tests for KPI Excel citation branch — Contract T2-a/b/c."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from eval.retrieval.errors import PreconditionError
from eval.retrieval.gold.bootstrap import (
    GoldLabelBootstrap,
    KPI_CLAIM_INTENT_MAP_PATH,
    KPI_ITEM12_INTENT_IDS,
    _excel_tab_candidate_from_location,
    _excel_tab_from_data_rows_location,
    _is_excel_shaped_location,
    _tabs_matching_excel_candidate,
    load_kpi_claim_intent_map,
)
from eval.retrieval.models import RetrievalIntent


class MockSpark:
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
        "source_file": "databricks/agents/workstreams/kpi_agent.py",
        "catalog": "uc13_ale",
        "query": "sample query",
        "top_k": 10,
        "invocation_path": "direct",
    }
    base.update(overrides)
    return RetrievalIntent.model_validate(base)


def _kpi_citations_json(
    entries: list[tuple[str, str, str | None]],
) -> str:
    import json

    payload = [
        {"document": doc, "location": loc, **({"claim": claim} if claim else {})}
        for doc, loc, claim in entries
    ]
    return json.dumps(payload)


@pytest.fixture
def kpi_spark_handlers() -> dict[str, list[dict]]:
    return {
        "COUNT(*) AS chunk_count": [{"chunk_count": 55812}],
        "analysis.kpi": [
            {
                "citations": _kpi_citations_json(
                    [
                        (
                            "Company KPI Dashboard SAMPLE.xlsx",
                            "Sheet: 2025 Company KPIs, Data Rows 1–50",
                            "healthcare_kpis.census_or_patient_panel",
                        ),
                        (
                            "Elder Care Projection Model Refresh_vF.xlsx",
                            "Sheet: Revenue Build, Summary",
                            "healthcare_kpis.revenue_per_hour_dollars",
                        ),
                    ]
                ),
                "created_at": "2026-07-28T00:00:00Z",
            }
        ],
        "SELECT DISTINCT c.tab": [
            {"tab": "Revenue Build"},
            {"tab": "Summary P&L"},
        ],
        "c.tab = '2025 Company KPIs'": [{"chunk_id": "ops_chunk_1"}],
        "c.tab = 'Revenue Build'": [{"chunk_id": "rev_chunk_1"}],
    }


def test_load_kpi_claim_intent_map_totality():
    claim_map, intent_block = load_kpi_claim_intent_map()
    assert set(intent_block) == KPI_ITEM12_INTENT_IDS
    assert set(claim_map.values()) <= KPI_ITEM12_INTENT_IDS
    assert claim_map["healthcare_kpis.census_or_patient_panel"] == (
        "kpi.retrieve_healthcare_ops"
    )
    assert claim_map["healthcare_kpis.revenue_per_hour_dollars"] == (
        "kpi.retrieve_healthcare_revenue_per_unit"
    )
    assert claim_map["bill_rates_by_role — North America Rank 05"] == (
        "kpi.retrieve_bill_rates_and_margins"
    )


def test_excel_location_form_i_exact_tab():
    loc = "Sheet: 2025 Company KPIs, Data Rows 1–50"
    assert _is_excel_shaped_location(loc)
    assert _excel_tab_from_data_rows_location(loc) == "2025 Company KPIs"


def test_excel_location_form_ii_candidate_segment():
    loc = "Sheet: Revenue Build, Summary — Revenue per Client Served"
    assert _excel_tab_from_data_rows_location(loc) is None
    assert _excel_tab_candidate_from_location(loc) == "Revenue Build"


def test_prefix_resolution_unique_tab():
    matches = _tabs_matching_excel_candidate(
        ["Revenue Build", "Summary P&L"],
        "Revenue Build",
    )
    assert matches == ["Revenue Build"]


def test_prefix_resolution_ambiguous_raises():
    matches = _tabs_matching_excel_candidate(
        ["Revenue Build", "Revenue Build Summary"],
        "Revenue Build",
    )
    assert len(matches) >= 2


def test_kpi_excel_branch_resolves_both_location_forms(kpi_spark_handlers):
    spark = MockSpark(kpi_spark_handlers)
    bootstrap = GoldLabelBootstrap(spark, ingestion_date=date(2026, 8, 11))

    ops_intent = _sample_intent("kpi.retrieve_healthcare_ops", agent_id="kpi")
    ops_label = bootstrap.bootstrap([ops_intent])[0]
    assert ops_label.gold_method == "citation_backfill"
    assert ops_label.positive_chunk_ids == ["ops_chunk_1"]
    assert ops_label.notes and "excel_branch" in ops_label.notes

    rev_intent = _sample_intent(
        "kpi.retrieve_healthcare_revenue_per_unit",
        agent_id="kpi",
    )
    rev_label = bootstrap.bootstrap([rev_intent])[0]
    assert rev_label.positive_chunk_ids == ["rev_chunk_1"]


def test_unmapped_claim_raises(kpi_spark_handlers):
    handlers = dict(kpi_spark_handlers)
    handlers["analysis.kpi"] = [
        {
            "citations": _kpi_citations_json(
                [
                    (
                        "Company KPI Dashboard SAMPLE.xlsx",
                        "Sheet: 2025 Company KPIs, Data Rows 1–50",
                        "healthcare_kpis.unknown_claim_key",
                    ),
                ]
            ),
            "created_at": "2026-07-28T00:00:00:00Z",
        }
    ]
    spark = MockSpark(handlers)
    bootstrap = GoldLabelBootstrap(spark, ingestion_date=date(2026, 8, 11))
    intent = _sample_intent("kpi.retrieve_healthcare_ops", agent_id="kpi")
    with pytest.raises(PreconditionError, match="Unmapped KPI claim"):
        bootstrap.bootstrap([intent])


def test_missing_claim_raises(kpi_spark_handlers):
    handlers = dict(kpi_spark_handlers)
    handlers["analysis.kpi"] = [
        {
            "citations": _kpi_citations_json(
                [
                    (
                        "Company KPI Dashboard SAMPLE.xlsx",
                        "Sheet: 2025 Company KPIs, Data Rows 1–50",
                        None,
                    ),
                ]
            ),
            "created_at": "2026-07-28T00:00:00:00Z",
        }
    ]
    spark = MockSpark(handlers)
    bootstrap = GoldLabelBootstrap(spark, ingestion_date=date(2026, 8, 11))
    intent = _sample_intent("kpi.retrieve_healthcare_ops", agent_id="kpi")
    with pytest.raises(PreconditionError, match="missing claim"):
        bootstrap.bootstrap([intent])


def test_zero_tab_match_raises(kpi_spark_handlers):
    handlers = dict(kpi_spark_handlers)
    handlers["SELECT DISTINCT c.tab"] = [{"tab": "Summary P&L"}]
    spark = MockSpark(handlers)
    bootstrap = GoldLabelBootstrap(spark, ingestion_date=date(2026, 8, 11))
    intent = _sample_intent(
        "kpi.retrieve_healthcare_revenue_per_unit",
        agent_id="kpi",
    )
    with pytest.raises(PreconditionError, match="zero candidates"):
        bootstrap.bootstrap([intent])


def test_ambiguous_tab_match_raises(kpi_spark_handlers):
    handlers = dict(kpi_spark_handlers)
    handlers["SELECT DISTINCT c.tab"] = [
        {"tab": "Revenue Build"},
        {"tab": "Revenue Build Summary"},
    ]
    spark = MockSpark(handlers)
    bootstrap = GoldLabelBootstrap(spark, ingestion_date=date(2026, 8, 11))
    intent = _sample_intent(
        "kpi.retrieve_healthcare_revenue_per_unit",
        agent_id="kpi",
    )
    with pytest.raises(PreconditionError, match="ambiguous"):
        bootstrap.bootstrap([intent])


def test_zero_resolved_chunks_raises(kpi_spark_handlers):
    handlers = dict(kpi_spark_handlers)
    handlers["c.tab = '2025 Company KPIs'"] = []
    spark = MockSpark(handlers)
    bootstrap = GoldLabelBootstrap(spark, ingestion_date=date(2026, 8, 11))
    intent = _sample_intent("kpi.retrieve_healthcare_ops", agent_id="kpi")
    with pytest.raises(PreconditionError, match="Zero chunks"):
        bootstrap.bootstrap([intent])


def test_non_kpi_agent_citation_path_unchanged():
    spark = MockSpark(
        {
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
        }
    )
    bootstrap = GoldLabelBootstrap(spark, ingestion_date=date(2026, 7, 30))
    intent = RetrievalIntent.model_validate(
        {
            "intent_id": "fta.opex.q1_financial_statements",
            "agent_id": "fta.opex",
            "source_file": "databricks/agents/workstreams/example.py",
            "catalog": "uc13_ale",
            "query": "sample query",
            "top_k": 10,
            "invocation_path": "direct",
            "workstream_filter": ["FINANCIAL"],
        }
    )
    label = bootstrap.bootstrap([intent])[0]
    assert label.gold_status == "ready"
    assert label.gold_method == "citation_backfill"
    assert label.positive_chunk_ids == ["chunk_abc123"]
    assert label.notes is None


def test_mapping_artifact_path_is_tracked():
    assert KPI_CLAIM_INTENT_MAP_PATH.is_file()
