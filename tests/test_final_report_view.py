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


# =========================================================================
# 8. Format policy — caps and screens pinned as literals (T03b)
#
# These numbers are FORMAT POLICY (plan §2.2: "caps are part of the format"),
# and the screens encode Rallyday's sector screening rules. A test that reads
# its expectation from the constant it is testing moves when that constant
# moves and cannot catch an accidental edit — that is what let two mutants
# (CAP_QUESTIONS 8 -> 12, nrr_pct "dir": "min" -> "max") survive T03's suite.
# This section is meant to fail when a value changes. If a cap or a screen
# genuinely should move, change it here too, in the same commit, with the
# reason in the commit message. Do not "fix" this test by reading the
# constant.
# =========================================================================

_EXPECTED_CAPS = {
    "CAP_TILES": 6,
    "CAP_THESIS": 3,
    "CAP_WATCHOUTS": 3,
    "CAP_BULLETS": 4,
    "CAP_SEGMENTS": 6,
    "CAP_TOP_CUSTOMERS": 5,
    "CAP_KPIS": 8,
    "CAP_RISKS": 8,
    "CAP_QUESTIONS": 8,
    "CAP_GAPS": 10,
}


@pytest.mark.parametrize("name, expected", sorted(_EXPECTED_CAPS.items()))
def test_cap_constant_pinned_literally(name, expected):
    assert getattr(frv, name) == expected


def test_expected_caps_covers_every_cap_constant_in_the_module():
    # A new CAP_* constant must land in _EXPECTED_CAPS in the same commit
    # that adds it, or this test fails.
    module_caps = {name for name in vars(frv) if name.startswith("CAP_")}
    assert module_caps == set(_EXPECTED_CAPS)


# (sector, key, threshold, dir) — the whole `_SCREENS` table, pinned.
_EXPECTED_SCREENS = {
    ("tech_services", "nrr_pct", 90, "min"),
    ("tech_services", "grr_pct", 85, "min"),
    ("tech_services", "gross_margin_pct", 40, "min"),
    ("tech_services", "top1_pct", 25, "max"),
    ("tech_services", "organic_growth_pct", 10, "min"),
    ("tech_services", "ebitda_margin_pct", 10, "min"),
    ("tech_services", "avg_account_size", 100, "min"),
    ("healthcare_services", "revenue_growth_pct", 5, "min"),
    ("healthcare_services", "ebitda_margin_pct", 10, "min"),
    ("healthcare_services", "gross_margin_pct", 30, "min"),
    ("healthcare_services", "top1_pct", 20, "max"),
    ("healthcare_services", "government_payor_pct", 50, "max"),
    ("healthcare_services", "employee_turnover_pct", 30, "max"),
    ("healthcare_services", "utilization_pct", 70, "min"),
}


def test_screens_table_pinned_literally():
    actual = {(s["sector"], s["key"], s["threshold"], s["dir"]) for s in frv._SCREENS}
    assert actual == _EXPECTED_SCREENS
    assert len(frv._SCREENS) == 14


def test_screen_nrr_pct_min_direction_hardcoded_threshold():
    # _SCREENS says tech_services/nrr_pct is threshold=90, dir="min" — written
    # here as literals, not read from _SCREENS, so a flipped "dir" or a moved
    # threshold in the module cannot make this test agree with the bug.
    below = frv._retention_rows({"revenue_quality": {"retention": {"nrr_pct": "85%"}}}, "tech_services")
    assert below[0]["read_class"] == "high"
    above = frv._retention_rows({"revenue_quality": {"retention": {"nrr_pct": "95%"}}}, "tech_services")
    assert above[0]["read_class"] == "low"


def test_screen_top1_pct_max_direction_hardcoded_threshold():
    # _SCREENS says tech_services/top1_pct is threshold=25, dir="max" —
    # written here as literals for the same reason as above.
    bundle_flagged = {"kpi_dashboard": [{"metric_id": "top1_pct", "display_name": "Top1", "stated_value": "30%"}]}
    view = frv._kpi_scorecard(bundle_flagged, "tech_services")
    assert _kpi_row(view, "Top1")["flag"] is True

    bundle_not_flagged = {"kpi_dashboard": [{"metric_id": "top1_pct", "display_name": "Top1", "stated_value": "20%"}]}
    view = frv._kpi_scorecard(bundle_not_flagged, "tech_services")
    assert _kpi_row(view, "Top1")["flag"] is False


