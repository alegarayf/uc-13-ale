"""C6 trust-statement generator v0 — spec §8.2 / §8.4 / §12.2 / §17 item 10."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Protocol

import yaml

from eval.retrieval.errors import EvalError

_DEFAULT_CATALOG = "uc13_ale"
_DEFAULT_OUTPUT = Path(".dev/eval-program/trust_statement.md")
_DEFAULT_REGISTRY = Path(".dev/eval-program/registry.yaml")
_UNNORMALIZABLE_SLUG = "__unnormalizable__"

LAYERS = (
    "ingest_completeness",
    "retrieval",
    "agent_fields",
    "e2e",
    "content_correctness",
)
CONTENT_SURFACES = ("fta_numeric", "legal_register", "exec_summary")
ATTESTATIONS = frozenset({"attested", "partial", "not_attested", "known_gap"})
REASONS = frozenset(
    {
        "no_completed_run",
        "zero_claim_run",
        "claim_failures",
        "exempted_corpus_failures",
        "incomplete_corpus",
        "probe_unavailable",
        "denominator_undefined",
        "unnormalizable_company",
        "corpus_absent",
        "corpus_thin",
        "overlay_mismatch",
    }
)
METHODS = frozenset({"sql_chunk_count", "doc_status", "null"})
RUNGS = frozenset({"deterministic", "judge", "human", "null"})


class TrustStatementGenerationError(EvalError):
    """Whole-artifact halt on schema or vocabulary violation (DG-14)."""


@dataclass(frozen=True)
class CompanyDomainRow:
    company: str
    catalog: str
    display_name: str | None = None


@dataclass(frozen=True)
class IngestProbeResult:
    company: str
    catalog: str
    backend: Literal["sql_chunk_count", "doc_status"]
    status: Literal["measured", "denominator_undefined", "probe_failed"]
    completeness: float | None = None
    denominator: int | None = None
    per_doc_type: dict[str, dict[str, int]] = field(default_factory=dict)


@dataclass(frozen=True)
class TrustStatementRow:
    company: str
    layer: str
    surface: str | None
    attestation: str
    reason: str | None
    method: str | None
    rung: str | None
    evidence_refs: list[str] = field(default_factory=list)
    known_gaps: list[str] = field(default_factory=list)
    manual_check: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "company": self.company,
            "layer": self.layer,
            "surface": self.surface,
            "attestation": self.attestation,
            "reason": self.reason,
            "method": self.method,
            "rung": self.rung,
            "evidence_refs": list(self.evidence_refs),
            "known_gaps": list(self.known_gaps),
            "manual_check": self.manual_check,
        }


class SqlExecutor(Protocol):
    def __call__(self, sql: str) -> list[list[str | None]]: ...


def _escape_sql_literal(value: str) -> str:
    return value.replace("'", "''")


def _rows_per_company(company: str) -> list[tuple[str, str | None]]:
    keys: list[tuple[str, str | None]] = []
    for layer in LAYERS:
        if layer == "content_correctness":
            for surface in CONTENT_SURFACES:
                keys.append((layer, surface))
        else:
            keys.append((layer, None))
    return keys


def validate_row(row: TrustStatementRow) -> None:
    if row.layer not in LAYERS:
        raise TrustStatementGenerationError(
            f"row ({row.company}, {row.layer}, {row.surface}): out-of-vocabulary layer {row.layer!r}"
        )
    if row.layer == "content_correctness":
        if row.surface not in CONTENT_SURFACES:
            raise TrustStatementGenerationError(
                f"row ({row.company}, {row.layer}, {row.surface}): "
                "surface required for content_correctness"
            )
    elif row.surface is not None:
        raise TrustStatementGenerationError(
            f"row ({row.company}, {row.layer}, {row.surface}): "
            "surface must be null outside content_correctness"
        )
    if row.attestation not in ATTESTATIONS:
        raise TrustStatementGenerationError(
            f"row ({row.company}, {row.layer}, {row.surface}): "
            f"out-of-vocabulary attestation {row.attestation!r}"
        )
    if row.attestation == "attested":
        if row.reason is not None:
            raise TrustStatementGenerationError(
                f"row ({row.company}, {row.layer}, {row.surface}): "
                "reason must be null on attested rows"
            )
    else:
        if not row.reason:
            raise TrustStatementGenerationError(
                f"row ({row.company}, {row.layer}, {row.surface}): "
                f"reason required when attestation is {row.attestation!r}"
            )
        if row.reason not in REASONS:
            raise TrustStatementGenerationError(
                f"row ({row.company}, {row.layer}, {row.surface}): "
                f"out-of-vocabulary reason {row.reason!r}"
            )
    if row.method is not None and row.method not in METHODS:
        raise TrustStatementGenerationError(
            f"row ({row.company}, {row.layer}, {row.surface}): "
            f"out-of-vocabulary method {row.method!r}"
        )
    if row.rung is not None and row.rung not in RUNGS:
        raise TrustStatementGenerationError(
            f"row ({row.company}, {row.layer}, {row.surface}): "
            f"out-of-vocabulary rung {row.rung!r}"
        )
    if row.attestation in {"attested", "partial"}:
        if row.layer == "content_correctness" and row.rung is None:
            raise TrustStatementGenerationError(
                f"row ({row.company}, {row.layer}, {row.surface}): "
                f"rung required for run-provenance attestation {row.attestation!r}"
            )
    elif row.rung is not None:
        raise TrustStatementGenerationError(
            f"row ({row.company}, {row.layer}, {row.surface}): "
            f"rung must be null when attestation is {row.attestation!r}"
        )


def validate_rows(rows: list[TrustStatementRow]) -> None:
    seen: set[tuple[str, str, str | None]] = set()
    for row in rows:
        validate_row(row)
        key = (row.company, row.layer, row.surface)
        if key in seen:
            raise TrustStatementGenerationError(f"duplicate row key {key}")
        seen.add(key)


def assert_row_set_total(rows: list[TrustStatementRow], companies: list[str]) -> None:
    """HALT-12 guard: every company carries the full layer × surface cross-product."""
    for company in companies:
        expected = {(company, layer, surface) for layer, surface in _rows_per_company(company)}
        actual = {(row.company, row.layer, row.surface) for row in rows if row.company == company}
        if actual != expected:
            missing = expected - actual
            extra = actual - expected
            raise TrustStatementGenerationError(
                f"row set non-total for {company!r}: missing={sorted(missing)!r} extra={sorted(extra)!r}"
            )


def _ingest_row_from_probe(
    company: str,
    probe: IngestProbeResult | None,
    *,
    registry_gap_titles: list[str],
) -> TrustStatementRow:
    if probe is None:
        return TrustStatementRow(
            company=company,
            layer="ingest_completeness",
            surface=None,
            attestation="not_attested",
            reason="unnormalizable_company",
            method=None,
            rung=None,
            manual_check="Fix predecessor-owned company_name in retrieval_harness_runs",
        )
    if probe.status == "probe_failed":
        return TrustStatementRow(
            company=company,
            layer="ingest_completeness",
            surface=None,
            attestation="not_attested",
            reason="probe_unavailable",
            method=None,
            rung=None,
            manual_check="Re-run sql_chunk_count ingest probe against live warehouse",
        )
    if probe.status == "denominator_undefined":
        return TrustStatementRow(
            company=company,
            layer="ingest_completeness",
            surface=None,
            attestation="not_attested",
            reason="denominator_undefined",
            method=None,
            rung=None,
            manual_check="Establish expected-document profile before attesting ingest",
        )
    assert probe.status == "measured"
    assert probe.completeness is not None
    assert probe.denominator is not None
    if probe.completeness >= 1.0:
        return TrustStatementRow(
            company=company,
            layer="ingest_completeness",
            surface=None,
            attestation="attested",
            reason=None,
            method=probe.backend,
            rung=None,
        )
    ingested = round(probe.completeness * probe.denominator)
    known_gaps = [
        f"ingest completeness {probe.completeness:.0%} "
        f"({ingested}/{probe.denominator} expected docs with chunks)"
    ]
    known_gaps.extend(registry_gap_titles)
    return TrustStatementRow(
        company=company,
        layer="ingest_completeness",
        surface=None,
        attestation="partial",
        reason="incomplete_corpus",
        method=probe.backend,
        rung=None,
        known_gaps=known_gaps,
    )


def _default_not_attested_row(company: str, layer: str, surface: str | None) -> TrustStatementRow:
    return TrustStatementRow(
        company=company,
        layer=layer,
        surface=surface,
        attestation="not_attested",
        reason="no_completed_run",
        method=None,
        rung=None,
    )


def _sentinel_rows(company: str) -> list[TrustStatementRow]:
    rows: list[TrustStatementRow] = []
    for layer, surface in _rows_per_company(company):
        if layer == "ingest_completeness":
            rows.append(_ingest_row_from_probe(company, probe=None, registry_gap_titles=[]))
        else:
            rows.append(
                TrustStatementRow(
                    company=company,
                    layer=layer,
                    surface=surface,
                    attestation="not_attested",
                    reason="unnormalizable_company",
                    method=None,
                    rung=None,
                    manual_check="Fix predecessor-owned company_name in retrieval_harness_runs",
                )
            )
    return rows


def derive_rows_for_company(
    domain: CompanyDomainRow,
    *,
    ingest_probe: IngestProbeResult | None,
    registry_gap_titles: list[str] | None = None,
) -> list[TrustStatementRow]:
    gap_titles = registry_gap_titles or []
    if domain.company == _UNNORMALIZABLE_SLUG:
        return _sentinel_rows(domain.company)

    rows: list[TrustStatementRow] = []
    for layer, surface in _rows_per_company(domain.company):
        if layer == "ingest_completeness":
            rows.append(
                _ingest_row_from_probe(
                    domain.company,
                    ingest_probe,
                    registry_gap_titles=gap_titles,
                )
            )
        else:
            rows.append(_default_not_attested_row(domain.company, layer, surface))
    validate_rows(rows)
    return rows


def derive_rows(
    domain: list[CompanyDomainRow],
    *,
    ingest_probes: dict[str, IngestProbeResult | None],
    registry_gap_titles_by_company: dict[str, list[str]] | None = None,
) -> list[TrustStatementRow]:
    gap_map = registry_gap_titles_by_company or {}
    rows: list[TrustStatementRow] = []
    for entry in domain:
        rows.extend(
            derive_rows_for_company(
                entry,
                ingest_probe=ingest_probes.get(entry.company),
                registry_gap_titles=gap_map.get(entry.company, []),
            )
        )
    validate_rows(rows)
    return rows


def load_registry(registry_path: Path) -> dict[str, Any]:
    if not registry_path.is_file():
        raise TrustStatementGenerationError(f"registry not found: {registry_path}")
    return yaml.safe_load(registry_path.read_text(encoding="utf-8"))


def registry_gap_titles_for_company(
    registry: dict[str, Any],
    *,
    company_slug: str,
) -> list[str]:
    slug_tokens = company_slug.replace("_", " ")
    titles: list[str] = []
    for item in registry.get("items") or []:
        if item.get("disposition") != "staged":
            continue
        title = str(item.get("title") or "")
        title_lower = title.lower()
        if "ingest" not in title_lower and "corpus" not in title_lower:
            continue
        if slug_tokens not in title_lower and company_slug not in title_lower:
            if company_slug != "elder_care" or "elder" not in title_lower:
                continue
        titles.append(title)
    return titles


def _ingest_probe_sql(catalog: str, company_display: str) -> str:
    company_literal = _escape_sql_literal(company_display)
    return f"""
