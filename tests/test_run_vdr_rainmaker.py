"""Unit tests for jobs/scripts/run_vdr_rainmaker.py — the unified VDR runner.
Mocks every heavy dependency (Spark, ingestion, the 7-agent DAG, the full
pipeline, BundleBuilder, render_rainmaker) so this runs offline, no cluster
needed.

Covers the ONE decision the runner makes (plan docs/plans/connect-all-vdr-er.md
§1/§5): if a CIM is found → run the scoped Ruta 2 flow and render the
Rainmaker PDF; if not → (default, no_cim_mode="full") run the full Phase 1-5
pipeline and render the SAME Rainmaker PDF plus the full report, or
(no_cim_mode="noop", a kill switch) restore the old message-only behavior.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "databricks" / "jobs" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# This test needs the REAL mlflow package (BundleBuilder/agent_base do
# `import mlflow.pyfunc`). Some other test modules (e.g.
# test_ingestion_parser_sync.py, test_file_whitelist.py) install a minimal
# fake `types.ModuleType("mlflow")` into sys.modules to avoid needing a real
# mlflow install; if pytest happens to collect/run one of those files first
# in the same session, that stub (no `__path__`, so `mlflow.pyfunc` can't be
# imported as a submodule) leaks into this file's tests. Evict it so the
# next `import mlflow` re-resolves the real package — full-suite runs are
# unaffected either way since some other file always imports real mlflow
# first there; this only matters for narrow/selective test-file subsets.
_fake_mlflow = sys.modules.get("mlflow")
if _fake_mlflow is not None and not hasattr(_fake_mlflow, "__path__"):
    for _mod_name in [n for n in sys.modules if n == "mlflow" or n.startswith("mlflow.")]:
        del sys.modules[_mod_name]

import run_vdr_rainmaker as rvr  # noqa: E402
import run_vdr_pipeline as rvp  # noqa: E402
import vdr_progress as vp  # noqa: E402


def _make_spark():
    spark = MagicMock()
    spark.sql.return_value = None
    return spark


@pytest.fixture(autouse=True)
def _common_patches(monkeypatch, tmp_path):
    """Patch the Delta-table/Spark plumbing shared by every test."""
    spark = _make_spark()
    monkeypatch.setattr(rvp, "_get_spark", lambda: spark)
    monkeypatch.setattr(
        rvp, "_read_vdr_record",
        lambda _spark, _table, _id: {"id": _id, "company_name": "Elder Care"},
    )
    updates_log: list[dict] = []

    def _update(_spark, _table, _id, updates):
        updates_log.append(updates)

    monkeypatch.setattr(rvp, "_update_vdr_record", _update)
    monkeypatch.setattr(rvp, "_now_iso", lambda: "2026-08-04T00:00:00Z")
    monkeypatch.setattr(rvp, "_build_output_dir", lambda _company: str(tmp_path / "vdr_out"))
    return {"spark": spark, "updates": updates_log, "tmp_path": tmp_path}


def test_no_cim_found_noop_mode_is_a_pure_noop(monkeypatch, _common_patches):
    """no_cim_mode='noop' is the kill switch that restores the old
    message-only behavior — not the default, but must stay covered."""
    monkeypatch.setattr(rvr, "_detect_cim_files", lambda _company, _folder: [])

    ingestion_mock = MagicMock(side_effect=AssertionError("must not run ingestion without a CIM"))
    monkeypatch.setattr(
        "run_ingestion_pipeline.run_ingestion_pipeline", ingestion_mock, raising=False
    )
    pipeline_mock = MagicMock(side_effect=AssertionError("must not run the agent DAG without a CIM"))
    monkeypatch.setattr("agents.orchestration.pipeline.run_pipeline", pipeline_mock)
    render_mock = MagicMock(side_effect=AssertionError("must not render without a CIM"))
    monkeypatch.setattr("agents.exec_summary.renderers.render_rainmaker", render_mock)
    full_pipeline_mock = MagicMock(side_effect=AssertionError("must not run the full pipeline in noop mode"))
    monkeypatch.setattr("run_full_pipeline.run_full_pipeline", full_pipeline_mock, raising=False)

    result = rvr.run_vdr_rainmaker("some.table", 1, no_cim_mode="noop")

    assert result == {"status": "skipped", "company_name": "Elder Care", "reason": "no_cim_found"}
    updates = _common_patches["updates"]
    assert updates[0]["processing_status"] == "processing"
    assert updates[-1]["processing_status"] == "done"
    assert updates[-1]["completion_status"] == "success"
    assert "No CIM found" in updates[-1]["error_message"]
    ingestion_mock.assert_not_called()
    pipeline_mock.assert_not_called()
    render_mock.assert_not_called()
    full_pipeline_mock.assert_not_called()


def test_cim_found_runs_scoped_route_2_and_renders_pdf(monkeypatch, _common_patches):
    tmp_path = _common_patches["tmp_path"]
    cim_files = ["2024 Elder Care - CIM_vF.pdf"]
    monkeypatch.setattr(rvr, "_detect_cim_files", lambda _company, _folder: cim_files)

    ingestion_mock = MagicMock(
        return_value={
            "summary": {"SUCCESS": 4},
            "phases": {"ingestion_parser": {"status": "SUCCESS", "error": None}},
        }
    )
    monkeypatch.setattr(
        "run_ingestion_pipeline.run_ingestion_pipeline", ingestion_mock, raising=False
    )

    pipeline_mock = MagicMock(return_value={"summary": {"SUCCESS": 7}})
    monkeypatch.setattr("agents.orchestration.pipeline.run_pipeline", pipeline_mock)

    full_pipeline_mock = MagicMock(side_effect=AssertionError("must not run the full pipeline when a CIM is found"))
    monkeypatch.setattr("run_full_pipeline.run_full_pipeline", full_pipeline_mock, raising=False)

    fake_bundle = {"meta": {"company_name": "Elder Care"}}
    build_mock = MagicMock(return_value=fake_bundle)
    monkeypatch.setattr(
        "agents.exec_summary.bundle_builder.BundleBuilder.build", build_mock
    )
    validate_mock = MagicMock(return_value=None)
    monkeypatch.setattr("agents.exec_summary.validate.validate_bundle", validate_mock)

    pdf_path = tmp_path / "rainmaker.pdf"
    html_path = tmp_path / "rainmaker.html"
    pdf_path.write_bytes(b"%PDF-fake")
    html_path.write_text("<html>fake</html>")
    render_mock = MagicMock(return_value={"pdf": str(pdf_path), "html": str(html_path)})
    monkeypatch.setattr("agents.exec_summary.renderers.render_rainmaker", render_mock)

    monkeypatch.setattr(
        "agents.shared.agent_base.reset_token_counter", MagicMock(), raising=False
    )
    monkeypatch.setattr(
        "agents.shared.agent_base.get_token_totals",
        MagicMock(return_value={"completion_tokens": 1, "prompt_tokens": 2, "total_tokens": 3}),
        raising=False,
    )
    monkeypatch.setattr(
        "agents.shared.agent_base.print_token_summary", MagicMock(), raising=False
    )

    # Stage 2 (T09) also runs on Branch A — stub it out so this test stays
    # focused on stage 1 / the CIM-scoped Ruta 2 flow. Its own call sequence
    # and args are covered by test_branch_a_stage1_untouched_and_stage2_success.
    final_report_mock = _stub_final_report(monkeypatch, tmp_path, pdf=False, html=False)
    _stub_prior_mps_runs(monkeypatch)

    result = rvr.run_vdr_rainmaker("some.table", 1)

    # Ruta 2, scoped to the isolated preview catalog with the CIM whitelist.
    # Called twice: stage 1 (this assertion) and stage 2 (unscoped, T09).
    assert ingestion_mock.call_count == 2
    _, ingestion_kwargs = ingestion_mock.call_args_list[0]
    assert ingestion_kwargs["catalog"] == "uc13_preview"
    assert ingestion_kwargs["file_whitelist"] == cim_files
    assert ingestion_kwargs["parse_priority_tiers"] == "all"
    # Since Ale's M0-M4 merge, ParseManifest skips docs already COMPLETE in
    # doc_status. Without force, re-previewing the same CIM is a silent no-op.
    assert ingestion_kwargs["force"] == "company"

    assert pipeline_mock.call_count == 2
    _, pipeline_kwargs = pipeline_mock.call_args_list[0]
    assert pipeline_kwargs["catalog"] == "uc13_preview"
    assert pipeline_kwargs["run_orchestrator"] is False  # one-pager only, no memo

    build_mock.assert_called_once()
    validate_mock.assert_called_once_with(fake_bundle)
    render_mock.assert_called_once()
    full_pipeline_mock.assert_not_called()
    final_report_mock.assert_called_once()

    assert result["status"] == "success"
    assert result["mode"] == "cim_preview"
    assert result["cim_files"] == cim_files
    copied = {Path(p).name for p in result["files"]}
    assert copied == {"executive_summary.pdf", "rainmaker_opportunity_summary.html"}
    for p in result["files"]:
        assert Path(p).exists()

    updates = _common_patches["updates"]
    assert updates[-1]["processing_status"] == "done"
    assert updates[-1]["completion_status"] == "success"
    assert updates[-1]["results_location"].endswith("/")


def test_exception_during_route_2_marks_record_as_error(monkeypatch, _common_patches):
    monkeypatch.setattr(
        rvr, "_detect_cim_files", lambda _company, _folder: ["2024 Elder Care - CIM_vF.pdf"]
    )
    monkeypatch.setattr(
        "run_ingestion_pipeline.run_ingestion_pipeline",
        MagicMock(side_effect=RuntimeError("ingestion boom")),
        raising=False,
    )

    with pytest.raises(RuntimeError, match="ingestion boom"):
        rvr.run_vdr_rainmaker("some.table", 1)

    updates = _common_patches["updates"]
    assert updates[-1]["processing_status"] == "error"
    assert updates[-1]["completion_status"] == "failure"
    assert "ingestion boom" in updates[-1]["error_message"]


def test_failed_parse_phase_aborts_instead_of_building_on_stale_chunks(
    monkeypatch, _common_patches
):
    """`run_ingestion_pipeline` reports phase failures in its return value rather
    than raising — only its CLI `main()` maps failure to a non-zero exit. Called
    programmatically, a failed parse used to pass silently: the agents would run
    against whatever chunks the catalog already held and the job reported SUCCESS
    on a PDF built from stale data (observed on run 572985817765568).
    """
    monkeypatch.setattr(
        rvr, "_detect_cim_files", lambda _company, _folder: ["2024 Elder Care - CIM_vF.pdf"]
    )
    monkeypatch.setattr(
        "run_ingestion_pipeline.run_ingestion_pipeline",
        MagicMock(
            return_value={
                "summary": {"SUCCESS": 2, "FAILED": 1},
                "phases": {
                    "download_upload": {"status": "SUCCESS", "error": None},
                    "document_classifier": {"status": "SUCCESS", "error": None},
                    "ingestion_parser": {
                        "status": "FAILED",
                        "error": "WRONG_COLUMN_DEFAULTS_FOR_DELTA_FEATURE_NOT_ENABLED",
                    },
                },
            }
        ),
        raising=False,
    )
    pipeline_mock = MagicMock()
    monkeypatch.setattr("agents.orchestration.pipeline.run_pipeline", pipeline_mock)

    with pytest.raises(RuntimeError, match="refusing to build a preview"):
        rvr.run_vdr_rainmaker("some.table", 1)

    # The agents must never have been reached.
    pipeline_mock.assert_not_called()

    updates = _common_patches["updates"]
    assert updates[-1]["processing_status"] == "error"
    assert updates[-1]["completion_status"] == "failure"
    # The operator needs the underlying cause, not just "it failed".
    assert "ingestion_parser=FAILED" in updates[-1]["error_message"]


def test_no_regression_run_vdr_pipeline_module_untouched():
    """The existing VDR job's module must not be modified by this work (plan §10)."""
    import run_vdr_pipeline as rvp_module

    assert hasattr(rvp_module, "run_vdr_pipeline")
    assert hasattr(rvp_module, "main")