# =========================================================================
# _forecast — plan §1.7: say the absent projected EBITDA margin out loud
# =========================================================================

_NO_MARGIN_CLAUSE = "The plan does not state a projected EBITDA margin."


def test_forecast_footnote_gains_clause_when_plan_rows_carry_no_margin():
    bundle = {
        "financials": {
            "table_rows": [{"year": "2023A", "revenue": "10"}],
            "forecast_rows": [{"year": "2024P", "revenue": "12"}],  # no ebitda_margin_pct
        }
    }
    forecast = frv._forecast(bundle, {})
    assert _NO_MARGIN_CLAUSE in forecast["chart"]["footnote"]


def test_forecast_footnote_omits_clause_when_plan_rows_state_a_margin():
    bundle = {
        "financials": {
            "table_rows": [{"year": "2023A", "revenue": "10"}],
            "forecast_rows": [{"year": "2024P", "revenue": "12", "ebitda_margin_pct": "15%"}],
        }
    }
    forecast = frv._forecast(bundle, {})
    assert _NO_MARGIN_CLAUSE not in forecast["chart"]["footnote"]


def test_forecast_footnote_omits_clause_when_there_are_no_plan_rows():
    bundle = {"financials": {"table_rows": [{"year": "2023A", "revenue": "10"}]}}
    forecast = frv._forecast(bundle, {})
    assert _NO_MARGIN_CLAUSE not in forecast["chart"]["footnote"]


# =========================================================================
# 8. T11 — kpis.take, the recommendation adapter, core_business threading
# =========================================================================


def test_kpi_scorecard_take_reads_from_narrative():
    view = frv._kpi_scorecard({}, "tech_services", {"kpi_take": "ARR of $5M against screens."})
    assert view["take"] == "ARR of $5M against screens."


def test_kpi_scorecard_take_is_none_without_narrative():
    assert frv._kpi_scorecard({}, "tech_services")["take"] is None
    assert frv._kpi_scorecard({}, "tech_services", {})["take"] is None


def test_recommendation_passes_through_a_dict_unchanged():
    rec = {"verdict": "Proceed", "rationale": "Because.", "conditions": ["A"], "tone": "pass"}
    assert frv._recommendation({"recommendation": rec}) == rec


def test_recommendation_wraps_a_bare_string_as_rationale():
    """A degraded T11 call plus a successful ER one can leave `recommendation`
    as a plain sentence. The template reads `rec.verdict`/`rec.rationale`; a
    bare string must not silently print 'Not yet concluded' over a usable
    sentence."""
    wrapped = frv._recommendation({"recommendation": "Worthy of pursuit because of A, B and C."})
    assert wrapped == {
        "verdict": None,
        "rationale": "Worthy of pursuit because of A, B and C.",
        "conditions": [],
        "tone": None,
    }


def test_recommendation_defaults_when_absent():
    assert frv._recommendation({}) == {"verdict": None, "rationale": None, "conditions": []}


def test_recommendation_defaults_when_empty_string():
    assert frv._recommendation({"recommendation": ""}) == {"verdict": None, "rationale": None, "conditions": []}


def test_final_report_view_threads_recommendation_dict_into_headline():
    narrative = {"recommendation": {"verdict": "Proceed", "rationale": "R", "conditions": [], "tone": "pass"}}
    view = frv.final_report_view({}, narrative)
    assert view["headline"]["recommendation"]["verdict"] == "Proceed"


def test_final_report_view_business_core_business_from_narrative_capped_at_three():
    narrative = {"core_business": ["line one", "line two", "line three", "line four"]}
    view = frv.final_report_view({}, narrative)
    assert view["business"]["core_business"] == ["line one", "line two", "line three"]


def test_final_report_view_business_core_business_absent_is_empty_list():
    view = frv.final_report_view({}, {})
    assert view["business"]["core_business"] == []


