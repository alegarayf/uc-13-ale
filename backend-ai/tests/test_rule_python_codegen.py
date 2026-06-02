import ast

import pytest

from app.services.rule_python_codegen import ensure_rule_python_function, generate_python_function


def test_generate_python_function_with_conditions():
    rule = {
        "name": "Min ARR",
        "conditions": [
            {"field": "AnnualRevenue", "operator": ">=", "value": 20_000_000},
        ],
    }
    pf = generate_python_function(rule, user_prompt="ARR floor", summary="Require 20M ARR")
    assert pf["entrypoint"].startswith("evaluate_")
    ast.parse(pf["source"])
    assert "opportunity['AnnualRevenue']" in pf["source"]
    assert "passed" in pf["source"]


def test_ensure_rule_python_function_adds_when_missing():
    rule = {"name": "Test rule", "conditions": []}
    enriched = ensure_rule_python_function(rule, user_prompt="test", summary="A test rule")
    assert "python_function" in enriched
    assert enriched["python_function"]["source"]


def test_ensure_rule_python_function_keeps_valid_existing():
    source = "def evaluate_ok(opportunity: dict) -> dict:\n    return {'passed': True, 'reason': 'ok'}\n"
    ast.parse(source)
    rule = {
        "name": "OK",
        "python_function": {"entrypoint": "evaluate_ok", "source": source},
    }
    enriched = ensure_rule_python_function(rule, user_prompt="x", summary="y")
    assert enriched["python_function"]["source"] == source
