"""Lockstep GKF leftover-zero query rewrites (cycle 14 / P3).

Gold is embedded; pin `baseline_8d8d8620bfaa` misses the bag because the
shared registry/producer strings target the wrong lexical neighborhood.
These four strings must stay identical in intent_registry.yaml and the
producer call sites.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from eval.retrieval.registry_extractor import IntentRegistryExtractor

REPO_ROOT = Path(__file__).resolve().parents[3]
REGISTRY_PATH = REPO_ROOT / "eval" / "retrieval" / "intent_registry.yaml"

LOCATION_QUERY = (
    "clients served active accounts customers by location by market by segment "
    "billed hours per client revenue per customer revenue per account "
    "utilization per customer sessions per user visits per patient "
    "customer count trend quarterly growth by location by geography "
    "length of stay customer tenure distribution cohort by duration "
    "revenue per location revenue by market adjusted revenue by geography "
    "revenue CAGR financial highlights headline metrics acquisition pipeline "
    "same store revenue organic growth by market revenue goal by location "
    "Shared Practices Dashboard new patient visits distribution within my network locations "
    "Corporate Organization Current State leadership team DMV Mike Pesi CEO "
    "Ross Flax Ellicott City Academic Director Teachers and Staff"
)
# NOTE (cycle 14 gate-2 reconciliation): this intent's producer method
# (`_tool_retrieve_revenue_by_location_and_metrics` in business_model_agent.py)
# is NOT company-scoped -- it is the same query for every company. P3 (GKF,
# this file) and P4 (SPG, test_spg_revenue_dashboard_query_append.py) both
# targeted it in cycle 14 with mutually exclusive edits (replace vs append).
# Reconciled by the meta orchestrator into one additive merged query so both
# companies' gains survive. See runs/ledger.md cycle-14 process/CRITICAL entries.
VISIBILITY_QUERY = (
    "Clear Strategic Roadmap of Growth Opportunities Project Ajax revenue target "
    "86.6 million 2030 24 schools historical projected revenue PF Adj EBITDA School "
    "Financial Performance BALANCE SHEET SUMMARY"
)
Q4_QUERY = (
    "Project Ajax Financial Due Diligence Databook Location Analysis Revenue "
    "Detail Combined FY23 tuition by school enrollment"
)
KPI_QUERY = (
    "Employee Retention Analysis Staff beginning of Year Hires Terminations Staff "
    "at End of Year Employee Count Payroll Build Project Ajax Model vE"
)

Q4_ADDED_FILTER_TOKENS = ("Databook", "CIM", "Ajax", "Model")
Q4_KEPT_FILTER_TOKENS = (
    "Customer",
    "QuickBooks",
    "QBO",
    "Sales",
    "Concentration",
    "Client",
    "Payor",
    "Revenue",
)

NAMED = {
    "bma.retrieve_revenue_by_location_and_metrics": LOCATION_QUERY,
    "bma.retrieve_revenue_visibility": VISIBILITY_QUERY,
    "fta.revenue.q4_customer_concentration_fallback": Q4_QUERY,
    "kpi.retrieve_headcount_attrition": KPI_QUERY,
}


def _by_id():
    extractor = IntentRegistryExtractor(REPO_ROOT)
    return {intent.intent_id: intent for intent in extractor.extract()}


def _committed_by_id():
    rows = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    return {row["intent_id"]: row for row in rows}


def test_gkf_leftover_zero_queries_match_registry_and_producer():
    live = _by_id()
    committed = _committed_by_id()
    for intent_id, expected in NAMED.items():
        assert live[intent_id].query == expected, intent_id
        assert committed[intent_id]["query"] == expected, intent_id


def test_gkf_q4_file_name_filter_adds_gold_filename_tokens():
    live = _by_id()
    committed = _committed_by_id()
    live_filter = list(live["fta.revenue.q4_customer_concentration_fallback"].file_name_filter)
    committed_filter = list(committed["fta.revenue.q4_customer_concentration_fallback"]["file_name_filter"])
    assert live_filter == committed_filter
    for token in Q4_KEPT_FILTER_TOKENS:
        assert token in live_filter, token
    for token in Q4_ADDED_FILTER_TOKENS:
        assert token in live_filter, token
    assert "Databook" not in list(
        live["kpi.retrieve_headcount_attrition"].file_name_filter or []
    )


def test_gkf_location_query_is_org_chart_not_healthcare_overlay():
    # Cycle-14 reconciliation: this shared query is additive across GKF (org
    # chart tokens) and SPG (dashboard tokens) since the producer method is
    # not company-scoped. Assert GKF's tokens are present -- do not assert
    # exclusivity of SPG's tokens (that assumption no longer holds).
    live = _by_id()
    query = live["bma.retrieve_revenue_by_location_and_metrics"].query
    assert "Mike Pesi" in query
    assert "Corporate Organization Current State" in query


def test_gkf_visibility_query_drops_msa_sow_backlog():
    live = _by_id()
    query = live["bma.retrieve_revenue_visibility"].query
    assert "86.6 million" in query
    assert "MSA" not in query
    assert "SOW" not in query
    assert "backlog" not in query.lower()
