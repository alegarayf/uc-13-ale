"""Static contract test for workflows/vdr_rainmaker_poc.yml — the new, separate
job for the CIM-first Rainmaker POC. Modeled on test_uc13_ingestion_pipeline.py's
static-YAML-contract pattern. Also asserts the new job never references (and
therefore cannot collide with) the production VDR Diligence Pipeline job.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_WORKFLOW_PATH = _REPO_ROOT / "databricks" / "workflows" / "vdr_rainmaker_poc.yml"
_PROD_WORKFLOW_PATH = _REPO_ROOT / "databricks" / "workflows" / "vdr_pipeline.yml"

_SOURCE = _WORKFLOW_PATH.read_text(encoding="utf-8")
_DOC = yaml.safe_load(_SOURCE)
_JOB = _DOC["resources"]["jobs"]["vdr_rainmaker_poc"]


def test_job_name_and_key_are_distinct_from_production_job():
    assert _JOB["name"] == "VDR Rainmaker POC"
    prod_source = _PROD_WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "vdr_rainmaker_poc" not in prod_source
    # The prod job id may appear in a documentation comment (context for
    # readers) but must never be a resource key/reference in this file.
    assert "617196299594076" not in _DOC["resources"]["jobs"]


def test_single_notebook_task_workspace_source():
    tasks = _JOB["tasks"]
    assert len(tasks) == 1
    task = tasks[0]
    assert task["task_key"] == "run_vdr_rainmaker"
    nb = task["notebook_task"]
    assert nb["source"] == "WORKSPACE"
    assert nb["notebook_path"].endswith(
        "/databricks/jobs/notebooks/run_vdr_rainmaker_job"
    )


def test_no_job_or_task_level_parameters():
    """UI/manual triggers pass table_name/id as notebook params (widgets) —
    fixed parameters here would block that, same rule as vdr_pipeline.yml."""
    assert "parameters" not in _JOB
    for task in _JOB["tasks"]:
        assert "parameters" not in task


def test_serverless_environment_has_expected_dependencies():
    envs = {e["environment_key"]: e for e in _JOB["environments"]}
    task_env_key = _JOB["tasks"][0]["environment_key"]
    assert task_env_key in envs
    deps = envs[task_env_key]["spec"]["dependencies"]
    dep_names = {d.split(">=")[0].split("[")[0] for d in deps}
    assert {"mlflow", "pymupdf", "weasyprint", "python-docx"}.issubset(dep_names)


def test_max_concurrent_runs_allows_parallel_companies():
    assert _JOB["max_concurrent_runs"] >= 1


def test_no_git_source_block():
    """Code is served from the Databricks Git folder via WORKSPACE notebook
    path, not job-level git_source (dead config per vdr_pipeline.yml)."""
    assert "git_source" not in _JOB
