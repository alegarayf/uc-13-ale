"""CI guard: §5.17 item 2 callers must not treat semantic_search as a bare list.

Scans enumerated production modules for assignments that consume ``semantic_search()``
or ``self._semantic_search_with_fallback()`` without ``.chunks`` unpacking.
Wrapper internals that assign ``result = semantic_search(...)`` and return
``RouteResult`` are permitted.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

# Context-map §Orchestrator handoff — direct caller census for §5.17 item 2.
ENUMERATED_CALLER_MODULES = [
    "databricks/agents/workstreams/kpi_agent.py",
    "databricks/agents/workstreams/customer_quality_agent.py",
    "databricks/agents/workstreams/quality_of_earnings_agent.py",
    "databricks/agents/workstreams/business_model_agent.py",
    "databricks/agents/workstreams/legal_contracts_agent.py",
    "databricks/jobs/scripts/company_profiler.py",
]

WRAPPER_FUNCTION_NAMES = frozenset(
    {"_semantic_search_with_fallback", "semantic_search_with_fallback"}
)


def _is_semantic_search_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name) and func.id == "semantic_search":
        return True
    return isinstance(func, ast.Attribute) and func.attr == "semantic_search"


def _is_wrapper_fallback_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return isinstance(func, ast.Attribute) and func.attr == "_semantic_search_with_fallback"


def _call_uses_chunks_attribute(node: ast.Call) -> bool:
    parent = getattr(node, "_parent", None)
    while parent is not None:
        if isinstance(parent, ast.Attribute) and parent.attr == "chunks":
            return True
        parent = getattr(parent, "_parent", None)
    return False


def _attach_parents(tree: ast.AST) -> None:
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            setattr(child, "_parent", parent)


def _find_bare_route_result_assignments(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    _attach_parents(tree)
    violations: list[str] = []

    class _Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.wrapper_depth = 0

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            prev = self.wrapper_depth
            if node.name in WRAPPER_FUNCTION_NAMES:
                self.wrapper_depth += 1
            self.generic_visit(node)
            self.wrapper_depth = prev

        visit_AsyncFunctionDef = visit_FunctionDef

        def _check_assign_value(self, node: ast.AST, lineno: int) -> None:
            if not isinstance(node, ast.Call):
                return
            if self.wrapper_depth > 0 and _is_semantic_search_call(node):
                return
            if _call_uses_chunks_attribute(node):
                return
            if _is_semantic_search_call(node):
                violations.append(
                    f"{path.relative_to(REPO_ROOT)}:{lineno}: "
                    "semantic_search() assigned without .chunks"
                )
            elif _is_wrapper_fallback_call(node):
                violations.append(
                    f"{path.relative_to(REPO_ROOT)}:{lineno}: "
                    "_semantic_search_with_fallback() assigned without .chunks"
                )

        def visit_Assign(self, node: ast.Assign) -> None:
            self._check_assign_value(node.value, node.lineno)
            self.generic_visit(node)

        def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
            if node.value is not None:
                self._check_assign_value(node.value, node.lineno)
            self.generic_visit(node)

    _Visitor().visit(tree)
    return violations


@pytest.mark.parametrize("rel_path", ENUMERATED_CALLER_MODULES)
def test_enumerated_callers_unpack_route_result_chunks(rel_path: str) -> None:
    path = REPO_ROOT / rel_path
    assert path.is_file(), f"enumerated module missing: {rel_path}"
    violations = _find_bare_route_result_assignments(path)
    assert not violations, "RouteResult migration guard failed:\n" + "\n".join(violations)


def test_guard_detects_synthetic_bare_semantic_search_assignment() -> None:
    """Falsifier: visitor flags bare list assignment pattern."""
    snippet = """
def _tool_bad(spark):
    chunks = semantic_search(query="x", spark=spark, top_k=1)
"""
    tree = ast.parse(snippet)
    _attach_parents(tree)
    violations: list[str] = []

    class _Visitor(ast.NodeVisitor):
        def visit_Assign(self, node: ast.Assign) -> None:
            if isinstance(node.value, ast.Call) and _is_semantic_search_call(node.value):
                if not _call_uses_chunks_attribute(node.value):
                    violations.append("bare assignment")

    _Visitor().visit(tree)
    assert violations, "expected synthetic bare assignment to be detected"


def test_agents_tree_has_no_bare_semantic_search_outside_wrappers() -> None:
    """Scan databricks/agents/ for stray direct semantic_search list assignments."""
    agents_root = REPO_ROOT / "databricks" / "agents"
    all_violations: list[str] = []
    for path in sorted(agents_root.rglob("*.py")):
        if path.name == "retrieval.py":
            continue
        all_violations.extend(_find_bare_route_result_assignments(path))
    assert not all_violations, "agents/ tree migration guard failed:\n" + "\n".join(
        all_violations
    )
