"""Wave-3 company-scoped harness overrides (cycle 37 / P1).

Six in-loop W3 slugs get D29 live filename / workstream tokens.
Shared BMA / CQA / KPI / FTA / legal / QoE registry query: strings stay
byte-identical (D11). CS / GKF / Elder Care leftover branches stay intact.
SPG keeps shared registry strings on W3-touched intents.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from eval.retrieval.harness import (
    CS_ACCOUNT_SIZE_FILE_NAME_FILTER,
    CS_ACCOUNT_SIZE_INTENT_ID,
    CS_ACCOUNT_SIZE_QUERY,
    CS_BENCH_FILE_NAME_FILTER,
    CS_BENCH_INTENT_ID,
    CS_BENCH_QUERY,
    CS_KPI_DASHBOARD_FILE_NAME_FILTER,
    CS_KPI_DASHBOARD_INTENT_ID,
    CS_KPI_DASHBOARD_QUERY,
    CS_LOCATION_FILE_NAME_FILTER,
    CS_LOCATION_INTENT_ID,
    CS_LOCATION_QUERY,
    CS_Q4_FALLBACK_FILE_NAME_FILTER,
    CS_Q4_FALLBACK_INTENT_ID,
    CS_Q4_FALLBACK_QUERY,
    CS_VISIBILITY_FILE_NAME_FILTER,
    CS_VISIBILITY_INTENT_ID,
    CS_VISIBILITY_QUERY,
    EC_CIM_PRESENCE_FILE_NAME_FILTER,
    EC_CIM_PRESENCE_INTENT_ID,
    EC_CIM_PRESENCE_QUERY,
    EC_CONTRACTS_FILE_NAME_FILTER,
    EC_CONTRACTS_INTENT_ID,
    EC_CONTRACTS_QUERY,
    GKF_LOCATION_FILE_NAME_FILTER,
    GKF_LOCATION_INTENT_ID,
    GKF_LOCATION_QUERY,
    INF_BENCH_FILE_NAME_FILTER,
    INF_BENCH_INTENT_ID,
    INF_BENCH_QUERY,
    INF_OVERVIEW_FILE_NAME_FILTER,
    INF_OVERVIEW_FILE_NAME_FILTER_FALLBACK,
    INF_OVERVIEW_INTENT_ID,
    INF_OVERVIEW_QUERY,
    INF_PEOPLE_INTENT_ID,
    INF_VISIBILITY_FILE_NAME_FILTER,
    INF_VISIBILITY_INTENT_ID,
    INF_VISIBILITY_QUERY,
    IR_ACCOUNT_SIZE_FILE_NAME_FILTER,
    IR_ACCOUNT_SIZE_INTENT_ID,
    IR_ACCOUNT_SIZE_QUERY,
    IR_BENCH_FILE_NAME_FILTER,
    IR_BENCH_INTENT_ID,
    IR_BENCH_QUERY,
    IR_HEADCOUNT_FILE_NAME_FILTER,
    IR_HEADCOUNT_INTENT_ID,
    IR_HEADCOUNT_QUERY,
    IR_LOCATION_FILE_NAME_FILTER,
    IR_LOCATION_INTENT_ID,
    IR_LOCATION_QUERY,
    NB_Q3_FILE_NAME_FILTER,
    NB_Q3_INTENT_ID,
    NB_Q3_QUERY,
    NB_VISIBILITY_FILE_NAME_FILTER,
    NB_VISIBILITY_INTENT_ID,
    NB_VISIBILITY_QUERY,
    NB_VISIBILITY_WORKSTREAM_FILTER,
    SHERPA_QOFE_FILE_NAME_FILTER,
    SHERPA_QOFE_INTENT_ID,
    SHERPA_QOFE_QUERY,
    SHERPA_QOFE_WORKSTREAM_FILTER,
    SHERPA_SALES_FILE_NAME_FILTER,
    SHERPA_SALES_INTENT_ID,
    SHERPA_SALES_QUERY,
    SOLVD_CONCENTRATION_INTENT_ID,
    SOLVD_CONCENTRATION_QUERY,
    SOLVD_CONCENTRATION_WORKSTREAM_FILTER,
    SOLVD_CONTRACT_FILE_NAME_FILTER,
    SOLVD_CONTRACT_INTENT_ID,
    SOLVD_CONTRACT_QUERY,
    SOLVD_CONTRACT_WORKSTREAM_FILTER,
    SOLVD_MODEL_CHANGES_FILE_NAME_FILTER,
    SOLVD_MODEL_CHANGES_INTENT_ID,
    SOLVD_MODEL_CHANGES_QUERY,
    SOLVD_OVERVIEW_FILE_NAME_FILTER,
    SOLVD_OVERVIEW_INTENT_ID,
    SOLVD_OVERVIEW_QUERY,
    SOLVD_Q2_FILE_NAME_FILTER,
    SOLVD_Q2_INTENT_ID,
    SOLVD_Q2_QUERY,
    SOLVD_Q3_FILE_NAME_FILTER,
    SOLVD_Q3_INTENT_ID,
    SOLVD_Q3_QUERY,
    SOLVD_VISIBILITY_FILE_NAME_FILTER,
    SOLVD_VISIBILITY_INTENT_ID,
    SOLVD_VISIBILITY_QUERY,
    STRIDE_CONCENTRATION_INTENT_ID,
    STRIDE_CONCENTRATION_WORKSTREAM_FILTER,
    STRIDE_CQA_FILE_NAME_FILTER,
    STRIDE_CQA_QUERY,
    STRIDE_HEADCOUNT_FILE_NAME_FILTER,
    STRIDE_HEADCOUNT_INTENT_ID,
    STRIDE_HEADCOUNT_QUERY,
    STRIDE_HEADCOUNT_WORKSTREAM_FILTER,
    STRIDE_HEALTH_INTENT_ID,
    STRIDE_KPI_DASHBOARD_FILE_NAME_FILTER,
    STRIDE_KPI_DASHBOARD_FILE_NAME_FILTER_FALLBACK,
    STRIDE_KPI_DASHBOARD_INTENT_ID,
    STRIDE_KPI_DASHBOARD_QUERY,
    STRIDE_Q4_FALLBACK_FILE_NAME_FILTER,
    STRIDE_Q4_FALLBACK_INTENT_ID,
    STRIDE_Q4_FALLBACK_QUERY,
    STRIDE_REVENUE_TYPE_FILE_NAME_FILTER,
    STRIDE_REVENUE_TYPE_FILE_NAME_FILTER_FALLBACK,
    STRIDE_REVENUE_TYPE_INTENT_ID,
    STRIDE_REVENUE_TYPE_QUERY,
    STRIDE_REVENUE_TYPE_WORKSTREAM_FILTER,
    _fallback_kwargs_from_intent,
    apply_company_intent_overrides,
    build_search_kwargs,
    dispatch_retrieval,
)
from eval.retrieval.registry_extractor import IntentRegistryExtractor

REPO_ROOT = Path(__file__).resolve().parents[3]
REGISTRY_PATH = REPO_ROOT / "eval" / "retrieval" / "intent_registry.yaml"

W3_COMPANIES = (
    "Infinitive",
    "Integrity Risk",
    "Northbound",
    "Stride",
    "Project Sherpa",
    "Solvd",
)
INCUMBENT_COMPANIES = ("Clearsulting", "GKF", "SPG", "Elder Care")

PRIMARY_Q4_INTENT_ID = "fta.revenue.q4_customer_concentration"

SHARED_VISIBILITY_QUERY = (
    "Clear Strategic Roadmap of Growth Opportunities Project Ajax revenue target "
    "86.6 million 2030 24 schools historical projected revenue PF Adj EBITDA School "
    "Financial Performance BALANCE SHEET SUMMARY"
)
SHARED_VISIBILITY_FILE_NAME_FILTER = [
    "CIM",
    "Pipeline",
    "Backlog",
    "Contract",
    "Revenue",
    "KPI",
    "Metrics",
    "Overview",
    "Model",
]
SHARED_VISIBILITY_WORKSTREAM_FILTER = [
    "BUSINESS_MODEL",
    "FINANCIAL",
    "KPI_OPS",
]

SHARED_BENCH_QUERY = (
    "bench size bench cost unassigned headcount non-billable available capacity "
    "delivery capacity sales pipeline coverage capacity planning staffing plan billable "
    "vs non-billable overhead headcount average sales cycle pipeline conversion"
)
SHARED_BENCH_FILE_NAME_FILTER = [
    "Bench",
    "Capacity",
    "Staffing",
    "Pipeline",
    "Workforce",
    "Headcount",
    "KPI",
    "Operations",
    "GTM",
    "Sales",
]

SHARED_PEOPLE_QUERY = (
    "management team key executives CEO founder CTO COO VP president director "
    "ownership structure capitalization shareholder equity ownership percentage organizational "
    "chart org chart key personnel management depth bench entity structure subsidiary "
    "holding company operating entity executive biography background experience years "
    "tenure key man risk leadership team senior management"
)
SHARED_PEOPLE_FILE_NAME_FILTER = [
    "CIM",
    "OM",
    "Management",
    "Team",
    "Overview",
    "Org",
    "Chart",
    "Cap",
    "Table",
    "Personnel",
    "Executive",
    "Leadership",
    "Presentation",
]
SHARED_PEOPLE_WORKSTREAM_FILTER = ["BUSINESS_MODEL"]

SHARED_OVERVIEW_QUERY = (
    "company overview what does this company do products services offerings geographic "
    "footprint locations markets business description revenue streams what the company "
    "sells how it makes money"
)
SHARED_OVERVIEW_FILE_NAME_FILTER = [
    "CIM",
    "OM",
    "Overview",
    "Offering",
    "Memorandum",
    "Profile",
    "Summary",
    "Presentation",
    "Deck",
    "Management",
    "Executive",
]
SHARED_OVERVIEW_WORKSTREAM_FILTER = ["BUSINESS_MODEL"]

SHARED_LOCATION_QUERY = (
    "clients served active accounts customers by location by market by segment "
    "billed hours per client revenue per customer revenue per account utilization "
    "per customer sessions per user visits per patient customer count trend quarterly "
    "growth by location by geography length of stay customer tenure distribution cohort "
    "by duration revenue per location revenue by market adjusted revenue by geography "
    "revenue CAGR financial highlights headline metrics acquisition pipeline same store "
    "revenue organic growth by market revenue goal by location Shared Practices "
    "Dashboard new patient visits distribution within my network locations Corporate "
    "Organization Current State leadership team DMV Mike Pesi CEO Ross Flax Ellicott "
    "City Academic Director Teachers and Staff"
)
SHARED_LOCATION_FILE_NAME_FILTER = [
    "CIM",
    "OM",
    "Financial",
    "Revenue",
    "Metrics",
    "Overview",
    "Summary",
    "KPI",
    "Dashboard",
]

SHARED_HEADCOUNT_QUERY = (
    "Employee Retention Analysis Staff beginning of Year Hires Terminations Staff "
    "at End of Year Employee Count Payroll Build Project Ajax Model vE"
)
SHARED_HEADCOUNT_WORKSTREAM_FILTER = ["KPI_OPS", "FINANCIAL"]

SHARED_Q3_QUERY = (
    "projected revenue forecast 2025 2026 2027 2028 2029 gross profit gross margin "
    "operating expenses OPEX salaries labor projected EBITDA summary P&L income statement "
    "forward projections revenue projection plan financial model projection assumptions "
    "cost of revenue compensation benefits G&A overhead"
)
SHARED_Q3_FILE_NAME_FILTER = [
    "Model",
    "Projection",
    "Forecast",
    "Budget",
    "CIM",
    "Financial",
    "P&L",
]

SHARED_CONCENTRATION_QUERY = (
    "top customers revenue concentration customer list percentage revenue share "
    "billing amount summary by client Billing"
)
SHARED_CONCENTRATION_FILE_NAME_FILTER = [
    "Customer",
    "Revenue",
    "Concentration",
    "CIM",
    "QofE",
]
SHARED_CONCENTRATION_WORKSTREAM_FILTER = ["CUSTOMER"]

SHARED_HEALTH_QUERY = (
    "customer health AR aging late payment overdue DSO discounts rebates concessions "
    "complaints NPS utilization declining spend collections"
)
SHARED_HEALTH_FILE_NAME_FILTER = [
    "AR",
    "Aging",
    "Customer",
    "Collections",
    "Revenue",
    "QofE",
]
SHARED_HEALTH_WORKSTREAM_FILTER = [
    "CUSTOMER",
    "QUALITY_EARNINGS",
    "FINANCIAL",
]

SHARED_Q4_FALLBACK_QUERY = (
    "Project Ajax Financial Due Diligence Databook Location Analysis Revenue "
    "Detail Combined FY23 tuition by school enrollment"
)
SHARED_Q4_FALLBACK_FILE_NAME_FILTER = [
    "Customer",
    "QuickBooks",
    "QBO",
    "Sales",
    "Concentration",
    "Client",
    "Payor",
    "Revenue",
    "Databook",
    "CIM",
    "Ajax",
    "Model",
]

SHARED_SALES_QUERY = (
    "sales motion go to market customer acquisition business development customer "
    "segment end market vertical buyer persona channel partner referral network enterprise "
    "sales inbound outbound sales process new customer acquisition how we sell who "
    "we sell to"
)
SHARED_SALES_FILE_NAME_FILTER = [
    "CIM",
    "Sales",
    "GTM",
    "Customer",
    "Marketing",
    "Overview",
    "OM",
    "Strategy",
    "Presentation",
]

SHARED_QOFE_QUERY = (
    "quality of earnings QofE adjusted EBITDA addback schedule sell-side accounting "
    "due diligence"
)
SHARED_QOFE_FILE_NAME_FILTER = [
    "QofE",
    "Quality",
    "Earnings",
    "Due Diligence",
    "Accounting",
    "Addback",
]
SHARED_QOFE_WORKSTREAM_FILTER = ["QUALITY_EARNINGS"]

SHARED_Q2_QUERY = (
    "revenue by segment product line geography service line revenue split breakdown "
    "revenue by location revenue by office revenue by division revenue by customer "
    "type"
)
SHARED_Q2_FILE_NAME_FILTER = [
    "P&L",
    "Financial",
    "Revenue",
    "Segment",
    "CIM",
]

SHARED_CONTRACT_QUERY = (
    "contract terms termination for convenience change of control pricing escalator "
    "CPI escalation auto-renewal exclusivity MSA SOW renewal mechanics notice period "
    "right to terminate"
)
SHARED_CONTRACT_FILE_NAME_FILTER = [
    "Contract",
    "MSA",
    "Agreement",
    "SOW",
    "Legal",
    "Customer",
]
SHARED_CONTRACT_WORKSTREAM_FILTER = ["CUSTOMER", "LEGAL"]

SHARED_REVENUE_TYPE_QUERY = (
    "recurring revenue project revenue one-time revenue retainer ARR MRR renewal "
    "rate expansion revenue upsell revenue mix contracted backlog"
)
SHARED_REVENUE_TYPE_FILE_NAME_FILTER = [
    "CIM",
    "Revenue",
    "Customer",
    "Model",
    "KPI",
    "Metrics",
]
SHARED_REVENUE_TYPE_WORKSTREAM_FILTER = [
    "CUSTOMER",
    "BUSINESS_MODEL",
    "FINANCIAL",
]

SHARED_MODEL_CHANGES_QUERY = (
    "business model change pricing change go to market change recent initiative "
    "ERP CRM EMR payroll HR software scheduling platform technology system outsourcing "
    "offshore remote team global staffing third-party operations acquisition M&A history "
    "strategic initiative timeline milestones launched expanded hired opened acquired "
    "transitioned implemented automated key dependency concentration risk single vendor "
    "platform tool new product new service new geography new channel new pricing model "
    "digital transformation process improvement technology adoption"
)
SHARED_MODEL_CHANGES_FILE_NAME_FILTER = [
    "CIM",
    "Overview",
    "Timeline",
    "History",
    "OM",
    "Strategy",
    "Presentation",
    "Management",
    "Deck",
]
SHARED_MODEL_CHANGES_WORKSTREAM_FILTER = ["BUSINESS_MODEL", "KPI_OPS"]

SHARED_ACCOUNT_SIZE_QUERY = (
    "average account size ACV annual contract value revenue per customer SMB enterprise"
)

SHARED_KPI_DASHBOARD_QUERY = (
    "GL KPI spreadsheet internal intranet utilization revenue per FTE headcount operating"
)
SHARED_KPI_DASHBOARD_FILE_NAME_FILTER = [
    "KPI",
    "Dashboard",
    "Metrics",
    "Scorecard",
    "Operating",
    "Performance",
]
SHARED_KPI_DASHBOARD_WORKSTREAM_FILTER = ["KPI_OPS"]

REGISTRY_LOCKSTEP = (
    (INF_VISIBILITY_INTENT_ID, SHARED_VISIBILITY_QUERY, SHARED_VISIBILITY_FILE_NAME_FILTER),
    (INF_BENCH_INTENT_ID, SHARED_BENCH_QUERY, SHARED_BENCH_FILE_NAME_FILTER),
    (INF_PEOPLE_INTENT_ID, SHARED_PEOPLE_QUERY, SHARED_PEOPLE_FILE_NAME_FILTER),
    (INF_OVERVIEW_INTENT_ID, SHARED_OVERVIEW_QUERY, SHARED_OVERVIEW_FILE_NAME_FILTER),
    (IR_LOCATION_INTENT_ID, SHARED_LOCATION_QUERY, SHARED_LOCATION_FILE_NAME_FILTER),
    (IR_HEADCOUNT_INTENT_ID, SHARED_HEADCOUNT_QUERY, None),
    (IR_ACCOUNT_SIZE_INTENT_ID, SHARED_ACCOUNT_SIZE_QUERY, None),
    (NB_Q3_INTENT_ID, SHARED_Q3_QUERY, SHARED_Q3_FILE_NAME_FILTER),
    (STRIDE_CONCENTRATION_INTENT_ID, SHARED_CONCENTRATION_QUERY, SHARED_CONCENTRATION_FILE_NAME_FILTER),
    (STRIDE_HEALTH_INTENT_ID, SHARED_HEALTH_QUERY, SHARED_HEALTH_FILE_NAME_FILTER),
    (STRIDE_Q4_FALLBACK_INTENT_ID, SHARED_Q4_FALLBACK_QUERY, SHARED_Q4_FALLBACK_FILE_NAME_FILTER),
    (STRIDE_REVENUE_TYPE_INTENT_ID, SHARED_REVENUE_TYPE_QUERY, SHARED_REVENUE_TYPE_FILE_NAME_FILTER),
    (SHERPA_SALES_INTENT_ID, SHARED_SALES_QUERY, SHARED_SALES_FILE_NAME_FILTER),
    (SHERPA_QOFE_INTENT_ID, SHARED_QOFE_QUERY, SHARED_QOFE_FILE_NAME_FILTER),
    (SOLVD_Q2_INTENT_ID, SHARED_Q2_QUERY, SHARED_Q2_FILE_NAME_FILTER),
    (SOLVD_CONTRACT_INTENT_ID, SHARED_CONTRACT_QUERY, SHARED_CONTRACT_FILE_NAME_FILTER),
    (SOLVD_MODEL_CHANGES_INTENT_ID, SHARED_MODEL_CHANGES_QUERY, SHARED_MODEL_CHANGES_FILE_NAME_FILTER),
)


def _by_id():
    extractor = IntentRegistryExtractor(REPO_ROOT)
    return {intent.intent_id: intent for intent in extractor.extract()}


def _committed_by_id():
    rows = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    return {row["intent_id"]: row for row in rows}


def test_shared_w3_registry_queries_stay_byte_identical():
    live = _by_id()
    committed = _committed_by_id()
    for intent_id, shared_query, shared_filter in REGISTRY_LOCKSTEP:
        assert live[intent_id].query == shared_query
        assert committed[intent_id]["query"] == shared_query
        if shared_filter is None:
            assert live[intent_id].file_name_filter is None
            assert committed[intent_id].get("file_name_filter") is None
        else:
            assert list(live[intent_id].file_name_filter) == shared_filter
            assert list(committed[intent_id]["file_name_filter"]) == shared_filter
    assert live[PRIMARY_Q4_INTENT_ID].query == STRIDE_Q4_FALLBACK_QUERY
    assert committed[PRIMARY_Q4_INTENT_ID]["query"] == STRIDE_Q4_FALLBACK_QUERY


def test_infinitive_gets_visibility_and_bench_overrides():
    live = _by_id()
    vis = apply_company_intent_overrides(
        live[INF_VISIBILITY_INTENT_ID], company_name="Infinitive"
    )
    assert vis.query == INF_VISIBILITY_QUERY
    assert list(vis.file_name_filter) == list(INF_VISIBILITY_FILE_NAME_FILTER)
    assert "Visibility" in vis.file_name_filter
    assert "2026E" in vis.file_name_filter
    assert "Revenue" not in vis.file_name_filter
    assert "Memorandum" not in vis.file_name_filter
    assert live[INF_VISIBILITY_INTENT_ID].query == SHARED_VISIBILITY_QUERY

    bench = apply_company_intent_overrides(
        live[INF_BENCH_INTENT_ID], company_name="Infinitive"
    )
    assert bench.query == INF_BENCH_QUERY
    assert list(bench.file_name_filter) == list(INF_BENCH_FILE_NAME_FILTER)
    assert bench.file_name_filter == ["Contractor"]
    assert "Census" not in bench.file_name_filter
    assert "Employee" not in bench.file_name_filter
    assert "Attrition" not in bench.file_name_filter
    assert "Comp" not in bench.file_name_filter

    people = apply_company_intent_overrides(
        live[INF_PEOPLE_INTENT_ID], company_name="Infinitive"
    )
    assert people is live[INF_PEOPLE_INTENT_ID]
    assert people.query == SHARED_PEOPLE_QUERY
    assert list(people.workstream_filter) == SHARED_PEOPLE_WORKSTREAM_FILTER
    assert people.workstream_filter != ["CUSTOMER"]
    assert "CUSTOMER" not in (people.workstream_filter or [])


def test_infinitive_gets_overview_tm_override():
    live = _by_id()
    overview = apply_company_intent_overrides(
        live[INF_OVERVIEW_INTENT_ID], company_name="Infinitive"
    )
    assert overview is not live[INF_OVERVIEW_INTENT_ID]
    assert overview.query == INF_OVERVIEW_QUERY
    assert "T-M vs Fixed Fee Revenue" in overview.query
    assert "Orange Crush" in overview.query
    assert list(overview.file_name_filter) == list(INF_OVERVIEW_FILE_NAME_FILTER)
    assert overview.file_name_filter == ["T-M"]
    assert overview.workstream_filter is None
    assert "CIP" not in overview.query
    assert "CIP" not in (overview.file_name_filter or [])
    assert "CUSTOMER" not in (overview.workstream_filter or [])
    assert "BUSINESS_MODEL" not in (overview.workstream_filter or [])
    assert "CIM" not in overview.file_name_filter
    assert "Offering" not in overview.file_name_filter
    assert "Memorandum" not in overview.file_name_filter
    assert live[INF_OVERVIEW_INTENT_ID].query == SHARED_OVERVIEW_QUERY
    assert list(live[INF_OVERVIEW_INTENT_ID].workstream_filter) == (
        SHARED_OVERVIEW_WORKSTREAM_FILTER
    )

    vis = apply_company_intent_overrides(
        live[INF_VISIBILITY_INTENT_ID], company_name="Infinitive"
    )
    assert vis.query == INF_VISIBILITY_QUERY
    assert list(vis.file_name_filter) == list(INF_VISIBILITY_FILE_NAME_FILTER)
    bench = apply_company_intent_overrides(
        live[INF_BENCH_INTENT_ID], company_name="Infinitive"
    )
    assert bench.query == INF_BENCH_QUERY
    assert list(bench.file_name_filter) == list(INF_BENCH_FILE_NAME_FILTER)
    people = apply_company_intent_overrides(
        live[INF_PEOPLE_INTENT_ID], company_name="Infinitive"
    )
    assert people is live[INF_PEOPLE_INTENT_ID]

    ir_overview = apply_company_intent_overrides(
        live[INF_OVERVIEW_INTENT_ID], company_name="Integrity Risk"
    )
    assert ir_overview is live[INF_OVERVIEW_INTENT_ID]
    assert ir_overview.query == SHARED_OVERVIEW_QUERY


def test_integrity_risk_gets_location_and_headcount_overrides():
    live = _by_id()
    loc = apply_company_intent_overrides(
        live[IR_LOCATION_INTENT_ID], company_name="Integrity Risk"
    )
    assert loc.query == IR_LOCATION_QUERY
    assert list(loc.file_name_filter) == list(IR_LOCATION_FILE_NAME_FILTER)
    assert loc.file_name_filter == ["Cube"]
    assert "Revenue Retention Dashboard" in loc.query
    assert "Memorandum" not in loc.file_name_filter
    assert "Ajax" not in loc.file_name_filter

    hc = apply_company_intent_overrides(
        live[IR_HEADCOUNT_INTENT_ID], company_name="Integrity Risk"
    )
    assert hc.query == IR_HEADCOUNT_QUERY
    assert list(hc.file_name_filter) == list(IR_HEADCOUNT_FILE_NAME_FILTER)
    assert "CIP Graphs" in hc.query
    assert "Attrition" in hc.file_name_filter
    assert "Retention" in hc.file_name_filter
    assert "Ajax" not in hc.query
    assert "Payroll Build" not in hc.query
    assert live[IR_HEADCOUNT_INTENT_ID].file_name_filter is None

    bench = apply_company_intent_overrides(
        live[IR_BENCH_INTENT_ID], company_name="Integrity Risk"
    )
    assert bench.query == IR_BENCH_QUERY
    assert list(bench.file_name_filter) == list(IR_BENCH_FILE_NAME_FILTER)
    assert "CIP Graphs" in bench.query
    assert "Attrition" in bench.file_name_filter
    assert "Retention" in bench.file_name_filter
    assert "Bench" not in bench.file_name_filter
    assert "Capacity" not in bench.file_name_filter
    assert "Staffing" not in bench.file_name_filter
    assert live[IR_BENCH_INTENT_ID].query == SHARED_BENCH_QUERY

    acct = apply_company_intent_overrides(
        live[IR_ACCOUNT_SIZE_INTENT_ID], company_name="Integrity Risk"
    )
    assert acct.query == IR_ACCOUNT_SIZE_QUERY
    assert list(acct.file_name_filter) == list(IR_ACCOUNT_SIZE_FILE_NAME_FILTER)
    assert acct.file_name_filter == ["Cube"]
    assert "Revenue Retention Dashboard" in acct.query
    assert "Memorandum" not in acct.file_name_filter
    assert "ACV" not in acct.query
    assert live[IR_ACCOUNT_SIZE_INTENT_ID].query == SHARED_ACCOUNT_SIZE_QUERY
    assert live[IR_ACCOUNT_SIZE_INTENT_ID].file_name_filter is None

    people = apply_company_intent_overrides(
        live[INF_PEOPLE_INTENT_ID], company_name="Integrity Risk"
    )
    assert people is live[INF_PEOPLE_INTENT_ID]
    assert people.query == SHARED_PEOPLE_QUERY


def test_northbound_gets_replace_visibility_and_q3_overrides():
    live = _by_id()
    vis = apply_company_intent_overrides(
        live[NB_VISIBILITY_INTENT_ID], company_name="Northbound"
    )
    assert vis.query == NB_VISIBILITY_QUERY
    assert list(vis.file_name_filter) == list(NB_VISIBILITY_FILE_NAME_FILTER)
    assert list(vis.workstream_filter) == list(NB_VISIBILITY_WORKSTREAM_FILTER)
    assert vis.file_name_filter == ["B.4.Revenue"]
    assert "CUSTOMER" in vis.workstream_filter
    assert "Revenue" not in vis.file_name_filter
    assert "Memorandum" not in vis.file_name_filter
    assert not set(SHARED_VISIBILITY_FILE_NAME_FILTER).intersection(vis.file_name_filter)

    q3 = apply_company_intent_overrides(
        live[NB_Q3_INTENT_ID], company_name="Northbound"
    )
    assert q3.query == NB_Q3_QUERY
    assert list(q3.file_name_filter) == list(NB_Q3_FILE_NAME_FILTER)
    assert q3.file_name_filter == ["Profit and Loss (1)"]
    assert "P&L" not in q3.file_name_filter
    assert "Financial" not in q3.file_name_filter
    assert "CIM" not in q3.file_name_filter
    assert not set(SHARED_Q3_FILE_NAME_FILTER).intersection(q3.file_name_filter)


def test_stride_gets_cqa_q4_and_headcount_overrides():
    live = _by_id()
    conc = apply_company_intent_overrides(
        live[STRIDE_CONCENTRATION_INTENT_ID], company_name="Stride"
    )
    assert conc.query == STRIDE_CQA_QUERY
    assert list(conc.file_name_filter) == list(STRIDE_CQA_FILE_NAME_FILTER)
    assert list(conc.workstream_filter) == list(STRIDE_CONCENTRATION_WORKSTREAM_FILTER)
    assert conc.file_name_filter == ["2.10"]
    assert "FINANCIAL" in conc.workstream_filter
    assert "Audit" not in conc.file_name_filter
    assert "Customer" not in conc.file_name_filter

    health = apply_company_intent_overrides(
        live[STRIDE_HEALTH_INTENT_ID], company_name="Stride"
    )
    assert health.query == STRIDE_CQA_QUERY
    assert list(health.file_name_filter) == list(STRIDE_CQA_FILE_NAME_FILTER)
    assert health.file_name_filter == ["2.10"]
    assert "Audit" not in health.file_name_filter
    assert list(health.workstream_filter) == SHARED_HEALTH_WORKSTREAM_FILTER

    q4 = apply_company_intent_overrides(
        live[STRIDE_Q4_FALLBACK_INTENT_ID], company_name="Stride"
    )
    assert q4.query == STRIDE_Q4_FALLBACK_QUERY
    assert q4.query == live[PRIMARY_Q4_INTENT_ID].query
    assert list(q4.file_name_filter) == list(STRIDE_Q4_FALLBACK_FILE_NAME_FILTER)
    assert "12.1" in q4.file_name_filter
    assert "Presentation" in q4.file_name_filter
    assert "Josie" not in q4.file_name_filter
    assert "CIM" not in q4.file_name_filter
    assert q4.query != SHARED_Q4_FALLBACK_QUERY

    hc = apply_company_intent_overrides(
        live[STRIDE_HEADCOUNT_INTENT_ID], company_name="Stride"
    )
    assert hc.query == STRIDE_HEADCOUNT_QUERY
    assert list(hc.file_name_filter) == list(STRIDE_HEADCOUNT_FILE_NAME_FILTER)
    assert list(hc.workstream_filter) == list(STRIDE_HEADCOUNT_WORKSTREAM_FILTER)
    assert "BUSINESS_MODEL" in hc.workstream_filter
    assert "EBITDA" in hc.query
    assert "Payroll" not in hc.file_name_filter
    assert "Build" not in hc.file_name_filter


def test_stride_gets_revenue_type_override_and_keeps_f1_f3():
    live = _by_id()
    rev = apply_company_intent_overrides(
        live[STRIDE_REVENUE_TYPE_INTENT_ID], company_name="Stride"
    )
    assert rev is not live[STRIDE_REVENUE_TYPE_INTENT_ID]
    assert rev.query == STRIDE_REVENUE_TYPE_QUERY
    assert "Embedded Relationships" in rev.query
    assert list(rev.file_name_filter) == list(STRIDE_REVENUE_TYPE_FILE_NAME_FILTER)
    assert rev.file_name_filter == ["12.1"]
    assert list(rev.workstream_filter) == list(STRIDE_REVENUE_TYPE_WORKSTREAM_FILTER)
    assert rev.workstream_filter == ["BUSINESS_MODEL"]
    assert "Josie" not in (rev.file_name_filter or [])
    assert "CIM" not in rev.file_name_filter
    assert "Revenue" not in rev.file_name_filter
    assert "Customer" not in rev.file_name_filter
    assert "Model" not in rev.file_name_filter
    assert "KPI" not in rev.file_name_filter
    assert "Metrics" not in rev.file_name_filter
    assert "CUSTOMER" not in (rev.workstream_filter or [])
    assert live[STRIDE_REVENUE_TYPE_INTENT_ID].query == SHARED_REVENUE_TYPE_QUERY
    assert list(live[STRIDE_REVENUE_TYPE_INTENT_ID].file_name_filter) == (
        SHARED_REVENUE_TYPE_FILE_NAME_FILTER
    )
    assert list(live[STRIDE_REVENUE_TYPE_INTENT_ID].workstream_filter) == (
        SHARED_REVENUE_TYPE_WORKSTREAM_FILTER
    )

    # F1–F3 stay byte-identical to the closed overlay.
    conc = apply_company_intent_overrides(
        live[STRIDE_CONCENTRATION_INTENT_ID], company_name="Stride"
    )
    assert conc.query == STRIDE_CQA_QUERY
    assert list(conc.file_name_filter) == list(STRIDE_CQA_FILE_NAME_FILTER)
    assert list(conc.workstream_filter) == list(STRIDE_CONCENTRATION_WORKSTREAM_FILTER)
    health = apply_company_intent_overrides(
        live[STRIDE_HEALTH_INTENT_ID], company_name="Stride"
    )
    assert health.query == STRIDE_CQA_QUERY
    assert list(health.file_name_filter) == list(STRIDE_CQA_FILE_NAME_FILTER)
    q4 = apply_company_intent_overrides(
        live[STRIDE_Q4_FALLBACK_INTENT_ID], company_name="Stride"
    )
    assert q4.query == STRIDE_Q4_FALLBACK_QUERY
    assert list(q4.file_name_filter) == list(STRIDE_Q4_FALLBACK_FILE_NAME_FILTER)
    hc = apply_company_intent_overrides(
        live[STRIDE_HEADCOUNT_INTENT_ID], company_name="Stride"
    )
    assert hc.query == STRIDE_HEADCOUNT_QUERY
    assert list(hc.file_name_filter) == list(STRIDE_HEADCOUNT_FILE_NAME_FILTER)
    assert list(hc.workstream_filter) == list(STRIDE_HEADCOUNT_WORKSTREAM_FILTER)

    solvd = apply_company_intent_overrides(
        live[STRIDE_REVENUE_TYPE_INTENT_ID], company_name="Solvd"
    )
    assert solvd is live[STRIDE_REVENUE_TYPE_INTENT_ID]
    assert solvd.query == SHARED_REVENUE_TYPE_QUERY
    cs = apply_company_intent_overrides(
        live[STRIDE_REVENUE_TYPE_INTENT_ID], company_name="Clearsulting"
    )
    assert cs is live[STRIDE_REVENUE_TYPE_INTENT_ID]


def test_stride_gets_kpi_dashboard_override_and_keeps_f1_f3_revenue_type():
    live = _by_id()
    dash = apply_company_intent_overrides(
        live[STRIDE_KPI_DASHBOARD_INTENT_ID], company_name="Stride"
    )
    assert dash is not live[STRIDE_KPI_DASHBOARD_INTENT_ID]
    assert dash.query == STRIDE_KPI_DASHBOARD_QUERY
    assert "Backlog & Pipeline 7.13" in dash.query
    assert "utilization" not in dash.query
    assert "Organizational" not in dash.query
    assert list(dash.file_name_filter) == list(STRIDE_KPI_DASHBOARD_FILE_NAME_FILTER)
    assert dash.file_name_filter == ["2.24"]
    assert dash.workstream_filter is None
    assert "Josie" not in (dash.file_name_filter or [])
    assert "KPI" not in dash.file_name_filter
    assert "Dashboard" not in dash.file_name_filter
    assert "Utilization" not in dash.file_name_filter
    assert "Organizational" not in dash.file_name_filter
    assert "Chart" not in dash.file_name_filter
    assert "Bill Rate" not in dash.file_name_filter
    assert live[STRIDE_KPI_DASHBOARD_INTENT_ID].query == SHARED_KPI_DASHBOARD_QUERY
    assert list(live[STRIDE_KPI_DASHBOARD_INTENT_ID].file_name_filter) == (
        SHARED_KPI_DASHBOARD_FILE_NAME_FILTER
    )
    assert list(live[STRIDE_KPI_DASHBOARD_INTENT_ID].workstream_filter) == (
        SHARED_KPI_DASHBOARD_WORKSTREAM_FILTER
    )

    # F1–F3 + revenue_type stay byte-identical to the closed overlay.
    conc = apply_company_intent_overrides(
        live[STRIDE_CONCENTRATION_INTENT_ID], company_name="Stride"
    )
    assert conc.query == STRIDE_CQA_QUERY
    assert list(conc.file_name_filter) == list(STRIDE_CQA_FILE_NAME_FILTER)
    assert list(conc.workstream_filter) == list(STRIDE_CONCENTRATION_WORKSTREAM_FILTER)
    health = apply_company_intent_overrides(
        live[STRIDE_HEALTH_INTENT_ID], company_name="Stride"
    )
    assert health.query == STRIDE_CQA_QUERY
    assert list(health.file_name_filter) == list(STRIDE_CQA_FILE_NAME_FILTER)
    q4 = apply_company_intent_overrides(
        live[STRIDE_Q4_FALLBACK_INTENT_ID], company_name="Stride"
    )
    assert q4.query == STRIDE_Q4_FALLBACK_QUERY
    assert list(q4.file_name_filter) == list(STRIDE_Q4_FALLBACK_FILE_NAME_FILTER)
    hc = apply_company_intent_overrides(
        live[STRIDE_HEADCOUNT_INTENT_ID], company_name="Stride"
    )
    assert hc.query == STRIDE_HEADCOUNT_QUERY
    assert list(hc.file_name_filter) == list(STRIDE_HEADCOUNT_FILE_NAME_FILTER)
    assert list(hc.workstream_filter) == list(STRIDE_HEADCOUNT_WORKSTREAM_FILTER)
    rev = apply_company_intent_overrides(
        live[STRIDE_REVENUE_TYPE_INTENT_ID], company_name="Stride"
    )
    assert rev.query == STRIDE_REVENUE_TYPE_QUERY
    assert list(rev.file_name_filter) == list(STRIDE_REVENUE_TYPE_FILE_NAME_FILTER)
    assert list(rev.workstream_filter) == list(STRIDE_REVENUE_TYPE_WORKSTREAM_FILTER)

    solvd = apply_company_intent_overrides(
        live[STRIDE_KPI_DASHBOARD_INTENT_ID], company_name="Solvd"
    )
    assert solvd is live[STRIDE_KPI_DASHBOARD_INTENT_ID]
    assert solvd.query == SHARED_KPI_DASHBOARD_QUERY
    cs = apply_company_intent_overrides(
        live[STRIDE_KPI_DASHBOARD_INTENT_ID], company_name="Clearsulting"
    )
    assert cs.query == CS_KPI_DASHBOARD_QUERY
    assert list(cs.file_name_filter) == list(CS_KPI_DASHBOARD_FILE_NAME_FILTER)
    assert "Organizational" in cs.file_name_filter
    assert "Chart" in cs.file_name_filter
    assert cs.query != STRIDE_KPI_DASHBOARD_QUERY


def test_project_sherpa_gets_sales_and_qofe_overrides():
    live = _by_id()
    sales = apply_company_intent_overrides(
        live[SHERPA_SALES_INTENT_ID], company_name="Project Sherpa"
    )
    assert sales.query == SHERPA_SALES_QUERY
    assert list(sales.file_name_filter) == list(SHERPA_SALES_FILE_NAME_FILTER)
    assert set(sales.file_name_filter) == {"Memorandum", "Confidential"}
    assert "GTM" not in sales.file_name_filter
    assert "Overview" not in sales.file_name_filter
    assert "CIM" not in sales.file_name_filter

    qofe = apply_company_intent_overrides(
        live[SHERPA_QOFE_INTENT_ID], company_name="Project Sherpa"
    )
    assert qofe.query == SHERPA_QOFE_QUERY
    assert list(qofe.file_name_filter) == list(SHERPA_QOFE_FILE_NAME_FILTER)
    assert list(qofe.workstream_filter) == list(SHERPA_QOFE_WORKSTREAM_FILTER)
    assert "FINANCIAL" in qofe.workstream_filter
    assert "Financial" in qofe.file_name_filter
    assert "Package" in qofe.file_name_filter
    assert live[SHERPA_QOFE_INTENT_ID].workstream_filter == SHARED_QOFE_WORKSTREAM_FILTER


def test_solvd_gets_q2_q3_and_cqa_overrides():
    live = _by_id()
    q2 = apply_company_intent_overrides(
        live[SOLVD_Q2_INTENT_ID], company_name="Solvd"
    )
    assert q2.query == SOLVD_Q2_QUERY
    assert list(q2.file_name_filter) == list(SOLVD_Q2_FILE_NAME_FILTER)
    assert "CIM" in q2.file_name_filter
    assert "FINANCIAL HIGHLIGHT" in q2.query
    assert "YE- December" in q2.query
    assert q2.top_k == live[SOLVD_Q2_INTENT_ID].top_k

    q3 = apply_company_intent_overrides(
        live[SOLVD_Q3_INTENT_ID], company_name="Solvd"
    )
    assert q3.query == SOLVD_Q3_QUERY
    assert list(q3.file_name_filter) == list(SOLVD_Q3_FILE_NAME_FILTER)
    assert "CIM" in q3.file_name_filter
    assert "Income Statement" in q3.query
    assert "CY22A" in q3.query
    assert "Booked Forecast" not in q3.query

    conc = apply_company_intent_overrides(
        live[SOLVD_CONCENTRATION_INTENT_ID], company_name="Solvd"
    )
    assert conc.query == SOLVD_CONCENTRATION_QUERY
    assert list(conc.workstream_filter) == list(SOLVD_CONCENTRATION_WORKSTREAM_FILTER)
    assert "BUSINESS_MODEL" in conc.workstream_filter
    assert "FINANCIAL" in conc.workstream_filter
    assert "CIM" in conc.file_name_filter
    assert conc.file_name_filter == SHARED_CONCENTRATION_FILE_NAME_FILTER
    assert "Key Highlight" in conc.query

    contract = apply_company_intent_overrides(
        live[SOLVD_CONTRACT_INTENT_ID], company_name="Solvd"
    )
    assert contract.query == SOLVD_CONTRACT_QUERY
    assert list(contract.file_name_filter) == list(SOLVD_CONTRACT_FILE_NAME_FILTER)
    assert list(contract.workstream_filter) == list(SOLVD_CONTRACT_WORKSTREAM_FILTER)
    assert contract.file_name_filter == ["CIM"]
    assert contract.workstream_filter == ["BUSINESS_MODEL"]
    assert "Revenue Retention" in contract.query
    assert {"Contract", "MSA", "Legal", "Customer"}.isdisjoint(contract.file_name_filter)


def test_solvd_gets_bma_trio_overrides():
    live = _by_id()
    vis = apply_company_intent_overrides(
        live[SOLVD_VISIBILITY_INTENT_ID], company_name="Solvd"
    )
    assert vis is not live[SOLVD_VISIBILITY_INTENT_ID]
    assert vis.query == SOLVD_VISIBILITY_QUERY
    assert list(vis.file_name_filter) == list(SOLVD_VISIBILITY_FILE_NAME_FILTER)
    assert vis.file_name_filter == ["CIM"]
    assert vis.workstream_filter is None
    assert "Revenue Retention" in vis.query
    assert "Managed Services Client" in vis.query
    assert "AI-Native Operating MODEL" in vis.query
    assert "Ajax" not in vis.query
    assert "24 schools" not in vis.query
    assert "86.6 million" not in vis.query
    assert "Pipeline" not in vis.file_name_filter
    assert live[SOLVD_VISIBILITY_INTENT_ID].query == SHARED_VISIBILITY_QUERY
    assert "Ajax" in live[SOLVD_VISIBILITY_INTENT_ID].query
    assert "24 schools" in live[SOLVD_VISIBILITY_INTENT_ID].query

    overview = apply_company_intent_overrides(
        live[SOLVD_OVERVIEW_INTENT_ID], company_name="Solvd"
    )
    assert overview is not live[SOLVD_OVERVIEW_INTENT_ID]
    assert overview.query == SOLVD_OVERVIEW_QUERY
    assert list(overview.file_name_filter) == list(SOLVD_OVERVIEW_FILE_NAME_FILTER)
    assert overview.file_name_filter == ["CIM"]
    assert overview.workstream_filter is None
    assert "Subscription-First Economic" in overview.query
    assert "BUSINESS_MODEL" not in (overview.workstream_filter or [])
    assert "Offering" not in overview.file_name_filter
    assert live[SOLVD_OVERVIEW_INTENT_ID].query == SHARED_OVERVIEW_QUERY
    assert list(live[SOLVD_OVERVIEW_INTENT_ID].workstream_filter) == (
        SHARED_OVERVIEW_WORKSTREAM_FILTER
    )

    model = apply_company_intent_overrides(
        live[SOLVD_MODEL_CHANGES_INTENT_ID], company_name="Solvd"
    )
    assert model is not live[SOLVD_MODEL_CHANGES_INTENT_ID]
    assert model.query == SOLVD_MODEL_CHANGES_QUERY
    assert list(model.file_name_filter) == list(SOLVD_MODEL_CHANGES_FILE_NAME_FILTER)
    assert model.file_name_filter == ["CIM"]
    assert model.workstream_filter is None
    assert "AI-Native Operating MODEL" in model.query
    assert "Executive Leadership" in model.query
    assert "Ajax" not in model.query
    assert live[SOLVD_MODEL_CHANGES_INTENT_ID].query == SHARED_MODEL_CHANGES_QUERY
    assert list(live[SOLVD_MODEL_CHANGES_INTENT_ID].workstream_filter) == (
        SHARED_MODEL_CHANGES_WORKSTREAM_FILTER
    )

    q2 = apply_company_intent_overrides(
        live[SOLVD_Q2_INTENT_ID], company_name="Solvd"
    )
    assert q2.query == SOLVD_Q2_QUERY
    assert list(q2.file_name_filter) == list(SOLVD_Q2_FILE_NAME_FILTER)
    q3 = apply_company_intent_overrides(
        live[SOLVD_Q3_INTENT_ID], company_name="Solvd"
    )
    assert q3.query == SOLVD_Q3_QUERY
    conc = apply_company_intent_overrides(
        live[SOLVD_CONCENTRATION_INTENT_ID], company_name="Solvd"
    )
    assert conc.query == SOLVD_CONCENTRATION_QUERY
    contract = apply_company_intent_overrides(
        live[SOLVD_CONTRACT_INTENT_ID], company_name="Solvd"
    )
    assert contract.query == SOLVD_CONTRACT_QUERY
    assert list(contract.workstream_filter) == list(SOLVD_CONTRACT_WORKSTREAM_FILTER)


def test_incumbents_keep_shared_or_landed_not_w3_overrides():
    live = _by_id()
    for company in INCUMBENT_COMPANIES:
        people = apply_company_intent_overrides(
            live[INF_PEOPLE_INTENT_ID], company_name=company
        )
        assert people is live[INF_PEOPLE_INTENT_ID]
        assert people.query == SHARED_PEOPLE_QUERY
        assert list(people.workstream_filter) == SHARED_PEOPLE_WORKSTREAM_FILTER

        overview = apply_company_intent_overrides(
            live[INF_OVERVIEW_INTENT_ID], company_name=company
        )
        assert overview is live[INF_OVERVIEW_INTENT_ID]
        assert overview.query == SHARED_OVERVIEW_QUERY
        assert list(overview.workstream_filter) == SHARED_OVERVIEW_WORKSTREAM_FILTER

        qofe = apply_company_intent_overrides(
            live[SHERPA_QOFE_INTENT_ID], company_name=company
        )
        assert qofe is live[SHERPA_QOFE_INTENT_ID]
        assert qofe.query == SHARED_QOFE_QUERY

        q2 = apply_company_intent_overrides(
            live[SOLVD_Q2_INTENT_ID], company_name=company
        )
        assert q2 is live[SOLVD_Q2_INTENT_ID]
        assert q2.query == SHARED_Q2_QUERY

        contract = apply_company_intent_overrides(
            live[SOLVD_CONTRACT_INTENT_ID], company_name=company
        )
        assert contract is live[SOLVD_CONTRACT_INTENT_ID]
        assert contract.query == SHARED_CONTRACT_QUERY

        headcount = apply_company_intent_overrides(
            live[IR_HEADCOUNT_INTENT_ID], company_name=company
        )
        assert headcount is live[IR_HEADCOUNT_INTENT_ID]
        assert headcount.query == SHARED_HEADCOUNT_QUERY


def test_clearsulting_gkf_ec_landed_branches_stay_intact():
    live = _by_id()
    vis = apply_company_intent_overrides(
        live[CS_VISIBILITY_INTENT_ID], company_name="Clearsulting"
    )
    assert vis.query == CS_VISIBILITY_QUERY
    assert list(vis.file_name_filter) == list(CS_VISIBILITY_FILE_NAME_FILTER)
    bench = apply_company_intent_overrides(
        live[CS_BENCH_INTENT_ID], company_name="Clearsulting"
    )
    assert bench.query == CS_BENCH_QUERY
    assert list(bench.file_name_filter) == list(CS_BENCH_FILE_NAME_FILTER)
    loc = apply_company_intent_overrides(
        live[CS_LOCATION_INTENT_ID], company_name="Clearsulting"
    )
    assert loc.query == CS_LOCATION_QUERY
    assert list(loc.file_name_filter) == list(CS_LOCATION_FILE_NAME_FILTER)
    q4 = apply_company_intent_overrides(
        live[CS_Q4_FALLBACK_INTENT_ID], company_name="Clearsulting"
    )
    assert q4.query == CS_Q4_FALLBACK_QUERY
    assert list(q4.file_name_filter) == list(CS_Q4_FALLBACK_FILE_NAME_FILTER)
    acct = apply_company_intent_overrides(
        live[CS_ACCOUNT_SIZE_INTENT_ID], company_name="Clearsulting"
    )
    assert acct.query == CS_ACCOUNT_SIZE_QUERY
    assert list(acct.file_name_filter) == list(CS_ACCOUNT_SIZE_FILE_NAME_FILTER)
    dash = apply_company_intent_overrides(
        live[CS_KPI_DASHBOARD_INTENT_ID], company_name="Clearsulting"
    )
    assert dash.query == CS_KPI_DASHBOARD_QUERY
    assert list(dash.file_name_filter) == list(CS_KPI_DASHBOARD_FILE_NAME_FILTER)

    gkf = apply_company_intent_overrides(
        live[GKF_LOCATION_INTENT_ID], company_name="GKF"
    )
    assert gkf.query == GKF_LOCATION_QUERY
    assert list(gkf.file_name_filter) == list(GKF_LOCATION_FILE_NAME_FILTER)
    assert gkf.query != IR_LOCATION_QUERY

    cim = apply_company_intent_overrides(
        live[EC_CIM_PRESENCE_INTENT_ID], company_name="Elder Care"
    )
    assert cim.query == EC_CIM_PRESENCE_QUERY
    assert list(cim.file_name_filter) == list(EC_CIM_PRESENCE_FILE_NAME_FILTER)
    contracts = apply_company_intent_overrides(
        live[EC_CONTRACTS_INTENT_ID], company_name="Elder Care"
    )
    assert contracts.query == EC_CONTRACTS_QUERY
    assert list(contracts.file_name_filter) == list(EC_CONTRACTS_FILE_NAME_FILTER)


def test_w3_companies_do_not_take_cs_gkf_ec_leftover_branches():
    live = _by_id()
    for company in W3_COMPANIES:
        acct = apply_company_intent_overrides(
            live[CS_ACCOUNT_SIZE_INTENT_ID], company_name=company
        )
        if company == "Integrity Risk":
            assert acct.query == IR_ACCOUNT_SIZE_QUERY
            assert list(acct.file_name_filter) == list(IR_ACCOUNT_SIZE_FILE_NAME_FILTER)
            assert acct.query != CS_ACCOUNT_SIZE_QUERY
        else:
            assert acct is live[CS_ACCOUNT_SIZE_INTENT_ID]
        dash = apply_company_intent_overrides(
            live[CS_KPI_DASHBOARD_INTENT_ID], company_name=company
        )
        if company == "Stride":
            assert dash.query == STRIDE_KPI_DASHBOARD_QUERY
            assert list(dash.file_name_filter) == list(STRIDE_KPI_DASHBOARD_FILE_NAME_FILTER)
            assert dash.workstream_filter is None
            assert dash.query != CS_KPI_DASHBOARD_QUERY
            assert "Organizational" not in dash.query
            assert list(dash.file_name_filter) != list(CS_KPI_DASHBOARD_FILE_NAME_FILTER)
        else:
            assert dash is live[CS_KPI_DASHBOARD_INTENT_ID]
        cim = apply_company_intent_overrides(
            live[EC_CIM_PRESENCE_INTENT_ID], company_name=company
        )
        assert cim is live[EC_CIM_PRESENCE_INTENT_ID]
        contracts = apply_company_intent_overrides(
            live[EC_CONTRACTS_INTENT_ID], company_name=company
        )
        assert contracts is live[EC_CONTRACTS_INTENT_ID]


def test_visibility_location_q4_are_slug_isolated():
    live = _by_id()
    vis_intent = live[CS_VISIBILITY_INTENT_ID]
    inf = apply_company_intent_overrides(vis_intent, company_name="Infinitive")
    nb = apply_company_intent_overrides(vis_intent, company_name="Northbound")
    cs = apply_company_intent_overrides(vis_intent, company_name="Clearsulting")
    solvd = apply_company_intent_overrides(vis_intent, company_name="Solvd")
    spg = apply_company_intent_overrides(vis_intent, company_name="SPG")
    assert inf.query == INF_VISIBILITY_QUERY
    assert nb.query == NB_VISIBILITY_QUERY
    assert cs.query == CS_VISIBILITY_QUERY
    assert solvd.query == SOLVD_VISIBILITY_QUERY
    assert solvd.workstream_filter is None
    assert spg is vis_intent
    assert inf.query != cs.query != nb.query != solvd.query

    loc_intent = live[CS_LOCATION_INTENT_ID]
    ir = apply_company_intent_overrides(loc_intent, company_name="Integrity Risk")
    gkf = apply_company_intent_overrides(loc_intent, company_name="GKF")
    cs_loc = apply_company_intent_overrides(loc_intent, company_name="Clearsulting")
    assert ir.query == IR_LOCATION_QUERY
    assert gkf.query == GKF_LOCATION_QUERY
    assert cs_loc.query == CS_LOCATION_QUERY
    assert ir.file_name_filter == ["Cube"]
    assert "Memorandum" in cs_loc.file_name_filter
    assert "Ajax" in gkf.file_name_filter

    q4_intent = live[CS_Q4_FALLBACK_INTENT_ID]
    stride = apply_company_intent_overrides(q4_intent, company_name="Stride")
    cs_q4 = apply_company_intent_overrides(q4_intent, company_name="Clearsulting")
    gkf_q4 = apply_company_intent_overrides(q4_intent, company_name="GKF")
    assert stride.query == STRIDE_Q4_FALLBACK_QUERY
    assert list(stride.file_name_filter) == list(STRIDE_Q4_FALLBACK_FILE_NAME_FILTER)
    assert cs_q4.query == CS_Q4_FALLBACK_QUERY
    assert list(cs_q4.file_name_filter) == list(CS_Q4_FALLBACK_FILE_NAME_FILTER)
    assert gkf_q4 is q4_intent


def test_build_search_kwargs_applies_each_w3_slug():
    live = _by_id()
    cases = (
        ("Infinitive", INF_VISIBILITY_INTENT_ID, INF_VISIBILITY_QUERY, list(INF_VISIBILITY_FILE_NAME_FILTER)),
        ("Infinitive", INF_OVERVIEW_INTENT_ID, INF_OVERVIEW_QUERY, list(INF_OVERVIEW_FILE_NAME_FILTER)),
        ("Integrity Risk", IR_LOCATION_INTENT_ID, IR_LOCATION_QUERY, list(IR_LOCATION_FILE_NAME_FILTER)),
        ("Integrity Risk", IR_BENCH_INTENT_ID, IR_BENCH_QUERY, list(IR_BENCH_FILE_NAME_FILTER)),
        ("Integrity Risk", IR_ACCOUNT_SIZE_INTENT_ID, IR_ACCOUNT_SIZE_QUERY, list(IR_ACCOUNT_SIZE_FILE_NAME_FILTER)),
        ("Northbound", NB_Q3_INTENT_ID, NB_Q3_QUERY, list(NB_Q3_FILE_NAME_FILTER)),
        ("Stride", STRIDE_CONCENTRATION_INTENT_ID, STRIDE_CQA_QUERY, list(STRIDE_CQA_FILE_NAME_FILTER)),
        ("Stride", STRIDE_REVENUE_TYPE_INTENT_ID, STRIDE_REVENUE_TYPE_QUERY, list(STRIDE_REVENUE_TYPE_FILE_NAME_FILTER)),
        ("Stride", STRIDE_KPI_DASHBOARD_INTENT_ID, STRIDE_KPI_DASHBOARD_QUERY, list(STRIDE_KPI_DASHBOARD_FILE_NAME_FILTER)),
        ("Project Sherpa", SHERPA_SALES_INTENT_ID, SHERPA_SALES_QUERY, list(SHERPA_SALES_FILE_NAME_FILTER)),
        ("Solvd", SOLVD_Q2_INTENT_ID, SOLVD_Q2_QUERY, list(SOLVD_Q2_FILE_NAME_FILTER)),
        ("Solvd", SOLVD_VISIBILITY_INTENT_ID, SOLVD_VISIBILITY_QUERY, list(SOLVD_VISIBILITY_FILE_NAME_FILTER)),
        ("Solvd", SOLVD_OVERVIEW_INTENT_ID, SOLVD_OVERVIEW_QUERY, list(SOLVD_OVERVIEW_FILE_NAME_FILTER)),
        ("Solvd", SOLVD_MODEL_CHANGES_INTENT_ID, SOLVD_MODEL_CHANGES_QUERY, list(SOLVD_MODEL_CHANGES_FILE_NAME_FILTER)),
    )
    for company, intent_id, query, file_filter in cases:
        intent = live[intent_id]
        kwargs = build_search_kwargs(intent, company_name=company, spark=object())
        assert kwargs["query"] == query
        assert kwargs["file_name_filter"] == file_filter
        if company == "Infinitive" and intent_id == INF_OVERVIEW_INTENT_ID:
            assert kwargs["workstream_filter"] is None
        if company == "Stride" and intent_id == STRIDE_REVENUE_TYPE_INTENT_ID:
            assert kwargs["workstream_filter"] == list(STRIDE_REVENUE_TYPE_WORKSTREAM_FILTER)
        if company == "Stride" and intent_id == STRIDE_KPI_DASHBOARD_INTENT_ID:
            assert kwargs["workstream_filter"] is None
        if company == "Solvd" and intent_id in {
            SOLVD_VISIBILITY_INTENT_ID,
            SOLVD_OVERVIEW_INTENT_ID,
            SOLVD_MODEL_CHANGES_INTENT_ID,
        }:
            assert kwargs["workstream_filter"] is None
        fallback = _fallback_kwargs_from_intent(
            intent, company_name=company, spark=object()
        )
        assert fallback["query"] == query
        assert fallback["file_name_filter"] == file_filter


def test_w3_siblings_do_not_take_ir_bench_account_or_inf_people():
    live = _by_id()
    for company in ("Northbound", "Stride", "Project Sherpa", "Solvd", "SPG"):
        people = apply_company_intent_overrides(
            live[INF_PEOPLE_INTENT_ID], company_name=company
        )
        assert people is live[INF_PEOPLE_INTENT_ID]
        assert list(people.workstream_filter) == SHARED_PEOPLE_WORKSTREAM_FILTER
        overview = apply_company_intent_overrides(
            live[INF_OVERVIEW_INTENT_ID], company_name=company
        )
        if company == "Solvd":
            assert overview.query == SOLVD_OVERVIEW_QUERY
            assert overview.workstream_filter is None
            assert list(overview.file_name_filter) == list(SOLVD_OVERVIEW_FILE_NAME_FILTER)
        else:
            assert overview is live[INF_OVERVIEW_INTENT_ID]
            assert overview.query == SHARED_OVERVIEW_QUERY
            assert list(overview.workstream_filter) == SHARED_OVERVIEW_WORKSTREAM_FILTER
        bench = apply_company_intent_overrides(
            live[IR_BENCH_INTENT_ID], company_name=company
        )
        assert bench is live[IR_BENCH_INTENT_ID]
        assert bench.query == SHARED_BENCH_QUERY
        acct = apply_company_intent_overrides(
            live[IR_ACCOUNT_SIZE_INTENT_ID], company_name=company
        )
        assert acct is live[IR_ACCOUNT_SIZE_INTENT_ID]
        assert acct.query == SHARED_ACCOUNT_SIZE_QUERY


@patch("agents.shared.fallback.semantic_search_with_fallback")
@patch("agents.shared.retrieval.semantic_search")
def test_dispatch_infinitive_visibility_sends_override_query(mock_semantic, mock_fallback):
    mock_fallback.return_value = (MagicMock(chunks=["hit"], mode="semantic"), False)
    live = _by_id()
    dispatch_retrieval(
        live[INF_VISIBILITY_INTENT_ID],
        company_name="Infinitive",
        spark=MagicMock(),
    )
    assert mock_fallback.call_args.kwargs["query"] == INF_VISIBILITY_QUERY
    assert mock_fallback.call_args.kwargs["file_name_filter"] == list(
        INF_VISIBILITY_FILE_NAME_FILTER
    )
    mock_semantic.assert_not_called()


@patch("agents.shared.fallback.semantic_search_with_fallback")
@patch("agents.shared.retrieval.semantic_search")
def test_dispatch_solvd_contract_sends_override_query(mock_semantic, mock_fallback):
    mock_fallback.return_value = (MagicMock(chunks=["hit"], mode="semantic"), False)
    live = _by_id()
    dispatch_retrieval(
        live[SOLVD_CONTRACT_INTENT_ID],
        company_name="Solvd",
        spark=MagicMock(),
    )
    assert mock_fallback.call_args.kwargs["query"] == SOLVD_CONTRACT_QUERY
    assert mock_fallback.call_args.kwargs["file_name_filter"] == list(
        SOLVD_CONTRACT_FILE_NAME_FILTER
    )
    assert mock_fallback.call_args.kwargs["workstream_filter"] == list(
        SOLVD_CONTRACT_WORKSTREAM_FILTER
    )
    mock_semantic.assert_not_called()


@patch("agents.shared.fallback.semantic_search_with_fallback")
@patch("agents.shared.retrieval.semantic_search")
def test_dispatch_spg_visibility_keeps_shared_query(mock_semantic, mock_fallback):
    mock_fallback.return_value = (MagicMock(chunks=["hit"], mode="semantic"), False)
    live = _by_id()
    dispatch_retrieval(
        live[INF_VISIBILITY_INTENT_ID],
        company_name="SPG",
        spark=MagicMock(),
    )
    assert mock_fallback.call_args.kwargs["query"] == SHARED_VISIBILITY_QUERY
    assert mock_fallback.call_args.kwargs["file_name_filter"] == (
        SHARED_VISIBILITY_FILE_NAME_FILTER
    )
    mock_semantic.assert_not_called()


@patch("agents.shared.fallback.semantic_search_with_fallback")
@patch("agents.shared.retrieval.semantic_search")
def test_dispatch_infinitive_overview_uses_tm_not_unfiltered(
    mock_semantic, mock_fallback
):
    mock_semantic.return_value = MagicMock(chunks=["tm-hit"], mode="semantic")
    live = _by_id()
    dispatch_retrieval(
        live[INF_OVERVIEW_INTENT_ID],
        company_name="Infinitive",
        spark=MagicMock(),
    )
    assert mock_semantic.call_count == 1
    assert mock_semantic.call_args.kwargs["query"] == INF_OVERVIEW_QUERY
    assert mock_semantic.call_args.kwargs["file_name_filter"] == list(
        INF_OVERVIEW_FILE_NAME_FILTER
    )
    assert mock_semantic.call_args.kwargs["workstream_filter"] is None
    mock_fallback.assert_not_called()


@patch("agents.shared.fallback.semantic_search_with_fallback")
@patch("agents.shared.retrieval.semantic_search")
def test_dispatch_infinitive_overview_empty_tm_retries_fixed_fee(
    mock_semantic, mock_fallback
):
    empty = MagicMock(chunks=[], mode="empty")
    filled = MagicMock(chunks=["ff-hit"], mode="semantic")
    mock_semantic.side_effect = [empty, filled]
    live = _by_id()
    result = dispatch_retrieval(
        live[INF_OVERVIEW_INTENT_ID],
        company_name="Infinitive",
        spark=MagicMock(),
    )
    assert result is filled
    assert mock_semantic.call_count == 2
    first = mock_semantic.call_args_list[0].kwargs
    second = mock_semantic.call_args_list[1].kwargs
    assert first["file_name_filter"] == list(INF_OVERVIEW_FILE_NAME_FILTER)
    assert second["file_name_filter"] == list(INF_OVERVIEW_FILE_NAME_FILTER_FALLBACK)
    assert first["workstream_filter"] is None
    assert second["workstream_filter"] is None
    assert first["file_name_filter"] != [None]
    assert second["file_name_filter"] is not None
    mock_fallback.assert_not_called()


@patch("agents.shared.fallback.semantic_search_with_fallback")
@patch("agents.shared.retrieval.semantic_search")
def test_dispatch_stride_revenue_type_uses_12_1_not_unfiltered(
    mock_semantic, mock_fallback
):
    mock_semantic.return_value = MagicMock(chunks=["deck-hit"], mode="semantic")
    live = _by_id()
    dispatch_retrieval(
        live[STRIDE_REVENUE_TYPE_INTENT_ID],
        company_name="Stride",
        spark=MagicMock(),
    )
    assert mock_semantic.call_count == 1
    assert mock_semantic.call_args.kwargs["query"] == STRIDE_REVENUE_TYPE_QUERY
    assert mock_semantic.call_args.kwargs["file_name_filter"] == list(
        STRIDE_REVENUE_TYPE_FILE_NAME_FILTER
    )
    assert mock_semantic.call_args.kwargs["workstream_filter"] == list(
        STRIDE_REVENUE_TYPE_WORKSTREAM_FILTER
    )
    mock_fallback.assert_not_called()


@patch("agents.shared.fallback.semantic_search_with_fallback")
@patch("agents.shared.retrieval.semantic_search")
def test_dispatch_stride_revenue_type_empty_12_1_retries_presentation(
    mock_semantic, mock_fallback
):
    empty = MagicMock(chunks=[], mode="empty")
    filled = MagicMock(chunks=["pres-hit"], mode="semantic")
    mock_semantic.side_effect = [empty, filled]
    live = _by_id()
    result = dispatch_retrieval(
        live[STRIDE_REVENUE_TYPE_INTENT_ID],
        company_name="Stride",
        spark=MagicMock(),
    )
    assert result is filled
    assert mock_semantic.call_count == 2
    first = mock_semantic.call_args_list[0].kwargs
    second = mock_semantic.call_args_list[1].kwargs
    assert first["file_name_filter"] == list(STRIDE_REVENUE_TYPE_FILE_NAME_FILTER)
    assert second["file_name_filter"] == list(
        STRIDE_REVENUE_TYPE_FILE_NAME_FILTER_FALLBACK
    )
    assert first["workstream_filter"] == list(STRIDE_REVENUE_TYPE_WORKSTREAM_FILTER)
    assert second["workstream_filter"] == list(STRIDE_REVENUE_TYPE_WORKSTREAM_FILTER)
    assert first["file_name_filter"] != [None]
    assert second["file_name_filter"] is not None
    mock_fallback.assert_not_called()


@patch("agents.shared.fallback.semantic_search_with_fallback")
@patch("agents.shared.retrieval.semantic_search")
def test_dispatch_stride_kpi_dashboard_uses_2_24_not_unfiltered(
    mock_semantic, mock_fallback
):
    mock_semantic.return_value = MagicMock(chunks=["backlog-hit"], mode="semantic")
    live = _by_id()
    dispatch_retrieval(
        live[STRIDE_KPI_DASHBOARD_INTENT_ID],
        company_name="Stride",
        spark=MagicMock(),
    )
    assert mock_semantic.call_count == 1
    assert mock_semantic.call_args.kwargs["query"] == STRIDE_KPI_DASHBOARD_QUERY
    assert mock_semantic.call_args.kwargs["file_name_filter"] == list(
        STRIDE_KPI_DASHBOARD_FILE_NAME_FILTER
    )
    assert mock_semantic.call_args.kwargs["workstream_filter"] is None
    mock_fallback.assert_not_called()


@patch("agents.shared.fallback.semantic_search_with_fallback")
@patch("agents.shared.retrieval.semantic_search")
def test_dispatch_stride_kpi_dashboard_empty_2_24_retries_pipeline(
    mock_semantic, mock_fallback
):
    empty = MagicMock(chunks=[], mode="empty")
    filled = MagicMock(chunks=["pipe-hit"], mode="semantic")
    mock_semantic.side_effect = [empty, filled]
    live = _by_id()
    result = dispatch_retrieval(
        live[STRIDE_KPI_DASHBOARD_INTENT_ID],
        company_name="Stride",
        spark=MagicMock(),
    )
    assert result is filled
    assert mock_semantic.call_count == 2
    first = mock_semantic.call_args_list[0].kwargs
    second = mock_semantic.call_args_list[1].kwargs
    assert first["file_name_filter"] == list(STRIDE_KPI_DASHBOARD_FILE_NAME_FILTER)
    assert second["file_name_filter"] == list(
        STRIDE_KPI_DASHBOARD_FILE_NAME_FILTER_FALLBACK
    )
    assert first["workstream_filter"] is None
    assert second["workstream_filter"] is None
    assert first["file_name_filter"] != [None]
    assert second["file_name_filter"] is not None
    mock_fallback.assert_not_called()


@patch("agents.shared.fallback.semantic_search_with_fallback")
@patch("agents.shared.retrieval.semantic_search")
def test_dispatch_solvd_kpi_dashboard_keeps_shared_query(mock_semantic, mock_fallback):
    mock_fallback.return_value = (MagicMock(chunks=["hit"], mode="semantic"), False)
    live = _by_id()
    dispatch_retrieval(
        live[STRIDE_KPI_DASHBOARD_INTENT_ID],
        company_name="Solvd",
        spark=MagicMock(),
    )
    assert mock_fallback.call_args.kwargs["query"] == SHARED_KPI_DASHBOARD_QUERY
    assert mock_fallback.call_args.kwargs["file_name_filter"] == (
        SHARED_KPI_DASHBOARD_FILE_NAME_FILTER
    )
    assert mock_fallback.call_args.kwargs["workstream_filter"] == (
        SHARED_KPI_DASHBOARD_WORKSTREAM_FILTER
    )
    mock_semantic.assert_not_called()


@patch("agents.shared.fallback.semantic_search_with_fallback")
@patch("agents.shared.retrieval.semantic_search")
def test_dispatch_solvd_revenue_type_keeps_shared_query(mock_semantic, mock_fallback):
    mock_fallback.return_value = (MagicMock(chunks=["hit"], mode="semantic"), False)
    live = _by_id()
    dispatch_retrieval(
        live[STRIDE_REVENUE_TYPE_INTENT_ID],
        company_name="Solvd",
        spark=MagicMock(),
    )
    assert mock_fallback.call_args.kwargs["query"] == SHARED_REVENUE_TYPE_QUERY
    assert mock_fallback.call_args.kwargs["file_name_filter"] == (
        SHARED_REVENUE_TYPE_FILE_NAME_FILTER
    )
    assert mock_fallback.call_args.kwargs["workstream_filter"] == (
        SHARED_REVENUE_TYPE_WORKSTREAM_FILTER
    )
    mock_semantic.assert_not_called()


@patch("agents.shared.fallback.semantic_search_with_fallback")
@patch("agents.shared.retrieval.semantic_search")
def test_dispatch_spg_overview_keeps_shared_query(mock_semantic, mock_fallback):
    mock_fallback.return_value = (MagicMock(chunks=["hit"], mode="semantic"), False)
    live = _by_id()
    dispatch_retrieval(
        live[INF_OVERVIEW_INTENT_ID],
        company_name="SPG",
        spark=MagicMock(),
    )
    assert mock_fallback.call_args.kwargs["query"] == SHARED_OVERVIEW_QUERY
    assert mock_fallback.call_args.kwargs["file_name_filter"] == (
        SHARED_OVERVIEW_FILE_NAME_FILTER
    )
    assert mock_fallback.call_args.kwargs["workstream_filter"] == (
        SHARED_OVERVIEW_WORKSTREAM_FILTER
    )
    mock_semantic.assert_not_called()


@patch("agents.shared.fallback.semantic_search_with_fallback")
@patch("agents.shared.retrieval.semantic_search")
def test_dispatch_solvd_bma_trio_uses_cim_not_unfiltered(mock_semantic, mock_fallback):
    mock_semantic.return_value = MagicMock(chunks=["cim-hit"], mode="semantic")
    live = _by_id()
    cases = (
        (SOLVD_VISIBILITY_INTENT_ID, SOLVD_VISIBILITY_QUERY, list(SOLVD_VISIBILITY_FILE_NAME_FILTER)),
        (SOLVD_OVERVIEW_INTENT_ID, SOLVD_OVERVIEW_QUERY, list(SOLVD_OVERVIEW_FILE_NAME_FILTER)),
        (SOLVD_MODEL_CHANGES_INTENT_ID, SOLVD_MODEL_CHANGES_QUERY, list(SOLVD_MODEL_CHANGES_FILE_NAME_FILTER)),
    )
    for intent_id, query, file_filter in cases:
        mock_semantic.reset_mock()
        mock_fallback.reset_mock()
        dispatch_retrieval(live[intent_id], company_name="Solvd", spark=MagicMock())
        assert mock_semantic.call_count == 1
        assert mock_semantic.call_args.kwargs["query"] == query
        assert mock_semantic.call_args.kwargs["file_name_filter"] == file_filter
        assert mock_semantic.call_args.kwargs["workstream_filter"] is None
        assert mock_semantic.call_args.kwargs["file_name_filter"] != [None]
        mock_fallback.assert_not_called()


@patch("agents.shared.fallback.semantic_search_with_fallback")
@patch("agents.shared.retrieval.semantic_search")
def test_dispatch_solvd_bma_trio_empty_cim_does_not_drop_filename(
    mock_semantic, mock_fallback
):
    mock_semantic.return_value = MagicMock(chunks=[], mode="empty")
    live = _by_id()
    result = dispatch_retrieval(
        live[SOLVD_VISIBILITY_INTENT_ID],
        company_name="Solvd",
        spark=MagicMock(),
    )
    assert result.chunks == []
    assert mock_semantic.call_count == 1
    assert mock_semantic.call_args.kwargs["file_name_filter"] == list(
        SOLVD_VISIBILITY_FILE_NAME_FILTER
    )
    assert mock_semantic.call_args.kwargs["workstream_filter"] is None
    mock_fallback.assert_not_called()


@patch("agents.shared.fallback.semantic_search_with_fallback")
@patch("agents.shared.retrieval.semantic_search")
def test_dispatch_spg_model_changes_keeps_shared_query(mock_semantic, mock_fallback):
    mock_fallback.return_value = (MagicMock(chunks=["hit"], mode="semantic"), False)
    live = _by_id()
    dispatch_retrieval(
        live[SOLVD_MODEL_CHANGES_INTENT_ID],
        company_name="SPG",
        spark=MagicMock(),
    )
    assert mock_fallback.call_args.kwargs["query"] == SHARED_MODEL_CHANGES_QUERY
    assert mock_fallback.call_args.kwargs["file_name_filter"] == (
        SHARED_MODEL_CHANGES_FILE_NAME_FILTER
    )
    assert mock_fallback.call_args.kwargs["workstream_filter"] == (
        SHARED_MODEL_CHANGES_WORKSTREAM_FILTER
    )
    mock_semantic.assert_not_called()
