"""Unit tests for agents.exec_summary.rainmaker_view — Rainmaker template projection.

Uses the real, most-recent-per-company `orchestrator_bundle.yaml` fixtures
(§11.7 / Apéndice A.6 of docs/plans/CIM-first-rainmaker-template/plan.md) —
NOT the pre-existing `elder_care_builder_expectations.yaml` family, which has
a different shape and belongs to the BundleBuilder/tldr tests.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from agents.exec_summary.mps_rubric import load_rubric, mps_total, mps_verdict
from agents.exec_summary.rainmaker_view import (
    _mps_table,
    rainmaker_view,
    severity_color_var,
    severity_label,
)

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
_COMPANIES = ["elder_care", "clearsulting", "gkf", "b2b_saas"]


def _load(name: str) -> dict:
    with open(_FIXTURES_DIR / f"{name}_bundle.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.fixture(params=_COMPANIES)
def bundle(request):
    return _load(request.param)


def test_does_not_mutate_input_bundle(bundle):
    snapshot = copy.deepcopy(bundle)
    rainmaker_view(bundle)
    assert bundle == snapshot


def test_financial_availability_has_no_none_values(bundle):
    view = rainmaker_view(bundle)
    for row in view["financial_availability"]:
        assert row["label"]
        assert row["status"] is not None
        assert row["status"] != "None"


def test_financial_availability_covers_expected_labels(bundle):
    view = rainmaker_view(bundle)
    labels = {row["label"] for row in view["financial_availability"]}
    assert labels == {
        "LTM Revenue",
        "Gross Margin",
        "Reported EBITDA",
        "Adjusted EBITDA",
        "Revenue CAGR / YoY",
        "Addback ledger",
        "Quality of Earnings report",
        "CIM / Offering memo",
        "Audited financials",
    }


def test_ltm_revenue_blank_maps_to_not_in_vdr():
    # All three real fixtures have headline_metrics.ltm_revenue == "" today.
    bundle = _load("elder_care")
    assert bundle["headline_metrics"]["ltm_revenue"] == ""
    view = rainmaker_view(bundle)
    row = next(r for r in view["financial_availability"] if r["label"] == "LTM Revenue")
    assert row["status"] == "NOT IN VDR"


def test_addback_ledger_reports_items_and_tier4_from_real_flags():
    bundle = _load("elder_care")
    view = rainmaker_view(bundle)
    row = next(r for r in view["financial_availability"] if r["label"] == "Addback ledger")
    # elder_care_bundle.yaml: 16 tier4_addback + 10 large_unsupported_addback flags.
    assert "26 ITEMS" in row["status"]
    assert "16 TIER-4" in row["status"]


def test_cim_offering_memo_present_when_cim_detected_in_basis_of_preparation():
    bundle = _load("elder_care")
    assert "cim_detected=True" in bundle["meta"]["basis_of_preparation"]
    view = rainmaker_view(bundle)
    row = next(r for r in view["financial_availability"] if r["label"] == "CIM / Offering memo")
    assert row["status"] == "PRESENT"


def test_stat_tiles_within_bounds_and_no_raw_kpi_dicts(bundle):
    view = rainmaker_view(bundle)
    tiles = view["stat_tiles"]
    assert 0 <= len(tiles) <= 6
    for tile in tiles:
        assert isinstance(tile["value"], str)
        assert isinstance(tile["label"], str)
        assert tile["value"]
        assert tile["label"]


def test_stat_tiles_fall_back_generically_when_kpi_dashboard_is_sparse():
    # clearsulting/gkf kpi_dashboard rows are non-numeric (site_level_visibility
    # booleans/notes) — the view must still produce generic tiles from
    # headline_metrics/risks/confidence, not company-specific literals.
    bundle = _load("clearsulting")
    view = rainmaker_view(bundle)
    assert len(view["stat_tiles"]) >= 3
    labels = {t["label"] for t in view["stat_tiles"]}
    assert labels.issubset(
        {
            "LTM EBITDA Margin",
            "Revenue CAGR",
            "Revenue Growth (YoY)",
            "Flagged Risks",
            "Data Room Gaps",
            "Overall Confidence",
        }
    )


def test_stat_tiles_never_leak_company_entity_names():
    # "census"/"caregiver" are generic KPI-dashboard domain terms (the KPI
    # agent's own metric vocabulary, reusable across healthcare companies) —
    # not company literals. Only actual entity names (this company, its
    # acquisitions) must never appear, since those don't generalize.
    bundle = _load("elder_care")
    view = rainmaker_view(bundle)
    forbidden_entities = ("elder care", "unicity", "guided living")
    for tile in view["stat_tiles"]:
        text = f"{tile['value']} {tile['label']}".lower()
        for entity in forbidden_entities:
            assert entity not in text, f"stat tile leaked company entity {entity!r}: {tile}"


def test_stat_tiles_extract_leading_number_from_narrative_kpi_values():
    # Real regression: kpi_dashboard.stated_value is often a real figure
    # followed by long narrative context ("998 clients served TTM Aug-24;
    # 2024E 1,251 total clients across...") — the leading number must still
    # produce a tile rather than being discarded for "not being short."
    bundle = {
        "kpi_dashboard": [
            {
                "metric_id": "census_or_patient_panel",
                "display_name": "Census Or Patient Panel",
                "stated_value": "998 clients served TTM Aug-24; 2024E 1,251 total clients across all markets",
            }
        ],
        "headline_metrics": {},
        "risks": [],
        "data_room_gaps": [],
        "meta": {},
    }
    view = rainmaker_view(bundle)
    tiles = {t["label"]: t["value"] for t in view["stat_tiles"]}
    assert tiles.get("Census Or Patient Panel") == "998"


@pytest.mark.parametrize(
    ("severity", "label", "color_var"),
    [
        ("critical", "CRITICAL", "--red-txt"),
        ("material", "HIGH", "--ylw-txt"),
        ("track", "OPEN", "--meta"),
        ("", "", "--meta"),
    ],
)
def test_severity_label_and_color_mapping(severity, label, color_var):
    assert severity_label(severity) == label
    assert severity_color_var(severity) == color_var


def test_risks_are_enriched_with_precomputed_severity(bundle):
    view = rainmaker_view(bundle)
    assert 0 < len(view["risks"]) <= 8
    for row in view["risks"]:
        assert row["risk"]
        assert row["risk_label"]
        assert row["severity_label"] in {"CRITICAL", "HIGH", "OPEN"}
        assert row["severity_color_var"] in {"--red-txt", "--ylw-txt", "--meta"}
        assert row["severity_bg_var"] in {"--red-bg", "--ylw-bg", "--box-bg"}


@pytest.mark.parametrize(
    ("slug", "expected"),
    [
        ("large_unsupported_addback", "Large Unsupported Addback"),
        ("ebitda_margin_pct", "EBITDA Margin %"),
        ("coc_consent_required", "CoC Consent Required"),
        ("revenue_quality_unusual_credits_rebates_refunds", "Revenue Quality Unusual Credits Rebates Refunds"),
        ("", ""),
    ],
)
def test_risk_labels_keep_domain_acronyms_uppercase(slug, expected):
    from agents.exec_summary.rainmaker_view import _humanize_slug

    assert _humanize_slug(slug) == expected


def test_diligence_questions_dedupe_exact_repeats():
    # Real regression: a legal-agent bundle had the same (category, question)
    # repeated 3x — verify the render view collapses exact repeats.
    bundle = {
        "diligence_questions": [
            {"category": "legal", "question": "Request and review Top Customer Contracts / MSAs / SOWs"},
            {"category": "legal", "question": "Request and review Top Customer Contracts / MSAs / SOWs"},
            {"category": "legal", "question": "Request and review Top Customer Contracts / MSAs / SOWs"},
            {"category": "legal", "question": "Request and review Vendor Contracts"},
        ]
    }
    view = rainmaker_view(bundle)
    questions = [q["question"] for q in view["diligence_questions"]]
    assert questions == [
        "Request and review Top Customer Contracts / MSAs / SOWs",
        "Request and review Vendor Contracts",
    ]


def test_confidence_rows_include_all_areas_plus_overall(bundle):
    view = rainmaker_view(bundle)
    areas = {row["area"] for row in view["confidence_rows"]}
    assert "Overall" in areas
    # confidence_by_area always has 7 keys (schema) + the synthesized Overall row.
    assert len(view["confidence_rows"]) == 8
    for row in view["confidence_rows"]:
        assert row["level"] in {"HIGH", "MEDIUM", "LOW", "MEDIUM_LOW", ""}


# ---------------------------------------------------------------------------
# Capa A — deterministic financial projection (plan_raimaker_format.md §3.1).
# ---------------------------------------------------------------------------


def test_financial_table_never_crashes_on_any_real_fixture(bundle):
    """Anti-overfit (P2): must not crash on any of the 3 diverse fixtures
    (elder_care/clearsulting = healthcare_services, gkf = other overlay),
    regardless of how sparse financials.table_rows is."""
    view = rainmaker_view(bundle)
    table = view["financials"]
    assert isinstance(table["periods"], list)
    assert isinstance(table["rows"], list)
    for row in table["rows"]:
        assert len(row["cells"]) == len(table["periods"])


def test_financial_table_empty_series_yields_no_crash_and_no_fabrication():
    empty_bundle = {"financials": {"table_rows": []}}
    from agents.exec_summary.rainmaker_view import rainmaker_view as view_fn

    view = view_fn(empty_bundle)
    assert view["financials"]["periods"] == []
    assert view["financials"]["rows"][0]["cells"] == []
    assert view["financials"]["growth_col_label"] is None
    assert view["rule_of_x"] == []


def test_financial_table_reads_dollar_figures_and_computes_growth():
    bundle = {
        "financials": {
            "table_rows": [
                {"year": "2023A", "revenue": "$1.9", "gross_profit": "$1.6", "gross_margin_pct": "82.3%", "ebitda": "$0.7", "ebitda_margin_pct": "35.7%"},
                {"year": "2024A", "revenue": "$8.3", "gross_profit": "$7.0", "gross_margin_pct": "85.1%", "ebitda": "$4.4", "ebitda_margin_pct": "53.4%"},
            ]
        }
    }
    view = rainmaker_view(bundle)
    table = view["financials"]
    assert table["periods"] == ["2023A", "2024A"]
    metrics = {r["metric_name"]: r["cells"] for r in table["rows"]}
    assert metrics["Total Revenue"] == ["$1.9", "$8.3"]
    assert metrics["EBITDA"] == ["$0.7", "$4.4"]
    assert metrics["% Growth"][0] is None
    assert metrics["% Growth"][1] == "336.8%"  # (8.3-1.9)/1.9 * 100, pure arithmetic


def test_financial_table_never_fabricates_missing_dollar_cells():
    bundle = {
        "financials": {
            "table_rows": [
                {"year": "2020A", "revenue": "", "gross_profit": "", "gross_margin_pct": "42.1%", "ebitda": "", "ebitda_margin_pct": "36.6%"},
            ]
        }
    }
    view = rainmaker_view(bundle)
    metrics = {r["metric_name"]: r["cells"] for r in view["financials"]["rows"]}
    assert metrics["Total Revenue"] == [None]
    assert metrics["EBITDA"] == [None]
    assert metrics["% Gross Margin"] == ["42.1%"]


def test_financial_table_dedupes_defensively_against_stale_duplicate_rows():
    """Belt-and-suspenders: even a bundle persisted before the field_mapping
    fix (duplicate year rows already baked into financials.table_rows) must
    not double-count periods here."""
    bundle = {
        "financials": {
            "table_rows": [
                {"year": "2020A", "revenue": "$1.0"},
                {"year": "2020A", "revenue": "$1.0"},
            ]
        }
    }
    view = rainmaker_view(bundle)
    assert view["financials"]["periods"] == ["2020A"]


def test_rule_of_x_extracts_leading_number_from_messy_percent_strings():
    bundle = {
        "financials": {
            "table_rows": [
                {"year": "2021A", "revenue": "$1.0", "ebitda_margin_pct": "33.4%"},
                {
                    "year": "2022A",
                    "revenue": "$2.0",
                    "ebitda_margin_pct": "31.4% (Historical P&L) / 33.0% (Pro Forma — DISCREPANCY)",
                },
            ]
        }
    }
    view = rainmaker_view(bundle)
    assert len(view["rule_of_x"]) == 1  # first period has no growth (no prior)
    assert view["rule_of_x"][0]["label"] == "Rule of 131"  # 100% growth + leading 31.4% margin


# ---------------------------------------------------------------------------
# Round 3, A5 — Rule of 40/X presentation fields (value_num/components/benchmark).
# ---------------------------------------------------------------------------


def test_rule_of_x_tile_carries_presentation_fields_above_benchmark():
    bundle = {
        "financials": {
            "table_rows": [
                {"year": "2021A", "revenue": "$1.0", "ebitda_margin_pct": "10%"},
                {"year": "2022A", "revenue": "$2.0", "ebitda_margin_pct": "10%"},
            ]
        }
    }
    view = rainmaker_view(bundle)
    tile = view["rule_of_x"][0]
    assert tile["value_num"] == 110.0  # 100% growth + 10% margin
    assert tile["components"] == "100.0% growth + 10% margin"
    assert tile["benchmark"] == "above"


def test_rule_of_x_tile_below_benchmark():
    bundle = {
        "financials": {
            "table_rows": [
                {"year": "2021A", "revenue": "$1.0", "ebitda_margin_pct": "5%"},
                {"year": "2022A", "revenue": "$1.1", "ebitda_margin_pct": "5%"},
            ]
        }
    }
    view = rainmaker_view(bundle)
    tile = view["rule_of_x"][0]
    assert tile["value_num"] == 15.0  # 10% growth + 5% margin
    assert tile["benchmark"] == "below"


def test_metadata_never_leaks_company_entity_into_preparer_fields(bundle):
    """Company-agnostic (P2): prepared_for/prepared_by are the tool operator's
    identity (Rallyday Partners), not derived from the target company."""
    view = rainmaker_view(bundle)
    metadata = view["metadata"]
    assert metadata["prepared_by"] == "Rallyday Partners"
    assert metadata["company_name"] == bundle["meta"]["company_name"]


def test_key_metrics_matches_stat_tiles(bundle):
    view = rainmaker_view(bundle)
    assert view["key_metrics"] == view["stat_tiles"]


def test_financial_table_populates_dollar_figures_on_diverse_overlay():
    """Anti-overfit (P2): b2b_saas_bundle.yaml is a different vertical_overlay
    from Elder Care/Clearsulting (healthcare_services) with real $ figures
    (post field_mapping-fix shape) — proves Capa A isn't Elder-Care-shaped."""
    bundle = _load("b2b_saas")
    assert bundle["meta"]["vertical_overlay"] == "b2b_saas"
    view = rainmaker_view(bundle)
    table = view["financials"]
    assert table["periods"] == ["2022A", "2023A", "2024A"]
    metrics = {r["metric_name"]: r["cells"] for r in table["rows"]}
    assert metrics["Total Revenue"] == ["$4.0", "$7.0", "$12.0"]
    assert metrics["EBITDA"] == ["$0.4", "$1.3", "$2.9"]
    assert table["growth_col_label"] is not None  # both Revenue and EBITDA CAGR computable


