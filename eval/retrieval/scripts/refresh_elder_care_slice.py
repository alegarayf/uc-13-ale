"""Regenerate elder_care_slice.json from committed gold + live warehouse chunks.

Operator-run only (spec item 19 / plan T9). Never wired into CI.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

from dotenv import load_dotenv

from eval.retrieval.errors import PreconditionError
from eval.retrieval.gold.bootstrap import (
    DEFAULT_CATALOG,
    DEFAULT_COMPANY_NAME,
    load_gold_labels,
)
from eval.retrieval.models import EvalFixtureSlice, FixtureChunk, GoldLabel

SLICE_INTENT_IDS: tuple[str, ...] = (
    "fta.opex.q3_projected_financials",
    "legal.contracts_vendors_platform",
    "cqa.retrieve_customer_concentration",
)

EXPECTED_GOLD_METHOD = "citation_backfill"
_PREVIEW_LEN = 120
_MOCK_SCORE_INTENTS: tuple[str, ...] = (
    "fta.opex.q3_projected_financials",
    "legal.contracts_vendors_platform",
)
_MOCK_SCORE_TEMPLATE = (0.92, 0.90, 0.88, 0.86, 0.84)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_gold_path() -> Path:
    return _repo_root() / "eval" / "retrieval" / "gold_labels" / "elder_care.yaml"


def _default_fixture_path() -> Path:
    return _repo_root() / "eval" / "retrieval" / "fixtures" / "elder_care_slice.json"


def _escape_sql_literal(value: str) -> str:
    return value.replace("'", "''")


def _chunk_ids_in_clause(chunk_ids: Sequence[str]) -> str:
    if not chunk_ids:
        raise PreconditionError("slice refresh requires at least one chunk id")
    literals = ", ".join(f"'{_escape_sql_literal(cid)}'" for cid in chunk_ids)
    return f"({literals})"


def load_slice_labels(
    gold_path: Path,
    intent_ids: Sequence[str] = SLICE_INTENT_IDS,
) -> list[GoldLabel]:
    by_intent = {row.intent_id: row for row in load_gold_labels(gold_path)}
    missing = [intent_id for intent_id in intent_ids if intent_id not in by_intent]
    if missing:
        raise PreconditionError(
            f"committed gold missing slice intents: {missing}"
        )
    labels = [by_intent[intent_id] for intent_id in intent_ids]
    assert_slice_gold_methods(labels)
    return labels


def assert_slice_gold_methods(
    labels: Sequence[GoldLabel],
    *,
    expected_method: str = EXPECTED_GOLD_METHOD,
) -> None:
    for label in labels:
        if label.gold_method != expected_method:
            raise PreconditionError(
                f"{label.intent_id} gold_method={label.gold_method!r} "
                f"!= expected {expected_method!r} — method change is out of scope"
            )


def collect_slice_chunk_ids(labels: Sequence[GoldLabel]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for label in labels:
        for chunk_id in label.positive_chunk_ids:
            if chunk_id not in seen:
                seen.add(chunk_id)
                ordered.append(chunk_id)
        for chunk_id in label.negative_chunk_ids or []:
            if chunk_id not in seen:
                seen.add(chunk_id)
                ordered.append(chunk_id)
    return ordered


def build_mock_vs_scores(labels: Sequence[GoldLabel]) -> dict[str, dict[str, float]]:
    by_intent = {label.intent_id: label for label in labels}
    scores: dict[str, dict[str, float]] = {}
    for intent_id in _MOCK_SCORE_INTENTS:
        if intent_id not in by_intent:
            continue
        label = by_intent[intent_id]
        top_ids = label.positive_chunk_ids[: len(_MOCK_SCORE_TEMPLATE)]
        template = _MOCK_SCORE_TEMPLATE[: len(top_ids)]
        scores[intent_id] = {
            chunk_id: score
            for chunk_id, score in zip(top_ids, template, strict=True)
        }
    return scores


def _chunks_query(
    catalog: str,
    company_name: str,
    chunk_ids: Sequence[str],
) -> str:
    company_lit = _escape_sql_literal(company_name)
    ids_clause = _chunk_ids_in_clause(chunk_ids)
    return f"""
        SELECT
            c.chunk_id,
            c.file_name,
            c.section_header,
            c.page_start,
            COALESCE(c.source_type, 'text') AS source_type,
            r.priority_tier,
            c.chunk_text
        FROM {catalog}.ingestion.chunks c
        JOIN {catalog}.classification.doc_relevance r
            ON c.doc_id = r.doc_id
        WHERE c.company_name = '{company_lit}'
          AND c.chunk_id IN {ids_clause}
    """


def _preview_text(chunk_text: str | None) -> str:
    text = (chunk_text or "").strip().replace("\n", " ")
    if len(text) <= _PREVIEW_LEN:
        return text or "Placeholder preview for CI fixture chunk."
    return text[: _PREVIEW_LEN - 3] + "..."


def _row_to_fixture_chunk(row: dict[str, Any]) -> FixtureChunk:
    return FixtureChunk(
        chunk_id=str(row["chunk_id"]),
        file_name=str(row["file_name"]),
        section_header=str(row.get("section_header") or ""),
        page_start=int(row.get("page_start") or 0),
        source_type=str(row.get("source_type") or "text"),
        priority_tier=int(row.get("priority_tier") or 1),
        chunk_text_preview=_preview_text(
            row.get("chunk_text") if row.get("chunk_text") is not None else None
        ),
    )


def fetch_chunk_rows_via_warehouse(
    chunk_ids: Sequence[str],
    *,
    catalog: str = DEFAULT_CATALOG,
    company_name: str = DEFAULT_COMPANY_NAME,
) -> list[dict[str, Any]]:
    from databricks.sdk import WorkspaceClient

    load_dotenv(_repo_root() / ".env")
    host = os.environ.get("DATABRICKS_SERVER_HOSTNAME")
    token = os.environ.get("DATABRICKS_TOKEN")
    http_path = os.environ.get("DATABRICKS_HTTP_PATH")
    if not host or not token or not http_path:
        raise RuntimeError(
            "Missing DATABRICKS_SERVER_HOSTNAME, DATABRICKS_TOKEN, or "
            "DATABRICKS_HTTP_PATH in repo-root .env"
        )

    warehouse_id = http_path.rstrip("/").split("/")[-1]
    client = WorkspaceClient(host=host, token=token)
    statement = _chunks_query(catalog, company_name, chunk_ids)
    result = client.statement_execution.execute_statement(
        warehouse_id=warehouse_id,
        statement=statement,
        wait_timeout="50s",
    )
    state = result.status.state.value if result.status else "UNKNOWN"
    if state != "SUCCEEDED":
        message = getattr(result.status, "error", None)
        raise RuntimeError(f"warehouse query failed: state={state} error={message}")

    columns = [col.name for col in result.manifest.schema.columns]
    rows: list[dict[str, Any]] = []
    data = result.result.data_array if result.result else []
    for raw in data:
        rows.append(dict(zip(columns, raw, strict=True)))
    return rows


def build_fixture_slice(
    labels: Sequence[GoldLabel],
    chunk_rows: Sequence[dict[str, Any]],
) -> EvalFixtureSlice:
    chunk_ids = collect_slice_chunk_ids(labels)
    row_by_id = {str(row["chunk_id"]): row for row in chunk_rows}
    missing = [chunk_id for chunk_id in chunk_ids if chunk_id not in row_by_id]
    if missing:
        raise PreconditionError(
            f"{len(missing)} slice chunk ids missing from live corpus: "
            f"{missing[:5]}{'...' if len(missing) > 5 else ''}"
        )

    snapshots = {label.ingestion_snapshot for label in labels}
    if len(snapshots) != 1:
        raise PreconditionError(
            f"slice intents disagree on ingestion_snapshot: {sorted(snapshots)}"
        )
    ingestion_snapshot = next(iter(snapshots))
    catalog = labels[0].catalog
    company_name = labels[0].company_name

    chunks = [_row_to_fixture_chunk(row_by_id[chunk_id]) for chunk_id in chunk_ids]
    return EvalFixtureSlice(
        catalog=catalog,
        company_name=company_name,
        ingestion_snapshot=ingestion_snapshot,
        chunks=chunks,
        intents=list(labels),
        mock_vs_scores=build_mock_vs_scores(labels),
    )


def refresh_elder_care_slice(
    *,
    gold_path: Path,
    output_path: Path,
    dry_run: bool = False,
) -> EvalFixtureSlice:
    labels = load_slice_labels(gold_path)
    chunk_ids = collect_slice_chunk_ids(labels)
    chunk_rows = fetch_chunk_rows_via_warehouse(chunk_ids)
    fixture = build_fixture_slice(labels, chunk_rows)

    print(
        f"[refresh_elder_care_slice] intents={len(labels)} "
        f"chunk_ids={len(chunk_ids)} resolved={len(chunk_rows)} "
        f"snapshot={fixture.ingestion_snapshot}"
    )
    if missing := [cid for cid in chunk_ids if cid not in {r['chunk_id'] for r in chunk_rows}]:
        raise PreconditionError(f"unresolved ids after build: {missing}")

    payload = fixture.model_dump(mode="json")
    if dry_run:
        print("[refresh_elder_care_slice] dry-run — fixture not written")
        return fixture

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"[refresh_elder_care_slice] wrote {output_path}")
    return fixture


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eval.retrieval.scripts.refresh_elder_care_slice",
        description=(
            "Regenerate eval/retrieval/fixtures/elder_care_slice.json from "
            "committed gold + live uc13_ale.ingestion.chunks (operator-run)."
        ),
    )
    parser.add_argument(
        "--gold-path",
        type=Path,
        default=_default_gold_path(),
        help="Committed gold YAML (default: eval/retrieval/gold_labels/elder_care.yaml)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_default_fixture_path(),
        help="Fixture JSON output path",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate + print summary without writing the fixture",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        refresh_elder_care_slice(
            gold_path=args.gold_path,
            output_path=args.output,
            dry_run=args.dry_run,
        )
    except (PreconditionError, RuntimeError, ValueError) as exc:
        print(f"[refresh_elder_care_slice] ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
