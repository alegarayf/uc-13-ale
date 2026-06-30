"""Unit tests for BundleBuilder and GapAggregator (M2 T3)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agents.orchestrator.bundle_builder import (
    BundleBuilder,
    GapAggregator,
    merge_risks_from_flags,
)
from agents.orchestrator.constants import AGENTS_PRESENT_KEYS
from agents.orchestrator.validate import BundleValidationError


def test_gap_aggregator_dedupes_on_normalized_text_and_source_agent() -> None:
    agg = GapAggregator()
    snapshots = {
        "legal": {
            "delta_row": {
                "data_room_gaps": [
                    "Missing CoC document",
                    "missing coc document",
                ],
            },
        },
    }
    gaps = agg.merge_data_room_gaps(snapshots)
    assert len(gaps) == 1
    assert gaps[0]["source_agent"] == "legal"


def test_gap_aggregator_keeps_same_text_from_different_agents() -> None:
    agg = GapAggregator()
    snapshots = {
        "kpi": {"delta_row": {"data_room_gaps": ["Missing census data"]}},
        "legal": {"delta_row": {"data_room_gaps": ["Missing census data"]}},
    }
    gaps = agg.merge_data_room_gaps(snapshots)
    assert len(gaps) == 2
    agents = {g["source_agent"] for g in gaps}
    assert agents == {"kpi", "legal"}


def test_merge_risks_from_flags_sorts_critical_first() -> None:
    snapshots = {
        "financial_trends": {
            "delta_row": {
                "flags": [
                    {"severity": "Green", "metric": "Track metric"},
                    {"severity": "Red", "metric": "Critical metric"},
                ],
            },
        },
    }
    risks = merge_risks_from_flags(snapshots)
    assert risks[0]["severity"] == "critical"
    assert len(risks) <= 8


def test_bundle_builder_sets_production_meta_and_provenance() -> None:
    builder = BundleBuilder()
    mock_spark = MagicMock()
    minimal_snapshots = {
        "business_model": {
            "delta_row": {"flags": [], "data_room_gaps": []},
            "yaml_dict": {"executive_summary": "Test co"},
            "report_path": "/Volumes/uc13/analysis/reports/Elder_Care/business_model.yaml",
        },
    }

    with (
        patch(
            "agents.orchestrator.bundle_builder._ingest_snapshots",
            return_value=minimal_snapshots,
        ),
        patch(
            "agents.orchestrator.bundle_builder._load_company_profile",
            return_value={"industry_overlay": "healthcare"},
        ),
        patch(
            "agents.orchestrator.bundle_builder.freshness",
            return_value="current",
        ),
        patch(
            "agents.orchestrator.bundle_builder.validate_bundle",
        ) as mock_validate,
        patch(
            "agents.orchestrator.bundle_builder.write_bundle_yaml",
        ) as mock_write,
    ):
        bundle = builder.build("Elder Care", "uc13_ale", spark=mock_spark)

    assert bundle["meta"]["demo_mode"] is False
    assert bundle["meta"]["disclaimer_text"] == ""
    assert bundle["provenance"]["bundle_builder_version"] == "0.2.0-m2"
    assert bundle["meta"]["freshness"] == "current"
    assert set(bundle["provenance"]["agent_delta_tables"]) == set(AGENTS_PRESENT_KEYS)
    mock_validate.assert_called_once()
    mock_write.assert_called_once()


def test_bundle_builder_halts_when_validate_fails() -> None:
    builder = BundleBuilder()
    mock_spark = MagicMock()

    with (
        patch(
            "agents.orchestrator.bundle_builder._ingest_snapshots",
            return_value={},
        ),
        patch(
            "agents.orchestrator.bundle_builder._load_company_profile",
            return_value={},
        ),
        patch(
            "agents.orchestrator.bundle_builder.freshness",
            return_value="current",
        ),
        patch(
            "agents.orchestrator.bundle_builder.validate_bundle",
            side_effect=BundleValidationError("schema fail"),
        ),
        patch(
            "agents.orchestrator.bundle_builder.write_bundle_yaml",
        ) as mock_write,
    ):
        with pytest.raises(BundleValidationError):
            builder.build("Elder Care", "uc13_ale", spark=mock_spark)

    mock_write.assert_not_called()


def test_bundle_builder_raises_without_spark() -> None:
    builder = BundleBuilder()
    mock_sql = MagicMock()
    mock_sql.SparkSession.getActiveSession.return_value = None
    with patch.dict("sys.modules", {"pyspark": MagicMock(), "pyspark.sql": mock_sql}):
        with pytest.raises(RuntimeError, match="No active Spark session"):
            builder.build("Elder Care", "uc13_ale", spark=None)
