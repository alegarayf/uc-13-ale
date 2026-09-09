"""Unit tests for agents.exec_summary.field_mapping — FTA → bundle mapping fix.

Covers the bug found on a real run (docs/plans/plan_raimaker_format.md §2):
_fta_table_rows/_headline_from_fta read the wrong field names from
financial_trends_agent.py's actual output schema (revenue_stated,
ebitda_dollars, gm_dollars_stated — not revenue/ebitda/gross_profit), and
revenue_trend/ebitda can carry duplicate/multi-version records per period.

No company-specific literals — periods are generic ("2023A", "TTM") so this
generalizes across verticals (plan §Principios rectores, P2).
"""

from __future__ import annotations

from agents.exec_summary.field_mapping import (
    _company_framing_from_bma,
    _fta_table_rows,
    _headline_from_fta,
    _kpi_overlay_block,
    _kpi_rows_from_yaml,
    _revenue_quality_from_agents,
)


def test_fta_table_rows_reads_real_field_names():
    fta_yaml = {
        "revenue_trend": [
            {"period": "2023A", "revenue_stated": "$1.9", "yoy_growth_pct": None},
            {"period": "2024A", "revenue_stated": "$8.3", "yoy_growth_pct": "331%"},
        ],
        "gross_margin": [
            {"period": "2023A", "gm_dollars_stated": "$1.6", "gm_pct_stated": "82.3%"},
            {"period": "2024A", "gm_dollars_stated": "$7.0", "gm_pct_stated": "85.1%"},
        ],
        "ebitda": [
            {"period": "2023A", "version": "reported", "ebitda_dollars": "$0.7", "ebitda_margin_pct": "35.7%"},
            {"period": "2024A", "version": "reported", "ebitda_dollars": "$4.4", "ebitda_margin_pct": "53.4%"},
        ],
    }
    rows = _fta_table_rows(fta_yaml)
    assert len(rows) == 2
    assert rows[0] == {
        "year": "2023A",
        "revenue": "$1.9",
        "gross_profit": "$1.6",
        "gross_margin_pct": "82.3%",
        "ebitda": "$0.7",
        "ebitda_margin_pct": "35.7%",
    }
    assert rows[1]["revenue"] == "$8.3"
    assert rows[1]["ebitda"] == "$4.4"


def test_fta_table_rows_dedupes_duplicate_periods():
    """Fix B0 — revenue_trend can carry exact-duplicate period records
    (observed on a real run: each year appeared twice)."""
    fta_yaml = {
        "revenue_trend": [
            {"period": "2020A", "revenue_stated": "$1.0"},
            {"period": "2021A", "revenue_stated": "$2.0"},
            {"period": "2020A", "revenue_stated": "$1.0"},
            {"period": "2021A", "revenue_stated": "$2.0"},
        ],
        "gross_margin": [],
        "ebitda": [],
    }
    rows = _fta_table_rows(fta_yaml)
    assert [r["year"] for r in rows] == ["2020A", "2021A"]


def test_fta_table_rows_picks_canonical_ebitda_version():
    """When a period has multiple EBITDA version records, prefer
    pf_adjusted > clinic_level_adjusted > reported."""
    fta_yaml = {
        "revenue_trend": [{"period": "2024A", "revenue_stated": "$10"}],
        "gross_margin": [],
        "ebitda": [
            {"period": "2024A", "version": "reported", "ebitda_dollars": "$1.0", "ebitda_margin_pct": "10%"},
            {"period": "2024A", "version": "pf_adjusted", "ebitda_dollars": "$3.0", "ebitda_margin_pct": "30%"},
        ],
    }
    rows = _fta_table_rows(fta_yaml)
    assert len(rows) == 1
    assert rows[0]["ebitda"] == "$3.0"
    assert rows[0]["ebitda_margin_pct"] == "30%"


def test_fta_table_rows_never_invents_missing_dollar_figures():
    """A period with only margin % stated (no $ extracted) must render an
    empty $ cell, never a fabricated number."""
    fta_yaml = {
        "revenue_trend": [{"period": "2020A"}],
        "gross_margin": [{"period": "2020A", "gm_pct_stated": "42.1%"}],
        "ebitda": [{"period": "2020A", "ebitda_margin_pct": "36.6%"}],
    }
    rows = _fta_table_rows(fta_yaml)
    assert rows[0]["revenue"] == ""
    assert rows[0]["gross_profit"] == ""
    assert rows[0]["ebitda"] == ""
    assert rows[0]["gross_margin_pct"] == "42.1%"
    assert rows[0]["ebitda_margin_pct"] == "36.6%"


