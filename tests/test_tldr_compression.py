"""Unit tests for TL;DR compression layer (formatters T1; compress/render in T2/T6)."""

from __future__ import annotations

import copy

import pytest

from agents.orchestrator import formatters as fmt
from agents.orchestrator.tldr_compress import compress_for_tldr


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


# --- T2 compress_for_tldr unit tests ---


def _minimal_bundle(**overrides: object) -> dict:
    base: dict = {
        "headline_metrics": {
            "ltm_revenue": "",
            "ltm_ebitda": "",
            "ltm_ebitda_margin_pct": "",
            "revenue_cagr": "",
            "enterprise_value_indicated": None,
            "rule_of_40": None,
        },
        "executive": {
            "in_one_line": "",
            "preliminary_view": {"strengths": [], "concerns": [], "closing": ""},
        },
        "company_framing": {
            "overview_bullets": [],
            "revenue_model": {"tag": "", "quality_flag": "", "note": ""},
            "recent_changes": [],
            "thesis": {"bullets": [], "value_creation_levers": []},
        },
        "financials": {"table_rows": [], "observations": [], "geographic_mix": []},
        "revenue_quality": {
            "scale_narrative": "",
            "concentration": "",
            "end_market_mix": "",
            "retention_notes": "",
        },
        "kpi_dashboard": [],
        "legal": {
            "assessed_count": 0,
            "checklist_total": 11,
            "section_confidence": "low",
            "top_flags": [],
            "top_gaps": [],
            "recommended_diligence": [],
        },
        "qoe": {"addback_pct_of_ebitda": "", "tier_summary": "", "flags": []},
        "risks": [],
        "diligence_questions": [],
        "data_room_gaps": [],
        "confidence_by_area": {},
    }
    base.update(overrides)
    return base


def test_compress_for_tldr_does_not_mutate_input_bundle():
    bundle = _minimal_bundle(
        risks=[
            {
                "risk": "tier4_addback",
                "severity": "material",
                "evidence": "ev",
                "mitigant_or_question": "q",
                "source_agent": "quality_of_earnings",
                "confidence": "low",
                "fill_state": "filled_cited",
            }
        ],
    )
    snapshot = copy.deepcopy(bundle)
    compress_for_tldr(bundle)
    assert bundle == snapshot


def test_risk_dedupe_tier4_collapses_to_one_row():
    risks = [
        {
            "risk": "tier4_addback",
            "severity": "track",
            "evidence": f"ev{i}",
            "mitigant_or_question": f"mit{i}",
            "source_agent": "quality_of_earnings",
            "confidence": "low",
            "fill_state": "filled_cited",
        }
        for i in range(9)
    ]
    risks.append(
        {
            "risk": "coc_consent",
            "severity": "critical",
            "evidence": "legal ev",
            "mitigant_or_question": "legal mit",
            "source_agent": "legal",
            "confidence": "high",
            "fill_state": "filled_cited",
        }
    )
    tldr = compress_for_tldr(_minimal_bundle(risks=risks))
    tier4_rows = [r for r in tldr["risks"] if r["risk"] == "tier4_addback"]
    assert len(tier4_rows) == 1
    assert "(+8 related)" in tier4_rows[0]["evidence"]
    assert len(tldr["risks"]) <= 5


def test_risk_mitigant_mapped_from_mitigant_or_question():
    tldr = compress_for_tldr(
        _minimal_bundle(
            risks=[
                {
                    "risk": "coc_consent",
                    "severity": "critical",
                    "evidence": "ev",
                    "mitigant_or_question": "Obtain consent schedule",
                    "source_agent": "legal",
                    "confidence": "high",
                    "fill_state": "filled_cited",
                }
            ],
        )
    )
    assert tldr["risks"][0]["mitigant"] == "Obtain consent schedule"
    assert "mitigant_or_question" not in tldr["risks"][0]


