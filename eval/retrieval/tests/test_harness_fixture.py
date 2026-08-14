"""EvalHarness metric math and compare() golden gate tests."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
for _path in (_REPO_ROOT / "databricks", _REPO_ROOT):
    _entry = str(_path)
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from eval.retrieval.errors import PreconditionError
from eval.retrieval.harness import (
    EvalHarness,
    compare_results,
    compute_metrics,
    default_gold_path,
    default_registry_path,
    dispatch_retrieval,
    metric_gate_pass,
)
from eval.retrieval.gold.bootstrap import load_gold_labels, load_registry
from eval.retrieval.models import GoldLabel, HarnessResult, RetrievalIntent
from eval.retrieval.store import SqliteEvalStore

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
COMPARE_CASES = FIXTURES_DIR / "compare_gate_cases.yaml"
GOLD_PATH = Path(__file__).resolve().parents[1] / "gold_labels" / "elder_care.yaml"


@dataclass
class _FakeChunk:
    chunk_id: str
    file_name: str = "CIM.pdf"
    section_header: str = "Overview"
    priority_tier: int = 1
    source_type: str = "text"


@dataclass
class _FakeRouteResult:
    chunks: list
    mode: str
    scores: list[float]


def _result_from_case(intent_id: str, payload: dict) -> HarnessResult:
    fields = {"intent_id": intent_id, **payload}
    return HarnessResult.model_validate(fields)


def _load_compare_cases() -> list[dict]:
    return yaml.safe_load(COMPARE_CASES.read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", _load_compare_cases(), ids=lambda c: c["id"])
def test_compare_gate_cases_yaml(case: dict):
    intent_id = case["intent_id"]
    baseline = _result_from_case(intent_id, case["baseline"])
    current = _result_from_case(intent_id, case["current"])
    gated = [] if case["expect"].get("in_gated_scope") is False else [intent_id]

    deltas, intent_gates = compare_results(
        run_id="enhancement_test",
        baseline_ref_run_id="baseline_test",
        gated_intents=gated,
        baseline_results={intent_id: baseline},
        current_results={intent_id: current},
    )

    gate = next(row for row in intent_gates if row.intent_id == intent_id)
    assert gate.intent_gate_pass is case["expect"]["intent_gate_pass"]
    if "in_gated_scope" in case["expect"]:
        assert gate.in_gated_scope is case["expect"]["in_gated_scope"]

    for metric, expected in case["expect"].get("gate_metrics", {}).items():
        delta = next(row for row in deltas if row.metric == metric)
        assert delta.gate_pass is expected

    for metric, expected in case["expect"].get("audit_only", {}).items():
        delta = next(row for row in deltas if row.metric == metric)
        assert delta.gate_pass is expected
        assert metric not in case["expect"].get("gate_metrics", {})


def test_basis_conflict_direction_not_inverted():
    assert metric_gate_pass("basis_conflict_at_10", 0.4, 0.2) is True
    assert metric_gate_pass("basis_conflict_at_10", 0.2, 0.5) is False
    assert metric_gate_pass("recall_at_10", 0.5, 0.8) is True


def test_mrr_not_in_intent_gate_and():
    baseline = HarnessResult(
        intent_id="x",
        eval_status="evaluated",
        recall_at_10=1.0,
        mrr=1.0,
        result_count=3,
        mode="semantic",
    )
    current = HarnessResult(
        intent_id="x",
        eval_status="evaluated",
        recall_at_10=1.0,
        mrr=0.1,
        result_count=3,
        mode="semantic",
    )
    _, gates = compare_results(
        run_id="r1",
        baseline_ref_run_id="b1",
        gated_intents=["x"],
        baseline_results={"x": baseline},
        current_results={"x": current},
    )
    assert gates[0].intent_gate_pass is True


def test_compute_metrics_recall_and_basis_conflict():
    intent = RetrievalIntent(
        intent_id="fta.opex.q3_projected_financials",
        agent_id="fta.opex",
        source_file="databricks/agents/subagents/workstream/financial/opex_sub_agent.py",
        catalog="uc13_ale",
        query="opex projected financials",
        top_k=10,
        invocation_path="with_fallback",
    )
    gold_rows = load_gold_labels(GOLD_PATH)
    gold = next(
        row for row in gold_rows if row.intent_id == "fta.opex.q3_projected_financials"
    )
    recall_gold = gold.model_copy(
        update={"positive_chunk_ids": gold.positive_chunk_ids[:3]}
    )
    positive_ids = recall_gold.positive_chunk_ids
    route = _FakeRouteResult(
        chunks=[_FakeChunk(chunk_id) for chunk_id in positive_ids],
        mode="semantic",
        scores=[0.9, 0.85, 0.8],
    )
    result = compute_metrics(intent, recall_gold, route)
    assert result.recall_at_10 == 1.0
    assert result.eval_status == "evaluated"

    basis_gold = GoldLabel(
        intent_id="fta.opex.q3_projected_financials",
        company_name="Elder Care",
        catalog="uc13_ale",
        gold_status="ready",
        positive_chunk_ids=["bfbcfe31-e9b1-4017-acd7-97601be54c04"],
        negative_chunk_ids=["c088efb9-8cf9-46a5-8aba-aed9eab703dc"],
        negative_method="basis_rule",
        gold_method="citation_backfill",
        ingestion_snapshot="uc13_ale:35034:2026-07-02",
        confidence="high",
    )
    basis_route = _FakeRouteResult(
        chunks=[
            _FakeChunk("bfbcfe31-e9b1-4017-acd7-97601be54c04"),
            _FakeChunk("c088efb9-8cf9-46a5-8aba-aed9eab703dc"),
            _FakeChunk("7cf789fd-dabd-47fa-8ee7-47a001d5fb68"),
        ],
        mode="semantic",
        scores=[0.9, 0.85, 0.8],
    )
    basis_result = compute_metrics(intent, basis_gold, basis_route)
    assert basis_result.basis_conflict_at_10 == pytest.approx(1 / 3)
    assert basis_result.precision_at_10 == pytest.approx(2 / 3)


def test_semantic_search_importable_for_harness_dispatch():
    """Kill criterion: harness can import migrated semantic_search."""
    from agents.shared.retrieval import semantic_search

    assert callable(semantic_search)
    assert callable(dispatch_retrieval)


def _with_fallback_intent() -> RetrievalIntent:
    return RetrievalIntent(
        intent_id="fta.opex.q3_projected_financials",
        agent_id="fta.opex",
        source_file="databricks/agents/subagents/workstream/financial/opex_sub_agent.py",
        catalog="uc13_ale",
        query="opex projected financials",
        workstream_filter=["FINANCIAL"],
        file_name_filter=["Model", "Projection"],
        top_k=8,
        min_chunk_length=100,
        min_results=3,
        source_type_priority=True,
        invocation_path="with_fallback",
    )


@patch("agents.shared.fallback.semantic_search_with_fallback")
@patch("agents.shared.retrieval.semantic_search")
def test_dispatch_retrieval_with_fallback_delegates_to_shared_fallback(
    mock_semantic_search,
    mock_fallback,
):
    """Production path: ``with_fallback`` intents call ``fallback.py``, not inline retry."""
    route = _FakeRouteResult(
        chunks=[_FakeChunk("chunk-a"), _FakeChunk("chunk-b"), _FakeChunk("chunk-c")],
        mode="keyword",
        scores=[0.9, 0.8, 0.7],
    )
    mock_fallback.return_value = (route, True)

    result = dispatch_retrieval(
        _with_fallback_intent(),
        company_name="Elder Care",
        spark=MagicMock(),
    )

    mock_fallback.assert_called_once()
    call_kwargs = mock_fallback.call_args.kwargs
    assert call_kwargs["company_name"] == "Elder Care"
    assert call_kwargs["catalog"] == "uc13_ale"
    assert call_kwargs["intent_id"] == "fta.opex.q3_projected_financials"
    assert call_kwargs["file_name_filter"] == ["Model", "Projection"]
    assert call_kwargs["min_results"] == 3
    assert call_kwargs["source_type_priority"] is True
    mock_semantic_search.assert_not_called()
    assert result is route
    assert result.mode == "keyword"


@patch("agents.shared.fallback.semantic_search_with_fallback")
@patch("agents.shared.retrieval.semantic_search")
def test_dispatch_retrieval_direct_path_skips_shared_fallback(
    mock_semantic_search,
    mock_fallback,
):
    direct_intent = _with_fallback_intent().model_copy(
        update={
            "invocation_path": "direct",
            "file_name_filter": None,
            "min_results": None,
        }
    )
    route = _FakeRouteResult(
        chunks=[_FakeChunk("chunk-only")],
        mode="semantic",
        scores=[0.95],
    )
    mock_semantic_search.return_value = route

    result = dispatch_retrieval(
        direct_intent,
        company_name="Elder Care",
        spark=MagicMock(),
    )

    mock_fallback.assert_not_called()
    mock_semantic_search.assert_called_once()
    assert result is route


@patch("agents.shared.fallback.semantic_search_with_fallback")
@patch("agents.shared.retrieval.semantic_search")
def test_dispatch_retrieval_ablation_with_fallback_threads_merge_rank_inline(
    mock_semantic_search,
    mock_fallback,
):
    """Ablation-only branch: merge_rank_mode cannot pass through ``fallback.py``."""
    route = _FakeRouteResult(
        chunks=[_FakeChunk("chunk-a")],
        mode="semantic",
        scores=[0.9],
    )
    mock_semantic_search.return_value = route

    dispatch_retrieval(
        _with_fallback_intent(),
        company_name="Elder Care",
        spark=MagicMock(),
        ablation_arm="tier_only",
    )

    mock_fallback.assert_not_called()
    assert mock_semantic_search.call_count >= 1
    assert mock_semantic_search.call_args.kwargs["merge_rank_mode"] == "tier_only"


def test_validate_baseline_ref_and_compare_round_trip(tmp_path):
    from eval.retrieval.harness import EvalHarness

    store = SqliteEvalStore(tmp_path / "gate.sqlite")
    harness = EvalHarness(gold_path=GOLD_PATH, registry_path=default_registry_path())
    created = datetime(2026, 7, 1, tzinfo=timezone.utc)

    from eval.retrieval.harness import compute_gold_snapshot, compute_registry_hash
    from eval.retrieval.models import HarnessRun

    registry_hash = compute_registry_hash(default_registry_path())
    gold_labels = load_gold_labels(GOLD_PATH)
    gold_snapshot = compute_gold_snapshot(gold_labels)
    gated = [
        "fta.opex.q3_projected_financials",
        "legal.contracts_vendors_platform",
    ]

    baseline_run = HarnessRun(
        run_id="baseline_gate_001",
        run_type="baseline",
        company_name="Elder Care",
        catalog="uc13_ale",
        ingestion_snapshot="uc13_ale:35034:2026-07-02",
        registry_hash=registry_hash,
        gold_snapshot=gold_snapshot,
        affected_intents=gated,
        gated_intents=gated,
        store_backend="sqlite",
        harness_status="incomplete",
        intent_count=len(gated),
        created_at=created,
    )
    store.insert_run(baseline_run)
    store.append_results(
        "baseline_gate_001",
        [
            HarnessResult(
                intent_id="fta.opex.q3_projected_financials",
                eval_status="evaluated",
                recall_at_10=1.0,
                precision_at_10=0.8,
                basis_conflict_at_10=0.1,
                mrr=1.0,
                result_count=4,
                mode="semantic",
            ),
            HarnessResult(
                intent_id="legal.contracts_vendors_platform",
                eval_status="evaluated",
                recall_at_10=1.0,
                mrr=1.0,
                result_count=2,
                mode="semantic",
            ),
        ],
    )
    store.finalize_run("baseline_gate_001", gate_pass=None, fallback_rate=0.0)

    current_run = HarnessRun(
        run_id="enhancement_gate_001",
        run_type="enhancement",
        company_name="Elder Care",
        catalog="uc13_ale",
        ingestion_snapshot="uc13_ale:35034:2026-07-02",
        registry_hash=registry_hash,
        gold_snapshot=gold_snapshot,
        affected_intents=gated,
        gated_intents=gated,
        baseline_ref_run_id="baseline_gate_001",
        store_backend="sqlite",
        harness_status="incomplete",
        intent_count=len(gated),
        created_at=created,
    )
    store.insert_run(current_run)
    store.append_results(
        "enhancement_gate_001",
        [
            HarnessResult(
                intent_id="fta.opex.q3_projected_financials",
                eval_status="evaluated",
                recall_at_10=0.5,
                precision_at_10=0.9,
                basis_conflict_at_10=0.1,
                mrr=1.0,
                result_count=4,
                mode="semantic",
            ),
            HarnessResult(
                intent_id="legal.contracts_vendors_platform",
                eval_status="evaluated",
                recall_at_10=1.0,
                mrr=1.0,
                result_count=2,
                mode="semantic",
            ),
        ],
    )
    store.finalize_run("enhancement_gate_001", gate_pass=None, fallback_rate=0.0)

    current_manifest = store.get_run("enhancement_gate_001").manifest
    harness.validate_baseline_ref(
        store,
        "baseline_gate_001",
        gated_intents=gated,
        current_manifest=current_manifest,
    )
    deltas, gates = harness.compare(store, "baseline_gate_001", "enhancement_gate_001")
    opex_gate = next(
        gate for gate in gates if gate.intent_id == "fta.opex.q3_projected_financials"
    )
    assert opex_gate.intent_gate_pass is False
    recall_delta = next(
        row
        for row in deltas
        if row.intent_id == "fta.opex.q3_projected_financials"
        and row.metric == "recall_at_10"
    )
    assert recall_delta.gate_pass is False
    store.close()


def test_default_gold_path_requires_slug():
    with pytest.raises(TypeError):
        default_gold_path()
    assert default_gold_path("elder_care").name == "elder_care.yaml"
    assert default_gold_path("clearsulting").name == "clearsulting.yaml"


def test_harness_resolves_gold_path_from_company_slug():
    harness = EvalHarness(company_slug="elder_care")
    assert harness.gold_path == default_gold_path("elder_care")

    with pytest.raises(PreconditionError, match="gold_path or company_slug"):
        EvalHarness()