def test_fta_table_rows_empty_input_returns_empty_list():
    assert _fta_table_rows(None) == []
    assert _fta_table_rows({}) == []


def test_headline_from_fta_reads_real_field_names():
    fta_yaml = {
        "revenue_trend": [
            {"period": "2023A", "revenue_stated": "$1.9", "yoy_growth_pct": None},
            {"period": "2024A", "revenue_stated": "$8.3", "yoy_growth_pct": "331%"},
        ],
        "ebitda": [
            {"period": "2023A", "version": "reported", "ebitda_dollars": "$0.7", "ebitda_margin_pct": "35.7%"},
            {"period": "2024A", "version": "reported", "ebitda_dollars": "$4.4", "ebitda_margin_pct": "53.4%"},
        ],
    }
    headline = _headline_from_fta(fta_yaml)
    assert headline["ltm_revenue"] == "$8.3"
    assert headline["ltm_ebitda"] == "$4.4"
    assert headline["ltm_ebitda_margin_pct"] == "53.4%"
    assert headline["revenue_cagr"] == "331%"


def test_headline_from_fta_empty_input_returns_blank_fields():
    headline = _headline_from_fta(None)
    assert headline["ltm_revenue"] == ""
    assert headline["ltm_ebitda"] == ""
    assert headline["revenue_cagr"] == ""


# ---------------------------------------------------------------------------
# _revenue_quality_from_agents — the mapping bug found reading the Elder Care
# render (docs/plans/connect-all-vdr-er.md Part B, follow-up). CQA's report
# yaml has always used "concentration_summary"/"customer_tenure"/"retention"
# as key names, and this function checked "customer_concentration"/
# "concentration" (neither ever existed) and hardcoded end_market_mix/
# retention_notes to "" — so it always returned blank regardless of what CQA
# actually extracted, even when the CIM's own data (e.g. a length-of-stay
# distribution, a per-client billed-amount figure) was captured correctly
# by the agent. absence_check.py's reclassification ("present but not
# extracted") was papering over this — this fixes it at the source.
# ---------------------------------------------------------------------------


def test_revenue_quality_reads_concentration_summary_not_the_old_wrong_keys():
    cqa_yaml = {
        "concentration_summary": {"top1_pct": 12.0, "top3_pct": 28.0, "top5_pct": None, "top10_pct": None},
    }
    result = _revenue_quality_from_agents(None, cqa_yaml)
    assert "Top 1: 12.0%" in result["concentration"]
    assert "Top 3: 28.0%" in result["concentration"]
    assert "Top 5" not in result["concentration"]  # null fields are omitted, not fabricated as 0%


def test_revenue_quality_concentration_blank_when_agent_found_nothing():
    """A genuine gap (every pct null) stays blank — absence_check is what
    decides whether that blank is a real gap or a mapping miss, not this
    function fabricating a placeholder."""
    cqa_yaml = {"concentration_summary": {"top1_pct": None, "top3_pct": None, "top5_pct": None, "top10_pct": None}}
    result = _revenue_quality_from_agents(None, cqa_yaml)
    assert result["concentration"] == ""


def test_revenue_quality_retention_notes_combines_tenure_and_retention():
    """Real Elder Care shape: no SaaS-style NRR/GRR (private-pay home care
    doesn't report that), but a length-of-stay distribution IS the agent's
    retention signal for this vertical — both sources are read generically,
    whichever the agent populated."""
    cqa_yaml = {
        "retention": {"nrr_pct": None, "grr_pct": None, "logo_churn_rate_annual_pct": None},
        "customer_tenure": {
            "average_tenure_years": None,
            "tenure_distribution_note": "4+ Years 57%, 1-2 Months 8%.",
        },
    }
    result = _revenue_quality_from_agents(None, cqa_yaml)
    assert "4+ Years 57%" in result["retention_notes"]


