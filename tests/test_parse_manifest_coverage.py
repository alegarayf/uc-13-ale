"""Spark-free regression tests for the coverage sub-pass flag provenance (M0 / T6, audit F1).

`coverage_injected` must be TRUE iff a doc entered the work list via the coverage
sub-pass (a genuine SKIP->work-list rescue, or a fresh add), NOT because it was already
admitted by the tier-filtered main pass. F1 was an unconditional flag-set on any
already-resolved coverage candidate; these two cases pin both directions.

The exercised branch (`existing is not None` early-return in `_inject_coverage_doc`) is
in-memory only: no SparkSession, no filesystem. `ParseManifest.__init__` merely stores
`spark/catalog/schema/company`, so `spark=None` is sufficient.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace

# --- sys.path shim (mirrors tests/test_make_doc_id.py) ------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = _REPO_ROOT / "databricks" / "jobs" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# --- Spark-free stub (mirrors tests/test_ingestion_parser_sync.py) ------------------
# parse_manifest -> status_store import pyspark at module load; the suite has no real
# pyspark. Provide a stub and guarantee every type name status_store needs is present,
# even if an earlier-collected test module installed a narrower stub (e.g. without
# LongType).
if "pyspark" not in sys.modules:
    _pyspark_mod = types.ModuleType("pyspark")
    _sql_mod = types.ModuleType("pyspark.sql")

    class _SparkSession:  # pragma: no cover - annotation target only
        @staticmethod
        def getActiveSession():
            return None

    _sql_mod.SparkSession = _SparkSession
    _sql_mod.Row = lambda **kwargs: SimpleNamespace(**kwargs)
    _pyspark_mod.sql = _sql_mod
    sys.modules["pyspark"] = _pyspark_mod
    sys.modules["pyspark.sql"] = _sql_mod

if "pyspark.sql.types" not in sys.modules:
    _types_mod = types.ModuleType("pyspark.sql.types")
    sys.modules["pyspark.sql.types"] = _types_mod
    sys.modules["pyspark.sql"].types = _types_mod


class _StubSparkType:  # pragma: no cover - construction-only stub
    def __init__(self, *args, **kwargs):
        pass


for _name in (
    "StructType",
    "StructField",
    "StringType",
    "IntegerType",
    "LongType",
    "BooleanType",
    "ArrayType",
    "FloatType",
    "TimestampType",
):
    if not hasattr(sys.modules["pyspark.sql.types"], _name):
        setattr(sys.modules["pyspark.sql.types"], _name, _StubSparkType)

from parse_manifest import (  # noqa: E402
    ParseManifest,
    ManifestSummary,
    _ApprovedDoc,
    _ResolvedDoc,
    _CLASSIFICATION_NEW,
    _CLASSIFICATION_SKIP,
)

_CATALOG = "uc13"
_SCHEMA = "ingestion"
_COMPANY = "Elder Care"


def _manifest() -> ParseManifest:
    return ParseManifest(spark=None, catalog=_CATALOG, schema=_SCHEMA, company=_COMPANY)


def _approved() -> _ApprovedDoc:
    return _ApprovedDoc(
        file_name="report.pdf",
        folder_path="Financials",
        workstreams=("financial_trends",),
        priority_tier=1,
    )


def _resolved(pm: ParseManifest, approved: _ApprovedDoc, classification: str) -> _ResolvedDoc:
    return _ResolvedDoc(
        approved=approved,
        doc_id=pm._doc_id_for_approved(approved),
        relative_path="Financials/report.pdf",
        full_path=f"/Volumes/{_CATALOG}/{_SCHEMA}/raw_files/{_COMPANY}/Financials/report.pdf",
        source_mtime=0,
        source_size=0,
        classification=classification,
        coverage_injected=False,
    )


def test_in_tier_already_resolved_doc_not_flagged() -> None:
    """F1 regression: a NEW doc already admitted by the main tier pass, re-seen as a
    coverage candidate, keeps coverage_injected=False and its classification/count."""
    pm = _manifest()
    approved = _approved()
    existing = _resolved(pm, approved, _CLASSIFICATION_NEW)
    resolved_by_id = {existing.doc_id: existing}
    summary = ManifestSummary()
    summary.classification_counts[_CLASSIFICATION_NEW] = 1

    pm._inject_coverage_doc(
        approved,
        _CLASSIFICATION_NEW,
        status_map={},
        force_all=False,
        force_ids=set(),
        summary=summary,
        resolved_by_id=resolved_by_id,
    )

    assert existing.coverage_injected is False
    assert existing.classification == _CLASSIFICATION_NEW
    assert summary.classification_counts[_CLASSIFICATION_NEW] == 1


def test_skip_rescue_flips_flag_and_reclassifies() -> None:
    """A SKIP doc (not in the work list) rescued by the coverage sub-pass gets
    coverage_injected=True, is reclassified, and the counts move (SKIP -1, new +1)."""
    pm = _manifest()
    approved = _approved()
    existing = _resolved(pm, approved, _CLASSIFICATION_SKIP)
    resolved_by_id = {existing.doc_id: existing}
    summary = ManifestSummary()
    summary.classification_counts[_CLASSIFICATION_SKIP] = 1

    pm._inject_coverage_doc(
        approved,
        _CLASSIFICATION_NEW,
        status_map={},
        force_all=False,
        force_ids=set(),
        summary=summary,
        resolved_by_id=resolved_by_id,
    )

    assert existing.coverage_injected is True
    assert existing.classification == _CLASSIFICATION_NEW
    assert summary.classification_counts[_CLASSIFICATION_SKIP] == 0
    assert summary.classification_counts[_CLASSIFICATION_NEW] == 1
