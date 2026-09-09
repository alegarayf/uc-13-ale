"""Citation-backfill destack — CQA/BMA/FTA claim filter (cycle-8 P1)."""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import pytest

from eval.retrieval.gold.bootstrap import (
    CITATION_CLAIM_INTENT_MAP_PATH,
    DESTACK_INTENT_IDS,
    DESTACK_MAX_CHUNKS_PER_REF,
    GoldLabelBootstrap,
    destack_intents_for_claim,
    destack_location_patterns,
    filter_citation_refs_for_intent,
    load_citation_claim_intent_map,
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
        "agent_id": intent_id.split(".")[0] if not intent_id.startswith("fta.") else ".".join(intent_id.split(".")[:2]),
        "source_file": "databricks/agents/workstreams/example.py",
        "catalog": "uc13_ale",
        "query": "sample query",
        "top_k": 10,
        "invocation_path": "direct",
        "workstream_filter": ["CUSTOMER"],
    }
    base.update(overrides)
    return RetrievalIntent.model_validate(base)


def _citations_json(entries: list[tuple[str, str, str | None]]) -> str:
    payload = [
        {
            "document": document,
            "location": location,
            **({"claim": claim} if claim is not None else {}),
        }
        for document, location, claim in entries
    ]
    return json.dumps(payload)


def test_load_citation_claim_intent_map_totality():
    prefix_map, intent_block = load_citation_claim_intent_map()
    assert CITATION_CLAIM_INTENT_MAP_PATH.is_file()
    assert set(intent_block) == DESTACK_INTENT_IDS
    mapped = {intent for targets in prefix_map.values() for intent in targets}
    assert mapped <= DESTACK_INTENT_IDS
    assert destack_intents_for_claim(
        "top_customers — rank 1 revenue_dollars", prefix_map
    ) == frozenset({"cqa.retrieve_customer_concentration"})
    assert destack_intents_for_claim(
        "average_account_size — computation_note", prefix_map
    ) == frozenset({"cqa.retrieve_account_size"})
    assert destack_intents_for_claim(
        "customer_profile.geographic_concentration", prefix_map
    ) == frozenset({"bma.retrieve_revenue_by_location_and_metrics"})
    assert destack_intents_for_claim(
        "revenue_visibility.renewal_cadence_note", prefix_map
    ) == frozenset({"bma.retrieve_revenue_visibility"})
    assert destack_intents_for_claim("revenue_by_segment_json[0]", prefix_map) == (
        frozenset({"fta.revenue.q2_revenue_by_segment"})
    )


def test_filter_drops_other_intent_claims():
    prefix_map, _intent_block = load_citation_claim_intent_map()
    refs = [
        ("billing.xlsx", "sheet1", "top_customers — rank 1"),
        ("projection.xlsx", "Revenue Build", "average_account_size — note"),
        ("legacy.pdf", "p. 1", None),
    ]
    concentration = filter_citation_refs_for_intent(
        refs, "cqa.retrieve_customer_concentration", prefix_map
    )
    account_size = filter_citation_refs_for_intent(
        refs, "cqa.retrieve_account_size", prefix_map
    )
    assert [row[0] for row in concentration] == ["billing.xlsx", "legacy.pdf"]
    assert [row[0] for row in account_size] == ["projection.xlsx", "legacy.pdf"]


def _cqa_handlers() -> dict[str, list[dict]]:
    return {
        "COUNT(*) AS chunk_count": [{"chunk_count": 100}],
        "analysis.customer_quality": [
            {
                "citations": _citations_json(
                    [
                        (
                            "Revenue 36 months Billing Amount Summary.xlsx",
                            "sheet1 Summary",
                            "top_customers — rank 1 revenue_dollars",
                        ),
                        (
                            "Elder Care Projection Model_vUPLOAD.xlsx",
                            "Revenue Build",
                            "average_account_size — computation_note",
                        ),
                        (
                            "Elder Care Performance Detail_12.31.24_vF.xlsx",
                            "Performance Detail",
                            "customer_tenure — tenure_distribution_note",
                        ),
                    ]
                ),
                "created_at": "2026-09-01T00:00:00Z",
            }
        ],
        "Billing Amount Summary": [{"chunk_id": "cqa_conc_1"}],
        "Projection Model": [{"chunk_id": "cqa_acct_1"}],
        "Performance Detail": [{"chunk_id": "cqa_tenure_1"}],
    }


def test_cqa_citation_destack_splits_cloned_bag():
    """Named regression: nine CQA intents must not share one billing-xlsx bag."""
    spark = MockSpark(_cqa_handlers())
    bootstrap = GoldLabelBootstrap(
        spark, company_name="Elder Care", ingestion_date=date(2026, 9, 9)
    )
    intents = [
        _sample_intent("cqa.retrieve_customer_concentration"),
        _sample_intent("cqa.retrieve_account_size"),
        _sample_intent("cqa.retrieve_customer_tenure"),
    ]
    labels = {row.intent_id: row for row in bootstrap.bootstrap(intents)}
    conc = labels["cqa.retrieve_customer_concentration"]
    acct = labels["cqa.retrieve_account_size"]
    tenure = labels["cqa.retrieve_customer_tenure"]
    assert conc.gold_method == "citation_backfill"
    assert acct.gold_method == "citation_backfill"
    assert tenure.gold_method == "citation_backfill"
    assert conc.positive_chunk_ids == ["cqa_conc_1"]
    assert acct.positive_chunk_ids == ["cqa_acct_1"]
    assert tenure.positive_chunk_ids == ["cqa_tenure_1"]
    assert conc.positive_chunk_ids != acct.positive_chunk_ids
    assert acct.positive_chunk_ids != tenure.positive_chunk_ids


