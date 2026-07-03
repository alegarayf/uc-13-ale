"""Ablation dispatch wiring tests — M-RE3 T4."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
for _path in (_REPO_ROOT / "databricks", _REPO_ROOT):
    _entry = str(_path)
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from eval.retrieval.errors import PreconditionError
from eval.retrieval.harness import (
    EvalHarness,
    ablation_arm_to_merge_rank_mode,
    compute_gold_snapshot,
    compute_registry_hash,
    default_registry_path,
    dispatch_retrieval,
    resolve_ablation_arm,
)
from eval.retrieval.harness_cli import build_parser
from eval.retrieval.models import ABLATION_ARMS, HarnessRun, RetrievalIntent
from eval.retrieval.store import SqliteEvalStore

GOLD_PATH = Path(__file__).resolve().parents[1] / "gold_labels" / "elder_care.yaml"


def test_ablation_arms_constant_matches_contract():
    assert ABLATION_ARMS == (
        "merge_rank_on",
        "merge_rank_off",
        "sim_only",
        "tier_only",
    )


def test_resolve_ablation_arm_none_returns_none():
    assert resolve_ablation_arm(None) is None


def test_resolve_ablation_arm_parses_sim_only():
    assert resolve_ablation_arm({"arm": "sim_only"}) == "sim_only"


@pytest.mark.parametrize("bad_config", [{"arm": "bogus"}, {"not_arm": "sim_only"}, {}])
def test_resolve_ablation_arm_raises_on_malformed(bad_config: dict):
    with pytest.raises(PreconditionError):
        resolve_ablation_arm(bad_config)


def test_resolve_ablation_arm_accepts_vs_filter_pushdown_name():
    assert resolve_ablation_arm({"arm": "vs_filter_pushdown"}) == "vs_filter_pushdown"


def test_ablation_arm_to_merge_rank_mode_mapping():
    assert ablation_arm_to_merge_rank_mode("merge_rank_on") == "sim_tier"
    assert ablation_arm_to_merge_rank_mode("merge_rank_off") == "off"
    assert ablation_arm_to_merge_rank_mode("sim_only") == "sim_only"
    assert ablation_arm_to_merge_rank_mode("tier_only") == "tier_only"
    assert ablation_arm_to_merge_rank_mode(None) is None


def test_vs_filter_pushdown_arm_raises_at_dispatch_mapping():
    with pytest.raises(PreconditionError, match="not dispatchable"):
        ablation_arm_to_merge_rank_mode("vs_filter_pushdown")


@dataclass
class _FakeChunk:
    chunk_id: str
    file_name: str = "CIM.pdf"
    chunk_text: str = "A" * 120
    section_header: str = "Overview"
    page_start: int = 1
    source_type: str = "text"
    workstream: list[str] | None = None
    priority_tier: int = 1


def _intent() -> RetrievalIntent:
    return RetrievalIntent(
        intent_id="fta.opex.q3_projected_financials",
        agent_id="fta.opex",
        source_file="databricks/agents/subagents/workstream/financial/opex_sub_agent.py",
        catalog="uc13_ale",
        query="opex projected financials",
        top_k=10,
        invocation_path="direct",
    )


@patch("agents.shared.retrieval.WorkspaceClient")
@patch("agents.shared.retrieval.mlflow.deployments.get_deploy_client")
def test_dispatch_retrieval_ablation_arm_changes_chunk_order(
    mock_get_deploy_client,
    mock_workspace_client,
    monkeypatch,
):
    monkeypatch.setenv("catalog", "uc13_ale")
    mock_client = MagicMock()
    mock_get_deploy_client.return_value = mock_client
    mock_client.predict.return_value = {"data": [{"embedding": [0.1, 0.2]}]}

    vs_result = MagicMock()
    vs_result.result.data_array = [
        ["c1", "d1", "CIM.pdf", 0.99],
        ["c2", "d2", "P&L.pdf", 0.10],
    ]
    mock_w = MagicMock()
    mock_w.vector_search_indexes.query_index.return_value = vs_result
    mock_workspace_client.return_value = mock_w

    hydrated_c1 = _FakeChunk(chunk_id="c1", priority_tier=2)
    hydrated_c2 = _FakeChunk(chunk_id="c2", priority_tier=1)
    spark = MagicMock()
    spark.sql.return_value.collect.return_value = [hydrated_c1, hydrated_c2]

    intent = _intent()
    default_result = dispatch_retrieval(
        intent,
        company_name="Elder Care",
        spark=spark,
    )
    tier_only_result = dispatch_retrieval(
        intent,
        company_name="Elder Care",
        spark=spark,
        ablation_arm="tier_only",
    )

    default_order = [c.chunk_id for c in default_result.chunks]
    tier_only_order = [c.chunk_id for c in tier_only_result.chunks]
    assert default_order != tier_only_order
    assert tier_only_order == ["c2", "c1"]


def test_harness_cli_ablation_config_round_trip():
    parser = build_parser()
    args = parser.parse_args(
        [
            "run",
            "--store-backend",
            "sqlite",
            "--run-type",
            "ablation",
            "--company-name",
            "Elder Care",
            "--catalog",
            "uc13_ale",
            "--ablation-config",
            '{"arm": "sim_only"}',
        ]
    )
    assert args.ablation_config == {"arm": "sim_only"}
    assert resolve_ablation_arm(args.ablation_config) == "sim_only"


def test_harness_cli_rejects_malformed_ablation_json():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "run",
                "--store-backend",
                "sqlite",
                "--run-type",
                "ablation",
                "--company-name",
                "Elder Care",
                "--catalog",
                "uc13_ale",
                "--ablation-config",
                "not-json",
            ]
        )


def test_eval_harness_populates_ablation_arm_on_ablation_run(tmp_path):
    store = SqliteEvalStore(tmp_path / "ablation.sqlite")
    harness = EvalHarness(gold_path=GOLD_PATH, registry_path=default_registry_path())
    created = datetime(2026, 7, 3, tzinfo=timezone.utc)
    registry_hash = compute_registry_hash(default_registry_path())
    from eval.retrieval.gold.bootstrap import load_gold_labels

    gold_labels = load_gold_labels(GOLD_PATH)
    gold_snapshot = compute_gold_snapshot(gold_labels)

    baseline_run = HarnessRun(
        run_id="baseline_ablation_001",
        run_type="baseline",
        company_name="Elder Care",
        catalog="uc13_ale",
        ingestion_snapshot="uc13_ale:35034:2026-07-02",
        registry_hash=registry_hash,
        gold_snapshot=gold_snapshot,
        affected_intents=["fta.opex.q3_projected_financials"],
        gated_intents=["fta.opex.q3_projected_financials"],
        store_backend="sqlite",
        harness_status="incomplete",
        intent_count=1,
        created_at=created,
    )
    store.insert_run(baseline_run)
    from eval.retrieval.models import HarnessResult

    store.append_results(
        "baseline_ablation_001",
        [
            HarnessResult(
                intent_id="fta.opex.q3_projected_financials",
                eval_status="evaluated",
                recall_at_10=1.0,
                mrr=1.0,
                result_count=3,
                mode="semantic",
            ),
        ],
    )
    store.finalize_run("baseline_ablation_001", gate_pass=None, fallback_rate=0.0)

    @dataclass
    class _Route:
        chunks: list
        mode: str
        scores: list[float]

    def _fake_dispatch(intent, *, company_name, spark, ablation_arm=None):
        order = ["c-tier-2", "c-tier-1"] if ablation_arm == "tier_only" else ["c-tier-1", "c-tier-2"]
        return _Route(
            chunks=[SimpleNamespace(chunk_id=cid) for cid in order],
            mode="semantic",
            scores=[0.9, 0.8],
        )

    harness._retrieval_dispatch = _fake_dispatch
    report = harness.run(
        run_type="ablation",
        company_name="Elder Care",
        catalog="uc13_ale",
        store=store,
        store_backend="sqlite",
        baseline_ref_run_id="baseline_ablation_001",
        affected_intents=["fta.opex.q3_projected_financials"],
        ablation_config={"arm": "tier_only"},
        spark=MagicMock(),
    )

    assert report.manifest.ablation_arm == "tier_only"
    assert report.manifest.ablation_config == {"arm": "tier_only"}
    assert all(row.ablation_arm == "tier_only" for row in report.results)
    store.close()


def test_eval_harness_ablation_config_unknown_arm_fails_fast(tmp_path):
    store = SqliteEvalStore(tmp_path / "ablation_bad.sqlite")
    harness = EvalHarness(gold_path=GOLD_PATH, registry_path=default_registry_path())

    with pytest.raises(PreconditionError, match="unknown ablation arm"):
        harness.run(
            run_type="ablation",
            company_name="Elder Care",
            catalog="uc13_ale",
            store=store,
            store_backend="sqlite",
            ablation_config={"arm": "bogus"},
            spark=MagicMock(),
            skip_retrieval=True,
        )
    store.close()
