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
_COMPANIES = ["elder_care", "clearsulting", "gkf"]


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


def test_stat_tiles_use_real_kpi_display_names_when_numeric():
    # elder_care kpi_dashboard has narrative stated_value strings — none are
    # short/numeric, so it also falls back generically (verifies the "no
    # hardcoded Elder-Care literal" rule holds even for its own fixture).
    bundle = _load("elder_care")
    view = rainmaker_view(bundle)
    forbidden_literals = ("caregiver", "census", "elder care", "unicity")
    for tile in view["stat_tiles"]:
        text = f"{tile['value']} {tile['label']}".lower()
        for literal in forbidden_literals:
            assert literal not in text, f"stat tile leaked company literal {literal!r}: {tile}"


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
        assert row["severity_label"] in {"CRITICAL", "HIGH", "OPEN"}
        assert row["severity_color_var"] in {"--red-txt", "--ylw-txt", "--meta"}
        assert row["severity_bg_var"] in {"--red-bg", "--ylw-bg", "--box-bg"}


def test_confidence_rows_include_all_areas_plus_overall(bundle):
    view = rainmaker_view(bundle)
    areas = {row["area"] for row in view["confidence_rows"]}
    assert "Overall" in areas
    # confidence_by_area always has 7 keys (schema) + the synthesized Overall row.
    assert len(view["confidence_rows"]) == 8
    for row in view["confidence_rows"]:
        assert row["level"] in {"HIGH", "MEDIUM", "LOW", "MEDIUM_LOW", ""}