# ---------------------------------------------------------------------------
# No-CIM branch — full-room pipeline + the same Rainmaker executive review
# ---------------------------------------------------------------------------

def _fake_full_pipeline_result(tmp_path, *, ingestion_status="SUCCESS", diligence_success=9):
    report_docx = tmp_path / "full_report.docx"
    report_docx.write_bytes(b"fake docx")
    tldr_docx = tmp_path / "executive_summary_rev3.docx"
    tldr_docx.write_bytes(b"fake docx")
    return {
        "company_name": "Elder Care",
        "ingestion": {
            "phases": {
                "download_upload": {"status": "SUCCESS", "error": None},
                "document_classifier": {"status": "SUCCESS", "error": None},
                "ingestion_parser": {"status": ingestion_status, "error": None},
                "company_profiler": {"status": "SUCCESS", "error": None},
            },
            "summary": {"SUCCESS": 4, "FAILED": 0, "SKIPPED": 0},
        },
        "diligence": {"summary": {"SUCCESS": diligence_success, "FAILED": 0, "SKIPPED": 9 - diligence_success}},
        "summary": {
            "ingestion": {"SUCCESS": 4, "FAILED": 0, "SKIPPED": 0},
            "diligence": {"SUCCESS": diligence_success, "FAILED": 0, "SKIPPED": 9 - diligence_success},
        },
        "report_md_path": None,
        "report_docx_path": str(report_docx),
        "tldr_md_path": None,
        "tldr_docx_path": str(tldr_docx),
    }


