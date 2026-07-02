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
    ContextAllocation,
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
    context, stats, allocations = assemble_labeled_context(groups)

    for label in OPEX_SECTION_LABELS:
        assert label in context
    assert "payroll 100" in context
    assert "DPO 45 days" in context
    assert "OPEX forecast 2025" in context
    assert "Q1(8,000):" in stats
    assert "Q2(3,000):" in stats
    assert "Q3(4,000):" in stats
    assert len(allocations) == 3
    assert all(isinstance(alloc, ContextAllocation) for alloc in allocations)
    assert {alloc.context_section for alloc in allocations} == set(OPEX_SECTION_LABELS)


def test_assemble_labeled_context_empty_group_still_emits_header():
    groups = [[], [], []]
    context, _, allocations = assemble_labeled_context(groups)

    for label in OPEX_SECTION_LABELS:
        assert label in context
    assert "(no chunks retrieved)" in context
    assert allocations == []


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

    labeled_context, _, labeled_allocations = assemble_labeled_context(groups)
    pooled_context, _ = build_focused_context(q1, max_chars=15_000)

    labeled_q1_body = labeled_context.split(OPEX_SECTION_LABELS[1])[0]
    assert labeled_q1_body.count("[File: CIM.pdf]") < pooled_context.count("[File: CIM.pdf]")
    assert all(alloc.chars_allocated > 0 for alloc in labeled_allocations)


def test_opex_basis_preference_instruction_present():
    assert "opex_breakdown" in OPEX_BASIS_PREFERENCE_INSTRUCTION
    assert "Historical P&L" in OPEX_BASIS_PREFERENCE_INSTRUCTION


def test_build_focused_context_track_allocations_returns_metadata():
    chunks = [
        _chunk(file_name="hist.pdf", section_header="Historical P&L", text="payroll 100"),
    ]
    context, stats, allocations = build_focused_context(
        chunks,
        max_chars=8_000,
        track_allocations=True,
    )

    assert "payroll 100" in context
    assert "1/1 chunks" in stats
    assert len(allocations) == 1
    assert allocations[0].chars_allocated > 0
    assert allocations[0].context_section == ""


def test_opex_provenance_patch_sets_chars_allocated_on_open_run(tmp_path):
    """Kill criterion falsifier: OPEX provenance rows carry non-null allocation metadata."""
    import sys

    _repo_root = Path(__file__).resolve().parents[1]
    for _entry in (str(_repo_root / "databricks"), str(_repo_root)):
        if _entry not in sys.path:
            sys.path.insert(0, _entry)

    from agents.shared.run_context import close_agent_run, open_agent_run, set_pipeline_thread
    from eval.retrieval.provenance import ProvenanceEmitter
    from eval.retrieval.store import SqliteEvalStore

    store = SqliteEvalStore(tmp_path / "re2_store.sqlite")
    try:
        set_pipeline_thread("thread-opex-alloc")
        run_id = open_agent_run(
            "fta",
            company_name="Elder Care",
            catalog="uc13_ale",
            affected_intents=["fta.opex.q1_financial_statements"],
            store=store,
        )
        chunk = _chunk(
            file_name="hist.pdf",
            section_header="Historical P&L Summary",
            text="payroll 100",
        )
        route = SimpleNamespace(
            chunks=[chunk],
            mode="semantic",
            scores=[0.9],
        )
        ProvenanceEmitter.emit(
            route_result=route,
            company_name="Elder Care",
            query="operating expenses",
            intent_id="fta.opex.q1_financial_statements",
        )

        _, _, allocations = assemble_labeled_context(
            [[chunk], [], []],
        )
        ProvenanceEmitter.patch_context_allocations(
            "fta.opex.q1_financial_statements",
            [
                alloc
                for alloc in allocations
                if alloc.context_section == OPEX_SECTION_LABELS[0]
            ],
        )

        row = store._conn.execute(
            """
            SELECT chars_allocated, context_section
            FROM retrieval_provenance
            WHERE run_id = ? AND intent_id = ? AND chunk_id = ?
            """,
            (run_id, "fta.opex.q1_financial_statements", chunk.chunk_id),
        ).fetchone()
        assert row is not None
        assert row["chars_allocated"] is not None
        assert row["chars_allocated"] > 0
        assert row["context_section"] == OPEX_SECTION_LABELS[0]
    finally:
        try:
            close_agent_run()
        except Exception:
            pass
        store.close()
