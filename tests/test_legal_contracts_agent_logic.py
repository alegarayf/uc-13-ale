"""Runtime behavioral tests for legal_contracts_agent pure helpers and option-C flags (M3 T2)."""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from agents.workstreams.legal_contracts_agent import (
    LegalContractsAgent,
    STAKEHOLDER_COVERAGE_REQUIREMENTS,
    _DOMAIN_PASS_BUDGETS,
    _DOMAIN_PASS_IDS,
    _DOMAIN_PASS_QUERIES,
    _eq_str,
    _is_not_found,
    _is_true,
    _merge_query_hits,
    _merge_register_records,
    _pred_restrictive,
    _reconcile_register_from_citations,
    _register_dedupe_key,
)

_EMPTY_MERGED = {
    "contract_register": [],
    "vendor_register": [],
    "platform_dependency_register": [],
    "employment_register": [],
    "litigation_register": [],
    "privacy_security_register": [],
    "ip_register": [],
    "insurance_register": [],
}


def _zero_pass_chunk_counts() -> dict[str, int]:
    return {pass_id: 0 for pass_id in _DOMAIN_PASS_IDS}


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


def test_merge_register_records_upgrades_restrictive_not_found_to_true():
    """Falsifier: longer raw_quote row must not preserve not_found over true on merge."""
    existing = {
        "counterparty_name": "Landlord",
        "contract_type": "Lease",
        "raw_quote": "much longer supporting quote text from winning row",
        "restrictive_covenants": {"present": "not_found", "scope_note": None},
    }
    incoming = {
        "counterparty_name": "Landlord",
        "contract_type": "Lease",
        "raw_quote": "short",
        "restrictive_covenants": {"present": "true", "scope_note": "non-compete"},
    }
    merged = _merge_register_records(existing, incoming)
    assert merged["restrictive_covenants"]["present"] == "true"


def test_reconcile_register_from_citations_backfills_restrictive_present():
    merged = {
        "contract_register": [
            {
                "contract_id": 4,
                "counterparty_name": "Guided Living",
                "source_doc": "Guided Living - Asset Purchase Agreement - 02.07.24.pdf",
                "restrictive_covenants": {"present": "not_found", "scope_note": None},
            }
        ],
    }
    citations = [
        {
            "claim": "restrictive_covenants (contract_id 4)",
            "document": "Guided Living - Asset Purchase Agreement - 02.07.24.pdf",
            "raw_text": "Seller has not made any changes to its Business operations",
        }
    ]
    _reconcile_register_from_citations(merged, citations)
    row = merged["contract_register"][0]
    assert row["restrictive_covenants"]["present"] == "true"
    assert _pred_restrictive(merged) is True


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


def test_stakeholder_coverage_requirements_has_eleven_rows():
    assert len(STAKEHOLDER_COVERAGE_REQUIREMENTS) == 11
    assert all(
        req["domain_pass_id"] in _DOMAIN_PASS_IDS
        for req in STAKEHOLDER_COVERAGE_REQUIREMENTS
    )


def test_assess_coverage_gaps_step3_retrieval_miss(agent: LegalContractsAgent):
    """Step-3: chunks=0 → recommended diligence for unassessed item."""
    agent._assess_coverage_gaps(_EMPTY_MERGED, _zero_pass_chunk_counts(), None)
    diligence_ids = {row["item_id"] for row in agent._recommended_diligence}
    assert "litigation" in diligence_ids
    assert "Litigation exposure" in agent._unable_to_assess_items


def test_assess_coverage_gaps_step2_extraction_miss(agent: LegalContractsAgent):
    """Step-2: chunks>0 but predicate false → unable_to_assess without diligence row."""
    pass_chunk_counts = _zero_pass_chunk_counts()
    pass_chunk_counts["litigation"] = 4
    agent._assess_coverage_gaps(_EMPTY_MERGED, pass_chunk_counts, None)
    diligence_ids = {row["item_id"] for row in agent._recommended_diligence}
    assert "litigation" not in diligence_ids
    assert "Litigation exposure" in agent._unable_to_assess_items
    gap_text = " ".join(agent._data_room_gaps)
    assert "litigation: chunks retrieved but no extractable terms" in gap_text


