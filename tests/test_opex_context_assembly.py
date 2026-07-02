"""Unit tests for OPEX labeled context assembly — spec §5.12.4 Options A + C."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

from agents.subagents.workstream.financial.context_utils import (  # noqa: E402
    OPEX_QUERY_BUDGETS,
    OPEX_SECTION_LABELS,
    assemble_labeled_context,
    build_focused_context,
)
from agents.subagents.workstream.financial.shared_prompts import (  # noqa: E402
    OPEX_BASIS_PREFERENCE_INSTRUCTION,
)


def _chunk(*, file_name: str, section_header: str, text: str, tier: int = 2):
    return SimpleNamespace(
        chunk_id=f"id-{file_name}-{len(text)}",
        file_name=file_name,
        chunk_text=text,
        section_header=section_header,
        page_start=1,
        source_type="text",
        workstream=["FINANCIAL"],
        priority_tier=tier,
    )


def test_opex_query_budgets_match_spec():
    assert OPEX_QUERY_BUDGETS == (8_000, 3_000, 4_000)


def test_opex_section_labels_match_spec():
    assert OPEX_SECTION_LABELS == (
        "=== Historical / reported P&L sources ===",
        "=== Working capital sources ===",
        "=== Projection / model sources ===",
    )


def test_assemble_labeled_context_includes_all_section_headers():
    groups = [
        [_chunk(file_name="hist.pdf", section_header="Historical P&L Summary", text="payroll 100")],
        [_chunk(file_name="bs.pdf", section_header="Balance Sheet", text="DPO 45 days")],
        [_chunk(file_name="model.xlsx", section_header="Projection", text="OPEX forecast 2025")],
    ]
    context, stats = assemble_labeled_context(groups)

    for label in OPEX_SECTION_LABELS:
        assert label in context
    assert "payroll 100" in context
    assert "DPO 45 days" in context
    assert "OPEX forecast 2025" in context
    assert "Q1(8,000):" in stats
    assert "Q2(3,000):" in stats
    assert "Q3(4,000):" in stats


def test_assemble_labeled_context_empty_group_still_emits_header():
    groups = [[], [], []]
    context, _ = assemble_labeled_context(groups)

    for label in OPEX_SECTION_LABELS:
        assert label in context
    assert "(no chunks retrieved)" in context


def test_assemble_labeled_context_applies_per_group_budget_not_pooled():
    """Falsifier: pooled 15K would admit more Q1 chunks than the 8K per-query cap."""
    q1 = [
        _chunk(
            file_name="CIM.pdf",
            section_header="Historical P&L Summary",
            text="x" * 2_400 + f" chunk-{i}",
            tier=0,
        )
        for i in range(6)
    ]
    groups = [q1, [], []]

    labeled_context, _ = assemble_labeled_context(groups)
    pooled_context, _ = build_focused_context(q1, max_chars=15_000)

    labeled_q1_body = labeled_context.split(OPEX_SECTION_LABELS[1])[0]
    assert labeled_q1_body.count("[File: CIM.pdf]") < pooled_context.count("[File: CIM.pdf]")


def test_opex_basis_preference_instruction_present():
    assert "opex_breakdown" in OPEX_BASIS_PREFERENCE_INSTRUCTION
    assert "Historical P&L" in OPEX_BASIS_PREFERENCE_INSTRUCTION
