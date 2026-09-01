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
    _USER_PROMPT_CONTRACTS_VENDORS_PLATFORM,
    _eq_str,
    _is_not_found,
    _is_true,
    _merge_query_hits,
    _merge_register_records,
    _pred_coc,
    _pred_founder,
    _pred_ip,
    _pred_privacy,
    _pred_restrictive,
    _pred_t4c,
    _reconcile_coc_from_nested_fields,
    _reconcile_register_from_citations,
    _reconcile_t4c_from_nested_fields,
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


def test_reconcile_coc_from_nested_fields_backfills_clause_present():
    """Elder Care live re-run (T1, ledger-close-now-slice) showed the LLM
    populating change_of_control.consent_required/consent_standard/
    ownership_threshold_pct with real lease-assignment detail (Westchester
    landlord consent clause) while leaving clause_present itself
    'not_found' — an internal-consistency gap g1_score_all_agents.score_legal
    reads strictly (coc scored gap-correct, not pass). Mutation-checked:
    commenting out the has_evidence upgrade branch left clause_present
    'not_found' and made the final assertion fail; reverted after confirming
    the failure."""
    merged = {
        "contract_register": [
            {
                "contract_id": 5,
                "counterparty_name": "Landlord (Westchester)",
                "source_doc": "Westchester_Lease_0121.pdf",
                "change_of_control": {
                    "clause_present": "not_found",
                    "consent_required": "true",
                    "consent_standard": "Prior written consent of Owner required for assignment",
                    "ownership_threshold_pct": "majority",
                },
            },
            {
                "contract_id": 6,
                "counterparty_name": "No evidence counterparty",
                "change_of_control": {
                    "clause_present": "not_found",
                    "consent_required": None,
                    "consent_standard": None,
                    "ownership_threshold_pct": None,
                },
            },
        ],
    }
    _reconcile_coc_from_nested_fields(merged)
    assert merged["contract_register"][0]["change_of_control"]["clause_present"] == "true"
    assert merged["contract_register"][1]["change_of_control"]["clause_present"] == "not_found"
    assert _pred_coc(merged) is True


# --- T11 fix #1: contracts-pass prompt hardening (field-sync rule) --------


def test_contracts_prompt_has_field_sync_rule_for_coc_and_t4c():
    """The LLM must be instructed to keep change_of_control.clause_present /
    termination_for_convenience.present in sync with their own nested detail
    fields — mirrors the intent of _reconcile_coc_from_nested_fields (T1)
    inside the prompt itself, targeting the Run-2 failure mode (T1.md: the
    second Elder Care live run populated NO CoC detail fields at all, so
    post-merge reconciliation had nothing to backfill from). Mutation-checked:
    removing the 'Field-sync rule' sentence from the prompt constant made the
    second assertion fail; reverted after confirming the failure."""
    prompt = _USER_PROMPT_CONTRACTS_VENDORS_PLATFORM
    assert "CLAUSE-FAMILY EXTRACTION RULES" in prompt
    assert "Field-sync rule" in prompt
    assert "must be \"true\", never \"not_found\"" in prompt


# --- T11 fix #2: contracts-pass retrieval widen ----------------------------


def test_contracts_vendors_platform_budget_widened_workstream_and_vs_filters():
    """Mirrors the employment (T1) / insurance workstream_filter widen and the
    ip_privacy (C6 R5) vs_metadata_filters precedent — superset filter, cannot
    remove previously-eligible chunks. Mutation-checked: removing the
    workstream_filter key made this assertion fail (falls back to the
    _domain_retrieve_pass default of ["LEGAL"] only); reverted after
    confirming the failure."""
    budget = _DOMAIN_PASS_BUDGETS["contracts_vendors_platform"]
    assert budget.get("workstream_filter") == ["LEGAL", "BACKGROUND"]
    assert budget.get("vs_metadata_filters") is True

    retrieve_src = inspect.getsource(LegalContractsAgent._domain_retrieve_pass)
    assert 'budget.get("workstream_filter", ["LEGAL"])' in retrieve_src


# --- T11 fix #3: deterministic t4c backfill (mirrors CoC pattern) ---------


