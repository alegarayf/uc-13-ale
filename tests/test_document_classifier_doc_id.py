"""doc_id write path + backfill contract tests (M3 / T1)."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = _REPO_ROOT / "databricks" / "jobs" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from doc_id import make_doc_id  # noqa: E402
import document_classifier as dc  # noqa: E402

_CATALOG = "uc13"
_SCHEMA = "ingestion"
_COMPANY = "Elder Care"
_TABLE = f"{_CATALOG}.classification.doc_relevance"


def _base_kwargs() -> dict:
    return {
        "company_name": _COMPANY,
        "catalog": _CATALOG,
        "schema": _SCHEMA,
        "filename": "annual_report.pdf",
        "folder_path": "Financials",
        "workstream": ["FINANCIAL"],
        "priority_tier": 1,
        "priority_reason": "audited financials",
        "should_parse": True,
        "extraction_confidence": "high",
        "mod_date": "2026-01-15",
        "format_": "pdf",
    }


def test_classification_record_includes_doc_id() -> None:
    record = dc._build_classification_record(**_base_kwargs())

    expected_doc_id = make_doc_id(
        _CATALOG, _SCHEMA, _COMPANY, "Financials", "annual_report.pdf",
    )
    assert record["doc_id"] == expected_doc_id
    assert record["filename"] == "annual_report.pdf"
    assert record["folder_path"] == "Financials"
    assert record["document_id"]


@pytest.mark.parametrize(
    ("workstream", "priority_tier", "priority_reason", "should_parse", "confidence"),
    [
        (["FINANCIAL"], 1, "batch-success", True, "high"),
        (["LEGAL"], 2, "individual-retry-success", True, "medium"),
        (["BACKGROUND"], None, None, False, "low"),
    ],
    ids=["batch-success", "individual-retry-success", "individual-retry-fallback"],
)
def test_classification_record_all_three_call_sites_populate_doc_id(
    workstream: list[str],
    priority_tier: int | None,
    priority_reason: str | None,
    should_parse: bool,
    confidence: str,
) -> None:
    """Each classifier row-construction path must stamp the same doc_id constructor."""
    kwargs = _base_kwargs()
    kwargs.update(
        workstream=workstream,
        priority_tier=priority_tier,
        priority_reason=priority_reason,
        should_parse=should_parse,
        extraction_confidence=confidence,
    )
    record = dc._build_classification_record(**kwargs)

    assert record["doc_id"] == make_doc_id(
        _CATALOG, _SCHEMA, _COMPANY, kwargs["folder_path"], kwargs["filename"],
    )


def test_backfill_computes_doc_id_from_stored_folder_path_and_filename() -> None:
    spark = MagicMock()
    spark.sql.return_value.collect.return_value = [
        SimpleNamespace(
            company_name=_COMPANY,
            filename="contract.pdf",
            folder_path="Legal",
        ),
        SimpleNamespace(
            company_name=_COMPANY,
            filename="root.docx",
            folder_path=".",
        ),
    ]

    merge_builder = MagicMock()
    merge_builder.whenMatchedUpdate.return_value = merge_builder
    delta_table = MagicMock()
    delta_table.alias.return_value.merge.return_value = merge_builder

    expected_ids = [
        make_doc_id(_CATALOG, _SCHEMA, _COMPANY, "Legal", "contract.pdf"),
        make_doc_id(_CATALOG, _SCHEMA, _COMPANY, ".", "root.docx"),
    ]

    mock_delta = MagicMock()
    mock_delta.tables.DeltaTable.forName.return_value = delta_table
    with patch.dict(sys.modules, {"delta": mock_delta, "delta.tables": mock_delta.tables}):
        updated = dc._backfill_missing_doc_ids(spark, _CATALOG, _SCHEMA, _TABLE)

    assert updated == 2
    spark.sql.assert_called_once()
    assert "doc_id IS NULL" in spark.sql.call_args[0][0]
    merge_call = delta_table.alias.return_value.merge
    merge_call.assert_called_once()
    merge_predicate = merge_call.call_args[0][1]
    assert "coalesce(t.folder_path, '') = coalesce(s.folder_path, '')" in merge_predicate
    merge_builder.whenMatchedUpdate.assert_called_once_with(set={"doc_id": "s.doc_id"})

    created_rows = spark.createDataFrame.call_args[0][0]
    assert [row.doc_id for row in created_rows] == expected_ids


def test_build_classification_record_folder_path_dot_matches_root_doc_id() -> None:
    """Falsifier: folder_path '.' must not bypass make_doc_id sentinel normalization."""
    record = dc._build_classification_record(
        **_base_kwargs() | {"folder_path": ".", "filename": "root_only.pdf"},
    )
    expected = make_doc_id(_CATALOG, _SCHEMA, _COMPANY, None, "root_only.pdf")
    assert record["doc_id"] == expected
