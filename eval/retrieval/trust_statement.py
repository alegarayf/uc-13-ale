"""C6 trust-statement generator v1 — spec §8.2 / §8.4 / §12.2 / §17 item 10 / §15.3."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Protocol

import yaml

from eval.content.s2_writer import WRITERS
from eval.retrieval.errors import EvalError
from eval.retrieval.exemptions import IntentExemption, load_exemptions

logger = logging.getLogger(__name__)

_DEFAULT_CATALOG = "uc13_ale"
_DEFAULT_OUTPUT = Path("eval/program/trust_statement.md")
_DEFAULT_REGISTRY = Path("eval/program/registry.yaml")
_DEFAULT_EXEMPTIONS = Path("eval/program/eval_exemptions.yaml")
_DEFAULT_BASELINE_REPORT = Path("eval/retrieval/reports/baseline_acf58bcc4968.json")
_UNNORMALIZABLE_SLUG = "__unnormalizable__"
_GENERATOR_VERSION = "v1"
_GOLD_READY_SUMMARY = "52 ready/partial + 5 annotated exclusions (no_citation_source)"

LAYERS = (
    "ingest_completeness",
    "retrieval",
    "agent_fields",
    "e2e",
    "content_correctness",
)
CONTENT_SURFACES = ("fta_numeric", "legal_register", "exec_summary")
LAYER_CONTENT_CORRECTNESS = "content_correctness"
ATTESTATIONS = frozenset({"attested", "partial", "not_attested", "known_gap"})
WRITER_TO_RUNG: dict[str, str] = {
    "deterministic_verifier": "deterministic",
    "judge_harness": "judge",
    "human_spot_check": "human",
}
if frozenset(WRITER_TO_RUNG) != WRITERS:
    raise RuntimeError("WRITER_TO_RUNG keys must match eval.content.s2_writer.WRITERS")
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
_EXEMPTION_REASON_SEVERITY: dict[str, int] = {
    "corpus_absent": 0,
    "corpus_thin": 1,
    "overlay_mismatch": 2,
}


class TrustStatementGenerationError(EvalError):
    """Whole-artifact halt on schema or vocabulary violation (DG-14)."""


@dataclass(frozen=True)
class CompanyDomainRow:
    company: str
    catalog: str
    display_name: str | None = None


@dataclass(frozen=True)
class TrustEpochContext:
    baseline_id: str
    ingestion_snapshot: str
    gold_ready_summary: str
    refresh_event_refs: list[str] = field(default_factory=list)


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
    content_surface: str | None = None

    def __post_init__(self) -> None:
        if self.layer == LAYER_CONTENT_CORRECTNESS:
            resolved = self.content_surface if self.content_surface is not None else self.surface
            if resolved is None or resolved not in CONTENT_SURFACES:
                raise ValueError(
                    f"content_correctness row ({self.company!r}, {self.surface!r}): "
                    "content_surface required and must be a §16 surface"
                )
            if self.surface is not None and self.surface != resolved:
                raise ValueError(
                    f"content_correctness row ({self.company!r}): "
                    f"surface {self.surface!r} disagrees with content_surface {resolved!r}"
                )
            object.__setattr__(self, "content_surface", resolved)
            object.__setattr__(self, "surface", resolved)
        elif self.content_surface is not None:
            raise ValueError(
                f"row ({self.company}, {self.layer}): "
                "content_surface must be null outside content_correctness"
            )

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
        resolved_surface = (
            row.content_surface if row.content_surface is not None else row.surface
        )
        if resolved_surface not in CONTENT_SURFACES:
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
    if row.layer != "ingest_completeness" and row.method is not None:
        raise TrustStatementGenerationError(
            f"row ({row.company}, {row.layer}, {row.surface}): "
            "method must be null outside ingest_completeness"
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
        elif row.layer != "content_correctness" and row.rung is not None:
            raise TrustStatementGenerationError(
                f"row ({row.company}, {row.layer}, {row.surface}): "
                "rung must be null outside content_correctness"
            )
    elif row.rung is not None:
        raise TrustStatementGenerationError(
            f"row ({row.company}, {row.layer}, {row.surface}): "
            f"rung must be null when attestation is {row.attestation!r}"
        )
    if row.layer == "content_correctness" and row.content_surface is None:
        raise TrustStatementGenerationError(
            f"row ({row.company}, {row.layer}, {row.surface}): "
            "content_surface required for content_correctness"
        )
    if row.layer != "content_correctness" and row.content_surface is not None:
        raise TrustStatementGenerationError(
            f"row ({row.company}, {row.layer}, {row.surface}): "
            "content_surface must be null outside content_correctness"
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


def load_epoch_context_from_baseline_report(
    report_path: Path,
    *,
    gold_ready_summary: str = _GOLD_READY_SUMMARY,
    refresh_event_refs: list[str] | None = None,
) -> TrustEpochContext:
    if not report_path.is_file():
        raise TrustStatementGenerationError(f"baseline report not found: {report_path}")
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    manifest = payload.get("manifest") if isinstance(payload, dict) else None
    if not isinstance(manifest, dict):
        raise TrustStatementGenerationError(
            f"baseline report missing manifest block: {report_path}"
        )
    baseline_id = str(manifest.get("run_id") or "").strip()
    ingestion_snapshot = str(manifest.get("ingestion_snapshot") or "").strip()
    if not baseline_id or not ingestion_snapshot:
        raise TrustStatementGenerationError(
            f"baseline report manifest missing run_id or ingestion_snapshot: {report_path}"
        )
    if ":35104:" in ingestion_snapshot:
        raise TrustStatementGenerationError(
            f"baseline report cites stale 35104-epoch snapshot: {ingestion_snapshot!r}"
        )
    refs = refresh_event_refs or [
        "signoffs/T4-refresh.md",
        "signoffs/T5-baseline.md",
        str(report_path).replace("\\", "/"),
    ]
    return TrustEpochContext(
        baseline_id=baseline_id,
        ingestion_snapshot=ingestion_snapshot,
        gold_ready_summary=gold_ready_summary,
        refresh_event_refs=refs,
    )


def _retrieval_row_from_epoch(company: str, epoch: TrustEpochContext) -> TrustStatementRow:
    return TrustStatementRow(
        company=company,
        layer="retrieval",
        surface=None,
        attestation="attested",
        reason=None,
        method=None,
        rung=None,
        evidence_refs=[
            epoch.baseline_id,
            epoch.ingestion_snapshot,
            *epoch.refresh_event_refs,
        ],
        known_gaps=[f"Gold epoch: {epoch.gold_ready_summary} (@ {epoch.ingestion_snapshot})"],
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


def display_name_from_company_slug(slug: str) -> str:
    """Inverse display label for a canonical slug (paired with ``canonical_company_slug``).

    Valid only when ``canonical_company_slug(display_name_from_company_slug(slug)) == slug``.
    Callers must keep slugs on the write path folded via ``canonical_company_slug`` (§2.2).
    """
    return slug.replace("_", " ").title()


def merge_exemption_companies_into_domain(
    domain: list[CompanyDomainRow],
    exemptions: list[IntentExemption],
    *,
    catalog: str,
) -> list[CompanyDomainRow]:
    """Union §8.3 exemption-store companies into the §12.2 derived domain."""
    known = {entry.company for entry in domain}
    merged = list(domain)
    for exemption in exemptions:
        if exemption.company in known:
            continue
        known.add(exemption.company)
        merged.append(
            CompanyDomainRow(
                company=exemption.company,
                catalog=catalog,
                display_name=display_name_from_company_slug(exemption.company),
            )
        )
    return merged


def _index_company_exemptions(
    exemptions: list[IntentExemption],
) -> tuple[dict[str, list[IntentExemption]], frozenset[str]]:
    eliminates: dict[str, list[IntentExemption]] = {}
    narrows: set[str] = set()
    for exemption in exemptions:
        if exemption.surface is None:
            continue
        if exemption.coverage == "eliminates":
            eliminates.setdefault(exemption.surface, []).append(exemption)
        elif exemption.coverage == "narrows":
            narrows.add(exemption.surface)
    return eliminates, frozenset(narrows)


def _eliminates_reason_for_surface(exemptions: list[IntentExemption]) -> str:
    """Pick highest-severity reason among eliminates annotations (spec §16)."""
    return min(exemptions, key=lambda row: _EXEMPTION_REASON_SEVERITY[row.reason]).reason


def _known_gap_content_row(company: str, surface: str, reason: str) -> TrustStatementRow:
    return TrustStatementRow(
        company=company,
        layer=LAYER_CONTENT_CORRECTNESS,
        surface=surface,
        content_surface=surface,
        attestation="known_gap",
        reason=reason,
        method=None,
        rung=None,
    )


def _apply_narrows_relabel(
    row: TrustStatementRow,
    *,
    narrows_surfaces: frozenset[str],
) -> TrustStatementRow:
    surface = row.content_surface
    if (
        row.layer == LAYER_CONTENT_CORRECTNESS
        and surface is not None
        and surface in narrows_surfaces
        and row.attestation == "partial"
        and row.reason == "claim_failures"
    ):
        return TrustStatementRow(
            company=row.company,
            layer=row.layer,
            surface=row.surface,
            content_surface=row.content_surface,
            attestation=row.attestation,
            reason="exempted_corpus_failures",
            method=row.method,
            rung=row.rung,
            evidence_refs=list(row.evidence_refs),
            known_gaps=list(row.known_gaps),
            manual_check=row.manual_check,
        )
    return row


def _writer_to_rung(writer: str | None) -> str:
    if writer is None:
        raise ValueError("completion marker missing writer")
    if writer not in WRITERS:
        raise ValueError(f"marker writer {writer!r} not in §16 vocabulary")
    rung = WRITER_TO_RUNG.get(writer)
    if rung is None:
        raise ValueError(f"marker writer {writer!r} has no rung mapping")
    return rung


def _parse_decimal_field(value: str | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


_S2_SCORE_ROW_COLUMNS = 17


def _parse_sdk_run_ts(value: Any) -> datetime:
    """Normalize warehouse ``run_ts`` from SDK string readback (§9.1).

    Delta retains microsecond precision; Databricks SDK ``data_array`` default
    serialization truncates fractional seconds to three digits. Normalize-and-
    record: parse the returned string as-is — production readback cannot recover
    sub-millisecond precision from the SDK path.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    text = str(value).strip()
    if not text:
        raise ValueError("run_ts must be non-empty")
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"run_ts is not parseable ISO-8601: {value!r}") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _select_latest_marker(markers: Sequence[Any], *, surface: str) -> Any:
    """Pick the temporally latest completion marker; fail closed on SDK ties."""
    if not markers:
        raise ValueError(f"no completion markers for surface {surface!r}")
    latest_ts = max(marker.run_ts for marker in markers)
    tied = [marker for marker in markers if marker.run_ts == latest_ts]
    if len(tied) > 1:
        run_ids = sorted(marker.run_id for marker in tied)
        raise ValueError(
            f"ambiguous latest marker for surface {surface!r}: "
            f"{len(tied)} completion markers share run_ts {latest_ts.isoformat()} "
            "(SDK readback truncates sub-millisecond precision); "
            f"run_ids: {run_ids}"
        )
    return tied[0]