def _stub_rainmaker_summary(monkeypatch, tmp_path):
    pdf_path = tmp_path / "rainmaker.pdf"
    html_path = tmp_path / "rainmaker.html"
    pdf_path.write_bytes(b"%PDF-fake")
    html_path.write_text("<html>fake</html>")
    mock = MagicMock(
        return_value={"pdf": str(pdf_path), "html": str(html_path), "synthesis_status": "success"}
    )
    monkeypatch.setattr("agents.exec_summary.rainmaker_entry.build_rainmaker_summary", mock)
    return mock


def _stub_token_counters(monkeypatch):
    monkeypatch.setattr("agents.shared.agent_base.reset_token_counter", MagicMock(), raising=False)
    monkeypatch.setattr(
        "agents.shared.agent_base.get_token_totals",
        MagicMock(return_value={"completion_tokens": 1, "prompt_tokens": 2, "total_tokens": 3}),
        raising=False,
    )
    monkeypatch.setattr("agents.shared.agent_base.print_token_summary", MagicMock(), raising=False)


def test_no_cim_runs_full_pipeline_and_renders_rainmaker(monkeypatch, _common_patches):
    tmp_path = _common_patches["tmp_path"]
    monkeypatch.setattr(rvr, "_detect_cim_files", lambda _company, _folder: [])

    full_pipeline_mock = MagicMock(return_value=_fake_full_pipeline_result(tmp_path))
    monkeypatch.setattr("run_full_pipeline.run_full_pipeline", full_pipeline_mock, raising=False)

    rainmaker_mock = _stub_rainmaker_summary(monkeypatch, tmp_path)
    _stub_token_counters(monkeypatch)

    ingestion_mock = MagicMock(side_effect=AssertionError("must not run the CIM-scoped ingestion path"))
    monkeypatch.setattr(
        "run_ingestion_pipeline.run_ingestion_pipeline", ingestion_mock, raising=False
    )
    pipeline_mock = MagicMock(side_effect=AssertionError("must not run the CIM-scoped Ruta 2 DAG"))
    monkeypatch.setattr("agents.orchestration.pipeline.run_pipeline", pipeline_mock)

    result = rvr.run_vdr_rainmaker("some.table", 1)

    full_pipeline_mock.assert_called_once()
    _, kwargs = full_pipeline_mock.call_args
    assert kwargs["catalog"] == "uc13_preview"
    assert "force" not in kwargs
    assert "file_whitelist" not in kwargs

    rainmaker_mock.assert_called_once()
    args, kwargs = rainmaker_mock.call_args
    assert args[1] == "uc13_preview"
    assert kwargs.get("run_mode") == "full_vdr_no_cim"

    ingestion_mock.assert_not_called()
    pipeline_mock.assert_not_called()

    assert result["status"] == "success"
    assert result["mode"] == "full_pipeline"
    assert result["cim_files"] == []
    names = {Path(p).name for p in result["files"]}
    # The Phase-5 orchestrator memo is still generated, but no longer copied
    # into the delivery folder: the stage-2 final report now delivers as
    # full_report.pdf/html and the UI resolves a run's report by that base
    # name alone, so two different documents cannot share it.
    assert names == {"executive_summary.pdf", "rainmaker_opportunity_summary.html"}
    assert "executive_summary.docx" not in names

    updates = _common_patches["updates"]
    assert updates[-1]["processing_status"] == "done"
    assert updates[-1]["completion_status"] == "success"