# ---------------------------------------------------------------------------
# Part B, B4 — a stated % must never contradict the $ figures shown right
# next to it. Regression case built from the real Elder Care render (see
# docs/plans/connect-all-vdr-er.md Part B, B4): the rendered PDF said "36.6%
# Gross Margin" next to $3,208/$35,136 (= 9.1%) and "19.9% EBITDA Margin"
# next to $9,239/$35,136 (= 26.3%) — extracted independently, on different
# bases, and never cross-checked.
# ---------------------------------------------------------------------------


def test_margin_reconciliation_overrides_a_contradicting_stated_percent():
    bundle = {
        "financials": {
            "table_rows": [
                {
                    "year": "TTM Aug-24",
                    "revenue": "35136",
                    "gross_profit": "3208",
                    "gross_margin_pct": "36.6%",   # contradicts 3208/35136 = 9.1%
                    "ebitda": "9239",
                    "ebitda_margin_pct": "19.9%",  # contradicts 9239/35136 = 26.3%
                },
            ]
        }
    }
    view = rainmaker_view(bundle)
    metrics = {r["metric_name"]: r["cells"] for r in view["financials"]["rows"]}
    # Money cells are rendered uniformly across periods (thousands separated,
    # the source's own precision kept), so a column does not mix "35136" with
    # "$57,090 thousand". The reconciliation below is about the % rows and is
    # unaffected by how the $ row is written.
    assert metrics["Total Revenue"] == ["35,136"]
    assert metrics["Gross Profit"] == ["3,208"]  # the $ VALUE is never touched, only its formatting
    assert metrics["% Gross Margin"] == ["9.1%"]  # recomputed, not the stated 36.6%
    assert metrics["EBITDA"] == ["9,239"]
    assert metrics["% EBITDA Margin"] == ["26.3%"]  # recomputed, not the stated 19.9%


