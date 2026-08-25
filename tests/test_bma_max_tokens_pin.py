"""AST pin for BMA extraction max_tokens=8_000 (C36; supersedes C34's 12_000).

Does not import the agent module. No live Spark/warehouse.
"""

from __future__ import annotations

import ast
from pathlib import Path

_AGENT_PATH = (
    Path(__file__).resolve().parents[1]
    / "databricks"
    / "agents"
    / "workstreams"
    / "business_model_agent.py"
)

_FORBIDDEN_SOURCE_FORMS = (
    "max_tokens=12_000",
    "max_tokens=12000",
    "max_tokens=16_000",
    "max_tokens=16000",
)


def _agent_tree() -> ast.AST:
    return ast.parse(_AGENT_PATH.read_text(encoding="utf-8"))


def _call_llm_calls(tree: ast.AST) -> list[ast.Call]:
    found: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "_call_llm":
            found.append(node)
        elif isinstance(func, ast.Name) and func.id == "_call_llm":
            found.append(node)
    return found


def _first_arg_name(call: ast.Call) -> str | None:
    if not call.args:
        return None
    arg0 = call.args[0]
    if isinstance(arg0, ast.Name):
        return arg0.id
    return None


def _max_tokens_literal(call: ast.Call) -> int | None:
    for kw in call.keywords:
        if kw.arg != "max_tokens":
            continue
        val = kw.value
        if isinstance(val, ast.Constant) and isinstance(val.value, int):
            return val.value
    return None


def test_bma_extraction_call_max_tokens_is_8000() -> None:
    tree = _agent_tree()
    extraction_calls = [
        call
        for call in _call_llm_calls(tree)
        if _first_arg_name(call) == "_SYSTEM_PROMPT"
    ]
    assert extraction_calls, "no _call_llm invocation with first arg _SYSTEM_PROMPT"
    assert len(extraction_calls) == 1, (
        f"expected one extraction _call_llm, found {len(extraction_calls)}"
    )
    assert _max_tokens_literal(extraction_calls[0]) == 8000


def test_bma_no_12000_or_16000_max_tokens_remains() -> None:
    tree = _agent_tree()
    leftovers: list[int] = []
    for call in _call_llm_calls(tree):
        token = _max_tokens_literal(call)
        if token in {12000, 12_000, 16000, 16_000}:
            leftovers.append(token)
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "max_tokens":
            val = node.value
            if isinstance(val, ast.Constant) and val.value in {12000, 12_000, 16000, 16_000}:
                leftovers.append(int(val.value))
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, int)
            and node.value in {12000, 16000}
        ):
            # Only fail if this is a max_tokens binding; the keyword
            # walk above covers Call keywords. Dict literals use ast.keyword
            # only in calls, so also flag bare 12000/16000 next to a 'max_tokens' key.
            pass
    source = _AGENT_PATH.read_text(encoding="utf-8")
    for form in _FORBIDDEN_SOURCE_FORMS:
        assert form not in source
    assert leftovers == []
    # Pin form is present; the unrelated "max_tokens": 3000 dict is not a kwarg.
    assert "max_tokens=8_000" in source