def _latest_marker_runs_by_surface(
    rows: Sequence[Any],
    *,
    company: str,
) -> dict[str, tuple[Any, list[Any]]]:
    """Return latest marker-complete run per surface for ``company``."""
    by_surface: dict[str, list[Any]] = {surface: [] for surface in CONTENT_SURFACES}
    for row in rows:
        if row.company != company or row.surface not in CONTENT_SURFACES:
            continue
        by_surface[row.surface].append(row)

    latest: dict[str, tuple[Any, list[Any]]] = {}
    for surface, surface_rows in by_surface.items():
        markers = [row for row in surface_rows if row.row_type == "completion_marker"]
        if not markers:
            continue
        marker = _select_latest_marker(markers, surface=surface)
        claims = [
            row
            for row in surface_rows
            if row.run_id == marker.run_id and row.row_type == "claim"
        ]
        latest[surface] = (marker, claims)
    return latest


def _content_row_from_run(
    company: str,
    surface: str,
    *,
    marker: Any,
    claims: Sequence[Any],
) -> TrustStatementRow:
    rung = _writer_to_rung(marker.writer)
    run_ref = f"s2_scores:{marker.run_id}"
    if not claims:
        return TrustStatementRow(
            company=company,
            layer=LAYER_CONTENT_CORRECTNESS,
            surface=surface,
            content_surface=surface,
            attestation="not_attested",
            reason="zero_claim_run",
            method=None,
            rung=None,
            evidence_refs=[run_ref],
        )

    failures = [
        claim
        for claim in claims
        if claim.verdict in {"contradicted", "unsupported"}
    ]
    if failures:
        return TrustStatementRow(
            company=company,
            layer=LAYER_CONTENT_CORRECTNESS,
            surface=surface,
            content_surface=surface,
            attestation="partial",
            reason="claim_failures",
            method=None,
            rung=rung,
            evidence_refs=[run_ref],
            known_gaps=[
                f"{len(failures)}/{len(claims)} claims failed on {surface}"
            ],
        )

    return TrustStatementRow(
        company=company,
        layer=LAYER_CONTENT_CORRECTNESS,
        surface=surface,
        content_surface=surface,
        attestation="attested",
        reason=None,
        method=None,
        rung=rung,
        evidence_refs=[run_ref],
    )


