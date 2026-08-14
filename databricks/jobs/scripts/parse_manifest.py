"""Read-only ParseManifest: classified work list + cross-tier coverage sub-pass (M0)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from pyspark.sql import SparkSession

from doc_id import make_doc_id
from status_store import (
    COMPLETE,
    EMBEDDING,
    FAILED,
    PARSING,
    PENDING,
    PARSER_VERSION,
    ZERO_CHUNKS,
    StatusRow,
    StatusStore,
)

_ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".xlsm", ".docx", ".doc", ".csv"}

_CLASSIFICATION_NEW = "NEW"
_CLASSIFICATION_STALE = "STALE"
_CLASSIFICATION_RETRY = "RETRY"
_CLASSIFICATION_SKIP = "SKIP"

_WORK_LIST_CLASSIFICATIONS = frozenset(
    {_CLASSIFICATION_NEW, _CLASSIFICATION_STALE, _CLASSIFICATION_RETRY}
)


def build_file_whitelist_filter(whitelist: list[str] | None) -> tuple[str, str]:
    """``(sql_clause, label)`` for the optional ``filename IN (...)`` scoping of
    the ``doc_relevance`` read (CIM-first preview — plan §7 Día 2, Apéndice A.1).

    Empty/``None`` → ``("", "no whitelist")``, i.e. today's full-room behavior
    unchanged. Lives here rather than in ``ingestion_parser`` because the read
    it scopes moved into this module with the M0 manifest; putting it here also
    means the coverage sub-pass (which re-reads ``doc_relevance`` with
    ``tiers=None``) is scoped by the same clause and cannot inject non-CIM docs.
    """
    if not whitelist:
        return "", "no whitelist"
    quoted = ", ".join("'" + fn.replace("'", "''") + "'" for fn in whitelist)
    return f"AND filename IN ({quoted})", f"whitelist ({len(whitelist)} file(s))"


@dataclass(frozen=True)
class ManifestItem:
    doc_id: str
    file_name: str
    relative_path: str
    full_path: str
    source_mtime: int
    source_size: int
    classification: str
    coverage_injected: bool


@dataclass
class ManifestSummary:
    """Structured run summary for T5 harness printing (no stdout in this module)."""

    classification_counts: dict[str, int] = field(
        default_factory=lambda: {
            _CLASSIFICATION_NEW: 0,
            _CLASSIFICATION_STALE: 0,
            _CLASSIFICATION_RETRY: 0,
            _CLASSIFICATION_SKIP: 0,
        }
    )
    coverage_injected_count: int = 0
    zero_coverable_residuals: list[tuple[str, int]] = field(default_factory=list)
    absent_on_volume: list[str] = field(default_factory=list)
    disallowed_extensions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _ApprovedDoc:
    file_name: str
    folder_path: str | None
    workstreams: tuple[str, ...]
    priority_tier: int | None


@dataclass
class _ResolvedDoc:
    approved: _ApprovedDoc
    doc_id: str
    relative_path: str
    full_path: str
    source_mtime: int
    source_size: int
    classification: str
    coverage_injected: bool = False


class ParseManifest:
    """Read-only manifest builder; never writes doc_status."""

    def __init__(
        self,
        spark: SparkSession,
        catalog: str,
        schema: str,
        company: str,
        file_whitelist: list[str] | None = None,
    ) -> None:
        self.spark = spark
        self.catalog = catalog
        self.schema = schema
        self.company = company
        self.file_whitelist = file_whitelist or None
        self.last_summary: ManifestSummary | None = None

    @property
    def _volume_root(self) -> str:
        return f"/Volumes/{self.catalog}/{self.schema}/raw_files/{self.company}"

    @property
    def _relevance_table(self) -> str:
        return f"{self.catalog}.classification.doc_relevance"

    def build(
        self,
        tiers: list[int] | None,
        coverage_per_workstream: int,
        force_all: bool = False,
        force_doc_ids: set[str] | None = None,
    ) -> list[ManifestItem]:
        force_ids = force_doc_ids or set()
        status_map = StatusStore(self.spark, self.catalog, self.schema).read_status_map(
            self.company
        )
        summary = ManifestSummary()
        resolved_by_id: dict[str, _ResolvedDoc] = {}

        main_rows = self._read_doc_relevance(tiers)
        for row in main_rows:
            self._process_approved_row(
                row,
                status_map=status_map,
                force_all=force_all,
                force_ids=force_ids,
                summary=summary,
                resolved_by_id=resolved_by_id,
            )

        if tiers is not None:
            self._run_coverage_subpass(
                coverage_per_workstream=coverage_per_workstream,
                status_map=status_map,
                force_all=force_all,
                force_ids=force_ids,
                summary=summary,
                resolved_by_id=resolved_by_id,
            )

        work_list = [
            self._to_manifest_item(doc)
            for doc in resolved_by_id.values()
            if doc.classification in _WORK_LIST_CLASSIFICATIONS
        ]
        work_list.sort(
            key=lambda item: (
                _priority_sort_key(
                    resolved_by_id[item.doc_id].approved.priority_tier
                ),
                item.file_name,
            )
        )

        summary.coverage_injected_count = sum(
            1 for doc in resolved_by_id.values() if doc.coverage_injected
        )
        self.last_summary = summary
        return work_list

    def _read_doc_relevance(self, tiers: list[int] | None) -> list[_ApprovedDoc]:
        escaped_company = self.company.replace("'", "''")
        tier_sql = ""
        if tiers is not None:
            tier_sql = f"AND priority_tier IN ({', '.join(str(t) for t in tiers)})"
        whitelist_sql, _ = build_file_whitelist_filter(self.file_whitelist)
        try:
            rows = self.spark.sql(f"""
                SELECT
                    filename AS file_name,
                    folder_path,
                    workstream,
                    priority_tier,
                    should_parse
                FROM {self._relevance_table}
                WHERE should_parse = true
                  AND company_name = '{escaped_company}'
                  {tier_sql}
                  {whitelist_sql}
                ORDER BY priority_tier ASC NULLS LAST, filename ASC
            """).collect()
        except Exception as exc:
            raise RuntimeError(
                f"doc_relevance unreadable at {self._relevance_table}: {exc}"
            ) from exc

        return [
            _ApprovedDoc(
                file_name=row.file_name,
                folder_path=row.folder_path,
                workstreams=tuple(row.workstream or []),
                priority_tier=row.priority_tier,
            )
            for row in rows
        ]

    def _process_approved_row(
        self,
        approved: _ApprovedDoc,
        *,
        status_map: dict[str, StatusRow],
        force_all: bool,
        force_ids: set[str],
        summary: ManifestSummary,
        resolved_by_id: dict[str, _ResolvedDoc],
    ) -> _ResolvedDoc | None:
        full_path, relative_path = self._resolve_paths(
            approved.folder_path, approved.file_name
        )
        if not os.path.exists(full_path):
            summary.absent_on_volume.append(approved.file_name)
            return None
        if Path(approved.file_name).suffix.lower() not in _ALLOWED_EXTENSIONS:
            summary.disallowed_extensions.append(approved.file_name)
            return None

        source_mtime, source_size = self._stat_source(full_path)
        doc_id = make_doc_id(
            self.catalog,
            self.schema,
            self.company,
            approved.folder_path,
            approved.file_name,
        )
        classification = self._classify(
            status_map.get(doc_id),
            source_mtime=source_mtime,
            source_size=source_size,
            force_all=force_all,
            forced=doc_id in force_ids,
        )
        summary.classification_counts[classification] += 1

        resolved = _ResolvedDoc(
            approved=approved,
            doc_id=doc_id,
            relative_path=relative_path,
            full_path=full_path,
            source_mtime=source_mtime,
            source_size=source_size,
            classification=classification,
        )
        resolved_by_id[doc_id] = resolved
        return resolved

    def _run_coverage_subpass(
        self,
        *,
        coverage_per_workstream: int,
        status_map: dict[str, StatusRow],
        force_all: bool,
        force_ids: set[str],
        summary: ManifestSummary,
        resolved_by_id: dict[str, _ResolvedDoc],
    ) -> None:
        all_tier_rows = self._read_doc_relevance(tiers=None)
        workstream_docs: dict[str, list[_ApprovedDoc]] = {}
        for approved in all_tier_rows:
            for workstream in approved.workstreams:
                workstream_docs.setdefault(workstream, []).append(approved)

        for workstream, docs in sorted(workstream_docs.items()):
            complete_count = sum(
                1
                for doc in docs
                if self._is_complete(self._doc_id_for_approved(doc), status_map)
            )
            if complete_count > 0:
                continue

            candidates: list[tuple[int, int, _ApprovedDoc, str]] = []
            coverable_count = 0
            for approved in docs:
                inject_classification = self._coverage_inject_classification(
                    approved,
                    status_map=status_map,
                    force_all=force_all,
                    force_ids=force_ids,
                )
                if inject_classification is None:
                    continue
                coverable_count += 1
                preference = _coverage_preference_rank(
                    status_map.get(self._doc_id_for_approved(approved)),
                    inject_classification,
                )
                candidates.append(
                    (
                        preference,
                        _priority_sort_key(approved.priority_tier),
                        approved,
                        inject_classification,
                    )
                )

            if coverable_count == 0 and len(docs) > 0:
                summary.zero_coverable_residuals.append((workstream, len(docs)))
                continue

            candidates.sort(key=lambda item: (item[0], item[1], item[2].file_name))
            for _, _, approved, inject_classification in candidates[:coverage_per_workstream]:
                self._inject_coverage_doc(
                    approved,
                    inject_classification,
                    status_map=status_map,
                    force_all=force_all,
                    force_ids=force_ids,
                    summary=summary,
                    resolved_by_id=resolved_by_id,
                )

    def _coverage_inject_classification(
        self,
        approved: _ApprovedDoc,
        *,
        status_map: dict[str, StatusRow],
        force_all: bool,
        force_ids: set[str],
    ) -> str | None:
        full_path, _ = self._resolve_paths(approved.folder_path, approved.file_name)
        if not os.path.exists(full_path):
            return None
        if Path(approved.file_name).suffix.lower() not in _ALLOWED_EXTENSIONS:
            return None

        source_mtime, source_size = self._stat_source(full_path)
        doc_id = self._doc_id_for_approved(approved)
        if force_all or doc_id in force_ids:
            return _CLASSIFICATION_STALE

        status_row = status_map.get(doc_id)
        if status_row is None:
            return _CLASSIFICATION_NEW
        if status_row.status in (FAILED, PARSING, EMBEDDING, PENDING):
            return _CLASSIFICATION_RETRY
        if status_row.status == ZERO_CHUNKS:
            if (
                status_row.source_mtime != source_mtime
                or status_row.source_size != source_size
            ):
                return _CLASSIFICATION_RETRY
            return None
        if status_row.status == COMPLETE:
            return None
        return _CLASSIFICATION_RETRY

    def _inject_coverage_doc(
        self,
        approved: _ApprovedDoc,
        classification: str,
        *,
        status_map: dict[str, StatusRow],
        force_all: bool,
        force_ids: set[str],
        summary: ManifestSummary,
        resolved_by_id: dict[str, _ResolvedDoc],
    ) -> None:
        existing = resolved_by_id.get(self._doc_id_for_approved(approved))
        if existing is not None:
            if existing.classification not in _WORK_LIST_CLASSIFICATIONS:
                summary.classification_counts[existing.classification] -= 1
                existing.classification = classification
                summary.classification_counts[classification] += 1
                existing.coverage_injected = True
            return

        resolved = self._process_approved_row(
            approved,
            status_map=status_map,
            force_all=force_all,
            force_ids=force_ids,
            summary=summary,
            resolved_by_id=resolved_by_id,
        )
        if resolved is None:
            return
        resolved.coverage_injected = True
        if resolved.classification not in _WORK_LIST_CLASSIFICATIONS:
            summary.classification_counts[resolved.classification] -= 1
            resolved.classification = classification
            summary.classification_counts[classification] += 1

    def _doc_id_for_approved(self, approved: _ApprovedDoc) -> str:
        return make_doc_id(
            self.catalog,
            self.schema,
            self.company,
            approved.folder_path,
            approved.file_name,
        )

    @staticmethod
    def _is_complete(doc_id: str, status_map: dict[str, StatusRow]) -> bool:
        row = status_map.get(doc_id)
        return row is not None and row.status == COMPLETE

    def _resolve_paths(
        self, folder_path: str | None, file_name: str
    ) -> tuple[str, str]:
        volume_root = self._volume_root
        if folder_path not in ("", ".", None):
            full_path = os.path.join(volume_root, folder_path, file_name)
            relative_path = f"{folder_path}/{file_name}"
        else:
            full_path = os.path.join(volume_root, file_name)
            relative_path = file_name
        return full_path, relative_path

    @staticmethod
    def _stat_source(full_path: str) -> tuple[int, int]:
        stat = os.stat(full_path)
        return int(stat.st_mtime), int(stat.st_size)

    @staticmethod
    def _classify(
        status_row: StatusRow | None,
        *,
        source_mtime: int,
        source_size: int,
        force_all: bool,
        forced: bool,
    ) -> str:
        if force_all or forced:
            return _CLASSIFICATION_STALE
        if status_row is None:
            return _CLASSIFICATION_NEW
        status = status_row.status
        if status == COMPLETE:
            if status_row.parser_version != PARSER_VERSION:
                return _CLASSIFICATION_STALE
            if (
                status_row.source_mtime != source_mtime
                or status_row.source_size != source_size
            ):
                return _CLASSIFICATION_STALE
            return _CLASSIFICATION_SKIP
        if status == FAILED:
            return _CLASSIFICATION_RETRY
        if status == ZERO_CHUNKS:
            if (
                status_row.source_mtime != source_mtime
                or status_row.source_size != source_size
            ):
                return _CLASSIFICATION_RETRY
            return _CLASSIFICATION_SKIP
        if status in (PARSING, EMBEDDING, PENDING):
            return _CLASSIFICATION_RETRY
        return _CLASSIFICATION_RETRY

    @staticmethod
    def _to_manifest_item(doc: _ResolvedDoc) -> ManifestItem:
        return ManifestItem(
            doc_id=doc.doc_id,
            file_name=doc.approved.file_name,
            relative_path=doc.relative_path,
            full_path=doc.full_path,
            source_mtime=doc.source_mtime,
            source_size=doc.source_size,
            classification=doc.classification,
            coverage_injected=doc.coverage_injected,
        )


def _priority_sort_key(priority_tier: int | None) -> int:
    return priority_tier if priority_tier is not None else 1_000_000


def _coverage_preference_rank(
    status_row: StatusRow | None, classification: str
) -> int:
    if classification not in _WORK_LIST_CLASSIFICATIONS:
        return 2
    if status_row is not None and status_row.status == ZERO_CHUNKS:
        return 1
    return 0