# Six take-box sites the template guards with `{%- if report.X.take %}`
# (final_report.html.j2:521,591,649,696,745,788). A full narrative populates
# all six; a degraded one (all fields None, per final_report_narrative's
# contract) must leave every site falsy so the template renders zero boxes
# and no page goes missing.
_ALL_SIX_TAKES_NARRATIVE = {
    "business_take": "b",
    "financial_take": "f",
    "customer_take": "c",
    "kpi_take": "k",
    "quality_take": "q",
    "forecast_take": "fc",
}
_DEGRADED_NARRATIVE = {key: None for key in _ALL_SIX_TAKES_NARRATIVE}


def _take_sites(view: dict) -> list:
    return [
        view["business"]["take"],
        view["financials"]["take"],
        view["customers"]["take"],
        view["kpis"]["take"],
        view["quality"]["take"],
        view["forecast"]["take"],
    ]


def test_final_report_view_renders_all_six_take_boxes_with_full_narrative():
    view = frv.final_report_view({}, _ALL_SIX_TAKES_NARRATIVE)
    assert all(_take_sites(view))


def test_final_report_view_renders_zero_take_boxes_with_degraded_narrative():
    view = frv.final_report_view({}, _DEGRADED_NARRATIVE)
    assert not any(_take_sites(view))


# ---------------------------------------------------------------------------
# Raw agent records rendered into reader-facing cells (points 5, 6, 9 of the
# 2026-09-09 review of the first live reports).
# ---------------------------------------------------------------------------


def test_flag_text_prefers_the_note_the_agent_wrote():
    flag = {"metric": "tier4_addback", "value": "Signing bonus ($95)",
            "severity": "Red", "note": "Tier 4 addback: unlikely to survive buyer QofE."}
    assert frv.flag_text(flag) == "Tier 4 addback: unlikely to survive buyer QofE."


def test_flag_text_never_prints_a_dict_repr():
    """The defect this replaces: falling back to the record itself put
    "{'metric': 'tier4_addback', 'value': ...}" into the earnings-quality and
    legal tables of every report."""
    rendered = frv.flag_text({"metric": "x", "severity": "Red"})
    assert "{" not in rendered and "'" not in rendered


def test_flag_text_falls_back_to_value_when_there_is_no_note():
    assert frv.flag_text({"metric": "x", "value": "Goddard Franchising, LLC"}) == "Goddard Franchising, LLC"


def test_humanize_metric_reads_as_prose_not_as_an_identifier():
    assert frv.humanize_metric("coc_consent_required") == "CoC consent required"
    assert frv.humanize_metric("revenue_quality_non_recurring_in_run_rate") == (
        "Revenue quality non recurring in run rate"
    )
    assert frv.humanize_metric("nrr_pct") == "NRR %"
    assert frv.humanize_metric("") == ""


def test_humanize_metric_leaves_an_already_readable_label_alone():
    assert frv.humanize_metric("Unusual indemnity") == "Unusual indemnity"


# ---------------------------------------------------------------------------
# Chart magnitude and period order (point 7 of the 2026-09-09 review).
# ---------------------------------------------------------------------------


def test_money_label_uses_the_tables_own_unit():
    """A P&L stated in thousands: 57,090 is $57.1M, not "57.1bn"."""
    assert frv.money_label(57090, "in thousands") == "$57.1M"
    assert frv.money_label(9027, "in thousands") == "$9.0M"
    assert frv.money_label(40251, "in thousands") == "$40.3M"


def test_money_label_scales_by_each_unit():
    assert frv.money_label(2_500_000, "in dollars") == "$2.5M"
    assert frv.money_label(1500, "in millions") == "$1.5B"


def test_money_label_falls_back_rather_than_assuming_dollars():
    """An unknown unit must not be silently treated as one — assuming is how
    the old label came to call thousands "bn"."""
    assert frv.money_label(57090, "") == "57,090"
    assert frv.money_label(57090, "something else") == "57,090"
    assert frv.money_label(None, "in thousands") is None


def test_short_no_longer_invents_a_billions_suffix():
    assert "bn" not in (frv._short(57090) or "")