def test_margin_reconciliation_leaves_a_consistent_stated_percent_untouched():
    """A % that already matches its own $ row is kept verbatim — this is a
    consistency check, not a re-derivation of every cell."""
    bundle = {
        "financials": {
            "table_rows": [
                {
                    "year": "2024A",
                    "revenue": "100",
                    "gross_profit": "40",
                    "gross_margin_pct": "40.0%",
                    "ebitda": "20",
                    "ebitda_margin_pct": "20%",
                },
            ]
        }
    }
    view = rainmaker_view(bundle)
    metrics = {r["metric_name"]: r["cells"] for r in view["financials"]["rows"]}
    assert metrics["% Gross Margin"] == ["40.0%"]
    assert metrics["% EBITDA Margin"] == ["20%"]


def test_margin_reconciliation_fills_a_blank_percent_from_the_dollar_row():
    bundle = {
        "financials": {
            "table_rows": [
                {
                    "year": "2024A",
                    "revenue": "200",
                    "gross_profit": "80",
                    "gross_margin_pct": "",
                    "ebitda": "30",
                    "ebitda_margin_pct": "",
                },
            ]
        }
    }
    view = rainmaker_view(bundle)
    metrics = {r["metric_name"]: r["cells"] for r in view["financials"]["rows"]}
    assert metrics["% Gross Margin"] == ["40.0%"]
    assert metrics["% EBITDA Margin"] == ["15.0%"]