def test_revenue_quality_retention_notes_generalizes_to_saas_shaped_data():
    """Anti-overfit: a subscription business reports NRR/GRR, not a
    length-of-stay distribution — same function, no vertical-specific code
    path, must read this shape too."""
    cqa_yaml = {
        "retention": {"nrr_pct": 112.0, "grr_pct": 94.0, "logo_churn_rate_annual_pct": 8.0},
        "customer_tenure": {"average_tenure_years": None, "tenure_distribution_note": None},
    }
    result = _revenue_quality_from_agents(None, cqa_yaml)
    assert "NRR 112.0%" in result["retention_notes"]
    assert "GRR 94.0%" in result["retention_notes"]
    assert "Annual logo churn 8.0%" in result["retention_notes"]


def test_revenue_quality_end_market_mix_from_payor_mix():
    cqa_yaml = {
        "payor_mix": [
            {"payor_category": "Medicare", "pct_of_revenue": 10.0},
            {"payor_category": "Private Pay", "pct_of_revenue": 90.0},
            {"payor_category": "Medicaid", "pct_of_revenue": None},  # omitted, not fabricated
        ]
    }
    result = _revenue_quality_from_agents(None, cqa_yaml)
    assert "Medicare: 10.0%" in result["end_market_mix"]
    assert "Private Pay: 90.0%" in result["end_market_mix"]
    assert "Medicaid" not in result["end_market_mix"]


def test_revenue_quality_never_raises_on_missing_or_malformed_cqa_yaml():
    assert _revenue_quality_from_agents(None, None) == {
        "scale_narrative": "", "concentration": "", "end_market_mix": "", "retention_notes": "",
    }
    # Malformed shapes (wrong types) degrade to blank rather than raising.
    malformed = {"concentration_summary": "not a dict", "retention": [], "customer_tenure": None, "payor_mix": {}}
    result = _revenue_quality_from_agents(None, malformed)
    assert result["concentration"] == "not a dict"
    assert result["retention_notes"] == ""
    assert result["end_market_mix"] == ""


# ---------------------------------------------------------------------------
# _revenue_quality_from_agents — KPI fallback (2026-08-13 follow-up). CQA's
# concentration_summary/payor_mix are frequently null (not every vertical's
# CIM reports a top-N-clients table or a payor split), but kpi_agent already
# extracts an overlay-specific market/geography/channel signal for exactly
# this purpose (e.g. healthcare's census_or_patient_panel embeds the
# page-44-style "Clients by Location" breakdown). Falls back to it only when
# CQA's own field came back blank — never overrides a value CQA gave.
# ---------------------------------------------------------------------------


def test_revenue_quality_falls_back_to_kpi_census_when_cqa_concentration_is_blank():
    """Real Elder Care shape: concentration_summary all-null, but
    healthcare_kpis.census_or_patient_panel has the location breakdown."""
    cqa_yaml = {"concentration_summary": {"top1_pct": None, "top3_pct": None, "top5_pct": None, "top10_pct": None}}
    kpi_yaml = {
        "overlay_confirmed": "healthcare_services",
        "healthcare_kpis": {
            "census_or_patient_panel": "1,186 total clients TTM Aug-24 across NYC: 331, Westchester: 259, New Jersey: 306",
            "referral_source_breakdown": None,
        },
    }
    result = _revenue_quality_from_agents(None, cqa_yaml, kpi_yaml)
    assert "1,186 total clients" in result["end_market_mix"]
    assert result["concentration"] == ""  # referral_source_breakdown was null too — genuine gap, stays blank


def test_revenue_quality_kpi_fallback_never_overrides_a_real_cqa_value():
    cqa_yaml = {
        "concentration_summary": {"top1_pct": 12.0, "top3_pct": None, "top5_pct": None, "top10_pct": None},
        "payor_mix": [{"payor_category": "Medicare", "pct_of_revenue": 40.0}],
    }
    kpi_yaml = {
        "healthcare_kpis": {
            "census_or_patient_panel": "should never appear",
            "referral_source_breakdown": "should never appear either",
        }
    }
    result = _revenue_quality_from_agents(None, cqa_yaml, kpi_yaml)
    assert result["concentration"] == "Top 1: 12.0% of revenue"
    assert "Medicare" in result["end_market_mix"]
    assert "should never appear" not in result["concentration"]
    assert "should never appear" not in result["end_market_mix"]


