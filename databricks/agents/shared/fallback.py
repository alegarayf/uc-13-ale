"""Shared filename-filter retry fallback for BMA and Legal retrieval wrappers (R-03)."""

from __future__ import annotations

from agents.shared._types import RouteResult
from agents.shared.retrieval import semantic_search


def semantic_search_with_fallback(
    *,
    company_name: str,
    spark,
    query: str,
    workstream_filter: list,
    top_k: int,
    file_name_filter,
    min_chunk_length: int = 150,
    min_results: int = 3,
    catalog: str | None = None,
    source_type_priority: bool = False,
    source_type_filter: list[str] | None = None,
    intent_id: str | None = None,
) -> tuple[RouteResult, bool]:
    """Semantic search with automatic fallback when the filename filter is too narrow.

    When ``len(chunks) < min_results`` and ``file_name_filter`` is set, retries once
    without the filename filter. Returns ``(result, used_fallback)`` so callers can
    append their own trace shape when fallback fires.
    """
    search_kwargs = dict(
        query=query,
        spark=spark,
        company_name=company_name,
        top_k=top_k,
        workstream_filter=workstream_filter,
        file_name_filter=file_name_filter,
        min_chunk_length=min_chunk_length,
        catalog=catalog,
        source_type_priority=source_type_priority,
        source_type_filter=source_type_filter,
        intent_id=intent_id,
    )
    result = semantic_search(**search_kwargs)

    used_fallback = False
    if len(result.chunks) < min_results and file_name_filter is not None:
        used_fallback = True
        result = semantic_search(**{**search_kwargs, "file_name_filter": None})

    return result, used_fallback
