"""Hermetic tests for §8.4 two-backend ingest preflight — M4 T5."""

from __future__ import annotations

from typing import Any

import pytest

from eval.retrieval.ingest_preflight import (
    IngestPreflightError,
    IngestProbeResult,
    format_preflight_summary,
    run_ingest_preflight,
)
from eval.retrieval.trust_statement import IngestProbeResult as TrustIngestProbeResult


class _SparkRow:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]


class _SparkResult:
    def __init__(self, rows: list[_SparkRow]) -> None:
        self._rows = rows

    def collect(self) -> list[_SparkRow]:
        return self._rows


class _MockSpark:
    def __init__(self, rows: list[_SparkRow] | None = None, *, fail: bool = False) -> None:
        self._rows = rows or []
        self._fail = fail

    def sql(self, _sql: str) -> _SparkResult:
        if self._fail:
            raise RuntimeError("spark unavailable")
        return _SparkResult(self._rows)


def test_result_type_is_the_trust_statement_dataclass() -> None:
    assert IngestProbeResult is TrustIngestProbeResult


def test_unknown_backend_rejected() -> None:
    with pytest.raises(IngestPreflightError, match="unknown ingest preflight backend"):
        run_ingest_preflight(
            backend="made_up",  # type: ignore[arg-type]
            company_slug="elder_care",
            catalog="uc13_ale",
            company_display="Elder Care",
            execute_sql=lambda _sql: [],
        )


def test_sql_chunk_count_requires_execute_sql() -> None:
    with pytest.raises(IngestPreflightError, match="requires execute_sql"):
        run_ingest_preflight(
            backend="sql_chunk_count",
            company_slug="elder_care",
            catalog="uc13_ale",
            company_display="Elder Care",
        )


def test_doc_status_requires_spark() -> None:
    with pytest.raises(IngestPreflightError, match="requires spark"):
        run_ingest_preflight(
            backend="doc_status",
            company_slug="elder_care",
            catalog="uc13_ale",
            company_display="Elder Care",
        )


def test_wrong_injection_pair_rejected() -> None:
    with pytest.raises(IngestPreflightError, match="must not receive spark"):
        run_ingest_preflight(
            backend="sql_chunk_count",
            company_slug="elder_care",
            catalog="uc13_ale",
            company_display="Elder Care",
            execute_sql=lambda _sql: [["10", "8"]],
            spark=_MockSpark(),
        )

    with pytest.raises(IngestPreflightError, match="must not receive execute_sql"):
        run_ingest_preflight(
            backend="doc_status",
            company_slug="elder_care",
            catalog="uc13_ale",
            company_display="Elder Care",
            execute_sql=lambda _sql: [],
            spark=_MockSpark(),
        )


def test_both_backends_satisfy_return_contract() -> None:
    sql_result = run_ingest_preflight(
        backend="sql_chunk_count",
        company_slug="elder_care",
        catalog="uc13_ale",
        company_display="Elder Care",
        execute_sql=lambda sql: [["10", "8"]] if "GROUP BY" not in sql else [["FINANCIAL", "10", "8"]],
    )
    doc_result = run_ingest_preflight(
        backend="doc_status",
        company_slug="elder_care",
        catalog="uc13_ale",
        company_display="Elder Care",
        spark=_MockSpark([_SparkRow({"status": "COMPLETE", "cnt": 5})]),
    )

    for result in (sql_result, doc_result):
        assert isinstance(result, IngestProbeResult)
        assert result.company == "elder_care"
        assert result.catalog == "uc13_ale"
        assert result.backend in {"sql_chunk_count", "doc_status"}
        assert result.status in {"measured", "denominator_undefined", "probe_failed"}


def test_sql_chunk_count_measured_status_reachable() -> None:
    result = run_ingest_preflight(
        backend="sql_chunk_count",
        company_slug="elder_care",
        catalog="uc13_ale",
        company_display="Elder Care",
        execute_sql=lambda sql: [["412", "214"]] if "GROUP BY" not in sql else [],
    )
    assert result.status == "measured"
    assert result.backend == "sql_chunk_count"
    assert result.completeness == pytest.approx(214 / 412)
    assert result.denominator == 412


def test_sql_chunk_count_denominator_undefined_reachable() -> None:
    result = run_ingest_preflight(
        backend="sql_chunk_count",
        company_slug="elder_care",
        catalog="uc13_ale",
        company_display="Elder Care",
        execute_sql=lambda _sql: [["0", "0"]],
    )
    assert result.status == "denominator_undefined"
    assert result.completeness is None
    assert result.denominator is None


def test_sql_chunk_count_probe_failed_never_raises() -> None:
    def _boom(_sql: str) -> list[list[str | None]]:
        raise RuntimeError("warehouse down")

    result = run_ingest_preflight(
        backend="sql_chunk_count",
        company_slug="elder_care",
        catalog="uc13_ale",
        company_display="Elder Care",
        execute_sql=_boom,
    )
    assert result.status == "probe_failed"
    assert result.backend == "sql_chunk_count"


def test_doc_status_denominator_undefined_reachable() -> None:
    result = run_ingest_preflight(
        backend="doc_status",
        company_slug="elder_care",
        catalog="uc13_ale",
        company_display="Elder Care",
        spark=_MockSpark([_SparkRow({"status": "COMPLETE", "cnt": 12})]),
    )
    assert result.status == "denominator_undefined"
    assert result.backend == "doc_status"
    assert result.completeness is None
    assert result.denominator is None


def test_doc_status_probe_failed_never_raises() -> None:
    result = run_ingest_preflight(
        backend="doc_status",
        company_slug="elder_care",
        catalog="uc13_ale",
        company_display="Elder Care",
        spark=_MockSpark(fail=True),
    )
    assert result.status == "probe_failed"
    assert result.backend == "doc_status"


def test_format_preflight_summary_names_slug_and_catalog() -> None:
    result = IngestProbeResult(
        company="elder_care",
        catalog="uc13_ale",
        backend="sql_chunk_count",
        status="measured",
        completeness=0.52,
        denominator=412,
    )
    summary = format_preflight_summary(result)
    assert "elder_care" in summary
    assert "uc13_ale" in summary
    assert "backend=sql_chunk_count" in summary
