"""Per-document ingestion worker (M1 DocWorker — claim, clean, parse, write chunks)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import ingestion_parser as ip
from parse_manifest import ManifestItem
from pyspark.sql import Row, SparkSession
from pyspark.sql.types import (
    IntegerType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)
from status_store import PARSER_VERSION, PARSING, ZERO_CHUNKS, StatusStore

_CLASSIFICATION_NEW = "NEW"
EMPTY_EXTRACTION = "EMPTY_EXTRACTION"
ALL_CHUNKS_FILTERED = "ALL_CHUNKS_FILTERED"


def _escape_sql_literal(value: str) -> str:
    return value.replace("'", "''")


class DocWorker:
    """Per-doc unit of work: claim → clean → parse → write chunks (embed/complete in T3+)."""

    def __init__(
        self,
        spark: SparkSession,
        catalog: str,
        schema: str,
        company: str,
        run_id: str,
        vision_endpoint: Optional[str] = None,
    ) -> None:
        self.spark = spark
        self.catalog = catalog
        self.schema = schema
        self.company = company
        self.run_id = run_id
        self.vision_endpoint = vision_endpoint
        self._status_store = StatusStore(spark, catalog, schema)

    @property
    def _table_chunks(self) -> str:
        return f"{self.catalog}.{self.schema}.chunks"

    @property
    def _table_embeddings(self) -> str:
        return f"{self.catalog}.{self.schema}.embeddings"

    def process(self, item: ManifestItem) -> None:
        now = datetime.now(timezone.utc)

        self._status_store.upsert(
            company_name=self.company,
            doc_id=item.doc_id,
            file_name=item.file_name,
            relative_path=item.relative_path,
            status=PARSING,
            source_mtime=item.source_mtime,
            source_size=item.source_size,
            run_id=self.run_id,
            parser_version=PARSER_VERSION,
            updated_at=now,
            coverage_injected=item.coverage_injected,
        )

        if item.classification != _CLASSIFICATION_NEW:
            self._delete_stale_corpus(item.doc_id)

        chunks = ip.parse_file(
            item.full_path,
            item.doc_id,
            self.spark,
            vision_endpoint=self.vision_endpoint,
        )

        if not chunks:
            zero_reason = (
                ALL_CHUNKS_FILTERED
                if item.source_size > 0
                else EMPTY_EXTRACTION
            )
            self._status_store.upsert(
                company_name=self.company,
                doc_id=item.doc_id,
                file_name=item.file_name,
                relative_path=item.relative_path,
                status=ZERO_CHUNKS,
                source_mtime=item.source_mtime,
                source_size=item.source_size,
                run_id=self.run_id,
                parser_version=PARSER_VERSION,
                updated_at=datetime.now(timezone.utc),
                coverage_injected=item.coverage_injected,
                error=zero_reason,
            )
            return

        self._append_chunks(chunks, now)

    def _delete_stale_corpus(self, doc_id: str) -> None:
        """Delete prior chunks/embeddings for this doc_id (loud — no swallow)."""
        escaped_company = _escape_sql_literal(self.company)
        escaped_doc_id = _escape_sql_literal(doc_id)
        self.spark.sql(
            f"DELETE FROM {self._table_chunks} "
            f"WHERE company_name = '{escaped_company}' AND doc_id = '{escaped_doc_id}'"
        )
        self.spark.sql(
            f"DELETE FROM {self._table_embeddings} "
            f"WHERE company_name = '{escaped_company}' AND doc_id = '{escaped_doc_id}'"
        )

    def _append_chunks(self, chunks: list[ip.Chunk], created_at: datetime) -> None:
        chunk_schema = StructType(
            [
                StructField("company_name", StringType(), False),
                StructField("chunk_id", StringType(), False),
                StructField("doc_id", StringType(), False),
                StructField("file_name", StringType(), False),
                StructField("file_type", StringType(), False),
                StructField("relative_path", StringType(), False),
                StructField("chunk_index", IntegerType(), False),
                StructField("chunk_text", StringType(), False),
                StructField("section_header", StringType(), True),
                StructField("page_start", IntegerType(), True),
                StructField("page_end", IntegerType(), True),
                StructField("tab", StringType(), True),
                StructField("source_type", StringType(), True),
                StructField("char_count", IntegerType(), False),
                StructField("created_at", TimestampType(), False),
            ]
        )
        rows = [
            Row(
                company_name=self.company,
                chunk_id=c.chunk_id,
                doc_id=c.doc_id,
                file_name=c.file_name,
                file_type=c.file_type,
                relative_path=c.relative_path,
                chunk_index=int(c.chunk_index),
                chunk_text=c.chunk_text,
                section_header=c.section_header,
                page_start=int(c.page_start) if c.page_start is not None else None,
                page_end=int(c.page_end) if c.page_end is not None else None,
                tab=c.tab,
                source_type=c.source_type,
                char_count=int(c.char_count),
                created_at=created_at,
            )
            for c in chunks
        ]
        frame = self.spark.createDataFrame(rows, schema=chunk_schema)
        frame.write.mode("append").option("mergeSchema", "true").saveAsTable(
            self._table_chunks
        )
