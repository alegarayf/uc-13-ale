"""Intent exemption annotation store — spec §8.3 / M4 item 33."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from eval.retrieval.companies import canonical_company_slug
from eval.retrieval.errors import EvalError

DEFAULT_STORE_PATH = Path("eval/program/eval_exemptions.yaml")

SURFACES = frozenset({"fta_numeric", "legal_register", "exec_summary"})
COVERAGES = frozenset({"eliminates", "narrows"})
REASONS = frozenset({"corpus_absent", "corpus_thin", "overlay_mismatch"})


class ExemptionValidationError(EvalError):
    """Exemption row failed §8.3 schema or mutual-requiredness rules."""


@dataclass(frozen=True)
class IntentExemption:
    company: str
    intent_id: str
    surface: str | None
    coverage: str | None
    reason: str
    corpus_evidence: dict[str, Any]
    approved_by: str


def _validate_exemption_fields(
    *,
    company: str,
    intent_id: str,
    surface: str | None,
    coverage: str | None,
    reason: str,
    corpus_evidence: dict[str, Any],
    approved_by: str,
) -> None:
    if not intent_id:
        raise ExemptionValidationError("intent_id must be non-empty")
    if not approved_by:
        raise ExemptionValidationError("approved_by must be non-empty")
    if not isinstance(corpus_evidence, dict):
        raise ExemptionValidationError("corpus_evidence must be a mapping")
    if reason not in REASONS:
        raise ExemptionValidationError(f"reason must be one of {sorted(REASONS)}")
    if surface is not None and surface not in SURFACES:
        raise ExemptionValidationError(f"surface must be one of {sorted(SURFACES)} or null")
    if coverage is not None and coverage not in COVERAGES:
        raise ExemptionValidationError(f"coverage must be one of {sorted(COVERAGES)} or null")

    if surface is None:
        if coverage is not None:
            raise ExemptionValidationError(
                "coverage must be null when surface is null (§8.3 case 3)"
            )
    elif coverage is None:
        raise ExemptionValidationError(
            "coverage is required when surface is non-null (§8.3 cases 1–2)"
        )


def _exemption_from_mapping(row: dict[str, Any]) -> IntentExemption:
    for key in (
        "company",
        "intent_id",
        "surface",
        "coverage",
        "reason",
        "corpus_evidence",
        "approved_by",
    ):
        if key not in row:
            raise ExemptionValidationError(f"missing required field: {key}")
    extra = set(row) - {
        "company",
        "intent_id",
        "surface",
        "coverage",
        "reason",
        "corpus_evidence",
        "approved_by",
    }
    if extra:
        raise ExemptionValidationError(f"unexpected fields: {sorted(extra)}")

    surface = row["surface"]
    coverage = row["coverage"]
    if surface == "null":
        surface = None
    if coverage == "null":
        coverage = None

    _validate_exemption_fields(
        company=str(row["company"]),
        intent_id=str(row["intent_id"]),
        surface=surface,
        coverage=coverage,
        reason=str(row["reason"]),
        corpus_evidence=row["corpus_evidence"],
        approved_by=str(row["approved_by"]),
    )
    return IntentExemption(
        company=str(row["company"]),
        intent_id=str(row["intent_id"]),
        surface=surface,
        coverage=coverage,
        reason=str(row["reason"]),
        corpus_evidence=dict(row["corpus_evidence"]),
        approved_by=str(row["approved_by"]),
    )


def _exemption_to_mapping(exemption: IntentExemption) -> dict[str, Any]:
    return {
        "company": exemption.company,
        "intent_id": exemption.intent_id,
        "surface": exemption.surface,
        "coverage": exemption.coverage,
        "reason": exemption.reason,
        "corpus_evidence": dict(exemption.corpus_evidence),
        "approved_by": exemption.approved_by,
    }


def _load_store_document(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ExemptionValidationError(f"exemption store not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ExemptionValidationError("exemption store root must be a mapping")
    if payload.get("schema_version") != 1:
        raise ExemptionValidationError("schema_version must be 1")
    exemptions = payload.get("exemptions")
    if exemptions is None:
        raise ExemptionValidationError("exemptions key is required")
    if not isinstance(exemptions, list):
        raise ExemptionValidationError("exemptions must be a list")
    return payload


def load_exemptions(path: Path) -> list[IntentExemption]:
    payload = _load_store_document(path)
    return [_exemption_from_mapping(row) for row in payload["exemptions"]]


def write_exemption(path: Path, exemption: IntentExemption) -> None:
    folded_company = canonical_company_slug(exemption.company)
    _validate_exemption_fields(
        company=folded_company,
        intent_id=exemption.intent_id,
        surface=exemption.surface,
        coverage=exemption.coverage,
        reason=exemption.reason,
        corpus_evidence=exemption.corpus_evidence,
        approved_by=exemption.approved_by,
    )
    normalized = IntentExemption(
        company=folded_company,
        intent_id=exemption.intent_id,
        surface=exemption.surface,
        coverage=exemption.coverage,
        reason=exemption.reason,
        corpus_evidence=dict(exemption.corpus_evidence),
        approved_by=exemption.approved_by,
    )

    if path.is_file():
        payload = _load_store_document(path)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": 1, "exemptions": []}

    rows: list[dict[str, Any]] = []
    for row in payload["exemptions"]:
        if isinstance(row, dict):
            rows.append(dict(row))
        else:
            rows.append(_exemption_to_mapping(row))
    rows.append(_exemption_to_mapping(normalized))
    payload["exemptions"] = rows
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _parse_evidence_pairs(pairs: list[str]) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    for pair in pairs:
        if "=" not in pair:
            raise ExemptionValidationError(
                f"--evidence must be key=value, got {pair!r}"
            )
        key, _, raw = pair.partition("=")
        key = key.strip()
        if not key:
            raise ExemptionValidationError(f"--evidence key must be non-empty: {pair!r}")
        if raw.isdigit():
            evidence[key] = int(raw)
        else:
            evidence[key] = raw
    return evidence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eval.retrieval.exemptions")
    parser.add_argument(
        "--store",
        type=Path,
        default=DEFAULT_STORE_PATH,
        help="Path to eval_exemptions.yaml",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Append one exemption row")
    add_parser.add_argument("--company", required=True)
    add_parser.add_argument("--intent-id", required=True)
    add_parser.add_argument(
        "--surface",
        required=True,
        choices=(*sorted(SURFACES), "null"),
    )
    add_parser.add_argument(
        "--coverage",
        required=True,
        choices=(*sorted(COVERAGES), "null"),
    )
    add_parser.add_argument(
        "--reason",
        required=True,
        choices=sorted(REASONS),
    )
    add_parser.add_argument(
        "--evidence",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Corpus evidence key=value (repeatable)",
    )
    add_parser.add_argument("--approved-by", required=True)

    list_parser = subparsers.add_parser("list", help="List exemption rows")
    list_parser.add_argument("--company")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    store_path: Path = args.store

    try:
        if args.command == "add":
            surface = None if args.surface == "null" else args.surface
            coverage = None if args.coverage == "null" else args.coverage
            exemption = IntentExemption(
                company=args.company,
                intent_id=args.intent_id,
                surface=surface,
                coverage=coverage,
                reason=args.reason,
                corpus_evidence=_parse_evidence_pairs(args.evidence),
                approved_by=args.approved_by,
            )
            write_exemption(store_path, exemption)
            slug = canonical_company_slug(args.company)
            print(
                f"exemptions: wrote 1 row for company={slug} "
                f"intent={args.intent_id} -> {store_path}"
            )
            return 0

        if args.command == "list":
            rows = load_exemptions(store_path)
            if args.company:
                slug = canonical_company_slug(args.company)
                rows = [row for row in rows if row.company == slug]
            for row in rows:
                print(
                    f"{row.company}\t{row.intent_id}\t{row.surface}\t"
                    f"{row.coverage}\t{row.reason}"
                )
            print(f"exemptions: listed {len(rows)} rows from {store_path}")
            return 0
    except (ExemptionValidationError, ValueError) as exc:
        print(f"exemptions: {exc}", file=sys.stderr)
        return 1

    parser.error(f"unknown command: {args.command}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