WITH ingested AS (
  SELECT DISTINCT c.doc_id
  FROM {catalog}.ingestion.chunks c
  WHERE c.company_name = '{company_literal}'
)
SELECT
  (SELECT COUNT(DISTINCT doc_id) FROM {catalog}.classification.doc_relevance
   WHERE company_name = '{company_literal}' AND should_parse = true) AS denominator,
  (SELECT COUNT(1) FROM ingested i
   WHERE i.doc_id IN (
     SELECT doc_id FROM {catalog}.classification.doc_relevance
     WHERE company_name = '{company_literal}' AND should_parse = true
   )) AS ingested_count
"""


def _ingest_per_doc_type_sql(catalog: str, company_display: str) -> str:
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
)
SELECT e.doc_type,
       COUNT(DISTINCT e.doc_id) AS expected,
       COUNT(DISTINCT CASE WHEN i.doc_id IS NOT NULL THEN e.doc_id END) AS ingested
FROM expected e
LEFT JOIN ingested i ON e.doc_id = i.doc_id
GROUP BY e.doc_type
ORDER BY e.doc_type
"""


def run_ingest_probe(
    execute_sql: SqlExecutor,
    *,
    company_slug: str,
    catalog: str,
    company_display: str,
) -> IngestProbeResult:
    """Implement §8.4 sql_chunk_count backend; never raises across the boundary."""
    try:
        count_rows = execute_sql(_ingest_probe_sql(catalog, company_display))
        if not count_rows or len(count_rows[0]) < 2:
            return IngestProbeResult(
                company=company_slug,
                catalog=catalog,
                backend="sql_chunk_count",
                status="probe_failed",
            )
        denominator = int(count_rows[0][0] or 0)
        ingested_count = int(count_rows[0][1] or 0)
        if denominator <= 0:
            return IngestProbeResult(
                company=company_slug,
                catalog=catalog,
                backend="sql_chunk_count",
                status="denominator_undefined",
            )
        per_doc_type: dict[str, dict[str, int]] = {}
        breakdown_rows = execute_sql(_ingest_per_doc_type_sql(catalog, company_display))
        for row in breakdown_rows:
            if len(row) < 3 or row[0] is None:
                continue
            per_doc_type[str(row[0])] = {
                "expected": int(row[1] or 0),
                "ingested": int(row[2] or 0),
            }
        completeness = ingested_count / denominator
        return IngestProbeResult(
            company=company_slug,
            catalog=catalog,
            backend="sql_chunk_count",
            status="measured",
            completeness=completeness,
            denominator=denominator,
            per_doc_type=per_doc_type,
        )
    except Exception:  # noqa: BLE001 - §8.4 boundary contract
        return IngestProbeResult(
            company=company_slug,
            catalog=catalog,
            backend="sql_chunk_count",
            status="probe_failed",
        )


