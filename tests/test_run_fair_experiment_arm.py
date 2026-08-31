"""Hermetic tests for the fair CIM vs full-VDR experiment driver.

On a clone without ``.dev/analysis/cim-vs-vdr/run_fair_experiment_arm.py``, tests
skip (path-exists guard) rather than fail.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DRIVER_PATH = REPO_ROOT / ".dev" / "analysis" / "cim-vs-vdr" / "run_fair_experiment_arm.py"
SUBMIT_PATH = REPO_ROOT / ".dev" / "analysis" / "cim-vs-vdr" / "submit_fair_experiment.py"

if not DRIVER_PATH.is_file():
    pytest.skip(
        "gitignored driver missing — skip on clones without .dev/analysis/",
        allow_module_level=True,
    )

_spec = importlib.util.spec_from_file_location("run_fair_experiment_arm", DRIVER_PATH)
assert _spec and _spec.loader
rfe = importlib.util.module_from_spec(_spec)
sys.modules["run_fair_experiment_arm"] = rfe
_spec.loader.exec_module(rfe)

_submit_spec = importlib.util.spec_from_file_location("submit_fair_experiment", SUBMIT_PATH)
assert _submit_spec and _submit_spec.loader
submit_mod = importlib.util.module_from_spec(_submit_spec)
sys.modules["submit_fair_experiment"] = submit_mod
_submit_spec.loader.exec_module(submit_mod)


def _sample_config(**overrides):
    defaults = {
        "arm": "A",
        "catalog": "uc13_ale",
        "company": "Elder Care",
        "llm_endpoint": "databricks-claude-sonnet-4-6",
        "extraction_endpoint": "databricks-claude-sonnet-4-6",
        "vision_endpoint": "",
        "skip_ingest": True,
        "git_sha": "abc123",
        "run_card_out": Path("/tmp/run_card.json"),
    }
    defaults.update(overrides)
    return rfe.FairExperimentArmConfig(**defaults)


def _sample_run_card(tmp_path: Path) -> rfe.RunCard:
    return rfe.RunCard(
        schema_version=1,
        arm="A",
        git_sha="sha",
        catalog="uc13_ale",
        company="Elder Care",
        llm_endpoint="databricks-claude-sonnet-4-6",
        extraction_endpoint="databricks-claude-sonnet-4-6",
        vision_endpoint="",
        run_orchestrator=True,
        ingest_ran=False,
        job_run_id=None,
        job_result_state="LOCAL",
        pipeline_manifest={"summary": {"SUCCESS": 9}, "runs": []},
        token_totals={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        token_breakdown={
            "databricks-claude-sonnet-4-6": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            }
        },
        estimated_cost_usd=0.01,
        wall_clock_s=1.0,
        duration_s_by_agent={"business_model": 12.0},
        analysis_row_created_at={"business_model": "2026-08-24T00:00:00"},
        report_paths={
            "phase5_memo_md": "/memo.md",
            "phase5_memo_docx": "/memo.docx",
            "tldr_md": "/tldr.md",
            "tldr_docx": "/tldr.docx",
            "full_report_md": "/full.md",
            "full_report_docx": "/full.docx",
        },
        diligence_report_present=True,
        bma_executive_summary_ok=True,
        status="SUCCESS",
    )


def test_run_card_roundtrip_required_keys(tmp_path: Path) -> None:
    out = tmp_path / "card.json"
    card = _sample_run_card(tmp_path)
    rfe.write_run_card(card, out)
    loaded = rfe.load_run_card(out)
    for field_name in rfe.RunCard.__dataclass_fields__:
        assert hasattr(loaded, field_name)
        assert getattr(loaded, field_name) == getattr(card, field_name)


def test_run_card_includes_token_breakdown(tmp_path: Path) -> None:
    card = _sample_run_card(tmp_path)
    assert "databricks-claude-sonnet-4-6" in card.token_breakdown
    assert card.token_breakdown["databricks-claude-sonnet-4-6"]["total_tokens"] == 15


def test_run_card_schema_version_is_1(tmp_path: Path) -> None:
    card = _sample_run_card(tmp_path)
    assert card.schema_version == 1


def test_config_rejects_catalog_uc13() -> None:
    with pytest.raises(rfe.FairExperimentConfigError, match="uc13"):
        _sample_config(catalog="uc13")


def test_config_accepts_uc13_ale_arm_a() -> None:
    cfg = _sample_config(arm="A", catalog="uc13_ale")
    assert cfg.catalog == "uc13_ale"


def test_config_arm_catalog_pairing() -> None:
    _sample_config(arm="A", catalog="uc13_ale")
    _sample_config(arm="B", catalog="uc13_preview")
    with pytest.raises(rfe.FairExperimentConfigError):
        _sample_config(arm="A", catalog="uc13_preview")
    with pytest.raises(rfe.FairExperimentConfigError):
        _sample_config(arm="B", catalog="uc13_ale")


def test_config_run_orchestrator_frozen_true() -> None:
    cfg = _sample_config()
    assert cfg.run_orchestrator is True


def test_config_default_endpoints_match() -> None:
    cfg = _sample_config()
    assert cfg.llm_endpoint == "databricks-claude-sonnet-4-6"
    assert cfg.extraction_endpoint == "databricks-claude-sonnet-4-6"


def test_run_arm_calls_run_pipeline_with_run_orchestrator_true(tmp_path: Path) -> None:
    config = _sample_config(run_card_out=tmp_path / "card.json", skip_ingest=True)
    spark = MagicMock()
    spark.sql.return_value.collect.side_effect = [
        [{"cnt": 1}],
        [{"executive_summary": "ok summary", "data_room_gaps": []}],
    ]

    manifest = {"summary": {"SUCCESS": 9}, "runs": [], "report_md_path": "/m.md"}
    exec_paths = {
        "tldr_md": "/t.md",
        "tldr_docx": "/t.docx",
        "full_report_md": "/f.md",
        "full_report_docx": "/f.docx",
    }

    with (
        patch.object(rfe, "_ensure_repo_paths", return_value=("d", "s")),
        patch("agents.shared.agent_base.reset_token_counter"),
        patch("agents.shared.agent_base.get_token_totals", return_value={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}),
        patch("agents.shared.agent_base.get_token_breakdown", return_value={}),
        patch("agents.orchestration.pipeline.run_pipeline", return_value=manifest) as rp,
        patch("agents.exec_summary.pipeline_entry.build_exec_summary", return_value=exec_paths),
        patch.object(rfe, "_latest_analysis_created_at", return_value={}),
    ):
        rfe.run_arm(config, spark=spark)

    rp.assert_called_once()
    assert rp.call_args.kwargs["run_orchestrator"] is True


def test_run_arm_calls_build_exec_summary_after_run_pipeline(tmp_path: Path) -> None:
    config = _sample_config(run_card_out=tmp_path / "card.json", skip_ingest=True)
    spark = MagicMock()
    spark.sql.return_value.collect.side_effect = [
        [{"cnt": 1}],
        [{"executive_summary": "ok", "data_room_gaps": []}],
    ]
    calls: list[str] = []

    def fake_pipeline(**_kwargs):
        calls.append("pipeline")
        return {"summary": {"SUCCESS": 1}, "runs": []}

    def fake_exec(**_kwargs):
        calls.append("exec")
        return {"tldr_md": "", "tldr_docx": "", "full_report_md": "", "full_report_docx": ""}

    with (
        patch.object(rfe, "_ensure_repo_paths", return_value=("d", "s")),
        patch("agents.shared.agent_base.reset_token_counter"),
        patch("agents.shared.agent_base.get_token_totals", return_value={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}),
        patch("agents.shared.agent_base.get_token_breakdown", return_value={}),
        patch("agents.orchestration.pipeline.run_pipeline", side_effect=fake_pipeline),
        patch("agents.exec_summary.pipeline_entry.build_exec_summary", side_effect=fake_exec),
        patch.object(rfe, "_latest_analysis_created_at", return_value={}),
    ):
        rfe.run_arm(config, spark=spark)

    assert calls == ["pipeline", "exec"]


def test_run_arm_does_not_call_rainmaker_or_diligence_runner(tmp_path: Path) -> None:
    config = _sample_config(run_card_out=tmp_path / "card.json", skip_ingest=True)
    spark = MagicMock()
    spark.sql.return_value.collect.side_effect = [
        [{"cnt": 1}],
        [{"executive_summary": "ok", "data_room_gaps": []}],
    ]

    rainmaker = MagicMock(side_effect=AssertionError("rainmaker"))
    diligence = MagicMock(side_effect=AssertionError("diligence"))
    full = MagicMock(side_effect=AssertionError("full"))

    with (
        patch.object(rfe, "_ensure_repo_paths", return_value=("d", "s")),
        patch("agents.shared.agent_base.reset_token_counter"),
        patch("agents.shared.agent_base.get_token_totals", return_value={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}),
        patch("agents.shared.agent_base.get_token_breakdown", return_value={}),
        patch("agents.orchestration.pipeline.run_pipeline", return_value={"summary": {"SUCCESS": 1}, "runs": []}),
        patch("agents.exec_summary.pipeline_entry.build_exec_summary", return_value={"tldr_md": "", "tldr_docx": "", "full_report_md": "", "full_report_docx": ""}),
        patch.object(rfe, "_latest_analysis_created_at", return_value={}),
        patch.dict(sys.modules, {"run_vdr_rainmaker": rainmaker}),
        patch.dict(sys.modules, {"run_diligence_pipeline": diligence}),
        patch.dict(sys.modules, {"run_full_pipeline": full}),
    ):
        rfe.run_arm(config, spark=spark)

    rainmaker.assert_not_called()
    diligence.assert_not_called()
    full.assert_not_called()


def test_run_arm_mirrors_catalog_to_environ_before_run_pipeline(tmp_path: Path) -> None:
    config = _sample_config(run_card_out=tmp_path / "card.json", skip_ingest=True)
    spark = MagicMock()
    spark.sql.return_value.collect.side_effect = [
        [{"cnt": 1}],
        [{"executive_summary": "ok", "data_room_gaps": []}],
    ]
    mirror_calls: list[tuple[bool, ...]] = []

    def track_mirror(cfg, **kwargs):
        mirror_calls.append((kwargs.get("include_vision", False),))

    pipeline_called = False

    def fake_pipeline(**_kwargs):
        nonlocal pipeline_called
        pipeline_called = True
        assert os.environ.get("catalog") == "uc13_ale"
        assert os.environ.get("RE2_CATALOG") == "uc13_ale"
        assert os.environ.get("RE2_STORE_BACKEND") == "delta"
        return {"summary": {"SUCCESS": 1}, "runs": []}

    with (
        patch.object(rfe, "_ensure_repo_paths", return_value=("d", "s")),
        patch.object(rfe, "_mirror_catalog_env", side_effect=track_mirror),
        patch("agents.shared.agent_base.reset_token_counter"),
        patch("agents.shared.agent_base.get_token_totals", return_value={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}),
        patch("agents.shared.agent_base.get_token_breakdown", return_value={}),
        patch("agents.orchestration.pipeline.run_pipeline", side_effect=fake_pipeline),
        patch("agents.exec_summary.pipeline_entry.build_exec_summary", return_value={"tldr_md": "", "tldr_docx": "", "full_report_md": "", "full_report_docx": ""}),
        patch.object(rfe, "_latest_analysis_created_at", return_value={}),
    ):
        rfe.run_arm(config, spark=spark)

    assert pipeline_called
    assert mirror_calls == [(False,)]


def test_run_arm_resets_tokens_before_dag(tmp_path: Path) -> None:
    config = _sample_config(run_card_out=tmp_path / "card.json", skip_ingest=True)
    spark = MagicMock()
    spark.sql.return_value.collect.side_effect = [
        [{"cnt": 1}],
        [{"executive_summary": "ok", "data_room_gaps": []}],
    ]
    order: list[str] = []

    with (
        patch.object(rfe, "_ensure_repo_paths", return_value=("d", "s")),
        patch("agents.shared.agent_base.reset_token_counter", side_effect=lambda: order.append("reset")),
        patch("agents.shared.agent_base.get_token_totals", return_value={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}),
        patch("agents.shared.agent_base.get_token_breakdown", return_value={}),
        patch("agents.orchestration.pipeline.run_pipeline", side_effect=lambda **_k: order.append("pipeline") or {"summary": {"SUCCESS": 1}, "runs": []}),
        patch("agents.exec_summary.pipeline_entry.build_exec_summary", return_value={"tldr_md": "", "tldr_docx": "", "full_report_md": "", "full_report_docx": ""}),
        patch.object(rfe, "_latest_analysis_created_at", return_value={}),
    ):
        rfe.run_arm(config, spark=spark)

    assert order[0] == "reset"
    assert "pipeline" in order


def test_run_scoped_ingest_mirrors_vision_endpoint() -> None:
    from types import ModuleType

    config = _sample_config(skip_ingest=False, vision_endpoint="")
    fake_ingest_mod = ModuleType("run_ingestion_pipeline")
    fake_ingest_mod.run_ingestion_pipeline = MagicMock(
        return_value={"phases": {"ingestion_parser": {"status": "SUCCESS"}}}
    )
    with (
        patch.object(rfe, "_mirror_catalog_env") as mirror,
        patch.dict(sys.modules, {"run_ingestion_pipeline": fake_ingest_mod}),
    ):
        rfe._run_scoped_ingest(config, str(rfe.SCRIPTS_DIR))
    mirror.assert_called_once_with(config, include_vision=True)


def test_run_arm_invokes_ingest_when_not_skipped(tmp_path: Path) -> None:
    config = _sample_config(
        run_card_out=tmp_path / "card.json",
        skip_ingest=False,
        ingest_if_stale=True,
    )
    spark = MagicMock()
    spark.sql.return_value.collect.side_effect = [
        [{"cnt": 1}],
        [{"executive_summary": "ok", "data_room_gaps": []}],
    ]

    with (
        patch.object(rfe, "_ensure_repo_paths", return_value=("d", "s")),
        patch.object(rfe, "_corpus_needs_ingest", return_value=True),
        patch.object(
            rfe,
            "_run_scoped_ingest",
            return_value={"phases": {"ingestion_parser": {"status": "SUCCESS"}}},
        ) as ingest_mock,
        patch("agents.shared.agent_base.reset_token_counter"),
        patch("agents.shared.agent_base.get_token_totals", return_value={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}),
        patch("agents.shared.agent_base.get_token_breakdown", return_value={}),
        patch("agents.orchestration.pipeline.run_pipeline", return_value={"summary": {"SUCCESS": 1}, "runs": []}),
        patch("agents.exec_summary.pipeline_entry.build_exec_summary", return_value={"tldr_md": "", "tldr_docx": "", "full_report_md": "", "full_report_docx": ""}),
        patch.object(rfe, "_latest_analysis_created_at", return_value={}),
    ):
        rfe.run_arm(config, spark=spark)

    ingest_mock.assert_called_once()


def test_run_arm_raises_fair_experiment_arm_failure_on_null_bma(tmp_path: Path) -> None:
    config = _sample_config(run_card_out=tmp_path / "card.json", skip_ingest=True)
    spark = MagicMock()
    spark.sql.return_value.collect.side_effect = [
        [{"cnt": 1}],
        [{"executive_summary": None, "data_room_gaps": []}],
    ]

    with (
        patch.object(rfe, "_ensure_repo_paths", return_value=("d", "s")),
        patch("agents.shared.agent_base.reset_token_counter"),
        patch("agents.shared.agent_base.get_token_totals", return_value={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}),
        patch("agents.shared.agent_base.get_token_breakdown", return_value={}),
        patch("agents.orchestration.pipeline.run_pipeline", return_value={"summary": {"SUCCESS": 1}, "runs": []}),
        patch("agents.exec_summary.pipeline_entry.build_exec_summary", return_value={"tldr_md": "", "tldr_docx": "", "full_report_md": "", "full_report_docx": ""}),
        patch.object(rfe, "_latest_analysis_created_at", return_value={}),
    ):
        with pytest.raises(rfe.FairExperimentArmFailure, match="bma_executive_summary_ok"):
            rfe.run_arm(config, spark=spark)

    loaded = rfe.load_run_card(config.run_card_out)
    assert loaded.status == "FAILED"
    assert loaded.bma_executive_summary_ok is False


def test_cli_flag_strings() -> None:
    parser = rfe.build_arg_parser()
    option_strings = sorted(
        opt
        for action in parser._actions
        for opt in action.option_strings
        if action.dest != "help"
    )
    expected = sorted(
        [
            "--arm",
            "--catalog",
            "--company",
            "--llm-endpoint",
            "--extraction-endpoint",
            "--vision-endpoint",
            "--skip-ingest",
            "--ingest-if-stale",
            "--run-card-out",
            "--git-sha",
        ]
    )
    assert option_strings == expected


def test_submit_env_deps_include_onboarding_minimum() -> None:
    deps = submit_mod.SERVERLESS_DEPS
    assert "pyyaml" in deps
    assert any("pydantic" in d for d in deps)
    assert "mlflow" in deps
    assert "jsonschema" in deps
    assert "python-docx" in deps


def test_config_rejects_catalog_uc13_mutation_falsifier() -> None:
    """Mutation check: removing uc13 guard lets invalid catalog construct."""
    with pytest.raises(rfe.FairExperimentConfigError):
        _sample_config(catalog="uc13", arm="A")

    original_post_init = rfe.FairExperimentArmConfig.__post_init__

    def lax_post_init(self) -> None:
        if self.arm not in ("A", "B"):
            raise rfe.FairExperimentConfigError("bad arm")

    rfe.FairExperimentArmConfig.__post_init__ = lax_post_init
    try:
        cfg = _sample_config(catalog="uc13", arm="A")
        assert cfg.catalog == "uc13"
    finally:
        rfe.FairExperimentArmConfig.__post_init__ = original_post_init