def test_operator_gaps_excluded_from_open_items():
    gaps = [
        {
            "item": "LLM response was truncated at 8192 tokens",
            "priority": "high",
            "source_agent": "financial_trends",
            "fill_state": "filled_cited",
        },
        {
            "item": "Customer contracts missing from data room",
            "priority": "high",
            "source_agent": "legal",
            "fill_state": "gap_correct",
        },
        {
            "item": "Change-of-control provisions not provided",
            "priority": "high",
            "source_agent": "legal",
            "fill_state": "gap_correct",
        },
    ]
    tldr = compress_for_tldr(_minimal_bundle(data_room_gaps=gaps))
    assert len(tldr["open_items"]) == 2
    assert all("LLM response" not in item for item in tldr["open_items"])


def test_open_items_cap_at_five_high_priority_seller_gaps():
    gaps = [
        {
            "item": f"Seller gap {i}",
            "priority": "high",
            "source_agent": "legal",
            "fill_state": "gap_correct",
        }
        for i in range(8)
    ]
    tldr = compress_for_tldr(_minimal_bundle(data_room_gaps=gaps))
    assert len(tldr["open_items"]) == 5


def test_headline_fallback_extracts_metrics_from_preliminary_view():
    bundle = _minimal_bundle(
        executive={
            "in_one_line": "",
            "preliminary_view": {
                "strengths": [
                    "LTM revenue of $21M with 18% revenue CAGR and 22% EBITDA margin.",
                ],
                "concerns": [],
                "closing": "",
            },
        },
    )
    tldr = compress_for_tldr(bundle)
    assert len(tldr["headline"]["metrics"]) >= 2
    assert tldr["headline"]["fallback_note"] is None
    labels = {m["label"] for m in tldr["headline"]["metrics"]}
    assert "Revenue" in labels


def test_headline_fallback_note_when_fewer_than_two_metrics():
    tldr = compress_for_tldr(_minimal_bundle())
    assert tldr["headline"]["fallback_note"] is not None
    assert len(tldr["headline"]["metrics"]) < 2


def test_qoe_collapse_tier4_addbacks():
    flags = [
        {
            "metric": "tier4_addback",
            "value": "0",
            "note": f"Addback {i}",
            "source_doc": "CIM",
        }
        for i in range(5)
    ]
    tldr = compress_for_tldr(
        _minimal_bundle(qoe={"addback_pct_of_ebitda": "10%", "tier_summary": "Summary", "flags": flags})
    )
    assert len(tldr["qoe"]["bullets"]) == 1
    assert "5 Tier 4 addbacks" in tldr["qoe"]["bullets"][0]


def test_risk_dedupe_keeps_most_severe_row_in_group():
    tldr = compress_for_tldr(
        _minimal_bundle(
            risks=[
                {
                    "risk": "tier4_addback",
                    "severity": "track",
                    "evidence": "weak",
                    "mitigant_or_question": "a",
                    "source_agent": "quality_of_earnings",
                    "confidence": "low",
                    "fill_state": "filled_cited",
                },
                {
                    "risk": "tier4_addback",
                    "severity": "critical",
                    "evidence": "strong",
                    "mitigant_or_question": "b",
                    "source_agent": "quality_of_earnings",
                    "confidence": "low",
                    "fill_state": "filled_cited",
                },
            ],
        )
    )
    row = next(r for r in tldr["risks"] if r["risk"] == "tier4_addback")
    assert row["severity"] == "critical"
    assert row["evidence"].startswith("strong")
    assert "(+1 related)" in row["evidence"]


def test_empty_financial_rows_omitted():
    rows = [
        {
            "year": "Jan 2024",
            "revenue": "",
            "gross_profit": "",
            "gross_margin_pct": "",
            "ebitda": "",
            "ebitda_margin_pct": "",
        }
        for _ in range(6)
    ]
    tldr = compress_for_tldr(
        _minimal_bundle(financials={"table_rows": rows, "observations": [], "geographic_mix": []})
    )
    assert tldr["financial"]["show"] is False
    assert tldr["financial"]["rows"] == []