def test_margin_reconciliation_never_touches_a_percent_with_no_dollar_to_check_against():
    """A blank/missing $ figure means there is nothing to verify against —
    the agent's own stated % is left exactly as extracted, never dropped or
    invented over (matches the existing no-fabrication contract)."""
    bundle = {
        "financials": {
            "table_rows": [
                {
                    "year": "2020A",
                    "revenue": "",
                    "gross_profit": "",
                    "gross_margin_pct": "42.1%",
                    "ebitda": "",
                    "ebitda_margin_pct": "36.6%",
                },
            ]
        }
    }
    view = rainmaker_view(bundle)
    metrics = {r["metric_name"]: r["cells"] for r in view["financials"]["rows"]}
    assert metrics["% Gross Margin"] == ["42.1%"]
    assert metrics["% EBITDA Margin"] == ["36.6%"]


def test_margin_reconciliation_flows_through_to_rule_of_x():
    """The reconciled % must be what downstream Capa A projections (the
    "Rule of N" tile) actually use — not the original contradicting stated
    value — since they read the same `table` this function returns."""
    bundle = {
        "financials": {
            "table_rows": [
                {
                    "year": "2023A",
                    "revenue": "28330",
                    "gross_profit": "10820",
                    "gross_margin_pct": "38.2%",
                    "ebitda": "6677",
                    "ebitda_margin_pct": "19.5%",
                },
                {
                    "year": "TTM Aug-24",
                    "revenue": "35136",
                    "gross_profit": "3208",
                    "gross_margin_pct": "36.6%",   # contradicts 3208/35136 = 9.1%
                    "ebitda": "9239",
                    "ebitda_margin_pct": "19.9%",  # contradicts 9239/35136 = 26.3%
                },
            ]
        }
    }
    view = rainmaker_view(bundle)
    assert view["rule_of_x"], "expected at least one Rule of N tile"
    latest_tile = view["rule_of_x"][-1]
    assert latest_tile["margin"] == "26.3%"  # the reconciled value, not the stated 19.9%


