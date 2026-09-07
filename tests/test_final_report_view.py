"""Unit tests for agents.exec_summary.final_report_view — the numeric contract.

This is the only place in the final-report feature that does arithmetic
(docs/plans/final_report/tasks/T03_view_numeric_tests.md), so this file pins
the behaviour that must never regress: an absent figure stays ``None`` all
the way to the page (never silently becomes ``0``), scaling and CAGR math
never fabricate or explode, the sector screens flag the correct side of a
threshold, and every cap is a hard ceiling read from the module's own
constants.

Modelled on ``tests/test_rainmaker_view.py`` — same style, same level of
mocking (none: this module is pure and is exercised through its public
surface, including the leading-underscore section builders, which is the
established convention in ``tests/test_final_report_numeric_parity.py``).
"""

from __future__ import annotations

import pytest

from agents.exec_summary import final_report_view as frv


# =========================================================================
# 1. `None` never becomes `0`
# =========================================================================

@pytest.mark.parametrize("value", [None, "", "n/a", "N/A", "-", "—"])
def test_parse_money_absent_is_none(value):
    assert frv.parse_money(value) is None


@pytest.mark.parametrize("value", [None, "", "n/a", "N/A"])
def test_parse_percent_absent_is_none(value):
    assert frv.parse_percent(value) is None


def test_parse_money_zero_stays_zero_not_none():
    # 0 is a figure; only an absence is None. A parser that maps "0" to None
    # would be indistinguishable from one that maps it to a fabricated 0.
    assert frv.parse_money("0") == 0.0
    assert frv.parse_money("0") is not None


def test_pnl_table_empty_bundle_produces_not_extracted_shape():
    view = frv._pnl_table({})
    assert view["periods"] == []
    assert view["rows"] == []  # not a zero-filled row set


def test_pnl_table_missing_field_in_populated_period_is_none_not_zero():
    bundle = {
        "financials": {
            "table_rows": [
                {"year": "2023A", "revenue": "10"},
                {"year": "2024A", "ebitda_margin_pct": "10%"},  # no "revenue" this period
            ]
        }
    }
    view = frv._pnl_table(bundle)
    revenue_row = next(r for r in view["rows"] if r["label"] == "Revenue")
    assert revenue_row["cells"][1] is None
    assert revenue_row["cells"][1] != 0


def test_trend_chart_bar_is_none_not_zero_when_revenue_absent():
    bundle = {"financials": {"table_rows": [{"year": "2024A", "ebitda_margin_pct": "10%"}]}}
    chart = frv._trend_chart(bundle)
    # Assert on `is None`, not falsiness: `0 == None` is False but `not 0` is
    # True, so a truthiness assertion would pass on the bug this pins.
    assert chart["series"][0]["bar1_pct"] is None
    assert chart["series"][0]["bar1_value"] is None


def test_final_report_view_on_empty_bundle_produces_not_extracted_shapes():
    view = frv.final_report_view({})
    assert view["financials"]["table"]["rows"] == []
    assert view["kpis"]["rows"] == []
    assert view["risks"]["grid"] == []
    assert view["questions"] == []
    assert view["appendix"]["gaps"] == []
    assert view["customers"]["top_customers"] == []
    assert view["business"]["revenue_mix"]["segments"] == []


# =========================================================================
# 2. `scale()`
# =========================================================================

def test_scale_all_none_stays_all_none():
    assert frv.scale([None, None]) == [None, None]


def test_scale_none_inside_populated_list_stays_none():
    result = frv.scale([10.0, None, 20.0])
    assert result[1] is None
    assert result[0] == 50.0
    assert result[2] == 100.0


def test_scale_never_exceeds_100():
    result = frv.scale([150.0], max_value=100.0)
    assert result[0] is not None
    assert result[0] <= 100.0


def test_scale_largest_input_maps_to_100_by_default():
    result = frv.scale([10.0, 20.0])
    assert result[1] == 100.0


def test_scale_largest_input_maps_to_explicit_max_value():
    result = frv.scale([10.0, 20.0], max_value=20.0)
    assert result[1] == 100.0