def _execute_warehouse_sql(client: Any, sql: str) -> list[list[str | None]]:
    if callable(client) and not hasattr(client, "execute_sql"):
        return client(sql)
    execute = getattr(client, "execute_sql", None)
    if not callable(execute):
        raise TypeError("S2 client must be a SqlExecutor callable or expose execute_sql")
    return execute(sql)


def fetch_s2_score_rows(
    company: str,
    catalog: str,
    *,
    client: Any,
) -> list[Any]:
    """Load ``s2_scores`` rows for one company via the warehouse client."""
    from eval.content.s2_writer import S2ScoreRow, TABLE_SUFFIX

    table = f"{catalog}.{TABLE_SUFFIX}"
    sql = f"""
        SELECT company, surface, run_id, run_ts, row_type, claim_id, verdict,
               rationale, writer, asserted_magnitude, asserted_unit,
               extracted_magnitude, extracted_unit, cited_chunk_id,
               cited_locator_kind, cited_locator_value, judge_verdict_advisory
        FROM {table}
        WHERE company = '{_escape_sql_literal(company)}'
    """
    logger.info(
        "fetch_s2_score_rows",
        extra={
            "event": "fetch_s2_score_rows",
            "company": company,
            "surface": "*",
            "run_id": "",
            "n_claims": 0,
        },
    )
    raw_rows = _execute_warehouse_sql(client, sql)
    parsed: list[S2ScoreRow] = []
    for row in raw_rows:
        if len(row) < _S2_SCORE_ROW_COLUMNS:
            raise ValueError(
                f"s2_scores row has {len(row)} columns; expected "
                f"{_S2_SCORE_ROW_COLUMNS} from projection"
            )
        run_ts = _parse_sdk_run_ts(row[3])
        parsed.append(
            S2ScoreRow(
                company=str(row[0]),
                surface=str(row[1]),
                run_id=str(row[2]),
                run_ts=run_ts,
                row_type=row[4],  # type: ignore[arg-type]
                claim_id=row[5],
                verdict=row[6],
                rationale=row[7],
                writer=row[8],
                asserted_magnitude=_parse_decimal_field(row[9]),
                asserted_unit=row[10],
                extracted_magnitude=_parse_decimal_field(row[11]),
                extracted_unit=row[12],
                cited_chunk_id=row[13],
                cited_locator_kind=row[14],
                cited_locator_value=row[15],
                judge_verdict_advisory=row[16],
            )
        )
    return parsed


