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


def _function_body_source(name: str) -> str:
    tree = ast.parse(_AGENT_SOURCE)
    fn = next(
        n for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == name
    )
    return ast.get_source_segment(_AGENT_SOURCE, fn) or ""


def _method_body_source(class_name: str, name: str) -> str:
    tree = ast.parse(_AGENT_SOURCE)
    cls = next(
        n for n in tree.body
        if isinstance(n, ast.ClassDef) and n.name == class_name
    )
    method = next(
        n for n in cls.body
        if isinstance(n, ast.FunctionDef) and n.name == name
    )
    return ast.get_source_segment(_AGENT_SOURCE, method) or ""


def test_run_signature_includes_catalog():
    tree = ast.parse(_AGENT_SOURCE)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "LegalContractsAgent")
    run_fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "run")
    arg_names = [a.arg for a in run_fn.args.args]
    assert arg_names == ["self", "company_name", "spark", "llm_endpoint", "catalog"]
    body = _method_body_source("LegalContractsAgent", "run")
    assert "self._catalog = catalog" in body


def test_load_contract_triggers_sql_uses_catalog_not_module_constant():
    body = _method_body_source("LegalContractsAgent", "_load_contract_triggers")
    assert "_CATALOG" not in body
    assert "self._catalog" in body
    assert ".analysis.customer_quality" in body


def test_company_profile_sql_uses_catalog_not_module_constant():
    body = _method_body_source("LegalContractsAgent", "_tool_load_company_profile")
    assert "_CATALOG" not in body
    assert "self._catalog" in body
    assert ".classification.company_profile" in body


def test_semantic_search_calls_pass_catalog():
    retrieval_methods = [
        "_tool_retrieve_material_contracts",
        "_tool_retrieve_coc_and_termination",
        "_tool_retrieve_restrictive_covenants",
        "_tool_retrieve_litigation",
        "_tool_retrieve_ip_and_data",
    ]
    for method_name in retrieval_methods:
        body = _method_body_source("LegalContractsAgent", method_name)
        assert "semantic_search(" in body
        assert "catalog=self._catalog" in body, f"{method_name} must pass catalog=self._catalog"


def test_main_passes_catalog_to_run():
    main_body = _function_body_source("main")
    assert "catalog=catalog" in main_body
    assert "_CATALOG" not in _AGENT_SOURCE