def test_no_cim_narrative_llm_runs_on_the_full_room_path(monkeypatch, _common_patches):
    """Guards against silently degrading the full-room executive review by
    skipping the LLM narrative — it must run identically to the CIM path."""
    tmp_path = _common_patches["tmp_path"]
    monkeypatch.setattr(rvr, "_detect_cim_files", lambda _company, _folder: [])
    monkeypatch.setattr(
        "run_full_pipeline.run_full_pipeline",
        MagicMock(return_value=_fake_full_pipeline_result(tmp_path)),
        raising=False,
    )
    rainmaker_mock = _stub_rainmaker_summary(monkeypatch, tmp_path)
    _stub_token_counters(monkeypatch)

    rvr.run_vdr_rainmaker("some.table", 1)

    args, kwargs = rainmaker_mock.call_args
    llm_endpoint = args[3] if len(args) > 3 else kwargs.get("llm_endpoint")
    assert llm_endpoint, "build_rainmaker_summary must receive a non-empty llm_endpoint"


def test_no_branch_ever_writes_to_production_catalog(monkeypatch, _common_patches):
    """The one regression that would silently write to production `uc13`."""
    tmp_path = _common_patches["tmp_path"]

    # No-CIM branch.
    monkeypatch.setattr(rvr, "_detect_cim_files", lambda _company, _folder: [])
    full_pipeline_mock = MagicMock(return_value=_fake_full_pipeline_result(tmp_path))
    monkeypatch.setattr("run_full_pipeline.run_full_pipeline", full_pipeline_mock, raising=False)
    rainmaker_mock = _stub_rainmaker_summary(monkeypatch, tmp_path)
    _stub_token_counters(monkeypatch)

    rvr.run_vdr_rainmaker("some.table", 1)

    for call in (full_pipeline_mock.call_args, rainmaker_mock.call_args):
        args, kwargs = call
        catalogs = [a for a in args if isinstance(a, str)] + [
            v for v in kwargs.values() if isinstance(v, str)
        ]
        assert "uc13" not in catalogs, f"a literal 'uc13' catalog leaked into {call}"
        assert all(c != "uc13" for c in catalogs)


def test_no_cim_full_pipeline_failed_parse_aborts(monkeypatch, _common_patches):
    """run_full_pipeline's own `parser_ok` guard accepts SKIPPED as well as
    SUCCESS — not strict enough for this job. Require SUCCESS explicitly."""
    tmp_path = _common_patches["tmp_path"]
    monkeypatch.setattr(rvr, "_detect_cim_files", lambda _company, _folder: [])
    monkeypatch.setattr(
        "run_full_pipeline.run_full_pipeline",
        MagicMock(return_value=_fake_full_pipeline_result(tmp_path, ingestion_status="SKIPPED")),
        raising=False,
    )
    rainmaker_mock = _stub_rainmaker_summary(monkeypatch, tmp_path)
    _stub_token_counters(monkeypatch)

    with pytest.raises(RuntimeError, match="Full-room ingestion did not complete"):
        rvr.run_vdr_rainmaker("some.table", 1)

    rainmaker_mock.assert_not_called()
    updates = _common_patches["updates"]
    assert updates[-1]["processing_status"] == "error"
    assert updates[-1]["completion_status"] == "failure"


def test_no_cim_zero_successful_agents_aborts(monkeypatch, _common_patches):
    tmp_path = _common_patches["tmp_path"]
    monkeypatch.setattr(rvr, "_detect_cim_files", lambda _company, _folder: [])
    monkeypatch.setattr(
        "run_full_pipeline.run_full_pipeline",
        MagicMock(return_value=_fake_full_pipeline_result(tmp_path, diligence_success=0)),
        raising=False,
    )
    rainmaker_mock = _stub_rainmaker_summary(monkeypatch, tmp_path)
    _stub_token_counters(monkeypatch)

    with pytest.raises(RuntimeError, match="no successful agents"):
        rvr.run_vdr_rainmaker("some.table", 1)

    rainmaker_mock.assert_not_called()
    updates = _common_patches["updates"]
    assert updates[-1]["processing_status"] == "error"