def test_revenue_quality_kpi_fallback_generalizes_to_tech_services_and_consumer():
    """Anti-overfit: two other overlays, two different field names, same
    generic composition function — no vertical-specific branching."""
    tech = _revenue_quality_from_agents(
        None, None,
        {"tech_services_kpis": {"delivery_geography_note": "80% of delivery is offshore (India)."}},
    )
    assert "80% of delivery is offshore" in tech["end_market_mix"]

    consumer = _revenue_quality_from_agents(
        None, None,
        {"consumer_kpis": {
            "channel_mix_note": "DTC 60% / wholesale 40%.",
            "platform_concentration_note": "Amazon is 70% of online revenue.",
        }},
    )
    assert "DTC 60%" in consumer["end_market_mix"]
    assert "Amazon is 70%" in consumer["concentration"]


def test_revenue_quality_kpi_fallback_blank_for_overlays_with_no_analog_field():
    """b2b_saas and industrial genuinely have no geography/channel/
    concentration concept in kpi_agent's schema — must stay blank, not
    fabricate one, so absence_check keeps covering the real gap."""
    saas = _revenue_quality_from_agents(None, None, {"saas_kpis": {"nrr_pct": 110.0}})
    assert saas["end_market_mix"] == ""
    assert saas["concentration"] == ""

    industrial = _revenue_quality_from_agents(None, None, {"industrial_kpis": {"backlog_months": 6}})
    assert industrial["end_market_mix"] == ""
    assert industrial["concentration"] == ""


def test_revenue_quality_no_kpi_yaml_is_the_same_as_before():
    """Backwards compatible: omitting kpi_yaml (existing callers) behaves
    exactly as it did before this fallback was added."""
    cqa_yaml = {"concentration_summary": {"top1_pct": None, "top3_pct": None, "top5_pct": None, "top10_pct": None}}
    assert _revenue_quality_from_agents(None, cqa_yaml) == _revenue_quality_from_agents(None, cqa_yaml, None)


# ---------------------------------------------------------------------------
# _fta_table_rows — two bugs found reviewing a live Elder Care render
# (docs/plans/connect-all-vdr-er.md Part B, follow-up):
#
# (1) a stray non-data record (e.g. a discrepancy note the extractor
#     sometimes appends inline instead of using the dedicated
#     discrepancy-flagging path) was rendering as an empty phantom column
#     in the P&L table and the Financial Snapshot chart.
# (2) gross_margin has no dedicated segment array (unlike revenue_by_segment),
#     so a multi-location P&L sometimes appends each location's Gross Profit
#     to the SAME array under a suffixed label ("Gross Profit (Westchester)")
#     -- a naive last-record-wins pick silently replaced the company-wide
#     figure with whichever location happened to be extracted last.
#
# Both fixes are structural (numeric-signal presence, label shape), never a
# hardcoded sentinel string or city/segment name, so they generalize to any
# company's data room.
# ---------------------------------------------------------------------------


def test_fta_table_rows_drops_a_non_data_period_like_discrepancy_flag():
    """Real Elder Care shape: revenue_trend carried an inline discrepancy
    note with period='DISCREPANCY_FLAG' and every numeric field null, with
    no companion record in gross_margin/ebitda either -- must not become a
    phantom empty column."""
    fta_yaml = {
        "revenue_trend": [
            {"period": "2023A", "revenue_stated": "28,330"},
            {"period": "TTM Aug-24", "revenue_stated": "35,136"},
            {
                "period": "DISCREPANCY_FLAG",
                "label": "NOTE: figures differ between two CIM sections.",
                "revenue_stated": None,
                "yoy_growth_pct": None,
            },
        ],
        "gross_margin": [
            {"period": "2023A", "gm_dollars_stated": "14,910", "gm_pct_stated": "43.6%"},
            {"period": "TTM Aug-24", "gm_dollars_stated": "20,170", "gm_pct_stated": "43.4%"},
        ],
        "ebitda": [
            {"period": "2023A", "version": "pf_adjusted", "ebitda_dollars": "6,677", "ebitda_margin_pct": "19.5%"},
            {"period": "TTM Aug-24", "version": "pf_adjusted", "ebitda_dollars": "9,239", "ebitda_margin_pct": "19.9%"},
        ],
    }
    rows = _fta_table_rows(fta_yaml)
    assert [r["year"] for r in rows] == ["2023A", "TTM Aug-24"]
    assert "DISCREPANCY_FLAG" not in [r["year"] for r in rows]


