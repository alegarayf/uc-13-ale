"""Hermetic tests for KPI Excel citation branch — Contract T2-a/b/c."""

from __future__ import annotations

import json
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
    _walk_json_for_source_refs,
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


class _SparkRow(SimpleNamespace):
    """Spark-shaped row so overlay JSON columns survive `_analysis_row_as_dict`."""

    def asDict(self, recursive: bool = False) -> dict:
        return vars(self).copy()


class MockDataFrame:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = [_SparkRow(**row) for row in rows]

    def collect(self) -> list[_SparkRow]:
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


def test_excel_location_form_iii_slash_section_suffix():
    loc = "Sheet: SUMMARY-Bonus / Section: Summary"
    assert _excel_tab_candidate_from_location(loc) == "SUMMARY-Bonus"


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


_CS_FDR_PDF = (
    "Project Infinity - Draft Financial Diligence Report - August 29, 2025_redacted.pdf"
)


def _clearsulting_overlay_block() -> dict:
    """Live CS tech_services shape: provenance source_doc, no claim/field."""
    return {
        "source_doc": _CS_FDR_PDF,
        "bill_rates_by_role": [
            {"role": "Analyst", "source_doc": _CS_FDR_PDF},
            {"role": "Manager", "source_doc": _CS_FDR_PDF},
        ],
        "gross_margin_by_segment": [
            {"segment": "NA", "source_doc": _CS_FDR_PDF},
        ],
    }


def test_walk_skips_claimless_overlay_source_doc():
    refs: list = []
    _walk_json_for_source_refs(
        _clearsulting_overlay_block(), refs, skip_claimless=True
    )
    assert refs == []
    claimed = {
        "source_doc": _CS_FDR_PDF,
        "claim": "healthcare_kpis.census_or_patient_panel",
        "source_location": "p. 12",
    }
    kept: list = []
    _walk_json_for_source_refs(claimed, kept, skip_claimless=True)
    assert kept == [(_CS_FDR_PDF, "p. 12", "healthcare_kpis.census_or_patient_panel")]


def test_claimless_overlay_source_doc_does_not_fail_close(kpi_spark_handlers):
    """Named regression: CS overlay source_doc claim=None must not enter KPI validate."""
    handlers = dict(kpi_spark_handlers)
    row = dict(handlers["analysis.kpi"][0])
    row["tech_services_kpis_json"] = json.dumps(_clearsulting_overlay_block())
    handlers["analysis.kpi"] = [row]
    spark = MockSpark(handlers)
    bootstrap = GoldLabelBootstrap(spark, ingestion_date=date(2026, 8, 11))
    refs = bootstrap._citation_refs_for_agent("kpi")
    assert all(claim is not None for _document, _location, claim in refs)
    assert not any(document == _CS_FDR_PDF for document, _location, _claim in refs)
    bootstrap._validate_kpi_citation_refs(refs)
    intent = _sample_intent("kpi.retrieve_healthcare_ops", agent_id="kpi")
    label = bootstrap.bootstrap([intent])[0]
    assert label.positive_chunk_ids == ["ops_chunk_1"]


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


# Warehouse-verified claim keys (uc13_ale.analysis.kpi, 2026-08-18 probe).
_GKF_WAREHOUSE_CLAIMS: tuple[tuple[str, str], ...] = (
    (
        "consumer_kpis.channel_mix_note — Revenue line items",
        "kpi.retrieve_bill_rates_and_margins",
    ),
    (
        "consumer_kpis.channel_mix_note — Tuition fees as % of revenue",
        "kpi.retrieve_bill_rates_and_margins",
    ),
    (
        "consumer_kpis.platform_concentration_note — Franchise fees",
        "kpi.retrieve_bill_rates_and_margins",
    ),
    (
        "consumer_kpis.platform_concentration_note — School locations",
        "kpi.retrieve_bench_and_capacity",
    ),
    ("equity — Distributions", "kpi.retrieve_bill_rates_and_margins"),
    ("equity — Ending equity balance", "kpi.retrieve_bill_rates_and_margins"),
    ("management — Named executives", "kpi.retrieve_headcount_attrition"),
    (
        "payroll — Salaries as % of revenue (Top Farm)",
        "kpi.retrieve_bill_rates_and_margins",
    ),
    (
        "payroll — Teachers and Staff headcount by school (2025 budget)",
        "kpi.retrieve_headcount_attrition",
    ),
    (
        "revenue — Total combined tuition fees FY23",
        "kpi.retrieve_bill_rates_and_margins",
    ),
    (
        "revenue — Total revenue FY23/FY24/TTM25 (one entity)",
        "kpi.retrieve_bill_rates_and_margins",
    ),
)

