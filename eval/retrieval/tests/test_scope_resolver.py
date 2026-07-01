"""IntentScopeResolver golden scope tests — spec §5.12.10."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from eval.retrieval.errors import ScopeMismatchError, ScopeResolutionError
from eval.retrieval.gold.bootstrap import load_gold_labels, load_registry
from eval.retrieval.scope_resolver import IntentScopeResolver

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
SCOPE_CASES = FIXTURES_DIR / "scope_resolver_cases.yaml"
REGISTRY_PATH = Path(__file__).resolve().parents[1] / "intent_registry.yaml"
GOLD_PATH = Path(__file__).resolve().parents[1] / "gold_labels" / "elder_care.yaml"


def _load_scope_cases() -> list[dict]:
    return yaml.safe_load(SCOPE_CASES.read_text(encoding="utf-8"))["cases"]


@pytest.fixture
def resolver() -> IntentScopeResolver:
    return IntentScopeResolver()


@pytest.fixture
def registry():
    return load_registry(REGISTRY_PATH)


@pytest.fixture
def gold_labels():
    return load_gold_labels(GOLD_PATH)


@pytest.mark.parametrize("case", _load_scope_cases(), ids=lambda c: c["id"])
def test_scope_resolver_cases_yaml(
    case: dict,
    resolver: IntentScopeResolver,
    registry,
    gold_labels,
):
    expect = case["expect"]
    if expect.get("error"):
        with pytest.raises(globals()[expect["error"]]):
            resolver.resolve(
                case["git_diff_paths"],
                registry,
                gold_labels=gold_labels,
                company_name="Elder Care",
                catalog="uc13_ale",
            )
        return

    scope = resolver.resolve(
        case["git_diff_paths"],
        registry,
        gold_labels=gold_labels,
        company_name="Elder Care",
        catalog="uc13_ale",
    )
    affected = scope["affected_intents"]
    gated = scope["gated_intents"]

    if expect.get("affected_all"):
        assert len(affected) == len(registry)

    if prefix := expect.get("affected_prefix"):
        assert affected
        assert all(intent_id.startswith(prefix) for intent_id in affected)

    if expect.get("gated_subset") == "gate_eligible_only":
        assert set(gated).issubset(set(affected))
        for intent_id in gated:
            gold = next(row for row in gold_labels if row.intent_id == intent_id)
            assert gold.gold_status in {"ready", "partial"}
            assert gold.positive_chunk_ids

    if bootstrap_failed := expect.get("bootstrap_failed_in_affected_not_gated"):
        assert bootstrap_failed in affected
        assert bootstrap_failed not in gated


def test_validate_pr_scope_mismatch(resolver: IntentScopeResolver):
    computed = {"affected_intents": ["a"], "gated_intents": ["a"]}
    with pytest.raises(ScopeMismatchError):
        resolver.validate_pr_scope(["b"], ["b"], computed)