def test_fta_table_rows_keeps_a_sparse_but_real_period():
    """A period genuinely missing revenue but with real gross-margin/EBITDA
    data must NOT be dropped -- the filter targets records with zero data
    anywhere, not records merely missing one field."""
    fta_yaml = {
        "revenue_trend": [{"period": "2020A"}],
        "gross_margin": [{"period": "2020A", "gm_pct_stated": "42.1%"}],
        "ebitda": [{"period": "2020A", "ebitda_margin_pct": "36.6%"}],
    }
    rows = _fta_table_rows(fta_yaml)
    assert len(rows) == 1
    assert rows[0]["year"] == "2020A"
    assert rows[0]["revenue"] == ""
    assert rows[0]["gross_margin_pct"] == "42.1%"


def test_fta_table_rows_prefers_consolidated_gross_margin_over_a_location_breakdown():
    """Real Elder Care shape: 'Gross Profit (New Jersey)' appears after the
    consolidated 'Gross Profit' record for the same period. Order must not
    matter -- the unqualified label always wins."""
    fta_yaml = {
        "revenue_trend": [{"period": "TTM Aug-24", "revenue_stated": "35,136"}],
        "gross_margin": [
            {"period": "TTM Aug-24", "label": "Gross Profit", "gm_dollars_stated": "20,170", "gm_pct_stated": "43.4%"},
            {"period": "TTM Aug-24", "label": "Gross Profit (Westchester)", "gm_dollars_stated": "3,208", "gm_pct_stated": "36.6%"},
            {"period": "TTM Aug-24", "label": "Gross Profit (Long Island)", "gm_dollars_stated": "5,205", "gm_pct_stated": "44.7%"},
            {"period": "TTM Aug-24", "label": "Gross Profit (New Jersey)", "gm_dollars_stated": "3,455", "gm_pct_stated": "45.6%"},
        ],
        "ebitda": [],
    }
    rows = _fta_table_rows(fta_yaml)
    assert rows[0]["gross_profit"] == "20,170"
    assert rows[0]["gross_margin_pct"] == "43.4%"


def test_fta_table_rows_consolidated_wins_regardless_of_array_order():
    """Anti-overfit: the consolidated record can appear LAST too -- the
    selection must key off label shape, not array position."""
    fta_yaml = {
        "revenue_trend": [{"period": "2023A", "revenue_stated": "10,000"}],
        "gross_margin": [
            {"period": "2023A", "label": "Gross Profit (Segment A)", "gm_dollars_stated": "500", "gm_pct_stated": "5%"},
            {"period": "2023A", "label": "Gross Profit", "gm_dollars_stated": "4,000", "gm_pct_stated": "40%"},
        ],
        "ebitda": [],
    }
    rows = _fta_table_rows(fta_yaml)
    assert rows[0]["gross_profit"] == "4,000"
    assert rows[0]["gross_margin_pct"] == "40%"


def test_fta_table_rows_no_consolidated_label_falls_back_to_first_seen():
    """When every record for a period is segment-qualified (no plain label
    exists at all), there is no consolidated figure to prefer -- keep the
    first one seen rather than raising or fabricating a total."""
    fta_yaml = {
        "revenue_trend": [{"period": "2023A", "revenue_stated": "10,000"}],
        "gross_margin": [
            {"period": "2023A", "label": "Gross Profit (Segment A)", "gm_dollars_stated": "500", "gm_pct_stated": "5%"},
            {"period": "2023A", "label": "Gross Profit (Segment B)", "gm_dollars_stated": "600", "gm_pct_stated": "6%"},
        ],
        "ebitda": [],
    }
    rows = _fta_table_rows(fta_yaml)
    assert rows[0]["gross_profit"] == "500"


