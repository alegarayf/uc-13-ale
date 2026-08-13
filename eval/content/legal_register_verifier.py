"""Rung-1 deterministic verifier for the ``legal_register`` surface (item 25 / §12.1)."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Protocol

from eval.content.s2_writer import S2ScoreRow, S2Writer, SqlExecutor, _sql_str
from eval.retrieval.companies import DEFAULT_COMPANY_DISPLAY, canonical_company_slug

logger = logging.getLogger(__name__)

SURFACE = "legal_register"
WRITER = "deterministic_verifier"
LEGAL_TABLE_SUFFIX = "analysis.legal"

REGISTER_COLUMNS: tuple[tuple[str, str], ...] = (
    ("contract_register_json", "contract_register"),
    ("vendor_register_json", "vendor_register"),
    ("platform_dependency_register_json", "platform_dependency_register"),
    ("employment_register_json", "employment_register"),
    ("litigation_register_json", "litigation_register"),
    ("privacy_security_register_json", "privacy_security_register"),
    ("ip_register_json", "ip_register"),
    ("insurance_register_json", "insurance_register"),
    ("coc_consent_list_json", "coc_consent_list"),
    ("termination_exposure_json", "termination_exposure"),
    ("restrictive_covenant_map_json", "restrictive_covenant_map"),
    ("unable_to_assess_json", "unable_to_assess"),
    ("recommended_diligence_json", "recommended_diligence"),
)

_PAGE_RE = re.compile(r"(?:page|p\.?)\s*(\d+)", re.IGNORECASE)
_SECTION_PREFIX_RE = re.compile(r"^section:\s*", re.IGNORECASE)


@dataclass(frozen=True)
class ChunkResolution:
    """Corpus chunk matched from register traceability fields."""

    chunk_id: str
    chunk_text: str
    page_start: int | None
    section_header: str | None


ChunkResolver = Callable[[str, str, str], ChunkResolution | None]
DocumentChunkEnumerator = Callable[[str], list[ChunkResolution]]


class LegalRowLoader(Protocol):
    """Load the latest ``analysis.legal`` row for a company display name."""

    def __call__(self, company_display: str) -> dict[str, Any]: ...


def _utc_now_micro() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_quote(text: str) -> str:
    """Whitespace fold, case fold, and hyphenation de-break for quote matching."""
    folded = str(text or "").casefold()
    folded = folded.replace("\u00ad", "")
    folded = re.sub(r"(\w)-\s+(\w)", r"\1\2", folded)
    return re.sub(r"\s+", " ", folded.strip())


def _quote_supported_by_chunk(quote: str, chunk_text: str) -> bool:
    """Deterministic full-quote containment after normalization."""
    normalized_quote = _normalize_quote(quote)
    normalized_chunk = _normalize_quote(chunk_text)
    if not normalized_quote or not normalized_chunk:
        return False
    return normalized_quote in normalized_chunk


def _quote_prefix_anchor_in_chunk(quote: str, chunk_text: str) -> bool:
    """True when the opening six-word anchor matches but the full quote does not."""
    normalized_quote = _normalize_quote(quote)
    normalized_chunk = _normalize_quote(chunk_text)
    words = normalized_quote.split()
    if len(words) <= 6 or not normalized_chunk:
        return False
    anchor = " ".join(words[:6])
    return anchor in normalized_chunk and normalized_quote not in normalized_chunk


def _parse_page_from_location(location: str | None) -> int | None:
    if not location:
        return None
    match = _PAGE_RE.search(location)
    if match:
        return int(match.group(1))
    return None


def _section_value_from_location(location: str | None) -> str | None:
    if not location:
        return None
    text = location.strip()
    if not text:
        return None
    if ";" in text:
        text = text.split(";", 1)[0].strip()
    text = _SECTION_PREFIX_RE.sub("", text).strip()
    return text or None


def _derive_locator(*, chunk: ChunkResolution) -> tuple[str | None, str | None]:
    """§8.8 HALT-31: locator derived from the cited chunk only (section > page > null)."""
    if chunk.section_header:
        return "section", chunk.section_header
    if chunk.page_start is not None:
        return "page", str(chunk.page_start)
    return None, None


def _claim_id(register_name: str, index: int) -> str:
    return f"legal.{register_name}.{index:04d}"


def _verdict_and_citation(
    *,
    primary_chunk: ChunkResolution | None,
    raw_quote: str,
    source_doc: str,
    enumerate_document_chunks: DocumentChunkEnumerator | None,
) -> tuple[str, ChunkResolution | None]:
    """Map quote evidence to §16 verdict and the chunk that carries the citation."""
    if primary_chunk is None:
        return "unsupported", None

    chunks: list[ChunkResolution] = [primary_chunk]
    if enumerate_document_chunks is not None:
        seen = {primary_chunk.chunk_id}
        for candidate in enumerate_document_chunks(source_doc):
            if candidate.chunk_id not in seen:
                chunks.append(candidate)
                seen.add(candidate.chunk_id)

    for chunk in chunks:
        if _quote_supported_by_chunk(raw_quote, chunk.chunk_text):
            return "supported", chunk

    for chunk in chunks:
        if _quote_prefix_anchor_in_chunk(raw_quote, chunk.chunk_text):
            return "contradicted", primary_chunk

    return "unsupported", primary_chunk


def _parse_register_list(raw: Any, *, register_name: str) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, str):
        if not raw.strip():
            return []
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"invalid JSON in register {register_name!r}: {exc}"
            ) from exc
    else:
        parsed = raw
    if not isinstance(parsed, list):
        raise ValueError(
            f"register {register_name!r} must be a JSON array, got {type(parsed).__name__}"
        )
    rows: list[dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            # e.g. ``unable_to_assess`` carries display-name strings, not traceable rows.
            continue
        rows.append(item)
    return rows


def _registers_from_legal_row(legal_row: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    registers: dict[str, list[dict[str, Any]]] = {}
    for column, register_name in REGISTER_COLUMNS:
        registers[register_name] = _parse_register_list(
            legal_row.get(column),
            register_name=register_name,
        )
    return registers


def build_claim_rows(
    company: str,
    *,
    registers: Mapping[str, list[dict[str, Any]]],
    run_id: str,
    run_ts: datetime,
    resolve_chunk: ChunkResolver,
    enumerate_document_chunks: DocumentChunkEnumerator | None = None,
) -> list[S2ScoreRow]:
    """Translate verifiable register rows into §8.8 claim rows."""
    slug = canonical_company_slug(company) if " " in company else company
    rows: list[S2ScoreRow] = []

    for register_name, register_rows in registers.items():
        if not isinstance(register_rows, list):
            raise ValueError(
                f"register {register_name!r} must be a list, got {type(register_rows).__name__}"
            )
        for index, record in enumerate(register_rows):
            if not isinstance(record, dict):
                continue
            source_doc = str(record.get("source_doc") or "").strip()
            if not source_doc:
                continue

            source_location = str(record.get("source_location") or "").strip()
            raw_quote = str(record.get("raw_quote") or "").strip()
            primary_chunk = resolve_chunk(source_doc, source_location, raw_quote)
            verdict, cited_chunk = _verdict_and_citation(
                primary_chunk=primary_chunk,
                raw_quote=raw_quote,
                source_doc=source_doc,
                enumerate_document_chunks=enumerate_document_chunks,
            )

            cited_chunk_id: str | None = None
            cited_locator_kind: str | None = None
            cited_locator_value: str | None = None
            if cited_chunk is not None:
                cited_chunk_id = cited_chunk.chunk_id
                cited_locator_kind, cited_locator_value = _derive_locator(
                    chunk=cited_chunk,
                )

            rows.append(
                S2ScoreRow(
                    company=slug,
                    surface=SURFACE,
                    run_id=run_id,
                    run_ts=run_ts,
                    row_type="claim",
                    claim_id=_claim_id(register_name, index),
                    verdict=verdict,
                    rationale=None,
                    writer=None,
                    asserted_magnitude=None,
                    asserted_unit=None,
                    extracted_magnitude=None,
                    extracted_unit=None,
                    cited_chunk_id=cited_chunk_id,
                    cited_locator_kind=cited_locator_kind,
                    cited_locator_value=cited_locator_value,
                    judge_verdict_advisory=None,
                )
            )

    return rows


def _display_name_for_slug(slug: str) -> str:
    if slug == canonical_company_slug(DEFAULT_COMPANY_DISPLAY):
        return DEFAULT_COMPANY_DISPLAY
    return slug.replace("_", " ").title()


def make_warehouse_chunk_resolver(
    *,
    catalog: str,
    company_display: str,
    sql_executor: SqlExecutor,
) -> ChunkResolver:
    """Resolve ``source_doc``/``source_location`` against ``ingestion.chunks``."""

    company_lit = f"'{_sql_str(company_display)}'"

    def resolve(source_doc: str, source_location: str, _raw_quote: str) -> ChunkResolution | None:
        doc_lit = f"'{_sql_str(source_doc)}'"
        doc_suffix = source_doc[-40:] if len(source_doc) > 40 else source_doc
        suffix_lit = f"'{_sql_str('%' + doc_suffix + '%')}'"
        page = _parse_page_from_location(source_location)
        section_pattern = _section_value_from_location(source_location)
        page_clause = f"AND c.page_start = {page}" if page is not None else ""
        section_clause = ""
        if section_pattern:
            section_lit = f"'{_sql_str('%' + section_pattern[:80] + '%')}'"
            section_clause = f"AND c.section_header ILIKE {section_lit}"

        query = f"""
            SELECT c.chunk_id, c.chunk_text, c.page_start, c.section_header
            FROM {catalog}.ingestion.chunks c
            WHERE c.company_name = {company_lit}
              AND (c.file_name = {doc_lit} OR c.file_name ILIKE {suffix_lit})
              {page_clause}
              {section_clause}
            ORDER BY c.page_start NULLS LAST, c.chunk_id
            LIMIT 1
        """
        result = sql_executor(query)
        if not result:
            return None
        row = result[0]
        return _chunk_row_to_resolution(row)

    return resolve


def _chunk_row_to_resolution(row: list[Any]) -> ChunkResolution | None:
    chunk_id = str(row[0]) if row[0] is not None else ""
    if not chunk_id:
        return None
    chunk_text = str(row[1] or "")
    page_start = int(row[2]) if row[2] is not None else None
    section_header = str(row[3]) if row[3] is not None else None
    return ChunkResolution(
        chunk_id=chunk_id,
        chunk_text=chunk_text,
        page_start=page_start,
        section_header=section_header or None,
    )


def make_warehouse_document_chunks_enumerator(
    *,
    catalog: str,
    company_display: str,
    sql_executor: SqlExecutor,
) -> DocumentChunkEnumerator:
    """Return all corpus chunks for a register ``source_doc`` (sibling search)."""

    company_lit = f"'{_sql_str(company_display)}'"

    def enumerate(source_doc: str) -> list[ChunkResolution]:
        doc_lit = f"'{_sql_str(source_doc)}'"
        doc_suffix = source_doc[-40:] if len(source_doc) > 40 else source_doc
        suffix_lit = f"'{_sql_str('%' + doc_suffix + '%')}'"
        query = f"""
            SELECT c.chunk_id, c.chunk_text, c.page_start, c.section_header
            FROM {catalog}.ingestion.chunks c
            WHERE c.company_name = {company_lit}
              AND (c.file_name = {doc_lit} OR c.file_name ILIKE {suffix_lit})
            ORDER BY c.page_start NULLS LAST, c.chunk_id
        """
        result = sql_executor(query)
        chunks: list[ChunkResolution] = []
        for row in result:
            resolution = _chunk_row_to_resolution(row)
            if resolution is not None:
                chunks.append(resolution)
        return chunks

    return enumerate


def make_warehouse_chunk_id_resolver(
    *,
    catalog: str,
    sql_executor: SqlExecutor,
) -> Callable[[frozenset[str]], frozenset[str]]:
    """Batch-resolve cited chunk ids against ``ingestion.chunks`` (S-61 guard)."""

    def resolve(chunk_ids: frozenset[str]) -> frozenset[str]:
        if not chunk_ids:
            return frozenset()
        id_literals = ", ".join(f"'{_sql_str(cid)}'" for cid in sorted(chunk_ids))
        query = f"""
            SELECT chunk_id
            FROM {catalog}.ingestion.chunks
            WHERE chunk_id IN ({id_literals})
        """
        result = sql_executor(query)
        return frozenset(str(row[0]) for row in result if row and row[0] is not None)

    return resolve


def make_warehouse_legal_row_loader(
    *,
    catalog: str,
    sql_executor: SqlExecutor,
) -> LegalRowLoader:
    columns = ", ".join(column for column, _ in REGISTER_COLUMNS)

    def load(company_display: str) -> dict[str, Any]:
        query = f"""
            SELECT {columns}, created_at
            FROM {catalog}.{LEGAL_TABLE_SUFFIX}
            WHERE company_name = '{_sql_str(company_display)}'
            ORDER BY created_at DESC
            LIMIT 1
        """
        result = sql_executor(query)
        if not result:
            raise ValueError(
                f"no legal analysis row for company {company_display!r}"
            )
        payload: dict[str, Any] = {}
        for idx, (column, _) in enumerate(REGISTER_COLUMNS):
            payload[column] = result[0][idx]
        payload["created_at"] = result[0][-1]
        return payload

    return load


def verify_legal_register(
    company: str,
    run_id: str,
    *,
    catalog: str = "uc13_ale",
    run_ts: datetime | None = None,
    sql_executor: SqlExecutor | None = None,
    legal_row_loader: LegalRowLoader | None = None,
    chunk_resolver: ChunkResolver | None = None,
    document_chunks_enumerator: DocumentChunkEnumerator | None = None,
) -> int:
    """Run the whole-surface verifier: claim rows then completion marker."""
    if sql_executor is None and (legal_row_loader is None or chunk_resolver is None):
        raise RuntimeError("sql_executor or injected loaders are required")

    slug = canonical_company_slug(company) if " " in company else company
    ts = run_ts or _utc_now_micro()
    display = _display_name_for_slug(slug)

    loader = legal_row_loader
    resolver = chunk_resolver
    enumerator = document_chunks_enumerator
    if loader is None or resolver is None:
        assert sql_executor is not None
        loader = loader or make_warehouse_legal_row_loader(
            catalog=catalog, sql_executor=sql_executor
        )
        resolver = resolver or make_warehouse_chunk_resolver(
            catalog=catalog,
            company_display=display,
            sql_executor=sql_executor,
        )
        enumerator = enumerator or make_warehouse_document_chunks_enumerator(
            catalog=catalog,
            company_display=display,
            sql_executor=sql_executor,
        )

    legal_row = loader(display)
    registers = _registers_from_legal_row(legal_row)
    claim_rows = build_claim_rows(
        slug,
        registers=registers,
        run_id=run_id,
        run_ts=ts,
        resolve_chunk=resolver,
        enumerate_document_chunks=enumerator,
    )

    chunk_id_resolver = None
    if sql_executor is not None:
        chunk_id_resolver = make_warehouse_chunk_id_resolver(
            catalog=catalog,
            sql_executor=sql_executor,
        )

    writer = S2Writer(catalog=catalog, sql_executor=sql_executor)
    writer.write_claims(
        slug,
        SURFACE,
        run_id,
        ts,
        claim_rows,
        chunk_id_resolver=chunk_id_resolver,
    )
    writer.write_completion_marker(slug, SURFACE, run_id, ts, WRITER)

    logger.info(
        "legal_register_verify_complete",
        extra={
            "event": "legal_register_verify_complete",
            "company": slug,
            "surface": SURFACE,
            "run_id": run_id,
            "n_claims": len(claim_rows),
        },
    )
    return len(claim_rows)
