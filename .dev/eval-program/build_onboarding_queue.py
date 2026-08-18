"""Build ranked SharePoint onboarding queue from warehouse inventory (spec D5 / M5 T5).

Read-only: queries ``ingestion.chunks`` and ``classification.doc_relevance`` via
Databricks SQL warehouse; optionally runs ``ingest_preflight`` (``sql_chunk_count``)
per company. Emits ``eval/program/onboarding_queue.yaml``.

When the discovered company count is large, preflight for every company may be
expensive — pass ``--preflight none`` to emit ``ingest_completeness_ratio: null``
for all companies (D5 null-sort rule). A full preflight batch is a follow-up, not
blocking for queue generation.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from eval.retrieval.companies import canonical_company_slug
from eval.retrieval.ingest_preflight import run_ingest_preflight

_DEFAULT_CATALOG = "uc13_ale"
_DEFAULT_OUTPUT = Path("eval/program/onboarding_queue.yaml")
_SCHEMA_VERSION = 1
_PREFLIGHT_BATCH_CAP = 20

# Playbook §2.1 documented eval set — always preflighted when mode is ``documented``.
_DOCUMENTED_SLUGS = frozenset({"elder_care", "clearsulting", "gkf", "spg"})

_WAVE_BY_SLUG = {
    "elder_care": "W0",
    "clearsulting": "W1",
    "gkf": "W2",
    "spg": "W2",
}

REQUIRED_COMPANY_FIELDS = (
    "display_name",
    "slug",
    "chunk_count",
    "ingest_completeness_ratio",
    "doc_type_diversity_score",
    "rank_score",
    "wave",
    "notes",
)


class SqlExecutor(Protocol):
    def __call__(self, sql: str) -> list[list[str | None]]: ...


@dataclass(frozen=True)
class CompanyInventoryRow:
    display_name: str
    slug: str
    chunk_count: int
    ingest_completeness_ratio: float | None
    doc_type_diversity_score: float
    rank_score: float | None
    wave: str
    notes: str


def _escape_sql_literal(value: str) -> str:
    return value.replace("'", "''")


def _company_inventory_sql(catalog: str) -> str:
    return f"""
SELECT company_name, COUNT(*) AS chunk_count
FROM {catalog}.ingestion.chunks
GROUP BY company_name
"""


def _doc_type_diversity_sql(catalog: str, company_display: str) -> str:
    company_literal = _escape_sql_literal(company_display)
    return f"""
WITH expected AS (
  SELECT doc_id, explode(workstream) AS doc_type
  FROM {catalog}.classification.doc_relevance
  WHERE company_name = '{company_literal}' AND should_parse = true
),
ingested AS (
  SELECT DISTINCT c.doc_id
  FROM {catalog}.ingestion.chunks c
  WHERE c.company_name = '{company_literal}'
),
category_stats AS (
  SELECT e.doc_type,
         MAX(CASE WHEN i.doc_id IS NOT NULL THEN 1 ELSE 0 END) AS has_chunked
  FROM expected e
  LEFT JOIN ingested i ON e.doc_id = i.doc_id
  GROUP BY e.doc_type
)
SELECT
  COUNT(*) AS max_categories,
  COALESCE(SUM(has_chunked), 0) AS populated_categories