def test_cim_branch_unchanged(monkeypatch, _common_patches):
    """The refactor to share build_rainmaker_summary must not change the CIM
    branch's own decisions: still whitelisted + force='company', still
    one-pager only, and it must never touch the full-room entry point."""
    tmp_path = _common_patches["tmp_path"]
    cim_files = ["2024 Elder Care - CIM_vF.pdf"]
    monkeypatch.setattr(rvr, "_detect_cim_files", lambda _company, _folder: cim_files)

    ingestion_mock = MagicMock(
        return_value={
            "summary": {"SUCCESS": 4},
            "phases": {"ingestion_parser": {"status": "SUCCESS", "error": None}},
        }
    )
    monkeypatch.setattr(
        "run_ingestion_pipeline.run_ingestion_pipeline", ingestion_mock, raising=False
    )
    pipeline_mock = MagicMock(return_value={"summary": {"SUCCESS": 7}})
    monkeypatch.setattr("agents.orchestration.pipeline.run_pipeline", pipeline_mock)
    full_pipeline_mock = MagicMock(side_effect=AssertionError("CIM branch must never call run_full_pipeline"))
    monkeypatch.setattr("run_full_pipeline.run_full_pipeline", full_pipeline_mock, raising=False)

    rainmaker_mock = _stub_rainmaker_summary(monkeypatch, tmp_path)
    _stub_token_counters(monkeypatch)
    # Stage 2 (T09) also runs on Branch A — stub it out, out of scope here.
    _stub_final_report(monkeypatch, tmp_path, pdf=False, html=False)
    _stub_prior_mps_runs(monkeypatch)

    rvr.run_vdr_rainmaker("some.table", 1)

    _, ingestion_kwargs = ingestion_mock.call_args_list[0]
    assert ingestion_kwargs["file_whitelist"] == cim_files
    assert ingestion_kwargs["force"] == "company"
    _, pipeline_kwargs = pipeline_mock.call_args_list[0]
    assert pipeline_kwargs["run_orchestrator"] is False
    full_pipeline_mock.assert_not_called()
    rainmaker_mock.assert_called_once()
    _, rainmaker_kwargs = rainmaker_mock.call_args
    assert rainmaker_kwargs.get("run_mode") == "cim_only"


# ---------------------------------------------------------------------------
# T09 — Stage 2: _run_final_report_stage(), wired into both branches
# ---------------------------------------------------------------------------

_LEGAL_PROCESSING_STATUSES = {"processing", "done", "error"}


def _assert_processing_status_always_legal(updates):
    for u in updates:
        if "processing_status" in u:
            assert u["processing_status"] in _LEGAL_PROCESSING_STATUSES, u


def _stub_final_report(monkeypatch, tmp_path, *, status="success", pdf=True,
                        html=True, pdf_degraded=False, mps_source="scored"):
    result = {"status": status, "mps_source": mps_source, "pdf_degraded": pdf_degraded,
              "synthesis_status": status, "final_narrative_status": status,
              "mps_status": status, "error": None}
    if pdf:
        pdf_path = tmp_path / "full_report.pdf"
        pdf_path.write_bytes(b"%PDF-fake-final")
        result["pdf"] = str(pdf_path)
    else:
        result["pdf"] = None
    if html:
        html_path = tmp_path / "full_report.html"
        html_path.write_text("<html>final</html>")
        result["html"] = str(html_path)
    else:
        result["html"] = None
    mock = MagicMock(return_value=result)
    monkeypatch.setattr("agents.exec_summary.final_report_entry.build_final_report", mock)
    return mock


def _stub_prior_mps_runs(monkeypatch, return_value=None):
    mock = MagicMock(return_value=[] if return_value is None else return_value)
    monkeypatch.setattr("agents.exec_summary.final_report_entry._load_prior_mps_runs", mock)
    return mock


def _cim_branch_common_mocks(monkeypatch, cim_files=("2024 Elder Care - CIM_vF.pdf",)):
    cim_files = list(cim_files)
    monkeypatch.setattr(rvr, "_detect_cim_files", lambda _company, _folder: cim_files)
    ingestion_mock = MagicMock(
        return_value={
            "summary": {"SUCCESS": 4},
            "phases": {"ingestion_parser": {"status": "SUCCESS", "error": None}},
        }
    )
    monkeypatch.setattr(
        "run_ingestion_pipeline.run_ingestion_pipeline", ingestion_mock, raising=False
    )
    pipeline_mock = MagicMock(return_value={"summary": {"SUCCESS": 7}})
    monkeypatch.setattr("agents.orchestration.pipeline.run_pipeline", pipeline_mock)
    return cim_files, ingestion_mock, pipeline_mock


