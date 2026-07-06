"""Static contract tests for test_pipeline.ipynb Cell 1 LLM endpoint defaults (M-PHV1 T3)."""

from __future__ import annotations

import json
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_NOTEBOOK_PATH = _REPO_ROOT / "databricks" / "jobs" / "notebooks" / "test_pipeline.ipynb"

EXPECTED_LLM_ENDPOINT = "databricks-claude-sonnet-4-6"
_LLM_WIDGET_CALL_RE = re.compile(
    r'dbutils\.widgets\.text\(\s*"llm_endpoint"\s*,\s*"([^"]+)"\s*\)'
)
_DATABRICKS_NB_KEY = "application/vnd.databricks.v1+notebook"


def _load_notebook() -> dict:
    return json.loads(_NOTEBOOK_PATH.read_text(encoding="utf-8"))


def _cell1_config_source(nb: dict) -> str:
    for cell in nb.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        source = "".join(cell.get("source", []))
        if "Widgets so the Workflow UI" in source and "llm_endpoint" in source:
            return source
    raise AssertionError("Cell 1 config cell with llm_endpoint widget not found")


def _llm_endpoint_widget_meta(nb: dict) -> dict:
    widgets = nb.get("metadata", {}).get(_DATABRICKS_NB_KEY, {}).get("widgets", {})
    meta = widgets.get("llm_endpoint")
    if meta is None:
        raise AssertionError("llm_endpoint widget metadata block not found")
    return meta


def test_cell1_llm_endpoint_widget_default_is_sonnet_4_6():
    source = _cell1_config_source(_load_notebook())
    match = _LLM_WIDGET_CALL_RE.search(source)
    assert match is not None, "llm_endpoint dbutils.widgets.text call not found in Cell 1"
    assert match.group(1) == EXPECTED_LLM_ENDPOINT


def test_llm_endpoint_widget_metadata_defaults_are_sonnet_4_6():
    meta = _llm_endpoint_widget_meta(_load_notebook())
    assert meta["currentValue"] == EXPECTED_LLM_ENDPOINT
    assert meta["typedWidgetInfo"]["defaultValue"] == EXPECTED_LLM_ENDPOINT
    assert meta["widgetInfo"]["defaultValue"] == EXPECTED_LLM_ENDPOINT


def test_llm_endpoint_metadata_default_fields_stay_in_sync():
    """Falsifier: Databricks can revert widget defaults if metadata fields disagree."""
    meta = _llm_endpoint_widget_meta(_load_notebook())
    typed_default = meta["typedWidgetInfo"]["defaultValue"]
    widget_default = meta["widgetInfo"]["defaultValue"]
    current = meta["currentValue"]
    assert typed_default == widget_default == current == EXPECTED_LLM_ENDPOINT
