"""Hermetic tests for S2 score-table writer (T1 / §8.8)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from eval.content.s2_writer import (
    S2ScoreRow,
    S2Writer,
    _ensure_utc_microsecond,
    _row_to_insert_values,
    _sql_literal,
    _sql_str,
    apply_s2_scores_ddl,
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
    def __init__(
        self,
        *,
        marker_exists: bool = False,
        claims_without_marker: bool = False,
    ) -> None:
        self.statements: list[str] = []
        self._marker_exists = marker_exists
        self._claims_without_marker = claims_without_marker

    def __call__(self, statement: str) -> list[list[str]]:
        self.statements.append(statement)
        normalized = " ".join(statement.split())
        if normalized.startswith("SELECT"):
            if "row_type IN ('claim', 'completion_marker')" in normalized:
                rows: list[list[str]] = []
                if self._claims_without_marker:
                    rows.append(["claim"])
                if self._marker_exists:
                    rows.append(["completion_marker"])
                return rows
            if "row_type = 'completion_marker'" in normalized:
                return [["completion_marker"]] if self._marker_exists else []
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
        chunk_id_resolver=lambda ids: ids,
    )

    assert len(recorder.statements) == 2
    guard = recorder.statements[0]
    insert = recorder.statements[1]
    assert "row_type IN ('claim', 'completion_marker')" in guard
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

    with pytest.raises(ValueError, match="rung-2 numeric"):
        writer.write_claims(
            "elder_care",
            "fta_numeric",
            "20260914T101133Z-a41",
            _run_ts(),
            [_claim_row(surface="fta_numeric", asserted_magnitude=Decimal("4.2"))],
        )


def test_write_claims_accepts_magnitude_without_unit_at_rung_3() -> None:
    recorder = RecordingSqlExecutor()
    writer = S2Writer(catalog="uc13_ale", sql_executor=recorder)

    writer.write_claims(
        "elder_care",
        "fta_numeric",
        "20260914T101133Z-a41",
        _run_ts(),
        [
            _claim_row(
                surface="fta_numeric",
                asserted_magnitude=Decimal("8955"),
                asserted_unit=None,
            )
        ],
        rung=3,
        chunk_id_resolver=lambda ids: ids,
    )

    assert len(recorder.statements) == 2
    assert "8955" in recorder.statements[1]


def test_write_claims_rejects_unit_without_magnitude_at_rung_3() -> None:
    writer = S2Writer(catalog="uc13_ale", sql_executor=RecordingSqlExecutor())

    with pytest.raises(ValueError, match="unit set without magnitude"):
        writer.write_claims(
            "elder_care",
            "fta_numeric",
            "20260914T101133Z-a41",
            _run_ts(),
            [_claim_row(surface="fta_numeric", asserted_unit="USD_m")],
            rung=3,
        )


def test_write_claims_rung_2_explicit_matches_default_strict_pairing() -> None:
    writer = S2Writer(catalog="uc13_ale", sql_executor=RecordingSqlExecutor())
    row = _claim_row(surface="fta_numeric", asserted_magnitude=Decimal("4.2"))

    with pytest.raises(ValueError, match="rung-2 numeric"):
        writer.write_claims(
            "elder_care",
            "fta_numeric",
            "20260914T101133Z-a41",
            _run_ts(),
            [row],
            rung=2,
        )

    with pytest.raises(ValueError, match="rung-2 numeric"):
        writer.write_claims(
            "elder_care",
            "fta_numeric",
            "20260914T101133Z-a41",
            _run_ts(),
            [row],
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


def test_write_claims_requires_rationale_when_flagged() -> None:
    writer = S2Writer(catalog="uc13_ale", sql_executor=RecordingSqlExecutor())

    with pytest.raises(ValueError, match="requires non-null rationale"):
        writer.write_claims(
            "elder_care",
            "exec_summary",
            "20260914T101133Z-a41",
            _run_ts(),
            [_claim_row(surface="exec_summary", rationale=None)],
            rationale_required=True,
        )


def test_write_claims_s61_requires_resolver_when_cited() -> None:
    writer = S2Writer(catalog="uc13_ale", sql_executor=RecordingSqlExecutor())
    row = _claim_row(cited_chunk_id="chunk-abc")

    with pytest.raises(ValueError, match="chunk_id_resolver is required"):
        writer.write_claims(
            "elder_care",
            "legal_register",
            "20260914T101133Z-a41",
            _run_ts(),
            [row],
        )


def test_write_claims_s61_allows_no_resolver_when_uncited() -> None:
    recorder = RecordingSqlExecutor()
    writer = S2Writer(catalog="uc13_ale", sql_executor=recorder)

    writer.write_claims(
        "elder_care",
        "legal_register",
        "20260914T101133Z-a41",
        _run_ts(),
        [_claim_row(cited_chunk_id=None, cited_locator_kind=None, cited_locator_value=None)],
    )

    assert len(recorder.statements) == 2


def test_write_claims_s61_kills_unresolved_chunk_ids() -> None:
    writer = S2Writer(catalog="uc13_ale", sql_executor=RecordingSqlExecutor())
    row = _claim_row(cited_chunk_id="missing-chunk")

    def resolver(ids: frozenset[str]) -> frozenset[str]:
        return frozenset({"c817"} & ids)

    with pytest.raises(ValueError, match="S-61"):
        writer.write_claims(
            "elder_care",
            "legal_register",
            "20260914T101133Z-a41",
            _run_ts(),
            [row],
            chunk_id_resolver=resolver,
        )


def test_write_claims_s61_batches_chunk_resolution() -> None:
    recorder = RecordingSqlExecutor()
    writer = S2Writer(catalog="uc13_ale", sql_executor=recorder)
    seen: list[frozenset[str]] = []

    def resolver(ids: frozenset[str]) -> frozenset[str]:
        seen.append(ids)
        return ids

    rows = [
        _claim_row(claim_id="legal.a.001", cited_chunk_id="c817"),
        _claim_row(claim_id="legal.a.002", cited_chunk_id="c818"),
    ]
    writer.write_claims(
        "elder_care",
        "legal_register",
        "20260914T101133Z-a41",
        _run_ts(),
        rows,
        chunk_id_resolver=resolver,
    )
    assert len(seen) == 1
    assert seen[0] == frozenset({"c817", "c818"})


def test_sql_str_escapes_backslash_and_quote() -> None:
    assert _sql_str("O'Brien") == "O''Brien"
    assert _sql_str(r"path\to\file") == r"path\\to\\file"
    rendered = _row_to_insert_values(
        _claim_row(
            company=r"elder\_care",
            cited_locator_value="it's a \\test",
        )
    )
    assert r"elder\\_care" in rendered
    assert "it''s a \\\\test" in rendered


def test_run_ts_sql_literal_retains_six_fractional_digits() -> None:
    ts = datetime(2026, 9, 14, 10, 11, 33, 481920, tzinfo=timezone.utc)
    assert _sql_literal(ts) == "TIMESTAMP '2026-09-14 10:11:33.481920'"


def test_ensure_utc_microsecond_normalizes_naive_to_utc() -> None:
    naive = datetime(2026, 8, 13, 18, 30, 0, 481920)
    normalized = _ensure_utc_microsecond(naive)
    assert normalized.tzinfo == timezone.utc
    assert normalized.microsecond == 481920


def test_write_claims_refuses_partial_run_retry() -> None:
    recorder = RecordingSqlExecutor(claims_without_marker=True)
    writer = S2Writer(catalog="uc13_ale", sql_executor=recorder)

    with pytest.raises(ValueError, match="without completion marker"):
        writer.write_claims(
            "elder_care",
            "legal_register",
            "20260914T101133Z-a41",
            _run_ts(),
            [_claim_row()],
        )

    assert len(recorder.statements) == 1


def test_apply_s2_scores_ddl_executes_comment_first_statements() -> None:
    executed: list[str] = []

    def executor(statement: str) -> list[list[str]]:
        executed.append(statement)
        return []

    apply_s2_scores_ddl(catalog="uc13_test", sql_executor=executor)
    assert any("CREATE SCHEMA" in stmt for stmt in executed)
    assert any("CREATE TABLE" in stmt for stmt in executed)
    assert len(executed) == 2
