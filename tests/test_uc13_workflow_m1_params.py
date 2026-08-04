"""Static contract tests for M1 T7 workflow YAML force/coverage_per_workstream wiring."""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FULL_PIPELINE = _REPO_ROOT / "databricks" / "workflows" / "uc13_full_pipeline.yml"
_INGESTION_PIPELINE = _REPO_ROOT / "databricks" / "workflows" / "uc13_ingestion_pipeline.yml"

_FULL_SOURCE = _FULL_PIPELINE.read_text(encoding="utf-8")
_INGESTION_SOURCE = _INGESTION_PIPELINE.read_text(encoding="utf-8")


def _task_block(source: str, task_key: str) -> str:
    start = source.index(f"- task_key: {task_key}")
    next_task = source.find("\n        - task_key:", start + 1)
    if next_task == -1:
        next_task = source.find("\n        # ------------------------------------------------------------------", start + 1)
    return source[start:next_task]


def test_full_pipeline_ingestion_task_param_order_matches_run_ingestion_pipeline_argv():
    """Falsifier: positional YAML list must match run_ingestion_pipeline.py argv slots 0-7."""
    block = _task_block(_FULL_SOURCE, "ingestion_pipeline")
    params = re.findall(r"\{\{job\.parameters\.(\w+)\}\}", block)
    assert params[:8] == [
        "sp_company_name",
        "catalog",
        "schema",
        "embedding_endpoint",
        "vision_endpoint",
        "parse_priority_tiers",
        "force",
        "coverage_per_workstream",
    ]


def test_ingestion_pipeline_ingestion_parser_task_appends_force_and_coverage():
    """Falsifier: direct ingestion_parser task must wire T5's frozen param names."""
    block = _task_block(_INGESTION_SOURCE, "ingestion_parser")
    params = re.findall(r"\{\{job\.parameters\.(\w+)\}\}", block)
    assert params[-2:] == ["force", "coverage_per_workstream"]


def test_job_parameters_define_force_and_coverage_defaults():
    """Falsifier: job-level params must exist with T5 frozen defaults for bundle refs."""
    for source in (_FULL_SOURCE, _INGESTION_SOURCE):
        force = re.search(
            r"- name: force\s+default: \"([^\"]+)\"",
            source,
        )
        coverage = re.search(
            r"- name: coverage_per_workstream\s+default: \"([^\"]+)\"",
            source,
        )
        assert force is not None and force.group(1) == "none"
        assert coverage is not None and coverage.group(1) == "3"


def test_full_pipeline_uses_spark_python_task_not_python_script_for_ingestion():
    """Adversarial: Surface 2 applies only to python_script_task — full pipeline path differs."""
    block = _task_block(_FULL_SOURCE, "ingestion_pipeline")
    assert "spark_python_task:" in block
    assert "python_script_task:" not in block
    assert 'python_file: "databricks/jobs/scripts/run_ingestion_pipeline.py"' in block
