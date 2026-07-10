"""Static contract tests for §5.12.3 catalog convention (M-PHV3 T5 / PG3 gate)."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]

PRODUCTION_SCRIPTS = [
    "databricks/jobs/scripts/ingestion_parser.py",
    "databricks/jobs/scripts/ensure_coverage.py",
    "databricks/jobs/scripts/document_classifier.py",
    "databricks/jobs/scripts/download_upload.py",
    "databricks/jobs/scripts/company_profiler.py",
    "databricks/jobs/scripts/setup_vector_search.py",
    "databricks/jobs/scripts/vs_filter_pushdown_probe.py",
]

PRODUCTION_AGENTS = [
    "databricks/agents/workstreams/business_model_agent.py",
    "databricks/agents/workstreams/financial_trends_agent.py",
    "databricks/agents/workstreams/kpi_agent.py",
    "databricks/agents/workstreams/customer_quality_agent.py",
    "databricks/agents/workstreams/quality_of_earnings_agent.py",
    "databricks/agents/workstreams/legal_contracts_agent.py",
]

EXPECTED_PRODUCTION_CATALOG = "uc13"
EXPECTED_NOTEBOOK_CATALOG = "uc13_ale"

_NOTEBOOK_PATH = _REPO_ROOT / "databricks" / "jobs" / "notebooks" / "test_pipeline.ipynb"
_WORKFLOW_PATH = _REPO_ROOT / "databricks" / "workflows" / "uc13_ingestion_pipeline.yml"
_DATABRICKS_NB_KEY = "application/vnd.databricks.v1+notebook"

_CATALOG_WIDGET_CALL_RE = re.compile(
    r'dbutils\.widgets\.text\(\s*"catalog"\s*,\s*"([^"]+)"\s*\)'
)
_DIRECT_CATALOG_ASSIGN_RE = re.compile(
    r'^\s*(?:catalog|CATALOG)\s*=\s*["\'](uc13(?:_ale)?)["\']\s*$',
    re.MULTILINE,
)

_EVAL_HARNESS_MARKERS = (
    "EvalHarness",
    "GoldLabelBootstrap",
    "DeltaEvalStore(",
    "retrieval_harness",
)


def _read_source(rel_path: str) -> str:
    return (_REPO_ROOT / rel_path).read_text(encoding="utf-8")


def _parse_module(rel_path: str) -> ast.Module:
    return ast.parse(_read_source(rel_path))


def _main_function(tree: ast.Module) -> ast.FunctionDef | None:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            return node
    return None


def _is_docstring_expr(node: ast.AST, parent_body: list[ast.stmt]) -> bool:
    return (
        parent_body
        and parent_body[0] is node
        and isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _catalog_default_from_get_param(call: ast.Call) -> str | None:
    if not (isinstance(call.func, ast.Name) and call.func.id == "get_param"):
        return None
    if not call.args:
        return None
    first = call.args[0]
    if not (isinstance(first, ast.Constant) and first.value == "catalog"):
        return None
    for keyword in call.keywords:
        if keyword.arg == "default" and isinstance(keyword.value, ast.Constant):
            value = keyword.value.value
            if isinstance(value, str):
                return value
    if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant):
        value = call.args[1].value
        if isinstance(value, str):
            return value
    return None


def _iter_get_param_catalog_calls(nodes: ast.AST) -> list[tuple[int, str | None]]:
    found: list[tuple[int, str | None]] = []
    for node in ast.walk(nodes):
        if isinstance(node, ast.Call):
            default = _catalog_default_from_get_param(node)
            if default is not None or (
                node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "catalog"
                and isinstance(node.func, ast.Name)
                and node.func.id == "get_param"
            ):
                found.append((node.lineno, default))
    return found


def _inside_get_param_catalog_default(node: ast.Constant, ancestors: list[ast.AST]) -> bool:
    for parent in ancestors:
        if not isinstance(parent, ast.Call):
            continue
        if _catalog_default_from_get_param(parent) is None:
            continue
        for child in ast.walk(parent):
            if child is node:
                return True
    return False


def _inside_secrets_scope_name(node: ast.Constant, ancestors: list[ast.AST]) -> bool:
    for parent in ancestors:
        if not isinstance(parent, ast.Call):
            continue
        func = parent.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "get"
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "secrets"
            and parent.args
            and parent.args[0] is node
        ):
            return True
    return False


def _catalog_literal_violations_in_body(body: list[ast.stmt]) -> list[int]:
    violations: list[int] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self._ancestors: list[ast.AST] = []

        def generic_visit(self, node: ast.AST) -> None:
            if isinstance(node, ast.Constant) and node.value in {"uc13", "uc13_ale"}:
                if _inside_get_param_catalog_default(node, self._ancestors):
                    return
                if _inside_secrets_scope_name(node, self._ancestors):
                    return
                parent = self._ancestors[-1] if self._ancestors else None
                if isinstance(parent, ast.Assign):
                    for target in parent.targets:
                        if isinstance(target, ast.Name) and target.id in {"catalog", "CATALOG"}:
                            violations.append(node.lineno)
                            return
                if isinstance(parent, ast.keyword) and parent.arg == "catalog":
                    violations.append(node.lineno)
                    return
            self._ancestors.append(node)
            super().generic_visit(node)
            self._ancestors.pop()

    for stmt in body:
        if _is_docstring_expr(stmt, body):
            continue
        Visitor().visit(stmt)
    return violations


def _module_level_catalog_shadow_constants(tree: ast.Module) -> list[int]:
    lines: list[int] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "_CATALOG":
                lines.append(node.lineno)
                continue
        value = node.value
        if not isinstance(value, ast.Call):
            continue
        func = value.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr == "get"
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "environ"
        ):
            continue
        if not value.args:
            continue
        first = value.args[0]
        if isinstance(first, ast.Constant) and first.value == "catalog":
            lines.append(node.lineno)
    return lines


def _load_notebook() -> dict:
    return json.loads(_NOTEBOOK_PATH.read_text(encoding="utf-8"))


def _cell1_config_source(nb: dict) -> str:
    for cell in nb.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        source = "".join(cell.get("source", []))
        if "Widgets so the Workflow UI" in source and 'dbutils.widgets.text("catalog"' in source:
            return source
    raise AssertionError("Cell 1 config cell with catalog widget not found")


def _catalog_widget_meta(nb: dict) -> dict:
    widgets = nb.get("metadata", {}).get(_DATABRICKS_NB_KEY, {}).get("widgets", {})
    meta = widgets.get("catalog")
    if meta is None:
        raise AssertionError("catalog widget metadata block not found")
    return meta


def _is_cell1_config_cell(source: str) -> bool:
    return "Widgets so the Workflow UI" in source and 'dbutils.widgets.text("catalog"' in source


def _is_eval_harness_carveout_cell(source: str) -> bool:
    return any(marker in source for marker in _EVAL_HARNESS_MARKERS)


@pytest.mark.parametrize("rel_path", PRODUCTION_SCRIPTS)
def test_rule1_script_get_param_catalog_defaults_are_uc13(rel_path: str) -> None:
    tree = _parse_module(rel_path)
    calls = _iter_get_param_catalog_calls(tree)
    assert calls, f"{rel_path}: expected at least one get_param('catalog', ...) call"
    bad = [
        f"line {lineno}: default={default!r}"
        for lineno, default in calls
        if default != EXPECTED_PRODUCTION_CATALOG
    ]
    assert not bad, f"{rel_path}: non-uc13 catalog defaults: {', '.join(bad)}"


@pytest.mark.parametrize("rel_path", PRODUCTION_AGENTS)
def test_rule1_agent_main_get_param_catalog_default_is_uc13(rel_path: str) -> None:
    tree = _parse_module(rel_path)
    main_fn = _main_function(tree)
    assert main_fn is not None, f"{rel_path}: main() not found"
    calls = _iter_get_param_catalog_calls(main_fn)
    assert calls, f"{rel_path}: main() must call get_param('catalog', ...)"
    bad = [
        f"line {lineno}: default={default!r}"
        for lineno, default in calls
        if default != EXPECTED_PRODUCTION_CATALOG
    ]
    assert not bad, f"{rel_path} main(): non-uc13 catalog defaults: {', '.join(bad)}"


def test_rule2_cell1_catalog_widget_default_is_uc13_ale() -> None:
    source = _cell1_config_source(_load_notebook())
    match = _CATALOG_WIDGET_CALL_RE.search(source)
    assert match is not None, "catalog dbutils.widgets.text call not found in Cell 1"
    assert match.group(1) == EXPECTED_NOTEBOOK_CATALOG


def test_rule2_catalog_widget_metadata_defaults_are_uc13_ale() -> None:
    meta = _catalog_widget_meta(_load_notebook())
    assert meta["currentValue"] == EXPECTED_NOTEBOOK_CATALOG
    assert meta["typedWidgetInfo"]["defaultValue"] == EXPECTED_NOTEBOOK_CATALOG
    assert meta["widgetInfo"]["defaultValue"] == EXPECTED_NOTEBOOK_CATALOG


def test_rule2_yaml_catalog_default_is_uc13_ale_hygiene_only() -> None:
    """Hygiene-only, non-gating — duplicate of test_uc13_ingestion_pipeline coverage."""
    workflow_source = _WORKFLOW_PATH.read_text(encoding="utf-8")
    match = re.search(r'- name: catalog\s+default: "([^"]+)"', workflow_source)
    assert match is not None
    assert match.group(1) == EXPECTED_NOTEBOOK_CATALOG


@pytest.mark.parametrize("rel_path", PRODUCTION_SCRIPTS + PRODUCTION_AGENTS)
def test_rule3_no_module_level_catalog_shadow_constants(rel_path: str) -> None:
    tree = _parse_module(rel_path)
    shadows = _module_level_catalog_shadow_constants(tree)
    assert not shadows, (
        f"{rel_path}: module-level catalog shadow constant(s) at line(s) {shadows}"
    )


@pytest.mark.parametrize("rel_path", PRODUCTION_SCRIPTS + PRODUCTION_AGENTS)
def test_rule3_main_has_no_bare_catalog_literal_bypass(rel_path: str) -> None:
    tree = _parse_module(rel_path)
    main_fn = _main_function(tree)
    assert main_fn is not None, f"{rel_path}: main() not found"
    violations = _catalog_literal_violations_in_body(main_fn.body)
    assert not violations, (
        f"{rel_path} main(): bare catalog literal bypass at line(s) {violations}"
    )


def test_rule3_notebook_cells_no_direct_catalog_literal_bypass() -> None:
    nb = _load_notebook()
    violations: list[str] = []
    for idx, cell in enumerate(nb.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        source = "".join(cell.get("source", []))
        if _is_cell1_config_cell(source) or _is_eval_harness_carveout_cell(source):
            continue
        for match in _DIRECT_CATALOG_ASSIGN_RE.finditer(source):
            violations.append(
                f"cell_index={idx} catalog_literal={match.group(1)!r} at line {source[:match.start()].count(chr(10)) + 1}"
            )
    assert not violations, "notebook direct catalog literal assignment(s): " + "; ".join(violations)


def test_rule3_regression_module_level_catalog_shadow_falsifier() -> None:
    """Falsifier: rule 1 alone would not catch a reintroduced _CATALOG shadow constant."""
    tree = _parse_module("databricks/agents/workstreams/business_model_agent.py")
    module_names = [
        node.targets[0].id
        for node in tree.body
        if isinstance(node, ast.Assign)
        and node.targets
        and isinstance(node.targets[0], ast.Name)
    ]
    assert "_CATALOG" not in module_names
