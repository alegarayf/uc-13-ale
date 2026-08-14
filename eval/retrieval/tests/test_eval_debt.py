from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from eval.retrieval.companies import UnnormalizableCompanySlugError
from eval.retrieval.errors import EvalError
from eval.retrieval.eval_debt import (
    EvalDebtError,
    EvalDebtRow,
    assert_ledger_ratchet,
    close_debt,
    evidence_ref_resolves,
    load_debts,
    open_debt,
    open_debt_count,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMITTED_LEDGER = _REPO_ROOT / "eval" / "program" / "eval_debt" / "eval_debt.yaml"
_REGISTRY = _REPO_ROOT / "eval" / "program" / "registry.yaml"


def _seed_ledger(tmp_path: Path, *, hwm: int = 1) -> Path:
    ledger = tmp_path / "eval_debt.yaml"
    ledger.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "open_debt_high_water_mark": hwm,
                "debts": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return ledger


def test_ledger_roundtrip(tmp_path: Path) -> None:
    ledger = _seed_ledger(tmp_path, hwm=1)
    row = open_debt(
        ledger,
        company="Clearsulting",
        surface="legal_register",
        kind="gold_bootstrap",
        closes_when="legal_register attested at rung-3",
    )
    loaded = load_debts(ledger)
    assert len(loaded) == 1
    assert loaded[0] == row
    assert loaded[0].company == "clearsulting"
    assert loaded[0].surface == "legal_register"
    assert loaded[0].layer == "content"
    assert loaded[0].evidence_refs == [
        "trust:clearsulting:content:legal_register"
    ]
    assert loaded[0].is_open is True


def test_open_rejects_unfoldable_company(tmp_path: Path) -> None:
    ledger = _seed_ledger(tmp_path, hwm=1)
    with pytest.raises(UnnormalizableCompanySlugError):
        open_debt(
            ledger,
            company="---",
            surface="null",
            kind="domain_gap",
            closes_when="company slug normalizes",
        )


def test_open_rejects_high_water_mark_exceeded(tmp_path: Path) -> None:
    ledger = _seed_ledger(tmp_path, hwm=0)
    with pytest.raises(EvalDebtError, match="high-water mark"):
        open_debt(
            ledger,
            company="Clearsulting",
            surface="legal_register",
            kind="gold_bootstrap",
            closes_when="legal_register attested",
        )


def test_close_debt_preserves_committed_id_set(tmp_path: Path) -> None:
    """F-08: closing a row must not shrink the ledger's id set (no deletion-as-closure)."""
    ledger = _seed_ledger(tmp_path, hwm=2)
    first = open_debt(
        ledger,
        company="Clearsulting",
        surface="legal_register",
        kind="gold_bootstrap",
        closes_when="legal_register attested",
    )
    second = open_debt(
        ledger,
        company="Clearsulting",
        surface="null",
        kind="promotion_inputs",
        closes_when="pipeline run_id recorded",
    )
    ids_before = {row.id for row in load_debts(ledger)}
    close_debt(ledger, debt_id=first.id, closed_evidence_refs=["registry:UGA-1"])
    ids_after = {row.id for row in load_debts(ledger)}
    assert ids_before <= ids_after
    assert ids_after == ids_before
    assert second.id in ids_after


def test_close_records_state_without_deleting_row(tmp_path: Path) -> None:
    ledger = _seed_ledger(tmp_path, hwm=1)
    opened = open_debt(
        ledger,
        company="Clearsulting",
        surface="legal_register",
        kind="gold_bootstrap",
        closes_when="legal_register attested",
    )
    closed = close_debt(
        ledger,
        debt_id=opened.id,
        closed_evidence_refs=["registry:UGA-1"],
    )
    rows = load_debts(ledger)
    assert len(rows) == 1
    assert rows[0].closed_at == closed.closed_at
    assert rows[0].closed_evidence_refs == ["registry:UGA-1"]
    assert open_debt_count(rows) == 0


def test_committed_ledger_ratchet_passes() -> None:
    payload = yaml.safe_load(_COMMITTED_LEDGER.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["open_debt_high_water_mark"] == 14
    debts = load_debts(_COMMITTED_LEDGER)
    assert len(debts) == 14
    assert open_debt_count(debts) == 13
    assert_ledger_ratchet(
        _COMMITTED_LEDGER,
        repo_root=_REPO_ROOT,
        registry_path=_REGISTRY,
    )


def test_evidence_ref_resolution_variants() -> None:
    registry_ids = {"UGA-1"}
    assert evidence_ref_resolves(
        "registry:UGA-1",
        repo_root=_REPO_ROOT,
        registry_ids=registry_ids,
    )
    assert evidence_ref_resolves(
        "trust:clearsulting:content:legal_register",
        repo_root=_REPO_ROOT,
        registry_ids=registry_ids,
    )
    assert evidence_ref_resolves(
        "eval/program/registry.yaml",
        repo_root=_REPO_ROOT,
        registry_ids=registry_ids,
    )
    assert not evidence_ref_resolves(
        "registry:NOT-A-REAL-ID",
        repo_root=_REPO_ROOT,
        registry_ids=registry_ids,
    )
    assert not evidence_ref_resolves(
        "trust:bad:layer:legal_register",
        repo_root=_REPO_ROOT,
        registry_ids=registry_ids,
    )


def test_ratchet_rejects_unresolved_open_evidence(tmp_path: Path) -> None:
    ledger = tmp_path / "eval_debt.yaml"
    ledger.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "open_debt_high_water_mark": 1,
                "debts": [
                    {
                        "id": "clearsulting:legal_register:gap",
                        "company": "clearsulting",
                        "surface": "legal_register",
                        "layer": "content",
                        "kind": "gap",
                        "opened_at": "2026-08-14",
                        "evidence_refs": ["registry:NOT-A-REAL-ID"],
                        "closes_when": "fixed",
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(EvalDebtError, match="does not resolve"):
        assert_ledger_ratchet(
            ledger,
            repo_root=_REPO_ROOT,
            registry_path=_REGISTRY,
        )


def test_eval_debt_error_subclasses_eval_error() -> None:
    assert issubclass(EvalDebtError, EvalError)


def test_eval_debt_row_is_frozen() -> None:
    row = EvalDebtRow(
        id="x",
        company="clearsulting",
        surface=None,
        layer="retrieval",
        kind="gap",
        opened_at="2026-08-14",
        evidence_refs=["trust:clearsulting:retrieval:null"],
        closes_when="done",
    )
    with pytest.raises(AttributeError):
        row.kind = "other"  # type: ignore[misc]
