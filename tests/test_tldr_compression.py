"""Unit tests for TL;DR compression layer (formatters T1; compress/render in T2/T6)."""

from __future__ import annotations

import pytest

from agents.orchestrator import formatters as fmt


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Customer Contracts!", "customer contracts"),
        ("  Foo   Bar  ", "foo bar"),
        ("Same-Gap", "samegap"),
    ],
)
def test_normalize_gap_case_and_punctuation_insensitive(raw: str, expected: str):
    assert fmt.normalize_gap(raw) == expected


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        ("LLM response was truncated at 8192 tokens", True),
        ("Check TOKEN LIMIT configuration", True),
        ("Partial JSON was recovered from agent output", True),
        ("Retrieval coverage below threshold for legal", True),
        ("Please re-run the agent after fixing prompt", True),
        ("Customer contracts missing from data room", False),
        ("Request change-of-control provisions", False),
    ],
)
def test_is_operator_gap_substring_classifier(item: str, expected: bool):
    assert fmt.is_operator_gap(item) is expected


def test_format_agent_flag_prefers_note():
    flag = {
        "metric": "tier4_addback",
        "value": "0",
        "note": "Undocumented addback unlikely to survive QoE.",
        "source_doc": "CIM p.45",
    }
    assert fmt.format_agent_flag(flag) == "Undocumented addback unlikely to survive QoE."


def test_format_agent_flag_composes_when_note_missing():
    flag = {"metric": "coc_consent", "value": "required", "source_doc": "MSA §12"}
    assert fmt.format_agent_flag(flag) == "coc_consent: required — MSA §12"


def test_format_agent_flag_never_returns_dict_repr():
    flag = {"metric": "open_legal_matter", "value": "pending"}
    result = fmt.format_agent_flag(flag)
    assert not result.startswith("{")
    assert "dict" not in result


def test_format_agent_flag_truncates_at_220_chars():
    flag = {"note": "x" * 250}
    result = fmt.format_agent_flag(flag)
    assert len(result) == 220
    assert result.endswith("...")


def test_format_diligence_entry_dict_doc_type():
    entry = {"doc_type": "Healthcare Referral Agreements", "item_id": "healthcare_referral"}
    assert fmt.format_diligence_entry(entry) == "Request and review Healthcare Referral Agreements"


def test_format_diligence_entry_elder_care_legacy_dict_repr():
    """Kill criterion: dict-shaped legal question must not render as Python literal."""
    raw = "{'doc_type': 'Healthcare Referral Agreements', 'item_id': 'healthcare_referral'}"
    assert fmt.format_diligence_entry(raw) == "Request and review Healthcare Referral Agreements"


def test_format_diligence_entry_plain_string_passthrough():
    assert fmt.format_diligence_entry("Obtain customer concentration schedule?") == (
        "Obtain customer concentration schedule?"
    )


def test_format_diligence_entry_malformed_dict_literal_returns_stripped_string():
    """Falsifier: invalid literal_eval input must not raise or emit dict repr."""
    raw = "{not a valid dict"
    assert fmt.format_diligence_entry(raw) == raw
