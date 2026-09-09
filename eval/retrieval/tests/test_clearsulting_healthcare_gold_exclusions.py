"""Cycle-2 P3 — remaining Clearsulting healthcare filename_closure exclusions.

T11 pattern: bloated healthcare-overlay intents are aggregate_exclude /
no_citation_source on a tech-services room. Modest FTA/KPI gold stays scored.
"""

from __future__ import annotations

from pathlib import Path

from eval.retrieval.gold.bootstrap import load_gold_exclusions

REPO_ROOT = Path(__file__).resolve().parents[3]
GOLD_EXCLUSIONS_PATH = (
    REPO_ROOT / "eval" / "retrieval" / "gold" / "gold_exclusions.yaml"
)

CLEARSULTING_HEALTHCARE_FILENAME_CLOSURE = frozenset(
    {
        "kpi.retrieve_healthcare_labor_market",
        "kpi.retrieve_healthcare_ops",
        "kpi.retrieve_healthcare_revenue_per_unit",
        "cqa.retrieve_customer_health",
        "cqa.retrieve_payor_mix",
        "cqa.retrieve_cohort_data",
        "cqa.retrieve_retention_metrics",
    }
)

CLEARSULTING_MODEST_GOLD_MUST_STAY = frozenset(
    {
        "fta.ebitda.q2_ebitda_and_margins",
        "fta.ebitda.q3_working_capital",
        "fta.opex.q2_working_capital",
        "fta.opex.q3_projected_financials",
        "fta.revenue.q2_revenue_by_segment",
        "fta.revenue.q3_revenue_by_geography",
        "fta.revenue.q4_customer_concentration",
        "fta.revenue.q4_customer_concentration_fallback",
        "fta.revenue.q5_quickbooks_pl",
        "kpi.retrieve_pipeline_backlog",
        "kpi.retrieve_bill_rates_and_margins",
        "kpi.retrieve_kpi_dashboard",
        "kpi.retrieve_bench_and_capacity",
        "cqa.retrieve_account_size",
    }
)


def test_clearsulting_healthcare_filename_closure_intents_are_excluded():
    exclusions = load_gold_exclusions(
        GOLD_EXCLUSIONS_PATH, company_slug="clearsulting"
    )
    missing = CLEARSULTING_HEALTHCARE_FILENAME_CLOSURE - set(exclusions)
    assert not missing, f"healthcare filename_closure intents not excluded: {sorted(missing)}"
    for intent_id in CLEARSULTING_HEALTHCARE_FILENAME_CLOSURE:
        assert exclusions[intent_id] == "no_citation_source"


def test_clearsulting_modest_fta_kpi_gold_is_not_excluded():
    exclusions = load_gold_exclusions(
        GOLD_EXCLUSIONS_PATH, company_slug="clearsulting"
    )
    leaked = CLEARSULTING_MODEST_GOLD_MUST_STAY & set(exclusions)
    assert not leaked, f"modest FTA/KPI gold was excluded: {sorted(leaked)}"