def derive_content_rows(
    company: str,
    catalog: str,
    *,
    client: Any | None = None,
    s2_rows: Iterable[Any] | None = None,
    surfaces: Sequence[str] | None = None,
) -> list[TrustStatementRow]:
    """Derive content_correctness rows from latest marker-complete S2 runs."""
    target_surfaces = tuple(surfaces or CONTENT_SURFACES)
    if s2_rows is None:
        if client is None:
            raise ValueError(
                f"content_correctness for {company!r}: "
                "S2 dependency required — supply client or s2_rows"
            )
        rows = fetch_s2_score_rows(company, catalog, client=client)
    else:
        rows = list(s2_rows)

    latest = _latest_marker_runs_by_surface(rows, company=company)
    content_rows: list[TrustStatementRow] = []
    for surface in target_surfaces:
        run = latest.get(surface)
        if run is None:
            content_rows.append(
                _default_not_attested_row(company, LAYER_CONTENT_CORRECTNESS, surface)
            )
            continue
        marker, claims = run
        content_rows.append(
            _content_row_from_run(company, surface, marker=marker, claims=claims)
        )

    validate_rows(content_rows)
    return content_rows


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
                    content_surface=surface if layer == LAYER_CONTENT_CORRECTNESS else None,
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
    epoch_context: TrustEpochContext | None = None,
    s2_rows: Iterable[Any] | None = None,
    s2_client: Any | None = None,
    exemptions: list[IntentExemption] | None = None,
) -> list[TrustStatementRow]:
    gap_titles = registry_gap_titles or []
    if domain.company == _UNNORMALIZABLE_SLUG:
        return _sentinel_rows(domain.company)

    company_exemptions = [
        row for row in (exemptions or []) if row.company == domain.company
    ]
    eliminates_by_surface, narrows_surfaces = _index_company_exemptions(company_exemptions)
    run_surfaces = [
        surface for surface in CONTENT_SURFACES if surface not in eliminates_by_surface
    ]
    if run_surfaces:
        derived_by_surface = {
            row.content_surface: row
            for row in derive_content_rows(
                domain.company,
                domain.catalog,
                client=s2_client,
                s2_rows=s2_rows,
                surfaces=run_surfaces,
            )
        }
    else:
        derived_by_surface = {}

    content_rows: dict[str, TrustStatementRow] = {}
    for surface in CONTENT_SURFACES:
        if surface in eliminates_by_surface:
            content_rows[surface] = _known_gap_content_row(
                domain.company,
                surface,
                _eliminates_reason_for_surface(eliminates_by_surface[surface]),
            )
            continue
        row = derived_by_surface[surface]
        content_rows[surface] = _apply_narrows_relabel(
            row,
            narrows_surfaces=narrows_surfaces,
        )

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
        elif layer == "retrieval" and epoch_context is not None:
            rows.append(_retrieval_row_from_epoch(domain.company, epoch_context))
        elif layer == LAYER_CONTENT_CORRECTNESS:
            assert surface is not None
            rows.append(content_rows[surface])
        else:
            rows.append(_default_not_attested_row(domain.company, layer, surface))
    validate_rows(rows)
    return rows