def test_branch_a_stage1_untouched_and_stage2_success(monkeypatch, _common_patches):
    """Stage 1's own calls/args are exactly as before; stage 2 reads the rest
    of the room (no file_whitelist, no force) and both final_report.* files
    are copied. DoD-2."""
    tmp_path = _common_patches["tmp_path"]
    cim_files, ingestion_mock, pipeline_mock = _cim_branch_common_mocks(monkeypatch)
    rainmaker_mock = _stub_rainmaker_summary(monkeypatch, tmp_path)
    _stub_token_counters(monkeypatch)
    final_report_mock = _stub_final_report(monkeypatch, tmp_path)
    prior_mock = _stub_prior_mps_runs(monkeypatch, return_value=[{"run_mode": "cim_only"}])

    result = rvr.run_vdr_rainmaker("some.table", 1)

    assert ingestion_mock.call_count == 2
    stage1_kwargs = ingestion_mock.call_args_list[0].kwargs
    assert stage1_kwargs["file_whitelist"] == cim_files
    assert stage1_kwargs["force"] == "company"
    assert stage1_kwargs["parse_priority_tiers"] == "all"
    stage2_kwargs = ingestion_mock.call_args_list[1].kwargs
    assert "file_whitelist" not in stage2_kwargs
    assert "force" not in stage2_kwargs
    assert stage2_kwargs["catalog"] == "uc13_preview"
    assert stage2_kwargs["parse_priority_tiers"] == "1,2"

    assert pipeline_mock.call_count == 2
    for call in pipeline_mock.call_args_list:
        assert call.kwargs["run_orchestrator"] is False

    final_report_mock.assert_called_once()
    args, kwargs = final_report_mock.call_args
    assert kwargs["run_mode"] == "full_vdr_after_cim"
    assert kwargs["prior_mps_runs"] == [{"run_mode": "cim_only"}]
    prior_call_args = prior_mock.call_args_list[0][0]
    assert prior_call_args[1:] == ("uc13_preview", "Elder Care", ("cim_only",))

    assert result["status"] == "success"
    names = {Path(p).name for p in result["files"]}
    assert names == {
        "executive_summary.pdf", "rainmaker_opportunity_summary.html",
        "full_report.pdf", "full_report.html",
    }

    updates = _common_patches["updates"]
    assert updates[-1]["processing_status"] == "done"
    assert updates[-1]["completion_status"] == "success"
    assert updates[-1]["results_location"].endswith("/")
    _assert_processing_status_always_legal(updates)


def test_branch_a_stage2_ingestion_failure_keeps_er_intact(monkeypatch, _common_patches):
    """DoD-5: a stage-2 ingestion failure must not escape, must not remove
    the executive review, and the record stays honest about what failed."""
    tmp_path = _common_patches["tmp_path"]
    _cim_branch_common_mocks(monkeypatch)
    rainmaker_mock = _stub_rainmaker_summary(monkeypatch, tmp_path)
    _stub_token_counters(monkeypatch)

    stage2_ingestion_mock = MagicMock(
        return_value={
            "phases": {
                "ingestion_parser": {"status": "FAILED", "error": "boom"},
            },
        }
    )

    def _ingestion_router(**kwargs):
        if kwargs.get("file_whitelist"):
            return {
                "summary": {"SUCCESS": 4},
                "phases": {"ingestion_parser": {"status": "SUCCESS", "error": None}},
            }
        return stage2_ingestion_mock(**kwargs)

    monkeypatch.setattr(
        "run_ingestion_pipeline.run_ingestion_pipeline", _ingestion_router, raising=False
    )
    final_report_mock = MagicMock(side_effect=AssertionError("must not build the final report"))
    monkeypatch.setattr("agents.exec_summary.final_report_entry.build_final_report", final_report_mock)

    # No exception must escape.
    result = rvr.run_vdr_rainmaker("some.table", 1)

    final_report_mock.assert_not_called()
    assert result["status"] == "success"
    names = {Path(p).name for p in result["files"]}
    assert names == {"executive_summary.pdf", "rainmaker_opportunity_summary.html"}

    updates = _common_patches["updates"]
    assert updates[-1]["processing_status"] == "done"
    # A-1: no CHECK constraint exists on the live table, but only
    # success/failure have ever been written and the UI's vocabulary is
    # unknown — fall back to "success" + error_message rather than "partial".
    assert updates[-1]["completion_status"] == "success"
    assert updates[-1]["results_location"].endswith("/")
    assert "boom" in updates[-1]["error_message"] or "ingestion" in updates[-1]["error_message"].lower()
    _assert_processing_status_always_legal(updates)


def test_branch_a_stage2_build_final_report_failed_status(monkeypatch, _common_patches):
    """A `build_final_report` that reports status='failed' (never raises) is
    handled the same way as a raised exception in stage 2 — ER stays intact."""
    tmp_path = _common_patches["tmp_path"]
    _cim_branch_common_mocks(monkeypatch)
    _stub_rainmaker_summary(monkeypatch, tmp_path)
    _stub_token_counters(monkeypatch)
    _stub_prior_mps_runs(monkeypatch)
    _stub_final_report(monkeypatch, tmp_path, status="failed", pdf=False, html=False)

    result = rvr.run_vdr_rainmaker("some.table", 1)

    assert result["status"] == "success"
    names = {Path(p).name for p in result["files"]}
    assert names == {"executive_summary.pdf", "rainmaker_opportunity_summary.html"}

    updates = _common_patches["updates"]
    assert updates[-1]["processing_status"] == "done"
    assert updates[-1]["completion_status"] == "success"
    assert updates[-1]["error_message"]
    _assert_processing_status_always_legal(updates)