def test_ordered_financials_sorts_and_rescales_a_foreign_unit_period():
    """The real Clearsulting shape: a 2022 period extracted in raw dollars,
    emitted last by the agent, beside three periods stated in thousands. The
    P&L table already reconciled both; the charts read the raw rows and drew
    a bar 707x its neighbours, labelled "40251.4bn", after TTM25."""
    bundle = {"financials": {"table_rows": [
        {"year": "2023", "revenue": "$57,090 thousand"},
        {"year": "2024", "revenue": "$59,699 thousand"},
        {"year": "TTM25", "revenue": "$62,564 thousand"},
        {"year": "2022", "revenue": "$40,251,450"},
    ]}}
    ordered = frv.ordered_financials(bundle)
    assert [r.get("year") for r in ordered] == ["2022", "2023", "2024", "TTM25"]
    unit = frv.financial_unit_label(bundle, ordered)
    labels = [frv.money_label(frv.parse_money(r.get("revenue")), unit) for r in ordered]
    assert labels == ["$40.3M", "$57.1M", "$59.7M", "$62.6M"]


def test_every_money_chart_reads_the_same_ordered_rows():
    """The three charts and the table must not disagree about which periods
    exist or what order they are in."""
    bundle = {"financials": {"table_rows": [
        {"year": "2024", "revenue": "$200", "ebitda": "$20", "adjusted_ebitda": "$25"},
        {"year": "2023", "revenue": "$100", "ebitda": "$10", "adjusted_ebitda": "$12"},
    ]}}
    expected = [r.get("year") for r in frv.ordered_financials(bundle)]
    assert [s["label"] for s in frv._trend_chart(bundle)["series"]] == expected
    assert [s["label"] for s in frv._ebitda_chart(bundle)["series"]] == expected


def test_forecast_drops_a_plan_row_that_merely_restates_an_actual():
    """GKF's real shape: the revenue build opens with the actual periods it
    builds from, so 2023A/2024A/2025B were drawn twice — the second time
    suffixed "P", as though an actual were a projection."""
    bundle = {"financials": {
        "table_rows": [{"year": "2023A", "revenue": "$21,403"}, {"year": "2024A", "revenue": "$22,266"}],
        "forecast_rows": [
            {"year": "2023A", "revenue": "$21,403K"},
            {"year": "2024A", "revenue": "$22,266K"},
            {"year": "2026P", "revenue": "$24,753K"},
        ],
    }}
    labels = [s["label"] for s in frv._forecast(bundle, {})["chart"]["series"]]
    assert labels == ["2023A", "2024A", "2026PP"]


def test_forecast_keeps_a_plan_row_that_disagrees_with_the_actual():
    """Clearsulting's real shape: a 2025E full-year estimate ($70.1M) beside a
    TTM25 actual ($62.6M). Same year, genuinely different claims — matching on
    the year alone would delete the estimate the reader needs."""
    bundle = {"financials": {
        "table_rows": [{"year": "TTM25", "revenue": "$62,564 thousand"}],
        "forecast_rows": [{"year": "2025E", "revenue": "$70,142K"}],
    }}
    labels = [s["label"] for s in frv._forecast(bundle, {})["chart"]["series"]]
    assert labels == ["TTM25", "2025EP"]


def test_forecast_puts_both_series_on_one_scale():
    """History arrives in the table's implicit unit, the plan states its own.
    Parsed alike, the plan came out 1,000x smaller and every plan bar drew at
    zero height with its label floating over an empty axis."""
    bundle = {"financials": {
        "table_rows": [{"year": "2024A", "revenue": "$22,266"}],
        "forecast_rows": [{"year": "2026P", "revenue": "$24,753K"}],
    }}
    series = frv._forecast(bundle, {})["chart"]["series"]
    assert [s["bar1_value"] for s in series] == ["$22.3M", "$24.8M"]
    assert all(s["bar1_pct"] and s["bar1_pct"] > 50 for s in series)


def test_absolute_revenue_trusts_a_figure_that_names_its_own_magnitude():
    assert frv.absolute_revenue("$21,403K", "in thousands") == 21_403_000
    assert frv.absolute_revenue("$21,403", "in thousands") == 21_403_000
    assert frv.absolute_revenue(None, "in thousands") is None
