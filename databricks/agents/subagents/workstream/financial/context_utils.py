"""Shared retrieval and context-building utilities for FTA sub-agents.

Provides:
  semantic_search_with_fallback(...)  — semantic_search with filename-filter retry
  build_focused_context(chunks, max_chars)  — CIM-first, source-type-aware truncation
  assemble_labeled_context(chunk_groups, ...)  — per-query budgets + section headers (OPEX)

Extracted from financial_trends_agent.py so each sub-agent can own its own
retrieval without duplicating the fallback and budget logic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import overload

from agents.shared._types import RouteResult

_TYPE_ORDER = {"table": 0, "vision": 1, "text": 2}

# OPEX per-query budgets — spec §5.12.4 Option C (Q1 financial statements, Q2 WC, Q3 projections).
OPEX_QUERY_BUDGETS = (8_000, 3_000, 4_000)

# Section headers — spec §5.12.4 Option A.
OPEX_SECTION_LABELS = (
    "=== Historical / reported P&L sources ===",
    "=== Working capital sources ===",
    "=== Projection / model sources ===",
)


@dataclass(frozen=True)
class ContextAllocation:
    """Per-chunk context budget metadata for provenance patch (D10)."""

    chunk: object
    chars_allocated: int
    context_section: str


def _default_catalog() -> str:
    return os.environ.get("catalog", "uc13").strip() or "uc13"


def _chunk_tier(c) -> int:
    """0 = CIM, 1 = Priority Tier 1 non-CIM, 2 = other."""
    if "CIM" in (getattr(c, "file_name", "") or "").upper():
        return 0
    if getattr(c, "priority_tier", None) == 1:
        return 1
    return 2


def _chunk_char_limit(c) -> int:
    tier  = _chunk_tier(c)
    stype = getattr(c, "source_type", "text") or "text"
    is_structured = stype in ("table", "vision")
    if tier == 0:
        return 4_000 if is_structured else 2_500
    if tier == 1:
        return 3_000 if is_structured else 1_000
    return 1_000 if is_structured else 500


@overload
def build_focused_context(
    chunks: list,
    max_chars: int = 25_000,
    *,
    track_allocations: bool = False,
) -> tuple[str, str]: ...


@overload
def build_focused_context(
    chunks: list,
    max_chars: int,
    *,
    track_allocations: bool,
) -> tuple[str, str, list[ContextAllocation]]: ...


def build_focused_context(
    chunks: list,
    max_chars: int = 25_000,
    *,
    track_allocations: bool = False,
) -> tuple[str, str] | tuple[str, str, list[ContextAllocation]]:
    """Build a CIM-first, source-type-aware context string from a list of chunks.

    Deduplicates by chunk_text, sorts CIM → PT1 → other with table/vision
    before text within each tier, then fills up to max_chars.

    Returns (context_text, stats_str) or, when ``track_allocations=True``,
    (context_text, stats_str, allocations).
    """
    seen_texts: set[str] = set()
    deduped = []
    for c in chunks:
        txt = getattr(c, "chunk_text", "") or ""
        if txt not in seen_texts:
            seen_texts.add(txt)
            deduped.append(c)

    sorted_chunks = sorted(
        deduped,
        key=lambda c: (
            _chunk_tier(c),
            _TYPE_ORDER.get(getattr(c, "source_type", "text"), 2),
        ),
    )

    parts: list[str] = []
    allocations: list[ContextAllocation] = []
    total_chars = 0
    tier_counts = {0: 0, 1: 0, 2: 0}
    stype_counts: dict[str, int] = {}
    truncated = excluded = 0

    for c in sorted_chunks:
        tier  = _chunk_tier(c)
        stype = getattr(c, "source_type", "text") or "text"
        limit = _chunk_char_limit(c)
        raw   = getattr(c, "chunk_text", "") or ""
        was_truncated = len(raw) > limit
        text  = raw[:limit] + (" …[truncated]" if was_truncated else "")
        part  = f"[File: {c.file_name}] [Section: {c.section_header}]\n{text}"
        if total_chars + len(part) + 8 > max_chars:
            excluded += 1
            continue
        parts.append(part)
        total_chars += len(part) + 8
        tier_counts[tier] += 1
        stype_counts[stype] = stype_counts.get(stype, 0) + 1
        if was_truncated:
            truncated += 1
        if track_allocations:
            allocations.append(
                ContextAllocation(
                    chunk=c,
                    chars_allocated=len(part),
                    context_section="",
                )
            )

    stats = (
        f"{len(parts)}/{len(deduped)} chunks | "
        f"CIM={tier_counts[0]} PT1={tier_counts[1]} other={tier_counts[2]} | "
        f"table={stype_counts.get('table',0)} vision={stype_counts.get('vision',0)} text={stype_counts.get('text',0)} | "
        f"total={total_chars:,} chars"
        + (f" | {truncated} truncated" if truncated else "")
        + (f" | {excluded} excluded" if excluded else "")
    )

    context_text = "\n\n---\n\n".join(parts)
    if track_allocations:
        return context_text, stats, allocations
    return context_text, stats


def assemble_labeled_context(
    chunk_groups: list[list],
    budgets: tuple[int, ...] | None = None,
    section_labels: tuple[str, ...] | None = None,
) -> tuple[str, str, list[ContextAllocation]]:
    """Build labeled multi-section context from per-query chunk groups.

    Each group is ranked and truncated independently via ``build_focused_context``
    with its own budget (spec §5.12.4 Options A + C).
    """
    budgets = budgets or OPEX_QUERY_BUDGETS
    section_labels = section_labels or OPEX_SECTION_LABELS
    if len(chunk_groups) != len(budgets) or len(chunk_groups) != len(section_labels):
        raise ValueError(
            f"chunk_groups ({len(chunk_groups)}), budgets ({len(budgets)}), "
            f"and section_labels ({len(section_labels)}) must align"
        )

    sections: list[str] = []
    stats_parts: list[str] = []
    all_allocations: list[ContextAllocation] = []
    for idx, (group, budget, label) in enumerate(
        zip(chunk_groups, budgets, section_labels, strict=True),
    ):
        body, group_stats, group_allocations = build_focused_context(
            group,
            max_chars=budget,
            track_allocations=True,
        )
        all_allocations.extend(
            ContextAllocation(
                chunk=alloc.chunk,
                chars_allocated=alloc.chars_allocated,
                context_section=label,
            )
            for alloc in group_allocations
        )
        if body:
            sections.append(f"{label}\n{body}")
        else:
            sections.append(f"{label}\n(no chunks retrieved)")
        stats_parts.append(f"Q{idx + 1}({budget:,}): {group_stats}")

    return "\n\n".join(sections), " | ".join(stats_parts), all_allocations


def semantic_search_with_fallback(
    company_name: str,
    spark,
    query: str,
    workstream_filter: list,
    top_k: int,
    file_name_filter,
    min_chunk_length: int = 150,
    min_results: int = 3,
    source_type_priority: bool = False,
    source_type_filter: list | None = None,
    retrieval_mode: str = "semantic",
    intent_id: str | None = None,
) -> RouteResult:
    """Semantic search with automatic filename-filter fallback.

    Calls ``semantic_search`` (merge-rank enhancements live in ``retrieval.py``).
    ``retrieval_mode`` is accepted for FTA/sub-agent call-site compatibility but
    does not alter dispatch after Route A removal.
    ``intent_id`` is propagated to ``semantic_search`` for M-RE2 D3 provenance
    attribution; FTA sub-agents must pass the registry intent id.

    If result count < min_results with the filename filter, retries without it so
    documents with non-standard names are not silently excluded.
    """
    from agents.shared.retrieval import semantic_search

    catalog = _default_catalog()
    index_name = f"{catalog}.ingestion.embeddings_index"
    search_kwargs = dict(
        query=query,
        spark=spark,
        company_name=company_name,
        top_k=top_k,
        workstream_filter=workstream_filter,
        file_name_filter=file_name_filter,
        min_chunk_length=min_chunk_length,
        source_type_priority=source_type_priority,
        source_type_filter=source_type_filter,
        catalog=catalog,
        index_name=index_name,
        intent_id=intent_id,
    )

    result = semantic_search(**search_kwargs)
    if len(result.chunks) < min_results and file_name_filter is not None:
        result = semantic_search(**{**search_kwargs, "file_name_filter": None})

    print(f"  retrieval_mode={retrieval_mode} returned {len(result.chunks)} chunks")
    return result
