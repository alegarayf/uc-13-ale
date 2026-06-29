"""Runtime behavioral tests for legal_contracts_agent pure helpers and option-C flags (M3 T2)."""

from __future__ import annotations

import pytest

from agents.workstreams.legal_contracts_agent import (
    LegalContractsAgent,
    _eq_str,
    _is_not_found,
    _is_true,
    _merge_register_records,
    _register_dedupe_key,
)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("true", True),
        ("True", True),
        (" TRUE ", True),
        ("false", False),
        ("not_found", False),
        ("", False),
        (None, False),
    ],
)
def test_is_true_tri_state(value, expected):
    assert _is_true(value) is expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("not_found", True),
        ("NOT_FOUND", True),
        (" not_found ", True),
        ("true", False),
        ("false", False),
        ("", False),
        (None, False),
    ],
)
def test_is_not_found_tri_state(value, expected):
    assert _is_not_found(value) is expected


@pytest.mark.parametrize(
    "value,expected,match",
    [
        ("open", "open", True),
        ("OPEN", "open", True),
        (" regulatory ", "regulatory", True),
        ("closed", "open", False),
        ("", "open", False),
        (None, "regulatory", False),
    ],
)
def test_eq_str_case_insensitive(value, expected, match):
    assert _eq_str(value, expected) is match


def test_register_dedupe_key_normalizes_contract_counterparty():
    key_a = _register_dedupe_key(
        "contract_register",
        {"counterparty_name": "  Acme  Corp ", "contract_type": "MSA"},
    )
    key_b = _register_dedupe_key(
        "contract_register",
        {"counterparty_name": "acme corp", "contract_type": "msa"},
    )
    assert key_a == key_b == ("acme corp", "msa")


def test_merge_register_records_prefers_longer_raw_quote():
    existing = {
        "counterparty_name": "Acme",
        "contract_type": "MSA",
        "raw_quote": "short",
        "change_of_control": {"consent_required": "false"},
    }
    incoming = {
        "counterparty_name": "Acme",
        "contract_type": "MSA",
        "raw_quote": "much longer supporting quote text",
        "change_of_control": {"consent_required": "true"},
    }
    merged = _merge_register_records(existing, incoming)
    assert "much longer supporting quote text" in merged["raw_quote"]
    assert "short" in merged["raw_quote"]
    assert merged["change_of_control"]["consent_required"] == "true"


def test_merge_register_records_unions_source_doc_citations():
    existing = {"source_doc": "MSA.pdf", "raw_quote": "same length"}
    incoming = {"source_doc": "Amendment.pdf", "raw_quote": "same length"}
    merged = _merge_register_records(existing, incoming)
    assert merged["source_doc"] == "MSA.pdf | Amendment.pdf"


@pytest.fixture
def agent() -> LegalContractsAgent:
    return LegalContractsAgent()


def test_apply_legal_flags_coc_consent_required(agent: LegalContractsAgent):
    merged = {
        "contract_register": [
            {
                "counterparty_name": "Acme",
                "source_doc": "MSA.pdf",
                "change_of_control": {"consent_required": "true"},
            }
        ],
        "vendor_register": [],
        "litigation_register": [],
    }
    agent._apply_legal_flags(merged)
    metrics = {f.metric for f in agent._flags}
    assert "coc_consent_required" in metrics


def test_apply_legal_flags_restrictive_covenant_contract_only(agent: LegalContractsAgent):
    merged = {
        "contract_register": [
            {
                "counterparty_name": "Beta LLC",
                "source_doc": "SaaS.pdf",
                "restrictive_covenants": {"present": "true", "scope_note": "non-compete"},
            }
        ],
        "vendor_register": [],
        "litigation_register": [],
    }
    agent._apply_legal_flags(merged)
    metrics = {f.metric for f in agent._flags}
    assert "restrictive_covenant" in metrics


def test_apply_legal_flags_unusual_indemnity_contract_and_vendor(agent: LegalContractsAgent):
    merged = {
        "contract_register": [
            {
                "counterparty_name": "Gamma",
                "source_doc": "C1.pdf",
                "liability_indemnity": {"unusual_indemnity": "true"},
            }
        ],
        "vendor_register": [
            {
                "vendor_name": "VendorCo",
                "source_doc": "V1.pdf",
                "liability_indemnity": {"unusual_indemnity": "true"},
            }
        ],
        "litigation_register": [],
    }
    agent._apply_legal_flags(merged)
    metrics = [f.metric for f in agent._flags]
    assert metrics.count("unusual_indemnity") == 2


def test_apply_legal_flags_open_legal_matter(agent: LegalContractsAgent):
    merged = {
        "contract_register": [],
        "vendor_register": [],
        "litigation_register": [
            {
                "matter_type": "employment",
                "status": "open",
                "description": "Pending wage claim",
                "source_doc": "Lit.pdf",
            }
        ],
    }
    agent._apply_legal_flags(merged)
    metrics = {f.metric for f in agent._flags}
    assert "open_legal_matter_employment" in metrics


def test_apply_legal_flags_regulatory_matter_any_status(agent: LegalContractsAgent):
    merged = {
        "contract_register": [],
        "vendor_register": [],
        "litigation_register": [
            {
                "matter_type": "regulatory",
                "status": "closed",
                "description": "Historical HIPAA inquiry",
                "source_doc": "Reg.pdf",
            }
        ],
    }
    agent._apply_legal_flags(merged)
    metrics = {f.metric for f in agent._flags}
    assert "regulatory_matter" in metrics


def test_apply_legal_flags_open_regulatory_emits_both_flags(agent: LegalContractsAgent):
    """Falsifier: open regulatory matters emit open_legal_matter_regulatory and regulatory_matter."""
    merged = {
        "contract_register": [],
        "vendor_register": [],
        "litigation_register": [
            {
                "matter_type": "regulatory",
                "status": "open",
                "description": "Active state survey",
                "source_doc": "Survey.pdf",
            }
        ],
    }
    agent._apply_legal_flags(merged)
    metrics = {f.metric for f in agent._flags}
    assert metrics == {"open_legal_matter_regulatory", "regulatory_matter"}
