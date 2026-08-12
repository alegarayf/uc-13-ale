"""Hermetic tests for S2 score-table writer (T1 / §8.8)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from eval.content.s2_writer import (
    S2ScoreRow,
    S2Writer,
    _row_to_insert_values,
)


def _run_ts() -> datetime:
    return datetime(2026, 9, 14, 10, 11, 33, 481920, tzinfo=timezone.utc)


def _claim_row(**overrides: object) -> S2ScoreRow:
    base = dict(
        company="elder_care",
        surface="legal_register",
        run_id="20260914T101133Z-a41",
        run_ts=_run_ts(),
        row_type="claim",
        claim_id="legal.contract.001",
        verdict="supported",
        rationale=None,
        writer=None,
        asserted_magnitude=None,
        asserted_unit=None,
        extracted_magnitude=None,
        extracted_unit=None,
        cited_chunk_id="c817",
        cited_locator_kind="section",
        cited_locator_value="Historical P&L Summary",
        judge_verdict_advisory=None,
    )
    base.update(overrides)
    return S2ScoreRow(**base)  # type: ignore[arg-type]


class RecordingSqlExecutor:
    def __init__(self, *, marker_exists: bool = False) -> None:
        self.statements: list[str] = []
        self._marker_exists = marker_exists

    def __call__(self, statement: str) -> list[list[str]]:
        self.statements.append(statement)
        normalized = " ".join(statement.split())
        if (
            "row_type = 'completion_marker'" in normalized
            and normalized.startswith("SELECT")
        ):
            return [["1"]] if self._marker_exists else []
        return []


def test_write_claims_issues_guard_before_insert() -> None:
    recorder = RecordingSqlExecutor()
    writer = S2Writer(catalog="uc13_ale", sql_executor=recorder)
    rows = [_claim_row()]

    writer.write_claims(
        "elder_care",
        "legal_register",
        "20260914T101133Z-a41",
        _run_ts(),
        rows,
    )

    assert len(recorder.statements) == 2
    guard = recorder.statements[0]
    insert = recorder.statements[1]
    assert "row_type = 'completion_marker'" in guard
    assert guard.strip().upper().startswith("SELECT")
    assert insert.strip().upper().startswith("INSERT")


def test_write_claims_blocked_when_marker_exists() -> None:
    recorder = RecordingSqlExecutor(marker_exists=True)
    writer = S2Writer(catalog="uc13_ale", sql_executor=recorder)

    with pytest.raises(ValueError, match="completion marker already exists"):
        writer.write_claims(
            "elder_care",
            "legal_register",
            "20260914T101133Z-a41",
            _run_ts(),
            [_claim_row()],
        )

    assert len(recorder.statements) == 1
    assert recorder.statements[0].strip().upper().startswith("SELECT")


def test_write_claims_rejects_invalid_verdict() -> None:
    writer = S2Writer(catalog="uc13_ale", sql_executor=RecordingSqlExecutor())

    with pytest.raises(ValueError, match="not in §16 vocabulary"):
        writer.write_claims(
            "elder_care",
            "legal_register",
            "20260914T101133Z-a41",
            _run_ts(),
            [_claim_row(verdict="maybe")],
        )


def test_write_claims_rejects_magnitude_unit_mismatch() -> None:
    writer = S2Writer(catalog="uc13_ale", sql_executor=RecordingSqlExecutor())

    with pytest.raises(ValueError, match="magnitude and unit must both"):
        writer.write_claims(
            "elder_care",
            "fta_numeric",
            "20260914T101133Z-a41",
            _run_ts(),
            [_claim_row(surface="fta_numeric", asserted_magnitude=Decimal("4.2"))],
        )


def test_write_claims_serializes_decimal_magnitude_without_float() -> None:
    row = _claim_row(
        surface="fta_numeric",
        asserted_magnitude=Decimal("4200000"),
        asserted_unit="USD",
        extracted_magnitude=Decimal("4.2"),
        extracted_unit="USD_m",
    )
    rendered = _row_to_insert_values(row)
    assert "4200000" in rendered
    assert "4.2" in rendered
    assert "4200000.0" not in rendered


def test_write_completion_marker_requires_writer_vocabulary() -> None:
    writer = S2Writer(catalog="uc13_ale", sql_executor=RecordingSqlExecutor())

    with pytest.raises(ValueError, match="marker writer"):
        writer.write_completion_marker(
            "elder_care",
            "legal_register",
            "20260914T101133Z-a41",
            _run_ts(),
            "human:alice",
        )


def test_write_completion_marker_appends_marker_row() -> None:
    recorder = RecordingSqlExecutor()
    writer = S2Writer(catalog="uc13_ale", sql_executor=recorder)

    writer.write_completion_marker(
        "elder_care",
        "legal_register",
        "20260914T101133Z-a41",
        _run_ts(),
        "deterministic_verifier",
    )

    assert len(recorder.statements) == 2
    assert recorder.statements[0].strip().upper().startswith("SELECT")
    insert = recorder.statements[1]
    assert "completion_marker" in insert
    assert "deterministic_verifier" in insert


def test_run_id_must_be_time_sortable() -> None:
    writer = S2Writer(catalog="uc13_ale", sql_executor=RecordingSqlExecutor())

    with pytest.raises(ValueError, match="time-sortable"):
        writer.write_claims(
            "elder_care",
            "legal_register",
            "baseline_544eb3f2a0e2",
            _run_ts(),
            [_claim_row(run_id="baseline_544eb3f2a0e2")],
        )


def test_write_completion_marker_rejects_duplicate() -> None:
    recorder = RecordingSqlExecutor(marker_exists=True)
    writer = S2Writer(catalog="uc13_ale", sql_executor=recorder)

    with pytest.raises(ValueError, match="completion marker already exists"):
        writer.write_completion_marker(
            "elder_care",
            "legal_register",
            "20260914T101133Z-a41",
            _run_ts(),
            "deterministic_verifier",
        )

    assert len(recorder.statements) == 1

    marker = S2ScoreRow.from_completion_marker(
        company="elder_care",
        surface="fta_numeric",
        run_id="20260914T101133Z-a41",
        run_ts=_run_ts(),
        writer="judge_harness",
    )
    assert marker.row_type == "completion_marker"
    assert marker.writer == "judge_harness"
    assert marker.claim_id is None
    assert marker.verdict is None
