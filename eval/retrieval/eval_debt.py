"""Eval-debt ledger — spec §17 item 35 / M4 T7."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from collections.abc import Iterable
from typing import Any

import yaml

from eval.retrieval.companies import canonical_company_slug
from eval.retrieval.errors import EvalError

DEFAULT_LEDGER_PATH = Path("eval/program/eval_debt/eval_debt.yaml")
DEFAULT_REGISTRY_PATH = Path("eval/program/registry.yaml")

LAYERS = frozenset({"retrieval", "content", "trust"})
SURFACES = frozenset({"fta_numeric", "legal_register", "exec_summary"})
CONTENT_SURFACES = SURFACES

_TRUST_ROW_RE = re.compile(
    r"^trust:(?P<company>[a-z0-9_]+):(?P<layer>retrieval|content|trust):"
    r"(?P<surface>null|fta_numeric|legal_register|exec_summary)$"
)
_REGISTRY_REF_RE = re.compile(r"^registry:(?P<id>.+)$")


class EvalDebtError(EvalError):
    """Eval-debt ledger schema, reference, or high-water-mark violation."""


@dataclass(frozen=True)
class EvalDebtRow:
    id: str
    company: str
    surface: str | None
    layer: str
    kind: str
    opened_at: str
    evidence_refs: list[str]
    closes_when: str
    closed_at: str | None = None
    closed_evidence_refs: list[str] | None = None

    @property
    def is_open(self) -> bool:
        return self.closed_at is None


def _derive_layer(surface: str | None) -> str:
    if surface is not None:
        return "content"
    return "retrieval"


def _trust_row_ref(*, company: str, layer: str, surface: str | None) -> str:
    surface_token = surface if surface is not None else "null"
    return f"trust:{company}:{layer}:{surface_token}"


def _validate_row_fields(
    *,
    row_id: str,
    company: str,
    surface: str | None,
    layer: str,
    kind: str,
    opened_at: str,
    evidence_refs: list[str],
    closes_when: str,
    closed_at: str | None,
    closed_evidence_refs: list[str] | None,
) -> None:
    if not row_id:
        raise EvalDebtError("id must be non-empty")
    if not kind:
        raise EvalDebtError("kind must be non-empty")
    if not closes_when:
        raise EvalDebtError("closes_when must be non-empty")
    if not opened_at:
        raise EvalDebtError("opened_at must be non-empty")
    if layer not in LAYERS:
        raise EvalDebtError(f"layer must be one of {sorted(LAYERS)}")
    if surface is not None and surface not in SURFACES:
        raise EvalDebtError(f"surface must be one of {sorted(SURFACES)} or null")
    if not evidence_refs:
        raise EvalDebtError("evidence_refs must be non-empty")
    if closed_at is None:
        if closed_evidence_refs:
            raise EvalDebtError(
                "closed_evidence_refs must be null when closed_at is null"
            )
    else:
        if not closed_evidence_refs:
            raise EvalDebtError(
                "closed_evidence_refs must be non-empty when closed_at is set"
            )


def _row_from_mapping(row: dict[str, Any]) -> EvalDebtRow:
    required = (
        "id",
        "company",
        "surface",
        "layer",
        "kind",
        "opened_at",
        "evidence_refs",
        "closes_when",
    )
    for key in required:
        if key not in row:
            raise EvalDebtError(f"missing required field: {key}")

    allowed = {
        *required,
        "closed_at",
        "closed_evidence_refs",
    }
    extra = set(row) - allowed
    if extra:
        raise EvalDebtError(f"unexpected fields: {sorted(extra)}")

    surface = row["surface"]
    if surface == "null":
        surface = None

    closed_at = row.get("closed_at")
    closed_evidence_refs = row.get("closed_evidence_refs")
    evidence_refs = row["evidence_refs"]
    if not isinstance(evidence_refs, list):
        raise EvalDebtError("evidence_refs must be a list")
    if closed_evidence_refs is not None and not isinstance(closed_evidence_refs, list):
        raise EvalDebtError("closed_evidence_refs must be a list or null")

    _validate_row_fields(
        row_id=str(row["id"]),
        company=str(row["company"]),
        surface=surface,
        layer=str(row["layer"]),
        kind=str(row["kind"]),
        opened_at=str(row["opened_at"]),
        evidence_refs=[str(ref) for ref in evidence_refs],
        closes_when=str(row["closes_when"]),
        closed_at=str(closed_at) if closed_at is not None else None,
        closed_evidence_refs=(
            [str(ref) for ref in closed_evidence_refs]
            if closed_evidence_refs is not None
            else None
        ),
    )
    return EvalDebtRow(
        id=str(row["id"]),
        company=str(row["company"]),
        surface=surface,
        layer=str(row["layer"]),
        kind=str(row["kind"]),
        opened_at=str(row["opened_at"]),
        evidence_refs=[str(ref) for ref in evidence_refs],
        closes_when=str(row["closes_when"]),
        closed_at=str(closed_at) if closed_at is not None else None,
        closed_evidence_refs=(
            [str(ref) for ref in closed_evidence_refs]
            if closed_evidence_refs is not None
            else None
        ),
    )


def _row_to_mapping(row: EvalDebtRow) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": row.id,
        "company": row.company,
        "surface": row.surface,
        "layer": row.layer,
        "kind": row.kind,
        "opened_at": row.opened_at,
        "evidence_refs": list(row.evidence_refs),
        "closes_when": row.closes_when,
    }
    if row.closed_at is not None:
        payload["closed_at"] = row.closed_at
        payload["closed_evidence_refs"] = list(row.closed_evidence_refs or [])
    return payload


def _load_registry_ids(registry_path: Path) -> set[str]:
    if not registry_path.is_file():
        raise EvalDebtError(f"registry not found: {registry_path}")
    payload = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise EvalDebtError("registry root must be a mapping")
    items = payload.get("items")
    if not isinstance(items, list):
        raise EvalDebtError("registry items must be a list")
    ids: set[str] = set()
    for row in items:
        if isinstance(row, dict) and row.get("id"):
            ids.add(str(row["id"]))
    return ids


def evidence_ref_resolves(
    ref: str,
    *,
    repo_root: Path,
    registry_ids: set[str],
) -> bool:
    registry_match = _REGISTRY_REF_RE.match(ref)
    if registry_match:
        return registry_match.group("id") in registry_ids
    if _TRUST_ROW_RE.match(ref):
        return True
    # Operator-local; not a clone/pytest artifact.
    path = ref.split("#", 1)[0]
    if path.startswith(".dev/"):
        return True
    candidate = repo_root / path
    return candidate.is_file()


def validate_open_debt_evidence_refs(
    refs: list[str],
    *,
    repo_root: Path,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
) -> None:
    registry_ids = _load_registry_ids(registry_path)
    for ref in refs:
        if not evidence_ref_resolves(ref, repo_root=repo_root, registry_ids=registry_ids):
            raise EvalDebtError(f"evidence ref does not resolve: {ref!r}")


def _load_ledger_document(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise EvalDebtError(f"eval-debt ledger not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise EvalDebtError("eval-debt ledger root must be a mapping")
    if payload.get("schema_version") != 1:
        raise EvalDebtError("schema_version must be 1")
    if "open_debt_high_water_mark" not in payload:
        raise EvalDebtError("open_debt_high_water_mark is required")
    hwm = payload["open_debt_high_water_mark"]
    if not isinstance(hwm, int) or hwm < 0:
        raise EvalDebtError("open_debt_high_water_mark must be a non-negative integer")
    debts = payload.get("debts")
    if debts is None:
        raise EvalDebtError("debts key is required")
    if not isinstance(debts, list):
        raise EvalDebtError("debts must be a list")
    return payload


def load_debts(path: Path) -> list[EvalDebtRow]:
    payload = _load_ledger_document(path)
    rows = [_row_from_mapping(row) for row in payload["debts"]]
    seen: set[str] = set()
    for row in rows:
        if row.id in seen:
            raise EvalDebtError(f"duplicate debt id: {row.id}")
        seen.add(row.id)
    return rows


def open_debt_count(rows: Iterable[EvalDebtRow]) -> int:
    return sum(1 for row in rows if row.is_open)


def assert_ledger_ratchet(
    path: Path,
    *,
    repo_root: Path,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
) -> None:
    payload = _load_ledger_document(path)
    rows = load_debts(path)
    open_count = open_debt_count(rows)
    hwm = payload["open_debt_high_water_mark"]
    if open_count > hwm:
        raise EvalDebtError(
            f"open debt count {open_count} exceeds high-water mark {hwm}"
        )
    registry_ids = _load_registry_ids(registry_path)
    for row in rows:
        if not row.is_open:
            continue
        if not row.evidence_refs:
            raise EvalDebtError(f"open debt {row.id!r} has empty evidence_refs")
        for ref in row.evidence_refs:
            if not evidence_ref_resolves(
                ref, repo_root=repo_root, registry_ids=registry_ids
            ):
                raise EvalDebtError(
                    f"open debt {row.id!r} evidence ref does not resolve: {ref!r}"
                )


def open_debt(
    path: Path,
    *,
    company: str,
    surface: str | None,
    kind: str,
    closes_when: str,
    opened_at: str | None = None,
) -> EvalDebtRow:
    folded_company = canonical_company_slug(company)
    if surface == "null":
        surface = None
    layer = _derive_layer(surface)
    opened = opened_at or date.today().isoformat()
    surface_token = surface if surface is not None else "global"
    row_id = f"{folded_company}:{surface_token}:{kind}"
    evidence_refs = [
        _trust_row_ref(company=folded_company, layer=layer, surface=surface)
    ]

    _validate_row_fields(
        row_id=row_id,
        company=folded_company,
        surface=surface,
        layer=layer,
        kind=kind,
        opened_at=opened,
        evidence_refs=evidence_refs,
        closes_when=closes_when,
        closed_at=None,
        closed_evidence_refs=None,
    )

    if path.is_file():
        payload = _load_ledger_document(path)
        existing = load_debts(path)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": 1, "open_debt_high_water_mark": 0, "debts": []}
        existing = []

    if any(row.id == row_id for row in existing):
        raise EvalDebtError(f"debt id already exists: {row_id}")

    new_row = EvalDebtRow(
        id=row_id,
        company=folded_company,
        surface=surface,
        layer=layer,
        kind=kind,
        opened_at=opened,
        evidence_refs=evidence_refs,
        closes_when=closes_when,
    )
    projected_open = open_debt_count(existing) + 1
    hwm = payload["open_debt_high_water_mark"]
    if projected_open > hwm:
        raise EvalDebtError(
            f"open debt count would be {projected_open}, exceeding "
            f"high-water mark {hwm}; bump open_debt_high_water_mark first"
        )

    rows = [_row_to_mapping(row) for row in existing]
    rows.append(_row_to_mapping(new_row))
    payload["debts"] = rows
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return new_row


def close_debt(
    path: Path,
    *,
    debt_id: str,
    closed_at: str | None = None,
    closed_evidence_refs: list[str] | None = None,
) -> EvalDebtRow:
    payload = _load_ledger_document(path)
    rows = load_debts(path)
    closed = closed_at or date.today().isoformat()
    updated: list[EvalDebtRow] = []
    target: EvalDebtRow | None = None
    for row in rows:
        if row.id != debt_id:
            updated.append(row)
            continue
        if not row.is_open:
            raise EvalDebtError(f"debt is already closed: {debt_id}")
        closure_refs = closed_evidence_refs or [
            f"registry:closure-note:{debt_id}:{closed}"
        ]
        target = EvalDebtRow(
            id=row.id,
            company=row.company,
            surface=row.surface,
            layer=row.layer,
            kind=row.kind,
            opened_at=row.opened_at,
            evidence_refs=list(row.evidence_refs),
            closes_when=row.closes_when,
            closed_at=closed,
            closed_evidence_refs=list(closure_refs),
        )
        _validate_row_fields(
            row_id=target.id,
            company=target.company,
            surface=target.surface,
            layer=target.layer,
            kind=target.kind,
            opened_at=target.opened_at,
            evidence_refs=target.evidence_refs,
            closes_when=target.closes_when,
            closed_at=target.closed_at,
            closed_evidence_refs=target.closed_evidence_refs,
        )
        updated.append(target)

    if target is None:
        raise EvalDebtError(f"debt id not found: {debt_id}")

    payload["debts"] = [_row_to_mapping(row) for row in updated]
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eval.retrieval.eval_debt")
    parser.add_argument(
        "--ledger",
        type=Path,
        default=DEFAULT_LEDGER_PATH,
        help="Path to eval_debt.yaml",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    open_parser = subparsers.add_parser("open", help="Open one eval-debt row")
    open_parser.add_argument("--company", required=True)
    open_parser.add_argument(
        "--surface",
        required=True,
        choices=(*sorted(SURFACES), "null"),
    )
    open_parser.add_argument("--kind", required=True)
    open_parser.add_argument("--closes-when", required=True)

    list_parser = subparsers.add_parser("list", help="List eval-debt rows")
    list_parser.add_argument("--company")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    ledger_path: Path = args.ledger

    try:
        if args.command == "open":
            surface = None if args.surface == "null" else args.surface
            row = open_debt(
                ledger_path,
                company=args.company,
                surface=surface,
                kind=args.kind,
                closes_when=args.closes_when,
            )
            slug = canonical_company_slug(args.company)
            print(
                f"eval_debt: opened id={row.id} company={slug} "
                f"layer={row.layer} -> {ledger_path}"
            )
            return 0

        if args.command == "list":
            rows = load_debts(ledger_path)
            if args.company:
                slug = canonical_company_slug(args.company)
                rows = [row for row in rows if row.company == slug]
            for row in rows:
                status = "open" if row.is_open else "closed"
                print(
                    f"{row.id}\t{row.company}\t{row.surface}\t{row.layer}\t"
                    f"{row.kind}\t{status}"
                )
            print(f"eval_debt: listed {len(rows)} rows from {ledger_path}")
            return 0
    except EvalDebtError as exc:
        print(f"eval_debt: {exc}", file=sys.stderr)
        return 1

    parser.error(f"unknown command: {args.command}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
