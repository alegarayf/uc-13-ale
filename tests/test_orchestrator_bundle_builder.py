"""Unit tests for M2 BundleBuilder — field mapping (T1 stub; full suite lands T5)."""

from __future__ import annotations

from agents.orchestrator.constants import (
    AGENT_DELTA_TABLE_SUFFIXES,
    AGENTS_PRESENT_KEYS,
    TLDR_REQUIRED_FIELDS,
)
from agents.orchestrator.field_mapping import FIELD_MAPPINGS, tldr_bundle_paths


def test_field_mapping_rows_cover_appendix_b():
    """Every TLDR_REQUIRED_FIELDS path has a required_for_tldr FIELD_MAPPINGS row."""
    mapped = tldr_bundle_paths()
    for path in TLDR_REQUIRED_FIELDS:
        assert path in mapped, f"Appendix B / TLDR_REQUIRED_FIELDS path missing: {path}"
    assert len(FIELD_MAPPINGS) >= len(TLDR_REQUIRED_FIELDS)


def test_agent_delta_table_suffixes_round_trip():
    """AGENT_DELTA_TABLE_SUFFIXES keys match AGENTS_PRESENT_KEYS (D-M2-8)."""
    assert set(AGENT_DELTA_TABLE_SUFFIXES) == set(AGENTS_PRESENT_KEYS)
    for key in AGENTS_PRESENT_KEYS:
        assert AGENT_DELTA_TABLE_SUFFIXES[key] == key
