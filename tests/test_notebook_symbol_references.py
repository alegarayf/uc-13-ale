"""Static contract tests for test_pipeline.ipynb T8 notebook merge (Hector cells + rename).

Falsifier for T8 kill criteria (a) agents.orchestrator survives, (e) an added Hector
cell references a symbol the merged agents don't expose.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DATABRICKS_ROOT = _REPO_ROOT / "databricks"
_NOTEBOOK_PATH = _DATABRICKS_ROOT / "jobs" / "notebooks" / "test_pipeline.ipynb"

if str(_DATABRICKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_DATABRICKS_ROOT))


def _load_notebook() -> dict:
    return json.loads(_NOTEBOOK_PATH.read_text(encoding="utf-8"))


def _all_cell_source(nb: dict) -> str:
    return "\n".join("".join(c.get("source", [])) for c in nb.get("cells", []))


def test_no_agents_orchestrator_import_survives():
    src = _all_cell_source(_load_notebook())
    assert "agents.orchestrator" not in src, (
        "found a leftover agents.orchestrator reference — must be agents.exec_summary "
        "(T1 rename, deferred to T8 for notebook cells)"
    )


def test_added_cqa_cell_calls_symbol_the_merged_agent_exposes():
    src = _all_cell_source(_load_notebook())
    assert "generate_customer_quality_assessment" in src

    module = importlib.import_module("agents.workstreams.customer_quality_agent")
    importlib.reload(module)
    assert hasattr(module, "generate_customer_quality_assessment"), (
        "notebook Cell 14b calls generate_customer_quality_assessment but the merged "
        "customer_quality_agent module does not define it"
    )


def test_added_qoe_cell_calls_symbol_the_merged_agent_exposes():
    src = _all_cell_source(_load_notebook())
    assert "generate_qoe_assessment" in src

    module = importlib.import_module("agents.workstreams.quality_of_earnings_agent")
    importlib.reload(module)
    assert hasattr(module, "generate_qoe_assessment"), (
        "notebook Cell 17b calls generate_qoe_assessment but the merged "
        "quality_of_earnings_agent module does not define it"
    )


def test_added_dag_demo_cell_calls_symbol_the_merged_package_exposes():
    src = _all_cell_source(_load_notebook())
    assert "agents.orchestration import pipeline" in src

    module = importlib.import_module("agents.orchestration.pipeline")
    importlib.reload(module)
    assert hasattr(module, "run_pipeline"), (
        "notebook DAG-run demo cell calls pipeline.run_pipeline but "
        "agents.orchestration.pipeline does not define it"
    )
