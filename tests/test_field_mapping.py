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

import json

from agents.exec_summary.field_mapping import (
    _company_framing_from_bma,
    _value_creation_levers_from_bma,
    apply_field_mappings,
    _fta_table_rows,
    _headline_from_fta,
    _addbacks_from_qoe,
    _derive_customer_shares,
    _kpi_overlay_block,
    _kpi_rows_from_yaml,
    _qoe_from_snapshots,
    _revenue_quality_from_agents,
    _segment_performance_from_fta,
    money_to_dollars,
    period_sort_key,
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
        # Both periods carry a reported record only — the pf_adjusted series
        # is genuinely empty here and renders as such, not as a copy.
        "adjusted_ebitda": "",
        "adjusted_ebitda_margin_pct": "",
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
    """SUPERSEDED IN PLACE by the reported/PF-adjusted split (plan
    report-surface-truth-w1 T1, §2.2 items 1 and 4; decision log
    .dev/plans/report-surface-truth-w1/decision-logs/T1.md).

    This test previously asserted the OPPOSITE behaviour: that a period
    carrying several EBITDA versions collapses to one cell, preferring
    pf_adjusted > clinic_level_adjusted > reported, so ``ebitda`` here was
    "$3.0". That collapse is what made the earnings-quality gap render as
    zero — one figure was shown under both the "Reported EBITDA" and
    "Adjusted EBITDA" labels, so the chart whose entire purpose is the
    difference between them showed none.

    The superseding contract: ``ebitda``/``ebitda_margin_pct`` are the
    REPORTED series and ``adjusted_ebitda``/``adjusted_ebitda_margin_pct``
    the pf_adjusted one, disjoint, with both versions present yielding two
    distinct cells. The test is kept rather than deleted so the inverted
    invariant stays locatable.
    """
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
    assert rows[0]["ebitda"] == "$1.0"
    assert rows[0]["ebitda_margin_pct"] == "10%"
    assert rows[0]["adjusted_ebitda"] == "$3.0"
    assert rows[0]["adjusted_ebitda_margin_pct"] == "30%"
    # The invariant the collapse violated: the two labels never carry one value.
    assert rows[0]["ebitda"] != rows[0]["adjusted_ebitda"]


def test_fta_table_rows_pf_only_period_leaves_the_reported_cell_empty():
    """§2.2 item 3 — when the only EBITDA record for a period is pf_adjusted,
    the reported cell is empty and the adjusted cell is populated. Empty is
    the honest state; copying the PF figure into the reported column is the
    defect."""
    fta_yaml = {
        "revenue_trend": [{"period": "2024A", "revenue_stated": "$10"}],
        "gross_margin": [],
        "ebitda": [
            {"period": "2024A", "version": "pf_adjusted", "ebitda_dollars": "$3.0", "ebitda_margin_pct": "30%"},
        ],
    }
    rows = _fta_table_rows(fta_yaml)
    assert len(rows) == 1
    assert rows[0]["ebitda"] == ""
    assert rows[0]["ebitda_margin_pct"] == ""
    assert rows[0]["adjusted_ebitda"] == "$3.0"
    assert rows[0]["adjusted_ebitda_margin_pct"] == "30%"


def test_fta_table_rows_pf_only_period_still_appears_as_a_row():
    """§2.2 item 5 — period genuineness is decided over BOTH series. A period
    whose ONLY signal anywhere is a pf_adjusted EBITDA record must still
    render; feeding only the reported map into ``_periods_with_real_data``
    silently deletes the row."""
    fta_yaml = {
        "revenue_trend": [{"period": "2024A"}],
        "gross_margin": [],
        "ebitda": [
            {"period": "2024A", "version": "pf_adjusted", "ebitda_dollars": "$3.0", "ebitda_margin_pct": "30%"},
        ],
    }
    rows = _fta_table_rows(fta_yaml)
    assert [r["year"] for r in rows] == ["2024A"]
    assert rows[0]["adjusted_ebitda"] == "$3.0"
    assert rows[0]["ebitda"] == ""


def test_fta_table_rows_reported_absent_falls_back_to_non_pf_never_to_pf():
    """§2.2 item 2 — with no reported record, the reported column takes the
    best available NON-PF version (clinic_level_adjusted) and the adjusted
    column takes pf_adjusted. The fallback chain must never reach
    pf_adjusted, or the two columns collapse back onto one record."""
    fta_yaml = {
        "revenue_trend": [{"period": "2024A", "revenue_stated": "$10"}],
        "gross_margin": [],
        "ebitda": [
            {"period": "2024A", "version": "pf_adjusted", "ebitda_dollars": "$3.0", "ebitda_margin_pct": "30%"},
            {"period": "2024A", "version": "clinic_level_adjusted", "ebitda_dollars": "$2.0", "ebitda_margin_pct": "20%"},
        ],
    }
    rows = _fta_table_rows(fta_yaml)
    assert rows[0]["ebitda"] == "$2.0"
    assert rows[0]["ebitda_margin_pct"] == "20%"
    assert rows[0]["adjusted_ebitda"] == "$3.0"
    assert rows[0]["adjusted_ebitda_margin_pct"] == "30%"


def test_fta_table_rows_unversioned_ebitda_record_still_fills_the_reported_column():
    """§2.2 item 2, highest-risk failure mode — a weak extraction tags no
    version at all. An over-strict ``version == "reported"`` filter would
    empty the reported column for that company entirely; the non-PF fallback
    keeps the unversioned record eligible."""
    fta_yaml = {
        "revenue_trend": [{"period": "2024A", "revenue_stated": "$10"}],
        "gross_margin": [],
        "ebitda": [
            {"period": "2024A", "ebitda_dollars": "$1.5", "ebitda_margin_pct": "15%"},
        ],
    }
    rows = _fta_table_rows(fta_yaml)
    assert rows[0]["ebitda"] == "$1.5"
    assert rows[0]["ebitda_margin_pct"] == "15%"
    assert rows[0]["adjusted_ebitda"] == ""

    # version: null must behave identically to an absent version key.
    fta_yaml["ebitda"][0]["version"] = None
    rows = _fta_table_rows(fta_yaml)
    assert rows[0]["ebitda"] == "$1.5"


def test_fta_table_rows_explicit_reported_beats_clinic_level_adjusted():
    """§2.2 item 1 — an explicit reported record wins the reported column
    outright, regardless of array order, and is not outranked by
    clinic_level_adjusted (which is only a fallback when reported is absent)."""
    fta_yaml = {
        "revenue_trend": [{"period": "2024A", "revenue_stated": "$10"}],
        "gross_margin": [],
        "ebitda": [
            {"period": "2024A", "version": "clinic_level_adjusted", "ebitda_dollars": "$2.0"},
            {"period": "2024A", "version": "reported", "ebitda_dollars": "$1.0"},
        ],
    }
    assert _fta_table_rows(fta_yaml)[0]["ebitda"] == "$1.0"


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
    assert headline["ltm_adjusted_ebitda"] == ""
    assert headline["revenue_cagr"] == ""


def test_headline_from_fta_splits_reported_and_pf_adjusted_for_the_latest_period():
    """§2.2 item 6 — ltm_ebitda is the REPORTED figure for the latest period
    and ltm_adjusted_ebitda the pf_adjusted one for that same period. The
    cover previously showed a single unlabeled figure that was in fact the
    PF-adjusted number presented as "the" EBITDA."""
    fta_yaml = {
        "revenue_trend": [
            {"period": "2023A", "revenue_stated": "$1.9"},
            {"period": "2024A", "revenue_stated": "$8.3"},
        ],
        "ebitda": [
            {"period": "2023A", "version": "reported", "ebitda_dollars": "$0.7", "ebitda_margin_pct": "35.7%"},
            {"period": "2024A", "version": "reported", "ebitda_dollars": "$4.4", "ebitda_margin_pct": "53.4%"},
            {"period": "2024A", "version": "pf_adjusted", "ebitda_dollars": "$9.2", "ebitda_margin_pct": "110%"},
        ],
    }
    headline = _headline_from_fta(fta_yaml)
    assert headline["ltm_ebitda"] == "$4.4"
    assert headline["ltm_ebitda_margin_pct"] == "53.4%"
    assert headline["ltm_adjusted_ebitda"] == "$9.2"
    assert headline["ltm_ebitda"] != headline["ltm_adjusted_ebitda"]


def test_headline_from_fta_leaves_adjusted_blank_when_no_pf_record_exists():
    """§2.2 item 6, negative path — no pf_adjusted record for the latest
    period means an empty ltm_adjusted_ebitda, never a copy of the reported
    figure."""
    fta_yaml = {
        "revenue_trend": [{"period": "2024A", "revenue_stated": "$8.3"}],
        "ebitda": [
            {"period": "2024A", "version": "reported", "ebitda_dollars": "$4.4", "ebitda_margin_pct": "53.4%"},
        ],
    }
    headline = _headline_from_fta(fta_yaml)
    assert headline["ltm_ebitda"] == "$4.4"
    assert headline["ltm_adjusted_ebitda"] == ""


def test_headline_from_fta_pf_only_latest_period_leaves_reported_blank():
    """§2.2 items 3 + 6 — a latest period extracted only as pf_adjusted
    yields an empty ltm_ebitda. The legacy "fall back to the raw last
    record" path must not smuggle the PF figure under the reported label."""
    fta_yaml = {
        "revenue_trend": [{"period": "TTM Aug-24", "revenue_stated": "35,136"}],
        "ebitda": [
            {"period": "TTM Aug-24", "version": "pf_adjusted", "ebitda_dollars": "9,239", "ebitda_margin_pct": "19.9%"},
        ],
    }
    headline = _headline_from_fta(fta_yaml)
    assert headline["ltm_ebitda"] == ""
    assert headline["ltm_ebitda_margin_pct"] == ""
    assert headline["ltm_adjusted_ebitda"] == "9,239"


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
    # The real record is pf_adjusted, so it lands in the adjusted column
    # (report-surface-truth-w1 T1 §2.2); what this test pins is that the
    # sentinel "NOTE" record is filtered out of both series alike.
    assert rows[0]["adjusted_ebitda"] == "2,000"
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
# value_creation_levers (plan report-surface-truth-w1, T3 §2.3).
#
# The mapper used to hardcode `value_creation_levers: []` on the POPULATED
# branch too, so every company rendered "Value creation levers — not extracted
# from the data room" over a BMA extraction that did carry the underlying
# facts. These tests pin the four source classes, the priority order, the cap,
# and — the half that matters just as much — that a genuinely empty extraction
# still yields [] rather than an invented lever.
# ---------------------------------------------------------------------------


def test_levers_from_primary_model_changes_carry_the_stated_date():
    bma_yaml = {
        "recent_model_changes": [
            {"change_type": "ma", "description": "Acquired a regional operator",
             "approximate_date": "2024-06"},
            {"change_type": "geography", "description": "Opened a second region"},
            {"change_type": "customer_mix", "description": "Mix shifted"},
        ]
    }
    levers = _value_creation_levers_from_bma(bma_yaml)
    assert levers == [
        "Acquired a regional operator (2024-06)",
        "Opened a second region",
    ]
    # customer_mix is not a lever class — a mix shift is an observation.
    assert not any("Mix shifted" in lever for lever in levers)


def test_levers_from_revenue_visibility_pipeline_and_backlog():
    pipeline_only = _value_creation_levers_from_bma(
        {"revenue_visibility": {"pipeline_description": "Weighted pipeline of $40M."}}
    )
    assert pipeline_only == ["Forward pipeline: Weighted pipeline of $40M."]

    backlog_only = _value_creation_levers_from_bma(
        {"revenue_visibility": {"backlog_coverage_months": "7"}}
    )
    assert backlog_only == ["Backlog coverage: 7 months of forward revenue."]


def test_levers_from_offshore_delivery_capacity():
    levers = _value_creation_levers_from_bma(
        {
            "workforce_capacity": {
                "workforce_model": {
                    "offshore_or_contract_headcount": "153",
                    "offshore_pct_of_total": "8%",
                }
            }
        }
    )
    assert levers == [
        "Offshore/contract delivery capacity: 153 offshore/contract headcount, "
        "8% of total headcount."
    ]


def test_secondary_model_changes_are_used_but_rank_after_the_primary_classes():
    secondary_only = _value_creation_levers_from_bma(
        {
            "recent_model_changes": [
                {"change_type": "technology", "description": "Replatformed scheduling"},
                {"change_type": "staffing", "description": "Insourced recruiting"},
                {"change_type": "operational", "description": "Centralized intake"},
            ]
        }
    )
    assert secondary_only == [
        "Replatformed scheduling",
        "Insourced recruiting",
        "Centralized intake",
    ]

    both = _value_creation_levers_from_bma(
        {
            "recent_model_changes": [
                {"change_type": "technology", "description": "Replatformed scheduling"},
                {"change_type": "pricing", "description": "Raised rate card"},
            ]
        }
    )
    assert both == ["Raised rate card", "Replatformed scheduling"]


def test_levers_cap_at_four_in_declared_priority_order():
    bma_yaml = {
        "recent_model_changes": [
            {"change_type": "technology", "description": "Replatformed scheduling"},
            {"change_type": "ma", "description": "Acquired operator A"},
            {"change_type": "product", "description": "Launched a second service line"},
        ],
        "revenue_visibility": {
            "pipeline_description": "Weighted pipeline of $40M.",
            "backlog_coverage_months": "7",
        },
        "workforce_capacity": {"workforce_model": {"offshore_pct_of_total": "8%"}},
    }
    levers = _value_creation_levers_from_bma(bma_yaml)
    assert len(levers) == 4
    assert levers == [
        "Acquired operator A",
        "Launched a second service line",
        "Forward pipeline: Weighted pipeline of $40M.",
        "Backlog coverage: 7 months of forward revenue.",
    ]


def test_levers_are_deduped_stripped_and_never_empty_strings():
    bma_yaml = {
        "recent_model_changes": [
            {"change_type": "ma", "description": "  Acquired operator A  "},
            {"change_type": "geography", "description": "Acquired operator A"},
            {"change_type": "product", "description": "   "},
            {"change_type": "pricing", "description": None},
            {"change_type": "gtm", "description": "Hired a direct sales team"},
        ]
    }
    levers = _value_creation_levers_from_bma(bma_yaml)
    assert levers == ["Acquired operator A", "Hired a direct sales team"]
    assert all(lever == lever.strip() and lever for lever in levers)


def test_levers_stay_empty_when_all_four_source_classes_are_empty():
    """The honest-empty path. The nodata state the final report renders is
    correct when the extraction really is empty — this fix inverts it only for
    a populated extraction, it does not paper over a missing one."""
    assert _value_creation_levers_from_bma({}) == []
    assert _value_creation_levers_from_bma({"executive_summary": "A company."}) == []
    assert (
        _value_creation_levers_from_bma(
            {
                "recent_model_changes": [{"change_type": "customer_mix", "description": "Mix"}],
                "revenue_visibility": {"renewal_cadence_note": "Annual"},
                "workforce_capacity": {"workforce_model": {}},
                "key_dependencies": [
                    {"dependency_type": "customer", "name": "Top account",
                     "concentration_risk": "high"}
                ],
            }
        )
        == []
    )
    # and the no-BMA branch of the framing builder is untouched
    assert _company_framing_from_bma(None)["thesis"]["value_creation_levers"] == []
    assert _company_framing_from_bma({})["thesis"]["value_creation_levers"] == []


def test_company_framing_fills_levers_on_the_populated_branch():
    framing = _company_framing_from_bma(
        {
            "executive_summary": "A company.",
            "recent_model_changes": [
                {"change_type": "ma", "description": "Acquired operator A",
                 "approximate_date": "2024-06"}
            ],
        }
    )
    assert framing["thesis"]["value_creation_levers"] == ["Acquired operator A (2024-06)"]
    assert framing["thesis"]["bullets"] == []


def test_mapper_levers_are_plain_strings_that_satisfy_the_bundle_schema():
    """Schema round trip: the mapper emits list[str], and that is exactly what
    ``company_framing.thesis`` declares. This is the subschema
    ``validate.py::validate_bundle`` applies inside ``BundleBuilder.build``, so
    a dict-shaped lever would fail a whole VDR run, not just this block."""
    import jsonschema
    import yaml as _yaml
    from pathlib import Path

    snapshots = {
        "business_model": {
            "yaml_dict": {
                "executive_summary": "A consulting firm.",
                "recent_model_changes": [
                    {"change_type": "ma", "description": "Acquired operator A",
                     "approximate_date": "2024-06"},
                ],
                "workforce_capacity": {"workforce_model": {"offshore_pct_of_total": "8%"}},
            },
            "delta_row": {},
        },
        "financial_trends": {"yaml_dict": {}, "delta_row": {}},
        "customer_quality": {"yaml_dict": {}, "delta_row": {}},
        "kpi": {"yaml_dict": {}, "delta_row": {}},
        "quality_of_earnings": {"yaml_dict": {}, "delta_row": {}},
        "legal": {"yaml_dict": {}, "delta_row": {}},
    }
    partial = apply_field_mappings(
        snapshots,
        {"industry_overlay": "tech_services"},
        {"company_name": "Test Co", "generated_at": "2026-09-17T00:00:00Z"},
    )
    levers = partial["company_framing"]["thesis"]["value_creation_levers"]
    assert levers, "the fixture produced no levers — the check would pass vacuously"
    assert all(isinstance(lever, str) for lever in levers)

    schema = _yaml.safe_load(
        (
            Path(__file__).resolve().parents[1]
            / "databricks/agents/exec_summary/orchestrator_bundle.schema.yaml"
        ).read_text(encoding="utf-8")
    )
    jsonschema.Draft7Validator(
        {"$ref": "#/definitions/company_framing", "definitions": schema["definitions"]}
    ).validate(partial["company_framing"])


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


# ---------------------------------------------------------------------------
# Segment performance and derived concentration — the rest of the same sweep.
# financials.segment_performance was never written (only geographic_mix was),
# so the segment section rendered "not extracted" even for Elder Care, whose
# agent had five locations × five periods with dollar revenue on each.
# ---------------------------------------------------------------------------


def test_segment_performance_collapses_periods_to_the_latest_per_segment():
    fta_yaml = {
        "revenue_by_segment": [
            {"segment": "New York", "revenue_dollars": "1,525", "period": "2020A"},
            {"segment": "New York", "revenue_dollars": "13,588", "period": "TTM Aug-24"},
            {"segment": "New Jersey", "revenue_dollars": "900", "period": "2020A"},
        ],
    }
    rows = _segment_performance_from_fta(fta_yaml)
    by_name = {r["name"]: r for r in rows}
    assert by_name["New York"]["revenue"] == "13,588"
    assert by_name["New Jersey"]["revenue"] == "900"


def test_segment_performance_drops_a_segment_with_no_figure_at_all():
    """GKF's real shape: a named segment whose revenue_pct and revenue_dollars
    are both null. A bar of unknown height is worse than an empty section."""
    rows = _segment_performance_from_fta(
        {"revenue_by_segment": [{"segment": "Tysons Kids", "revenue_pct": None, "revenue_dollars": None}]}
    )
    assert rows == []


def test_segment_performance_empty_when_agent_extracted_none():
    assert _segment_performance_from_fta({"revenue_by_segment": []}) == []
    assert _segment_performance_from_fta(None) == []


def test_period_sort_key_orders_trailing_and_suffixed_labels_chronologically():
    labels = ["TTM Aug-24", "2020A", "FY23", "2025B", "2022A"]
    assert sorted(labels, key=period_sort_key) == ["2020A", "2022A", "FY23", "TTM Aug-24", "2025B"]


def test_money_to_dollars_honours_a_spelled_out_magnitude():
    assert money_to_dollars("$59,699 thousand") == 59_699_000.0
    assert money_to_dollars("$10,917,799") == 10_917_799.0
    assert money_to_dollars("$1.2 million") == 1_200_000.0
    assert money_to_dollars(None) is None
    assert money_to_dollars("not a number") is None


def test_derived_share_uses_dollars_when_the_agent_stated_no_percentage():
    """Clearsulting's real shape: every top*_pct null, clients carrying real
    dollars, company revenue stated in thousands."""
    customers = [{"customer_name": "Client 1", "revenue_pct_yr1": None,
                  "revenue_dollars": "2024: $10,917,799; 2023: $11,589,127"}]
    fta_yaml = {"revenue_trend": [{"revenue_stated": "$59,699 thousand"}]}
    enriched, note = _derive_customer_shares(customers, fta_yaml)
    assert enriched[0]["revenue_pct_yr1"] == "18.3%"
    assert enriched[0]["share_is_derived"] is True
    assert "computed" in note


def test_derived_share_is_discarded_when_the_magnitudes_disagree():
    """The guard that matters: company total read as bare thousands against
    per-client raw dollars yields 18,288%. Publish nothing rather than that."""
    customers = [{"customer_name": "Client 1", "revenue_pct_yr1": None,
                  "revenue_dollars": "$10,917,799"}]
    fta_yaml = {"revenue_trend": [{"revenue_stated": "$59,699"}]}
    enriched, note = _derive_customer_shares(customers, fta_yaml)
    assert enriched[0]["revenue_pct_yr1"] is None
    assert note == ""


def test_derived_share_never_overwrites_a_stated_percentage():
    customers = [{"customer_name": "C", "revenue_pct_yr1": "12%", "revenue_dollars": "$1"}]
    fta_yaml = {"revenue_trend": [{"revenue_stated": "$100"}]}
    enriched, _ = _derive_customer_shares(customers, fta_yaml)
    assert enriched[0]["revenue_pct_yr1"] == "12%"
    assert "share_is_derived" not in enriched[0]


def test_derived_share_divides_by_the_same_year_not_the_largest_period():
    """Numerator and denominator must describe the same window. The client
    figure names 2024; dividing it by TTM25 revenue understates every share,
    quietly and plausibly — the kind of wrong number a reader cannot catch."""
    customers = [{"customer_name": "C", "revenue_pct_yr1": None,
                  "revenue_dollars": "2024: $10,000,000"}]
    fta_yaml = {"revenue_trend": [
        {"period": "2024", "revenue_stated": "$50,000 thousand"},
        {"period": "TTM25", "revenue_stated": "$100,000 thousand"},
    ]}
    enriched, _ = _derive_customer_shares(customers, fta_yaml)
    assert enriched[0]["revenue_pct_yr1"] == "20.0%"  # 10M/50M, not 10M/100M


def test_derived_share_falls_back_to_latest_when_the_client_names_no_period():
    customers = [{"customer_name": "C", "revenue_pct_yr1": None, "revenue_dollars": "$10,000,000"}]
    fta_yaml = {"revenue_trend": [
        {"period": "2023", "revenue_stated": "$40,000 thousand"},
        {"period": "2024", "revenue_stated": "$50,000 thousand"},
    ]}
    enriched, _ = _derive_customer_shares(customers, fta_yaml)
    assert enriched[0]["revenue_pct_yr1"] == "20.0%"


# ---------------------------------------------------------------------------
# Quality of earnings — the section the recommendation leans on hardest, and
# the one rendering "Addbacks — not extracted" over a full ledger.
# ---------------------------------------------------------------------------


def test_addbacks_map_from_the_qoe_ledger():
    snap = {"yaml_dict": {"addback_ledger": [
        {"description": "Separation agreement [A]", "amount_dollars": "256",
         "period": "TTM25", "tier_classification": "Tier 4",
         "tier_rationale": "No supporting document referenced."},
    ]}}
    rows = _addbacks_from_qoe(snap)
    assert rows[0]["label"] == "Separation agreement [A]"
    assert rows[0]["amount"] == "256"
    assert rows[0]["tier"] == "Tier 4"


def test_addbacks_read_the_delta_json_column_when_no_yaml():
    snap = {"delta_row": {"addback_ledger_json": json.dumps(
        [{"description": "Signing bonus [B]", "amount_dollars": "95", "tier_classification": "Tier 4"}]
    )}}
    rows = _addbacks_from_qoe(snap)
    assert rows[0]["label"] == "Signing bonus [B]"


def test_addbacks_skip_an_item_with_no_amount():
    snap = {"yaml_dict": {"addback_ledger": [{"description": "Unpriced item", "amount_dollars": None}]}}
    assert _addbacks_from_qoe(snap) == []


def test_addbacks_empty_when_the_agent_produced_no_ledger():
    assert _addbacks_from_qoe(None) == []
    assert _addbacks_from_qoe({"yaml_dict": {}}) == []


def test_qoe_reads_the_real_percentage_column_not_the_short_name():
    """The column is total_addbacks_pct_of_ebitda. Reading the short name
    always returned None and fell through to FTA's own figure — how a caption
    came to read "Addbacks total 569.3 of reported EBITDA"."""
    snap = {"delta_row": {"total_addbacks_pct_of_ebitda": 12.2}}
    fta = {"addback_schedule": {"addback_pct_of_ebitda": 569.3}}
    result = _qoe_from_snapshots(snap, fta)
    assert result["addback_pct_of_ebitda"] == "12.2%"


def test_qoe_still_falls_back_to_fta_when_the_agent_computed_none():
    result = _qoe_from_snapshots({"delta_row": {}}, {"addback_schedule": {"addback_pct_of_ebitda": "40%"}})
    assert result["addback_pct_of_ebitda"] == "40%"
