"""Unit tests for per-company attestation measurement (M4 T6)."""

from __future__ import annotations

import pytest

from eval.retrieval.measure_attestation import (
    _attestation_error_sql,
    _attestation_status_sql,
    _vision_share_sql,
    format_attestation_phv_line,
    run_attestation_query,
    run_vision_share_query,
)


class _StubRow:
    def __init__(self, **fields: object) -> None:
        self._fields = fields

    def __getitem__(self, key: str) -> object:
        return self._fields[key]


class _StubSparkResult:
    def __init__(self, rows: list[_StubRow]) -> None:
        self._rows = rows

    def collect(self) -> list[_StubRow]:
        return self._rows


class _StubSpark:
    def __init__(
        self,
        status_rows: list[_StubRow],
        error_rows: list[_StubRow] | None = None,
        vision_rows: list[_StubRow] | None = None,
    ) -> None:
        self._status_rows = status_rows
        self._error_rows = error_rows or []
        self._vision_rows = vision_rows or []
        self.sql_calls: list[str] = []

    def sql(self, query: str) -> _StubSparkResult:
        self.sql_calls.append(query)
        normalized = " ".join(query.split())
        if "GROUP BY status, error" in normalized:
            return _StubSparkResult(self._error_rows)
        if "GROUP BY status" in normalized and "doc_status" in normalized:
            return _StubSparkResult(self._status_rows)
        if "GROUP BY source_type" in normalized:
            return _StubSparkResult(self._vision_rows)
        raise AssertionError(f"unexpected SQL: {query}")


_CATALOG = "uc13_ale"
_SCHEMA = "ingestion"
_COMPANY = "Elder Care"


def test_attestation_status_sql_targets_doc_status_group_by_status() -> None:
    sql = _attestation_status_sql(_CATALOG, _SCHEMA, _COMPANY)
    assert f"{_CATALOG}.{_SCHEMA}.doc_status" in sql
    assert "GROUP BY status" in sql
    assert f"company_name = '{_COMPANY}'" in sql


def test_attestation_error_sql_targets_non_complete_rows() -> None:
    sql = _attestation_error_sql(_CATALOG, _SCHEMA, "O'Brien Care")
    assert "status != 'COMPLETE'" in sql
    assert "GROUP BY status, error" in sql
    assert "company_name = 'O''Brien Care'" in sql


def test_vision_share_sql_targets_chunks_group_by_source_type() -> None:
    sql = _vision_share_sql(_CATALOG, _SCHEMA, _COMPANY)
    assert f"{_CATALOG}.{_SCHEMA}.chunks" in sql
    assert "GROUP BY source_type" in sql
    assert f"company_name = '{_COMPANY}'" in sql


def test_run_attestation_query_return_shape_and_sql() -> None:
    spark = _StubSpark(
        status_rows=[
            _StubRow(status="COMPLETE", cnt=375),
            _StubRow(status="FAILED", cnt=4),
        ],
        error_rows=[
            _StubRow(status="FAILED", error="PARSE_EXCEPTION: corrupt pdf", cnt=4),
        ],
    )

    result = run_attestation_query(spark, _CATALOG, _SCHEMA, _COMPANY)

    assert result["total"] == 379
    assert result["status_counts"] == {"COMPLETE": 375, "FAILED": 4}
    assert result["failed_details"] == [
        {
            "status": "FAILED",
            "error": "PARSE_EXCEPTION: corrupt pdf",
            "count": 4,
        }
    ]
    assert len(spark.sql_calls) == 2
    assert "doc_status" in spark.sql_calls[0]
    assert "status != 'COMPLETE'" in spark.sql_calls[1]


def test_format_attestation_phv_line_matches_charter_g5_example() -> None:
    result = {
        "total": 379,
        "status_counts": {"COMPLETE": 375, "FAILED": 4},
        "failed_details": [
            {
                "status": "FAILED",
                "error": "PARSE_EXCEPTION: corrupt pdf",
                "count": 4,
            }
        ],
    }

    line = format_attestation_phv_line(result)

    assert line == (
        "379 approved, 375 complete, 4 failed with reason "
        "PARSE_EXCEPTION: corrupt pdf (4)"
    )


def test_run_vision_share_query_return_shape_and_sql() -> None:
    spark = _StubSpark(
        status_rows=[],
        vision_rows=[
            _StubRow(source_type="text", cnt=100),
            _StubRow(source_type="vision", cnt=250),
            _StubRow(source_type="table", cnt=50),
        ],
    )

    result = run_vision_share_query(spark, _CATALOG, _SCHEMA, _COMPANY)

    assert result["source_type_counts"] == {
        "text": 100,
        "vision": 250,
        "table": 50,
    }
    assert result["total_chunks"] == 400
    assert len(spark.sql_calls) == 1
    assert "chunks" in spark.sql_calls[0]
    assert "GROUP BY source_type" in spark.sql_calls[0]


def test_attestation_and_vision_share_queries_use_distinct_tables() -> None:
    status_sql = _attestation_status_sql(_CATALOG, _SCHEMA, _COMPANY)
    vision_sql = _vision_share_sql(_CATALOG, _SCHEMA, _COMPANY)

    assert "doc_status" in status_sql
    assert "chunks" not in status_sql
    assert "chunks" in vision_sql
    assert "doc_status" not in vision_sql


def test_format_attestation_phv_line_zero_failed_omits_reason_clause() -> None:
    result = {
        "total": 10,
        "status_counts": {"COMPLETE": 10},
        "failed_details": [],
    }

    assert format_attestation_phv_line(result) == "10 approved, 10 complete"


@pytest.mark.parametrize(
    "company",
    ["Elder Care", "Acme's Docs"],
    ids=["plain", "apostrophe"],
)
def test_sql_literals_escape_company_name(company: str) -> None:
    sql = _attestation_status_sql(_CATALOG, _SCHEMA, company)
    expected = company.replace("'", "''")
    assert f"company_name = '{expected}'" in sql
