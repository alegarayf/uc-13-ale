"""Hermetic tests for the CHK-27 exec_summary judge harness (T5, construction/dry-run path).

Mirrors ``test_calibration_dual_source.py``/``test_s2_writer.py`` conventions: no live
Databricks or LLM calls — ``build_exec_dual_source_evidence``/``judge_claim`` and the
SQL executor are monkeypatched/mocked.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from eval.content.judge_harness import (
    JUDGE_HARNESS_RUNG,
    JUDGE_HARNESS_SURFACE,
    JUDGE_HARNESS_WRITER,
    build_claim_rows,
    judge_claims,
    run_judge_harness,
)
from eval.content.s2_writer import S2Writer
from eval.content.spot_check import SpotCheckClaim


def _run_ts() -> datetime:
    return datetime(2026, 8, 31, 12, 0, 0, 0, tzinfo=timezone.utc)


def _claim(claim_id: str, **overrides: object) -> SpotCheckClaim:
    base = dict(
        claim_id=claim_id,
        claim_text=f"claim text for {claim_id}",
        section="Business Overview",
        cited_chunk_id="c-1234",
        cited_locator_kind="section",
        cited_locator_value="Business Overview",
    )
    base.update(overrides)
    return SpotCheckClaim(**base)  # type: ignore[arg-type]


class RecordingSqlExecutor:
    """Minimal SqlExecutor stub: no marker/claim rows exist yet."""

    def __init__(self) -> None:
        self.statements: list[str] = []

    def __call__(self, statement: str) -> list[list[str]]:
        self.statements.append(statement)
        return []


def test_judge_claims_calls_dual_source_and_judge_per_claim(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def _fake_dual_source(_w, **kwargs):
        calls.append({"kind": "evidence", **kwargs})
        return [{"chunk_id": "c-1", "chunk_text": "evidence"}]

    def _fake_judge(**kwargs):
        calls.append({"kind": "judge", **kwargs})
        return {"verdict": "supported", "parse_failure": False, "raw_response": '{"verdict": "supported"}'}

    monkeypatch.setattr("eval.content.judge_harness.build_exec_dual_source_evidence", _fake_dual_source)
    monkeypatch.setattr("eval.content.judge_harness.judge_claim", _fake_judge)

    claims = (_claim("exec.claim.001"), _claim("exec.claim.002"))
    judged = judge_claims(
        MagicMock(),
        claims=claims,
        exec_analysis_cache={},
        company_slug="elder_care",
        catalog="uc13_ale",
        company="Elder Care",
        endpoint="databricks-claude-sonnet-4-6",
    )

    assert len(judged) == 2
    assert [c["claim"].claim_id for c in judged] == ["exec.claim.001", "exec.claim.002"]
    evidence_calls = [c for c in calls if c["kind"] == "evidence"]
    judge_calls = [c for c in calls if c["kind"] == "judge"]
    assert len(evidence_calls) == 2
    assert len(judge_calls) == 2
    assert judge_calls[0]["surface"] == JUDGE_HARNESS_SURFACE


def test_build_claim_rows_excludes_parse_failures() -> None:
    judged = [
        {
            "claim": _claim("exec.claim.001"),
            "judge_output": {"verdict": "supported", "parse_failure": False, "raw_response": "{}"},
        },
        {
            "claim": _claim("exec.claim.002"),
            "judge_output": {"verdict": None, "parse_failure": True, "raw_response": "not json"},
        },
    ]

    rows, parse_failures = build_claim_rows("elder_care", "20260831T120000Z-abc", _run_ts(), judged)

    assert parse_failures == 1
    assert len(rows) == 1
    assert rows[0].claim_id == "exec.claim.001"
    assert rows[0].verdict == "supported"
    assert rows[0].rationale  # non-null/non-empty per rungs 2-3 rationale_required contract
    assert rows[0].cited_chunk_id == "c-1234"


def test_build_claim_rows_falls_back_rationale_when_raw_response_blank() -> None:
    """Falsifier for _rationale_from_output: blank raw_response must not yield an empty rationale.

    S2Writer._validate_claim_row raises when rationale_required and rationale is None/blank
    (rungs 2-3) — mutating _rationale_from_output to return the raw text unconditionally
    (dropping the fallback) makes this test fail, because rows[0].rationale becomes "" and
    the assertion below fails.
    """
    judged = [
        {
            "claim": _claim("exec.claim.003"),
            "judge_output": {"verdict": "unsupported", "parse_failure": False, "raw_response": "   "},
        },
    ]

    rows, parse_failures = build_claim_rows("elder_care", "20260831T120000Z-abc", _run_ts(), judged)

    assert parse_failures == 0
    assert len(rows) == 1
    assert rows[0].rationale.strip() != ""
    assert "exec.claim.003" not in rows[0].rationale  # sanity: not accidentally echoing claim_id


def test_run_judge_harness_dry_run_does_not_write(monkeypatch) -> None:
    monkeypatch.setattr(
        "eval.content.judge_harness.build_exec_dual_source_evidence",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr(
        "eval.content.judge_harness.judge_claim",
        lambda **_k: {"verdict": "supported", "parse_failure": False, "raw_response": "{}"},
    )
    writer = MagicMock(spec=S2Writer)

    result = run_judge_harness(
        w=MagicMock(),
        writer=writer,
        claims=(_claim("exec.claim.001"),),
        exec_analysis_cache={},
        dry_run=True,
        run_id="20260831T120000Z-abc",
        run_ts=_run_ts(),
    )

    writer.write_claims.assert_not_called()
    writer.write_completion_marker.assert_not_called()
    assert result.written_count == 0
    assert result.claim_count == 1
    assert result.verdict_counts == {"supported": 1}


def test_run_judge_harness_execute_writes_claims_then_marker_with_resolver(monkeypatch) -> None:
    """Falsifier for the S-61 chunk_id_resolver wiring on the non-dry-run write path.

    Mutating run_judge_harness to omit chunk_id_resolver=... in the write_claims call
    (e.g. passing chunk_id_resolver=None unconditionally) makes this test fail because
    the assertion on call_kwargs below no longer matches the injected resolver.
    """
    monkeypatch.setattr(
        "eval.content.judge_harness.build_exec_dual_source_evidence",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr(
        "eval.content.judge_harness.judge_claim",
        lambda **_k: {"verdict": "contradicted", "parse_failure": False, "raw_response": "{}"},
    )
    writer = MagicMock(spec=S2Writer)
    resolver = MagicMock(return_value=frozenset({"c-1234"}))

    result = run_judge_harness(
        w=MagicMock(),
        writer=writer,
        claims=(_claim("exec.claim.001"),),
        exec_analysis_cache={},
        dry_run=False,
        chunk_id_resolver=resolver,
        run_id="20260831T120000Z-abc",
        run_ts=_run_ts(),
    )

    writer.write_claims.assert_called_once()
    call_args, call_kwargs = writer.write_claims.call_args
    assert call_kwargs["chunk_id_resolver"] is resolver
    assert call_kwargs["rung"] == JUDGE_HARNESS_RUNG
    assert call_kwargs["rationale_required"] is True
    assert call_args[1] == JUDGE_HARNESS_SURFACE

    writer.write_completion_marker.assert_called_once()
    marker_args, _marker_kwargs = writer.write_completion_marker.call_args
    assert marker_args[-1] == JUDGE_HARNESS_WRITER
    assert result.written_count == 1


def test_write_claims_end_to_end_against_real_s2writer_requires_resolver() -> None:
    """End-to-end (no mocks) exercise of the S-61 fail-closed guard through the real S2Writer."""
    recorder = RecordingSqlExecutor()
    writer = S2Writer(catalog="uc13_ale", sql_executor=recorder)
    judged = [
        {
            "claim": _claim("exec.claim.001"),
            "judge_output": {"verdict": "supported", "parse_failure": False, "raw_response": "{}"},
        }
    ]
    rows, _ = build_claim_rows("elder_care", "20260831T120000Z-abc", _run_ts(), judged)

    with pytest.raises(ValueError, match="chunk_id_resolver is required"):
        writer.write_claims(
            "elder_care",
            JUDGE_HARNESS_SURFACE,
            "20260831T120000Z-abc",
            _run_ts(),
            rows,
            rationale_required=True,
            rung=JUDGE_HARNESS_RUNG,
        )

    writer.write_claims(
        "elder_care",
        JUDGE_HARNESS_SURFACE,
        "20260831T120000Z-abc",
        _run_ts(),
        rows,
        rationale_required=True,
        rung=JUDGE_HARNESS_RUNG,
        chunk_id_resolver=lambda ids: ids,
    )
    assert any(s.strip().upper().startswith("INSERT") for s in recorder.statements)
