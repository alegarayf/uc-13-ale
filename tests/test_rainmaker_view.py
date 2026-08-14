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

from agents.exec_summary.rainmaker_view import (
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
    assert view["cagr_circles"] == []
    assert view["rule_of_x"] == []
    assert view["snapshot"]["has_data"] is False
    assert view["snapshot"]["max_value"] is None


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


def test_cagr_circles_pure_arithmetic_known_values():
    bundle = {
        "financials": {
            "table_rows": [
                {"year": "Y1", "revenue": "$100", "ebitda": "$10"},
                {"year": "Y2", "revenue": "$121", "ebitda": "$10"},
            ]
        }
    }
    view = rainmaker_view(bundle)
    revenue_circle = next(c for c in view["cagr_circles"] if c["label"].startswith("Revenue"))
    assert revenue_circle["value"] == "21%"  # (121/100)**(1/1) - 1 = 21%


def test_cagr_circles_omitted_when_insufficient_data():
    bundle = {"financials": {"table_rows": [{"year": "Y1", "revenue": "$100"}]}}
    view = rainmaker_view(bundle)
    assert view["cagr_circles"] == []


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


def test_snapshot_chart_max_value_and_has_data_flag():
    bundle = {
        "financials": {
            "table_rows": [
                {"year": "Y1", "revenue": "$5", "ebitda": "$10"},
            ]
        }
    }
    view = rainmaker_view(bundle)
    assert view["snapshot"]["max_value"] == 10.0
    assert view["snapshot"]["has_data"] is True


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
    assert view["cagr_circles"]  # both Revenue and EBITDA CAGR computable
    assert view["snapshot"]["has_data"] is True