def test_reconcile_t4c_from_nested_fields_backfills_present():
    """Mirrors test_reconcile_coc_from_nested_fields_backfills_clause_present
    (T1) for termination_for_convenience — a row carrying a concrete
    notice_days or penalty value is, by construction, describing a present
    clause even when the LLM left the flag itself 'not_found'. Negative case
    (all fields None) proves the backfill does not invent terms. Mutation-
    checked: neutralizing the has_evidence branch left present 'not_found'
    and made the first assertion fail; reverted after confirming the
    failure."""
    merged = {
        "contract_register": [
            {
                "contract_id": 1,
                "counterparty_name": "Landlord (Westchester)",
                "source_doc": "Westchester_Lease_0121.pdf",
                "termination_for_convenience": {
                    "present": "not_found",
                    "notice_days": "60",
                    "penalty": None,
                },
            },
            {
                "contract_id": 2,
                "counterparty_name": "No evidence counterparty",
                "termination_for_convenience": {
                    "present": "not_found",
                    "notice_days": None,
                    "penalty": None,
                },
            },
        ],
    }
    _reconcile_t4c_from_nested_fields(merged)
    assert merged["contract_register"][0]["termination_for_convenience"]["present"] == "true"
    assert merged["contract_register"][1]["termination_for_convenience"]["present"] == "not_found"
    assert _pred_t4c(merged) is True


def test_reconcile_t4c_from_nested_fields_backfills_from_penalty_alone():
    """Falsifier: penalty-only evidence (no notice_days) must still backfill —
    proves the two has_evidence branches are OR'd, not AND'd."""
    merged = {
        "contract_register": [
            {
                "contract_id": 1,
                "counterparty_name": "Penalty Only Co",
                "source_doc": "Penalty.pdf",
                "termination_for_convenience": {
                    "present": "not_found",
                    "notice_days": None,
                    "penalty": "$50,000 early termination fee",
                },
            },
        ],
    }
    _reconcile_t4c_from_nested_fields(merged)
    assert merged["contract_register"][0]["termination_for_convenience"]["present"] == "true"


def test_run_wires_reconcile_t4c_after_merge():
    """Falsifier: run() must call _reconcile_t4c_from_nested_fields after the
    existing CoC reconciliation, before roll-ups read contract_register."""
    body = inspect.getsource(LegalContractsAgent.run)
    coc_pos = body.index("_reconcile_coc_from_nested_fields(merged)")
    t4c_pos = body.index("_reconcile_t4c_from_nested_fields(merged)")
    rollup_pos = body.index("_build_coc_consent_list(")
    assert coc_pos < t4c_pos < rollup_pos


# --- T11 fix #4: restrictive predicate realignment (employment register) --


def test_pred_restrictive_still_requires_source_doc_on_employment_rows():
    """Falsifier: the employment-register widen must not bypass the
    has_source_doc gate that the contract_register branch already enforces."""
    merged = {
        "contract_register": [],
        "employment_register": [
            {"agreement_class": "employee", "source_doc": "", "non_compete": {"present": "true"}},
        ],
    }
    assert _pred_restrictive(merged) is False


def test_pred_restrictive_false_when_employment_restrictive_not_found():
    """Falsifier: sourced employment rows with not_found non_compete/non_solicit
    must not flip the predicate — only concrete evidence should."""
    merged = {
        "contract_register": [],
        "employment_register": [
            {
                "agreement_class": "employee",
                "source_doc": "generic_offer_letter.pdf",
                "non_compete": {"present": "not_found"},
                "non_solicit": {"present": "not_found"},
            }
        ],
    }
    assert _pred_restrictive(merged) is False


