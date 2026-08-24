"""Hermetic pins for eval/program/promote_w2a_clearsulting.py — M5 T5."""

from __future__ import annotations

import ast
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO_ROOT / "eval" / "program" / "promote_w2a_clearsulting.py"

_GATE_IDS = ("bma", "cqa", "kpi", "qoe", "profiler")
_CHECKLIST_SCORE_PATHS = {
    "bma": _REPO_ROOT / "eval" / "BMA" / "golden_checklist_clearsulting.md",
    "cqa": _REPO_ROOT / "eval" / "CQA" / "golden_checklist_clearsulting.md",
    "kpi": _REPO_ROOT / "eval" / "KPI" / "golden_checklist_clearsulting.md",
    "qoe": _REPO_ROOT / "eval" / "QOE" / "golden_checklist_clearsulting.md",
    "profiler": _REPO_ROOT / "eval" / "PROFILER" / "golden_checklist_clearsulting.md",
    "legal": _REPO_ROOT / "eval" / "LCA" / "golden_checklist_clearsulting.md",
}
_SUMMARY_SCORE_RE = re.compile(r"\*\*(\d+)/(\d+)\*\*")


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


def _assign_int(tree: ast.Module, name: str) -> int:
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
            and isinstance(value.value, int)
        ):
            return value.value
    raise AssertionError(f"int constant {name!r} not found")


def _gate_calls(tree: ast.Module) -> list[dict[str, object]]:
    for node in tree.body:
        value: ast.expr | None = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "GATE_CALLS":
                value = node.value
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "GATE_CALLS":
                    value = node.value
                    break
        if value is None:
            continue
        if not isinstance(value, ast.Tuple):
            raise AssertionError("GATE_CALLS is not a tuple")
        keys = (
            "e2e_agent_id",
            "candidate_score",
            "candidate_total",
            "e2e_snapshot_table",
        )
        calls: list[dict[str, object]] = []
        for elt in value.elts:
            if not isinstance(elt, ast.Tuple) or len(elt.elts) != 4:
                raise AssertionError("GATE_CALLS row must be a 4-tuple")
            row: dict[str, object] = {}
            for key, item in zip(keys, elt.elts, strict=True):
                if not isinstance(item, ast.Constant):
                    raise AssertionError(f"GATE_CALLS {key} is not a constant")
                row[key] = item.value
            calls.append(row)
        return calls
    raise AssertionError("GATE_CALLS not found")


def _fn(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"function {name!r} not found")


def _checklist_summary_score(path: Path) -> tuple[int, int]:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("**Summary:**"):
            matches = _SUMMARY_SCORE_RE.findall(line)
            if not matches:
                raise AssertionError(f"no **/ ** score on Summary line in {path}")
            score, total = matches[0]
            return int(score), int(total)
    raise AssertionError(f"Summary line missing in {path}")


def test_catalog_is_explicit_uc13_ale_not_production_default() -> None:
    tree = _tree()
    assert _assign_str(tree, "CATALOG") == "uc13_ale"
    fn = _fn(tree, "run_promotion")
    store_calls = [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "DeltaEvalStore"
    ]
    assert len(store_calls) == 1
    keywords = {kw.arg: kw.value for kw in store_calls[0].keywords}
    assert "catalog" in keywords
    catalog_value = keywords["catalog"]
    assert isinstance(catalog_value, ast.Name) and catalog_value.id == "CATALOG"


def test_legal_agent_id_is_legal_never_lca() -> None:
    tree = _tree()
    assert _assign_str(tree, "LEGAL_AGENT_ID") == "legal"
    fn = _fn(tree, "run_promotion")
    linkage_calls = [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "record_e2e_linkage"
    ]
    assert len(linkage_calls) == 1
    kwargs = {kw.arg: kw.value for kw in linkage_calls[0].keywords}
    agent = kwargs.get("e2e_agent_id")
    assert isinstance(agent, ast.Name) and agent.id == "LEGAL_AGENT_ID"
    source = ast.get_source_segment(_SCRIPT.read_text(encoding="utf-8"), linkage_calls[0]) or ""
    assert "lca" not in source


def test_gate_calls_cover_five_agents_and_omit_fta() -> None:
    calls = _gate_calls(_tree())
    ids = [c["e2e_agent_id"] for c in calls]
    assert ids == list(_GATE_IDS)
    assert "fta" not in ids
    assert "legal" not in ids
    assert "lca" not in ids


def test_evaluate_promotion_omits_waiver_id() -> None:
    fn = _fn(_tree(), "run_promotion")
    promo_calls = [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "evaluate_promotion"
    ]
    assert len(promo_calls) == 1
    keywords = {kw.arg for kw in promo_calls[0].keywords}
    assert "waiver_id" not in keywords
    source = ast.get_source_segment(_SCRIPT.read_text(encoding="utf-8"), promo_calls[0]) or ""
    assert "waiver_id" not in source


def test_qoe_candidate_total_is_six() -> None:
    qoe = next(c for c in _gate_calls(_tree()) if c["e2e_agent_id"] == "qoe")
    assert qoe["candidate_total"] == 6
    assert qoe["candidate_score"] == 4


def test_gate_and_legal_scores_match_checklist_summaries() -> None:
    tree = _tree()
    by_id = {c["e2e_agent_id"]: c for c in _gate_calls(tree)}
    for agent_id, path in _CHECKLIST_SCORE_PATHS.items():
        score, total = _checklist_summary_score(path)
        if agent_id == "legal":
            assert _assign_int(tree, "LEGAL_CHECKLIST_SCORE") == score
            assert _assign_int(tree, "LEGAL_CHECKLIST_TOTAL") == total
            continue
        row = by_id[agent_id]
        assert row["candidate_score"] == score, agent_id
        assert row["candidate_total"] == total, agent_id


def test_expected_status_is_baseline_bootstrap() -> None:
    assert _assign_str(_tree(), "EXPECTED_PROMOTION_STATUS") == "baseline_bootstrap"


def test_run_id_matches_clearsulting_pipeline_manifest() -> None:
    assert _assign_str(_tree(), "RUN_ID") == "6e1b4f5d95284b33bbd08942b3595dd6"


def test_cluster_driver_registers_module_before_exec() -> None:
    """Importlib exec_module without sys.modules registration crashes Py3.10 dataclasses."""
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "sys.modules[spec.name] = mod" in source
    assert "spec.loader.exec_module(mod)" in source