# ---------------------------------------------------------------------------
# Round 3, A3 — CAGR / growth column on the financial table.
# ---------------------------------------------------------------------------


def test_growth_column_cagr_on_dollar_rows_across_three_periods():
    bundle = {
        "financials": {
            "table_rows": [
                {"year": "2021A", "revenue": "100", "gross_profit": "40", "ebitda": "10"},
                {"year": "2022A", "revenue": "110", "gross_profit": "44", "ebitda": "11"},
                {"year": "2023A", "revenue": "121", "gross_profit": "48.4", "ebitda": "12.1"},
            ]
        }
    }
    view = rainmaker_view(bundle)
    rows = {r["metric_name"]: r for r in view["financials"]["rows"]}
    assert rows["Total Revenue"]["growth"] == "10%"  # (121/100)**(1/2)-1 = 10%
    assert rows["Total Revenue"]["growth_kind"] == "cagr"
    assert rows["Gross Profit"]["growth"] == "10%"
    assert rows["EBITDA"]["growth"] == "10%"
    assert view["financials"]["growth_col_label"] == "CAGR / Δ 2021A–2023A"


def test_growth_column_delta_pts_on_percent_margin_rows():
    bundle = {
        "financials": {
            "table_rows": [
                {"year": "2021A", "revenue": "100", "gross_profit": "40", "gross_margin_pct": "40.0%", "ebitda": "10", "ebitda_margin_pct": "10.0%"},
                {"year": "2023A", "revenue": "121", "gross_profit": "50.8", "gross_margin_pct": "42.0%", "ebitda": "9.68", "ebitda_margin_pct": "8.0%"},
            ]
        }
    }
    view = rainmaker_view(bundle)
    rows = {r["metric_name"]: r for r in view["financials"]["rows"]}
    assert rows["% Gross Margin"]["growth"] == "+2.0 pts"
    assert rows["% Gross Margin"]["growth_kind"] == "delta_pts"
    assert rows["% EBITDA Margin"]["growth"] == "-2.0 pts"


def test_growth_column_none_on_percent_growth_row():
    bundle = {
        "financials": {
            "table_rows": [
                {"year": "2021A", "revenue": "100"},
                {"year": "2022A", "revenue": "110"},
            ]
        }
    }
    view = rainmaker_view(bundle)
    rows = {r["metric_name"]: r for r in view["financials"]["rows"]}
    assert rows["% Growth"]["growth"] is None
    assert rows["% Growth"]["growth_kind"] is None


def test_growth_column_label_is_none_when_no_row_has_growth():
    bundle = {"financials": {"table_rows": [{"year": "2023A", "revenue": "100"}]}}
    view = rainmaker_view(bundle)
    assert view["financials"]["growth_col_label"] is None
    for row in view["financials"]["rows"]:
        assert row["growth"] is None


