"""Hermetic pins for legal_register_verify_submit.py — M8 T2.

CLI shape is ast-only (mirrors promote_w2a / rerun_profiler AST-guard). Semantic
proof of a live verify job is T3. ``mint_run_id`` is executed in isolation.
"""
from __future__ import annotations

import ast
import importlib.util
from datetime import datetime, timezone
from pathlib import Path

from eval.content.s2_writer import _RUN_ID_RE

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SUBMIT = _REPO_ROOT / "eval" / "program" / "legal_register_verify_submit.py"
_DRIVER = _REPO_ROOT / "eval" / "program" / "_legal_register_verify_driver.py"
_ONBOARDING = _REPO_ROOT / "eval" / "program" / "onboarding_cluster_submit.py"


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _fn(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"function {name!r} not found")


def _assign_list_str(tree: ast.Module, name: str) -> list[str]:
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
            and isinstance(value, ast.List)
        ):
            out: list[str] = []
            for elt in value.elts:
                if not isinstance(elt, ast.Constant) or not isinstance(elt.value, str):
                    raise AssertionError(f"{name} element is not a string constant")
                out.append(elt.value)
            return out
    raise AssertionError(f"list constant {name!r} not found")


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


def _add_parser_names(fn: ast.FunctionDef) -> list[str]:
    names: list[str] = []
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_parser"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            names.append(str(node.args[0].value))
    return names


def _add_argument_flags(fn: ast.FunctionDef) -> list[str]:
    flags: list[str] = []
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_argument"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            flags.append(str(node.args[0].value))
    return flags


def _argument_call(fn: ast.FunctionDef, flag: str) -> ast.Call:
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_argument"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == flag
        ):
            return node
    raise AssertionError(f"add_argument({flag!r}) not found")


def _load_submit():
    spec = importlib.util.spec_from_file_location(
        "legal_register_verify_submit",
        _SUBMIT,
    )
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {_SUBMIT}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cli_subcommands_are_sync_and_verify() -> None:
    fn = _fn(_tree(_SUBMIT), "build_parser")
    assert _add_parser_names(fn) == ["sync", "verify"]


def test_verify_flags_are_company_catalog_no_sync() -> None:
    fn = _fn(_tree(_SUBMIT), "build_parser")
    flags = _add_argument_flags(fn)
    assert "--company" in flags
    assert "--catalog" in flags
    assert "--no-sync" in flags


def test_verify_company_is_required() -> None:
    call = _argument_call(_fn(_tree(_SUBMIT), "build_parser"), "--company")
    required = next(kw.value for kw in call.keywords if kw.arg == "required")
    assert isinstance(required, ast.Constant) and required.value is True


def test_verify_catalog_defaults_to_uc13_ale() -> None:
    tree = _tree(_SUBMIT)
    assert _assign_str(tree, "DEFAULT_CATALOG") == "uc13_ale"
    call = _argument_call(_fn(tree, "build_parser"), "--catalog")
    default = next(kw.value for kw in call.keywords if kw.arg == "default")
    assert isinstance(default, ast.Name) and default.id == "DEFAULT_CATALOG"


def test_verify_no_sync_is_store_true() -> None:
    call = _argument_call(_fn(_tree(_SUBMIT), "build_parser"), "--no-sync")
    action = next(kw.value for kw in call.keywords if kw.arg == "action")
    assert isinstance(action, ast.Constant) and action.value == "store_true"


def test_job_deps_match_onboarding_cluster_submit() -> None:
    ours = _assign_list_str(_tree(_SUBMIT), "ONBOARDING_DEPS")
    theirs = _assign_list_str(_tree(_ONBOARDING), "ONBOARDING_DEPS")
    assert ours == theirs == ["pyyaml", "pydantic>=2.0", "mlflow"]


def test_submit_wrapper_does_not_call_verify_legal_register() -> None:
    source = _SUBMIT.read_text(encoding="utf-8")
    assert "verify_legal_register(" not in source
    assert "from eval.content.legal_register_verifier" not in source


def test_driver_main_signature() -> None:
    fn = _fn(_tree(_DRIVER), "main")
    assert [arg.arg for arg in fn.args.args] == ["company", "run_id", "catalog"]
    assert fn.args.defaults == []
    assert fn.args.kwonlyargs == []


def test_driver_reuses_make_sdk_sql_executor() -> None:
    fn = _fn(_tree(_DRIVER), "main")
    calls = [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "make_sdk_sql_executor"
    ]
    assert len(calls) == 1
    source = _DRIVER.read_text(encoding="utf-8")
    assert "from eval.content.s2_writer import make_sdk_sql_executor" in source
    assert "WorkspaceClient" not in source
    assert "execute_statement" not in source
    assert "statement_execution" not in source


def test_driver_delegates_to_verify_legal_register() -> None:
    fn = _fn(_tree(_DRIVER), "main")
    calls = [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    names = [node.func.id for node in calls]
    assert "verify_legal_register" in names
    assert "make_sdk_sql_executor" in names
    verify = next(node for node in calls if node.func.id == "verify_legal_register")
    kwargs = {kw.arg: kw.value for kw in verify.keywords}
    sql = kwargs.get("sql_executor")
    assert isinstance(sql, ast.Call)
    assert isinstance(sql.func, ast.Name)
    assert sql.func.id == "make_sdk_sql_executor"


def test_mint_run_id_matches_s2_writer_run_id_re() -> None:
    mod = _load_submit()
    ts = datetime(2026, 8, 26, 16, 22, 0, tzinfo=timezone.utc)
    run_id = mod.mint_run_id(ts)
    assert _RUN_ID_RE.match(run_id)
    assert run_id.startswith("20260826T162200Z-")
