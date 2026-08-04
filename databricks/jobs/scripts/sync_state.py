"""sync_state table DDL — M0 create-only; M2 extends with watermark read/write."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pyspark.sql.types import StringType, StructField, StructType, TimestampType

_SYNC_STATE_SCHEMA = StructType(
    [
        StructField("catalog_scope", StringType(), False),
        StructField("last_successful_sync", TimestampType(), True),
        StructField("run_id", StringType(), True),
    ]
)


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


def read_watermark(spark, catalog: str, schema: str) -> tuple[datetime | None, str | None]:
    """Read the singleton sync_state row for *catalog* (cold-start → ``(None, None)``)."""
    table = f"{catalog}.{schema}.sync_state"
    escaped_catalog = catalog.replace("'", "''")
    rows = spark.sql(f"""
        SELECT last_successful_sync, run_id
        FROM {table}
        WHERE catalog_scope = '{escaped_catalog}'
    """).collect()
    if not rows:
        return (None, None)
    row = rows[0]
    return (row.last_successful_sync, row.run_id)


def advance_watermark(
    spark,
    catalog: str,
    schema: str,
    timestamp: datetime,
    run_id: str,
) -> None:
    """MERGE-upsert the catalog-scoped watermark row (sole writer of sync_state)."""
    table = f"{catalog}.{schema}.sync_state"
    row: dict[str, Any] = {
        "catalog_scope": catalog,
        "last_successful_sync": timestamp,
        "run_id": run_id,
    }
    frame = spark.createDataFrame([row], schema=_SYNC_STATE_SCHEMA)
    temp_view = f"incoming_sync_state_{uuid.uuid4().hex}"
    frame.createOrReplaceTempView(temp_view)
    spark.sql(f"""
        MERGE INTO {table} AS target
        USING {temp_view} AS source
        ON target.catalog_scope = source.catalog_scope
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """)
