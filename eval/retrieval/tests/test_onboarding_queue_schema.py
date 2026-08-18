"""Hermetic schema and ranking tests for onboarding_queue.yaml — M5 T5 / spec D5."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_QUEUE_PATH = _REPO_ROOT / "eval" / "program" / "onboarding_queue.yaml"

import importlib.util
import sys

_spec = importlib.util.spec_from_file_location(
    "build_onboarding_queue",
    _REPO_ROOT / ".dev" / "eval-program" / "build_onboarding_queue.py",
)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

REQUIRED_COMPANY_FIELDS = _mod.REQUIRED_COMPANY_FIELDS
CompanyInventoryRow = _mod.CompanyInventoryRow
build_company_row = _mod.build_company_row
compute_doc_type_diversity_score = _mod.compute_doc_type_diversity_score
compute_rank_score = _mod.compute_rank_score
rank_companies = _mod.rank_companies
validate_queue_document = _mod.validate_queue_document


def _load_committed_queue() -> dict[str, Any]:
    return yaml.safe_load(_QUEUE_PATH.read_text(encoding="utf-8"))


def test_committed_queue_schema_version_and_companies() -> None:
    document = _load_committed_queue()
    validate_queue_document(document)
    assert document["schema_version"] == 1
    assert len(document["companies"]) >= 1


def test_committed_queue_required_fields_on_every_company() -> None:
    document = _load_committed_queue()
    for company in document["companies"]:
        for field in REQUIRED_COMPANY_FIELDS:
            assert field in company


def test_doc_type_diversity_score_normalizes_to_unit_interval() -> None:
    assert compute_doc_type_diversity_score(3, 6) == 0.5
    assert compute_doc_type_diversity_score(0, 0) == 0.0


def test_rank_score_null_when_preflight_not_measured() -> None:
    assert compute_rank_score(None, 1.0) is None
    assert compute_rank_score(0.98, 1.0) == pytest.approx(0.98)


def test_rank_companies_null_preflight_sorts_after_measured() -> None:
    """Falsifier for D5 null-preflight sort rule."""
    measured = CompanyInventoryRow(
        display_name="Measured Co",
        slug="measured_co",
        chunk_count=100,
        ingest_completeness_ratio=0.5,
        doc_type_diversity_score=1.0,
        rank_score=0.5,
        wave="W3",
        notes="",
    )
    unmeasured_high_chunks = CompanyInventoryRow(
        display_name="Unmeasured High",
        slug="unmeasured_high",
        chunk_count=99999,
        ingest_completeness_ratio=None,
        doc_type_diversity_score=0.8,
        rank_score=None,
        wave="W3",
        notes="preflight_not_run",
    )
    ranked = rank_companies([unmeasured_high_chunks, measured])
    assert ranked[0].slug == "measured_co"
    assert ranked[1].slug == "unmeasured_high"


class _FixtureSqlExecutor:
    """Hermetic SQL fixture path for build_company_row (no live warehouse)."""

    def __init__(self, responses: dict[str, list[list[str | None]]]) -> None:
        self._responses = responses

    def __call__(self, sql: str) -> list[list[str | None]]:
        for key, rows in self._responses.items():
            if key in sql:
                return rows
        if "COUNT(DISTINCT doc_id)" in sql and "denominator" in sql:
            return [["10", "10"]]
        if "GROUP BY e.doc_type" in sql:
            return []
        raise AssertionError(f"unexpected SQL in fixture: {sql[:120]!r}")


def test_build_company_row_fixture_sql_path() -> None:
    execute = _FixtureSqlExecutor(
        {
            "category_stats": [["4", "3"]],
        }
    )
    row = build_company_row(
        execute,
        catalog="uc13_ale",
        display_name="Fixture Co",
        chunk_count=42,
        preflight_mode="documented",
        company_count=1,
    )
    assert row.slug == "fixture_co"
    assert row.doc_type_diversity_score == 0.75
    assert row.ingest_completeness_ratio is None
    assert row.rank_score is None
    assert row.notes == "preflight_not_run"
