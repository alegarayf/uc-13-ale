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


def test_map_legacy_result_populates_legacy_keys_and_maps_pass_registers():
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
    assert 'result.get("section_confidence")' in source_segment
    assert 'result.get("vendor_register_json", "[]")' in source_segment
    assert 'result.get("platform_dependency_register_json", "[]")' in source_segment
    assert 'result.get("employment_register_json", "[]")' in source_segment
    assert 'result.get("ip_register_json", "[]")' in source_segment
    assert 'result.get("privacy_security_register_json", "[]")' in source_segment
    assert 'result.get("insurance_register_json", "[]")' in source_segment
    assert 'result.get("unable_to_assess_json")' in source_segment
    assert 'result.get("recommended_diligence_json")' in source_segment
    assert '"unable_to_assess_json":         "[]"' not in source_segment
    assert '"recommended_diligence_json":    "[]"' not in source_segment
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
    assert arg_names == ["self", "company_name", "spark", "extraction_endpoint", "catalog"]
    body = _method_body_source("LegalContractsAgent", "run")
    assert "self._catalog = catalog" in body
    assert "llm_endpoint" not in body


def test_main_passes_extraction_endpoint_to_run_not_llm_endpoint():
    """Falsifier: M0 F3 shadow llm_endpoint=extraction_endpoint or llm_endpoint must not return."""
    main_body = _function_body_source("main")
    assert "extraction_endpoint=extraction_endpoint" in main_body
    assert "llm_endpoint=extraction_endpoint" not in main_body
    assert "llm_endpoint=extraction_endpoint or llm_endpoint" not in main_body


def test_main_d6a_haiku_and_llama_override_to_sonnet():
    """Falsifier: notebook Cell 1 Haiku/Llama default must be overridden before agent.run()."""
    main_body = _function_body_source("main")
    assert '"haiku" in _widget_ep.lower()' in main_body
    assert '"llama" in _widget_ep.lower()' in main_body
    assert 'extraction_endpoint = "databricks-claude-sonnet-4-6"' in main_body
    assert "[override] extraction_endpoint" in main_body


def test_extract_methods_thread_extraction_endpoint_param():
    """Falsifier: extract stubs must accept extraction_endpoint for T3 _call_llm wiring."""
    for pass_id in (
        "contracts_vendors_platform",
        "employment",
        "litigation",
        "ip_privacy",
        "insurance",
    ):
        tree = ast.parse(_AGENT_SOURCE)
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "LegalContractsAgent")
        method = next(
            n for n in cls.body
            if isinstance(n, ast.FunctionDef) and n.name == f"_extract_{pass_id}"
        )
        arg_names = [a.arg for a in method.args.args]
        assert "extraction_endpoint" in arg_names, f"_extract_{pass_id} missing extraction_endpoint"
        assert "llm_endpoint" not in arg_names, f"_extract_{pass_id} still uses llm_endpoint"


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
    body = _method_body_source("LegalContractsAgent", "_domain_retrieve_pass")
    assert "_semantic_search_with_fallback" in body
    assert "catalog=self._catalog" not in body  # delegated to _semantic_search_with_fallback


def test_main_passes_catalog_to_run():
    main_body = _function_body_source("main")
    assert "catalog=catalog" in main_body
    assert "_CATALOG" not in _AGENT_SOURCE


def test_semantic_search_with_fallback_passes_catalog_on_both_paths():
    """Falsifier: fallback retry must not drop catalog=self._catalog (D3a / uc13_ale VS index)."""
    body = _method_body_source("LegalContractsAgent", "_semantic_search_with_fallback")
    assert body.count("catalog=self._catalog") >= 2
    assert '"tool":       "retrieval_fallback"' in body or '"tool": "retrieval_fallback"' in body


def test_domain_retrieve_methods_delegate_to_semantic_search_with_fallback():
    for pass_id in (
        "contracts_vendors_platform",
        "employment",
        "litigation",
        "ip_privacy",
        "insurance",
    ):
        body = _method_body_source("LegalContractsAgent", f"_domain_retrieve_{pass_id}")
        assert "_domain_retrieve_pass" in body


