"""T2 — characterization tests for eval/program/g1_score_all_agents.py:score_legal."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_G1_SCORER_PATH = _REPO_ROOT / "eval" / "program" / "g1_score_all_agents.py"

if not _G1_SCORER_PATH.is_file():
    pytest.skip(
        "eval/program/g1_score_all_agents.py absent — score_legal guard skipped",
        allow_module_level=True,
    )

RUBRIC_KEYS = (
    "t4c",
    "coc",
    "restrictive",
    "vendor",
    "platform",
    "employment",
    "founder",
    "litigation",
    "privacy",
    "ip",
    "insurance",
)


def _load_module_ast() -> ast.Module:
    return ast.parse(_G1_SCORER_PATH.read_text(encoding="utf-8"))


def _load_score_legal_callable() -> dict:
    """Compile score_legal() plus module-level helpers without importing
    g1_score_all_agents.py (top-level WorkspaceClient needs Databricks env)."""
    tree = _load_module_ast()
    needed_names = {"jl", "count_pass", "score_legal"}
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in needed_names:
            nodes.append(node)
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace: dict = {"json": json}
    exec(  # noqa: S102 — isolated AST subset, not attacker-controlled input
        compile(module, filename=str(_G1_SCORER_PATH), mode="exec"), namespace
    )
    missing = {"score_legal", "jl", "count_pass"} - namespace.keys()
    if missing:
        raise AssertionError(f"score_legal() isolation namespace missing: {missing}")
    return namespace


def _baseline_empty_dict() -> dict[str, str]:
    return {
        "contract_register_json": "[]",
        "vendor_register_json": "[]",
        "platform_dependency_register_json": "[]",
        "employment_register_json": "[]",
        "litigation_register_json": "[]",
        "privacy_security_register_json": "[]",
        "ip_register_json": "[]",
        "insurance_register_json": "[]",
    }


def _point_delta(score_legal, baseline: dict[str, str], variant: dict[str, str]) -> int:
    base_points, _ = score_legal(baseline)
    variant_points, _ = score_legal({**baseline, **variant})
    return variant_points - base_points


@pytest.fixture(scope="module")
def score_legal_ns() -> dict:
    return _load_score_legal_callable()


@pytest.fixture(scope="module")
def score_legal(score_legal_ns: dict):
    return score_legal_ns["score_legal"]


def test_score_legal_signature_and_eleven_key_rubric(score_legal) -> None:
    """Kill-criterion guard: score_legal stays (d: dict) -> tuple[int, dict] with 11 rubric keys."""
    tree = _load_module_ast()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "score_legal":
            assert node.returns is not None
            ann = ast.unparse(node.returns)
            assert "int" in ann
            assert "dict" in ann
            break
    else:
        raise AssertionError("score_legal() not found in g1_score_all_agents.py")

    points, verdicts = score_legal(_baseline_empty_dict())
    assert isinstance(points, int)
    assert set(verdicts.keys()) == set(RUBRIC_KEYS)
    assert len(verdicts) == 11


def test_score_legal_t4c_pass_contributes_one_point(score_legal) -> None:
    baseline = _baseline_empty_dict()
    variant = {
        "contract_register_json": json.dumps(
            [{"termination_for_convenience": {"present": "true"}}]
        ),
    }
    _, verdicts = score_legal({**baseline, **variant})
    assert verdicts["t4c"] == "pass"
    assert _point_delta(score_legal, baseline, variant) == 1


def test_score_legal_t4c_gap_correct_when_absent(score_legal) -> None:
    """Falsifier: t4c must stay gap-correct (0 points) when no contract carries t4c."""
    baseline = _baseline_empty_dict()
    _, verdicts = score_legal(baseline)
    assert verdicts["t4c"] == "gap-correct"
    assert _point_delta(score_legal, baseline, {}) == 0


def test_score_legal_coc_pass_contributes_one_point(score_legal) -> None:
    baseline = _baseline_empty_dict()
    variant = {
        "contract_register_json": json.dumps(
            [{"change_of_control": {"clause_present": "true"}}]
        ),
    }
    _, verdicts = score_legal({**baseline, **variant})
    assert verdicts["coc"] == "pass"
    assert _point_delta(score_legal, baseline, variant) == 1


def test_score_legal_restrictive_pass_contributes_one_point(score_legal) -> None:
    baseline = _baseline_empty_dict()
    variant = {
        "contract_register_json": json.dumps(
            [{"restrictive_covenants": {"present": "true"}}]
        ),
    }
    _, verdicts = score_legal({**baseline, **variant})
    assert verdicts["restrictive"] == "pass"
    assert _point_delta(score_legal, baseline, variant) == 1


def test_score_legal_vendor_pass_contributes_one_point(score_legal) -> None:
    baseline = _baseline_empty_dict()
    variant = {"vendor_register_json": json.dumps([{"vendor_name": "Acme Corp"}])}
    _, verdicts = score_legal({**baseline, **variant})
    assert verdicts["vendor"] == "pass"
    assert _point_delta(score_legal, baseline, variant) == 1


def test_score_legal_platform_pass_contributes_one_point(score_legal) -> None:
    baseline = _baseline_empty_dict()
    variant = {
        "platform_dependency_register_json": json.dumps([{"platform": "AWS"}]),
    }
    _, verdicts = score_legal({**baseline, **variant})
    assert verdicts["platform"] == "pass"
    assert _point_delta(score_legal, baseline, variant) == 1


def test_score_legal_employment_pass_contributes_one_point(score_legal) -> None:
    baseline = _baseline_empty_dict()
    variant = {
        "employment_register_json": json.dumps(
            [
                {"agreement_class": "employee", "source_doc": "emp1.pdf"},
                {"agreement_class": "employee", "source_doc": "emp2.pdf"},
            ]
        ),
    }
    _, verdicts = score_legal({**baseline, **variant})
    assert verdicts["employment"] == "pass"
    assert _point_delta(score_legal, baseline, variant) == 1


def test_score_legal_founder_pass_contributes_one_point(score_legal) -> None:
    baseline = _baseline_empty_dict()
    variant = {
        "employment_register_json": json.dumps(
            [{"agreement_class": "founder_key", "source_doc": "founder.pdf"}]
        ),
    }
    _, verdicts = score_legal({**baseline, **variant})
    assert verdicts["founder"] == "pass"
    assert _point_delta(score_legal, baseline, variant) == 1


def test_score_legal_litigation_pass_contributes_one_point(score_legal) -> None:
    baseline = _baseline_empty_dict()
    variant = {
        "litigation_register_json": json.dumps([{"matter": "pending dispute"}]),
    }
    _, verdicts = score_legal({**baseline, **variant})
    assert verdicts["litigation"] == "pass"
    assert _point_delta(score_legal, baseline, variant) == 1


def test_score_legal_privacy_pass_contributes_one_point(score_legal) -> None:
    baseline = _baseline_empty_dict()
    variant = {
        "privacy_security_register_json": json.dumps(
            [{"source_doc": f"privacy_{i}.pdf"} for i in range(5)]
        ),
    }
    _, verdicts = score_legal({**baseline, **variant})
    assert verdicts["privacy"] == "pass"
    assert _point_delta(score_legal, baseline, variant) == 1


def test_score_legal_ip_pass_contributes_one_point(score_legal) -> None:
    baseline = _baseline_empty_dict()
    variant = {"ip_register_json": json.dumps([{"source_doc": "IP Assignment.pdf"}])}
    _, verdicts = score_legal({**baseline, **variant})
    assert verdicts["ip"] == "pass"
    assert _point_delta(score_legal, baseline, variant) == 1


def test_score_legal_insurance_pass_contributes_one_point(score_legal) -> None:
    baseline = _baseline_empty_dict()
    variant = {
        "insurance_register_json": json.dumps(
            [{"policy": f"policy_{i}"} for i in range(3)]
        ),
    }
    _, verdicts = score_legal({**baseline, **variant})
    assert verdicts["insurance"] == "pass"
    assert _point_delta(score_legal, baseline, variant) == 1