def fetch_company_domain_sql(catalog: str) -> str:
    return f"""
SELECT
  b.company,
  b.catalog,
  lb.company_name AS display_name
FROM {catalog}.ops.baseline_complete_companies b
LEFT JOIN {catalog}.ops.retrieval_harness_latest_baseline lb
  ON {catalog}.ops.canonical_company_slug(lb.company_name) = b.company
 AND lb.catalog = b.catalog
"""


def parse_company_domain(rows: list[list[str | None]], catalog: str) -> list[CompanyDomainRow]:
    domain: list[CompanyDomainRow] = []
    for row in rows:
        if len(row) < 2 or row[0] is None:
            continue
        domain.append(
            CompanyDomainRow(
                company=str(row[0]),
                catalog=str(row[1] or catalog),
                display_name=str(row[2]) if len(row) > 2 and row[2] else None,
            )
        )
    return domain


def render_trust_statement_markdown(
    rows: list[TrustStatementRow],
    *,
    catalog: str,
    generated_at: datetime | None = None,
) -> str:
    when = generated_at or datetime.now(timezone.utc)
    payload = [row.as_dict() for row in rows]
    yaml_block = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    companies = sorted({row.company for row in rows})
    return "\n".join(
        [
            "# Trust statement (generated — do not edit)",
            "",
            f"Generated: {when.isoformat()}",
            f"Catalog: {catalog}",
            f"Companies: {', '.join(companies)}",
            f"Row count: {len(rows)}",
            "",
            "## Rows",
            "",
            "```yaml",
            yaml_block.rstrip(),
            "```",
            "",
        ]
    )


