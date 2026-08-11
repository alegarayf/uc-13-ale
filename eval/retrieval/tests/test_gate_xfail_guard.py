"""Item 17 — regression guard: eval suite stays xfail-free; PASS gates forbid xfail."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
EVAL_TEST_ROOT = REPO_ROOT / "eval" / "retrieval" / "tests"
TEST_ROOTS = (REPO_ROOT / "tests", EVAL_TEST_ROOT)
GATE_GLOB = ".dev/plans/**/CLUSTER_GATES.md"


class _NotXfail:
    pass


_NOT_XFAIL = _NotXfail()


def _iter_py_files(roots: tuple[Path, ...]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        files.extend(sorted(root.rglob("*.py")))
    return files


def _is_pytest_mark_xfail(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "xfail"
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "mark"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "pytest"
    )


def _xfail_strictness(decorator: ast.expr) -> bool | None | _NotXfail:
    """Return strict kw when decorator is xfail; otherwise return _NOT_XFAIL."""
    if isinstance(decorator, ast.Call) and _is_pytest_mark_xfail(decorator.func):
        for keyword in decorator.keywords:
            if keyword.arg == "strict" and isinstance(keyword.value, ast.Constant):
                if isinstance(keyword.value.value, bool):
                    return keyword.value.value
        return None
    if _is_pytest_mark_xfail(decorator):
        return None
    return _NOT_XFAIL


def _collect_xfail_markers(source: str) -> list[tuple[int, bool | None]]:
    tree = ast.parse(source)
    markers: list[tuple[int, bool | None]] = []

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "pytestmark":
                    candidates = (
                        [node.value]
                        if not isinstance(node.value, ast.List)
                        else list(node.value.elts)
                    )
                    for candidate in candidates:
                        strictness = _xfail_strictness(candidate)
                        if strictness is not _NOT_XFAIL:
                            markers.append((node.lineno, strictness))

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for decorator in node.decorator_list:
            strictness = _xfail_strictness(decorator)
            if strictness is not _NOT_XFAIL:
                markers.append((node.lineno, strictness))

    return markers


def _find_xfail_markers(roots: tuple[Path, ...]) -> list[str]:
    violations: list[str] = []
    for path in _iter_py_files(roots):
        if path.is_relative_to(REPO_ROOT):
            rel = path.relative_to(REPO_ROOT)
        else:
            rel = Path(path.name)
        for lineno, strict in _collect_xfail_markers(path.read_text(encoding="utf-8")):
            if strict is True:
                label = "strict"
            elif strict is False:
                label = "non-strict"
            else:
                label = "default-non-strict"
            violations.append(f"{rel}:{lineno} ({label})")
    return violations


def _gate_files_claim_pass() -> list[Path]:
    passing: list[Path] = []
    for path in REPO_ROOT.glob(GATE_GLOB):
        text = path.read_text(encoding="utf-8")
        if any(
            line.strip().startswith("**Status:** PASS") or " PASS" in line
            for line in text.splitlines()
        ):
            passing.append(path)
    return passing


def test_eval_suite_has_no_xfail_markers():
    violations = _find_xfail_markers((EVAL_TEST_ROOT,))
    assert not violations, f"xfail markers found in eval suite: {violations}"


def test_gate_pass_implies_zero_xfail_in_test_dirs():
    passing_gates = _gate_files_claim_pass()
    if not passing_gates:
        gate_files = list(REPO_ROOT.glob(GATE_GLOB))
        if not gate_files:
            pytest.skip("No CLUSTER_GATES.md files — fresh clone")
        pytest.skip("No gate file claims PASS — xfail coupling guard not armed")
    violations = _find_xfail_markers(TEST_ROOTS)
    assert not violations, (
        "PASS gate(s) "
        f"{[p.relative_to(REPO_ROOT) for p in passing_gates]} "
        f"forbid xfail markers; found: {violations}"
    )


def test_xfail_detector_flags_planted_non_strict_marker(tmp_path: Path):
    planted = tmp_path / "planted.py"
    planted.write_text(
        "import pytest\n\n@pytest.mark.xfail(strict=False)\ndef test_flaky():\n    assert False\n",
        encoding="utf-8",
    )
    violations = _find_xfail_markers((tmp_path,))
    assert len(violations) == 1
    assert "non-strict" in violations[0]


def test_xfail_detector_flags_default_non_strict_marker(tmp_path: Path):
    planted = tmp_path / "planted.py"
    planted.write_text(
        "import pytest\n\n@pytest.mark.xfail\ndef test_flaky():\n    assert False\n",
        encoding="utf-8",
    )
    violations = _find_xfail_markers((tmp_path,))
    assert len(violations) == 1
    assert "default-non-strict" in violations[0]
