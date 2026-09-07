"""Numeric parity between final_report_view.py and rainmaker_view.py.

T02 (docs/plans/final_report/tasks/T02_bundle_field_audit.md) adopts the
Sep-4 period-ordering and unit-normalisation fixes from ``rainmaker_view``
into ``final_report_view`` (plan §1.6), and de-duplicates the money/percent
parsers where they are proven equivalent (plan §1.4 step 6). Both documents
render the same bundle, so a silent disagreement here would move a number on
one page relative to the other with no way for a reader to know which is
right.
"""

from __future__ import annotations

import pytest

from agents.exec_summary import final_report_view as frv
from agents.exec_summary import rainmaker_view as rv

# --- parse_percent: proven equivalent, final_report_view.parse_percent -----
# delegates to rainmaker_view._parse_percent outright.

_PARSE_INPUTS = [
    None, "", "$1.2M", "1,234", "(500)", "12.5%", "n/a", "N/A",
    1234.5, -5, "-", "—", "–", "0", "(0.3)",
    "42.3% (Historical) / 44.3% (Pro Forma — DISCREPANCY)",
]


@pytest.mark.parametrize("value", _PARSE_INPUTS)
def test_parse_percent_matches_rainmaker_view(value):
    assert frv.parse_percent(value) == rv._parse_percent(value)


@pytest.mark.parametrize("value", _PARSE_INPUTS)
def test_parse_money_matches_rainmaker_view_on_non_suffix_inputs(value):
    assert frv.parse_money(value) == rv._parse_money(value)


# --- parse_money: documented divergence on magnitude suffixes --------------
# rainmaker_view._parse_money has no k/b/bn suffix handling; final_report_view
# does. Per plan §1.4 step 6, a disagreement means the inline copy stays and
# the divergence is pinned here rather than silently delegated.

@pytest.mark.parametrize(
    "value,final_report_expected,rainmaker_expected",
    [("2k", 0.002, 2.0), ("1.5bn", 1500.0, 1.5), ("1.5b", 1500.0, 1.5)],
)
def test_parse_money_diverges_from_rainmaker_view_on_magnitude_suffixes(
    value, final_report_expected, rainmaker_expected
):
    assert frv.parse_money(value) == final_report_expected
    assert rv._parse_money(value) == rainmaker_expected


# --- P&L column order and stated unit: must be identical across documents --

def test_pnl_period_order_and_unit_label_match_executive_review():
    """Periods out of emission order, plus one period extracted in a
    different unit than its neighbours (a real defect Sep-4 fixed for the
    executive review) — both documents must land on the same column order
    and the same stated unit."""
    bundle = {
        "meta": {"company_name": "Test Co", "vertical_overlay": "tech_services"},
        "headline_metrics": {"ltm_revenue": "$48.2M"},
        "financials": {
            "currency": "$",
            "table_rows": [
                {"year": "2022A", "revenue": "44.2", "ebitda_margin_pct": "10%"},
                # extracted in raw dollars while its neighbours are in millions
                {"year": "2021A", "revenue": "38000", "ebitda_margin_pct": "9%"},
                {"year": "LTM MAY 2025", "revenue": "48.2", "ebitda_margin_pct": "11%"},
                {"year": "2023A", "revenue": "40.1", "ebitda_margin_pct": "9.5%"},
            ],
        },
    }

    er = rv._financial_table(bundle)
    fr = frv._pnl_table(bundle)

    expected_periods = ["2021A", "2022A", "2023A", "LTM MAY 2025"]
    assert fr["periods"] == expected_periods
    assert er["periods"] == expected_periods
    assert fr["unit_label"] == er["unit_label"] == "in millions"


# --- P&L cell values: the two documents must agree, not just on order/unit --
# DoE-14 cares about the cell values themselves, which the test above does not
# assert. Same period-order-and-unit-outlier shape as above so the reordering
# and rescaling machinery is exercised, not just a trivially-ordered bundle.
# Row-name map because the two documents label rows differently (ER:
# "Total Revenue"/"EBITDA", final report: "Revenue"/"EBITDA") even though
# both read the same ``revenue``/``ebitda`` bundle fields through the same
# ``_normalize_period_units(_financial_periods(bundle))`` pipeline.
_ROW_NAME_MAP = {"Revenue": "Total Revenue", "EBITDA": "EBITDA"}


def test_pnl_cell_values_match_executive_review_for_revenue_and_ebitda():
    bundle = {
        "meta": {"company_name": "Test Co", "vertical_overlay": "tech_services"},
        "headline_metrics": {"ltm_revenue": "$48.2M"},
        "financials": {
            "currency": "$",
            "table_rows": [
                {"year": "2022A", "revenue": "44.2", "ebitda": "4.4", "ebitda_margin_pct": "10%"},
                # extracted in raw dollars while its neighbours are in millions
                {"year": "2021A", "revenue": "38000", "ebitda": "3420", "ebitda_margin_pct": "9%"},
                {"year": "LTM MAY 2025", "revenue": "48.2", "ebitda": "5.3", "ebitda_margin_pct": "11%"},
                {"year": "2023A", "revenue": "40.1", "ebitda": "3.8", "ebitda_margin_pct": "9.5%"},
            ],
        },
    }

    er = rv._financial_table(bundle)
    fr = frv._pnl_table(bundle)

    er_rows_by_name = {row["metric_name"]: row for row in er["rows"]}
    fr_rows_by_name = {row["label"]: row for row in fr["rows"]}

    for fr_name, er_name in _ROW_NAME_MAP.items():
        # Not asserted here: the growth/CAGR column. The ER formats to whole
        # percent ("8%"), the final report to one decimal ("8.2%") — same
        # underlying value, different presentation, deliberately (see
        # docs/plans/final_report/final_report_plan.md §9). Only "cells" is
        # compared.
        assert fr_rows_by_name[fr_name]["cells"] == er_rows_by_name[er_name]["cells"]