def generate_trust_statement(
    *,
    execute_sql: SqlExecutor,
    catalog: str,
    registry_path: Path,
) -> list[TrustStatementRow]:
    registry = load_registry(registry_path)
    domain_rows = execute_sql(fetch_company_domain_sql(catalog))
    domain = parse_company_domain(domain_rows, catalog)
    if not domain:
        raise TrustStatementGenerationError(
            f"derived company domain is empty for catalog {catalog!r}"
        )

    probes: dict[str, IngestProbeResult | None] = {}
    gap_titles: dict[str, list[str]] = {}
    for entry in domain:
        gap_titles[entry.company] = registry_gap_titles_for_company(
            registry, company_slug=entry.company
        )
        if entry.company == _UNNORMALIZABLE_SLUG:
            probes[entry.company] = None
            continue
        display = entry.display_name or entry.company.replace("_", " ").title()
        probes[entry.company] = run_ingest_probe(
            execute_sql,
            company_slug=entry.company,
            catalog=entry.catalog,
            company_display=display,
        )

    rows = derive_rows(domain, ingest_probes=probes, registry_gap_titles_by_company=gap_titles)
    assert_row_set_total(rows, [entry.company for entry in domain])
    return rows


def write_trust_statement(
    path: Path,
    rows: list[TrustStatementRow],
    *,
    catalog: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_trust_statement_markdown(rows, catalog=catalog),
        encoding="utf-8",
    )