_SPG_WAREHOUSE_CLAIMS: tuple[tuple[str, str], ...] = (
    ("ar_aging_by_payor_note", "kpi.retrieve_healthcare_revenue_per_unit"),
    ("census_or_patient_panel", "kpi.retrieve_healthcare_ops"),
    ("collections_note", "kpi.retrieve_healthcare_revenue_per_unit"),
    ("compliance_incidents[0]", "kpi.retrieve_healthcare_ops"),
    ("compliance_incidents[1]", "kpi.retrieve_healthcare_ops"),
    ("credentialing_status_note", "kpi.retrieve_healthcare_ops"),
    ("healthcare_kpis.source_doc", "kpi.retrieve_healthcare_ops"),
    ("site_level_visibility_note", "kpi.retrieve_healthcare_ops"),
    ("utilization_or_productivity_note", "kpi.retrieve_healthcare_ops"),
)

# Cycle-9 live exact strings (uc13_ale.analysis.kpi, 2026-09-09 warehouse walk).
_CS_LIVE_CLAIMS_CYCLE9: tuple[tuple[str, str], ...] = (
    ("average_bill_rate_dollars", "kpi.retrieve_bill_rates_and_margins"),
    ("bill_rates_by_role (North America USD)", "kpi.retrieve_bill_rates_and_margins"),
    ("bill_rates_by_role (EMEA GBP)", "kpi.retrieve_bill_rates_and_margins"),
    ("bill_rates_by_role (EMEA EUR)", "kpi.retrieve_bill_rates_and_margins"),
    (
        "gross_margin_by_segment (recast historical)",
        "kpi.retrieve_bill_rates_and_margins",
    ),
    (
        "gross_margin_by_segment (Financial Close Practice 2025E)",
        "kpi.retrieve_bill_rates_and_margins",
    ),
    (
        "gross_margin_by_segment (Treasury Practice 2025E)",
        "kpi.retrieve_bill_rates_and_margins",
    ),
    (
        "gross_margin_by_segment (Overall 2025E)",
        "kpi.retrieve_bill_rates_and_margins",
    ),
    (
        "gross_margin_by_segment (subcontracting fees)",
        "kpi.retrieve_bill_rates_and_margins",
    ),
    (
        "gross_margin_by_segment (Application Managed Services 2025E)",
        "kpi.retrieve_bill_rates_and_margins",
    ),
    ("gross_margin_by_segment (note on Other)", "kpi.retrieve_bill_rates_and_margins"),
    ("delivery_capacity_note (headcount)", "kpi.retrieve_headcount_attrition"),
    ("delivery_capacity_note (billable hours)", "kpi.retrieve_headcount_attrition"),
)

_GKF_LIVE_CLAIMS_CYCLE9: tuple[tuple[str, str], ...] = (
    (
        "consumer_kpis.channel_mix_note — Summer Camp revenue",
        "kpi.retrieve_bill_rates_and_margins",
    ),
    (
        "consumer_kpis.channel_mix_note — Total Revenue FY23",
        "kpi.retrieve_bill_rates_and_margins",
    ),
    (
        "consumer_kpis.channel_mix_note — Total Revenue FY24",
        "kpi.retrieve_bill_rates_and_margins",
    ),
    (
        "consumer_kpis.channel_mix_note — Total Revenue TTM25",
        "kpi.retrieve_bill_rates_and_margins",
    ),
    (
        "consumer_kpis.channel_mix_note — Tuition fees as % of revenue FY23",
        "kpi.retrieve_bill_rates_and_margins",
    ),
    (
        "consumer_kpis.platform_concentration_note — franchise fees",
        "kpi.retrieve_bill_rates_and_margins",
    ),
    (
        "consumer_kpis.platform_concentration_note — locations",
        "kpi.retrieve_bench_and_capacity",
    ),
    (
        "missing_kpis — Rockville single-location revenue detail",
        "kpi.retrieve_bill_rates_and_margins",
    ),
    (
        "missing_kpis — employee retention footnote",
        "kpi.retrieve_headcount_attrition",
    ),
    ("missing_kpis — employee retention ratio", "kpi.retrieve_headcount_attrition"),
    ("missing_kpis — enrollment counts", "kpi.retrieve_bench_and_capacity"),
    ("missing_kpis — equity distributions", "kpi.retrieve_bill_rates_and_margins"),
    ("missing_kpis — management headcount", "kpi.retrieve_headcount_attrition"),
    ("missing_kpis — payroll as % of revenue", "kpi.retrieve_bill_rates_and_margins"),
    ("missing_kpis — revenue seasonality", "kpi.retrieve_bill_rates_and_margins"),
    (
        "missing_kpis — teacher/staff headcount by school (Creative Learning)",
        "kpi.retrieve_headcount_attrition",
    ),
    ("missing_kpis — terminations headcount", "kpi.retrieve_headcount_attrition"),
)

