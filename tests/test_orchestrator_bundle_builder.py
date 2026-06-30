"""G4 pytest for M2 BundleBuilder — Elder Care fixtures and builder verification (T5)."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from agents.orchestrator.bundle_builder import BundleBuilder, GapAggregator
from agents.orchestrator.constants import (
    AGENT_DELTA_TABLE_SUFFIXES,
    AGENTS_PRESENT_KEYS,
    TLDR_REQUIRED_FIELDS,
)
from agents.orchestrator.field_mapping import FIELD_MAPPINGS, tldr_bundle_paths
from agents.orchestrator.validate import BundleValidationError, validate_bundle

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_SNAPSHOTS_PATH = _FIXTURES / "elder_care_agent_snapshots.yaml"
_EXPECTATIONS_PATH = _FIXTURES / "elder_care_builder_expectations.yaml"


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _load_elder_care_snapshots() -> dict:
    return _load_yaml(_SNAPSHOTS_PATH)


def _load_expectations() -> dict:
    return _load_yaml(_EXPECTATIONS_PATH)


def _build_with_snapshots(
    snapshots: dict,
    *,
    company_name: str = "Elder Care",
    catalog: str = "uc13_ale",
) -> dict:
    builder = BundleBuilder()
    mock_spark = MagicMock()
    profile = {"industry_overlay": "healthcare", "deal_type": "platform"}
    with (
        patch(
            "agents.orchestrator.bundle_builder._ingest_snapshots",
            return_value=snapshots,
        ),
        patch(
            "agents.orchestrator.bundle_builder._load_company_profile",
            return_value=profile,
        ),
        patch(
            "agents.orchestrator.bundle_builder.freshness",
            return_value="current",
        ),
        patch(
            "agents.orchestrator.bundle_builder.write_bundle_yaml",
        ),
    ):
        return builder.build(company_name, catalog, spark=mock_spark)


def _bundle_without_timestamps(bundle: dict) -> dict:
    result = deepcopy(bundle)
    result.get("meta", {}).pop("generated_at", None)
    return result


def _medium_low_snapshots(base: dict) -> dict:
    """Variant: no critical flags, sparse gaps so FTA/legal stay high, kpi stays low."""
    snaps = deepcopy(base)
    for key in snaps:
        snaps[key]["delta_row"]["flags"] = []
        if key == "financial_trends":
            snaps[key]["delta_row"]["data_room_gaps"] = ["One gap only"]
        elif key == "legal":
            snaps[key]["delta_row"]["data_room_gaps"] = ["One legal gap"]
            snaps[key]["delta_row"]["section_confidence"] = "high"
        elif key == "kpi":
            snaps[key]["yaml_dict"] = {"missing_kpis": []}
            snaps[key]["delta_row"]["data_room_gaps"] = []
        else:
            snaps[key]["delta_row"]["data_room_gaps"] = []
    return snaps


# --- T1 row-coverage tests (carried from T1 stub) ---


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


# --- T5 Elder Care builder verification (G4) ---


@pytest.fixture
def elder_care_snapshots() -> dict:
    return _load_elder_care_snapshots()


@pytest.fixture
def elder_care_expectations() -> dict:
    return _load_expectations()


@pytest.fixture
def elder_care_bundle(elder_care_snapshots: dict) -> dict:
    return _build_with_snapshots(elder_care_snapshots)


def test_elder_care_production_meta(elder_care_bundle: dict, elder_care_expectations: dict):
    meta = elder_care_expectations["production_meta"]
    assert elder_care_bundle["meta"]["demo_mode"] is meta["demo_mode"]
    assert elder_care_bundle["meta"]["disclaimer_text"] == meta["disclaimer_text"]
    assert elder_care_bundle["meta"]["freshness"] == meta["freshness"]
    assert elder_care_bundle["meta"]["render_state"] == meta["render_state"]
    assert (
        elder_care_bundle["provenance"]["bundle_builder_version"]
        == meta["bundle_builder_version"]
    )
    assert set(elder_care_bundle["provenance"]["agent_delta_tables"]) == set(
        AGENTS_PRESENT_KEYS
    )


def test_elder_care_confidence_by_area(elder_care_bundle: dict, elder_care_expectations: dict):
    expected = elder_care_expectations["confidence_by_area"]
    by_area = elder_care_bundle["confidence_by_area"]
    for key, value in expected.items():
        assert by_area[key] == value, f"confidence_by_area[{key}]"


def test_elder_care_overall_confidence_low_with_critical_risks(
    elder_care_bundle: dict,
    elder_care_expectations: dict,
):
    assert elder_care_bundle["meta"]["overall_confidence"] == elder_care_expectations[
        "overall_confidence"
    ]
    assert any(r.get("severity") == "critical" for r in elder_care_bundle.get("risks") or [])


def test_elder_care_overall_confidence_medium_low_without_critical_risks(
    elder_care_snapshots: dict,
    elder_care_expectations: dict,
):
    bundle = _build_with_snapshots(_medium_low_snapshots(elder_care_snapshots))
    assert bundle["meta"]["overall_confidence"] == elder_care_expectations["medium_low_case"][
        "overall_confidence"
    ]
    assert not any(r.get("severity") == "critical" for r in bundle.get("risks") or [])


def test_elder_care_data_room_gap_count(elder_care_bundle: dict, elder_care_expectations: dict):
    spec = elder_care_expectations["data_room_gaps"]
    count = len(elder_care_bundle["data_room_gaps"])
    assert spec["count_min"] <= count <= spec["count_max"]


def test_elder_care_gap_dedupe_collapses_normalized_duplicates(
    elder_care_snapshots: dict,
    elder_care_expectations: dict,
):
    base_count = len(_build_with_snapshots(elder_care_snapshots)["data_room_gaps"])
    dedupe_spec = elder_care_expectations["gap_dedupe"]
    snaps = deepcopy(elder_care_snapshots)
    agent = dedupe_spec["duplicate_inputs"]["agent"]
    extra = dedupe_spec["duplicate_inputs"]["gaps"]
    snaps[agent]["delta_row"]["data_room_gaps"] = list(
        snaps[agent]["delta_row"]["data_room_gaps"]
    ) + extra
    deduped_count = len(_build_with_snapshots(snaps)["data_room_gaps"])
    assert deduped_count == base_count + dedupe_spec["expected_extra_merged"]


def test_elder_care_risks_and_diligence_bounds(
    elder_care_bundle: dict,
    elder_care_expectations: dict,
):
    risks = elder_care_bundle.get("risks") or []
    spec_r = elder_care_expectations["risks"]
    assert spec_r["count_min"] <= len(risks) <= spec_r["count_max"]

    diligence = elder_care_bundle.get("diligence_questions") or []
    spec_d = elder_care_expectations["diligence_questions"]
    assert spec_d["count_min"] <= len(diligence) <= spec_d["count_max"]


def test_elder_care_headline_metrics_nonempty(
    elder_care_bundle: dict,
    elder_care_expectations: dict,
):
    hm = elder_care_expectations["headline_metrics"]
    metrics = elder_care_bundle["headline_metrics"]
    if hm.get("ltm_revenue_nonempty"):
        assert str(metrics.get("ltm_revenue") or "").strip()
    if hm.get("ltm_ebitda_margin_pct_nonempty"):
        assert str(metrics.get("ltm_ebitda_margin_pct") or "").strip()


def test_elder_care_legal_assessed_count(elder_care_bundle: dict, elder_care_expectations: dict):
    assert (
        elder_care_bundle["legal"]["assessed_count"]
        >= elder_care_expectations["legal"]["assessed_count_min"]
    )


def test_elder_care_synthesis_gaps_structure(
    elder_care_bundle: dict,
    elder_care_expectations: dict,
):
    spec = elder_care_expectations["synthesis_gaps"]
    gaps = elder_care_bundle["provenance"]["synthesis_gaps"]
    assert len(gaps) >= spec["count_min"]
    for row in gaps:
        for key in spec["required_keys"]:
            assert key in row and row[key]
    paths = {g["field_path"] for g in gaps}
    for expected in spec["expected_field_paths"]:
        assert expected in paths


def test_elder_care_builder_idempotent_excluding_generated_at(elder_care_snapshots: dict):
    first = _build_with_snapshots(elder_care_snapshots)
    second = _build_with_snapshots(elder_care_snapshots)
    assert _bundle_without_timestamps(first) == _bundle_without_timestamps(second)


def test_validate_bundle_rejects_malformed_bundle():
    """W-M1-SCHEMA-FUZZ: negative validate_bundle case (D-M2-5)."""
    malformed = {
        "meta": {"schema_version": "0.1.0", "company_name": "X"},
        "headline_metrics": {},
    }
    with pytest.raises(BundleValidationError):
        validate_bundle(malformed)


def test_validate_bundle_rejects_invalid_overall_confidence_enum():
    """Schema enum falsifier for overall_confidence."""
    bundle = _build_with_snapshots(_load_elder_care_snapshots())
    bad = deepcopy(bundle)
    bad["meta"]["overall_confidence"] = "very_high"
    with pytest.raises(BundleValidationError):
        validate_bundle(bad)


def test_kpi_missing_dict_diligence_question_readable():
    """F-M2-KPI-DILIGENCE-REPR: dict missing_kpis must not render Python dict repr."""
    kpi_item = {
        "kpi_name": "Census turnover",
        "management_question": "Provide monthly census turnover for trailing 12 months.",
    }
    snapshots = {
        "kpi": {
            "delta_row": {"flags": [], "data_room_gaps": []},
            "yaml_dict": {"missing_kpis": [kpi_item]},
        },
    }
    questions = GapAggregator().build_diligence_questions({}, snapshots)
    kpi_questions = [q for q in questions if q.get("source_agent") == "kpi"]
    assert len(kpi_questions) == 1
    question = kpi_questions[0]["question"]
    assert question == kpi_item["management_question"]
    assert "{" not in question
    assert "kpi_name" not in question
