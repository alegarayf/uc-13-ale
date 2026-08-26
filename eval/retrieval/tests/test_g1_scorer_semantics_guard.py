"""Item 15 — regression guard for .dev/g1_score_all_agents.py scorer semantics."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_G1_SCORER_PATH = _REPO_ROOT / ".dev" / "scripts" / "g1_score_all_agents.py"

if not _G1_SCORER_PATH.is_file():
    pytest.skip(
        ".dev/scripts/g1_score_all_agents.py absent — scorer guard skipped on fresh clone",
        allow_module_level=True,
    )


def _load_module_ast() -> ast.Module:
    return ast.parse(_G1_SCORER_PATH.read_text(encoding="utf-8"))


def _baselines_dict_keys(tree: ast.Module) -> set[str]:
    for node in tree.body:
        value_node: ast.expr | None = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "BASELINES" and node.value is not None:
                value_node = node.value
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "BASELINES":
                    value_node = node.value
                    break
        if value_node is not None and isinstance(value_node, ast.Dict):
            keys: set[str] = set()
            for key_node in value_node.keys:
                if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                    keys.add(key_node.value)
            return keys
    raise AssertionError("BASELINES dict not found in g1_score_all_agents.py")


def _score_fta_source(tree: ast.Module) -> str:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "score_fta":
            return ast.get_source_segment(
                _G1_SCORER_PATH.read_text(encoding="utf-8"), node
            ) or ""
    raise AssertionError("score_fta() not found in g1_score_all_agents.py")


def test_baselines_use_underscore_elder_care_slug() -> None:
    keys = _baselines_dict_keys(_load_module_ast())
    assert "elder_care" in keys
    assert "elder-care" not in keys


def test_company_slug_delegates_to_canonical_fold() -> None:
    source = _G1_SCORER_PATH.read_text(encoding="utf-8")
    assert "from eval.retrieval.companies import canonical_company_slug" in source
    fn_block = source.split("def company_slug", 1)[1].split("\ndef ", 1)[0]
    assert "canonical_company_slug" in fn_block
    assert ".replace(" not in fn_block


def test_score_fta_uses_pass_partial_miss_weights() -> None:
    body = _score_fta_source(_load_module_ast())
    assert '1.0 if x == "pass"' in body
    assert '0.5 if x == "partial"' in body
    assert "0.0" in body


def test_score_fta_return_annotation_is_float_tuple() -> None:
    tree = _load_module_ast()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "score_fta":
            assert node.returns is not None
            ann = ast.unparse(node.returns)
            assert "float" in ann
            assert "dict" in ann
            return
    raise AssertionError("score_fta() not found")


def test_report_fta_floor_is_sixteen_of_eighteen() -> None:
    source = _G1_SCORER_PATH.read_text(encoding="utf-8")
    assert "passes >= 16" in source
    assert "_ELDER_CARE_BASELINES" in source
    assert '"fta": (16, 18' in source