def test_domain_retrieve_pass_emits_domain_retrieve_trace_tool():
    body = _method_body_source("LegalContractsAgent", "_domain_retrieve_pass")
    assert 'tool_name=f"domain_retrieve_{pass_id}"' in body
    assert "_semantic_search_with_fallback" in body


def test_a0_tuned_employment_and_litigation_filename_filters():
    """Falsifier: MVP defaults that returned 0 chunks on Elder Care must be retuned."""
    assert '"Handbook"' in _AGENT_SOURCE
    assert '"Orientation"' in _AGENT_SOURCE
    assert '"Survey"' in _AGENT_SOURCE
    assert '"DOH"' in _AGENT_SOURCE


def test_does_not_import_financial_semantic_search_with_fallback():
    """Falsifier: shared financial fallback defaults catalog to uc13 — legal agent uses own method."""
    assert "from agents.subagents.workstream.financial.context_utils import" not in _AGENT_SOURCE
    assert "context_utils.semantic_search_with_fallback" not in _AGENT_SOURCE
    assert "_semantic_search_with_fallback" in _AGENT_SOURCE


def test_run_returns_m2_wired_shape():
    """Falsifier: M2 run() must expose merged registers, roll-ups, flags, and gap columns."""
    body = _method_body_source("LegalContractsAgent", "run")
    for key in (
        "contract_register_json",
        "vendor_register_json",
        "platform_dependency_register_json",
        "employment_register_json",
        "litigation_register_json",
        "ip_register_json",
        "privacy_security_register_json",
        "insurance_register_json",
        "coc_consent_list_json",
        "termination_exposure_json",
        "restrictive_covenant_map_json",
        "unable_to_assess_json",
        "recommended_diligence_json",
        "section_confidence",
        "executive_summary",
    ):
        assert f'"{key}"' in body, f"run() return missing {key}"
    assert "self._flags_as_dicts()" in body
    assert '"flags":                              []' not in body
    assert '"flags":                         []' not in body
    assert '"executive_summary":                  None' not in body


def test_run_calls_m2_rollup_flag_and_gap_builders():
    """Falsifier: M2 run() must invoke merge, roll-ups, flags, and gap assessment."""
    body = _method_body_source("LegalContractsAgent", "run")
    for required in (
        "_merge_registers",
        "_build_coc_consent_list",
        "_build_termination_exposure",
        "_build_restrictive_covenant_map",
        "_apply_legal_flags",
        "_assess_coverage_gaps",
    ):
        assert required in body, f"run() must call {required}"


def test_stakeholder_coverage_requirements_present_austin_absent():
    """Falsifier: normative §5.6 checklist must replace AUSTIN_ITEM_COVERAGE constant."""
    tree = ast.parse(_AGENT_SOURCE)
    module_constants: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    module_constants.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            module_constants.add(node.target.id)
    assert "STAKEHOLDER_COVERAGE_REQUIREMENTS" in module_constants
    assert "AUSTIN_ITEM_COVERAGE" not in module_constants


def test_run_serializes_merged_registers_not_raw_pass_accumulators():
    """Adversarial: run() must json.dumps merged output, not pre-merge registers dict."""
    body = _method_body_source("LegalContractsAgent", "run")
    assert 'json.dumps(merged["contract_register"])' in body
    assert 'json.dumps(registers["contract_register"])' not in body


def test_m2_tri_state_and_merge_helpers_defined():
    """Falsifier: §5.6.1 tri-state helpers and merge must exist at module level."""
    tree = ast.parse(_AGENT_SOURCE)
    top_level_names = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "_is_true" in top_level_names
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "LegalContractsAgent")
    method_names = {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}
    assert "_merge_registers" in method_names


def test_monolithic_retrieve_tools_removed():
    """Falsifier: legacy single-pass retrieval helpers must not remain callable dead code."""
    for dead in (
        "_tool_retrieve_material_contracts",
        "_tool_retrieve_coc_and_termination",
        "_tool_retrieve_restrictive_covenants",
        "_tool_retrieve_litigation",
        "_tool_retrieve_ip_and_data",
    ):
        assert f"def {dead}" not in _AGENT_SOURCE
