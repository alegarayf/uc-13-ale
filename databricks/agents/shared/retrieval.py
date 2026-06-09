"""
Semantic search helper for UC13 Phase 2/3 agents.

Wraps Databricks Vector Search + fallback keyword search.
All post-retrieval filters (file_name, workstream, chunk length) are applied
after fetching top_k * 3 candidates so filter losses don't starve results.
"""

from __future__ import annotations

import json

from databricks.sdk import WorkspaceClient
import mlflow.deployments


def semantic_search(
    query: str,
    spark,
    top_k: int = 10,
    company_name: str | None = None,
    file_name_filter: list[str] | None = None,
    workstream_filter: list[str] | None = None,
    tier_filter: int | None = None,
    min_chunk_length: int = 100,
    index_name: str = "uc13.ingestion.embeddings_index",
    embedding_endpoint: str = "databricks-bge-large-en",
) -> list:
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
        index_name: Unity Catalog fully-qualified vector index name.
        embedding_endpoint: Databricks embedding model endpoint name.

    Returns:
        List of Spark Row objects with fields:
        chunk_id, file_name, chunk_text, section_header, page_start,
        workstream, priority_tier.
    """
    client = mlflow.deployments.get_deploy_client("databricks")
    w = WorkspaceClient()

    # Embed the query.
    response = client.predict(
        endpoint=embedding_endpoint,
        inputs={"input": [query]},
    )
    query_embedding = response["data"][0]["embedding"]

    # Fetch more candidates than needed so post-retrieval filters have margin.
    fetch_k = top_k * 3

    try:
        results = w.vector_search_indexes.query_index(
            index_name=index_name,
            columns=["chunk_id", "doc_id", "file_name"],
            query_vector=query_embedding,
            num_results=fetch_k,
        )

        if not results.result or not results.result.data_array:
            raise ValueError("No results from vector search")

        chunk_ids = [row[0] for row in results.result.data_array]
        ids_str = "', '".join(chunk_ids)

        company_filter = f"AND c.company_name = '{company_name}'" if company_name else ""
        chunks = spark.sql(f"""
            SELECT
                c.chunk_id,
                c.file_name,
                c.chunk_text,
                c.section_header,
                c.page_start,
                r.workstream,
                r.priority_tier
            FROM uc13.ingestion.chunks c
            JOIN uc13.classification.doc_relevance r
                ON c.file_name = r.filename
               AND c.company_name = r.company_name
            WHERE c.chunk_id IN ('{ids_str}')
              {company_filter}
            ORDER BY r.priority_tier ASC NULLS LAST
        """).collect()

    except Exception as e:
        print(f"Vector search failed: {e} — falling back to keyword search")
        keywords = query.replace("'", "").split()[:5]
        conditions = " OR ".join([f"c.chunk_text LIKE '%{k}%'" for k in keywords])
        company_filter = f"AND c.company_name = '{company_name}'" if company_name else ""
        chunks = spark.sql(f"""
            SELECT
                c.chunk_id,
                c.file_name,
                c.chunk_text,
                c.section_header,
                c.page_start,
                r.workstream,
                r.priority_tier
            FROM uc13.ingestion.chunks c
            JOIN uc13.classification.doc_relevance r
                ON c.file_name = r.filename
               AND c.company_name = r.company_name
            WHERE ({conditions})
                AND r.should_parse = true
                {company_filter}
            ORDER BY r.priority_tier ASC NULLS LAST
            LIMIT {fetch_k}
        """).collect()

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

    # Cap to top_k.
    chunks = chunks[:top_k]

    # Log contributing files so callers can see provenance.
    source_files = list(dict.fromkeys(c.file_name for c in chunks))
    print(f"  Query '{query[:50]}': retrieved {len(chunks)} chunks from {source_files}")

    return chunks