def test_branch_a_stage2_unanticipated_exception_keeps_er_intact(monkeypatch, _common_patches):
    """DoD-18: an exception nobody wrote a branch for — here, the stage-2
    agent DAG call itself raising — must be swallowed by
    `_run_final_report_stage`'s own `try/except`, not by an explicit
    early-return path. The ER must survive exactly like the handled T09
    failures do."""
    tmp_path = _common_patches["tmp_path"]
    _cim_branch_common_mocks(monkeypatch)
    _stub_rainmaker_summary(monkeypatch, tmp_path)
    _stub_token_counters(monkeypatch)
    _stub_prior_mps_runs(monkeypatch)
    final_report_mock = MagicMock(side_effect=RuntimeError("must not build the final report"))
    monkeypatch.setattr("agents.exec_summary.final_report_entry.build_final_report", final_report_mock)

    # Stage 1's own agent call (run_orchestrator=False) must succeed as
    # normal; only stage 2's call (the second one) raises unexpectedly.
    pipeline_mock = MagicMock(
        side_effect=[{"summary": {"SUCCESS": 7}}, RuntimeError("agent DAG boom")]
    )
    monkeypatch.setattr("agents.orchestration.pipeline.run_pipeline", pipeline_mock)

    result = rvr.run_vdr_rainmaker("some.table", 1)

    assert pipeline_mock.call_count == 2
    final_report_mock.assert_not_called()
    assert result["status"] == "success"
    names = {Path(p).name for p in result["files"]}
    assert names == {"executive_summary.pdf", "rainmaker_opportunity_summary.html"}

    updates = _common_patches["updates"]
    assert updates[-1]["processing_status"] == "done"
    assert updates[-1]["completion_status"] == "success"
    assert updates[-1]["results_location"].endswith("/")
    assert "agent DAG boom" in updates[-1]["error_message"]
    progress_update = next(u for u in reversed(updates) if "progress_json" in u)
    progress_stages = {
        s["key"]: s["status"] for s in json.loads(progress_update["progress_json"])
    }
    assert progress_stages["vdr_agents"] == "failed"
    _assert_processing_status_always_legal(updates)


def test_branch_a_stage2_copy_final_report_raises_keeps_er_intact(monkeypatch, _common_patches):
    """DoD-18: a realistic unhandled raise from a stage-2 collaborator that
    is not `run_ingestion_pipeline`/`build_final_report` — here,
    `shutil.copy2` failing while delivering `full_report.pdf` (permission
    or quota error) — must degrade the same way."""
    tmp_path = _common_patches["tmp_path"]
    _cim_branch_common_mocks(monkeypatch)
    _stub_rainmaker_summary(monkeypatch, tmp_path)
    _stub_token_counters(monkeypatch)
    _stub_prior_mps_runs(monkeypatch)
    _stub_final_report(monkeypatch, tmp_path)

    real_copy2 = shutil.copy2

    def _copy2_router(src, dst, *args, **kwargs):
        if Path(dst).name == "full_report.pdf":
            raise RuntimeError("disk quota exceeded")
        return real_copy2(src, dst, *args, **kwargs)

    monkeypatch.setattr(rvr.shutil, "copy2", _copy2_router)

    result = rvr.run_vdr_rainmaker("some.table", 1)

    assert result["status"] == "success"
    names = {Path(p).name for p in result["files"]}
    assert names == {"executive_summary.pdf", "rainmaker_opportunity_summary.html"}

    updates = _common_patches["updates"]
    assert updates[-1]["processing_status"] == "done"
    assert updates[-1]["completion_status"] == "success"
    assert updates[-1]["results_location"].endswith("/")
    assert "disk quota exceeded" in updates[-1]["error_message"]
    progress_update = next(u for u in reversed(updates) if "progress_json" in u)
    progress_stages = {
        s["key"]: s["status"] for s in json.loads(progress_update["progress_json"])
    }
    assert progress_stages["final_report"] == "failed"
    _assert_processing_status_always_legal(updates)


def test_branch_a_stage1_failure_never_reaches_stage2(monkeypatch, _common_patches):
    monkeypatch.setattr(
        rvr, "_detect_cim_files", lambda _company, _folder: ["2024 Elder Care - CIM_vF.pdf"]
    )
    monkeypatch.setattr(
        "run_ingestion_pipeline.run_ingestion_pipeline",
        MagicMock(side_effect=RuntimeError("ingestion boom")),
        raising=False,
    )
    final_report_mock = MagicMock(side_effect=AssertionError("stage 2 must never run"))
    monkeypatch.setattr("agents.exec_summary.final_report_entry.build_final_report", final_report_mock)

    with pytest.raises(RuntimeError, match="ingestion boom"):
        rvr.run_vdr_rainmaker("some.table", 1)

    final_report_mock.assert_not_called()
    updates = _common_patches["updates"]
    assert updates[-1]["processing_status"] == "error"
    assert updates[-1]["completion_status"] == "failure"
    _assert_processing_status_always_legal(updates)


def test_branch_b_stage2_reuses_ingestion_and_agents_not_rerun(monkeypatch, _common_patches):
    tmp_path = _common_patches["tmp_path"]
    monkeypatch.setattr(rvr, "_detect_cim_files", lambda _company, _folder: [])
    monkeypatch.setattr(
        "run_full_pipeline.run_full_pipeline",
        MagicMock(return_value=_fake_full_pipeline_result(tmp_path)),
        raising=False,
    )
    _stub_rainmaker_summary(monkeypatch, tmp_path)
    _stub_token_counters(monkeypatch)

    ingestion_mock = MagicMock(side_effect=AssertionError("stage 2 must not re-ingest on Branch B"))
    monkeypatch.setattr(
        "run_ingestion_pipeline.run_ingestion_pipeline", ingestion_mock, raising=False
    )
    pipeline_mock = MagicMock(side_effect=AssertionError("stage 2 must not re-run agents on Branch B"))
    monkeypatch.setattr("agents.orchestration.pipeline.run_pipeline", pipeline_mock)

    final_report_mock = _stub_final_report(monkeypatch, tmp_path)
    prior_mock = _stub_prior_mps_runs(monkeypatch)

    result = rvr.run_vdr_rainmaker("some.table", 1)

    ingestion_mock.assert_not_called()
    pipeline_mock.assert_not_called()
    final_report_mock.assert_called_once()
    _, kwargs = final_report_mock.call_args
    assert kwargs["run_mode"] == "full_vdr_no_cim"
    assert kwargs["prior_mps_runs"] is None  # prior_run_modes=() → no prior column

    assert result["status"] == "success"
    names = {Path(p).name for p in result["files"]}
    assert names == {
        "executive_summary.pdf", "rainmaker_opportunity_summary.html",
        "full_report.pdf", "full_report.html",
    }
    updates = _common_patches["updates"]
    assert updates[-1]["processing_status"] == "done"
    assert updates[-1]["completion_status"] == "success"
    _assert_processing_status_always_legal(updates)


