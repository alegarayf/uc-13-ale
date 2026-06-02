"""
00_setup_vector_search.py — UC13 one-time environment setup.

Run once per Databricks workspace (or when tearing down and rebuilding the index).
All operations are idempotent: existing endpoints and indexes are left untouched.

Sequence:
  1. Create Unity Catalog schemas (classification, ingestion) if absent.
  2. Create the Vector Search endpoint if absent.
  3. Create uc13.ingestion.embeddings table with CDF enabled (if absent).
  4. Create the Delta Sync vector index over embeddings (if absent).

Dependencies:
  - Databricks Serverless cluster with SDK and Vector Search enabled.
  - Secrets scope "uc13" with key "vs_endpoint_name" (optional; defaults to
    "uc13-vector-search").
  - Unity Catalog catalog "uc13" pre-created by the workspace admin.
"""

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Secrets / params helpers
# ---------------------------------------------------------------------------

def _get_dbutils():
    """Return the Databricks dbutils object from any execution context.

    Works whether the code runs directly in a notebook cell or is called from
    an imported module (where dbutils is not a direct global but is reachable
    via the IPython user namespace injected by Databricks).
    """
    try:
        return dbutils  # noqa: F821
    except NameError:
        pass
    try:
        import IPython
        user_ns = IPython.get_ipython().user_ns
        if "dbutils" in user_ns:
            return user_ns["dbutils"]
    except Exception:
        pass
    return None


def _load_dotenv_if_local():
    if _get_dbutils() is None:
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

_load_dotenv_if_local()


def get_secret(key: str) -> str:
    _dbutils = _get_dbutils()
    if _dbutils is not None:
        try:
            return _dbutils.secrets.get("uc13", key)
        except Exception:
            pass
    value = os.environ.get(key)
    if value is None:
        raise RuntimeError(
            f"Secret '{key}' not found. "
            "On Databricks: add it to the 'uc13' secrets scope. "
            "Locally: add it to your .env file or export it as an env var."
        )
    return value


def get_param(key: str, default: str = None) -> str:
    _dbutils = _get_dbutils()
    if _dbutils is not None:
        try:
            value = _dbutils.widgets.get(key)
            if value:
                return value
        except Exception:
            pass
    value = os.environ.get(key, default)
    if value is None:
        raise RuntimeError(
            f"Parameter '{key}' not found. "
            "On Databricks: add it as a job task parameter. "
            "Locally: add it to your .env file or export it as an env var."
        )
    return value


# ---------------------------------------------------------------------------
# Repo root resolver
# ---------------------------------------------------------------------------

def get_current_path():
    try:
        notebook_path = (
            dbutils.notebook.entry_point  # noqa: F821
            .getDbutils()
            .notebook()
            .getContext()
            .notebookPath()
            .get()
        )
        return Path("/Workspace") / notebook_path.lstrip("/")
    except Exception:
        return Path(os.getcwd())


def find_repo_root(marker="agents"):
    current_path = get_current_path()
    if current_path.is_file():
        current_path = current_path.parent
    for path in [current_path, *current_path.parents]:
        if (path / marker).exists():
            return str(path)
    raise RuntimeError(f"Could not find a parent directory containing '{marker}'")


# ---------------------------------------------------------------------------
# Setup logic
# ---------------------------------------------------------------------------

def setup_schemas(spark):
    """Create UC schemas if they don't already exist."""
    spark.sql("CREATE SCHEMA IF NOT EXISTS uc13.ingestion")
    spark.sql("CREATE SCHEMA IF NOT EXISTS uc13.classification")
    print("Schemas: uc13.ingestion and uc13.classification — OK")


def setup_raw_files_volume(spark):
    """Create the managed UC Volume that stores raw ingested files (idempotent)."""
    spark.sql("CREATE VOLUME IF NOT EXISTS uc13.ingestion.raw_files")
    print("Volume: uc13.ingestion.raw_files — OK")


def setup_embeddings_table(spark):
    """Create embeddings table with CDF enabled (idempotent)."""
    spark.sql("""
        CREATE TABLE IF NOT EXISTS uc13.ingestion.embeddings (
            chunk_id      STRING NOT NULL,
            doc_id        STRING,
            file_name     STRING,
            workstream    ARRAY<STRING>,
            priority_tier INT,
            embedding     ARRAY<FLOAT>,
            created_at    TIMESTAMP
        ) USING DELTA
        TBLPROPERTIES (
            'delta.enableChangeDataFeed'          = 'true',
            'delta.deletedFileRetentionDuration'  = 'interval 30 days'
        )
    """)
    # Ensure CDF is on even if table already existed without it.
    spark.sql("""
        ALTER TABLE uc13.ingestion.embeddings
        SET TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true')
    """)
    print("Table: uc13.ingestion.embeddings — OK (CDF enabled)")


def setup_vector_search_endpoint(endpoint_name: str):
    """Create VS endpoint if it does not exist (idempotent)."""
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.vectorsearch import EndpointType

    w = WorkspaceClient()
    existing = [e.name for e in w.vector_search_endpoints.list_endpoints()]
    if endpoint_name in existing:
        print(f"Endpoint '{endpoint_name}' already exists — skipping")
        return

    w.vector_search_endpoints.create_endpoint_and_wait(
        name=endpoint_name,
        endpoint_type=EndpointType.STANDARD,
    )
    print(f"Endpoint '{endpoint_name}' created")


def setup_vector_search_index(endpoint_name: str, index_name: str):
    """Create Delta Sync vector index if it does not exist (idempotent)."""
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.vectorsearch import (
        VectorIndexType,
        DeltaSyncVectorIndexSpecRequest,
        EmbeddingVectorColumn,
        PipelineType,
    )

    w = WorkspaceClient()
    try:
        info = w.vector_search_indexes.get_index(index_name=index_name)
        print(f"Index '{index_name}' already exists (ready={info.status.ready}) — skipping")
        return
    except Exception:
        pass  # index does not exist; create it

    index = w.vector_search_indexes.create_index(
        name=index_name,
        endpoint_name=endpoint_name,
        primary_key="chunk_id",
        index_type=VectorIndexType.DELTA_SYNC,
        delta_sync_index_spec=DeltaSyncVectorIndexSpecRequest(
            source_table="uc13.ingestion.embeddings",
            pipeline_type=PipelineType.TRIGGERED,
            embedding_vector_columns=[
                EmbeddingVectorColumn(name="embedding", embedding_dimension=1024)
            ],
            columns_to_sync=[
                "chunk_id", "doc_id", "file_name",
                "workstream", "priority_tier",
            ],
        ),
    )
    print(f"Index '{index_name}' created — status: {index.status}")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    repo_root = find_repo_root()
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    print("repo_root:", repo_root)

    catalog  = get_param("catalog",  default="uc13")
    vs_endpoint_name = get_param("vs_endpoint_name", default="uc13-vector-search")
    index_name = f"{catalog}.ingestion.embeddings_index"

    from pyspark.sql import SparkSession as _SparkSession
    _spark = _SparkSession.getActiveSession()
    if _spark is None:
        raise RuntimeError("No active Spark session. This script must run on a Databricks cluster.")

    print("\n=== UC13 — Setup Vector Search ===")
    setup_schemas(_spark)
    setup_raw_files_volume(_spark)
    setup_embeddings_table(_spark)
    setup_vector_search_endpoint(vs_endpoint_name)
    setup_vector_search_index(vs_endpoint_name, index_name)
    print("\nSetup complete.")


if __name__ == "__main__":
    main()