def test_growth_column_reads_the_reconciled_percent_not_the_contradicting_stated_one():
    """The growth column for a % row must use the same reconciled cells
    _reconcile_margin_rows already produces — not the agent's original,
    possibly-contradicting stated percent."""
    bundle = {
        "financials": {
            "table_rows": [
                {
                    "year": "2023A", "revenue": "28330", "gross_profit": "10820",
                    "gross_margin_pct": "38.2%", "ebitda": "6677", "ebitda_margin_pct": "19.5%",
                },
                {
                    "year": "TTM Aug-24", "revenue": "35136", "gross_profit": "3208",
                    "gross_margin_pct": "36.6%",  # contradicts 3208/35136 = 9.1%
                    "ebitda": "9239", "ebitda_margin_pct": "19.9%",  # contradicts 9239/35136 = 26.3%
                },
            ]
        }
    }
    view = rainmaker_view(bundle)
    rows = {r["metric_name"]: r for r in view["financials"]["rows"]}
    # Gross margin: 38.2 -> 9.1 (reconciled), not 38.2 -> 36.6 (stated).
    assert rows["% Gross Margin"]["growth"] == "-29.1 pts"
    # EBITDA margin: 23.6 -> 26.3 (both reconciled from $, since neither
    # stated cell matches its own $ row), not 19.5 -> 19.9 (stated).
    assert rows["% EBITDA Margin"]["growth"] == "+2.7 pts"


def test_growth_column_never_alters_dollar_cells():
    bundle = {
        "financials": {
            "table_rows": [
                {"year": "2021A", "revenue": "100", "gross_profit": "40", "ebitda": "10"},
                {"year": "2023A", "revenue": "121", "gross_profit": "48.4", "ebitda": "12.1"},
            ]
        }
    }
    view = rainmaker_view(bundle)
    rows = {r["metric_name"]: r for r in view["financials"]["rows"]}
    assert rows["Total Revenue"]["cells"] == ["100", "121"]
    assert rows["Gross Profit"]["cells"] == ["40", "48.4"]
    assert rows["EBITDA"]["cells"] == ["10", "12.1"]


# ---------------------------------------------------------------------------
# T2 — MPS page projection (plan §4, §8; _mps_table).
# ---------------------------------------------------------------------------