def test_assess_coverage_gaps_wrong_pass_chunk_key_misclassifies_step3(agent: LegalContractsAgent):
    """Falsifier: typo pass_id in pass_chunk_counts defaults to 0 → false step-3."""
    pass_chunk_counts = _zero_pass_chunk_counts()
    pass_chunk_counts["litigaton"] = 6  # wrong key — not in _DOMAIN_PASS_IDS
    agent._assess_coverage_gaps(_EMPTY_MERGED, pass_chunk_counts, None)
    diligence_ids = {row["item_id"] for row in agent._recommended_diligence}
    assert "litigation" in diligence_ids


@pytest.mark.parametrize(
    "assessed_count,expected",
    [
        (0, "low"),
        (2, "low"),
        (3, "medium"),
        (6, "medium"),
        (7, "high"),
        (11, "high"),
    ],
)
def test_compute_section_confidence_band_edges(
    agent: LegalContractsAgent, assessed_count: int, expected: str
):
    agent._assessed_coverage_count = assessed_count
    assert agent._compute_section_confidence() == expected


def _hits(prefix: str, n: int) -> list[SimpleNamespace]:
    return [SimpleNamespace(chunk_id=f"{prefix}{i:02d}") for i in range(n)]


def test_merge_query_hits_reserves_generic_slots_without_dropping_targeted():
    """C5 Landed (R9): targeted hits survive the merge without starving the generic query.

    F-8 mechanism: four unique-hit queries round-robin under top_k=24 keep 6 slots
    each and drop generic ranks 6–23. Mutation: ignore ``merge_slot_allocation``
    and round-robin instead — generic kept count falls to 6 and this assertion
    fails.
    """
    budget = _DOMAIN_PASS_BUDGETS["contracts_vendors_platform"]
    allocation = budget["merge_slot_allocation"]
    top_k = budget["top_k"]
    queries = _DOMAIN_PASS_QUERIES["contracts_vendors_platform"]
    assert allocation == (14, 4, 3, 3)
    assert top_k == 24
    assert isinstance(queries, tuple) and len(queries) == 4
    assert len(allocation) == len(queries)
    assert sum(allocation) == top_k
    assert budget.get("vs_metadata_filters", False) is False

    generic = _hits("G", 24)
    t4c = [SimpleNamespace(chunk_id="G05")] + _hits("T", 8)
    coc = _hits("C", 8)
    platform = _hits("P", 8)
    per_query = [generic, t4c, coc, platform]

    starved_chunks, starved_kept = _merge_query_hits(per_query, top_k, None)
    assert starved_kept[0] == 6
    assert all(kept >= 1 for kept in starved_kept[1:])
    assert len(starved_chunks) == top_k

    chunks, kept = _merge_query_hits(per_query, top_k, allocation)
    assert kept == (14, 4, 3, 3)
    ids = [chunk.chunk_id for chunk in chunks]
    assert ids[:14] == [f"G{i:02d}" for i in range(14)]
    assert "G05" in ids[:14]
    assert ids[14:18] == [f"T{i:02d}" for i in range(4)]
    assert ids[18:21] == [f"C{i:02d}" for i in range(3)]
    assert ids[21:24] == [f"P{i:02d}" for i in range(3)]
    assert "G05" not in ids[14:]

    retrieve_src = inspect.getsource(LegalContractsAgent._domain_retrieve_pass)
    assert "_merge_query_hits" in retrieve_src
    assert 'budget.get("merge_slot_allocation")' in retrieve_src
    helper_src = inspect.getsource(_merge_query_hits)
    assert "slot_allocation" in helper_src