def test_pred_restrictive_four_company_regression_matrix():
    """Mandatory four-company hermetic regression (kill criterion 1) before
    shipping fix #4. Fixture shapes are hermetic, built from each company's
    documented live register pattern, not live warehouse reads:
    - Elder Care: contract_register-sourced restrictive covenant already
      passes (golden_checklist_elder_care.md L21: 5 contract_register rows,
      APA + Manhattan/Long Island leases) — must stay True, unaffected by
      the employment-register addition (it is additive, OR'd in).
    - Clearsulting: genuinely empty corpus for this clause family
      (golden_checklist_clearsulting.md L20: 0 non-compete/non-solicit/MFN/
      exclusivity hits in 2417 chunks) — must stay False, not become a false
      positive.
    - GKF: contract_register-sourced restrictive covenant already passes
      (golden_checklist_gkf.md L20: FDD Confidentiality and Noncompetition
      Agreement rows) — must stay True.
    - SPG: the row this fix targets. contract_register clause flags are all
      not_found (T1.md L96) but employment agreements carry non-compete/
      non-solicit language the old contract_register-only predicate could
      never see (golden_checklist_spg.md L20: Sacramento/Fairfax/Denver/Lewis
      employment & IC agreements) — must flip from False to True.
    Mutation-checked: reverting _pred_restrictive to its pre-fix,
    contract_register-only body made the SPG assertion fail (False instead
    of True) while leaving the other three assertions unchanged; reverted
    after confirming the failure."""
    elder_care_merged = {
        "contract_register": [
            {
                "contract_id": 1,
                "counterparty_name": "Manhattan Landlord",
                "source_doc": "Manhattan_Lease.pdf",
                "restrictive_covenants": {"present": "true", "scope_note": "non-compete clause"},
            }
        ],
        "employment_register": [],
    }
    assert _pred_restrictive(elder_care_merged) is True

    clearsulting_merged = {
        "contract_register": [],
        "employment_register": [],
    }
    assert _pred_restrictive(clearsulting_merged) is False

    gkf_merged = {
        "contract_register": [
            {
                "contract_id": 1,
                "counterparty_name": "Goddard Franchisor LLC",
                "source_doc": "FDD_Confidentiality_and_Noncompetition_Agreement.pdf",
                "restrictive_covenants": {
                    "present": "true",
                    "scope_note": "confidentiality and noncompetition",
                },
            }
        ],
        "employment_register": [],
    }
    assert _pred_restrictive(gkf_merged) is True

    spg_merged = {
        "contract_register": [
            {
                "contract_id": 1,
                "counterparty_name": "MSA counterparty",
                "source_doc": "1.1.3.1.10_Grand Junction MSA.pdf",
                "restrictive_covenants": {"present": "not_found", "scope_note": None},
            }
        ],
        "employment_register": [
            {
                "person_or_role": "Maximillion Jenson",
                "agreement_class": "employee",
                "source_doc": "7.5.38_Sacramento_-_Employment_Agreement__Maximillion_Jenson.pdf",
                "non_compete": {
                    "present": "true",
                    "scope_note": "Specialized Training; Goodwill; Non-Compete",
                },
                "non_solicit": {
                    "present": "true",
                    "scope_note": "Finder's Fee on hiring Company employees or contractors",
                },
            }
        ],
    }
    assert _pred_restrictive(spg_merged) is True


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
    # T11 (ledger-close-now-slice, amendment-2) flipped this to True as part of
    # fix #2's retrieval widen — superseded from the pre-T11 False baseline;
    # see test_contracts_vendors_platform_budget_widened_workstream_and_vs_filters.
    assert budget.get("vs_metadata_filters", False) is True

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


# --- T3: employment/ip_privacy retrieval-query fix (item 2) ---------------


def _domain_pass_queries_as_tuple(pass_id: str) -> tuple[str, ...]:
    raw_query = _DOMAIN_PASS_QUERIES[pass_id]
    return (raw_query,) if isinstance(raw_query, str) else tuple(raw_query)


def test_all_domain_passes_with_slot_allocation_match_query_count():
    """Falsifier for config drift: any pass declaring merge_slot_allocation
    must have an allocation tuple whose length matches its query tuple length
    and whose sum does not exceed top_k. This guards against exactly the class
    of bug this subtask introduces — two independently-edited dicts
    (_DOMAIN_PASS_QUERIES, _DOMAIN_PASS_BUDGETS) drifting out of sync. Mutation-
    checked: temporarily lengthening employment's merge_slot_allocation to a
    3-tuple while its query tuple stayed length 2 made this assertion fail;
    reverted after confirming the failure."""
    for pass_id, budget in _DOMAIN_PASS_BUDGETS.items():
        allocation = budget.get("merge_slot_allocation")
        if allocation is None:
            continue
        queries = _domain_pass_queries_as_tuple(pass_id)
        assert len(allocation) == len(queries), f"{pass_id}: allocation/query count drift"
        assert sum(allocation) <= budget["top_k"], f"{pass_id}: allocation exceeds top_k"


