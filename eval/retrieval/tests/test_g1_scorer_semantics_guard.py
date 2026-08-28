"""Item 15 — regression guard for eval/program/g1_score_all_agents.py scorer semantics."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
# Relocated from .dev/scripts/ (gitignored, untracked, unauditable at any SHA)
# to eval/program/ by iterate-pack-now-slice T9-bis's residual-decision
# follow-up (operator-approved) so this file is git-tracked and its AST
# semantics are verifiable at the same commit as the tests that guard it.
_G1_SCORER_PATH = _REPO_ROOT / "eval" / "program" / "g1_score_all_agents.py"

if not _G1_SCORER_PATH.is_file():
    pytest.skip(
        "eval/program/g1_score_all_agents.py absent — scorer guard skipped",
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


def _score_kpi_source(tree: ast.Module) -> str:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "score_kpi":
            return ast.get_source_segment(
                _G1_SCORER_PATH.read_text(encoding="utf-8"), node
            ) or ""
    raise AssertionError("score_kpi() not found in g1_score_all_agents.py")


def _main_kpi_fetch_columns(tree: ast.Module) -> list[str]:
    """Find `fetch_analysis("kpi", [...])` inside main() and return the
    string literals of its column-list argument, in source order."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "fetch_analysis" and len(node.args) >= 2:
                first_arg = node.args[0]
                if isinstance(first_arg, ast.Constant) and first_arg.value == "kpi":
                    cols_arg = node.args[1]
                    if isinstance(cols_arg, ast.List):
                        return [
                            elt.value
                            for elt in cols_arg.elts
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                        ]
    raise AssertionError('fetch_analysis("kpi", [...]) call not found in main()')


def _load_score_kpi_callable() -> dict:
    """Compile score_kpi() plus its module-level dependencies in an isolated
    namespace, skipping g1_score_all_agents.py's top-level WorkspaceClient()
    construction (which requires live Databricks env vars). This lets us
    exercise score_kpi()'s real behavior as a mutation-checkable falsifier
    without importing the module."""
    tree = _load_module_ast()
    needed_names = {
        "jl", "nonempty", "count_pass", "score_kpi",
        "_OVERLAY_TO_KPI_COLUMN", "_OVERLAY_BLOCK_FIELDS",
    }
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in needed_names:
            nodes.append(node)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id in needed_names:
                nodes.append(node)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in needed_names:
                    nodes.append(node)
                    break
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace: dict = {"json": json}
    exec(  # noqa: S102 — isolated AST subset, not attacker-controlled input
        compile(module, filename=str(_G1_SCORER_PATH), mode="exec"), namespace
    )
    missing = {"score_kpi", "_OVERLAY_TO_KPI_COLUMN", "_OVERLAY_BLOCK_FIELDS"} - namespace.keys()
    if missing:
        raise AssertionError(f"score_kpi() isolation namespace missing: {missing}")
    return namespace


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


# --- T2: score_kpi() overlay-aware dispatch (item 1, 4) --------------------


def test_score_kpi_uses_per_overlay_dispatch_not_hardcoded_healthcare() -> None:
    """score_kpi() must resolve the KPI block column via a per-overlay
    mapping, not a single hardcoded `d.get("healthcare_kpis_json")` call."""
    body = _score_kpi_source(_load_module_ast())
    assert "_OVERLAY_TO_KPI_COLUMN" in body
    assert 'd.get("healthcare_kpis_json")' not in body


def test_main_kpi_fetch_includes_all_five_sibling_kpi_columns() -> None:
    """main()'s KPI fetch_analysis() call must widen its column list to
    include all 5 sibling `_kpis_json` columns (Coupling Surface 1: a
    scorer dispatch change without this fetch-list widening is a silent
    no-op, since score_kpi() never receives the sibling columns)."""
    cols = _main_kpi_fetch_columns(_load_module_ast())
    for expected in (
        "tech_services_kpis_json",
        "healthcare_kpis_json",
        "saas_kpis_json",
        "industrial_kpis_json",
        "consumer_kpis_json",
    ):
        assert expected in cols, f"{expected} missing from main()'s KPI fetch column list"
    assert "overlay_confirmed" in cols
    assert "missing_kpis_json" in cols


