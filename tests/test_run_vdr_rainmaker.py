"""Unit tests for jobs/scripts/run_vdr_rainmaker.py — the CIM-first Rainmaker
POC runner. Mocks every heavy dependency (Spark, ingestion, the 7-agent DAG,
BundleBuilder, render_rainmaker) so this runs offline, no cluster needed.

Covers the ONE decision the runner makes (plan §4/§7/§8, user instruction):
if a CIM is found → run the scoped Ruta 2 flow and render the PDF; if not →
no-op with a message. No `preview_ready` gate, no fallback to the full
pipeline — those are explicitly out of scope for this POC.
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


def test_no_cim_found_is_a_pure_noop(monkeypatch, _common_patches):
    monkeypatch.setattr(rvr, "_detect_cim_files", lambda _company, _folder: [])

    ingestion_mock = MagicMock(side_effect=AssertionError("must not run ingestion without a CIM"))
    monkeypatch.setattr(
        "run_ingestion_pipeline.run_ingestion_pipeline", ingestion_mock, raising=False
    )
    pipeline_mock = MagicMock(side_effect=AssertionError("must not run the agent DAG without a CIM"))
    monkeypatch.setattr("agents.orchestration.pipeline.run_pipeline", pipeline_mock)
    render_mock = MagicMock(side_effect=AssertionError("must not render without a CIM"))
    monkeypatch.setattr("agents.exec_summary.renderers.render_rainmaker", render_mock)

    result = rvr.run_vdr_rainmaker("some.table", 1)

    assert result == {"status": "skipped", "company_name": "Elder Care", "reason": "no_cim_found"}
    updates = _common_patches["updates"]
    assert updates[0]["processing_status"] == "processing"
    assert updates[-1]["processing_status"] == "done"
    assert updates[-1]["completion_status"] == "success"
    assert "No CIM found" in updates[-1]["error_message"]
    ingestion_mock.assert_not_called()
    pipeline_mock.assert_not_called()
    render_mock.assert_not_called()


def test_cim_found_runs_scoped_route_2_and_renders_pdf(monkeypatch, _common_patches):
    tmp_path = _common_patches["tmp_path"]
    cim_files = ["2024 Elder Care - CIM_vF.pdf"]
    monkeypatch.setattr(rvr, "_detect_cim_files", lambda _company, _folder: cim_files)

    ingestion_mock = MagicMock(return_value={"summary": {"SUCCESS": 4}})
    monkeypatch.setattr(
        "run_ingestion_pipeline.run_ingestion_pipeline", ingestion_mock, raising=False
    )

    pipeline_mock = MagicMock(return_value={"summary": {"SUCCESS": 7}})
    monkeypatch.setattr("agents.orchestration.pipeline.run_pipeline", pipeline_mock)

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

    pipeline_mock.assert_called_once()
    _, pipeline_kwargs = pipeline_mock.call_args
    assert pipeline_kwargs["catalog"] == "uc13_preview"
    assert pipeline_kwargs["run_orchestrator"] is False  # one-pager only, no memo (plan §5.5)

    build_mock.assert_called_once()
    validate_mock.assert_called_once_with(fake_bundle)
    render_mock.assert_called_once()

    assert result["status"] == "success"
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


def test_no_regression_run_vdr_pipeline_module_untouched():
    """The existing VDR job's module must not be modified by this POC (plan §10)."""
    import run_vdr_pipeline as rvp_module

    assert hasattr(rvp_module, "run_vdr_pipeline")
    assert hasattr(rvp_module, "main")
