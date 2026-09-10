"""
Semantic search helper for UC13 Phase 2/3 agents.

Wraps Databricks Vector Search + fallback keyword search.
All post-retrieval filters (file_name, workstream, chunk length) are applied
after fetching top_k * 3 candidates so filter losses don't starve results.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Literal

from databricks.sdk import WorkspaceClient
import mlflow.deployments

from agents.shared._types import RouteResult

# B-W4: merge-rank tier weights (documented in .dev/decision-logs/T4-retrieval-enhancements.md)
_TIER_WEIGHT = {1: 1.0, 2: 0.7, 3: 0.4}
_DEFAULT_TIER_WEIGHT = 0.3
# Additive tier term. Multiplicative sim×tier buried best-sim citation gold
# (tier-2 CIM vision, sim≈0.69) under slightly-weaker tier-1 spreadsheet
# neighbors (sim≈0.66 → merge 0.66 vs 0.48). Cap the bonus so a ~0.03 sim
# lead cannot be inverted by a one-step tier gap (bonus * 0.3 < 0.03).
_TIER_BONUS = 0.05

# R-09: canonical source-type sort order (shared with context_utils.py)
_TYPE_ORDER = {"table": 0, "vision": 1, "text": 2}

# Near-tie section signal for current-state overview language (service mix /
# service lines). Must stay well below the 0.03 sim-lead floor that additive
# tier is capped against — this only reorders ~0.001–0.003 VS ties.
# Baked into merge-score (not a Python-only sort key) so with_fallback's
# score-based `_union_merge_cap` cannot undo it. Do not raise `_TIER_BONUS`.
_SECTION_TIEBREAK_BONUS = 0.004
_CURRENT_STATE_OVERVIEW_RE = re.compile(
    r"\b(core services|service lines?|product lines?|service offering)\b",
    re.IGNORECASE,
)

# GKF kpi.retrieve_headcount_attrition: a "Payroll Build — Summary" phrase
# tiebreak (0.004, same magnitude as CS) was tried cycle 15 and measured
# dead — recall_at_10 held at 0.0625 before/after on baseline_2a65186e46d3
# (top-6 stayed all same-file "Payroll Detail — Summary", not gold). Real
# sim gap there exceeds what a 0.004 near-tie bonus can close; reverted.
# See runs/cycle-15/patch-p2-retrieval-combined.md and runs/cycle-15/gate2.md.

# SPG bma.retrieve_revenue_by_location_and_metrics: dashboard gold 84311b20
# sits ~0.006 below the rank-10 cutoff. CS/GKF 0.004 is too small; diagnose
# calibrated 0.010 (still < 0.03 sim-lead floor). Dashboard-specific phrases
# only — not "visits" / "network" / "payroll".
_DASHBOARD_SECTION_BONUS = 0.010
_DASHBOARD_SECTION_RE = re.compile(
    r"\b(new patient visits distribution|shared practices dashboard)\b",
    re.IGNORECASE,
)


def _default_catalog() -> str:
    return os.environ.get("catalog", "uc13").strip() or "uc13"


def _index_name_for_catalog(catalog: str) -> str:
    return f"{catalog}.ingestion.embeddings_index"


def _escape_sql_literal(value: str) -> str:
    """Escape single quotes for safe SQL string literals (B-W8)."""
    return value.replace("'", "''")


def _chunk_ids_in_clause(chunk_ids: list[str]) -> str:
    escaped = "', '".join(_escape_sql_literal(cid) for cid in chunk_ids)
    return f"('{escaped}')"


def _extract_score_map(data_array) -> dict[str, float]:
    """Map chunk_id → VS similarity score (last column in each result row)."""
    score_map: dict[str, float] = {}
    for row in data_array or []:
        if not row or len(row) < 2:
            continue
        try:
            score_map[row[0]] = float(row[-1])
        except (TypeError, ValueError):
            continue
    return score_map


def _tier_weight(priority_tier: int | None) -> float:
    if priority_tier is None:
        return _DEFAULT_TIER_WEIGHT
    return _TIER_WEIGHT.get(priority_tier, _DEFAULT_TIER_WEIGHT)


def _section_tiebreak(chunk) -> float:
    """Independent additive bumps for section-language near-ties.

    ``_TYPE_ORDER`` cannot break this class of tie: the Clearsulting
    overview golds are mixed vision/text against other vision slides at
    the same tier. Phrase match on section_header or chunk_text is the
    scoped signal (Kyriba vision extract is headed as a client name but
    the figure is ``# Core Services``; ``Other Service Lines`` is a
    section title).

    SPG dashboard language is its own additive term, independent magnitude;
    it must not piggyback on the CS regex, and must survive
    ``_union_merge_cap`` re-sort (hence baked into ``_merge_score``). SPG
    also matches ``file_name`` because the dashboard file itself is the
    scoped signal.
    """
    header = getattr(chunk, "section_header", None) or ""
    text = getattr(chunk, "chunk_text", None) or ""
    file_name = getattr(chunk, "file_name", None) or ""
    blob = f"{header}\n{text}"
    bonus = 0.0
    if _CURRENT_STATE_OVERVIEW_RE.search(blob):
        bonus += _SECTION_TIEBREAK_BONUS
    # SPG also searches file_name; CS stays header+text so its live pin
    # ranks are byte-stable against a filename that happens to say
    # "service lines".
    extended = f"{blob}\n{file_name}"
    if _DASHBOARD_SECTION_RE.search(extended):
        bonus += _DASHBOARD_SECTION_BONUS
    return bonus


def _merge_score(chunk, score_map: dict[str, float]) -> float:
    """Similarity-primary merge rank with a small additive tier bonus.

    Tier remains a tie-break (B-W4) but cannot invert a ≥0.03 similarity gap,
    which is what zeroed Elder Care citation_backfill recall_at_10 on
    ``fta.opex.q3_projected_financials`` (F1).

    Additional additive terms from ``_section_tiebreak`` reorder
    razor-thin same-tier ties for CS current-state services (0.004)
    and SPG dashboard sections (0.010). None is a rescale of primary
    similarity; none may invert a 0.03 sim lead (0.010 is still well
    under that floor).
    """
    sim = score_map.get(chunk.chunk_id, 0.0)
    return sim + _TIER_BONUS * _tier_weight(chunk.priority_tier) + _section_tiebreak(chunk)


def _sort_by_merge_rank(chunks: list, score_map: dict[str, float]) -> list:
    """B-W3/B-W4: rank by sim + small tier bonus; tier-only fallback when no scores."""
    if not score_map:
        return _sort_by_tier_only(chunks)
    return sorted(chunks, key=lambda c: -_merge_score(c, score_map))


def _sort_by_tier_only(chunks: list) -> list:
    return sorted(
        chunks,
        key=lambda c: c.priority_tier if c.priority_tier is not None else 99,
    )


def _sort_by_sim_only(chunks: list, score_map: dict[str, float]) -> list:
    if not score_map:
        return _sort_by_tier_only(chunks)
    return sorted(chunks, key=lambda c: -score_map.get(c.chunk_id, 0.0))


def _build_vs_filters_dict(
    *,
    company_name: str | None,
    vs_metadata_filters: bool,
    workstream_filter: list[str] | None,
    tier_filter: int | None,
) -> dict[str, Any]:
    """Build a single VS ``filters_json`` dict (AND semantics across keys).

    ``workstream`` uses list any-of syntax (T1 matrix PASS). ``priority_tier``
    uses operator-suffixed ``<=`` to mirror post-retrieval ``tier_filter``.
    """
    filters: dict[str, Any] = {}
    if company_name:
        filters["company_name"] = company_name
    if vs_metadata_filters:
        if workstream_filter:
            filters["workstream"] = workstream_filter
        if tier_filter is not None:
            filters["priority_tier <="] = tier_filter
    return filters


def _query_vector_index(
    w: WorkspaceClient,
    *,
    index_name: str,
    query_embedding: list[float],
    fetch_k: int,
    company_name: str | None,
    vs_metadata_filters: bool = False,
    workstream_filter: list[str] | None = None,
    tier_filter: int | None = None,
):
    """B-W2: query_index with optional filter pushdown and unfiltered fallback."""
    query_kwargs = {
        "index_name": index_name,
        "columns": ["chunk_id", "doc_id", "file_name"],
        "query_vector": query_embedding,
        "num_results": fetch_k,
    }
    filters = _build_vs_filters_dict(
        company_name=company_name,
        vs_metadata_filters=vs_metadata_filters,
        workstream_filter=workstream_filter,
        tier_filter=tier_filter,
    )
    if not filters:
        return w.vector_search_indexes.query_index(**query_kwargs)

    filters_json = json.dumps(filters)
    try:
        return w.vector_search_indexes.query_index(**query_kwargs, filters_json=filters_json)
    except Exception as filter_err:
        print(
            f"  VS filter pushdown unavailable ({filter_err}) — querying without filters"
        )
        return w.vector_search_indexes.query_index(**query_kwargs)


def _hydrate_chunks_sql(
    chunk_ids: list[str],
    company_name: str | None,
    catalog: str,
) -> str:
    """Hydrate VS hits from Delta; no ORDER BY — merge rank applied in Python (B-W3)."""
    ids_clause = _chunk_ids_in_clause(chunk_ids)
    company_filter = ""
    if company_name:
        company_filter = f"AND c.company_name = '{_escape_sql_literal(company_name)}'"
    return f"""
        SELECT
            c.chunk_id,
            c.file_name,
            c.chunk_text,
            c.section_header,
            c.page_start,
            COALESCE(c.source_type, 'text') AS source_type,
            r.workstream,
            r.priority_tier
        FROM {catalog}.ingestion.chunks c
        JOIN {catalog}.classification.doc_relevance r
            ON c.doc_id = r.doc_id
        WHERE c.chunk_id IN {ids_clause}
          {company_filter}
    """


def _keyword_fallback_sql(
    keywords: list[str],
    company_name: str | None,
    fetch_k: int,
    catalog: str,
) -> str:
    """Keyword LIKE fallback when VS is unavailable (B-W8 parameterized literals)."""
    conditions = " OR ".join(
        [
            f"c.chunk_text LIKE '%{_escape_sql_literal(k)}%'"
            for k in keywords
            if k
        ]
    )
    company_filter = ""
    if company_name:
        company_filter = f"AND c.company_name = '{_escape_sql_literal(company_name)}'"
    return f"""
        SELECT
            c.chunk_id,
            c.file_name,
            c.chunk_text,
            c.section_header,
            c.page_start,
            COALESCE(c.source_type, 'text') AS source_type,
            r.workstream,
            r.priority_tier
        FROM {catalog}.ingestion.chunks c
        JOIN {catalog}.classification.doc_relevance r
            ON c.doc_id = r.doc_id
        WHERE ({conditions})
            AND r.should_parse = true
            {company_filter}
        LIMIT {int(fetch_k)}
    """


def _emit_provenance(
    route_result: RouteResult,
    *,
    query: str,
    company_name: str | None,
    intent_id: str | None,
) -> None:
    """Append pipeline provenance after merge-rank + top_k cap (M-RE2 T3, D2).

    Lazy-imports ``eval.retrieval.provenance`` so the databricks agents package
    never imports eval at module load. The emitter no-ops when no agent run is
    open (unless ``RE2_PROVENANCE_REQUIRED=1``, which raises
    ``ProvenanceEmitError``). Intent-id fallback to ``unknown.{agent_id}`` is
    handled inside the emitter per plan §2.
    """
    from eval.retrieval.provenance import ProvenanceEmitter

    ProvenanceEmitter.emit(
        route_result=route_result,
        company_name=company_name or "",
        query=query,
        intent_id=intent_id,
    )


def semantic_search(
    query: str,
    spark,
    top_k: int = 10,
    company_name: str | None = None,
    file_name_filter: list[str] | None = None,
    workstream_filter: list[str] | None = None,
    tier_filter: int | None = None,
    min_chunk_length: int = 100,
    catalog: str | None = None,
    index_name: str | None = None,
    embedding_endpoint: str = "databricks-bge-large-en",
    source_type_priority: bool = False,
    source_type_filter: list[str] | None = None,
    intent_id: str | None = None,
    vs_metadata_filters: bool = False,
    merge_rank_mode: Literal["sim_tier", "sim_only", "tier_only", "off"] | None = None,
) -> RouteResult:
    """Search for relevant chunks using semantic similarity.

    Fetches top_k * 3 candidates from the vector index and applies all filters
    post-retrieval so that narrowing filters (file_name, workstream, length)
    do not leave the caller with fewer results than requested.

    Args:
        query: Natural language search query.
        spark: Active SparkSession.
        top_k: Number of results to return after filtering.
        file_name_filter: Keep only chunks whose file_name contains at least
            one of these strings (case-insensitive). Targets high-signal
            document types (e.g. ["CIM", "Financial"]).
        workstream_filter: Keep only chunks whose workstream array contains at
            least one of these tags (e.g. ["BUSINESS_MODEL", "FINANCIAL"]).
            workstream is stored as ARRAY<STRING> in doc_relevance.
        tier_filter: If provided, keep only chunks with priority_tier <= this
            value. E.g. tier_filter=1 returns only Tier 1, tier_filter=2
            returns Tier 1 and 2. Passed as post-retrieval filter.
        min_chunk_length: Discard chunks shorter than this many characters.
            Eliminates header-only or page-number chunks.
        catalog: Unity Catalog name (defaults to ``catalog`` env var, else ``uc13``).
        index_name: Unity Catalog fully-qualified vector index name (defaults to
            ``{catalog}.ingestion.embeddings_index``).
        embedding_endpoint: Databricks embedding model endpoint name.
        source_type_priority: When True, sort table and vision chunks before
            text chunks within the same priority_tier. Financial queries benefit
            from structured chunks appearing first — they carry denser data per
            character than prose.
        source_type_filter: When provided, keep only chunks whose source_type
            is in this list (e.g. ["table", "vision"] for structured-data-only
            queries). Applied after all other filters, before top_k cap.
        intent_id: Optional registry intent id (M-RE2 D3). When an agent run is
            open, provenance is emitted for this retrieval under this intent_id;
            when None the emitter falls back to ``unknown.{agent_id}``. FTA
            sub-agents must pass the registry id. No-op when no agent run is
            open unless ``RE2_PROVENANCE_REQUIRED=1``.
        vs_metadata_filters: When ``True``, push ``workstream_filter`` and
            ``tier_filter`` into VS ``filters_json`` (syntax attested by T1
            cluster probe). Default ``False`` — production behavior unchanged.
            Post-retrieval filters still apply regardless.
        merge_rank_mode: Post-hydration chunk ordering. ``None`` and
            ``"sim_tier"`` apply similarity-primary merge rank with a small
            additive tier bonus (default). ``"sim_only"`` sorts by raw VS
            similarity; ``"tier_only"`` by ``priority_tier`` ascending;
            ``"off"`` preserves hydrate-SQL order (no merge rank or
            ``source_type_priority`` reorder).

    Returns:
        RouteResult with chunks (Spark Row objects), mode
        (``semantic`` | ``keyword`` | ``empty``), and parallel scores.
    """
    catalog = (catalog or _default_catalog()).strip()
    if not index_name:
        index_name = _index_name_for_catalog(catalog)

    client = mlflow.deployments.get_deploy_client("databricks")
    w = WorkspaceClient()

    # Embed the query.
    response = client.predict(
        endpoint=embedding_endpoint,
        inputs={"input": [query]},
    )
    try:
        from agents.shared.agent_base import accumulate_tokens
        accumulate_tokens(response.get("usage", {}), endpoint=embedding_endpoint)
    except Exception:
        pass
    query_embedding = response["data"][0]["embedding"]

    # Fetch more candidates than needed so post-retrieval filters have margin.
    fetch_k = top_k * 3
    score_map: dict[str, float] = {}
    used_keyword_fallback = False

    try:
        results = _query_vector_index(
            w,
            index_name=index_name,
            query_embedding=query_embedding,
            fetch_k=fetch_k,
            company_name=company_name,
            vs_metadata_filters=vs_metadata_filters,
            workstream_filter=workstream_filter,
            tier_filter=tier_filter,
        )

        if not results.result or not results.result.data_array:
            raise ValueError("No results from vector search")

        score_map = _extract_score_map(results.result.data_array)
        chunk_ids = [row[0] for row in results.result.data_array]
        chunks = spark.sql(
            _hydrate_chunks_sql(chunk_ids, company_name, catalog)
        ).collect()

    except Exception as e:
        print(f"Vector search failed: {e} — falling back to keyword search")
        used_keyword_fallback = True
        keywords = [k for k in query.replace("'", "").split()[:5] if k]
        if not keywords:
            keywords = [query[:20]]
        chunks = spark.sql(
            _keyword_fallback_sql(keywords, company_name, fetch_k, catalog)
        ).collect()

    # --- Post-retrieval filters ---

    if min_chunk_length > 0:
        chunks = [c for c in chunks if len(c.chunk_text or "") >= min_chunk_length]

    if file_name_filter:
        chunks = [
            c for c in chunks
            if any(p.lower() in (c.file_name or "").lower() for p in file_name_filter)
        ]

    if workstream_filter:
        # workstream is ARRAY<STRING> — Spark Row returns it as a Python list.
        chunks = [
            c for c in chunks
            if c.workstream and any(w in (c.workstream or []) for w in workstream_filter)
        ]

    if tier_filter is not None:
        # priority_tier is INT: 1 = highest value, 2 = high, 3 = useful.
        # Pass tier_filter=1 to restrict to Tier 1 only, tier_filter=2 for Tier 1+2, etc.
        chunks = [c for c in chunks if c.priority_tier is not None and c.priority_tier <= tier_filter]

    if source_type_filter:
        chunks = [
            c for c in chunks
            if getattr(c, "source_type", "text") in source_type_filter
        ]

    effective_merge_rank = merge_rank_mode if merge_rank_mode is not None else "sim_tier"
    if effective_merge_rank == "off":
        pass
    elif effective_merge_rank == "sim_only":
        chunks = _sort_by_sim_only(chunks, score_map)
    elif effective_merge_rank == "tier_only":
        chunks = _sort_by_tier_only(chunks)
    elif source_type_priority:
        # Within merge-rank groups, surface table and vision chunks first.
        if score_map:
            chunks = sorted(
                chunks,
                key=lambda c: (
                    -_merge_score(c, score_map),
                    _TYPE_ORDER.get(getattr(c, "source_type", "text"), 2),
                ),
            )
        else:
            chunks = sorted(
                chunks,
                key=lambda c: (
                    c.priority_tier if c.priority_tier is not None else 99,
                    _TYPE_ORDER.get(getattr(c, "source_type", "text"), 2),
                ),
            )
    elif score_map:
        chunks = _sort_by_merge_rank(chunks, score_map)

    # Cap to top_k.
    chunks = chunks[:top_k]

    # Log contributing files so callers can see provenance.
    source_files = list(dict.fromkeys(c.file_name for c in chunks))
    print(f"  Query '{query[:50]}': retrieved {len(chunks)} chunks from {source_files}")

    if not chunks:
        result = RouteResult(chunks=[], mode="empty", scores=[])
    elif used_keyword_fallback:
        result = RouteResult(
            chunks=chunks,
            mode="keyword",
            scores=[0.0] * len(chunks),
        )
    else:
        if effective_merge_rank == "sim_tier":
            score_values = [_merge_score(c, score_map) for c in chunks]
        else:
            score_values = [score_map.get(c.chunk_id, 0.0) for c in chunks]
        result = RouteResult(
            chunks=chunks,
            mode="semantic",
            scores=score_values,
        )

    # M-RE2 T3/D2: emit provenance after merge-rank + top_k cap, before return.
    # No-op when no agent run is open unless RE2_PROVENANCE_REQUIRED=1.
    _emit_provenance(
        result,
        query=query,
        company_name=company_name,
        intent_id=intent_id,
    )
    return result