def test_score_kpi_overlay_confirmed_passes_for_all_five_confirmed_overlays() -> None:
    """Bug fix: overlay_confirmed verdict must pass for any of the 5 known
    confirmed overlay values, not only 'healthcare_services'."""
    ns = _load_score_kpi_callable()
    score_kpi = ns["score_kpi"]
    for overlay in (
        "tech_services", "healthcare_services", "b2b_saas", "industrial", "consumer",
    ):
        d = {"overlay_confirmed": overlay, "missing_kpis_json": json.dumps([])}
        _, verdicts = score_kpi(d)
        assert verdicts["overlay_confirmed"] == "pass", f"overlay={overlay!r} should pass"


def test_score_kpi_overlay_confirmed_stays_partial_for_unknown_and_none() -> None:
    """unknown / None overlay values must remain 'partial' — they have no
    sibling KPI column to resolve."""
    ns = _load_score_kpi_callable()
    score_kpi = ns["score_kpi"]
    for overlay in ("unknown", None):
        d = {"overlay_confirmed": overlay, "missing_kpis_json": json.dumps([])}
        _, verdicts = score_kpi(d)
        assert verdicts["overlay_confirmed"] == "partial"
        assert verdicts["overlay_block_fields"] == "partial"


def test_score_kpi_reads_sibling_block_matching_overlay_not_healthcare() -> None:
    """Falsifier for the core bug: when overlay_confirmed is 'tech_services'
    but healthcare_kpis_json happens to carry a fully-populated block (e.g.
    stale data from a prior run or another overlay's leftover extraction),
    the scorer must grade the TECH SERVICES block, not fall back to
    healthcare. Under the pre-fix behavior (always read
    healthcare_kpis_json), this would score 'pass'; under the fix, an empty
    tech_services_kpis_json correctly scores 'partial'."""
    ns = _load_score_kpi_callable()
    score_kpi = ns["score_kpi"]
    fully_populated_healthcare = {
        "census_or_patient_panel": "120 patients",
        "caregiver_headcount": "45",
        "clinician_headcount": "12",
        "utilization_or_productivity_note": "85% utilization",
        "compliance_incidents": [{"type": "audit"}],
        "credentialing_status_note": "current",
        "site_level_visibility": "true",
    }
    d = {
        "overlay_confirmed": "tech_services",
        "healthcare_kpis_json": json.dumps(fully_populated_healthcare),
        "tech_services_kpis_json": json.dumps({}),
        "missing_kpis_json": json.dumps([]),
    }
    _, verdicts = score_kpi(d)
    assert verdicts["overlay_confirmed"] == "pass"
    assert verdicts["overlay_block_fields"] == "partial"


def test_score_kpi_passes_overlay_block_fields_when_matching_sibling_populated() -> None:
    """Positive counterpart: a populated tech_services_kpis_json block with
    overlay_confirmed='tech_services' must score 'pass', proving the
    dispatch reads the correct column (not just failing to read the wrong
    one)."""
    ns = _load_score_kpi_callable()
    score_kpi = ns["score_kpi"]
    fully_populated_tech = {
        "utilization_rate_pct": "82%",
        "utilization_period": "Q2 2026",
        "average_bill_rate_dollars": "185",
        "contractor_pct_of_workforce": "35%",
        "delivery_geography_note": "60% onshore, 40% offshore",
    }
    d = {
        "overlay_confirmed": "tech_services",
        "healthcare_kpis_json": json.dumps({}),
        "tech_services_kpis_json": json.dumps(fully_populated_tech),
        "missing_kpis_json": json.dumps([]),
    }
    _, verdicts = score_kpi(d)
    assert verdicts["overlay_block_fields"] == "pass"
