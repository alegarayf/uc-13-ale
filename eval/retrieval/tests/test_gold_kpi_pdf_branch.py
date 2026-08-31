"""Hermetic tests for KPI PDF citation branch — Contract T10-bis."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from eval.retrieval.gold.bootstrap import (
    GoldLabelBootstrap,
    _normalize_kpi_pdf_location,
)
from eval.retrieval.models import RetrievalIntent
from eval.retrieval.tests.test_gold_excel_branch import (
    MockDataFrame,
    MockSpark,
    _kpi_citations_json,
    _sample_intent,
)


def test_normalize_kpi_pdf_location_strips_section_prefix_and_page_suffix():
    loc = "Section: Gross margin trending - recast, Page 29"
    assert _normalize_kpi_pdf_location(loc) == "Gross margin trending - recast"


def test_kpi_pdf_branch_resolves_section_location():
    spark = MockSpark(
        {
            "COUNT(*) AS chunk_count": [{"chunk_count": 12000}],
            "analysis.kpi": [
                {
                    "citations": _kpi_citations_json(
                        [
                            (
                                "Clearsulting Diligence Report_vF.pdf",
                                "Section: Gross margin trending - recast, Page 29",
                                "gross_margin_by_segment — Overall Recast Historical",
                            ),
                        ]
                    ),
                    "created_at": "2026-07-28T00:00:00Z",
                }
            ],
            "page_start = 29": [{"chunk_id": "gm_chunk_1"}, {"chunk_id": "gm_chunk_2"}],
            "section_header ILIKE '%Gross margin trending - recast%'": [
                {"chunk_id": "gm_chunk_1"},
                {"chunk_id": "gm_chunk_2"},
            ],
        }
    )
    bootstrap = GoldLabelBootstrap(
        spark, ingestion_date=date(2026, 8, 11), company_name="Clearsulting"
    )
    intent = _sample_intent("kpi.retrieve_bill_rates_and_margins", agent_id="kpi")
    label = bootstrap.bootstrap([intent])[0]
    assert label.gold_status == "ready"
    assert label.gold_method == "citation_backfill"
    assert label.positive_chunk_ids == ["gm_chunk_1", "gm_chunk_2"]
    assert label.notes is not None
    assert "pdf_branch" in label.notes
    assert "gross_margin_by_segment — Overall Recast Historical" in label.notes


def test_kpi_pdf_branch_zero_chunks_skips_without_raising():
    spark = MockSpark(
        {
            "COUNT(*) AS chunk_count": [{"chunk_count": 12000}],
            "analysis.kpi": [
                {
                    "citations": _kpi_citations_json(
                        [
                            (
                                "Clearsulting Diligence Report_vF.pdf",
                                "Section: Nonexistent section header, Page 14",
                                "gross_margin_by_segment — Treasury Practice 2025E",
                            ),
                            (
                                "Clearsulting Diligence Report_vF.pdf",
                                "Section: Gross margin trending - recast, Page 29",
                                "gross_margin_by_segment — Overall Recast Historical",
                            ),
                        ]
                    ),
                    "created_at": "2026-07-28T00:00:00Z",
                }
            ],
            "page_start = 29": [{"chunk_id": "gm_chunk_1"}],
            "section_header ILIKE '%Gross margin trending - recast%'": [
                {"chunk_id": "gm_chunk_1"},
            ],
        }
    )
    bootstrap = GoldLabelBootstrap(
        spark, ingestion_date=date(2026, 8, 11), company_name="Clearsulting"
    )
    intent = _sample_intent("kpi.retrieve_bill_rates_and_margins", agent_id="kpi")
    label = bootstrap.bootstrap([intent])[0]
    assert label.positive_chunk_ids == ["gm_chunk_1"]
    assert label.notes is not None
    assert "pdf_branch_unresolved" in label.notes
    assert "gross_margin_by_segment — Treasury Practice 2025E" in label.notes
    assert "Nonexistent section header" in label.notes


def test_kpi_pdf_branch_intent_degrades_to_bootstrap_failed_when_no_citation_resolves():
    spark = MockSpark(
        {
            "COUNT(*) AS chunk_count": [{"chunk_count": 12000}],
            "analysis.kpi": [
                {
                    "citations": _kpi_citations_json(
                        [
                            (
                                "Clearsulting Diligence Report_vF.pdf",
                                "Section: Other EBITDA considerations, Page 14",
                                "bench_note",
                            ),
                            (
                                "Clearsulting Diligence Report_vF.pdf",
                                "Section: Other EBITDA considerations, Page 25",
                                "utilization_by_segment — leadership/sales-focused <50%",
                            ),
                        ]
                    ),
                    "created_at": "2026-07-28T00:00:00Z",
                }
            ],
        }
    )
    bootstrap = GoldLabelBootstrap(
        spark, ingestion_date=date(2026, 8, 11), company_name="Clearsulting"
    )
    intent = _sample_intent("kpi.retrieve_bench_and_capacity", agent_id="kpi")
    labels = bootstrap.bootstrap([intent])
    assert len(labels) == 1
    label = labels[0]
    assert label.gold_status == "bootstrap_failed"
    assert label.positive_chunk_ids == []
    assert label.notes is not None
    assert "Pass 1 found zero positives" in label.notes
    assert "pdf_branch_unresolved" in label.notes
    assert "bench_note" in label.notes
    assert "utilization_by_segment — leadership/sales-focused <50%" in label.notes


def test_kpi_pdf_branch_over_broad_section_pattern_resolves_exact_chunk_ids():
    """F-05: Overview matches multiple headers; page narrowing must pin exact positives."""
    spark = MockSpark(
        {
            "COUNT(*) AS chunk_count": [{"chunk_count": 12000}],
            "analysis.kpi": [
                {
                    "citations": _kpi_citations_json(
                        [
                            (
                                "Clearsulting Diligence Report_vF.pdf",
                                "Section: Overview, Page 14",
                                "gross_margin_by_segment — Overall Recast Historical",
                            ),
                        ]
                    ),
                    "created_at": "2026-07-28T00:00:00Z",
                }
            ],
            "page_start = 14 AND section_header ILIKE '%Overview%'": [
                {"chunk_id": "overview_p14_a"},
                {"chunk_id": "overview_p14_b"},
            ],
            "page_start = 14": [
                {"chunk_id": "overview_p14_a"},
                {"chunk_id": "overview_p14_b"},
            ],
            "section_header ILIKE '%Overview%'": [
                {"chunk_id": "overview_p14_a"},
                {"chunk_id": "overview_p14_b"},
                {"chunk_id": "overview_p99_unrelated"},
            ],
        }
    )
    bootstrap = GoldLabelBootstrap(
        spark, ingestion_date=date(2026, 8, 11), company_name="Clearsulting"
    )
    intent = _sample_intent("kpi.retrieve_bill_rates_and_margins", agent_id="kpi")
    label = bootstrap.bootstrap([intent])[0]
    assert label.positive_chunk_ids == ["overview_p14_a", "overview_p14_b"]
    assert "overview_p99_unrelated" not in label.positive_chunk_ids


def test_kpi_pdf_branch_no_page_location_is_document_scoped_not_page_scoped():
    """F-05: Section-only citation must not add page_start narrowing to the chunk query."""
    spark = MockSpark(
        {
            "COUNT(*) AS chunk_count": [{"chunk_count": 12000}],
            "analysis.kpi": [
                {
                    "citations": _kpi_citations_json(
                        [
                            (
                                "Clearsulting Diligence Report_vF.pdf",
                                "Section: Employee Analysis",
                                "gross_margin_by_segment — Overall Recast Historical",
                            ),
                        ]
                    ),
                    "created_at": "2026-07-28T00:00:00Z",
                }
            ],
            "section_header ILIKE '%Employee Analysis%'": [
                {"chunk_id": "employee_doc_a"},
                {"chunk_id": "employee_doc_b"},
            ],
        }
    )
    bootstrap = GoldLabelBootstrap(
        spark, ingestion_date=date(2026, 8, 11), company_name="Clearsulting"
    )
    intent = _sample_intent("kpi.retrieve_bill_rates_and_margins", agent_id="kpi")
    label = bootstrap.bootstrap([intent])[0]
    assert label.positive_chunk_ids == ["employee_doc_a", "employee_doc_b"]
    pdf_queries = [
        query
        for query in spark.queries
        if "section_header ILIKE '%Employee Analysis%'" in " ".join(query.split())
    ]
    assert pdf_queries, "expected a section-scoped KPI PDF query"
    assert all("page_start" not in query for query in pdf_queries)