def derive_rows(
    domain: list[CompanyDomainRow],
    *,
    ingest_probes: dict[str, IngestProbeResult | None],
    registry_gap_titles_by_company: dict[str, list[str]] | None = None,
    epoch_context: TrustEpochContext | None = None,
    s2_client: Any | None = None,
    s2_rows_by_company: dict[str, Iterable[Any]] | None = None,
    exemptions: list[IntentExemption] | None = None,
) -> list[TrustStatementRow]:
    gap_map = registry_gap_titles_by_company or {}
    s2_by_company = s2_rows_by_company or {}
    rows: list[TrustStatementRow] = []
    for entry in domain:
        company_s2_rows = s2_by_company.get(entry.company)
        rows.extend(
            derive_rows_for_company(
                entry,
                ingest_probe=ingest_probes.get(entry.company),
                registry_gap_titles=gap_map.get(entry.company, []),
                epoch_context=epoch_context,
                s2_client=s2_client,
                s2_rows=company_s2_rows,
                exemptions=exemptions,
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


def run_ingest_probe(
    execute_sql: SqlExecutor,
    *,
    company_slug: str,
    catalog: str,
    company_display: str,
) -> IngestProbeResult:
    """Implement §8.4 sql_chunk_count backend via shared ingest preflight."""
    from eval.retrieval.ingest_preflight import run_ingest_preflight

    return run_ingest_preflight(
        backend="sql_chunk_count",
        company_slug=company_slug,
        catalog=catalog,
        company_display=company_display,
        execute_sql=execute_sql,
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
    epoch_context: TrustEpochContext | None = None,
    generator_version: str = _GENERATOR_VERSION,
) -> str:
    when = generated_at or datetime.now(timezone.utc)
    payload = [row.as_dict() for row in rows]
    yaml_block = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    companies = sorted({row.company for row in rows})
    lines = [
        "# Trust statement (generated — do not edit)",
        "",
        f"Generated: {when.isoformat()}",
        f"Generator: {generator_version}",
        f"Catalog: {catalog}",
        f"Companies: {', '.join(companies)}",
        f"Row count: {len(rows)}",
    ]
    if epoch_context is not None:
        lines.extend(
            [
                f"Comparison epoch baseline: {epoch_context.baseline_id}",
                f"Ingestion snapshot: {epoch_context.ingestion_snapshot}",
                f"Gold ready summary: {epoch_context.gold_ready_summary}",
            ]
        )
    lines.extend(
        [
            "",
            "## Rows",
            "",
            "```yaml",
            yaml_block.rstrip(),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def generate_trust_statement(
    *,
    execute_sql: SqlExecutor,
    catalog: str,
    registry_path: Path,
    baseline_report_path: Path = _DEFAULT_BASELINE_REPORT,
    exemptions_path: Path = _DEFAULT_EXEMPTIONS,
) -> tuple[list[TrustStatementRow], TrustEpochContext]:
    registry = load_registry(registry_path)
    epoch_context = load_epoch_context_from_baseline_report(baseline_report_path)
    exemptions = load_exemptions(exemptions_path)
    domain_rows = execute_sql(fetch_company_domain_sql(catalog))
    domain = parse_company_domain(domain_rows, catalog)
    domain = merge_exemption_companies_into_domain(domain, exemptions, catalog=catalog)
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

    rows = derive_rows(
        domain,
        ingest_probes=probes,
        registry_gap_titles_by_company=gap_titles,
        epoch_context=epoch_context,
        s2_client=execute_sql,
        exemptions=exemptions,
    )
    assert_row_set_total(rows, [entry.company for entry in domain])
    return rows, epoch_context


def write_trust_statement(
    path: Path,
    rows: list[TrustStatementRow],
    *,
    catalog: str,
    epoch_context: TrustEpochContext | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_trust_statement_markdown(
            rows,
            catalog=catalog,
            epoch_context=epoch_context,
        ),
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
        help="Regenerate eval/program/trust_statement.md from live ops + registry",
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
    generate.add_argument(
        "--baseline-report",
        type=Path,
        default=_DEFAULT_BASELINE_REPORT,
        help=f"M1 baseline JSON for epoch context (default: {_DEFAULT_BASELINE_REPORT})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "generate":
        execute = databricks_sql_executor(args.catalog)
        rows, epoch_context = generate_trust_statement(
            execute_sql=execute,
            catalog=args.catalog,
            registry_path=args.registry,
            baseline_report_path=args.baseline_report,
        )
        write_trust_statement(
            args.output,
            rows,
            catalog=args.catalog,
            epoch_context=epoch_context,
        )
        print(
            f"trust_statement: wrote {len(rows)} rows for "
            f"{len({r.company for r in rows})} companies -> {args.output}"
        )
        return 0
    raise TrustStatementGenerationError(f"unknown command: {args.command}")


if __name__ == "__main__":
    sys.exit(main())
