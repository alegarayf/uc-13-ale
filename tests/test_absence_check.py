"""Unit tests for agents.exec_summary.absence_check — the false-absence
verification pass (docs/plans/connect-all-vdr-er.md Part B, B2).

Root cause this module exists for: a bundle field can read as an absence
claim ("not stated in available materials") purely because a workstream
agent's extraction schema has no home for the underlying concept — even
though the data room genuinely has material on it (confirmed on a real run:
Elder Care's CIM "Referral Source Mix" chart was ingested, but
customer_quality_agent has no referral-source field). This module checks a
handful of such fields against a cheap semantic search before the Rainmaker
narrative ever sees them.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

_DATABRICKS_ROOT = Path(__file__).resolve().parents[1] / "databricks"
if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))

from agents.exec_summary.absence_check import RECLASSIFIED_PREFIX, verify_bundle_claims


def _bundle(**revenue_quality_overrides) -> dict:
    return {
        "revenue_quality": {
            "concentration": "",
            "retention_notes": "",
            "end_market_mix": "",
            **revenue_quality_overrides,
        },
        "company_framing": {"revenue_model": {"tag": "x", "quality_flag": "y", "note": ""}},
    }


def _route(chunks):
    route = MagicMock()
    route.chunks = chunks
    return route


def _chunk(file_name: str):
    row = MagicMock()
    row.file_name = file_name
    return row


def test_empty_field_with_supporting_chunks_is_reclassified(monkeypatch):
    search_mock = MagicMock(return_value=_route([_chunk("CIM.pdf"), _chunk("CIM.pdf")]))
    monkeypatch.setattr("agents.shared.retrieval.semantic_search", search_mock)

    result = verify_bundle_claims(_bundle(), spark=MagicMock(), catalog="uc13_preview", company_name="Elder Care")

    concentration = result["revenue_quality"]["concentration"]
    assert concentration.startswith(RECLASSIFIED_PREFIX)
    assert "CIM.pdf" in concentration
    assert "2" in concentration  # chunk count is reported


def test_empty_field_with_no_supporting_chunks_is_left_untouched(monkeypatch):
    search_mock = MagicMock(return_value=_route([]))
    monkeypatch.setattr("agents.shared.retrieval.semantic_search", search_mock)

    bundle = _bundle()
    result = verify_bundle_claims(bundle, spark=MagicMock(), catalog="uc13_preview", company_name="Elder Care")

    assert result["revenue_quality"]["concentration"] == ""
    assert result == bundle  # a genuine gap — nothing reclassified


def test_populated_field_is_never_checked_or_touched(monkeypatch):
    """A real value is never second-guessed — the check only ever looks at
    fields that are already blank."""
    search_mock = MagicMock(side_effect=AssertionError("must not search a populated field"))
    monkeypatch.setattr("agents.shared.retrieval.semantic_search", search_mock)

    bundle = _bundle(concentration="Top 3 referral sources = 61% of revenue.")
    result = verify_bundle_claims(bundle, spark=MagicMock(), catalog="uc13_preview", company_name="Elder Care")

    assert result["revenue_quality"]["concentration"] == "Top 3 referral sources = 61% of revenue."


def test_never_mutates_the_input_bundle(monkeypatch):
    monkeypatch.setattr(
        "agents.shared.retrieval.semantic_search",
        MagicMock(return_value=_route([_chunk("CIM.pdf")])),
    )
    bundle = _bundle()
    verify_bundle_claims(bundle, spark=MagicMock(), catalog="uc13_preview", company_name="Elder Care")
    assert bundle["revenue_quality"]["concentration"] == ""  # original untouched


def test_retrieval_failure_degrades_to_leaving_the_field_unchanged(monkeypatch):
    monkeypatch.setattr(
        "agents.shared.retrieval.semantic_search",
        MagicMock(side_effect=RuntimeError("vector search endpoint unavailable")),
    )
    bundle = _bundle()
    result = verify_bundle_claims(bundle, spark=MagicMock(), catalog="uc13_preview", company_name="Elder Care")
    assert result == bundle  # never raises, never half-applies a change


def test_import_failure_degrades_to_returning_bundle_unchanged(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def _boom(name, *args, **kwargs):
        if name == "agents.shared.retrieval":
            raise ImportError("simulated import failure")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _boom)
    bundle = _bundle()
    result = verify_bundle_claims(bundle, spark=MagicMock(), catalog="uc13_preview", company_name="Elder Care")
    assert result == bundle


def test_catalog_and_company_are_forwarded_to_the_search(monkeypatch):
    """Catalog-agnostic by construction — both VDR branches must be able to
    call this with their own catalog and have it actually scope the search."""
    search_mock = MagicMock(return_value=_route([]))
    monkeypatch.setattr("agents.shared.retrieval.semantic_search", search_mock)

    verify_bundle_claims(_bundle(), spark=MagicMock(), catalog="some_other_catalog", company_name="GKF")

    for call in search_mock.call_args_list:
        _, kwargs = call
        assert kwargs["catalog"] == "some_other_catalog"
        assert kwargs["company_name"] == "GKF"
