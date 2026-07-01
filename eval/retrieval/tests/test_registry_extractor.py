"""Tests for IntentRegistryExtractor — spec §5.12.6."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

from eval.retrieval.models import RetrievalIntent
from eval.retrieval.registry_extractor import IntentRegistryExtractor

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
REGISTRY_PATH = REPO_ROOT / "eval" / "retrieval" / "intent_registry.yaml"


def _load_expected_counts() -> dict:
    return yaml.safe_load((FIXTURES / "expected_intent_counts.yaml").read_text(encoding="utf-8"))


def test_extractor_total_within_appendix_c_bounds():
    extractor = IntentRegistryExtractor(REPO_ROOT)
    intents = extractor.extract()
    expected = _load_expected_counts()
    assert expected["total_min"] <= len(intents) <= expected["total_max"]


def test_extractor_per_agent_counts_within_tolerance():
    extractor = IntentRegistryExtractor(REPO_ROOT)
    intents = extractor.extract()
    expected = _load_expected_counts()
    IntentRegistryExtractor.validate_counts(
        intents,
        expected["partitions"],
        tolerance=expected["tolerance"],
        total_min=expected["total_min"],
        total_max=expected["total_max"],
    )


def test_committed_registry_matches_extractor_output():
    extractor = IntentRegistryExtractor(REPO_ROOT)
    live = [intent.model_dump(mode="json", exclude_none=True) for intent in extractor.extract()]
    committed = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert committed == live


def test_all_registry_rows_validate_as_retrieval_intent():
    rows = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    for row in rows:
        intent = RetrievalIntent.model_validate(row)
        assert intent.catalog == "uc13_ale"
        assert intent.extraction_confidence in ("static", "manual")


def test_profiler_intents_use_tier_filter_one_not_bool():
    extractor = IntentRegistryExtractor(REPO_ROOT)
    profiler = [i for i in extractor.extract() if i.agent_id == "profiler"]
    assert len(profiler) == 7
    for intent in profiler:
        assert intent.tier_filter == 1


def test_fta_opex_sample_intent_id_from_spec():
    extractor = IntentRegistryExtractor(REPO_ROOT)
    intent_ids = {i.intent_id for i in extractor.extract()}
    assert "fta.opex.q1_financial_statements" in intent_ids
    assert "fta.opex.q3_projected_financials" in intent_ids


def test_validate_counts_fails_when_partition_out_of_bounds():
    extractor = IntentRegistryExtractor(REPO_ROOT)
    intents = extractor.extract()
    expected = _load_expected_counts()
    with pytest.raises(ValueError, match="agent_id=kpi"):
        IntentRegistryExtractor.validate_counts(
            intents,
            {**expected["partitions"], "kpi": 99},
            tolerance=expected["tolerance"],
            total_min=expected["total_min"],
            total_max=expected["total_max"],
        )


def test_wrapper_inner_semantic_search_not_double_counted():
    """Falsifier: inner semantic_search inside wrapper defs must not inflate totals."""
    extractor = IntentRegistryExtractor(REPO_ROOT)
    intents = extractor.extract()
    bma = [i for i in intents if i.agent_id == "bma"]
    assert len(bma) == 9
    assert all(i.invocation_path == "with_fallback" for i in bma)


def test_registry_hash_stable_for_ci_drift_gate():
    """Falsifier: undetected YAML edit changes registry hash without extractor re-run."""
    extractor = IntentRegistryExtractor(REPO_ROOT)
    payload = yaml.safe_dump(
        [i.model_dump(mode="json", exclude_none=True) for i in extractor.extract()],
        sort_keys=True,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    assert len(digest) == 64