_SPG_LIVE_CLAIMS_CYCLE9: tuple[tuple[str, str], ...] = (
    ("census_or_patient_panel — Total # of Starts 2024", "kpi.retrieve_healthcare_ops"),
    (
        "utilization_or_productivity_note — Appointment Completion Rate 2024",
        "kpi.retrieve_healthcare_ops",
    ),
    (
        "utilization_or_productivity_note — Arch Acceptance Rate 2024",
        "kpi.retrieve_healthcare_ops",
    ),
    (
        "revenue_per_unit_note — Net Revenue per Start AO4 2024",
        "kpi.retrieve_healthcare_revenue_per_unit",
    ),
    (
        "collections_note — Arrowhead GN Dental collections adjustment",
        "kpi.retrieve_healthcare_revenue_per_unit",
    ),
    (
        "collections_note — Valley D-I collections adjustment",
        "kpi.retrieve_healthcare_revenue_per_unit",
    ),
    (
        "collections_note — Dell Rapids collections adjustment",
        "kpi.retrieve_healthcare_revenue_per_unit",
    ),
    (
        "collections_note — Sharp Family Dentistry collections adjustment",
        "kpi.retrieve_healthcare_revenue_per_unit",
    ),
    (
        "credentialing_status_note — terminated providers",
        "kpi.retrieve_healthcare_ops",
    ),
    (
        "site_level_visibility_note — projection model site tabs",
        "kpi.retrieve_healthcare_ops",
    ),
    ("site_level_visibility_note — consolidated EBITDA", "kpi.retrieve_healthcare_ops"),
    (
        "utilization_or_productivity_note — KPIs tracked per sales playbook",
        "kpi.retrieve_healthcare_ops",
    ),
)

_EC_LIVE_CLAIMS_CYCLE9: tuple[tuple[str, str], ...] = (
    (
        "healthcare_kpis.utilization_or_productivity_note",
        "kpi.retrieve_healthcare_ops",
    ),
    ("healthcare_kpis.compliance_incidents[0]", "kpi.retrieve_healthcare_ops"),
    ("healthcare_kpis.compliance_incidents[1]", "kpi.retrieve_healthcare_ops"),
    ("healthcare_kpis.credentialing_status_note", "kpi.retrieve_healthcare_ops"),
    (
        "healthcare_kpis.revenue_per_client_dollars",
        "kpi.retrieve_healthcare_revenue_per_unit",
    ),
    ("healthcare_kpis.referral_source_breakdown", "kpi.retrieve_healthcare_ops"),
    ("healthcare_kpis.site_level_visibility_note", "kpi.retrieve_healthcare_ops"),
)

# Cycle-26 W3 live citation aliases (packet-named blockers + Infinitive warehouse walk).
_W3_LIVE_CLAIMS_CYCLE26: tuple[tuple[str, str], ...] = (
    (
        "average_bill_rate_dollars (2025 total)",
        "kpi.retrieve_bill_rates_and_margins",
    ),
    (
        "delivery_capacity_note (headcount by level)",
        "kpi.retrieve_headcount_attrition",
    ),
    ("utilization_rate_pct", "kpi.retrieve_bench_and_capacity"),
    ("tech_services_kpis.bookings_stated", "kpi.retrieve_pipeline_backlog"),
    (
        "tech_services_kpis.delivery_geography_note",
        "kpi.retrieve_bench_and_capacity",
    ),
    (
        "account_lead_comp_plan — billability factor",
        "kpi.retrieve_bench_and_capacity",
    ),
    (
        "average_bill_rate_dollars — T&M 2025",
        "kpi.retrieve_bill_rates_and_margins",
    ),
    (
        "pipeline_vs_capacity_note — booked backlog as of 03/31/26",
        "kpi.retrieve_pipeline_backlog",
    ),
    ("contractor_workforce_presence", "kpi.retrieve_headcount_attrition"),
    ("delivery_capacity_note", "kpi.retrieve_headcount_attrition"),
    (
        "tech_services_kpis.bookings_stated (subscription booked)",
        "kpi.retrieve_pipeline_backlog",
    ),
    ("utilization_rate_pct (target)", "kpi.retrieve_bench_and_capacity"),
)


