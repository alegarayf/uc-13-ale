"""Rung-3 human spot-check tooling — spec §12.1 rung 3 / item 26."""

from __future__ import annotations

import json
import logging
import re
import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml

from eval.content.legal_register_verifier import (
    ChunkResolution,
    derive_locator,
    make_warehouse_chunk_id_resolver,
    parse_page_from_location,
    section_value_from_location,
)
from eval.content.s2_writer import (
    CLAIM_VERDICTS,
    ChunkIdResolver,
    S2ScoreRow,
    S2Writer,
    SqlExecutor,
    SURFACES,
    _sql_str,
)
from eval.retrieval.companies import canonical_company_slug

logger = logging.getLogger(__name__)

DEFAULT_REGISTRY_PATH = Path("eval/program/registry.yaml")
HUMAN_WRITER = "human_spot_check"
MVP_SURFACES = frozenset({"exec_summary", "fta_numeric", "legal_register"})
RUNG_ASSIGNMENT_ITEMS = ("CHK-23a", "CHK-26a")

MANIFEST_PATHS: dict[str, str] = {
    "exec_summary": "eval/content/exec_summary_rubric_claims.json",
    "fta_numeric": "eval/content/fta_numeric_rubric_claims.json",
}

_FTA_CLAIM_RE = re.compile(
    r"^(?P<field>[a-z_][a-z0-9_]*):\s*(?P<value>.+?)(?P<pct>%)?$",
    re.IGNORECASE,
)

# M2 audit D2 / m3_backlog #3: broken vision-extraction placeholder → sibling chunk.
BROKEN_CHUNK_ID = "aee7745d-e270-4abf-8fc5-c60dd4f13bcc"
SIBLING_CHUNK_ID = "2d238ee0-4136-4818-bb18-201b82990479"
LOCATION_CHUNK_OVERRIDE: dict[str, str] = {
    "Pro Forma Income Statement & Projection": SIBLING_CHUNK_ID,
}

@dataclass(frozen=True)
class SpotCheckConfig:
    """Typed configuration for rung-3 spot-check prepare/ingest."""

    company: str
    surface: str
    source: str
    output_dir: Path
    verdicts_path: Path
    operator_id: str
    catalog: str = "uc13_ale"
    registry_path: Path = DEFAULT_REGISTRY_PATH
    repo_root: Path | None = None

    def __post_init__(self) -> None:
        if self.surface not in SURFACES:
            raise ValueError(f"surface {self.surface!r} not in §16 vocabulary")
        if self.surface not in MANIFEST_PATHS:
            raise ValueError(
                f"surface {self.surface!r} has no committed claim manifest for spot-check"
            )
        object.__setattr__(self, "output_dir", Path(self.output_dir))
        object.__setattr__(self, "verdicts_path", Path(self.verdicts_path))
        object.__setattr__(self, "registry_path", Path(self.registry_path))
        if self.repo_root is not None:
            object.__setattr__(self, "repo_root", Path(self.repo_root))


@dataclass(frozen=True)
class SpotCheckClaim:
    claim_id: str
    claim_text: str
    section: str | None = None
    source_ref: str | None = None
    source_doc: str | None = None
    source_location: str | None = None
    cited_chunk_id: str | None = None
    cited_locator_kind: str | None = None
    cited_locator_value: str | None = None
    asserted_magnitude: Decimal | None = None
    asserted_unit: str | None = None
    chunk_text: str | None = None


@dataclass(frozen=True)
class SpotCheckPrepareResult:
    company_slug: str
    claim_count: int
    packet_path: Path
    claims: tuple[SpotCheckClaim, ...]


@dataclass(frozen=True)
class SpotCheckWriteResult:
    run_id: str
    run_ts: datetime
    claim_count: int