def test_bma_citation_destack_splits_shared_cim_bag():
    handlers = {
        "COUNT(*) AS chunk_count": [{"chunk_count": 100}],
        "analysis.business_model": [
            {
                "citations": _citations_json(
                    [
                        (
                            "Project Ajax CIM vF.pdf",
                            "MANAGEMENT EXPERIENCE AND CREDENTIALS",
                            "people_and_org.key_executives",
                        ),
                        (
                            "Project Ajax CIM vF.pdf",
                            "LEAD TO CONVERSION STRATEGY",
                            "sales_motion.process_note",
                        ),
                    ]
                ),
                "created_at": "2026-09-01T00:00:00Z",
            }
        ],
        "MANAGEMENT EXPERIENCE": [{"chunk_id": "bma_people_1"}],
        "LEAD TO CONVERSION": [{"chunk_id": "bma_sales_1"}],
    }
    spark = MockSpark(handlers)
    bootstrap = GoldLabelBootstrap(
        spark, company_name="GKF", ingestion_date=date(2026, 9, 9)
    )
    people = _sample_intent(
        "bma.retrieve_people_and_org",
        agent_id="bma",
        workstream_filter=["BUSINESS_MODEL"],
    )
    sales = _sample_intent(
        "bma.retrieve_sales_and_customers",
        agent_id="bma",
        workstream_filter=["BUSINESS_MODEL"],
    )
    labels = {row.intent_id: row for row in bootstrap.bootstrap([people, sales])}
    assert labels["bma.retrieve_people_and_org"].positive_chunk_ids == ["bma_people_1"]
    assert labels["bma.retrieve_sales_and_customers"].positive_chunk_ids == [
        "bma_sales_1"
    ]


def test_fta_json_column_destack_splits_shared_two_id_bag():
    handlers = {
        "COUNT(*) AS chunk_count": [{"chunk_count": 100}],
        "analysis.financial_trends": [
            {
                "citations": "[]",
                "revenue_by_segment_json": json.dumps(
                    [
                        {
                            "source_doc": "Project Ajax Databook.xlsx",
                            "source_location": "Location Analysis",
                        }
                    ]
                ),
                "addback_schedule_json": json.dumps(
                    [
                        {
                            "source_doc": "Project Ajax CIM vF.pdf",
                            "source_location": "EBITDA ADJUSTMENTS",
                        }
                    ]
                ),
                "created_at": "2026-09-01T00:00:00Z",
            }
        ],
        "Databook": [{"chunk_id": "fta_seg_1"}],
        "EBITDA ADJUSTMENTS": [{"chunk_id": "fta_addback_1"}],
    }
    spark = MockSpark(handlers)
    bootstrap = GoldLabelBootstrap(
        spark, company_name="GKF", ingestion_date=date(2026, 9, 9)
    )
    segment = _sample_intent(
        "fta.revenue.q2_revenue_by_segment",
        agent_id="fta.revenue",
        workstream_filter=["FINANCIAL"],
    )
    addback = _sample_intent(
        "fta.ebitda.q4_addback_schedule",
        agent_id="fta.ebitda",
        workstream_filter=["FINANCIAL"],
    )
    labels = {row.intent_id: row for row in bootstrap.bootstrap([segment, addback])}
    assert labels["fta.revenue.q2_revenue_by_segment"].positive_chunk_ids == [
        "fta_seg_1"
    ]
    assert labels["fta.ebitda.q4_addback_schedule"].positive_chunk_ids == [
        "fta_addback_1"
    ]


def test_destack_location_patterns_prefer_full_then_head():
    patterns = destack_location_patterns("Revenue Build — Summary")
    assert patterns[0] == "%Revenue Build — Summary%"
    assert "%Revenue Build%" in patterns
    contract = destack_location_patterns(
        "Section 8. TERM AND TERMINATION, Section 8.3"
    )
    assert any("TERM AND TERMINATION" in item for item in contract)


def test_destack_drops_oversized_file_wide_match():
    handlers = {
        "COUNT(*) AS chunk_count": [{"chunk_count": 100}],
        "analysis.customer_quality": [
            {
                "citations": _citations_json(
                    [
                        (
                            "Elder Care Performance Detail_12.31.24_vF.xlsx",
                            "Performance Detail — Data Rows 5701-5750",
                            "customer_tenure — tenure_distribution_note",
                        )
                    ]
                ),
                "created_at": "2026-09-01T00:00:00Z",
            }
        ],
        "Performance Detail": [
            {"chunk_id": f"wide_{index}"} for index in range(DESTACK_MAX_CHUNKS_PER_REF + 5)
        ],
    }
    spark = MockSpark(handlers)
    bootstrap = GoldLabelBootstrap(
        spark, company_name="Elder Care", ingestion_date=date(2026, 9, 9)
    )
    label = bootstrap.bootstrap([_sample_intent("cqa.retrieve_customer_tenure")])[0]
    assert label.positive_chunk_ids == []
    assert label.gold_status == "bootstrap_failed"


def test_claimless_fta_citation_array_stays_shared_for_legacy_fixtures():
    handlers = {
        "COUNT(*) AS chunk_count": [{"chunk_count": 100}],
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
    spark = MockSpark(handlers)
    bootstrap = GoldLabelBootstrap(spark, ingestion_date=date(2026, 8, 11))
    intent = _sample_intent(
        "fta.opex.q1_financial_statements",
        agent_id="fta.opex",
        workstream_filter=["FINANCIAL"],
    )
    label = bootstrap.bootstrap([intent])[0]
    assert label.gold_method == "citation_backfill"
    assert "chunk_abc123" in label.positive_chunk_ids
