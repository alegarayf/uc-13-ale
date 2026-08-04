"""Thin get_coverage_report contract tests (M2 T4)."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = _REPO_ROOT / "databricks" / "jobs" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import ensure_coverage as ec  # noqa: E402
from status_store import COMPLETE, StatusRow  # noqa: E402

_TS = datetime(2026, 8, 4, 12, 0, 0, tzinfo=timezone.utc)


def _status_row(file_name: str, status: str = COMPLETE) -> StatusRow:
    return StatusRow(
        company_name="Elder Care",
        doc_id=f"doc-{file_name}",
        file_name=file_name,
        relative_path="",
        status=status,
        chunk_count=1,
        source_mtime=0,
        source_size=0,
        content_hash=None,
        coverage_injected=False,
        parser_version="v1",
        run_id="run-1",
        error=None,
        updated_at=_TS,
    )


def test_get_coverage_report_shape_unchanged():
    """Falsifier: thin query must preserve the dict contract print_coverage_report expects."""
    spark = MagicMock()
    spark.sql.return_value.collect.return_value = [
        SimpleNamespace(filename="a.pdf", workstream=["FINANCIAL"], priority_tier=1),
        SimpleNamespace(filename="b.pdf", workstream=["FINANCIAL", "LEGAL"], priority_tier=2),
        SimpleNamespace(filename="c.pdf", workstream=["LEGAL"], priority_tier=2),
    ]
    status_map = {
        "doc-a": _status_row("a.pdf"),
        "doc-c": _status_row("c.pdf"),
    }

    with patch("status_store.StatusStore.read_status_map", return_value=status_map):
        report = ec.get_coverage_report(
            company_name="Elder Care",
            catalog="uc13",
            tiers=[1, 2],
            spark=spark,
        )

    assert set(report.keys()) == {
        "company_name",
        "tiers_checked",
        "total_approved",
        "total_ingested",
        "total_missing",
        "by_workstream",
    }
    assert report["company_name"] == "Elder Care"
    assert report["tiers_checked"] == [1, 2]
    assert report["total_approved"] == 3
    assert report["total_ingested"] == 2
    assert report["total_missing"] == 1

    by_ws = report["by_workstream"]
    assert set(by_ws.keys()) == {"FINANCIAL", "LEGAL"}
    for ws_counts in by_ws.values():
        assert set(ws_counts.keys()) == {"approved", "ingested", "missing"}
        assert all(isinstance(v, list) for v in ws_counts.values())

    assert by_ws["FINANCIAL"]["approved"] == ["a.pdf", "b.pdf"]
    assert by_ws["FINANCIAL"]["ingested"] == ["a.pdf"]
    assert by_ws["FINANCIAL"]["missing"] == ["b.pdf"]
    assert by_ws["LEGAL"]["ingested"] == ["c.pdf"]
    assert by_ws["LEGAL"]["missing"] == ["b.pdf"]