class SpotCheckIngestionError(ValueError):
    """Fail-closed ingestion with a counted error report."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(
            f"{len(errors)} spot-check ingestion error(s): " + "; ".join(errors)
        )


def _repo_root(config: SpotCheckConfig) -> Path:
    if config.repo_root is not None:
        return config.repo_root
    return Path(__file__).resolve().parents[2]


def _load_registry_assignments(registry_path: Path) -> dict[str, str]:
    if not registry_path.is_file():
        raise FileNotFoundError(f"registry not found: {registry_path}")
    payload = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    merged: dict[str, str] = {}
    for item in payload.get("items", []):
        if item.get("id") not in RUNG_ASSIGNMENT_ITEMS:
            continue
        for surface, rung in (item.get("rung_assignments") or {}).items():
            merged[surface] = rung
    return merged


def _assert_human_spot_check_allowed(surface: str, registry_path: Path) -> None:
    assignments = _load_registry_assignments(registry_path)
    for mvp_surface, rung in assignments.items():
        if mvp_surface in MVP_SURFACES and rung == "judge":
            raise ValueError(
                f"registry records rung-2 (judge) assignment for {mvp_surface!r}; "
                "spot-check tooling requires human-only MVP surfaces"
            )
    assigned = assignments.get(surface)
    if assigned != "human":
        raise ValueError(
            f"surface {surface!r} registry rung assignment is {assigned!r}, "
            "expected 'human' for rung-3 spot-check"
        )


def _manifest_path(config: SpotCheckConfig) -> Path:
    return _repo_root(config) / MANIFEST_PATHS[config.surface]


def _parse_fta_claim_text(claim_text: str) -> tuple[Decimal | None, str | None]:
    match = _FTA_CLAIM_RE.match(claim_text.strip())
    if not match:
        return None, None
    raw_value = match.group("value").replace(",", "").strip()
    field = match.group("field").lower()
    try:
        magnitude = Decimal(raw_value)
    except InvalidOperation:
        return None, None
    if match.group("pct") or field.endswith("_pct") or "pct" in field:
        return magnitude, "percent"
    return magnitude, None


@dataclass(frozen=True)
class ChunkRecord:
    chunk_id: str
    file_name: str
    section_header: str | None
    page_start: int | None
    chunk_text: str


class ChunkIndex:
    """In-memory index over ``ingestion.chunks`` for direct citation lookup."""

    def __init__(
        self,
        records: list[ChunkRecord],
        *,
        sql_executor: SqlExecutor | None = None,
        catalog: str | None = None,
        company: str | None = None,
    ) -> None:
        self._by_id = {r.chunk_id: r for r in records}
        self._by_file: dict[str, list[ChunkRecord]] = {}
        for rec in records:
            self._by_file.setdefault(rec.file_name, []).append(rec)
        self._sql_executor = sql_executor
        self._catalog = catalog
        self._company = company

    @classmethod
    def from_sql(
        cls,
        sql_executor: SqlExecutor,
        *,
        catalog: str,
        company: str,
    ) -> ChunkIndex:
        rows = sql_executor(
            f"""
            SELECT chunk_id, file_name, section_header, page_start,
                   CAST(NULL AS STRING) AS chunk_text
            FROM {catalog}.ingestion.chunks
            WHERE company_name = '{_sql_str(company)}'
            """
        )
        records = [
            ChunkRecord(
                chunk_id=str(row[0]),
                file_name=str(row[1] or ""),
                section_header=str(row[2]) if row[2] is not None else None,
                page_start=int(row[3]) if row[3] is not None else None,
                chunk_text=str(row[4] or ""),
            )
            for row in (rows or [])
            if row and row[0]
        ]
        return cls(
            records,
            sql_executor=sql_executor,
            catalog=catalog,
            company=company,
        )

    def fetch_text(self, chunk_ids: frozenset[str]) -> dict[str, str]:
        """Load full ``chunk_text`` for resolved ids; bulk ``from_sql`` stays metadata-only."""
        if not chunk_ids or self._sql_executor is None:
            return {}
        if not self._catalog or not self._company:
            return {}
        in_list = ", ".join(f"'{_sql_str(cid)}'" for cid in sorted(chunk_ids))
        rows = self._sql_executor(
            f"""
            SELECT chunk_id, chunk_text
            FROM {self._catalog}.ingestion.chunks
            WHERE company_name = '{_sql_str(self._company)}'
              AND chunk_id IN ({in_list})
            """
        )
        fetched: dict[str, str] = {}
        for row in rows or []:
            if not row or not row[0]:
                continue
            cid = str(row[0])
            text = str(row[1] or "")
            fetched[cid] = text
            existing = self._by_id.get(cid)
            if existing is None:
                continue
            updated = replace(existing, chunk_text=text)
            self._by_id[cid] = updated
            file_recs = self._by_file.get(updated.file_name)
            if file_recs is None:
                continue
            for idx, rec in enumerate(file_recs):
                if rec.chunk_id == cid:
                    file_recs[idx] = updated
                    break
        return fetched

    def exists(self, chunk_id: str) -> bool:
        return chunk_id in self._by_id

    def resolve_ids(self, chunk_ids: frozenset[str]) -> frozenset[str]:
        return frozenset(cid for cid in chunk_ids if self.exists(cid))

    def record(self, chunk_id: str) -> ChunkRecord | None:
        return self._by_id.get(chunk_id)

    def lookup(self, source_doc: str, source_location: str | None) -> ChunkResolution | None:
        if not source_doc:
            return None

        override_id = None
        if source_location and source_location in LOCATION_CHUNK_OVERRIDE:
            override_id = LOCATION_CHUNK_OVERRIDE[source_location]

        if override_id and override_id in self._by_id:
            rec = self._by_id[override_id]
            return ChunkResolution(
                chunk_id=rec.chunk_id,
                chunk_text=rec.chunk_text,
                page_start=rec.page_start,
                section_header=rec.section_header,
            )

        candidates = self._candidates_for_doc(source_doc)
        if not candidates:
            return None

        page = parse_page_from_location(source_location)
        section_pattern = section_value_from_location(source_location)

        scored: list[tuple[int, ChunkRecord]] = []
        for rec in candidates:
            score = 0
            if page is not None and rec.page_start == page:
                score += 2
            if section_pattern and rec.section_header:
                if section_pattern.lower() in rec.section_header.lower():
                    score += 3
            if source_location and rec.section_header:
                if source_location.lower() in rec.section_header.lower():
                    score += 2
            if score > 0:
                scored.append((score, rec))

        if scored:
            scored.sort(key=lambda t: (-t[0], t[1].page_start or 0, t[1].chunk_id))
            rec = scored[0][1]
        elif len(candidates) == 1:
            rec = candidates[0]
        else:
            return None

        return ChunkResolution(
            chunk_id=rec.chunk_id,
            chunk_text=rec.chunk_text,
            page_start=rec.page_start,
            section_header=rec.section_header,
        )

    def _candidates_for_doc(self, source_doc: str) -> list[ChunkRecord]:
        if source_doc in self._by_file:
            return list(self._by_file[source_doc])
        suffix = source_doc[-40:] if len(source_doc) > 40 else source_doc
        out: list[ChunkRecord] = []
        for fname, recs in self._by_file.items():
            if fname.endswith(suffix) or suffix in fname:
                out.extend(recs)
        return out


def load_exec_analysis_cache(
    sql_executor: SqlExecutor,
    *,
    catalog: str,
    company: str,
) -> dict[str, Any]:
    """Fetch latest analysis rows used for exec_summary citation resolution."""

    def _json_col(table: str, column: str) -> Any:
        rows = sql_executor(
            f"""
            SELECT CAST({column} AS STRING)
            FROM {catalog}.analysis.{table}
            WHERE company_name = '{_sql_str(company)}'
            ORDER BY created_at DESC LIMIT 1
            """
        )
        if not rows or rows[0][0] is None:
            return None
        return json.loads(rows[0][0])

    def _scalar_col(table: str, column: str) -> Any:
        rows = sql_executor(
            f"""
            SELECT CAST({column} AS STRING)
            FROM {catalog}.analysis.{table}
            WHERE company_name = '{_sql_str(company)}'
            ORDER BY created_at DESC LIMIT 1
            """
        )
        return rows[0][0] if rows else None

    return {
        "revenue_trend_json": _json_col("financial_trends", "revenue_trend_json") or [],
        "ebitda_json": _json_col("financial_trends", "ebitda_json") or [],
        "addback_pct_of_ebitda": _scalar_col("financial_trends", "addback_pct_of_ebitda"),
        "addback_ledger_json": _json_col("quality_of_earnings", "addback_ledger_json") or [],
        "tier4_addback_count": _scalar_col("quality_of_earnings", "tier4_addback_count"),
        "ebitda_scenarios_json": _json_col("quality_of_earnings", "ebitda_scenarios_json") or {},
        "qofe_report_present": _scalar_col("quality_of_earnings", "qofe_report_present"),
        "healthcare_kpis_json": _json_col("kpi", "healthcare_kpis_json") or {},
        "compliance_incidents": _json_col("kpi", "healthcare_kpis_json"),
        "customer_operational_metrics_json": _json_col(
            "business_model", "customer_operational_metrics_json"
        )
        or {},
        "top_10_issues_json": _json_col("diligence_report", "top_10_issues_json") or [],
        "reconciliation_summary_json": _json_col(
            "diligence_report", "reconciliation_summary_json"
        )
        or {},
        "section_ratings_json": _json_col("diligence_report", "section_ratings_json") or {},
        "section_confidence_json": _json_col(
            "diligence_report", "section_confidence_json"
        )
        or {},
        "forecast_assumptions_json": _json_col("forecast", "forecast_assumptions_json") or {},
        "credibility_summary_json": _json_col("forecast", "credibility_summary_json") or {},
    }


def _fta_row_source(
    rows: list[dict[str, Any]], *, location_contains: str
) -> tuple[str | None, str | None]:
    for row in rows:
        loc = str(row.get("source_location") or "")
        if location_contains.lower() in loc.lower():
            return str(row.get("source_doc") or "") or None, loc or None
    return None, None


def _qoe_item_source(
    ledger: list[dict[str, Any]], letter: str
) -> tuple[str | None, str | None]:
    tag = f"[{letter.upper()}]"
    for row in ledger:
        desc = str(row.get("description") or "")
        if desc.startswith(tag) or f" {tag}" in desc:
            doc = str(row.get("source_doc") or "") or None
            loc = str(row.get("source_location") or "") or None
            if doc:
                return doc, loc
    return None, None


def _first_source(
    *pairs: tuple[str | None, str | None],
) -> tuple[str | None, str | None]:
    for doc, loc in pairs:
        if doc:
            return doc, loc
    return None, None


def _top10_source(
    issues: list[dict[str, Any]], rank: int
) -> tuple[str | None, str | None]:
    for issue in issues:
        if int(issue.get("rank") or 0) == rank:
            citations = issue.get("citations") or []
            if citations:
                return str(citations[0]), None
    return None, None


# Cache-free locators for the exec_summary truncation row (008/009/010/018). Used only
# when exec_analysis_cache is None so the FTA/analysis citation path stays unchanged.
_CACHE_FREE_TRUNCATION_SOURCES: dict[str, tuple[str, str]] = {
    "exec.claim.008": (
        "2024 Elder Care - CIM_vF.pdf",
        "Pro Forma Income Statement & Projection",
    ),
    "exec.claim.009": (
        "2024 Elder Care - CIM_vF.pdf",
        "Diligence Adjusted Income Statement",
    ),
    "exec.claim.010": (
        "2024 Elder Care - CIM_vF.pdf",
        "EBITDA Adjustment Detail",
    ),
    "exec.claim.018": (
        "2024 Elder Care - CIM_vF.pdf",
        "Pro Forma Income Statement & Projection",
    ),
}

_ELDER_CARE_STATIC_CLAIM_SOURCES: dict[str, tuple[str, str | None]] = {
    "exec.claim.001": ("2024 Elder Care - CIM_vF.pdf", "Elder Care by the Numbers"),
    "exec.claim.002": ("GL_0125-0325.xlsx", None),
    "exec.claim.003": ("Company KPI Dashboard SAMPLE.xlsx", "Census or Patient Panel"),
    "exec.claim.004": ("Company KPI Dashboard SAMPLE.xlsx", "Caregiver Headcount"),
    "exec.claim.005": ("2024 Elder Care - CIM_vF.pdf", "Corporate Functions"),
    "exec.claim.006": ("2024 Elder Care - CIM_vF.pdf", "Key Entity Metrics"),
    "exec.claim.011": ("2024 Elder Care - CIM_vF.pdf", "EBITDA Adjustment Detail"),
    "exec.claim.013": ("2024 Elder Care - CIM_vF.pdf", "EBITDA Adjustment Detail"),
    "exec.claim.031": ("2024 Elder Care - CIM_vF.pdf", "EBITDA Adjustment Detail"),
    "exec.claim.034": ("2024 Elder Care - CIM_vF.pdf", "EBITDA Adjustment Detail"),
    "exec.claim.020": (
        "Elder Care - Diligence Workbook - vSHARE_6.19.25.xlsx",
        "Q&A",
    ),
    "exec.claim.023": (
        "April 30 2025 Fully Executed Retainer Agreement for Collection Efforts by Peter Ackerman Esq.pdf",
        None,
    ),
    "exec.claim.024": ("Manhattan_Lease_0424.pdf", "Section 11"),
    "exec.claim.028": (
        "Project Orange Engagement Letter - May 1, 2025.pdf",
        None,
    ),
    "exec.claim.029": ("2024 Elder Care - CIM_vF.pdf", "Services Overview"),
    "exec.claim.030": ("2024 Elder Care - CIM_vF.pdf", "MD&A"),
    "exec.claim.037": ("2024 Elder Care - CIM_vF.pdf", "Growth Strategy"),
}

_EXEC_TOP10_RANK_MAP: dict[str, int] = {
    "exec.claim.021": 3,
    "exec.claim.022": 4,
    "exec.claim.035": 2,
    "exec.claim.036": 5,
    "exec.claim.038": 1,
    "exec.claim.039": 3,
    "exec.claim.040": 4,
    "exec.claim.041": 1,
    "exec.claim.042": 6,
    "exec.claim.043": 7,
    "exec.claim.044": 8,
    "exec.claim.045": 10,
    "exec.claim.048": 1,
    "exec.claim.049": 3,
    "exec.claim.050": 6,
    "exec.claim.051": 7,
    "exec.claim.052": 9,
    "exec.claim.053": 10,
}


def _forecast_assumption_source(
    forecast_rows: list[dict[str, Any]] | dict[str, Any],
) -> tuple[str | None, str | None]:
    rows = forecast_rows if isinstance(forecast_rows, list) else []
    for row in rows:
        doc = str(row.get("source_doc") or "") or None
        loc = str(row.get("source_location") or "") or None
        if doc:
            return doc, loc
    return None, None


def _exec_claim_source_from_cache(
    claim_id: str,
    cache: dict[str, Any],
    *,
    elder_care_fallbacks: bool,
) -> tuple[str | None, str | None]:
    """Resolve exec_summary claim sources from ``load_exec_analysis_cache`` payload."""

    revenue = cache.get("revenue_trend_json") or []
    ledger = cache.get("addback_ledger_json") or []
    top10 = cache.get("top_10_issues_json") or []
    forecast = cache.get("forecast_assumptions_json") or []

    if claim_id in {
        "exec.claim.007",
        "exec.claim.008",
        "exec.claim.009",
        "exec.claim.010",
        "exec.claim.012",
    }:
        return _fta_row_source(revenue, location_contains="Historical P&L Summary")
    if claim_id in {"exec.claim.011", "exec.claim.013", "exec.claim.031", "exec.claim.034"}:
        elder_fallback = (
            ("2024 Elder Care - CIM_vF.pdf", "EBITDA Adjustment Detail")
            if elder_care_fallbacks
            else (None, None)
        )
        return _first_source(elder_fallback, _top10_source(top10, 1))
    if claim_id == "exec.claim.014":
        return _qoe_item_source(ledger, "G")
    if claim_id == "exec.claim.015":
        return _qoe_item_source(ledger, "K")
    if claim_id == "exec.claim.016":
        return _qoe_item_source(ledger, "O")
    if claim_id == "exec.claim.017":
        if elder_care_fallbacks:
            return ("2024 Elder Care - CIM_vF.pdf", "Historical P&L Summary, Page 49")
        return _fta_row_source(revenue, location_contains="Historical P&L Summary")
    if claim_id == "exec.claim.018":
        if elder_care_fallbacks:
            return ("Elder Care Projection Model_vUPLOAD.xlsx", "Forecast Assumptions")
        return _forecast_assumption_source(forecast)
    if claim_id in {
        "exec.claim.019",
        "exec.claim.046",
        "exec.claim.047",
        "exec.claim.026",
        "exec.claim.025",
    }:
        if elder_care_fallbacks:
            return ("2024 Elder Care - CIM_vF.pdf", "Executive Summary")
        return (None, None)
    if claim_id == "exec.claim.032":
        return _qoe_item_source(ledger, "D")
    if claim_id == "exec.claim.033":
        return _qoe_item_source(ledger, "N")
    if claim_id in _EXEC_TOP10_RANK_MAP:
        return _top10_source(top10, _EXEC_TOP10_RANK_MAP[claim_id])
    if claim_id == "exec.claim.027":
        return (None, None)
    return (None, None)


def exec_claim_source(
    claim_id: str,
    cache: dict[str, Any],
    *,
    company_slug: str,
) -> tuple[str | None, str | None]:
    """Map exec_summary claim_id → (source_doc, source_location) from analysis artifacts."""

    if company_slug == "elder_care" and claim_id in _ELDER_CARE_STATIC_CLAIM_SOURCES:
        return _ELDER_CARE_STATIC_CLAIM_SOURCES[claim_id]

    return _exec_claim_source_from_cache(
        claim_id,
        cache,
        elder_care_fallbacks=(company_slug == "elder_care"),
    )


def _resolve_chunk_for_entry(
    *,
    chunk_index: ChunkIndex,
    source_doc: str | None,
    source_location: str | None,
) -> ChunkResolution | None:
    if source_doc:
        return chunk_index.lookup(str(source_doc), source_location)
    return None


def _claim_from_manifest_entry(
    surface: str,
    source: str,
    entry: dict[str, Any],
    *,
    company_slug: str,
    chunk_index: ChunkIndex | None = None,
    exec_analysis_cache: dict[str, Any] | None = None,
) -> SpotCheckClaim:
    claim_id = entry["claim_id"]
    claim_text = entry["claim_text"]
    section = entry.get("section")
    source_doc = entry.get("source_doc")
    source_location = entry.get("source_location")

    if surface == "exec_summary" and exec_analysis_cache is not None:
        derived_doc, derived_loc = exec_claim_source(
            claim_id,
            exec_analysis_cache,
            company_slug=company_slug,
        )
        if derived_doc:
            source_doc = derived_doc
            source_location = derived_loc
    elif (
        surface == "exec_summary"
        and exec_analysis_cache is None
        and chunk_index is not None
        and company_slug == "elder_care"
        and claim_id in _CACHE_FREE_TRUNCATION_SOURCES
    ):
        source_doc, source_location = _CACHE_FREE_TRUNCATION_SOURCES[claim_id]

    source_ref: str | None
    if source_doc and source_location:
        source_ref = f"source://{source_doc}#{source_location}"
    elif section:
        source_ref = f"source://{source}#{section}"
    else:
        source_ref = f"source://{source}"

    cited_chunk_id: str | None = None
    cited_locator_kind: str | None = None
    cited_locator_value: str | None = None
    if chunk_index is not None:
        chunk = _resolve_chunk_for_entry(
            chunk_index=chunk_index,
            source_doc=source_doc,
            source_location=source_location,
        )
        if chunk is not None:
            cited_chunk_id = chunk.chunk_id
            cited_locator_kind, cited_locator_value = derive_locator(chunk=chunk)

    asserted_magnitude: Decimal | None = None
    asserted_unit: str | None = None
    if surface == "fta_numeric":
        asserted_magnitude, asserted_unit = _parse_fta_claim_text(claim_text)

    return SpotCheckClaim(
        claim_id=claim_id,
        claim_text=claim_text,
        section=section,
        source_ref=source_ref,
        source_doc=source_doc,
        source_location=source_location,
        cited_chunk_id=cited_chunk_id,
        cited_locator_kind=cited_locator_kind,
        cited_locator_value=cited_locator_value,
        asserted_magnitude=asserted_magnitude,
        asserted_unit=asserted_unit,
    )


def _attach_fetched_chunk_text(
    claims: list[SpotCheckClaim],
    chunk_index: ChunkIndex,
) -> list[SpotCheckClaim]:
    """Copy post-``fetch_text`` index text onto each resolved claim."""
    attached: list[SpotCheckClaim] = []
    for claim in claims:
        text: str | None = None
        if claim.cited_chunk_id:
            rec = chunk_index.record(claim.cited_chunk_id)
            if rec is not None and rec.chunk_text:
                text = rec.chunk_text
        attached.append(replace(claim, chunk_text=text))
    return attached


def load_claim_enumeration(
    config: SpotCheckConfig,
    *,
    chunk_index: ChunkIndex | None = None,
    exec_analysis_cache: dict[str, Any] | None = None,
) -> tuple[SpotCheckClaim, ...]:
    """Load the whole-surface claim set from the committed rubric manifest."""
    company_slug = canonical_company_slug(config.company)
    manifest_file = _manifest_path(config)
    payload = json.loads(manifest_file.read_text(encoding="utf-8"))
    claims = [
        _claim_from_manifest_entry(
            config.surface,
            config.source,
            entry,
            company_slug=company_slug,
            chunk_index=chunk_index,
            exec_analysis_cache=exec_analysis_cache,
        )
        for entry in payload["claims"]
    ]
    if not claims:
        raise ValueError(f"claim manifest {manifest_file} is empty")
    if chunk_index is not None:
        cited = frozenset(c.cited_chunk_id for c in claims if c.cited_chunk_id)
        if cited:
            chunk_index.fetch_text(cited)
        claims = _attach_fetched_chunk_text(claims, chunk_index)
    return tuple(claims)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _generate_run_id(ts: datetime | None = None) -> tuple[str, datetime]:
    run_ts = ts or _utc_now()
    suffix = secrets.token_hex(2)
    run_id = f"{run_ts.strftime('%Y%m%dT%H%M%S')}Z-{suffix}"
    return run_id, run_ts


def prepare_spot_check(
    config: SpotCheckConfig,
    *,
    chunk_index: ChunkIndex | None = None,
) -> SpotCheckPrepareResult:
    """Enumerate claims, validate registry guard-rail, write presentation packet YAML."""
    _assert_human_spot_check_allowed(config.surface, config.registry_path)
    company_slug = canonical_company_slug(config.company)
    claims = load_claim_enumeration(config, chunk_index=chunk_index)

    config.output_dir.mkdir(parents=True, exist_ok=True)
    packet_name = f"{config.surface}_{company_slug}_presentation.yaml"
    packet_path = config.output_dir / packet_name

    packet = {
        "schema_version": 1,
        "format": "spot_check_presentation_v1",
        "surface": config.surface,
        "company": config.company,
        "company_slug": company_slug,
        "source": config.source,
        "operator_id": config.operator_id,
        "prepared_at": _utc_now().isoformat(),
        "claim_count": len(claims),
        "claims": [
            {
                "claim_id": claim.claim_id,
                "section": claim.section,
                "claim_text": claim.claim_text,
                "source_ref": claim.source_ref,
                "source_doc": claim.source_doc,
                "source_location": claim.source_location,
                "cited_chunk_id": claim.cited_chunk_id,
                "cited_locator_kind": claim.cited_locator_kind,
                "cited_locator_value": claim.cited_locator_value,
                "chunk_text": claim.chunk_text,
                "verdict": None,
                "rationale": None,
            }
            for claim in claims
        ],
    }
    packet_path.write_text(
        yaml.safe_dump(packet, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    logger.info(
        "spot_check_prepared",
        extra={
            "event": "spot_check_prepared",
            "company": company_slug,
            "surface": config.surface,
            "run_id": "",
            "n_claims": len(claims),
        },
    )
    return SpotCheckPrepareResult(
        company_slug=company_slug,
        claim_count=len(claims),
        packet_path=packet_path,
        claims=claims,
    )


def _load_verdicts(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"verdicts file not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("verdicts file must be a YAML mapping")
    entries = payload.get("claims")
    if not isinstance(entries, list):
        raise ValueError("verdicts file must contain a claims list")
    by_id: dict[str, dict[str, Any]] = {}
    for entry in entries:
        claim_id = entry.get("claim_id")
        if not claim_id:
            raise ValueError("verdict entry missing claim_id")
        if claim_id in by_id:
            raise ValueError(f"duplicate verdict for claim_id {claim_id!r}")
        by_id[claim_id] = entry
    return by_id


def _validate_verdict_ingestion(
    claims: tuple[SpotCheckClaim, ...],
    verdicts_by_id: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    errors: list[str] = []
    expected_ids = {claim.claim_id for claim in claims}
    for claim_id in sorted(verdicts_by_id.keys() - expected_ids):
        errors.append(f"unknown claim_id {claim_id!r}")
    for claim_id in sorted(expected_ids - verdicts_by_id.keys()):
        errors.append(f"missing verdict for claim_id {claim_id!r}")

    validated: dict[str, dict[str, Any]] = {}
    for claim in claims:
        entry = verdicts_by_id.get(claim.claim_id)
        if entry is None:
            continue
        verdict = entry.get("verdict")
        if verdict is None:
            errors.append(f"missing verdict value for claim_id {claim.claim_id!r}")
            continue
        if verdict not in CLAIM_VERDICTS:
            errors.append(
                f"claim_id {claim.claim_id!r} verdict {verdict!r} not in §16 vocabulary"
            )
            continue
        rationale = entry.get("rationale")
        if rationale is None or (isinstance(rationale, str) and not rationale.strip()):
            errors.append(f"missing rationale for claim_id {claim.claim_id!r}")
            continue
        if rationale is not None and not isinstance(rationale, str):
            errors.append(f"claim_id {claim.claim_id!r} rationale must be a string")
            continue
        validated[claim.claim_id] = entry

    if errors:
        raise SpotCheckIngestionError(errors)
    return validated


def _claim_row_from_verdict(
    *,
    config: SpotCheckConfig,
    company_slug: str,
    claim: SpotCheckClaim,
    verdict_entry: dict[str, Any],
    run_id: str,
    run_ts: datetime,
) -> S2ScoreRow:
    rationale = verdict_entry.get("rationale")
    if rationale is not None and not isinstance(rationale, str):
        raise ValueError(f"claim_id {claim.claim_id!r} rationale must be a string or null")

    return S2ScoreRow(
        company=company_slug,
        surface=config.surface,
        run_id=run_id,
        run_ts=run_ts,
        row_type="claim",
        claim_id=claim.claim_id,
        verdict=verdict_entry["verdict"],
        rationale=rationale,
        writer=None,
        asserted_magnitude=claim.asserted_magnitude,
        asserted_unit=claim.asserted_unit,
        extracted_magnitude=None,
        extracted_unit=None,
        cited_chunk_id=claim.cited_chunk_id,
        cited_locator_kind=claim.cited_locator_kind,
        cited_locator_value=claim.cited_locator_value,
        judge_verdict_advisory=None,
    )


def write_spot_check_results(
    config: SpotCheckConfig,
    *,
    writer: S2Writer | None = None,
    run_id: str | None = None,
    run_ts: datetime | None = None,
    chunk_index: ChunkIndex | None = None,
    chunk_id_resolver: ChunkIdResolver | None = None,
    exec_analysis_cache: dict[str, Any] | None = None,
) -> SpotCheckWriteResult:
    """Ingest operator verdicts and write claim rows + completion marker under one run_id."""
    _assert_human_spot_check_allowed(config.surface, config.registry_path)
    company_slug = canonical_company_slug(config.company)

    s2_writer = writer or S2Writer(catalog=config.catalog)
    sql_executor = getattr(s2_writer, "_sql", None)

    if chunk_index is None and sql_executor is not None:
        chunk_index = ChunkIndex.from_sql(
            sql_executor,
            catalog=config.catalog,
            company=config.company,
        )

    if exec_analysis_cache is None and config.surface == "exec_summary" and sql_executor is not None:
        exec_analysis_cache = load_exec_analysis_cache(
            sql_executor,
            catalog=config.catalog,
            company=config.company,
        )

    claims = load_claim_enumeration(
        config,
        chunk_index=chunk_index,
        exec_analysis_cache=exec_analysis_cache,
    )
    verdicts_by_id = _load_verdicts(config.verdicts_path)
    validated = _validate_verdict_ingestion(claims, verdicts_by_id)

    if run_id is None or run_ts is None:
        generated_id, generated_ts = _generate_run_id(run_ts)
        run_id = run_id or generated_id
        run_ts = run_ts or generated_ts

    rows = [
        _claim_row_from_verdict(
            config=config,
            company_slug=company_slug,
            claim=claim,
            verdict_entry=validated[claim.claim_id],
            run_id=run_id,
            run_ts=run_ts,
        )
        for claim in claims
    ]

    if chunk_id_resolver is None and sql_executor is not None:
        chunk_id_resolver = make_warehouse_chunk_id_resolver(
            catalog=config.catalog,
            sql_executor=sql_executor,
        )

    s2_writer.write_claims(
        company_slug,
        config.surface,
        run_id,
        run_ts,
        rows,
        rationale_required=True,
        rung=3,
        chunk_id_resolver=chunk_id_resolver,
    )
    s2_writer.write_completion_marker(
        company_slug,
        config.surface,
        run_id,
        run_ts,
        HUMAN_WRITER,
    )

    logger.info(
        "spot_check_written",
        extra={
            "event": "spot_check_written",
            "company": company_slug,
            "surface": config.surface,
            "run_id": run_id,
            "n_claims": len(rows),
        },
    )
    return SpotCheckWriteResult(run_id=run_id, run_ts=run_ts, claim_count=len(rows))
