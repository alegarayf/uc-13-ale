"""Per-document ingestion worker (M1 DocWorker — claim through COMPLETE)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import ingestion_parser as ip
from parse_manifest import ManifestItem
from pyspark.sql import Row, SparkSession
from pyspark.sql.types import (
    ArrayType,
    FloatType,
    IntegerType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)
from status_store import (
    COMPLETE,
    EMBEDDING,
    FAILED,
    PARSER_VERSION,
    PARSING,
    ZERO_CHUNKS,
    StatusStore,
)

_CLASSIFICATION_NEW = "NEW"
EMPTY_EXTRACTION = "EMPTY_EXTRACTION"
ALL_CHUNKS_FILTERED = "ALL_CHUNKS_FILTERED"
PARSE_EXCEPTION = "PARSE_EXCEPTION"
FILE_NOT_FOUND = "FILE_NOT_FOUND"
UNSUPPORTED_EXTENSION = "UNSUPPORTED_EXTENSION"
EMBED_EXCEPTION = "EMBED_EXCEPTION"
VISION_ENDPOINT_ERROR = "VISION_ENDPOINT_ERROR"

_ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".xlsm", ".docx", ".doc", ".csv"}


@dataclass
class RunSummary:
    """Per-run aggregates returned by DocWorker.run() (not ParseManifest.ManifestSummary)."""

    chunk_counts_by_source_type: dict[str, int] = field(default_factory=dict)
    vision_pages_attempted: int = 0
    vision_pages_skipped: int = 0
    vision_pages_failed: int = 0


def format_run_summary(summary: RunSummary) -> list[str]:
    """Pure formatter for RunSummary — printed once from main() after the per-doc loop."""
    lines = [
        "",
        "=== UC13 Phase 2b — DocWorker Run Summary ===",
        "",
    ]
    if summary.chunk_counts_by_source_type:
        lines.append("Chunks by source_type:")
        for source_type in sorted(summary.chunk_counts_by_source_type):
            count = summary.chunk_counts_by_source_type[source_type]
            lines.append(f"  {source_type}: {count}")
    else:
        lines.append("Chunks by source_type: (none)")
    lines.extend(
        [
            "",
            f"Vision pages attempted: {summary.vision_pages_attempted}",
            f"Vision pages skipped:   {summary.vision_pages_skipped}",
            f"Vision pages failed:    {summary.vision_pages_failed}",
        ]
    )
    return lines


def _escape_sql_literal(value: str) -> str:
    return value.replace("'", "''")


def _count_source_types(chunks: list[ip.Chunk]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for chunk in chunks:
        key = chunk.source_type or "text"
        counts[key] = counts.get(key, 0) + 1
    return counts


class DocWorker:
    """Per-doc unit of work: claim → clean → parse → write chunks → embed → COMPLETE."""

    def __init__(
        self,
        spark: SparkSession,
        catalog: str,
        schema: str,
        company: str,
        run_id: str,
        vision_endpoint: Optional[str] = None,
        embedding_endpoint: str = "databricks-bge-large-en",
    ) -> None:
        self.spark = spark
        self.catalog = catalog
        self.schema = schema
        self.company = company
        self.run_id = run_id
        self.vision_endpoint = vision_endpoint
        self.embedding_endpoint = embedding_endpoint
        self._status_store = StatusStore(spark, catalog, schema)
        self._last_chunk_source_counts: dict[str, int] | None = None

    @property
    def _table_chunks(self) -> str:
        return f"{self.catalog}.{self.schema}.chunks"

    @property
    def _table_embeddings(self) -> str:
        return f"{self.catalog}.{self.schema}.embeddings"

    @property
    def _table_relevance(self) -> str:
        return f"{self.catalog}.classification.doc_relevance"

    def run(self, work_list: list[ManifestItem]) -> RunSummary:
        """Process each manifest item; per-doc failures continue to the next doc."""
        summary = RunSummary()
        for item in work_list:
            self.process(item)
            if self._last_chunk_source_counts:
                for source_type, count in self._last_chunk_source_counts.items():
                    summary.chunk_counts_by_source_type[source_type] = (
                        summary.chunk_counts_by_source_type.get(source_type, 0)
                        + count
                    )
        return summary

    def process(self, item: ManifestItem) -> None:
        self._last_chunk_source_counts = None
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

        try:
            if item.classification != _CLASSIFICATION_NEW:
                self._delete_stale_corpus(item.doc_id)

            ext = Path(item.file_name).suffix.lower()
            if ext not in _ALLOWED_EXTENSIONS:
                self._upsert_failed(
                    item,
                    UNSUPPORTED_EXTENSION,
                    f"unsupported extension: {ext}",
                )
                return

            try:
                content_hash = self._compute_content_hash(item.full_path)
            except FileNotFoundError as exc:
                self._upsert_failed(item, FILE_NOT_FOUND, str(exc))
                return
            except OSError as exc:
                reason = (
                    FILE_NOT_FOUND
                    if getattr(exc, "errno", None) == 2
                    else PARSE_EXCEPTION
                )
                self._upsert_failed(item, reason, str(exc))
                return

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

            self._last_chunk_source_counts = _count_source_types(chunks)

            try:
                self._append_chunks(chunks, now)
                self._embed_and_complete(chunks, item, content_hash, now)
            except Exception as exc:
                self._upsert_failed(item, EMBED_EXCEPTION, str(exc))

        except Exception as exc:
            self._upsert_failed(item, PARSE_EXCEPTION, str(exc))

    def _upsert_failed(
        self,
        item: ManifestItem,
        reason_class: str,
        detail: str,
    ) -> None:
        self._status_store.upsert(
            company_name=self.company,
            doc_id=item.doc_id,
            file_name=item.file_name,
            relative_path=item.relative_path,
            status=FAILED,
            source_mtime=item.source_mtime,
            source_size=item.source_size,
            run_id=self.run_id,
            parser_version=PARSER_VERSION,
            updated_at=datetime.now(timezone.utc),
            coverage_injected=item.coverage_injected,
            error=f"{reason_class}: {detail}",
        )

    def _compute_content_hash(self, file_path: str) -> str:
        """Return md5 hex digest of file bytes (one explicit read per doc)."""
        with open(file_path, "rb") as fh:
            return hashlib.md5(fh.read()).hexdigest()

    def _lookup_relevance(self, file_name: str) -> tuple[Optional[list[str]], Optional[int]]:
        escaped_company = _escape_sql_literal(self.company)
        escaped_file_name = _escape_sql_literal(file_name)
        rows = self.spark.sql(
            f"SELECT workstream, priority_tier "
            f"FROM {self._table_relevance} "
            f"WHERE company_name = '{escaped_company}' "
            f"AND filename = '{escaped_file_name}' "
            f"LIMIT 1"
        ).collect()
        if not rows:
            return None, None
        row = rows[0]
        return list(row.workstream or []), row.priority_tier

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

    def _embed_and_complete(
        self,
        chunks: list[ip.Chunk],
        item: ManifestItem,
        content_hash: str,
        created_at: datetime,
    ) -> None:
        self._status_store.upsert(
            company_name=self.company,
            doc_id=item.doc_id,
            file_name=item.file_name,
            relative_path=item.relative_path,
            status=EMBEDDING,
            source_mtime=item.source_mtime,
            source_size=item.source_size,
            run_id=self.run_id,
            parser_version=PARSER_VERSION,
            updated_at=datetime.now(timezone.utc),
            coverage_injected=item.coverage_injected,
        )

        import mlflow.deployments

        client = mlflow.deployments.get_deploy_client("databricks")
        texts = [c.chunk_text for c in chunks]
        embeddings = ip.get_embeddings_batch(texts, client, self.embedding_endpoint)

        workstream, priority_tier = self._lookup_relevance(item.file_name)

        emb_schema = StructType(
            [
                StructField("company_name", StringType(), False),
                StructField("chunk_id", StringType(), False),
                StructField("doc_id", StringType(), False),
                StructField("file_name", StringType(), False),
                StructField("source_type", StringType(), True),
                StructField("workstream", ArrayType(StringType()), True),
                StructField("priority_tier", IntegerType(), True),
                StructField("embedding", ArrayType(FloatType()), False),
                StructField("created_at", TimestampType(), False),
            ]
        )
        emb_rows = [
            Row(
                company_name=self.company,
                chunk_id=chunks[i].chunk_id,
                doc_id=chunks[i].doc_id,
                file_name=chunks[i].file_name,
                source_type=chunks[i].source_type,
                workstream=workstream,
                priority_tier=priority_tier,
                embedding=[float(x) for x in embeddings[i]],
                created_at=created_at,
            )
            for i in range(len(chunks))
        ]
        emb_frame = self.spark.createDataFrame(emb_rows, schema=emb_schema)
        emb_frame.write.mode("append").option("mergeSchema", "true").saveAsTable(
            self._table_embeddings
        )

        self._status_store.upsert(
            company_name=self.company,
            doc_id=item.doc_id,
            file_name=item.file_name,
            relative_path=item.relative_path,
            status=COMPLETE,
            source_mtime=item.source_mtime,
            source_size=item.source_size,
            run_id=self.run_id,
            parser_version=PARSER_VERSION,
            updated_at=datetime.now(timezone.utc),
            coverage_injected=item.coverage_injected,
            chunk_count=len(chunks),
            content_hash=content_hash,
        )
