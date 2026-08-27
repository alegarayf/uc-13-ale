"""Tests for cache-free exec_summary truncation source locators (T7)."""

from eval.content.spot_check import _CACHE_FREE_TRUNCATION_SOURCES


def test_cache_free_truncation_source_exec_claim_008_resolves_historical_pl_summary() -> None:
    """exec.claim.008 must cite Historical P&L Summary, not Pro Forma Income Statement."""
    assert _CACHE_FREE_TRUNCATION_SOURCES["exec.claim.008"] == (
        "2024 Elder Care - CIM_vF.pdf",
        "Historical P&L Summary",
    )