def databricks_sql_executor(catalog: str) -> SqlExecutor:
    """Build a live warehouse SQL executor (not for pytest)."""

    def _execute(sql: str) -> list[list[str | None]]:
        from dotenv import load_dotenv

        load_dotenv()
        from databricks.sdk import WorkspaceClient

        w = WorkspaceClient(
            host=os.environ["DATABRICKS_SERVER_HOSTNAME"],
            token=os.environ["DATABRICKS_TOKEN"],
        )
        wh = os.environ["DATABRICKS_HTTP_PATH"].rstrip("/").split("/")[-1]
        stmt = w.statement_execution.execute_statement(
            warehouse_id=wh,
            statement=sql,
            wait_timeout="50s",
        )
        if stmt.status.state.value != "SUCCEEDED":
            raise RuntimeError(f"warehouse SQL failed: {stmt.status.state.value}")
        if not stmt.result or not stmt.result.data_array:
            return []
        return stmt.result.data_array

    return _execute


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eval.retrieval.trust_statement")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser(
        "generate",
        help="Regenerate .dev/eval-program/trust_statement.md from live ops + registry",
    )
    generate.add_argument(
        "--catalog",
        default=_DEFAULT_CATALOG,
        help=f"Unity Catalog (default: {_DEFAULT_CATALOG})",
    )
    generate.add_argument(
        "--output",
        type=Path,
        default=_DEFAULT_OUTPUT,
        help=f"Generated markdown path (default: {_DEFAULT_OUTPUT})",
    )
    generate.add_argument(
        "--registry",
        type=Path,
        default=_DEFAULT_REGISTRY,
        help=f"Registry YAML read path (default: {_DEFAULT_REGISTRY})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "generate":
        execute = databricks_sql_executor(args.catalog)
        rows = generate_trust_statement(
            execute_sql=execute,
            catalog=args.catalog,
            registry_path=args.registry,
        )
        write_trust_statement(args.output, rows, catalog=args.catalog)
        print(
            f"trust_statement: wrote {len(rows)} rows for "
            f"{len({r.company for r in rows})} companies -> {args.output}"
        )
        return 0
    raise TrustStatementGenerationError(f"unknown command: {args.command}")


if __name__ == "__main__":
    sys.exit(main())