def _load_mps_run() -> dict:
    with open(_FIXTURES_DIR / "mps_run_verbose.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _rubric_category_keys() -> list[str]:
    return [c["key"] for c in load_rubric()["categories"]]


def test_mps_table_empty_input_is_degraded_with_seven_rows():
    table = _mps_table([])
    assert table["mps_status"] == "degraded"
    assert table["columns"] == []
    assert len(table["rows"]) == 7
    assert [r["key"] for r in table["rows"]] == _rubric_category_keys()
    for row in table["rows"]:
        assert row["score_cells"] == []
        assert row["bullets"] == []


def test_mps_table_none_input_same_as_empty_list():
    # rainmaker_view() normalizes mps_runs=None to [] before calling
    # _mps_table (which itself always expects a list).
    view_none = rainmaker_view({}, mps_runs=None)
    view_empty = rainmaker_view({}, mps_runs=[])
    assert view_none["mps"] == view_empty["mps"]


def test_mps_table_seven_rows_in_rubric_file_order():
    run = _load_mps_run()
    table = _mps_table([run])
    assert [r["key"] for r in table["rows"]] == _rubric_category_keys()


def test_mps_table_never_computes_arithmetic_of_its_own():
    """The total/verdict the table returns must be exactly what
    mps_rubric.mps_total()/mps_verdict() compute from the same scores —
    _mps_table must not reimplement the product or the threshold compare."""
    run = _load_mps_run()
    table = _mps_table([run])
    key_order = _rubric_category_keys()
    scores_by_key = {c["key"]: c["score"] for c in run["categories"]}
    expected_scores = [scores_by_key[k] for k in key_order]
    expected_total = mps_total(expected_scores)
    expected_verdict = mps_verdict(expected_total, run["threshold"])
    assert table["total_cells"] == [f"{expected_total:.1f}"]
    assert table["verdict"] == expected_verdict


def test_mps_table_score_cells_and_verdict_from_verbose_fixture():
    run = _load_mps_run()
    table = _mps_table([run])
    assert table["mps_status"] == "success"
    assert table["threshold"] == 15
    assert table["verdict"] == "above threshold"
    assert table["n_scored"] == 7
    row_by_key = {r["key"]: r for r in table["rows"]}
    assert row_by_key["magical_business_model"]["score_cells"] == [4]
    assert row_by_key["financeable"]["score_cells"] == [4]


def test_mps_table_none_score_makes_total_none_never_a_default():
    run = copy.deepcopy(_load_mps_run())
    run["categories"][0]["score"] = None
    table = _mps_table([run])
    assert table["total_cells"] == [None]
    assert table["verdict"] is None
    assert table["n_scored"] == 6


def test_mps_table_commentary_capped_at_four_bullets():
    run = _load_mps_run()
    table = _mps_table([run])
    for row in table["rows"]:
        assert len(row["bullets"]) <= 4
    manageable = next(r for r in table["rows"] if r["key"] == "manageable_systemic_risk")
    assert len(manageable["bullets"]) == 4
    assert all(b["kind"] == "sub_axis" for b in manageable["bullets"])


def test_mps_table_evidence_marker_only_on_proxy_categories():
    run = _load_mps_run()
    table = _mps_table([run])
    row_by_key = {r["key"]: r for r in table["rows"]}
    assert row_by_key["growth_mindset"]["evidence_marker"]  # contact_dependent
    assert row_by_key["transformational_equity"]["evidence_marker"]  # judgment_over_context
    assert row_by_key["financeable"]["evidence_marker"]  # judgment_over_context
    assert not row_by_key["magical_business_model"]["evidence_marker"]  # document_derived
    assert table["show_legend"] is True


def test_mps_table_run_mode_label_lookup_with_safe_default():
    run = copy.deepcopy(_load_mps_run())
    run["run_mode"] = "cim_only"
    table = _mps_table([run])
    assert table["columns"][0]["header"].startswith("CIM-only preview")

    run["run_mode"] = "some_future_third_mode"
    table = _mps_table([run])
    assert table["columns"][0]["header"].startswith("some_future_third_mode")


def test_rainmaker_view_wires_mps_key(bundle):
    run = _load_mps_run()
    view = rainmaker_view(bundle, mps_runs=[run])
    assert view["mps"] == _mps_table([run])


def test_rainmaker_view_mps_defaults_to_degraded_skeleton(bundle):
    view = rainmaker_view(bundle)
    assert view["mps"]["mps_status"] == "degraded"
    assert len(view["mps"]["rows"]) == 7


# ---------------------------------------------------------------------------
# Period ordering, unit normalization and the revenue-growth tile — the three
# numeric defects reported on the 2026-09-02 stakeholder previews (a period
# column extracted in a different unit that made growth read "64572.4%", a
# table whose periods ran 2023 → 2024 → LTM 2025 → 2022, a header hardcoded to
# "in millions" over figures in thousands, and a CAGR tile that disagreed with
# the CAGR column right above it).
# ---------------------------------------------------------------------------


def _financials_bundle(rows, **meta) -> dict:
    return {
        "meta": {"company_name": "Acme", **meta},
        "headline_metrics": {},
        "financials": {"table_rows": rows},
    }


def _row(year, revenue, gross_profit=None, ebitda=None):
    return {
        "year": year,
        "revenue": revenue,
        "gross_profit": gross_profit,
        "gross_margin_pct": None,
        "ebitda": ebitda,
        "ebitda_margin_pct": None,
    }


def _cells(view, metric):
    return next(r["cells"] for r in view["financials"]["rows"] if r["metric_name"] == metric)


def test_financial_periods_are_sorted_chronologically():
    view = rainmaker_view(
        _financials_bundle(
            [
                _row("2023A", "$58,082"),
                _row("2024A", "$58,518"),
                _row("LTM MAY 2025", "$62,239"),
                _row("2022", "$40,251"),
            ]
        )
    )
    assert view["financials"]["periods"] == ["2022", "2023A", "2024A", "LTM MAY 2025"]
    assert _cells(view, "Total Revenue") == ["$40,251", "$58,082", "$58,518", "$62,239"]


def test_periods_without_a_year_keep_their_order_and_go_last():
    view = rainmaker_view(
        _financials_bundle(
            [_row("Budget", "$30"), _row("2025A", "$20"), _row("Plan", "$40"), _row("2024A", "$10")]
        )
    )
    assert view["financials"]["periods"] == ["2024A", "2025A", "Budget", "Plan"]


def test_fy_shorthand_periods_sort_by_the_year_they_name():
    view = rainmaker_view(_financials_bundle([_row("FY25", "$30"), _row("FY23", "$10"), _row("FY24", "$20")]))
    assert view["financials"]["periods"] == ["FY23", "FY24", "FY25"]


def test_period_extracted_in_a_different_unit_is_rescaled_onto_the_table_unit():
    # One period read in raw dollars while the rest of the P&L is in thousands
    # — verbatim shape of the defect on the Clearsulting preview.
    view = rainmaker_view(
        _financials_bundle(
            [
                _row("2022", "$40,251,450", gross_profit="$18,000,000"),
                _row("2023A", "$58,082"),
                _row("2024A", "$58,518"),
                _row("LTM MAY 2025", "$62,239"),
            ]
        )
    )
    assert _cells(view, "Total Revenue")[0] == "$40,251"
    assert _cells(view, "Gross Profit")[0] == "$18,000"
    # The growth row is now a real percentage rather than five digits of noise.
    assert _cells(view, "% Growth")[1] == "44.3%"


def test_unit_rescaling_never_mutates_the_input_bundle():
    bundle = _financials_bundle(
        [_row("2022", "$40,251,450"), _row("2023A", "$58,082"), _row("2024A", "$58,518")]
    )
    snapshot = copy.deepcopy(bundle)
    rainmaker_view(bundle)
    assert bundle == snapshot


def test_two_periods_are_never_rescaled_against_each_other():
    # With two figures there is no majority to identify the outlier — leave
    # both exactly as the agent extracted them rather than guess.
    view = rainmaker_view(_financials_bundle([_row("2023A", "$58,082"), _row("2024A", "$62,239,000")]))
    assert _cells(view, "Total Revenue") == ["$58,082", "$62,239,000"]


def test_unit_label_comes_from_the_headline_metric_when_it_carries_a_suffix():
    bundle = _financials_bundle([_row("2023A", "$21,403"), _row("2024A", "$22,266"), _row("2025B", "$23,022")])
    bundle["headline_metrics"] = {"ltm_revenue": "$23.0mm"}
    assert rainmaker_view(bundle)["financials"]["unit_label"] == "in thousands"


def test_unit_label_falls_back_to_the_magnitude_of_the_figures():
    thousands = _financials_bundle([_row("2023A", "$21,403"), _row("2024A", "$22,266")])
    assert rainmaker_view(thousands)["financials"]["unit_label"] == "in thousands"

    millions = _financials_bundle([_row("2023A", "$21.4"), _row("2024A", "$22.3")])
    assert rainmaker_view(millions)["financials"]["unit_label"] == "in millions"

    dollars = _financials_bundle([_row("2023A", "$21,403,000"), _row("2024A", "$22,266,000")])
    assert rainmaker_view(dollars)["financials"]["unit_label"] == "in dollars"


def test_unit_label_is_empty_when_no_dollar_figures_were_extracted():
    view = rainmaker_view(_financials_bundle([_row("2023A", None), _row("2024A", None)]))
    assert view["financials"]["unit_label"] == ""


def test_revenue_tile_reuses_the_cagr_the_table_already_displays():
    bundle = _financials_bundle([_row("2023A", "$100"), _row("2024A", "$110"), _row("2025A", "$121")])
    bundle["headline_metrics"] = {"revenue_cagr": "3%"}  # FTA's latest YoY, not a CAGR
    view = rainmaker_view(bundle)
    tile = next(t for t in view["stat_tiles"] if t["label"] == "Revenue CAGR")
    table_growth = next(
        r["growth"] for r in view["financials"]["rows"] if r["metric_name"] == "Total Revenue"
    )
    assert tile["value"] == table_growth == "10%"


def test_revenue_tile_relabels_the_headline_figure_when_no_cagr_is_computable():
    bundle = _financials_bundle([_row("2023A", None)])
    bundle["headline_metrics"] = {"revenue_cagr": "3%"}
    view = rainmaker_view(bundle)
    assert {"value": "3%", "label": "Revenue Growth (YoY)"} in view["stat_tiles"]
    assert not any(t["label"] == "Revenue CAGR" for t in view["stat_tiles"])


def test_format_period_money_removes_a_redundant_magnitude_word():
    """The same company's revenue arrives as "$40,251" for one period and
    "$57,090 thousand" for the next; printed side by side they read as two
    different quantities and the longer cell wrapped onto a second line."""
    from agents.exec_summary.rainmaker_view import format_period_money

    assert format_period_money("$57,090 thousand") == "$57,090"
    assert format_period_money("$40,251") == "$40,251"


def test_format_period_money_keeps_the_precision_the_source_stated():
    """Imposing a fixed rule turned a stated "40" into "40.0", inventing a
    significant digit the agent did not write."""
    from agents.exec_summary.rainmaker_view import format_period_money

    assert format_period_money("40") == "40"
    assert format_period_money("48.4") == "48.4"


def test_format_period_money_passes_unparseable_text_through():
    from agents.exec_summary.rainmaker_view import format_period_money

    assert format_period_money("not a number") == "not a number"
    assert format_period_money(None) is None


def test_format_period_money_keeps_a_negative_in_parentheses():
    from agents.exec_summary.rainmaker_view import format_period_money

    assert format_period_money("($1,200)") == "($1,200)"
