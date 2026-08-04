"""doc_status table DDL, status vocabulary, and StatusStore hub (M0 create-only reads; M1 writes)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
import uuid

from pyspark.sql import SparkSession
from pyspark.sql.types import (
    BooleanType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

PARSER_VERSION = "v1"

PENDING = "PENDING"
PARSING = "PARSING"
EMBEDDING = "EMBEDDING"
COMPLETE = "COMPLETE"
FAILED = "FAILED"
ZERO_CHUNKS = "ZERO_CHUNKS"

ALLOWED_STATUSES: frozenset[str] = frozenset(
    {PENDING, PARSING, EMBEDDING, COMPLETE, FAILED, ZERO_CHUNKS}
)

_DOC_STATUS_SCHEMA = StructType(
    [
        StructField("company_name", StringType(), False),
        StructField("doc_id", StringType(), False),
        StructField("file_name", StringType(), False),
        StructField("relative_path", StringType(), False),
        StructField("status", StringType(), False),
        StructField("chunk_count", IntegerType(), True),
        StructField("source_mtime", LongType(), False),
        StructField("source_size", LongType(), False),
        StructField("content_hash", StringType(), True),
        StructField("coverage_injected", BooleanType(), False),
        StructField("parser_version", StringType(), False),
        StructField("run_id", StringType(), False),
        StructField("error", StringType(), True),
        StructField("updated_at", TimestampType(), False),
    ]
)


def normalize_status(status: str | None) -> str:
    """Return status if in §16 closed set; otherwise FAILED."""
    if status in ALLOWED_STATUSES:
        return status
    return FAILED


def ensure_doc_status(spark: SparkSession, catalog: str, schema: str) -> None:
    """Create doc_status Delta table if it does not exist (§8.1, idempotent)."""
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
    table = f"{catalog}.{schema}.doc_status"
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {table} (
            company_name       STRING NOT NULL,
            doc_id             STRING NOT NULL,
            file_name          STRING NOT NULL,
            relative_path      STRING NOT NULL,
            status             STRING NOT NULL,
            chunk_count        INT,
            source_mtime       LONG NOT NULL,
            source_size        LONG NOT NULL,
            content_hash       STRING,
            coverage_injected  BOOLEAN NOT NULL DEFAULT FALSE,
            parser_version     STRING NOT NULL,
            run_id             STRING NOT NULL,
            error              STRING,
            updated_at         TIMESTAMP NOT NULL
        ) USING DELTA
    """)


@dataclass(frozen=True)
class StatusRow:
    company_name: str
    doc_id: str
    file_name: str
    relative_path: str
    status: str
    chunk_count: int | None
    source_mtime: int
    source_size: int
    content_hash: str | None
    coverage_injected: bool
    parser_version: str
    run_id: str
    error: str | None
    updated_at: datetime


class StatusStore:
    """Parser-owned doc_status authority. M0: read_status_map only exercised; upsert created for M1."""

    def __init__(self, spark: SparkSession, catalog: str, schema: str) -> None:
        self.spark = spark
        self.catalog = catalog
        self.schema = schema

    @property
    def table(self) -> str:
        return f"{self.catalog}.{self.schema}.doc_status"

    def read_status_map(self, company: str) -> dict[str, StatusRow]:
        """Company-filtered read keyed by doc_id (§8.1; M2 adds catalog-wide methods separately)."""
        escaped = company.replace("'", "''")
        rows = self.spark.sql(f"""
            SELECT
                company_name,
                doc_id,
                file_name,
                relative_path,
                status,
                chunk_count,
                source_mtime,
                source_size,
                content_hash,
                coverage_injected,
                parser_version,
                run_id,
                error,
                updated_at
            FROM {self.table}
            WHERE company_name = '{escaped}'
        """).collect()

        result: dict[str, StatusRow] = {}
        for row in rows:
            result[row.doc_id] = StatusRow(
                company_name=row.company_name,
                doc_id=row.doc_id,
                file_name=row.file_name,
                relative_path=row.relative_path,
                status=normalize_status(row.status),
                chunk_count=row.chunk_count,
                source_mtime=row.source_mtime,
                source_size=row.source_size,
                content_hash=row.content_hash,
                coverage_injected=bool(row.coverage_injected),
                parser_version=row.parser_version,
                run_id=row.run_id,
                error=row.error,
                updated_at=row.updated_at,
            )
        return result

    def upsert(
        self,
        company_name: str,
        doc_id: str,
        file_name: str,
        relative_path: str,
        status: str,
        source_mtime: int,
        source_size: int,
        run_id: str,
        parser_version: str,
        updated_at: datetime,
        coverage_injected: bool = False,
        chunk_count: int | None = None,
        content_hash: str | None = None,
        error: str | None = None,
    ) -> None:
        """Upsert one doc_status row per transition (exercised in M1 DocWorker)."""
        if status not in ALLOWED_STATUSES:
            raise ValueError(
                f"Invalid status {status!r}; must be one of {sorted(ALLOWED_STATUSES)}"
            )

        row: dict[str, Any] = {
            "company_name": company_name,
            "doc_id": doc_id,
            "file_name": file_name,
            "relative_path": relative_path,
            "status": status,
            "chunk_count": chunk_count,
            "source_mtime": source_mtime,
            "source_size": source_size,
            "content_hash": content_hash,
            "coverage_injected": coverage_injected,
            "parser_version": parser_version,
            "run_id": run_id,
            "error": error,
            "updated_at": updated_at,
        }

        frame = self.spark.createDataFrame([row], schema=_DOC_STATUS_SCHEMA)
        temp_view = f"incoming_doc_status_{uuid.uuid4().hex}"
        frame.createOrReplaceTempView(temp_view)

        self.spark.sql(f"""
            MERGE INTO {self.table} AS target
            USING {temp_view} AS source
            ON target.company_name = source.company_name
               AND target.doc_id = source.doc_id
            WHEN MATCHED THEN UPDATE SET *
            WHEN NOT MATCHED THEN INSERT *
        """)
