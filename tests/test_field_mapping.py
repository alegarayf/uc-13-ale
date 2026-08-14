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

from agents.exec_summary.field_mapping import _fta_table_rows, _headline_from_fta


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
