from databricks.sdk import WorkspaceClient
import mlflow.deployments
import json

def semantic_search(
    query,
    spark,
    top_k=10,
    workstream_filter=None,
    tier_filter=None,
    index_name="uc13.ingestion.embeddings_index",
    embedding_endpoint="databricks-bge-large-en"
):
    """
    Search for relevant chunks using semantic similarity.
    Works regardless of whether a CIM exists or not.
    """
    client = mlflow.deployments.get_deploy_client("databricks")
    w = WorkspaceClient()

    response = client.predict(
        endpoint=embedding_endpoint,
        inputs={"input": [query]}
    )
    query_embedding = response["data"][0]["embedding"]

    filters = {}
    if workstream_filter:
        filters["workstream"] = workstream_filter
    if tier_filter:
        filters["priority_tier"] = tier_filter

    try:
        results = w.vector_search_indexes.query_index(
            index_name=index_name,
            columns=["chunk_id", "doc_id", "file_name"],
            query_vector=query_embedding,
            num_results=top_k,
            filters_json=json.dumps(filters) if filters else None
        )

        if not results.result or not results.result.data_array:
            raise ValueError("No results from vector search")

        chunk_ids = [row[0] for row in results.result.data_array]
        ids_str = "', '".join(chunk_ids)

        chunks = spark.sql(f"""
            SELECT c.chunk_id, c.file_name, c.chunk_text,
                   c.section_header, c.page_start,
                   r.workstream, r.priority_tier
            FROM uc13.ingestion.chunks c
            JOIN uc13.classification.doc_relevance r
                ON c.file_name = r.file_name
            WHERE c.chunk_id IN ('{ids_str}')
            ORDER BY r.priority_tier ASC
        """).collect()

        return chunks

    except Exception as e:
        print(f"Vector search failed: {e} — falling back to keyword search")
        keywords = query.replace("'", "").split()[:5]
        conditions = " OR ".join([f"c.chunk_text LIKE '%{k}%'" for k in keywords])
        chunks = spark.sql(f"""
            SELECT c.chunk_id, c.file_name, c.chunk_text,
                   c.section_header, c.page_start,
                   r.workstream, r.priority_tier
            FROM uc13.ingestion.chunks c
            JOIN uc13.classification.doc_relevance r
                ON c.file_name = r.file_name
            WHERE ({conditions})
            AND r.should_parse = true
            ORDER BY r.priority_tier ASC
            LIMIT {top_k}
        """).collect()
        return chunks