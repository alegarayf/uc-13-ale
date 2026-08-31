"""Hermetic pins for eval/program/rerun_profiler_gkf.py — M6 T1."""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO_ROOT / "eval" / "program" / "rerun_profiler_gkf.py"


def _tree() -> ast.Module:
    return ast.parse(_SCRIPT.read_text(encoding="utf-8"))


def _assign_str(tree: ast.Module, name: str) -> str:
    for node in tree.body:
        target: ast.expr | None = None
        value: ast.expr | None = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target, value = node.target, node.value
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        if (
            isinstance(target, ast.Name)
            and target.id == name
            and isinstance(value, ast.Constant)
            and isinstance(value.value, str)
        ):
            return value.value
    raise AssertionError(f"string constant {name!r} not found")


def test_company_name_is_uppercase_gkf_never_slug() -> None:
    """Coupling Surface 11: lowercase 'gkf' silently matches zero warehouse rows."""
    assert _assign_str(_tree(), "COMPANY_NAME") == "GKF"
    source = _SCRIPT.read_text(encoding="utf-8")
    assert 'COMPANY_NAME = "gkf"' not in source
    assert "sp_company_name\"] = \"gkf\"" not in source
    assert 'os.environ["sp_company_name"] = "__COMPANY_NAME__"' in source


def test_catalog_is_explicit_uc13_ale_not_production_default() -> None:
    tree = _tree()
    assert _assign_str(tree, "CATALOG") == "uc13_ale"
    assert _assign_str(tree, "SCHEMA") == "classification"
    source = _SCRIPT.read_text(encoding="utf-8")
    assert 'os.environ["catalog"] = "__CATALOG__"' in source
    assert 'os.environ["schema"] = "__SCHEMA__"' in source


def test_driver_invokes_profiler_main_without_pipeline() -> None:
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "mod.main()" in source
    assert "PipelineOrchestrator" not in source
    assert "run_pipeline(" not in source
    assert "sys.modules[\"company_profiler\"] = mod" in source
    assert "spec.loader.exec_module(mod)" in source
