"""Every key the field mapper emits must be declared in the bundle schema.

This file exists because of a production failure on 2026-09-09. The mapper
gained a ``value_kind`` key on each KPI dashboard row; the schema declares
``additionalProperties: false`` on that row; and ``validate_bundle`` runs
inside ``BundleBuilder.build`` — which stage 1 calls, before the executive
review is rendered. So an undeclared key did not degrade the final report,
it failed the whole VDR run for every company, and the deal team got no
deliverable at all.

Nothing caught it earlier because the unit tests build bundles from fixtures
that populate only the keys each test cares about, and the schema-acceptance
test written alongside the change covered the blocks that change touched but
not this one. A test that enumerates one block at a time will always be one
block behind the next change.

So this compares the two sides directly: what the mapper produces for a
richly-populated snapshot set, against what the schema permits. A new key
fails here, at the point it is added, rather than on the next real run.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from agents.exec_summary.bundle_builder import BundleBuilder
from agents.exec_summary.field_mapping import apply_field_mappings
from agents.exec_summary.validate import BundleValidationError, validate_bundle

_SCHEMA = yaml.safe_load(
    (
        Path(__file__).resolve().parents[1]
        / "databricks/agents/exec_summary/orchestrator_bundle.schema.yaml"
    ).read_text(encoding="utf-8")
)


def _declared(node: dict) -> set[str]:
    """Property names a schema node permits, following one $ref hop."""
    if "$ref" in node:
        name = node["$ref"].rsplit("/", 1)[-1]
        node = _SCHEMA["definitions"][name]
    return set((node.get("properties") or {}).keys())


def _row_schema(node: dict) -> dict:
    items = node.get("items") or {}
    if "$ref" in items:
        return _SCHEMA["definitions"][items["$ref"].rsplit("/", 1)[-1]]
    return items


# Snapshot set shaped like the live uc13_preview rows: every agent present,
# every block the mapper reads populated, so the mapper emits its full key set.
_SNAPSHOTS = {
    "business_model": {"yaml_dict": {"executive_summary": "A consulting firm."}, "delta_row": {}},
    "financial_trends": {
        "yaml_dict": {
            "revenue_trend": [{"period": "2024", "revenue_stated": "$59,699 thousand"}],
            "gross_margin": [{"period": "2024", "gm_pct_stated": "42.3%"}],
            "ebitda": [{"period": "2024", "version": "reported", "ebitda_dollars": "11,400"}],
            "revenue_by_segment": [
                {"segment": "North", "revenue_dollars": "1,000", "period": "2024"},
            ],
            "addback_schedule": {"addback_pct_of_ebitda": "12%"},
        },
        "delta_row": {},
    },
    "customer_quality": {
        "yaml_dict": {
            "top_customers": [
                {"customer_name": "Client 1", "revenue_pct_yr1": None,
                 "revenue_dollars": "2024: $10,917,799"},
            ],
            "concentration_summary": {"top1_pct": None},
            "retention": {"nrr_pct": "73%"},
            "customer_tenure": {"average_tenure_years": 3},
            "payor_mix": [{"payor_category": "Private", "pct_of_revenue": 61}],
        },
        "delta_row": {},
    },
    "kpi": {
        "yaml_dict": {
            "tech_services_kpis": {
                "attrition_rate_pct": "14",
                "revenue_per_fte_dollars": "200000",
                "bench_note": "Non-billable cost of goods sold was $8,433K in 2023 and rose after.",
                "bill_rates_by_role": [{"role": "Level 1", "bill_rate_dollars": "146.30"}],
            },
        },
        "delta_row": {"overlay_confirmed": "tech_services", "data_room_gaps": []},
    },
    "quality_of_earnings": {
        "yaml_dict": {
            "addback_ledger": [
                {"description": "Signing bonus", "amount_dollars": "95",
                 "tier_classification": "Tier 4", "period": "TTM25",
                 "tier_rationale": "No supporting document referenced."},
            ],
        },
        "delta_row": {"total_addbacks_pct_of_ebitda": 12.2, "flags": "[]",
                      "tier4_addback_count": 11},
    },
    "legal": {"yaml_dict": {}, "delta_row": {}},
}

_PARTIAL = apply_field_mappings(
    _SNAPSHOTS,
    {"industry_overlay": "tech_services"},
    {"company_name": "Test Co", "generated_at": "2026-09-09T00:00:00Z"},
)


@pytest.mark.parametrize("block", ["revenue_quality", "financials", "qoe"])
def test_mapper_object_block_declares_every_key_it_emits(block):
    emitted = set((_PARTIAL.get(block) or {}).keys())
    assert emitted, f"the fixture did not populate {block} — the check would pass vacuously"
    undeclared = emitted - _declared(_SCHEMA["properties"][block])
    assert not undeclared, (
        f"{block} emits {sorted(undeclared)}, which the schema does not declare. "
        "validate_bundle runs inside BundleBuilder.build, which stage 1 calls, so an "
        "undeclared key fails the whole VDR run — not just the final report."
    )


def test_kpi_dashboard_rows_declare_every_key_they_emit():
    """The exact miss that failed the 2026-09-09 run: ``value_kind``."""
    rows = _PARTIAL.get("kpi_dashboard") or []
    assert rows, "the fixture produced no KPI rows — the check would pass vacuously"
    declared = set((_row_schema(_SCHEMA["properties"]["kpi_dashboard"]).get("properties") or {}).keys())
    for row in rows:
        assert not set(row) - declared, f"KPI row emits {sorted(set(row) - declared)}"


# ---------------------------------------------------------------------------
# Two disjoint EBITDA series (plan report-surface-truth-w1, T1 §2.1/§2.2).
#
# The block-level checks above compare the top-level keys of ``financials``;
# they do not descend into ``table_rows`` items, which carry their own
# ``additionalProperties: false``. So the two new row keys need both a row-key
# check and a real round trip: apply_field_mappings is reached through
# BundleBuilder.build, which calls validate_bundle before it returns. That is
# the path a VDR run takes, and the path an undeclared key fails.
# ---------------------------------------------------------------------------

_DUAL_VERSION_SNAPSHOTS = deepcopy(_SNAPSHOTS)
_DUAL_VERSION_SNAPSHOTS["financial_trends"]["yaml_dict"]["ebitda"] = [
    {"period": "2024", "version": "reported", "ebitda_dollars": "11,400",
     "ebitda_margin_pct": "19.1%"},
    {"period": "2024", "version": "pf_adjusted", "ebitda_dollars": "9,239",
     "ebitda_margin_pct": "19.9%"},
]


def _build_bundle(snapshots: dict) -> dict:
    """Full BundleBuilder.build round trip — the real call path, including the
    validate_bundle call inside build. No llm_endpoint, so stage-6 synthesis
    is skipped and the run stays hermetic."""
    builder = BundleBuilder()
    with (
        patch(
            "agents.exec_summary.bundle_builder._ingest_snapshots",
            return_value=deepcopy(snapshots),
        ),
        patch(
            "agents.exec_summary.bundle_builder._load_company_profile",
            return_value={"industry_overlay": "tech_services"},
        ),
        patch("agents.exec_summary.bundle_builder.freshness", return_value="current"),
        patch("agents.exec_summary.bundle_builder.write_bundle_yaml"),
    ):
        return builder.build("Test Co", "uc13_ale", spark=MagicMock())


def test_financial_table_rows_declare_every_key_they_emit():
    rows = (_PARTIAL.get("financials") or {}).get("table_rows") or []
    assert rows, "the fixture produced no financial table rows — the check would pass vacuously"
    financials = _SCHEMA["definitions"]["financials"]
    declared = set(
        (_row_schema(financials["properties"]["table_rows"]).get("properties") or {}).keys()
    )
    assert {"adjusted_ebitda", "adjusted_ebitda_margin_pct"} <= declared
    for row in rows:
        assert not set(row) - declared, f"table row emits {sorted(set(row) - declared)}"


def test_dual_version_ebitda_bundle_survives_validate_bundle_on_the_real_build_path():
    """The highest-risk row: both new table_rows keys plus
    headline_metrics.ltm_adjusted_ebitda are emitted by the mapper and must be
    accepted by validate_bundle, which runs inside BundleBuilder.build — so an
    undeclared key does not degrade a report, it fails the whole VDR run."""
    bundle = _build_bundle(_DUAL_VERSION_SNAPSHOTS)  # raises if validation fails

    row = bundle["financials"]["table_rows"][0]
    assert row["ebitda"] == "11,400"
    assert row["adjusted_ebitda"] == "9,239"
    assert row["ebitda"] != row["adjusted_ebitda"]
    assert bundle["headline_metrics"]["ltm_ebitda"] == "11,400"
    assert bundle["headline_metrics"]["ltm_adjusted_ebitda"] == "9,239"

    validate_bundle(bundle)  # must not raise


def test_baseline_single_version_bundle_still_validates_without_the_new_keys():
    """The three new keys are optional: a bundle whose FTA emitted no
    pf_adjusted record validates with them empty, and none of them entered
    the schema's `required` lists."""
    bundle = _build_bundle(_SNAPSHOTS)
    assert bundle["financials"]["table_rows"][0]["adjusted_ebitda"] == ""
    assert bundle["headline_metrics"]["ltm_adjusted_ebitda"] == ""
    validate_bundle(bundle)

    stripped = deepcopy(bundle)
    stripped["headline_metrics"].pop("ltm_adjusted_ebitda")
    for row in stripped["financials"]["table_rows"]:
        row.pop("adjusted_ebitda", None)
        row.pop("adjusted_ebitda_margin_pct", None)
    validate_bundle(stripped)


def test_additional_properties_false_still_holds_on_both_extended_objects():
    """Guards the guard: the two objects gained keys, so prove the constraint
    that makes declaring them necessary was not relaxed to get there."""
    bundle = _build_bundle(_DUAL_VERSION_SNAPSHOTS)

    stray_headline = deepcopy(bundle)
    stray_headline["headline_metrics"]["ltm_invented_ebitda"] = "$1"
    with pytest.raises(BundleValidationError):
        validate_bundle(stray_headline)

    stray_row = deepcopy(bundle)
    stray_row["financials"]["table_rows"][0]["invented_ebitda"] = "$1"
    with pytest.raises(BundleValidationError):
        validate_bundle(stray_row)


def test_the_populated_fixture_actually_exercises_the_new_mappings():
    """Guards the guard: if these stop being emitted the checks above go quiet
    while still passing, and the next undeclared key ships."""
    assert "top_customers" in (_PARTIAL.get("revenue_quality") or {})
    assert "segment_performance" in (_PARTIAL.get("financials") or {})
    assert "addbacks" in (_PARTIAL.get("qoe") or {})
    assert any("value_kind" in row for row in _PARTIAL.get("kpi_dashboard") or [])
