"""Static contract tests for legal_contracts_agent workflow + notebook wiring (T4)."""

from __future__ import annotations

import json
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_WORKFLOW_PATH = _REPO_ROOT / "databricks" / "workflows" / "uc13_ingestion_pipeline.yml"
_NOTEBOOK_PATH = _REPO_ROOT / "databricks" / "jobs" / "notebooks" / "test_pipeline.ipynb"

_WORKFLOW_SOURCE = _WORKFLOW_PATH.read_text(encoding="utf-8")
_NOTEBOOK_SOURCE = json.loads(_NOTEBOOK_PATH.read_text(encoding="utf-8"))


def _legal_task_block() -> str:
    """Return YAML text from legal_contracts_agent task_key through next task comment."""
    start = _WORKFLOW_SOURCE.index("- task_key: legal_contracts_agent")
    end = _WORKFLOW_SOURCE.index("# ------------------------------------------------------------------\n        # Task 10", start)
    return _WORKFLOW_SOURCE[start:end]


def _notebook_joined_source() -> str:
    return "\n".join(
        "".join(cell.get("source", []))
        for cell in _NOTEBOOK_SOURCE["cells"]
    )


def test_legal_task_depends_on_company_profiler_not_cqa():
    block = _legal_task_block()
    assert "task_key: company_profiler" in block
    assert "customer_quality_agent" not in block


def test_legal_task_passes_extraction_endpoint_not_llm_endpoint():
    block = _legal_task_block()
    assert "{{job.parameters.extraction_endpoint}}" in block
    assert "{{job.parameters.llm_endpoint}}" not in block


def test_legal_task_python_file_and_key_unchanged():
    block = _legal_task_block()
    assert "task_key: legal_contracts_agent" in block
    assert 'python_file: "databricks/agents/workstreams/legal_contracts_agent.py"' in block


def test_legal_task_description_standalone_writes_analysis_legal():
    block = _legal_task_block()
    assert "analysis.legal" in block
    assert "contract_trigger_list" not in block


def test_job_parameters_include_extraction_endpoint():
    assert "- name: extraction_endpoint" in _WORKFLOW_SOURCE


def test_notebook_cell18_includes_legal_and_legal_contracts_tables():
    src = _notebook_joined_source()
    assert '"legal":' in src and ".analysis.legal" in src
    assert '"legal_contracts":' in src and ".analysis.legal_contracts" in src


def test_notebook_removes_cqa_before_legal_ordering():
    src = _notebook_joined_source()
    assert "run Cell 14 before Cell 16" not in src
    assert "contract_trigger_list from uc13.analysis.customer_quality (run Cell 14 first)" not in src


def test_notebook_cell16_keeps_lca_main_import():
    """Adversarial: workflow wiring must not drop the Cell 16 lca.main() entrypoint."""
    src = _notebook_joined_source()
    assert "import legal_contracts_agent as lca" in src
    assert "lca.main()" in src


def test_legal_task_parameter_order_matches_main():
    """Falsifier: positional workflow params must be sp_company_name, catalog, extraction_endpoint."""
    block = _legal_task_block()
    params = re.findall(r'\{\{job\.parameters\.(\w+)\}\}', block)
    task_params = params[:3]
    assert task_params == ["sp_company_name", "catalog", "extraction_endpoint"]
