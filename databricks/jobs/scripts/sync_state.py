"""sync_state table DDL — M0 create-only; M2 extends with watermark read/write."""


def ensure_sync_state(spark, catalog: str, schema: str) -> None:
    """Create the sync_state Delta table if it does not exist (§8.4)."""
    table = f"{catalog}.{schema}.sync_state"
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {table} (
            catalog_scope          STRING NOT NULL,
            last_successful_sync   TIMESTAMP,
            run_id                 STRING
        ) USING DELTA
    """)