@pytest.mark.parametrize("max_value", [0.0, -10.0])
def test_scale_nonpositive_max_value_does_not_raise_or_produce_inf_nan(max_value):
    result = frv.scale([5.0], max_value=max_value)
    assert all(v is None or (v == v and abs(v) != float("inf")) for v in result)  # v == v rules out NaN


# =========================================================================
# 3. `_calc_column()`
# =========================================================================

def test_calc_column_none_when_period_missing():
    # Only one value present (n_periods matches len(nums), the real call
    # shape) — fewer than 2 populated points, no CAGR is computable.
    assert frv._calc_column([100.0, None], "money", 2) is None


@pytest.mark.parametrize("first", [0.0, -5.0])
def test_calc_column_none_when_starting_value_nonpositive(first):
    assert frv._calc_column([first, 10.0], "money", 2) is None


@pytest.mark.parametrize("nums", [[], [100.0]])
def test_calc_column_none_when_n_periods_is_zero_or_one(nums):
    # n_periods mirrors len(periods) at the real call site (`_pnl_table`
    # passes `len(periods)`), so 0/1 periods means at most one populated
    # value — never enough to compute a CAGR or YoY delta.
    assert frv._calc_column(nums, "money", len(nums)) is None


def test_calc_column_known_good_yoy():
    # 100 -> 121 over one step is exactly +21% YoY (span < 2, so the YoY
    # branch runs regardless of n_periods).
    assert frv._calc_column([100.0, 121.0], "money", 2) == "+21.0%"


def test_calc_column_known_good_cagr():
    # 100 -> 133.1 over 3 periods (span 3, cube root of 1.331 is exactly
    # 1.1): a clean 10.0% CAGR, hand-verifiable without a calculator.
    assert frv._calc_column([100.0, None, None, 133.1], "money", 4) == "10.0%"


def test_calc_column_known_good_percent_delta():
    assert frv._calc_column([10.0, 15.5], "percent", 2) == "+5.5 pp"


# =========================================================================
# 4. Threshold screens (`_SCREENS`, `_kpi_scorecard`, `_retention_rows`)
# =========================================================================

_SECTORS = sorted({s["sector"] for s in frv._SCREENS})


def _first_screen(sector: str, direction: str) -> dict:
    return next(s for s in frv._SCREENS if s["sector"] == sector and s["dir"] == direction)


def _kpi_row(view: dict, name: str) -> dict:
    return next(r for r in view["rows"] if r["name"] == name)


@pytest.mark.parametrize("sector", _SECTORS)
def test_kpi_scorecard_min_direction_flags_below_not_above(sector):
    screen = _first_screen(sector, "min")
    bundle = {
        "kpi_dashboard": [
            {"metric_id": screen["key"], "display_name": "Below", "stated_value": f"{screen['threshold'] - 5}%"},
            {"metric_id": screen["key"], "display_name": "Above", "stated_value": f"{screen['threshold'] + 5}%"},
        ]
    }
    view = frv._kpi_scorecard(bundle, sector)
    assert _kpi_row(view, "Below")["flag"] is True
    assert _kpi_row(view, "Above")["flag"] is False


@pytest.mark.parametrize("sector", _SECTORS)
def test_kpi_scorecard_max_direction_flags_above_not_below(sector):
    screen = _first_screen(sector, "max")
    bundle = {
        "kpi_dashboard": [
            {"metric_id": screen["key"], "display_name": "Below", "stated_value": f"{screen['threshold'] - 5}%"},
            {"metric_id": screen["key"], "display_name": "Above", "stated_value": f"{screen['threshold'] + 5}%"},
        ]
    }
    view = frv._kpi_scorecard(bundle, sector)
    assert _kpi_row(view, "Below")["flag"] is False
    assert _kpi_row(view, "Above")["flag"] is True