def test_fta_table_rows_ebitda_also_filters_non_data_sentinel_records():
    """Anti-overfit: the same class of stray inline note could appear in the
    ebitda array too -- same generic filter applies there, not something
    special-cased to revenue_trend."""
    fta_yaml = {
        "revenue_trend": [{"period": "2023A", "revenue_stated": "10,000"}],
        "gross_margin": [],
        "ebitda": [
            {"period": "2023A", "version": "pf_adjusted", "ebitda_dollars": "2,000", "ebitda_margin_pct": "20%"},
            {"period": "NOTE", "label": "some inline caveat", "ebitda_dollars": None, "ebitda_margin_pct": None},
        ],
    }
    rows = _fta_table_rows(fta_yaml)
    assert rows[0]["ebitda"] == "2,000"
    assert "NOTE" not in [r["year"] for r in rows]


# ---------------------------------------------------------------------------
# company_framing: the two facts the investment team kept having to ask for
# (who is running the sale process, and who the important partners are) plus
# the profiler's what-it-does/how-it-operates description. All three were
# already produced upstream — the bundle was simply dropping them.
# ---------------------------------------------------------------------------


def test_key_partners_keeps_only_commercial_relationships():
    bma_yaml = {
        "key_dependencies": [
            {"dependency_type": "platform", "name": "Platform A", "description": "Core stack"},
            {"dependency_type": "partner", "name": "Partner B"},
            {"dependency_type": "channel", "name": "Reseller C"},
            {"dependency_type": "vendor", "name": "Vendor D"},
            {"dependency_type": "person", "name": "Founder"},
            {"dependency_type": "team", "name": "Delivery team"},
            {"dependency_type": "geography", "name": "Region"},
            {"dependency_type": "customer", "name": "Top account"},
        ]
    }
    partners = _company_framing_from_bma(bma_yaml)["key_partners"]
    assert [p["name"] for p in partners] == ["Platform A", "Partner B", "Reseller C", "Vendor D"]
    assert partners[0] == {
        "name": "Platform A",
        "relationship_type": "platform",
        "description": "Core stack",
    }


def test_key_partners_dedupe_by_name_and_cap():
    bma_yaml = {
        "key_dependencies": [{"dependency_type": "partner", "name": "Partner A"}]
        + [{"dependency_type": "partner", "name": "partner a"}]
        + [{"dependency_type": "platform", "name": f"Platform {i}"} for i in range(10)]
    }
    partners = _company_framing_from_bma(bma_yaml)["key_partners"]
    assert len(partners) == 6
    assert [p["name"] for p in partners].count("Partner A") == 1


def test_business_description_and_sale_process_come_from_the_profile():
    profile = {
        "business_description": "Does a thing. Operates by doing it.",
        "sale_process": "Brought to market by an investment bank running a broad auction.",
    }
    framing = _company_framing_from_bma({"executive_summary": "Summary"}, profile)
    assert framing["business_description"] == "Does a thing. Operates by doing it."
    assert framing["sale_process"] == "Brought to market by an investment bank running a broad auction."


def test_sale_process_falls_back_to_the_banked_flag_when_no_advisor_is_named():
    framing = _company_framing_from_bma({}, {"banked": True, "banked_note": "CIM present."})
    assert "Banker-run process" in framing["sale_process"]
    assert "CIM present." in framing["sale_process"]


def test_sale_process_is_none_when_nothing_says_the_deal_is_banked():
    assert _company_framing_from_bma({}, {"banked": False})["sale_process"] is None
    assert _company_framing_from_bma({}, {"sale_process": "null"})["sale_process"] is None
    assert _company_framing_from_bma({}, {})["sale_process"] is None


def test_company_framing_carries_the_new_fields_even_with_no_bma_output():
    framing = _company_framing_from_bma(None, {"business_description": "Desc.", "banked": True})
    assert framing["business_description"] == "Desc."
    assert framing["sale_process"]
    assert framing["key_partners"] == []


