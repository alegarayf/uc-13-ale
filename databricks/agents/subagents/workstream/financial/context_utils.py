"""Shared retrieval and context-building utilities for FTA sub-agents.

Provides:
  semantic_search_with_fallback(...)  — semantic_search with filename-filter retry
  build_focused_context(chunks, max_chars)  — CIM-first, source-type-aware truncation

Extracted from financial_trends_agent.py so each sub-agent can own its own
retrieval without duplicating the fallback and budget logic.
"""

from __future__ import annotations

import os

from agents.shared._types import RouteResult

_TYPE_ORDER = {"table": 0, "vision": 1, "text": 2}


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


def build_focused_context(chunks: list, max_chars: int = 25_000) -> tuple[str, str]:
    """Build a CIM-first, source-type-aware context string from a list of chunks.

    Deduplicates by chunk_text, sorts CIM → PT1 → other with table/vision
    before text within each tier, then fills up to max_chars.

    Returns (context_text, stats_str).
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

    stats = (
        f"{len(parts)}/{len(deduped)} chunks | "
        f"CIM={tier_counts[0]} PT1={tier_counts[1]} other={tier_counts[2]} | "
        f"table={stype_counts.get('table',0)} vision={stype_counts.get('vision',0)} text={stype_counts.get('text',0)} | "
        f"total={total_chars:,} chars"
        + (f" | {truncated} truncated" if truncated else "")
        + (f" | {excluded} excluded" if excluded else "")
    )

    return "\n\n---\n\n".join(parts), stats


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
) -> RouteResult:
    """Dispatch retrieval by mode with automatic filename-filter fallback on semantic paths.

    ``retrieval_mode="routed"`` calls Route A (``route_chunks``); ``"semantic"`` and
    ``"enhanced_semantic"`` call ``semantic_search`` (Route B enhancements are in
    ``retrieval.py``). Any unrecognized value falls through to the semantic path.

    If result count < min_results with the filename filter, retries without it so
    documents with non-standard names are not silently excluded (semantic paths only).
    """
    if retrieval_mode == "routed":
        from agents.shared.route_chunks import route_chunks

        result = route_chunks(
            company_name=company_name,
            spark=spark,
            workstream_filter=workstream_filter,
            top_k=top_k,
            file_name_filter=file_name_filter,
            min_chunk_length=min_chunk_length,
            source_type_filter=source_type_filter,
        )
        print(f"  retrieval_mode={retrieval_mode} returned {len(result.chunks)} chunks")
        return result

    from agents.shared.retrieval import semantic_search

    catalog = _default_catalog()
    index_name = f"{catalog}.ingestion.embeddings_index"
    search_kwargs = dict(
        catalog=catalog,
        index_name=index_name,
    )

    chunks = semantic_search(
        query=query,
        spark=spark,
        company_name=company_name,
        top_k=top_k,
        workstream_filter=workstream_filter,
        file_name_filter=file_name_filter,
        min_chunk_length=min_chunk_length,
        source_type_priority=source_type_priority,
        source_type_filter=source_type_filter,
        **search_kwargs,
    )
    if len(chunks) < min_results and file_name_filter is not None:
        chunks = semantic_search(
            query=query,
            spark=spark,
            company_name=company_name,
            top_k=top_k,
            workstream_filter=workstream_filter,
            file_name_filter=None,
            min_chunk_length=min_chunk_length,
            source_type_priority=source_type_priority,
            source_type_filter=source_type_filter,
            **search_kwargs,
        )
    mode = "semantic" if retrieval_mode in ("semantic", "enhanced_semantic") else "semantic"
    result = RouteResult(chunks=chunks, mode=mode, scores=None)
    print(f"  retrieval_mode={retrieval_mode} returned {len(result.chunks)} chunks")
    return result