@pytest.mark.parametrize("sector", _SECTORS)
def test_kpi_scorecard_boundary_value_is_not_flagged(sector):
    # Pinned deliberately: both directions compare with a strict `<`/`>`, so
    # a value exactly at the threshold is never flagged, for either
    # direction. This test documents that choice rather than the opposite.
    screen = _first_screen(sector, "min")
    bundle = {"kpi_dashboard": [{"metric_id": screen["key"], "display_name": "AtThreshold", "stated_value": f"{screen['threshold']}%"}]}
    view = frv._kpi_scorecard(bundle, sector)
    assert _kpi_row(view, "AtThreshold")["flag"] is False


@pytest.mark.parametrize("sector", _SECTORS)
def test_kpi_scorecard_metric_with_no_screen_is_not_flagged_and_does_not_raise(sector):
    bundle = {"kpi_dashboard": [{"metric_id": "totally_unscreened_metric", "display_name": "Unscreened", "stated_value": "50.0%"}]}
    view = frv._kpi_scorecard(bundle, sector)
    assert _kpi_row(view, "Unscreened")["flag"] is False


def test_retention_rows_min_direction_flags_below_not_above():
    # nrr_pct/grr_pct screens exist only for tech_services (§_SCREENS), and
    # `_retention_rows` always compares with `<` (both its screened metrics
    # are "min"-direction), so this pins the one direction the function
    # implements.
    key = "nrr_pct"
    threshold = next(s["threshold"] for s in frv._SCREENS if s["key"] == key and s["sector"] == "tech_services")
    below = frv._retention_rows({"revenue_quality": {"retention": {key: f"{threshold - 5}%"}}}, "tech_services")
    assert below[0]["read_class"] == "high"
    above = frv._retention_rows({"revenue_quality": {"retention": {key: f"{threshold + 5}%"}}}, "tech_services")
    assert above[0]["read_class"] == "low"


def test_retention_rows_metric_with_no_screen_is_not_flagged_and_does_not_raise():
    # logo_churn_rate_annual_pct has no screen in either sector.
    bundle = {"revenue_quality": {"retention": {"logo_churn_rate_annual_pct": "19%"}}}
    for sector in _SECTORS:
        rows = frv._retention_rows(bundle, sector)
        assert rows[0]["read_class"] == "neutral"
        assert rows[0]["read_label"] == "No screen"


# =========================================================================
# 5. Caps
# =========================================================================

def test_cap_thesis_bullets():
    narrative = {"thesis_bullets": [f"thesis {i}" for i in range(frv.CAP_THESIS + 3)]}
    view = frv.final_report_view({}, narrative)
    assert len(view["headline"]["thesis"]) == frv.CAP_THESIS


def test_cap_watchouts():
    narrative = {"key_watchouts": [f"watchout {i}" for i in range(frv.CAP_WATCHOUTS + 3)]}
    view = frv.final_report_view({}, narrative)
    assert len(view["headline"]["watchouts"]) == frv.CAP_WATCHOUTS


def test_cap_bullets():
    bundle = {"company_framing": {"overview_bullets": [f"bullet {i}" for i in range(frv.CAP_BULLETS + 3)]}}
    view = frv.final_report_view(bundle)
    assert len(view["business"]["what_it_does"]) == frv.CAP_BULLETS


def test_cap_segments():
    bundle = {"revenue_quality": {"revenue_type_mix": [{"label": f"seg {i}", "pct_of_revenue": str(i + 1)} for i in range(frv.CAP_SEGMENTS + 3)]}}
    view = frv.final_report_view(bundle)
    assert len(view["business"]["revenue_mix"]["segments"]) == frv.CAP_SEGMENTS


def test_cap_top_customers():
    bundle = {"revenue_quality": {"top_customers": [{"customer_name": f"cust {i}", "revenue_pct_yr1": "5%"} for i in range(frv.CAP_TOP_CUSTOMERS + 3)]}}
    view = frv.final_report_view(bundle)
    assert len(view["customers"]["top_customers"]) == frv.CAP_TOP_CUSTOMERS


