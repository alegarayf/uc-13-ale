"""Static contract tests for legal_contracts_agent per-pass extraction (M1 T3)."""

from __future__ import annotations

import ast
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_AGENT_PATH = _REPO_ROOT / "databricks" / "agents" / "workstreams" / "legal_contracts_agent.py"
_AGENT_SOURCE = _AGENT_PATH.read_text(encoding="utf-8")

_PASS_REGISTER_KEYS = {
    "contracts_vendors_platform": (
        "contract_register",
        "vendor_register",
        "platform_dependency_register",
    ),
    "employment": ("employment_register",),
    "litigation": ("litigation_register",),
    "ip_privacy": ("ip_register", "privacy_security_register"),
    "insurance": ("insurance_register",),
}


def _method_body_source(class_name: str, name: str) -> str:
    tree = ast.parse(_AGENT_SOURCE)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(_AGENT_SOURCE, method) or ""


def test_monolithic_prompts_retired():
    assert "_USER_PROMPT_TEMPLATE" not in _AGENT_SOURCE
    assert "combined_chunk_text" not in _AGENT_SOURCE
    assert "_EXTRACT_SYSTEM_PROMPT" in _AGENT_SOURCE
    assert "_USER_PROMPT_CONTRACTS_VENDORS_PLATFORM" in _AGENT_SOURCE


def test_domain_pass_extract_config_covers_all_passes_and_registers():
    for pass_id, keys in _PASS_REGISTER_KEYS.items():
        assert f'"{pass_id}"' in _AGENT_SOURCE
        for key in keys:
            assert f'"{key}"' in _AGENT_SOURCE


def test_normative_schema_names_in_user_prompts():
    prompt_segment = _AGENT_SOURCE.split("_DOMAIN_PASS_BUDGETS", 1)[0]
    assert "restrictive_covenants" in prompt_segment
    assert "liability_indemnity" in prompt_segment
    assert "exclusivity_mfn_noncompete" not in prompt_segment
    assert "liability_cap" not in prompt_segment


def test_prompt_schema_examples_avoid_json_boolean_literals():
    """Falsifier: §5.6.1 — prompts must not show unquoted JSON true/false tokens."""
    prompt_segment = _AGENT_SOURCE.split("_DOMAIN_PASS_BUDGETS", 1)[0]
    assert not re.search(r":\s*true\b", prompt_segment)
    assert not re.search(r":\s*false\b", prompt_segment)


def test_domain_extract_pass_wires_build_focused_context_and_retry():
    body = _method_body_source("LegalContractsAgent", "_domain_extract_pass")
    assert "build_focused_context" in body
    assert "context_utils" in body
    assert "max_chars // 2" in body
    assert "_parse_json_response" in body
    assert "_call_llm" in body


def test_extract_methods_delegate_to_domain_extract_pass():
    for pass_id in _PASS_REGISTER_KEYS:
        body = _method_body_source("LegalContractsAgent", f"_extract_{pass_id}")
        assert "_domain_extract_pass" in body
        assert f'"{pass_id}"' in body


def test_normalize_pass_payload_ensures_register_keys():
    body = _method_body_source("LegalContractsAgent", "_normalize_pass_payload")
    assert "register_keys" in body
    assert "isinstance" in body
