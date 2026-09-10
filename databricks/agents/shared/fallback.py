"""Shared filename-filter retry fallback for BMA and Legal retrieval wrappers (R-03)."""

from __future__ import annotations

from typing import Any

from agents.shared._types import RouteResult
from agents.shared.retrieval import semantic_search

# Same vocabulary as retrieval.py; secondary key only — do not change merge-rank.
_TYPE_ORDER = {"table": 0, "vision": 1, "text": 2}


def _chunk_key(chunk: Any, index: int) -> str:
    cid = getattr(chunk, "chunk_id", None)
    if cid:
        return str(cid)
    return f"anon:{id(chunk)}:{index}"


def _scored_pairs(result: RouteResult) -> list[tuple[Any, float]]:
    chunks = list(result.chunks or [])
    scores = list(result.scores or [])
    if len(scores) < len(chunks):
        scores.extend([0.0] * (len(chunks) - len(scores)))
    return list(zip(chunks, scores[: len(chunks)]))


def _union_merge_cap(
    filtered: RouteResult,
    unfiltered: RouteResult,
    *,
    top_k: int,
    source_type_priority: bool = False,
) -> RouteResult:
    """Union filtered + unfiltered pools, keep best score per chunk, cap to top_k.

    Scores on each RouteResult are already similarity-primary merge scores
    (``sim + 0.05 * tier_weight``). This does not raise ``_TIER_BONUS`` or restore
    multiplicative rank.
    """
    by_id: dict[str, tuple[Any, float]] = {}
    for origin in (filtered, unfiltered):
        for index, (chunk, score) in enumerate(_scored_pairs(origin)):
            key = _chunk_key(chunk, index)
            prev = by_id.get(key)
            if prev is None or score > prev[1]:
                by_id[key] = (chunk, float(score))

    def _sort_key(item: tuple[Any, float]) -> tuple:
        chunk, score = item
        if source_type_priority:
            return (-score, _TYPE_ORDER.get(getattr(chunk, "source_type", "text"), 2))
        return (-score, 0)

    ranked = sorted(by_id.values(), key=_sort_key)[:top_k]
    chunks = [chunk for chunk, _ in ranked]
    scores = [score for _, score in ranked]
    modes = {filtered.mode, unfiltered.mode}
    if not chunks:
        mode = "empty"
    elif "semantic" in modes:
        mode = "semantic"
    elif "keyword" in modes:
        mode = "keyword"
    else:
        mode = "empty"
    return RouteResult(chunks=chunks, mode=mode, scores=scores)


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
    vs_metadata_filters: bool = False,
) -> tuple[RouteResult, bool]:
    """Semantic search with filename/workstream-filter empty-path fallback.

    When the filtered search returns **0** hits and a filename or workstream
    filter was applied, retries once with both filters dropped and **replaces**
    (union with empty is the retry set). That is the empty-path: gold tagged
    outside the caller's workstream (e.g. BUSINESS_MODEL vs CQA CUSTOMER/…)
    can enter the pool.

    When the filtered search returns `< min_results` (but not 0) and a filename
    filter was applied, retries once without the filename filter and
    **replaces**. When it returns `>= min_results` with a filename filter
    applied, retries once without the filename filter and **unions** via
    ``_union_merge_cap`` (best merge-score per chunk, cap ``top_k``) — this is
    what recovered Clearsulting's `fta.revenue.q4_customer_concentration_fallback`
    (cycle 11, `enhancement_0d673a9842f2`).

    A broader "union whenever `n>0`, regardless of `min_results`, and including
    `workstream_filter`" variant was tried and measured cycle 13
    (`enhancement_7f9d24a9f92b` vs SPG `baseline_7abfa840a717`) — 0/19 named
    zeros lifted, reverted at gate 2. Do not re-add it without a new hypothesis
    for *why* an unfiltered union would surface different gold than the
    filtered pass already returned (see `dead_hypotheses` /
    `spg_two_step_zero_overlap_union`, cycle-state.json).

    Returns ``(result, used_fallback)`` so callers can append their own trace shape
    when fallback fires.
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
        vs_metadata_filters=vs_metadata_filters,
    )
    result = semantic_search(**search_kwargs)

    used_fallback = False
    if len(result.chunks) == 0 and (file_name_filter or workstream_filter):
        used_fallback = True
        result = semantic_search(
            **{
                **search_kwargs,
                "file_name_filter": None,
                "workstream_filter": None,
            }
        )
        return result, used_fallback

    if len(result.chunks) < min_results and file_name_filter is not None:
        used_fallback = True
        result = semantic_search(**{**search_kwargs, "file_name_filter": None})
    elif len(result.chunks) >= min_results and file_name_filter is not None:
        used_fallback = True
        unfiltered = semantic_search(**{**search_kwargs, "file_name_filter": None})
        result = _union_merge_cap(
            result,
            unfiltered,
            top_k=top_k,
            source_type_priority=source_type_priority,
        )

    return result, used_fallback