def test_employment_budget_reserves_founder_query_slots():
    """founder/privacy items were reading retrieved_no_terms because the single
    generic employment query never surfaced Kate Marks Restricted Stock /
    Stock Transfer chunks within its ANN window (live warehouse check on
    Elder Care's latest analysis.legal row, T3 diagnostic step). Employment
    is now a 2-query pass with a founder-targeted second query and reserved
    merge slots."""
    budget = _DOMAIN_PASS_BUDGETS["employment"]
    queries = _domain_pass_queries_as_tuple("employment")
    allocation = budget["merge_slot_allocation"]
    assert len(queries) == 2
    assert allocation == (7, 3)
    assert sum(allocation) == budget["top_k"]
    founder_query = queries[1].lower()
    assert "founder" in founder_query
    assert "restricted stock" in founder_query
    assert "stock transfer" in founder_query


def test_employment_budget_admits_background_tagged_docs_for_spg():
    """SPG's employment-agreement docs are tagged LEGAL and BACKGROUND (not
    LEGAL-exclusive) post-reclassification, so a LEGAL-only workstream_filter
    misses them the same way the insurance pass missed BACKGROUND-tagged COI
    certs before its own workstream_filter fix (see the insurance budget's
    comment a few entries below). Mutation-checked: removing the employment
    budget's workstream_filter key made this assertion fail (falls back to
    the _domain_retrieve_pass default of ["LEGAL"] only); reverted after
    confirming the failure."""
    budget = _DOMAIN_PASS_BUDGETS["employment"]
    assert budget.get("workstream_filter") == ["LEGAL", "BACKGROUND"]

    retrieve_src = inspect.getsource(LegalContractsAgent._domain_retrieve_pass)
    assert 'budget.get("workstream_filter", ["LEGAL"])' in retrieve_src


def test_ip_privacy_budget_reserves_confidentiality_query_slots():
    """Same defect class for privacy: internal HIPAA confidentiality / employee
    non-disclosure / HIPAA-release docs were filename-matched but starved out
    of the generic BAA-weighted query's ANN window (live warehouse check:
    only 4 of 4+ privacy_security_register-eligible docs retrieved, one short
    of score_legal's len>=5 pass threshold). ip_privacy is now a 2-query pass
    with a confidentiality-targeted second query and reserved merge slots."""
    budget = _DOMAIN_PASS_BUDGETS["ip_privacy"]
    queries = _domain_pass_queries_as_tuple("ip_privacy")
    allocation = budget["merge_slot_allocation"]
    assert len(queries) == 2
    assert allocation == (5, 3)
    assert sum(allocation) == budget["top_k"]
    confidentiality_query = queries[1].lower()
    assert "hipaa confidentiality" in confidentiality_query
    assert "non-disclosure" in confidentiality_query


def test_pred_founder_requires_founder_key_agreement_class():
    """founder predicate still gates strictly on agreement_class=='founder_key'
    with a non-empty source_doc — the retrieval fix does not loosen this."""
    merged_no_founder = {
        "employment_register": [
            {"agreement_class": "employee", "source_doc": "Batistil Contract Agreement 2025.pdf"},
        ],
    }
    assert _pred_founder(merged_no_founder) is False

    merged_with_founder = {
        "employment_register": [
            {"agreement_class": "employee", "source_doc": "Batistil Contract Agreement 2025.pdf"},
            {"agreement_class": "founder_key", "source_doc": "Kate Marks Restricted Stock.pdf"},
        ],
    }
    assert _pred_founder(merged_with_founder) is True

    merged_founder_no_source = {
        "employment_register": [
            {"agreement_class": "founder_key", "source_doc": ""},
        ],
    }
    assert _pred_founder(merged_founder_no_source) is False