def test_branch_b_d02_reuses_the_ers_mps_run_and_never_rescopes(monkeypatch, _common_patches):
    """DoD-12: build_final_report receives the ER's read-back run as
    reuse_mps_run, and MPSAgent.score is never invoked a second time."""
    tmp_path = _common_patches["tmp_path"]
    monkeypatch.setattr(rvr, "_detect_cim_files", lambda _company, _folder: [])
    monkeypatch.setattr(
        "run_full_pipeline.run_full_pipeline",
        MagicMock(return_value=_fake_full_pipeline_result(tmp_path)),
        raising=False,
    )
    _stub_rainmaker_summary(monkeypatch, tmp_path)
    _stub_token_counters(monkeypatch)

    er_run = {"run_mode": "full_vdr_no_cim", "total": 24.0}
    prior_mock = _stub_prior_mps_runs(monkeypatch, return_value=[er_run])
    final_report_mock = _stub_final_report(monkeypatch, tmp_path, mps_source="reused")

    score_mock = MagicMock(side_effect=AssertionError("MPSAgent.score must not be called on reuse"))
    monkeypatch.setattr("agents.workstreams.mps_agent.MPSAgent.score", score_mock)

    result = rvr.run_vdr_rainmaker("some.table", 1)

    score_mock.assert_not_called()
    final_report_mock.assert_called_once()
    _, kwargs = final_report_mock.call_args
    assert kwargs["reuse_mps_run"] is er_run
    assert result["status"] == "success"


def test_branch_b_readback_empty_falls_back_to_scoring(monkeypatch, _common_patches):
    tmp_path = _common_patches["tmp_path"]
    monkeypatch.setattr(rvr, "_detect_cim_files", lambda _company, _folder: [])
    monkeypatch.setattr(
        "run_full_pipeline.run_full_pipeline",
        MagicMock(return_value=_fake_full_pipeline_result(tmp_path)),
        raising=False,
    )
    _stub_rainmaker_summary(monkeypatch, tmp_path)
    _stub_token_counters(monkeypatch)

    _stub_prior_mps_runs(monkeypatch, return_value=[])
    final_report_mock = _stub_final_report(monkeypatch, tmp_path, mps_source="scored_fallback")

    result = rvr.run_vdr_rainmaker("some.table", 1)

    _, kwargs = final_report_mock.call_args
    assert kwargs["reuse_mps_run"] is None
    assert result["status"] == "success"
    updates = _common_patches["updates"]
    assert updates[-1]["processing_status"] == "done"
    assert updates[-1]["completion_status"] == "success"


def test_branch_b_noop_mode_has_no_stage2_progress_beyond_scan(monkeypatch, _common_patches):
    monkeypatch.setattr(rvr, "_detect_cim_files", lambda _company, _folder: [])
    final_report_mock = MagicMock(side_effect=AssertionError("noop must never reach stage 2"))
    monkeypatch.setattr("agents.exec_summary.final_report_entry.build_final_report", final_report_mock)

    result = rvr.run_vdr_rainmaker("some.table", 1, no_cim_mode="noop")

    assert result == {"status": "skipped", "company_name": "Elder Care", "reason": "no_cim_found"}
    final_report_mock.assert_not_called()


def test_raising_progress_never_changes_the_outcome(monkeypatch, _common_patches):
    """A Progress whose every method raises must not change any result —
    progress is never load-bearing (plan §6, README rule 7)."""
    tmp_path = _common_patches["tmp_path"]

    class _RaisingProgress:
        def __init__(self, *args, **kwargs):
            pass

        def start(self, *args, **kwargs):
            raise RuntimeError("progress boom")

        def complete(self, *args, **kwargs):
            raise RuntimeError("progress boom")

        def fail(self, *args, **kwargs):
            raise RuntimeError("progress boom")

        def publish(self, *args, **kwargs):
            raise RuntimeError("progress boom")

    monkeypatch.setattr(vp, "Progress", _RaisingProgress)

    cim_files, ingestion_mock, pipeline_mock = _cim_branch_common_mocks(monkeypatch)
    _stub_rainmaker_summary(monkeypatch, tmp_path)
    _stub_token_counters(monkeypatch)
    _stub_final_report(monkeypatch, tmp_path)
    _stub_prior_mps_runs(monkeypatch, return_value=[{"run_mode": "cim_only"}])

    result = rvr.run_vdr_rainmaker("some.table", 1)

    assert result["status"] == "success"
    names = {Path(p).name for p in result["files"]}
    assert names == {
        "executive_summary.pdf", "rainmaker_opportunity_summary.html",
        "full_report.pdf", "full_report.html",
    }
    updates = _common_patches["updates"]
    assert updates[-1]["processing_status"] == "done"
    assert updates[-1]["completion_status"] == "success"
    _assert_processing_status_always_legal(updates)
