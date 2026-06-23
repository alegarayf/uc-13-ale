"""
Route A metadata router — SQL-based chunk selection without query-time embeddings.

Joins uc13.ingestion.chunks to uc13.classification.doc_relevance and applies the same
filter semantics as semantic_search (post-SQL Python filters for file_name, length,
source_type; SQL filters for company, workstream, tier, keyword).
"""

from __future__ import annotations

import re

from agents.shared._types import RouteResult

_ARRAYS_OVERLAP_AVAILABLE: bool | None = None


def _escape_sql_string(value: str) -> str:
    return value.replace("'", "''")


def _probe_arrays_overlap(spark) -> bool:
    """Cache whether arrays_overlap is available on this DBR runtime."""
    global _ARRAYS_OVERLAP_AVAILABLE
    if _ARRAYS_OVERLAP_AVAILABLE is not None:
        return _ARRAYS_OVERLAP_AVAILABLE
    try:
        spark.sql("SELECT arrays_overlap(array('A'), array('A')) AS ok").collect()
        _ARRAYS_OVERLAP_AVAILABLE = True
    except Exception:
        _ARRAYS_OVERLAP_AVAILABLE = False
    return _ARRAYS_OVERLAP_AVAILABLE


def _workstream_overlap_clause(workstream_filter: list[str], spark) -> str:
    if not workstream_filter:
        return "TRUE"
    if _probe_arrays_overlap(spark):
        ws_literals = ", ".join(
            f"'{_escape_sql_string(ws)}'" for ws in workstream_filter
        )
        return f"arrays_overlap(r.workstream, array({ws_literals}))"
    or_parts = [
        f"array_contains(r.workstream, '{_escape_sql_string(ws)}')"
        for ws in workstream_filter
    ]
    return "(" + " OR ".join(or_parts) + ")"


def _keyword_clause(keyword_filter: str | None) -> str:
    if not keyword_filter:
        return "TRUE"
    words = re.sub(r"[^\w\s]", "", keyword_filter).split()[:5]
    words = [w for w in words if w]
    if not words:
        return "TRUE"
    conditions = [
        (
            f"(c.chunk_text LIKE '%{_escape_sql_string(w)}%' "
            f"OR c.section_header LIKE '%{_escape_sql_string(w)}%')"
        )
        for w in words
    ]
    return "(" + " OR ".join(conditions) + ")"


def route_chunks(
    company_name: str,
    spark,
    workstream_filter: list[str],
    top_k: int = 10,
    file_name_filter: list[str] | None = None,
    tier_filter: int | None = None,
    min_chunk_length: int = 100,
    source_type_filter: list[str] | None = None,
    keyword_filter: str | None = None,
) -> RouteResult:
    """Select chunks via metadata routing (no embeddings / vector search)."""
    fetch_k = top_k * 3
    company_escaped = _escape_sql_string(company_name)
    tier_clause = (
        "" if tier_filter is None else f"AND r.priority_tier <= {int(tier_filter)}"
    )
    ws_clause = _workstream_overlap_clause(workstream_filter, spark)
    kw_clause = _keyword_clause(keyword_filter)

    sql = f"""
        SELECT
            c.chunk_id,
            c.file_name,
            c.chunk_text,
            c.section_header,
            c.page_start,
            COALESCE(c.source_type, 'text') AS source_type,
            r.workstream,
            r.priority_tier
        FROM uc13.ingestion.chunks c
        JOIN uc13.classification.doc_relevance r
            ON c.file_name = r.filename
           AND c.company_name = r.company_name
        WHERE c.company_name = '{company_escaped}'
          AND {ws_clause}
          AND r.should_parse = true
          {tier_clause}
          AND ({kw_clause})
        ORDER BY r.priority_tier ASC NULLS LAST, c.file_name, c.chunk_index
        LIMIT {fetch_k}
    """

    chunks = spark.sql(sql).collect()

    if min_chunk_length > 0:
        chunks = [
            c for c in chunks if len(c.chunk_text or "") >= min_chunk_length
        ]

    if file_name_filter:
        chunks = [
            c
            for c in chunks
            if any(
                p.lower() in (c.file_name or "").lower() for p in file_name_filter
            )
        ]

    if source_type_filter:
        chunks = [
            c
            for c in chunks
            if getattr(c, "source_type", "text") in source_type_filter
        ]

    chunks = chunks[:top_k]

    if not chunks:
        raise ValueError(
            f"route_chunks: no results — company={company_name} "
            f"workstream={workstream_filter}"
        )

    print(
        f"  route_chunks '{company_name}' ws={workstream_filter}: "
        f"{len(chunks)} chunks"
    )
    return RouteResult(chunks=chunks, mode="routed", scores=None)