FROM category_stats
"""


def compute_doc_type_diversity_score(
    populated_categories: int, max_categories: int
) -> float:
    """Normalized 0–1 score per spec D5."""
    if max_categories <= 0:
        return 0.0
    return populated_categories / max_categories


def compute_rank_score(
    ingest_completeness_ratio: float | None,
    doc_type_diversity_score: float,
) -> float | None:
    if ingest_completeness_ratio is None:
        return None
    return ingest_completeness_ratio * doc_type_diversity_score


def assign_wave(slug: str) -> str:
    return _WAVE_BY_SLUG.get(slug, "W3")


def rank_companies(rows: list[CompanyInventoryRow]) -> list[CompanyInventoryRow]:
    """D5 sort: measured rank_score desc, then null-preflight by chunk_count desc."""

    def sort_key(row: CompanyInventoryRow) -> tuple[int, float, int, str]:
        if row.rank_score is not None:
            return (0, -row.rank_score, -row.chunk_count, row.slug)
        return (1, 0.0, -row.chunk_count, row.slug)

    return sorted(rows, key=sort_key)


def fetch_company_inventory(
    execute_sql: SqlExecutor, *, catalog: str
) -> list[tuple[str, int]]:
    rows = execute_sql(_company_inventory_sql(catalog))
    inventory: list[tuple[str, int]] = []
    for row in rows:
        if not row or row[0] is None:
            continue
        inventory.append((str(row[0]), int(row[1] or 0)))
    return inventory


def fetch_doc_type_diversity(
    execute_sql: SqlExecutor, *, catalog: str, company_display: str
) -> tuple[int, int]:
    rows = execute_sql(_doc_type_diversity_sql(catalog, company_display))
    if not rows or len(rows[0]) < 2:
        return (0, 0)
    max_categories = int(rows[0][0] or 0)
    populated = int(rows[0][1] or 0)
    return populated, max_categories


def _should_run_preflight(
    slug: str,
    *,
    mode: str,
    company_count: int,
) -> bool:
    if mode == "none":
        return False
    if mode == "all":
        return company_count <= _PREFLIGHT_BATCH_CAP
    # documented
    return slug in _DOCUMENTED_SLUGS


def build_company_row(
    execute_sql: SqlExecutor,
    *,
    catalog: str,
    display_name: str,
    chunk_count: int,
    preflight_mode: str,
    company_count: int,
) -> CompanyInventoryRow:
    slug = canonical_company_slug(display_name)
    populated, max_categories = fetch_doc_type_diversity(
        execute_sql, catalog=catalog, company_display=display_name
    )
    diversity = compute_doc_type_diversity_score(populated, max_categories)

    completeness: float | None = None
    notes = ""
    if _should_run_preflight(
        slug, mode=preflight_mode, company_count=company_count
    ):
        probe = run_ingest_preflight(
            backend="sql_chunk_count",
            company_slug=slug,
            catalog=catalog,
            company_display=display_name,
            execute_sql=execute_sql,
        )
        if probe.status == "measured" and probe.completeness is not None:
            completeness = probe.completeness
        else:
            notes = f"preflight_status={probe.status}"
    elif preflight_mode == "all" and company_count > _PREFLIGHT_BATCH_CAP:
        notes = "preflight_skipped_batch_cap"
    elif preflight_mode == "documented" and slug not in _DOCUMENTED_SLUGS:
        notes = "preflight_not_run"

    rank_score = compute_rank_score(completeness, diversity)
    return CompanyInventoryRow(
        display_name=display_name,
        slug=slug,
        chunk_count=chunk_count,
        ingest_completeness_ratio=completeness,
        doc_type_diversity_score=diversity,
        rank_score=rank_score,
        wave=assign_wave(slug),
        notes=notes,
    )


def build_queue_document(
    execute_sql: SqlExecutor,
    *,
    catalog: str,
    preflight_mode: str = "documented",
) -> dict[str, Any]:
    inventory = fetch_company_inventory(execute_sql, catalog=catalog)
    if not inventory:
        raise RuntimeError("warehouse returned zero companies from ingestion.chunks")

    company_count = len(inventory)
    rows = [
        build_company_row(
            execute_sql,
            catalog=catalog,
            display_name=display_name,
            chunk_count=chunk_count,
            preflight_mode=preflight_mode,
            company_count=company_count,
        )
        for display_name, chunk_count in inventory
    ]
    ranked = rank_companies(rows)
    return {
        "schema_version": _SCHEMA_VERSION,
        "catalog": catalog,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "companies": [
            {
                "display_name": row.display_name,
                "slug": row.slug,
                "chunk_count": row.chunk_count,
                "ingest_completeness_ratio": row.ingest_completeness_ratio,
                "doc_type_diversity_score": row.doc_type_diversity_score,
                "rank_score": row.rank_score,
                "wave": row.wave,
                "notes": row.notes,
            }
            for row in ranked
        ],
    }


def validate_queue_document(document: dict[str, Any]) -> None:
    if document.get("schema_version") != _SCHEMA_VERSION:
        raise ValueError("schema_version must be 1")
    companies = document.get("companies")
    if not isinstance(companies, list) or not companies:
        raise ValueError("companies must be a non-empty list")
    for idx, company in enumerate(companies):
        if not isinstance(company, dict):
            raise ValueError(f"companies[{idx}] must be a mapping")
        missing = [field for field in REQUIRED_COMPANY_FIELDS if field not in company]
        if missing:
            raise ValueError(f"companies[{idx}] missing fields: {missing}")


def write_queue_document(path: Path, document: dict[str, Any]) -> None:
    validate_queue_document(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def probe_connectivity(execute_sql: SqlExecutor) -> None:
    rows = execute_sql("SELECT 1 AS ok")
    if not rows or rows[0][0] != "1":
        raise RuntimeError("connectivity probe failed: SELECT 1 did not return 1")


def _live_execute_sql(catalog: str) -> SqlExecutor:
    from eval.retrieval.trust_statement import databricks_sql_executor

    return databricks_sql_executor(catalog)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build_onboarding_queue",
        description="Build eval/program/onboarding_queue.yaml from warehouse inventory.",
    )
    parser.add_argument(
        "--catalog",
        default=_DEFAULT_CATALOG,
        help=f"Unity Catalog name (default: {_DEFAULT_CATALOG})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_DEFAULT_OUTPUT,
        help=f"Output YAML path (default: {_DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--preflight",
        choices=("none", "documented", "all"),
        default="documented",
        help=(
            "Preflight mode: documented=playbook §2.1 four companies; "
            f"all=every company when count<={_PREFLIGHT_BATCH_CAP}; none=skip"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    execute_sql = _live_execute_sql(args.catalog)
    try:
        probe_connectivity(execute_sql)
        document = build_queue_document(
            execute_sql,
            catalog=args.catalog,
            preflight_mode=args.preflight,
        )
        write_queue_document(args.output, document)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        f"onboarding_queue: wrote {len(document['companies'])} companies -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
