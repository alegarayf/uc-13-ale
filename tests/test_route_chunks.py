"""Unit tests for Route A metadata router (route_chunks)."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

from agents.shared._types import RouteResult  # noqa: E402
from agents.shared import route_chunks as route_chunks_module  # noqa: E402
from agents.shared.route_chunks import route_chunks  # noqa: E402


def _row(
    *,
    chunk_id: str = "c1",
    file_name: str = "CIM.pdf",
    chunk_text: str = "A" * 120,
    section_header: str = "Revenue",
    page_start: int = 1,
    source_type: str = "text",
    workstream: list[str] | None = None,
    priority_tier: int = 1,
):
    return SimpleNamespace(
        chunk_id=chunk_id,
        file_name=file_name,
        chunk_text=chunk_text,
        section_header=section_header,
        page_start=page_start,
        source_type=source_type,
        workstream=workstream or ["FINANCIAL"],
        priority_tier=priority_tier,
    )


def _mock_spark(rows: list, *, arrays_overlap_ok: bool = True) -> MagicMock:
    spark = MagicMock()
    probe_df = MagicMock()
    if arrays_overlap_ok:
        probe_df.collect.return_value = [SimpleNamespace(ok=True)]
    else:
        probe_df.collect.side_effect = Exception("arrays_overlap unavailable")
    route_df = MagicMock()
    route_df.collect.return_value = rows

    def sql_side_effect(query: str):
        if "arrays_overlap(array('A'), array('A'))" in query:
            return probe_df
        return route_df

    spark.sql.side_effect = sql_side_effect
    return spark


def test_route_result_shape_routed_mode():
    rows = [_row()]
    spark = _mock_spark(rows)
    result = route_chunks(
        "Acme Corp",
        spark,
        workstream_filter=["FINANCIAL"],
        top_k=5,
    )
    assert isinstance(result, RouteResult)
    assert result.mode == "routed"
    assert result.scores is None
    assert result.chunks == rows


def test_post_filters_file_name_min_length_and_source_type():
    rows = [
        _row(
            file_name="memo.txt",
            chunk_text="short",
            source_type="text",
            priority_tier=2,
        ),
        _row(
            file_name="CIM_Financial.pdf",
            chunk_text="B" * 150,
            source_type="table",
            priority_tier=1,
        ),
        _row(
            file_name="CIM_other.pdf",
            chunk_text="C" * 150,
            source_type="text",
            priority_tier=1,
        ),
    ]
    spark = _mock_spark(rows)
    result = route_chunks(
        "Acme Corp",
        spark,
        workstream_filter=["FINANCIAL"],
        top_k=10,
        file_name_filter=["CIM"],
        min_chunk_length=100,
        source_type_filter=["table"],
    )
    assert len(result.chunks) == 1
    assert result.chunks[0].file_name == "CIM_Financial.pdf"
    assert result.chunks[0].source_type == "table"


def test_sql_includes_tier_cap_and_workstream_overlap():
    rows = [_row(priority_tier=2)]
    spark = _mock_spark(rows)
    route_chunks(
        "O'Brien LLC",
        spark,
        workstream_filter=["FINANCIAL", "QUALITY_EARNINGS"],
        tier_filter=2,
        top_k=4,
    )
    sql = spark.sql.call_args_list[-1][0][0]
    assert "c.company_name = 'O''Brien LLC'" in sql
    assert "arrays_overlap(r.workstream, array('FINANCIAL', 'QUALITY_EARNINGS'))" in sql
    assert "r.priority_tier <= 2" in sql
    assert "r.should_parse = true" in sql
    assert "ORDER BY r.priority_tier ASC NULLS LAST, c.file_name, c.chunk_index" in sql
    assert "LIMIT 12" in sql


def test_workstream_or_chain_fallback_when_arrays_overlap_unavailable():
    route_chunks_module._ARRAYS_OVERLAP_AVAILABLE = None
    rows = [_row()]
    spark = _mock_spark(rows, arrays_overlap_ok=False)
    route_chunks("Acme", spark, workstream_filter=["FINANCIAL"], top_k=3)
    sql = spark.sql.call_args_list[-1][0][0]
    assert "array_contains(r.workstream, 'FINANCIAL')" in sql
    assert "arrays_overlap" not in sql


def test_keyword_filter_sanitized_into_sql_like_clauses():
    rows = [_row()]
    spark = _mock_spark(rows)
    route_chunks(
        "Acme",
        spark,
        workstream_filter=["FINANCIAL"],
        keyword_filter="revenue growth; margin!",
        top_k=5,
    )
    sql = spark.sql.call_args_list[-1][0][0]
    assert "c.chunk_text LIKE '%revenue%'" in sql
    assert "c.section_header LIKE '%growth%'" in sql
    assert "margin" in sql


def test_raises_value_error_when_no_chunks_remain():
    spark = _mock_spark([])
    with pytest.raises(ValueError, match="route_chunks: no results"):
        route_chunks("Acme", spark, workstream_filter=["FINANCIAL"], top_k=5)


def test_all_chunks_filtered_out_by_min_length_raises():
    spark = _mock_spark([_row(chunk_text="tiny")])
    with pytest.raises(ValueError, match="route_chunks: no results"):
        route_chunks(
            "Acme",
            spark,
            workstream_filter=["FINANCIAL"],
            min_chunk_length=100,
            top_k=5,
        )