def test_cap_kpis():
    bundle = {"kpi_dashboard": [{"metric_id": f"metric_{i}", "display_name": f"KPI {i}", "stated_value": "50.0%"} for i in range(frv.CAP_KPIS + 3)]}
    view = frv.final_report_view(bundle)
    assert len(view["kpis"]["rows"]) == frv.CAP_KPIS


def test_cap_risks():
    bundle = {"risks": [{"risk": f"risk {i}", "severity": "low"} for i in range(frv.CAP_RISKS + 3)]}
    view = frv.final_report_view(bundle)
    assert len(view["risks"]["grid"]) == frv.CAP_RISKS


def test_cap_questions():
    bundle = {"diligence_questions": [{"category": "General", "question": f"question {i}?"} for i in range(frv.CAP_QUESTIONS + 3)]}
    view = frv.final_report_view(bundle)
    assert len(view["questions"]) == frv.CAP_QUESTIONS


def test_cap_gaps():
    bundle = {"data_room_gaps": [{"item": f"gap {i}", "priority": "low"} for i in range(frv.CAP_GAPS + 3)]}
    view = frv.final_report_view(bundle)
    assert len(view["appendix"]["gaps"]) == frv.CAP_GAPS


def test_cap_tiles(monkeypatch):
    # `_headline_tiles` reads from a fixed 6-field spec, which already equals
    # CAP_TILES today, so there is no way to feed it "cap+3" inputs. Instead,
    # patch the module constant itself and confirm `final_report_view`'s
    # `[:CAP_TILES]` slice actually reads it at call time — the same
    # intent-preserving check ("raising the cap breaks the intent, not the
    # test") applied the other way.
    monkeypatch.setattr(frv, "CAP_TILES", 3)
    headline = {
        "ltm_revenue": "$1M", "revenue_cagr": "5%", "ltm_ebitda": "$1M",
        "ltm_ebitda_margin_pct": "10%", "top1_concentration_pct": "10%",
        "enterprise_value_indicated": "$5M",
    }
    view = frv.final_report_view({"headline_metrics": headline})
    assert len(view["headline"]["tiles"]) == 3


# =========================================================================
# 6. P&L rows
# =========================================================================

def test_pnl_row_dropped_when_absent_in_every_period():
    bundle = {
        "financials": {
            "table_rows": [
                {"year": "2023A", "revenue": "10"},
                {"year": "2024A", "revenue": "12"},
            ]
        }
    }
    view = frv._pnl_table(bundle)
    labels = {r["label"] for r in view["rows"]}
    assert "Capital expenditure" not in labels  # never populated -> dropped, not rendered empty


def test_pnl_row_kept_with_none_in_missing_cells_when_partially_present():
    bundle = {
        "financials": {
            "table_rows": [
                {"year": "2023A", "revenue": "10", "capex": "1.5"},
                {"year": "2024A", "revenue": "12"},  # capex absent this period
            ]
        }
    }
    view = frv._pnl_table(bundle)
    capex_row = next(r for r in view["rows"] if r["label"] == "Capital expenditure")
    assert capex_row["cells"][0] == "1.5"
    assert capex_row["cells"][1] is None


# =========================================================================
# 7. Deduplication and `why_it_matters`
# =========================================================================

def test_questions_dedupe_case_insensitive():
    bundle = {
        "diligence_questions": [
            {"category": "General", "question": "What drives churn?"},
            {"category": "General", "question": "WHAT DRIVES CHURN?"},
            {"category": "General", "question": "What else drives churn?"},
        ]
    }
    out = frv._questions(bundle)
    assert len(out) == 2


def test_questions_respects_cap():
    bundle = {"diligence_questions": [{"category": "General", "question": f"question {i}?"} for i in range(frv.CAP_QUESTIONS + 3)]}
    out = frv._questions(bundle)
    assert len(out) == frv.CAP_QUESTIONS


def test_questions_why_is_none_when_absent():
    bundle = {"diligence_questions": [{"category": "General", "question": "What drives churn?"}]}
    out = frv._questions(bundle)
    assert out[0]["why"] is None
