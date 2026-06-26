"""Static contract tests for legal_contracts_agent.py M0 storage migration (T3)."""

from __future__ import annotations

import ast
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_AGENT_PATH = _REPO_ROOT / "databricks" / "agents" / "workstreams" / "legal_contracts_agent.py"
_AGENT_SOURCE = _AGENT_PATH.read_text(encoding="utf-8")

APPENDIX_A_COLS = {
    "company_name",
    "executive_summary",
    "section_confidence",
    "contract_register_json",
    "vendor_register_json",
    "platform_dependency_register_json",
    "employment_register_json",
    "litigation_register_json",
    "privacy_security_register_json",
    "ip_register_json",
    "insurance_register_json",
    "coc_consent_list_json",
    "termination_exposure_json",
    "restrictive_covenant_map_json",
    "unable_to_assess_json",
    "recommended_diligence_json",
    "flags",
    "data_room_gaps",
    "citations",
    "reasoning_trace",
    "created_at",
}


def _extract_module_constant(name: str) -> str:
    tree = ast.parse(_AGENT_SOURCE)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.get_source_segment(_AGENT_SOURCE, node.value) or ""
    raise AssertionError(f"constant {name} not found")


def _extract_set_literal(name: str) -> set[str]:
    segment = _extract_module_constant(name)
    return set(re.findall(r'"([^"]+)"', segment))


def _ddl_column_names(ddl: str) -> set[str]:
    body = ddl.split("(", 1)[1].rsplit(")", 1)[0]
    return {
        line.strip().split()[0]
        for line in body.splitlines()
        if line.strip() and not line.strip().startswith("--")
    }


def test_expected_cols_matches_appendix_a():
    assert _extract_set_literal("_EXPECTED_COLS") == APPENDIX_A_COLS


def test_create_legal_table_ddl_columns_match_expected_cols():
    ddl_template = _extract_module_constant("_CREATE_LEGAL_TABLE_SQL")
    ddl_cols = _ddl_column_names(ddl_template.format(catalog="uc13_ale"))
    assert ddl_cols == APPENDIX_A_COLS


def test_compat_view_sql_maps_legacy_subset_and_triggered_reviews_zero():
    view_template = _extract_module_constant("_CREATE_LEGAL_CONTRACTS_VIEW_SQL")
    view_sql = view_template.format(catalog="uc13_ale")
    assert "CREATE OR REPLACE VIEW uc13_ale.analysis.legal_contracts AS" in view_sql
    assert "0 AS triggered_reviews_loaded" in view_sql
    assert "FROM uc13_ale.analysis.legal" in view_sql
    assert "vendor_register_json" not in view_sql


def test_map_legacy_result_populates_legacy_keys_and_empty_mvp_json_columns():
    tree = ast.parse(_AGENT_SOURCE)
    fn = next(
        n for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "_map_legacy_result_to_legal_row"
    )
    returns = [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict)
    ]
    assert returns, "_map_legacy_result_to_legal_row must return a dict literal"
    keys = {k.value for k in returns[0].value.keys if isinstance(k, ast.Constant)}
    assert keys == APPENDIX_A_COLS
    source_segment = ast.get_source_segment(_AGENT_SOURCE, returns[0].value) or ""
    assert '"section_confidence":            None' in source_segment
    assert '"vendor_register_json":          "[]"' in source_segment
    assert '"unable_to_assess_json":         "[]"' in source_segment
    assert "triggered_reviews_loaded" not in source_segment


def test_main_default_catalog_is_uc13_ale():
    assert 'get_param("catalog",             default="uc13_ale")' in _AGENT_SOURCE


def test_drop_table_before_view_in_ensure_legal_storage():
    """Adversarial: VIEW creation must follow DROP TABLE legal_contracts."""
    drop_pos = _AGENT_SOURCE.index('DROP TABLE IF EXISTS {catalog}.analysis.legal_contracts')
    view_pos = _AGENT_SOURCE.index("_CREATE_LEGAL_CONTRACTS_VIEW_SQL.format")
    assert drop_pos < view_pos
