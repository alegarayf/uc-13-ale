"""Unit tests for FTA BasisCrossCheck (Option D) — spec D6."""

from __future__ import annotations

import sys
from pathlib import Path

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

from agents.subagents.workstream.financial.basis_cross_check import (  # noqa: E402
    basis_cross_check,
    classify_basis,
    is_duplicate_basis_discrepancy,
)


def _opex(*, doc: str, loc: str, category: str = "Payroll") -> dict:
    return {
        "category": category,
        "amount_stated": "$100",
        "period": "FY23A",
        "source_doc": doc,
        "source_location": loc,
    }


def _revenue(*, doc: str, loc: str) -> dict:
    return {
        "period": "FY23A",
        "label": "Total Revenue",
        "revenue_stated": "$1,000",
        "source_doc": doc,
        "source_location": loc,
    }


def test_classify_basis_projection_and_historical():
    assert classify_basis(_opex(doc="CIM.pdf", loc="Pro Forma Income Statement")) == "projection"
    assert classify_basis(_revenue(doc="CIM.pdf", loc="Historical P&L Summary")) == "historical"


def test_basis_cross_check_flags_projection_opex_historical_revenue():
    entries = basis_cross_check(
        [_opex(doc="2024 Elder Care - CIM_vF.pdf", loc="Pro Forma Income Statement p.52")],
        [_revenue(doc="2024 Elder Care - CIM_vF.pdf", loc="Historical P&L Summary p.49")],
    )

    assert len(entries) == 1
    assert entries[0]["metric"] == "basis_mismatch"
    assert "OPEX:" in entries[0]["conflicting_values"][0]
    assert "Revenue:" in entries[0]["conflicting_values"][1]
    assert "projection" in entries[0]["note"].lower()


def test_basis_cross_check_no_flag_when_both_historical():
    entries = basis_cross_check(
        [_opex(doc="P&L.xlsx", loc="Historical P&L Summary")],
        [_revenue(doc="P&L.xlsx", loc="Reported financials")],
    )
    assert entries == []


def test_basis_cross_check_no_flag_when_both_projection():
    entries = basis_cross_check(
        [_opex(doc="Model.xlsx", loc="Projection assumptions")],
        [_revenue(doc="Model.xlsx", loc="Forecast revenue")],
    )
    assert entries == []


def test_basis_cross_check_empty_inputs():
    assert basis_cross_check([], [_revenue(doc="a.pdf", loc="Historical P&L")]) == []
    assert basis_cross_check([_opex(doc="a.pdf", loc="Projection")], []) == []


def test_is_duplicate_basis_discrepancy_detects_same_file_pair():
    candidate = {
        "metric": "basis_mismatch",
        "conflicting_values": [
            "OPEX: CIM.pdf (Pro Forma Income Statement)",
            "Revenue: CIM.pdf (Historical P&L Summary)",
        ],
        "note": "test",
    }
    existing = [
        {
            "metric": "EBITDA",
            "conflicting_values": [
                "CIM.pdf: $2M",
                "CIM.pdf: $3M",
            ],
            "note": "Conflicting EBITDA between CIM.pdf sections",
        }
    ]
    assert is_duplicate_basis_discrepancy(candidate, existing) is True


def test_is_duplicate_basis_discrepancy_allows_distinct_pair():
    candidate = {
        "metric": "basis_mismatch",
        "conflicting_values": [
            "OPEX: Model.xlsx (Projection)",
            "Revenue: P&L.xlsx (Historical P&L Summary)",
        ],
        "note": "test",
    }
    existing = [
        {
            "metric": "Revenue",
            "conflicting_values": ["CIM.pdf: $1M", "Tax.pdf: $2M"],
            "note": "Different docs",
        }
    ]
    assert is_duplicate_basis_discrepancy(candidate, existing) is False


def test_basis_cross_check_ambiguous_dual_pattern_does_not_flag():
    """Falsifier: dual historical+projection labels must not emit basis_mismatch."""
    opex = [_opex(doc="CIM.pdf", loc="Historical Pro Forma bridge")]
    revenue = [_revenue(doc="CIM.pdf", loc="Reported actuals")]
    assert basis_cross_check(opex, revenue) == []