def test_pred_privacy_passes_on_any_single_sourced_row():
    """_pred_privacy (agent-side 'assessed') passes on any single row with a
    source_doc — score_legal's G1 rubric (len>=5) is a stricter, separate
    threshold documented in the packet; the two are allowed to diverge."""
    assert _pred_privacy({"privacy_security_register": []}) is False
    assert _pred_privacy(
        {"privacy_security_register": [{"source_doc": "dropbox_hipaa_agreement.pdf"}]}
    ) is True


# --- T5: ip_register unable_to_assess / corpus_absent reroute (item 5) -----


def test_pred_ip_requires_sourced_ip_register_row():
    """_pred_ip stays any sourced ip_register row — T5 does not loosen it."""
    assert _pred_ip({"ip_register": []}) is False
    assert _pred_ip({"ip_register": [{"source_doc": ""}]}) is False
    assert _pred_ip({"ip_register": [{"source_doc": "IP Assignment.pdf"}]}) is True


def test_ip_coverage_entry_pins_display_and_corpus_absent_reroute():
    ip_req = next(req for req in STAKEHOLDER_COVERAGE_REQUIREMENTS if req["item_id"] == "ip")
    assert ip_req["display_name"] == "IP ownership, assignment, OSS"
    assert ip_req["domain_pass_id"] == "ip_privacy"
    assert ip_req["assessed_predicate"] is _pred_ip
    assert ip_req.get("corpus_absent_if_unassessed") is True


def test_ip_unable_to_assess_fallback_when_register_empty(agent: LegalContractsAgent):
    """Characterization: empty ip_register + shared ip_privacy chunks fires
    unable_to_assess_json with a corpus_absent rationale in flags/citations.

    Elder Care shape from T3's live diagnostic: ip_privacy=4 (privacy BAAs)
    while ip_register is empty. Shared-pass chunk_count>=1 must not classify
    IP as retrieved_no_terms.
    """
    pass_chunk_counts = _zero_pass_chunk_counts()
    pass_chunk_counts["ip_privacy"] = 4
    merged = {
        **_EMPTY_MERGED,
        "privacy_security_register": [
            {"source_doc": "dropbox_hipaa_agreement.pdf", "obligation_type": "BAA"}
        ],
    }
    agent._assess_coverage_gaps(merged, pass_chunk_counts, None)

    assert "IP ownership, assignment, OSS" in agent._unable_to_assess_items
    assert "Data privacy / security obligations" not in agent._unable_to_assess_items
    gap_text = " ".join(agent._data_room_gaps)
    assert "ip: no IP Assignment / OSS Policy in corpus — corpus_absent" in gap_text
    assert "ip: chunks retrieved but no extractable terms" not in gap_text
    flag = next(f for f in agent._flags if f.metric == "corpus_absent")
    assert flag.value == "IP ownership, assignment, OSS"
    assert "corpus_absent" in flag.note
    cites = agent._citations_as_dicts()
    assert any("corpus_absent" in (c.get("raw_text") or "") for c in cites)
    assert any(row["item_id"] == "ip" for row in agent._recommended_diligence)


def test_ip_unable_to_assess_fallback_skipped_when_register_sourced(
    agent: LegalContractsAgent,
):
    """Falsifier for the corpus_absent guard: a sourced ip_register row must
    not enter _unable_to_assess_items and must not emit the corpus_absent
    flag. Mutation-checked: firing the corpus_absent branch before the
    assessed_predicate skip made this assertion fail; reverted after.
    """
    pass_chunk_counts = _zero_pass_chunk_counts()
    pass_chunk_counts["ip_privacy"] = 4
    merged = {
        **_EMPTY_MERGED,
        "ip_register": [
            {
                "ip_type": "assignment",
                "ownership_assignment_note": "work product assigns to company",
                "source_doc": "IP Assignment.pdf",
            }
        ],
    }
    agent._assess_coverage_gaps(merged, pass_chunk_counts, None)
    assert "IP ownership, assignment, OSS" not in agent._unable_to_assess_items
    assert all(f.metric != "corpus_absent" for f in agent._flags)
    assert all(row["item_id"] != "ip" for row in agent._recommended_diligence)