# ---------------------------------------------------------------------------
# The two mapping bugs found by reading the first live final reports off
# uc13_preview (GKF, Clearsulting, Elder Care, 2026-09-09):
#
#   1. revenue_quality carried only prose notes, so the final report's
#      concentration chart, top-customers table and retention tiles — all of
#      which read CQA's structured shapes — rendered "not extracted" over a
#      fully populated CQA row (Clearsulting: 6.4KB of named clients with
#      revenue, NRR 73%).
#   2. The overlay block was picked by declaration order, and kpi_agent writes
#      all five blocks with only the confirmed one filled. Every non-healthcare
#      company therefore rendered an all-null healthcare stub instead of its
#      own KPIs (Clearsulting: a 706-char null record chosen over 12KB of
#      tech-services KPIs).
#
# The all-null stub below is the real shape, trimmed: what matters is that it
# is a full-length record whose values are all null, so plain truthiness
# cannot tell it apart from a populated one.
# ---------------------------------------------------------------------------

_NULL_HEALTHCARE_STUB = {
    "census_or_patient_panel": None,
    "caregiver_headcount": None,
    "turnover_rate_pct": None,
    "referral_source_breakdown": None,
    "compliance_incidents": [],
    "site_level_visibility": "false",
    "source_doc": None,
}


def test_revenue_quality_passes_cqa_structured_blocks_through():
    cqa_yaml = {
        "top_customers": [{"customer_name": "Client 1", "revenue_pct_yr1": None}],
        "retention": {"nrr_pct": "73%", "grr_pct": None},
        "concentration_summary": {"top1_pct": None, "top5_pct": None},
        "customer_tenure": {"average_tenure_years": 3},
    }
    result = _revenue_quality_from_agents(None, cqa_yaml)
    assert result["top_customers"] == cqa_yaml["top_customers"]
    assert result["retention"]["nrr_pct"] == "73%"
    assert result["concentration_summary"] == cqa_yaml["concentration_summary"]
    assert result["customer_tenure"]["average_tenure_years"] == 3


def test_revenue_quality_omits_blocks_the_agent_left_empty():
    """An absent block must stay absent, not become an empty dict — downstream
    ``or {}`` guards read "agent found nothing", and a blank record would make
    a gap look like an extraction that returned nothing to say."""
    result = _revenue_quality_from_agents(None, {"top_customers": [], "retention": {}})
    assert "top_customers" not in result
    assert "retention" not in result


def test_revenue_quality_structured_passthrough_survives_no_cqa():
    result = _revenue_quality_from_agents(None, None)
    assert "top_customers" not in result
    assert result["concentration"] == ""


def test_kpi_overlay_block_prefers_the_confirmed_overlay_over_declaration_order():
    kpi_yaml = {
        "healthcare_kpis": dict(_NULL_HEALTHCARE_STUB),
        "tech_services_kpis": {"utilization_rate_pct": "78%", "bill_rate_dollars": "$225"},
    }
    key, blob = _kpi_overlay_block(kpi_yaml, "tech_services")
    assert key == "tech_services_kpis"
    assert blob["utilization_rate_pct"] == "78%"


def test_kpi_overlay_block_falls_back_to_the_richest_block_without_a_hint():
    """No overlay hint (profile missing it) must not mean the first block wins
    — the block the agent actually filled does."""
    kpi_yaml = {
        "healthcare_kpis": dict(_NULL_HEALTHCARE_STUB),
        "consumer_kpis": {"channel_mix_note": "Tuition 98.7% of revenue"},
    }
    key, _ = _kpi_overlay_block(kpi_yaml, "")
    assert key == "consumer_kpis"


def test_kpi_overlay_block_ignores_an_unrecognised_hint_rather_than_going_blank():
    kpi_yaml = {"consumer_kpis": {"channel_mix_note": "Tuition 98.7%"}}
    key, _ = _kpi_overlay_block(kpi_yaml, "something_we_never_heard_of")
    assert key == "consumer_kpis"


def test_kpi_overlay_block_returns_none_when_every_block_is_a_null_stub():
    key, blob = _kpi_overlay_block({"healthcare_kpis": dict(_NULL_HEALTHCARE_STUB)}, "")
    assert key is None and blob is None


def test_kpi_rows_use_the_confirmed_overlay_not_the_null_stub():
    kpi_yaml = {
        "healthcare_kpis": dict(_NULL_HEALTHCARE_STUB),
        "tech_services_kpis": {"utilization_rate_pct": "78%"},
    }
    rows = _kpi_rows_from_yaml(kpi_yaml, "tech_services")
    assert [r["metric_id"] for r in rows] == ["utilization_rate_pct"]
