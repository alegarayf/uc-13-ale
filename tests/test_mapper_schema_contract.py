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

from pathlib import Path

import pytest
import yaml

from agents.exec_summary.field_mapping import apply_field_mappings

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


def test_the_populated_fixture_actually_exercises_the_new_mappings():
    """Guards the guard: if these stop being emitted the checks above go quiet
    while still passing, and the next undeclared key ships."""
    assert "top_customers" in (_PARTIAL.get("revenue_quality") or {})
    assert "segment_performance" in (_PARTIAL.get("financials") or {})
    assert "addbacks" in (_PARTIAL.get("qoe") or {})
    assert any("value_kind" in row for row in _PARTIAL.get("kpi_dashboard") or [])
