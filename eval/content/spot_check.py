"""Rung-3 human spot-check tooling — spec §12.1 rung 3 / item 26."""

from __future__ import annotations

import json
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml

from eval.content.s2_writer import CLAIM_VERDICTS, S2ScoreRow, S2Writer, SURFACES
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


def _claim_from_manifest_entry(surface: str, source: str, entry: dict[str, Any]) -> SpotCheckClaim:
    claim_id = entry["claim_id"]
    claim_text = entry["claim_text"]
    section = entry.get("section")
    source_doc = entry.get("source_doc")
    source_location = entry.get("source_location")

    source_ref: str | None
    if source_doc and source_location:
        source_ref = f"source://{source_doc}#{source_location}"
    elif section:
        source_ref = f"source://{source}#{section}"
    else:
        source_ref = f"source://{source}"

    locator_kind = "section" if source_location else None
    locator_value = source_location

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
        cited_locator_kind=locator_kind,
        cited_locator_value=locator_value,
        asserted_magnitude=asserted_magnitude,
        asserted_unit=asserted_unit,
    )


def load_claim_enumeration(config: SpotCheckConfig) -> tuple[SpotCheckClaim, ...]:
    """Load the whole-surface claim set from the committed rubric manifest."""
    manifest_file = _manifest_path(config)
    payload = json.loads(manifest_file.read_text(encoding="utf-8"))
    claims = [
        _claim_from_manifest_entry(config.surface, config.source, entry)
        for entry in payload["claims"]
    ]
    if not claims:
        raise ValueError(f"claim manifest {manifest_file} is empty")
    return tuple(claims)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _generate_run_id(ts: datetime | None = None) -> tuple[str, datetime]:
    run_ts = ts or _utc_now()
    suffix = secrets.token_hex(2)
    run_id = f"{run_ts.strftime('%Y%m%dT%H%M%S')}Z-{suffix}"
    return run_id, run_ts


def prepare_spot_check(config: SpotCheckConfig) -> SpotCheckPrepareResult:
    """Enumerate claims, validate registry guard-rail, write presentation packet YAML."""
    _assert_human_spot_check_allowed(config.surface, config.registry_path)
    company_slug = canonical_company_slug(config.company)
    claims = load_claim_enumeration(config)

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
) -> SpotCheckWriteResult:
    """Ingest operator verdicts and write claim rows + completion marker under one run_id."""
    _assert_human_spot_check_allowed(config.surface, config.registry_path)
    company_slug = canonical_company_slug(config.company)
    claims = load_claim_enumeration(config)
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

    s2_writer = writer or S2Writer(catalog=config.catalog)
    s2_writer.write_claims(
        company_slug,
        config.surface,
        run_id,
        run_ts,
        rows,
        rationale_required=True,
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