@pytest.mark.parametrize(("claim", "intent_id"), _GKF_WAREHOUSE_CLAIMS)
def test_gkf_warehouse_claims_resolve(claim: str, intent_id: str):
    claim_map, _ = load_kpi_claim_intent_map()
    assert claim_map[claim] == intent_id


@pytest.mark.parametrize(("claim", "intent_id"), _SPG_WAREHOUSE_CLAIMS)
def test_spg_bare_healthcare_claims_resolve(claim: str, intent_id: str):
    claim_map, _ = load_kpi_claim_intent_map()
    assert claim_map[claim] == intent_id


@pytest.mark.parametrize(("claim", "intent_id"), _CS_LIVE_CLAIMS_CYCLE9)
def test_cs_live_claims_cycle9_resolve(claim: str, intent_id: str):
    claim_map, _ = load_kpi_claim_intent_map()
    assert claim_map[claim] == intent_id


@pytest.mark.parametrize(("claim", "intent_id"), _GKF_LIVE_CLAIMS_CYCLE9)
def test_gkf_live_claims_cycle9_resolve(claim: str, intent_id: str):
    claim_map, _ = load_kpi_claim_intent_map()
    assert claim_map[claim] == intent_id


@pytest.mark.parametrize(("claim", "intent_id"), _SPG_LIVE_CLAIMS_CYCLE9)
def test_spg_live_claims_cycle9_resolve(claim: str, intent_id: str):
    claim_map, _ = load_kpi_claim_intent_map()
    assert claim_map[claim] == intent_id


@pytest.mark.parametrize(("claim", "intent_id"), _EC_LIVE_CLAIMS_CYCLE9)
def test_ec_live_claims_cycle9_resolve(claim: str, intent_id: str):
    claim_map, _ = load_kpi_claim_intent_map()
    assert claim_map[claim] == intent_id


@pytest.mark.parametrize(("claim", "intent_id"), _W3_LIVE_CLAIMS_CYCLE26)
def test_w3_live_claims_cycle26_resolve(claim: str, intent_id: str):
    claim_map, _ = load_kpi_claim_intent_map()
    assert claim_map[claim] == intent_id


def test_cycle9_live_claims_use_em_dash_not_hyphen():
    claim_map, _ = load_kpi_claim_intent_map()
    em_dash = "census_or_patient_panel — Total # of Starts 2024"
    hyphen = "census_or_patient_panel - Total # of Starts 2024"
    assert em_dash in claim_map
    assert hyphen not in claim_map
    assert "\u2014" in em_dash


def test_gkf_education_claim_bootstrap_excel_branch(kpi_spark_handlers):
    gkf_claim = (
        "consumer_kpis.channel_mix_note — Tuition fees as % of revenue"
    )
    handlers = dict(kpi_spark_handlers)
    handlers["analysis.kpi"] = [
        {
            "citations": _kpi_citations_json(
                [
                    (
                        "Project Ajax - Financial Due Diligence Databook - 12.22.25.xlsx",
                        "Sheet: Revenue, Section: Summary — Key Metrics: As a % of Total Revenue",
                        gkf_claim,
                    ),
                ]
            ),
            "created_at": "2026-08-18T00:00:00Z",
        }
    ]
    handlers["SELECT DISTINCT c.tab"] = [{"tab": "Revenue"}]
    handlers["c.tab = 'Revenue'"] = [{"chunk_id": "gkf_rev_chunk_1"}]
    spark = MockSpark(handlers)
    bootstrap = GoldLabelBootstrap(
        spark,
        ingestion_date=date(2026, 8, 18),
        company_name="GKF",
    )
    intent = _sample_intent(
        "kpi.retrieve_bill_rates_and_margins",
        agent_id="kpi",
    )
    label = bootstrap.bootstrap([intent])[0]
    assert label.gold_method == "citation_backfill"
    assert label.positive_chunk_ids == ["gkf_rev_chunk_1"]


def test_hyphen_dash_claim_variant_not_mapped():
    claim_map, _ = load_kpi_claim_intent_map()
    hyphen_variant = (
        "consumer_kpis.channel_mix_note - Tuition fees as % of revenue"
    )
    assert hyphen_variant not in claim_map
