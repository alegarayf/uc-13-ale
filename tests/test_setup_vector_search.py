"""Static contract tests for setup_vector_search.py VS schema alignment (B-W1)."""

from __future__ import annotations

import ast
import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SETUP_PATH = _REPO_ROOT / "databricks" / "jobs" / "scripts" / "setup_vector_search.py"
_NOTEBOOK_PATH = (
    _REPO_ROOT / "databricks" / "jobs" / "notebooks" / "00_setup_vector_search.ipynb"
)
_INGESTION_PARSER_PATH = (
    _REPO_ROOT / "databricks" / "jobs" / "scripts" / "ingestion_parser.py"
)

EXPECTED_COLUMNS_TO_SYNC = [
    "chunk_id",
    "doc_id",
    "file_name",
    "workstream",
    "priority_tier",
    "company_name",
    "source_type",
]

EXPECTED_EMBEDDINGS_DDL_COLUMNS = {
    "chunk_id",
    "doc_id",
    "file_name",
    "company_name",
    "workstream",
    "priority_tier",
    "source_type",
    "embedding",
    "created_at",
}


def _extract_columns_to_sync(source: str) -> list[str]:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg == "columns_to_sync" and isinstance(kw.value, ast.List):
                return [
                    elt.value
                    for elt in kw.value.elts
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                ]
    raise AssertionError("columns_to_sync not found in source")


def _extract_create_table_columns(ddl_block: str) -> set[str]:
    cols: set[str] = set()
    for line in ddl_block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("CREATE", ")", "USING", "TBLPROPERTIES", "--")):
            continue
        col = stripped.split()[0].rstrip(",")
        if col.isidentifier():
            cols.add(col)
    return cols


def test_setup_vector_search_columns_to_sync_matches_contract():
    source = _SETUP_PATH.read_text(encoding="utf-8")
    assert _extract_columns_to_sync(source) == EXPECTED_COLUMNS_TO_SYNC


def test_setup_embeddings_table_ddl_includes_company_name_and_source_type():
    source = _SETUP_PATH.read_text(encoding="utf-8")
    start = source.index("CREATE TABLE IF NOT EXISTS uc13.ingestion.embeddings")
    end = source.index(") USING DELTA", start)
    ddl_cols = _extract_create_table_columns(source[start:end])
    assert EXPECTED_EMBEDDINGS_DDL_COLUMNS.issubset(ddl_cols)


def test_ingestion_parser_embeddings_ddl_has_company_name_and_source_type():
    """Inspect-only confirmation per T3 packet — production DDL is authoritative."""
    source = _INGESTION_PARSER_PATH.read_text(encoding="utf-8")
    assert "company_name  STRING" in source
    assert "source_type   STRING" in source
    assert "CREATE TABLE IF NOT EXISTS {table_embeddings}" in source


def test_columns_to_sync_includes_filter_pushdown_fields():
    """Falsifier: missing company_name would break T4 filter pushdown silently."""
    assert "company_name" in EXPECTED_COLUMNS_TO_SYNC
    assert "source_type" in EXPECTED_COLUMNS_TO_SYNC


def test_notebook_columns_to_sync_matches_setup_script():
    """Falsifier: notebook drift would recreate index missing B-W1 columns."""
    nb = json.loads(_NOTEBOOK_PATH.read_text(encoding="utf-8"))
    notebook_cols: list[str] | None = None
    for cell in nb.get("cells", []):
        source = "".join(cell.get("source", []))
        if "columns_to_sync" not in source:
            continue
        notebook_cols = _extract_columns_to_sync(source)
        break
    assert notebook_cols is not None, "columns_to_sync not found in notebook"
    assert notebook_cols == EXPECTED_COLUMNS_TO_SYNC
