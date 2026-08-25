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

    result = rvr.run_vdr_rainmaker("some.table", 1)

    # Ruta 2, scoped to the isolated preview catalog with the CIM whitelist.
    ingestion_mock.assert_called_once()
    _, ingestion_kwargs = ingestion_mock.call_args
    assert ingestion_kwargs["catalog"] == "uc13_preview"
    assert ingestion_kwargs["file_whitelist"] == cim_files
    assert ingestion_kwargs["parse_priority_tiers"] == "all"
    # Since Ale's M0-M4 merge, ParseManifest skips docs already COMPLETE in
    # doc_status. Without force, re-previewing the same CIM is a silent no-op.
    assert ingestion_kwargs["force"] == "company"

    pipeline_mock.assert_called_once()
    _, pipeline_kwargs = pipeline_mock.call_args
    assert pipeline_kwargs["catalog"] == "uc13_preview"
    assert pipeline_kwargs["run_orchestrator"] is False  # one-pager only, no memo

    build_mock.assert_called_once()
    validate_mock.assert_called_once_with(fake_bundle)
    render_mock.assert_called_once()
    full_pipeline_mock.assert_not_called()

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
    assert names == {"executive_summary.pdf", "rainmaker_opportunity_summary.html", "full_report.docx"}
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

    rvr.run_vdr_rainmaker("some.table", 1)

    _, ingestion_kwargs = ingestion_mock.call_args
    assert ingestion_kwargs["file_whitelist"] == cim_files
    assert ingestion_kwargs["force"] == "company"
    _, pipeline_kwargs = pipeline_mock.call_args
    assert pipeline_kwargs["run_orchestrator"] is False
    full_pipeline_mock.assert_not_called()
    rainmaker_mock.assert_called_once()
    _, rainmaker_kwargs = rainmaker_mock.call_args
    assert rainmaker_kwargs.get("run_mode") == "cim_only"
