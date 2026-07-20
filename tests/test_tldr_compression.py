"""Unit tests for TL;DR compression layer (formatters T1; compress/render in T2/T6)."""

from __future__ import annotations

import copy
import hashlib
import re
from pathlib import Path

import pytest
import yaml
from jinja2 import Environment, FileSystemLoader

from agents.orchestrator import formatters as fmt
from agents.orchestrator import tldr_quality_check as tqc
from agents.orchestrator.renderers import ReportRenderer, render_to_volume
from agents.orchestrator.tldr_compress import (
    RISK_DISPLAY_TITLES,
    _first_sentence,
    _resolve_section_tag_citations,
    _risk_display_title,
    _source_docs_for_section_tag,
    _truncate_table_cell,
    compress_for_tldr,
)

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "databricks" / "agents" / "orchestrator" / "templates"
_COMPRESSED_TEMPLATE = "tldr_one_pager_compressed.md.j2"
_LEGACY_TEMPLATE = "tldr_one_pager.md.j2"
_FULL_REPORT_TEMPLATE = "full_report.md.j2"
_ELDER_CARE_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "elder_care_bundle_compression.yaml"


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


def test_format_agent_flag_truncates_on_word_boundary():
    words = " ".join(["token"] * 80)
    flag = {"note": words}
    result = fmt.format_agent_flag(flag)
    assert len(result) <= 220
    assert result.endswith("...")
    assert not result[:-3].endswith("toke")
    assert " token" in result or result.startswith("token")


def test_headline_no_spurious_small_dollar_match():
    bundle = _minimal_bundle(
        executive={
            "in_one_line": "",
            "preliminary_view": {
                "strengths": [
                    "Revenue reached $2,773K in the latest period with strong unit economics.",
                ],
                "concerns": [],
                "closing": "",
            },
        },
    )
    tldr = compress_for_tldr(bundle)
    revenue_values = [
        m["value"] for m in tldr["headline"]["metrics"] if m["label"] == "Revenue"
    ]
    assert revenue_values
    assert all(v != "$2" for v in revenue_values)
    assert any("773" in v or "2,773" in v for v in revenue_values)


def test_headline_gross_margin_not_labeled_ebitda():
    bundle = _minimal_bundle(
        executive={
            "in_one_line": "",
            "preliminary_view": {
                "strengths": [
                    "43.4% gross margin on LTM revenue of $2,773K with 72% YoY growth.",
                ],
                "concerns": [],
                "closing": "",
            },
        },
    )
    tldr = compress_for_tldr(bundle)
    labels = {m["label"] for m in tldr["headline"]["metrics"]}
    assert "Gross Margin" in labels
    assert "EBITDA Margin" not in labels


def test_headline_margin_labels_disambiguate_blended_vs_segment():
    """T12: Elder Care strength bullet must not emit duplicate Gross Margin labels."""
    elder_care_strength = (
        "Pro forma adjusted gross margin of 43.4% (TTM Aug-2024) is above typical "
        "home care benchmarks; HHA/Live-In line carries 54.2% gross margin"
    )
    bundle = _minimal_bundle(
        executive={
            "in_one_line": "",
            "preliminary_view": {
                "strengths": [elder_care_strength],
                "concerns": [],
                "closing": "",
            },
        },
    )
    tldr = compress_for_tldr(bundle)
    margin_rows = [
        m for m in tldr["headline"]["metrics"] if m["label"].startswith("Gross Margin")
    ]
    assert len(margin_rows) == 2
    labels = [m["label"] for m in margin_rows]
    values = [m["value"] for m in margin_rows]
    assert labels.count("Gross Margin") == 0
    assert "Gross Margin (Blended)" in labels
    assert "Gross Margin (HHA/Live-In)" in labels
    assert "43.4%" in values
    assert "54.2%" in values


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


def test_format_diligence_entry_kpi_missing_dict():
    """KPI missing_kpis dict shape: management_question wins over kpi_name."""
    assert fmt.format_diligence_entry(
        {
            "kpi_name": "Census turnover",
            "management_question": "Provide monthly census turnover for trailing 12 months.",
        }
    ) == "Provide monthly census turnover for trailing 12 months."
    assert fmt.format_diligence_entry({"kpi_name": "Census turnover"}) == (
        "Provide supporting data for KPI: Census turnover"
    )


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


def test_compress_risks_omits_mitigant_from_projection():
    """v1.1.0: mitigants live only in tldr.mitigants_digest — not per-row in Top Risks."""
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
    row = tldr["risks"][0]
    assert "mitigant" not in row
    assert "mitigant_or_question" not in row
    assert set(row.keys()) == {"risk", "display_title", "severity", "evidence"}


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


# --- T9 in_one_line + preliminary rank-before-cap ---


def test_in_one_line_uses_sentence_boundary_not_char_160():
    long_strength = (
        "Strong revenue growth: clients expanded 376% over three years driven by "
        "acquisitions in New Jersey, Pennsylvania, and surrounding markets with "
        "improving unit economics and expanding payer mix across skilled nursing lines. "
        "Second sentence should not appear in the one-liner."
    )
    line = _first_sentence(long_strength)
    assert line
    assert line.endswith((".", "!", "?"))
    assert "Second sentence" not in line
    assert len(line) > 160


def test_in_one_line_omitted_when_duplicates_first_strength():
    strength = "LTM revenue of $21M with 18% revenue CAGR and 22% EBITDA margin."
    bundle = _minimal_bundle(
        executive={
            "in_one_line": "",
            "preliminary_view": {
                "strengths": [strength],
                "concerns": [],
                "closing": "",
            },
        },
    )
    tldr = compress_for_tldr(bundle)
    assert tldr["in_one_line"] == ""
    assert tldr["show_in_one_line"] is False
    md = _render_compressed_template(
        _mock_bundle(),
        {**_mock_tldr_view(), "in_one_line": "", "show_in_one_line": False},
    )
    assert "## In One Line" not in md


def test_concerns_rank_key_person_before_cap():
    concerns = [
        "Generic operational noise item alpha.",
        "Generic operational noise item beta.",
        "Generic operational noise item gamma.",
        "Generic operational noise item delta.",
        "Founder retains 92% equity — key-person dependency on CEO.",
        "Primary facility lease assignment requires landlord consent.",
        "Insurance gaps including workers' comp and cyber coverage.",
        "Generic operational noise item epsilon.",
    ]
    risks = [
        {
            "risk": "key_person",
            "severity": "critical",
            "evidence": "ev",
            "mitigant_or_question": "q",
            "source_agent": "business_model",
            "confidence": "medium",
            "fill_state": "filled_cited",
        },
        {
            "risk": "coc_consent",
            "severity": "critical",
            "evidence": "ev",
            "mitigant_or_question": "q",
            "source_agent": "legal",
            "confidence": "high",
            "fill_state": "filled_cited",
        },
    ]
    bundle = _minimal_bundle(
        executive={
            "in_one_line": "Standalone summary.",
            "preliminary_view": {"strengths": [], "concerns": concerns, "closing": ""},
        },
        risks=risks,
    )
    tldr = compress_for_tldr(bundle)
    assert len(tldr["concerns"]) == 3
    joined = " ".join(tldr["concerns"]).casefold()
    assert "founder" in joined
    assert "lease" in joined
    assert "insurance" in joined


def test_elder_care_concerns_surface_founder_lease_insurance(elder_care_bundle: dict):
    tldr = compress_for_tldr(elder_care_bundle)
    joined = " ".join(tldr["concerns"]).casefold()
    assert "founder" in joined
    assert "lease" in joined
    assert "insurance" in joined


# --- T10 risk display titles + table cell trim ---


def test_risk_display_title_maps_tier4_addback():
    assert _risk_display_title("tier4_addback") == "Undocumented Tier 4 addbacks"
    tldr = compress_for_tldr(
        _minimal_bundle(
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
    )
    assert tldr["risks"][0]["display_title"] == "Undocumented Tier 4 addbacks"


def test_risk_display_title_maps_open_legal_matter():
    assert _risk_display_title("open_legal_matter_other") == "Open legal matters"
    tldr = compress_for_tldr(
        _minimal_bundle(
            risks=[
                {
                    "risk": "open_legal_matter_other",
                    "severity": "critical",
                    "evidence": "Pending litigation",
                    "mitigant_or_question": "Review docket",
                    "source_agent": "legal",
                    "confidence": "high",
                    "fill_state": "filled_cited",
                }
            ],
        )
    )
    assert tldr["risks"][0]["display_title"] == "Open legal matters"


def test_rendered_risk_table_no_raw_metric_keys():
    risks = [
        {
            "risk": "tier4_addback",
            "severity": "material",
            "evidence": "x" * 200,
            "mitigant_or_question": "y" * 200,
            "source_agent": "quality_of_earnings",
            "confidence": "low",
            "fill_state": "filled_cited",
        },
        {
            "risk": "open_legal_matter_other",
            "severity": "critical",
            "evidence": "Open matter evidence",
            "mitigant_or_question": "Legal review",
            "source_agent": "legal",
            "confidence": "high",
            "fill_state": "filled_cited",
        },
    ]
    md = _render_compressed_tldr(_volume_test_bundle(risks=risks))
    risks_section = md.split("## Top Risks", maxsplit=1)[1].split("## ", maxsplit=1)[0]
    assert "tier4_addback" not in risks_section
    assert "open_legal_matter_other" not in risks_section
    assert "Undocumented Tier 4 addbacks" in risks_section
    assert "Open legal matters" in risks_section
    assert "Mitigant" not in risks_section
    assert "| Risk | Severity | Evidence |" in risks_section
    tldr_risks = compress_for_tldr(_minimal_bundle(risks=risks))["risks"]
    tier4 = next(r for r in tldr_risks if r["risk"] == "tier4_addback")
    assert len(tier4["evidence"]) <= 120
    assert tier4["evidence"].endswith("...")


def test_clean_risk_evidence_strips_dict_repr_before_render():
    """§2.5: dict-shaped Evidence must render as prose, not Python literal."""
    risks = [
        {
            "risk": "coc_consent",
            "severity": "critical",
            "evidence": "{'metric': 'coc_consent', 'value': 'required', 'note': 'CoC consent on MSAs.', 'source_doc': 'MSA'}",
            "mitigant_or_question": "Review schedule",
            "source_agent": "legal",
            "confidence": "high",
            "fill_state": "filled_cited",
        }
    ]
    md = _render_compressed_tldr(_volume_test_bundle(risks=risks))
    risks_section = md.split("## Top Risks", maxsplit=1)[1].split("## ", maxsplit=1)[0]
    assert "{'metric':" not in risks_section
    assert "CoC consent on MSAs." in risks_section


def test_kpi_stated_value_renders_without_dict_repr():
    """§2.5: KPI stated_value must not leak dict repr into the dashboard table."""
    stated_dict = {
        "type": "adverse_survey",
        "value": "2.1%",
        "period": "LTM",
    }
    bundle = _volume_test_bundle(
        kpi_dashboard=[
            {
                "metric_id": "adverse_survey",
                "display_name": "Adverse survey rate",
                "stated_value": fmt.format_kpi_value(stated_dict),
                "threshold": "< 5%",
                "flag": "pass",
                "confidence": "medium",
                "fill_state": "filled_cited",
            }
        ],
    )
    md = _render_compressed_tldr(bundle)
    kpi_section = md.split("## KPI Dashboard", maxsplit=1)[1].split("## ", maxsplit=1)[0]
    assert "{'type':" not in kpi_section
    assert "2.1%" in kpi_section


def test_risk_evidence_trim_preserves_dedupe_suffix():
    """Falsifier: truncate after merge must keep (+N related) suffix."""
    risks = [
        {
            "risk": "tier4_addback",
            "severity": "track",
            "evidence": " ".join(["word"] * 40),
            "mitigant_or_question": "mit",
            "source_agent": "quality_of_earnings",
            "confidence": "low",
            "fill_state": "filled_cited",
        }
        for _ in range(3)
    ]
    row = compress_for_tldr(_minimal_bundle(risks=risks))["risks"][0]
    assert "(+2 related)" in row["evidence"]
    assert len(row["evidence"]) <= 120


def test_truncate_table_cell_word_boundary():
    text = " ".join(["token"] * 30)
    result = _truncate_table_cell(text, max_len=120)
    assert len(result) <= 120
    assert result.endswith("...")
    assert not result[:-3].endswith("toke")


# --- T3 compressed template tests ---


def _render_compressed_template(bundle: dict, tldr: dict) -> str:
    env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=False)
    template = env.get_template(_COMPRESSED_TEMPLATE)
    return template.render(bundle=bundle, tldr=tldr)


def _mock_tldr_view() -> dict:
    return {
        "headline": {"metrics": [{"label": "LTM Revenue", "value": "$12M"}], "fallback_note": None},
        "in_one_line": "Regional home health provider with stable census.",
        "show_in_one_line": True,
        "strengths": ["Strength 1"],
        "concerns": ["Concern 1"],
        "business_snapshot": None,
        "business_snapshot_narrative": None,
        "mitigants_digest": None,
        "confidence_rationale": None,
        "preliminary_digest": None,
        "financial": {"rows": [], "observations": [], "show": False},
        "revenue_quality": {"lines": [], "show": False},
        "kpi": {"rows": [], "show": False},
        "legal": {
            "bullets": ["Sample legal bullet."],
            "show": True,
        },
        "qoe": {"summary": "", "bullets": [], "show": False},
        "risks": [
            {
                "risk": "tier4_addback",
                "display_title": RISK_DISPLAY_TITLES["tier4_addback"],
                "severity": "material",
                "evidence": "Undocumented addback",
                "mitigant": "Request support",
            }
        ],
        "questions": [
            {
                "category": "legal",
                "question": "Request and review Healthcare Referral Agreements",
                "priority": "high",
            }
        ],
        "open_items": ["Customer contracts for top 10 accounts"],
        "confidence_by_area": {"legal": "medium"},
        "show_confidence_table": True,
    }


def _mock_bundle() -> dict:
    return {
        "meta": {
            "company_name": "Elder Care",
            "vertical_overlay": "healthcare",
            "generated_at": "2026-06-30",
            "overall_confidence": "medium",
            "demo_mode": False,
            "disclaimer_text": "",
        },
        "executive": {"preliminary_view": {"closing": "Further diligence recommended."}},
    }


def _volume_test_bundle(**overrides: object) -> dict:
    bundle = _minimal_bundle(
        meta={
            "company_name": "Elder Care",
            "vertical_overlay": "healthcare",
            "generated_at": "2026-06-30",
            "overall_confidence": "medium",
            "demo_mode": False,
            "disclaimer_text": "",
            "agents_present": {},
            "render_state": "pending",
        },
        executive={
            "in_one_line": "Regional provider.",
            "preliminary_view": {
                "strengths": [],
                "concerns": [],
                "closing": "Further diligence recommended.",
            },
        },
    )
    bundle.update(overrides)
    return bundle


def test_compressed_template_bundle_refs_allowlisted_only():
    content = (_TEMPLATES_DIR / _COMPRESSED_TEMPLATE).read_text(encoding="utf-8")
    refs = set(re.findall(r"bundle\.[\w.]+", content))
    for ref in refs:
        assert ref.startswith("bundle.meta.") or ref == "bundle.executive.preliminary_view.closing", ref


def test_compressed_template_omits_hidden_sections_and_three_col_risks():
    md = _render_compressed_template(_mock_bundle(), _mock_tldr_view())
    risks_section = md.split("## Top Risks", maxsplit=1)[1].split("## ", maxsplit=1)[0]
    assert "| Risk | Severity | Evidence |" in risks_section
    assert "Mitigant" not in risks_section
    assert "Request support" not in md
    assert "mitigant_or_question" not in md
    assert "_No " not in md
    assert "No KPI dashboard rows available" not in md
    assert "## Financial Strip" not in md
    assert "## KPI Dashboard" not in md
    assert "## Revenue Quality" not in md
    assert "## Quality of Earnings" not in md


def test_compressed_template_hides_kpi_when_show_false_despite_stale_rows():
    """Falsifier: show=False must omit KPI block even if rows were left populated."""
    tldr = _mock_tldr_view()
    tldr["kpi"] = {
        "rows": [{"display_name": "NRR", "stated_value": "95%", "threshold": "", "flag": "", "confidence": ""}],
        "show": False,
    }
    md = _render_compressed_template(_mock_bundle(), tldr)
    assert "## KPI Dashboard" not in md


def test_one_pager_h1_display_text_executive_summary():
    """§2.5 rename: compressed and legacy one-pager H1 must read Executive Summary."""
    compressed_md = _render_compressed_template(_mock_bundle(), _mock_tldr_view())
    legacy_md = ReportRenderer().render(_volume_test_bundle(), _TEMPLATES_DIR / _LEGACY_TEMPLATE)
    for md in (compressed_md, legacy_md):
        h1 = md.splitlines()[0]
        assert h1.startswith("# ")
        assert "Executive Summary" in h1
        assert "TL;DR One-Pager" not in h1


def test_compress_optional_executive_narrative_keys_none_when_absent():
    """§2.5: new tldr narrative keys are None when bundle executive fields are absent."""
    tldr = compress_for_tldr(_minimal_bundle())
    assert tldr["business_snapshot_narrative"] is None
    assert tldr["mitigants_digest"] is None
    assert tldr["confidence_rationale"] is None
    assert tldr["preliminary_digest"] is None
    for key in ("legal_digest", "qoe_digest", "kpi_digest", "open_items_digest"):
        assert key not in tldr


def test_compress_optional_executive_narrative_keys_present_when_set():
    """§2.5: new tldr narrative keys mirror trimmed executive strings when present."""
    bundle = _minimal_bundle(
        executive={
            "in_one_line": "",
            "preliminary_view": {"strengths": [], "concerns": [], "closing": ""},
            "business_snapshot_narrative": "  Regional home health platform. ",
            "mitigants_digest": "Management diversified payer mix.",
            "confidence_rationale": "CIM supports financial trends.",
        },
    )
    tldr = compress_for_tldr(bundle)
    assert tldr["business_snapshot_narrative"] == "Regional home health platform."
    assert tldr["mitigants_digest"] == "Management diversified payer mix."
    assert tldr["confidence_rationale"] == "CIM supports financial trends."


def test_compress_whitespace_only_executive_narrative_keys_project_as_none():
    """Falsifier: blank/whitespace executive narrative must not render as empty strings."""
    bundle = _minimal_bundle(
        executive={
            "in_one_line": "",
            "preliminary_view": {"strengths": [], "concerns": [], "closing": ""},
            "business_snapshot_narrative": "   ",
            "mitigants_digest": "—",
            "confidence_rationale": "",
        },
    )
    tldr = compress_for_tldr(bundle)
    assert tldr["business_snapshot_narrative"] is None
    assert tldr["mitigants_digest"] is None
    assert tldr["confidence_rationale"] is None


def test_compress_deterministic_business_snapshot_unchanged_when_narrative_present():
    """§2.5: deterministic business_snapshot is independent of optional narrative fields."""
    framing = {
        "overview_bullets": ["Regional home health provider serving NJ and PA."],
        "revenue_model": {"tag": "", "quality_flag": "", "note": ""},
        "recent_changes": [],
        "thesis": {"bullets": [], "value_creation_levers": []},
    }
    revenue_quality = {
        "scale_narrative": "",
        "concentration": "Top three payers represent 62% of revenue.",
        "end_market_mix": "",
        "retention_notes": "",
    }
    baseline = compress_for_tldr(
        _minimal_bundle(company_framing=framing, revenue_quality=revenue_quality)
    )
    with_narrative = compress_for_tldr(
        _minimal_bundle(
            company_framing=framing,
            revenue_quality=revenue_quality,
            executive={
                "in_one_line": "",
                "preliminary_view": {"strengths": [], "concerns": [], "closing": ""},
                "business_snapshot_narrative": "LLM-rich business snapshot narrative.",
                "mitigants_digest": "Overall mitigation posture.",
                "confidence_rationale": "Confidence supported by filings.",
            },
        )
    )
    assert with_narrative["business_snapshot"] == baseline["business_snapshot"]
    assert with_narrative["business_snapshot_narrative"] == "LLM-rich business snapshot narrative."


def test_compressed_template_prefers_business_snapshot_narrative():
    """§2.5: Business Snapshot body prefers narrative over deterministic snapshot."""
    tldr = _mock_tldr_view()
    tldr["business_snapshot"] = "Deterministic snapshot from company framing."
    tldr["business_snapshot_narrative"] = "Synthesized narrative preferred in template."
    md = _render_compressed_template(_mock_bundle(), tldr)
    snapshot_section = md.split("## Business Snapshot", maxsplit=1)[1].split("## ", maxsplit=1)[0]
    assert "Synthesized narrative preferred in template." in snapshot_section
    assert "Deterministic snapshot from company framing." not in snapshot_section


def test_compressed_template_gates_mitigants_and_confidence_sections():
    """§2.5 / T15: Risk Mitigation and Analysis Notes render only when truthy."""
    tldr = _mock_tldr_view()
    tldr["mitigants_digest"] = None
    tldr["confidence_rationale"] = None
    md_absent = _render_compressed_template(_mock_bundle(), tldr)
    assert "## Risk Mitigation" not in md_absent
    assert "## Analysis Notes" not in md_absent
    assert "## Confidence & Data Gaps" not in md_absent
    assert "## Mitigants Digest" not in md_absent
    assert "## Confidence Rationale" not in md_absent

    tldr["mitigants_digest"] = "Payer diversification and branch footprint offset concentration."
    tldr["confidence_rationale"] = "Financial trends and legal flags are well supported."
    md_present = _render_compressed_template(_mock_bundle(), tldr)
    assert "## Risk Mitigation" in md_present
    assert "Payer diversification and branch footprint offset concentration." in md_present
    assert "## Analysis Notes" in md_present
    assert "Financial trends and legal flags are well supported." in md_present
    assert "## Confidence & Data Gaps" not in md_present
    assert "## Mitigants Digest" not in md_present
    assert "## Confidence Rationale" not in md_present


def test_analysis_notes_renders_below_confidence_by_area():
    """T15 §2Δ.4: Analysis Notes follows Confidence by Area and precedes Closing."""
    tldr = _mock_tldr_view()
    tldr["confidence_rationale"] = "CIM supports financial trends; referral agreements missing."
    md = _render_compressed_template(_mock_bundle(), tldr)
    conf_idx = md.index("## Confidence by Area")
    notes_idx = md.index("## Analysis Notes")
    closing_idx = md.index("## Closing")
    assert conf_idx < notes_idx < closing_idx


def test_legal_assessed_label_renders_coverage_percent():
    """T21 §2Δ.5: Legal compress and render no longer emit coverage % or section confidence."""
    tldr = compress_for_tldr(
        _minimal_bundle(
            legal={
                "assessed_count": 7,
                "checklist_total": 11,
                "section_confidence": "high",
                "top_flags": [],
                "top_gaps": [],
                "recommended_diligence": [],
            },
        )
    )
    assert "assessed_label" not in tldr["legal"]
    assert "section_confidence" not in tldr["legal"]
    md = _render_compressed_template(_mock_bundle(), {**_mock_tldr_view(), "legal": tldr["legal"]})
    assert "**Coverage:**" not in md
    assert "Section confidence" not in md
    assert "7 / 11" not in md


def test_qoe_tier_summary_not_truncated_mid_sentence():
    """T15 §2Δ.2: QoE tier_summary must not end with mid-sentence ellipsis."""
    long_summary = (
        "Tier 4 addbacks total $450K across owner discretionary expenses, "
        "related-party rent, and one-time legal settlements without third-party support."
    )
    tldr = compress_for_tldr(
        _minimal_bundle(qoe={"addback_pct_of_ebitda": "12%", "tier_summary": long_summary, "flags": []})
    )
    assert tldr["qoe"]["summary"] == long_summary
    assert not tldr["qoe"]["summary"].endswith("...")


def test_legal_bullets_use_full_note_without_mid_sentence_ellipsis():
    """T15 §2Δ.2: Legal bullets prefer full note text over format_agent_flag truncation."""
    long_note = (
        "Change-of-control consent is required on three master service agreements covering "
        "the majority of recurring revenue and must be obtained prior to closing."
    )
    tldr = compress_for_tldr(
        _minimal_bundle(
            legal={
                "assessed_count": 7,
                "checklist_total": 11,
                "section_confidence": "high",
                "top_flags": [{"metric": "coc_consent", "value": "required", "note": long_note}],
                "top_gaps": [],
                "recommended_diligence": [],
            },
        )
    )
    assert tldr["legal"]["bullets"] == [long_note]
    assert not tldr["legal"]["bullets"][0].endswith("...")


def test_kpi_compress_formats_value_and_template_drops_noisy_columns():
    """T15 §2Δ.2: KPI rows format stated_value; template is 2-col Metric | Value."""
    stated_dict = {"type": "adverse_survey", "value": "2.1%", "period": "LTM"}
    bundle = _volume_test_bundle(
        kpi_dashboard=[
            {
                "metric_id": "adverse_survey",
                "display_name": "Adverse survey rate",
                "stated_value": stated_dict,
                "threshold": "< 5%",
                "flag": "pass",
                "confidence": "medium",
                "fill_state": "filled_cited",
            }
        ],
    )
    tldr = compress_for_tldr(bundle)
    assert tldr["kpi"]["rows"][0]["stated_value"] == "2.1%"
    md = _render_compressed_tldr(bundle)
    kpi_section = md.split("## KPI Dashboard", maxsplit=1)[1].split("## ", maxsplit=1)[0]
    assert "| Metric | Value |" in kpi_section
    assert "Threshold" not in kpi_section
    assert "Confidence" not in kpi_section
    assert "2.1%" in kpi_section


# --- T17 digest lead-in projection + template tests ---

_DIGEST_KEYS = ("preliminary_digest",)


def test_compress_digest_keys_project_from_executive():
    """T21 §2Δ.3: only preliminary_digest projects; four retired digests are absent from tldr."""
    bundle = _minimal_bundle(
        executive={
            "in_one_line": "",
            "preliminary_view": {"strengths": [], "concerns": [], "closing": ""},
            "legal_digest": "  Seven of eleven contracts assessed. ",
            "qoe_digest": "Adjusted EBITDA holds after addbacks.",
            "kpi_digest": "Census and payer mix metrics are green.",
            "open_items_digest": "Cap table and insurance schedules remain open.",
            "preliminary_digest": "Attractive regional platform with manageable risks.",
        },
    )
    tldr = compress_for_tldr(bundle)
    assert tldr["preliminary_digest"] == "Attractive regional platform with manageable risks."
    for key in ("legal_digest", "qoe_digest", "kpi_digest", "open_items_digest"):
        assert key not in tldr


def test_compress_whitespace_only_digest_keys_project_as_none():
    """T21 falsifier: blank preliminary_digest must not render as an empty string."""
    bundle = _minimal_bundle(
        executive={
            "in_one_line": "",
            "preliminary_view": {"strengths": [], "concerns": [], "closing": ""},
            "legal_digest": "   ",
            "qoe_digest": "—",
            "kpi_digest": "",
            "open_items_digest": None,
            "preliminary_digest": "\t",
        },
    )
    tldr = compress_for_tldr(bundle)
    assert tldr["preliminary_digest"] is None
    for key in ("legal_digest", "qoe_digest", "kpi_digest", "open_items_digest"):
        assert key not in tldr


def test_compress_deterministic_sections_unchanged_when_digests_present():
    """§2Δ.5: digest lead-ins must not alter deterministic compress output."""
    bundle_base = _minimal_bundle(
        legal={
            "assessed_count": 7,
            "checklist_total": 11,
            "section_confidence": "high",
            "top_flags": [{"metric": "coc_consent", "value": "required", "note": "CoC required."}],
            "top_gaps": [],
            "recommended_diligence": [],
        },
        qoe={
            "addback_pct_of_ebitda": "12%",
            "tier_summary": "Tier mix stable after normalizing addbacks.",
            "flags": [],
        },
        kpi_dashboard=[
            {
                "metric_id": "census",
                "display_name": "Census",
                "stated_value": "1,200",
                "threshold": "",
                "flag": "pass",
                "confidence": "medium",
                "fill_state": "filled_cited",
            }
        ],
        data_room_gaps=[
            {
                "item": "Cap table missing",
                "priority": "high",
                "source_agent": "legal",
                "fill_state": "gap_correct",
            }
        ],
        executive={
            "in_one_line": "",
            "preliminary_view": {
                "strengths": ["Strong payer mix."],
                "concerns": ["Founder concentration."],
                "closing": "",
            },
        },
    )
    baseline = compress_for_tldr(bundle_base)
    bundle_with_digests = copy.deepcopy(bundle_base)
    bundle_with_digests["executive"].update(
        {
            "legal_digest": "Seven of eleven contracts assessed.",
            "qoe_digest": "EBITDA stable after adjustments.",
            "kpi_digest": "Census metrics are healthy.",
            "open_items_digest": "Cap table remains open.",
            "preliminary_digest": "Compelling regional platform.",
        }
    )
    with_digests = compress_for_tldr(bundle_with_digests)
    for key in (
        "legal",
        "qoe",
        "kpi",
        "open_items",
        "strengths",
        "concerns",
        "business_snapshot",
        "headline",
        "risks",
    ):
        assert with_digests[key] == baseline[key], key
    assert with_digests["preliminary_digest"] is not None
    for key in ("legal_digest", "qoe_digest", "kpi_digest", "open_items_digest"):
        assert key not in with_digests


def _section_body(md: str, header: str) -> str:
    return md.split(header, maxsplit=1)[1].split("\n## ", maxsplit=1)[0]


def test_compressed_template_digest_lead_ins_gate_and_preserve_detail():
    """T22 §2Δ.3: preliminary_digest renders above Strengths; per-section lead-ins and Legal badges gone."""
    tldr = _mock_tldr_view()
    tldr["kpi"] = {"rows": [{"display_name": "Census", "stated_value": "1,200"}], "show": True}
    tldr["qoe"] = {
        "summary": "Tier mix stable after adjustments.",
        "bullets": ["Four Tier 4 addbacks lack support."],
        "show": True,
    }
    tldr["preliminary_digest"] = "Compelling regional platform with manageable risks."

    md = _render_compressed_template(_mock_bundle(), tldr)

    legal_section = _section_body(md, "## Legal Snapshot")
    assert "Seven of eleven contracts assessed" not in legal_section
    assert "**Coverage:**" not in legal_section
    assert "- Sample legal bullet." in legal_section

    kpi_section = _section_body(md, "## KPI Dashboard")
    assert "Census metrics are healthy" not in kpi_section
    assert "| Census | 1,200 |" in kpi_section

    qoe_section = _section_body(md, "## Quality of Earnings")
    assert "EBITDA is stable" not in qoe_section
    assert "Four Tier 4 addbacks lack support." in qoe_section

    prelim_section = _section_body(md, "## Preliminary View")
    assert prelim_section.index("Compelling regional platform") < prelim_section.index("### Strengths")
    assert "- Strength 1" in prelim_section

    open_section = _section_body(md, "## Open Items / Data Requests")
    assert "Insurance schedules and cap table" not in open_section
    assert "- Customer contracts" in open_section


def test_compressed_template_digest_absent_sections_byte_identical():
    """T17 falsifier: absent digests must not alter gated section bodies."""
    tldr = _mock_tldr_view()
    tldr["kpi"] = {"rows": [{"display_name": "Census", "stated_value": "1,200"}], "show": True}
    tldr["qoe"] = {
        "summary": "Tier mix stable after adjustments.",
        "bullets": ["Four Tier 4 addbacks lack support."],
        "show": True,
    }
    for key in _DIGEST_KEYS:
        del tldr[key]
    baseline_md = _render_compressed_template(_mock_bundle(), tldr)

    tldr_with_none = copy.deepcopy(tldr)
    for key in _DIGEST_KEYS:
        tldr_with_none[key] = None
    assert _render_compressed_template(_mock_bundle(), tldr) == _render_compressed_template(
        _mock_bundle(), tldr_with_none
    )

    for header in (
        "## Preliminary View",
        "## KPI Dashboard",
        "## Legal Snapshot",
        "## Quality of Earnings",
        "## Open Items / Data Requests",
    ):
        section = _section_body(baseline_md, header)
        assert section.strip()
        assert "digest" not in section.casefold()


# --- T4 renderers mode switch tests ---


def test_report_renderer_legacy_context_bundle_only():
    renderer = ReportRenderer()
    md = renderer.render(_volume_test_bundle(), _TEMPLATES_DIR / "tldr_one_pager.md.j2")
    assert "Further diligence recommended." in md


def test_report_renderer_compressed_context_includes_tldr():
    renderer = ReportRenderer()
    md = renderer.render(
        _mock_bundle(),
        _TEMPLATES_DIR / _COMPRESSED_TEMPLATE,
        tldr=_mock_tldr_view(),
    )
    assert "Regional home health provider" in md
    assert "| Risk | Severity | Evidence |" in md
    assert "Mitigant" not in md.split("## Top Risks", maxsplit=1)[1].split("## ", maxsplit=1)[0]


def test_render_to_volume_full_report_bytes_independent_of_mode(monkeypatch, tmp_path):
    """K4: full_report.md path must not depend on TLDR_RENDER_MODE."""
    bundle = _volume_test_bundle()
    monkeypatch.setattr(
        "agents.orchestrator.renderers.reports_volume_dir",
        lambda _catalog, _company: str(tmp_path),
    )

    def _mode_param(key: str, default: str | None = None) -> str:
        assert key == "TLDR_RENDER_MODE"
        return default or "compressed"

    monkeypatch.setattr("agents.orchestrator.renderers.get_param", _mode_param)
    render_to_volume(bundle, "uc13_ale", "Elder Care")
    compressed_full = (tmp_path / "full_report.md").read_text(encoding="utf-8")

    monkeypatch.setattr(
        "agents.orchestrator.renderers.get_param",
        lambda key, default=None: "legacy" if key == "TLDR_RENDER_MODE" else (default or ""),
    )
    render_to_volume(bundle, "uc13_ale", "Elder Care")
    legacy_full = (tmp_path / "full_report.md").read_text(encoding="utf-8")

    assert compressed_full == legacy_full


def test_render_to_volume_compressed_uses_projection_template(monkeypatch, tmp_path):
    bundle = _volume_test_bundle()
    monkeypatch.setattr(
        "agents.orchestrator.renderers.reports_volume_dir",
        lambda _catalog, _company: str(tmp_path),
    )
    monkeypatch.setattr(
        "agents.orchestrator.renderers.get_param",
        lambda key, default=None: "compressed" if key == "TLDR_RENDER_MODE" else (default or ""),
    )
    render_to_volume(bundle, "uc13_ale", "Elder Care")
    md = (tmp_path / "tldr_one_pager.md").read_text(encoding="utf-8")
    assert "Headline financial metrics incomplete" in md
    assert "Regional provider." in md


def test_render_to_volume_legacy_uses_m1_template(monkeypatch, tmp_path):
    bundle = _volume_test_bundle()
    monkeypatch.setattr(
        "agents.orchestrator.renderers.reports_volume_dir",
        lambda _catalog, _company: str(tmp_path),
    )
    monkeypatch.setattr(
        "agents.orchestrator.renderers.get_param",
        lambda key, default=None: "legacy" if key == "TLDR_RENDER_MODE" else (default or ""),
    )
    render_to_volume(bundle, "uc13_ale", "Elder Care")
    md = (tmp_path / "tldr_one_pager.md").read_text(encoding="utf-8")
    assert "Further diligence recommended." in md
    assert "Headline financial metrics incomplete" not in md


def test_render_to_volume_legacy_skips_compress_for_tldr(monkeypatch, tmp_path):
    """Falsifier: legacy mode must not invoke compress_for_tldr."""
    bundle = _volume_test_bundle()

    def _fail_compress(_bundle: dict) -> dict:
        raise AssertionError("compress_for_tldr must not run in legacy mode")

    monkeypatch.setattr("agents.orchestrator.renderers.compress_for_tldr", _fail_compress)
    monkeypatch.setattr(
        "agents.orchestrator.renderers.reports_volume_dir",
        lambda _catalog, _company: str(tmp_path),
    )
    monkeypatch.setattr(
        "agents.orchestrator.renderers.get_param",
        lambda key, default=None: "legacy" if key == "TLDR_RENDER_MODE" else (default or ""),
    )
    render_to_volume(bundle, "uc13_ale", "Elder Care")


def _write_tldr_md(vol_dir: Path, body: str) -> None:
    vol_dir.mkdir(parents=True, exist_ok=True)
    (vol_dir / "tldr_one_pager.md").write_text(body, encoding="utf-8")


def test_tldr_quality_check_passes_clean_fixture(tmp_path, monkeypatch, capsys):
    vol_dir = tmp_path / "reports" / "Elder_Care"
    _write_tldr_md(vol_dir, "# TL;DR\n\nClean stakeholder summary with no leaks.\n")
    monkeypatch.setattr(tqc, "reports_volume_dir", lambda _c, _n: str(vol_dir))

    exit_code = tqc.run(company_name="Elder Care", catalog="uc13_ale")

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "TLDR quality PASS" in out
    assert "WARN" not in out.split("TLDR quality PASS")[0].split("TLDR quality check")[-1]


def test_tldr_quality_check_warns_but_exits_zero_on_word_count(tmp_path, monkeypatch, capsys):
    """Falsifier: soft gates must not hard-fail when word count exceeds 1,200."""
    vol_dir = tmp_path / "reports" / "Elder_Care"
    body = " ".join(["word"] * 1201)
    _write_tldr_md(vol_dir, body)
    monkeypatch.setattr(tqc, "reports_volume_dir", lambda _c, _n: str(vol_dir))

    exit_code = tqc.run(company_name="Elder Care", catalog="uc13_ale")

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "word_count" in out
    assert "WARN" in out
    assert "TLDR quality WARN" in out


def test_tldr_quality_check_warns_on_dict_leak(tmp_path, monkeypatch, capsys):
    vol_dir = tmp_path / "reports" / "Elder_Care"
    _write_tldr_md(vol_dir, "Flag row leaked as {'metric': 'coc_consent'} in body.\n")
    monkeypatch.setattr(tqc, "reports_volume_dir", lambda _c, _n: str(vol_dir))

    exit_code = tqc.run(company_name="Elder Care", catalog="uc13_ale")

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "dict_leak" in out
    assert "WARN" in out


def test_tldr_quality_check_warns_on_operator_gap_substring(tmp_path, monkeypatch, capsys):
    vol_dir = tmp_path / "reports" / "Elder_Care"
    _write_tldr_md(vol_dir, "Legal workstream: LLM response was truncated at token limit.\n")
    monkeypatch.setattr(tqc, "reports_volume_dir", lambda _c, _n: str(vol_dir))

    exit_code = tqc.run(company_name="Elder Care", catalog="uc13_ale")

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "operator_gaps" in out
    assert "WARN" in out


def test_tldr_quality_check_exits_one_when_file_missing(tmp_path, monkeypatch, capsys):
    vol_dir = tmp_path / "reports" / "Elder_Care"
    vol_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(tqc, "reports_volume_dir", lambda _c, _n: str(vol_dir))

    exit_code = tqc.run(company_name="Elder Care", catalog="uc13_ale")

    assert exit_code == 1
    assert "file not found" in capsys.readouterr().out


def _headline_table_md(*rows: tuple[str, str]) -> str:
    lines = [
        "# TL;DR",
        "",
        "| Metric | Value |",
        "|--------|-------|",
    ]
    lines.extend(f"| {label} | {value} |" for label, value in rows)
    lines.append("---")
    return "\n".join(lines) + "\n"


def _risk_table_md(risk_cell: str) -> str:
    return (
        "# TL;DR\n\n"
        "## Top Risks\n\n"
        "| Risk | Severity | Evidence | Mitigant |\n"
        "|------|----------|----------|----------|\n"
        f"| {risk_cell} | critical | sample evidence | sample mitigant |\n"
        "---\n"
    )


def test_tldr_quality_check_warns_on_duplicate_headline_labels(tmp_path, monkeypatch, capsys):
    vol_dir = tmp_path / "reports" / "Elder_Care"
    body = _headline_table_md(
        ("Revenue CAGR", "376%"),
        ("Gross Margin", "43.4%"),
        ("Gross Margin", "54.2%"),
    )
    _write_tldr_md(vol_dir, body)
    monkeypatch.setattr(tqc, "reports_volume_dir", lambda _c, _n: str(vol_dir))

    exit_code = tqc.run(company_name="Elder Care", catalog="uc13_ale")

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "headline_duplicate_labels" in out
    assert "WARN" in out
    assert "Gross Margin" in out


def test_tldr_quality_check_passes_post_t12_headline(tmp_path, monkeypatch, capsys, elder_care_bundle):
    vol_dir = tmp_path / "reports" / "Elder_Care"
    _write_tldr_md(vol_dir, _render_compressed_tldr(elder_care_bundle))
    monkeypatch.setattr(tqc, "reports_volume_dir", lambda _c, _n: str(vol_dir))

    exit_code = tqc.run(company_name="Elder Care", catalog="uc13_ale")

    assert exit_code == 0
    out = capsys.readouterr().out
    assert re.search(r"headline_duplicate_labels\s*\|\s*PASS", out)


def test_tldr_quality_check_warns_on_raw_risk_metric_key(tmp_path, monkeypatch, capsys):
    vol_dir = tmp_path / "reports" / "Elder_Care"
    _write_tldr_md(vol_dir, _risk_table_md("tier4_addback"))
    monkeypatch.setattr(tqc, "reports_volume_dir", lambda _c, _n: str(vol_dir))

    exit_code = tqc.run(company_name="Elder Care", catalog="uc13_ale")

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "risk_raw_metric_keys" in out
    assert "WARN" in out


def test_tldr_quality_check_warns_on_spurious_headline_dollar(tmp_path, monkeypatch, capsys):
    vol_dir = tmp_path / "reports" / "Elder_Care"
    body = _headline_table_md(("Revenue", "$2"), ("Revenue CAGR", "72%"))
    _write_tldr_md(vol_dir, body)
    monkeypatch.setattr(tqc, "reports_volume_dir", lambda _c, _n: str(vol_dir))

    exit_code = tqc.run(company_name="Elder Care", catalog="uc13_ale")

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "headline_spurious_dollar" in out
    assert "WARN" in out


def test_tldr_quality_check_spurious_dollar_scoped_to_headline(tmp_path, monkeypatch, capsys):
    """Falsifier: QoE prose dollars must not trip headline_spurious_dollar."""
    vol_dir = tmp_path / "reports" / "Elder_Care"
    body = (
        _headline_table_md(("Revenue", "$21M"), ("Revenue CAGR", "22%"))
        + "\n## Quality of Earnings\n\n"
        "The reported EBITDA for 2023 is $2,773.\n"
    )
    _write_tldr_md(vol_dir, body)
    monkeypatch.setattr(tqc, "reports_volume_dir", lambda _c, _n: str(vol_dir))

    exit_code = tqc.run(company_name="Elder Care", catalog="uc13_ale")

    assert exit_code == 0
    out = capsys.readouterr().out
    assert re.search(r"headline_spurious_dollar\s*\|\s*PASS", out)


# --- T6 §7.1 integration tests (Elder Care synthetic fixture) ---


def _load_elder_care_fixture() -> dict:
    with _ELDER_CARE_FIXTURE.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _render_compressed_tldr(bundle: dict) -> str:
    tldr = compress_for_tldr(bundle)
    return ReportRenderer().render(
        bundle,
        _TEMPLATES_DIR / _COMPRESSED_TEMPLATE,
        tldr=tldr,
    )


def _word_count(text: str) -> int:
    return len(text.split())


def _risk_table_tier4_rows(md: str) -> int:
    in_risks = False
    count = 0
    display = RISK_DISPLAY_TITLES["tier4_addback"]
    for line in md.splitlines():
        if line.strip() == "## Top Risks":
            in_risks = True
            continue
        if in_risks and line.startswith("## "):
            break
        if in_risks and line.startswith(f"| {display}"):
            count += 1
    return count


@pytest.fixture
def elder_care_bundle() -> dict:
    return _load_elder_care_fixture()


def test_compress_word_budget(elder_care_bundle: dict):
    md = _render_compressed_tldr(elder_care_bundle)
    assert _word_count(md) <= 1200


def test_no_raw_dicts_in_render(elder_care_bundle: dict):
    md = _render_compressed_tldr(elder_care_bundle)
    assert "{'metric':" not in md


def test_operator_gaps_excluded(elder_care_bundle: dict):
    md = _render_compressed_tldr(elder_care_bundle)
    assert "LLM response was truncated" not in md


def test_risk_dedupe_tier4(elder_care_bundle: dict):
    md = _render_compressed_tldr(elder_care_bundle)
    assert _risk_table_tier4_rows(md) <= 2


def test_empty_financial_omitted(elder_care_bundle: dict):
    md = _render_compressed_tldr(elder_care_bundle)
    assert "## Financial Strip" not in md


def test_flag_formatting(elder_care_bundle: dict):
    md = _render_compressed_tldr(elder_care_bundle)
    assert "Change-of-control consent required on three MSAs." in md
    assert "{'metric':" not in md


def test_diligence_question_formatting(elder_care_bundle: dict):
    md = _render_compressed_tldr(elder_care_bundle)
    assert "Request and review Healthcare Referral Agreements" in md


def test_legacy_mode_unchanged(elder_care_bundle: dict, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "agents.orchestrator.renderers.reports_volume_dir",
        lambda _catalog, _company: str(tmp_path),
    )
    monkeypatch.setattr(
        "agents.orchestrator.renderers.get_param",
        lambda key, default=None: "legacy" if key == "TLDR_RENDER_MODE" else (default or ""),
    )
    render_to_volume(elder_care_bundle, "uc13_ale", "Elder Care")
    legacy_md = (tmp_path / "tldr_one_pager.md").read_text(encoding="utf-8")
    direct_md = ReportRenderer().render(
        elder_care_bundle,
        _TEMPLATES_DIR / _LEGACY_TEMPLATE,
    )
    assert legacy_md == direct_md
    assert "## Headline Metrics" in legacy_md
    assert "Headline financial metrics incomplete" not in legacy_md


# Baseline captured from full_report.md.j2 render of elder_care_bundle_compression.yaml (T6).
_FULL_REPORT_BASELINE_SHA256 = (
    "5eb12eb0b43f966d26666803bb066d183aed0693537b3c18ef3499f264449567"
)


def test_full_report_unaffected(elder_care_bundle: dict):
    renderer = ReportRenderer()
    md = renderer.render(elder_care_bundle, _TEMPLATES_DIR / _FULL_REPORT_TEMPLATE)
    digest = hashlib.sha256(md.encode("utf-8")).hexdigest()
    assert digest == _FULL_REPORT_BASELINE_SHA256


# --- T21 citation resolver + digest projection drop + Legal badge drop ---

_DROPPED_DIGEST_KEYS = ("legal_digest", "qoe_digest", "kpi_digest", "open_items_digest")


def test_compress_drops_v1_2_digest_projection_keys():
    """T21 §2Δ.3: four retired digests are no longer projected into the tldr view."""
    bundle = _minimal_bundle(
        executive={
            "in_one_line": "",
            "preliminary_view": {"strengths": [], "concerns": [], "closing": ""},
            "legal_digest": "Seven of eleven contracts assessed.",
            "qoe_digest": "Adjusted EBITDA holds after addbacks.",
            "kpi_digest": "Census metrics are healthy.",
            "open_items_digest": "Cap table remains open.",
            "preliminary_digest": "Compelling regional platform. [Legal Snapshot]",
        },
    )
    tldr = compress_for_tldr(bundle)
    for key in _DROPPED_DIGEST_KEYS:
        assert key not in tldr


def test_compress_legal_drops_coverage_and_section_confidence():
    """T21 §2Δ.5: Legal compress no longer emits assessed_label or section_confidence."""
    tldr = compress_for_tldr(
        _minimal_bundle(
            legal={
                "assessed_count": 7,
                "checklist_total": 11,
                "section_confidence": "high",
                "top_flags": [{"metric": "coc_consent", "value": "required", "note": "CoC required."}],
                "top_gaps": [],
                "recommended_diligence": [],
            },
        )
    )
    assert "assessed_label" not in tldr["legal"]
    assert "section_confidence" not in tldr["legal"]
    assert tldr["legal"]["bullets"] == ["CoC required."]


def test_resolve_legal_snapshot_tag_to_section_source_docs():
    """T21 §2Δ.4: tagged Legal Snapshot resolves to real top_flags source_doc refs."""
    bundle = _minimal_bundle(
        legal={
            "assessed_count": 2,
            "checklist_total": 11,
            "section_confidence": "high",
            "top_flags": [
                {"metric": "coc_consent", "value": "required", "source_doc": "MSA Schedule B"},
                {"metric": "open_legal_matter", "value": "pending", "source_doc": "Legal memo"},
            ],
            "top_gaps": [],
            "recommended_diligence": [],
        },
    )
    digest = "Change-of-control risk is material. [Legal Snapshot]"
    resolved = _resolve_section_tag_citations(digest, bundle)
    assert resolved == "Change-of-control risk is material. [Legal Snapshot: MSA Schedule B, Legal memo]"


def test_resolve_tag_without_source_doc_keeps_bare_tag():
    """T21 §2Δ.4: sections lacking source_doc keep the bare section tag."""
    bundle = _minimal_bundle(
        company_framing={
            "overview_bullets": ["Regional home health provider."],
            "revenue_model": {"tag": "", "quality_flag": "", "note": ""},
            "recent_changes": [],
            "thesis": {"bullets": [], "value_creation_levers": []},
        },
    )
    digest = "Platform overview is attractive. [Business Snapshot]"
    assert _resolve_section_tag_citations(digest, bundle) == digest


def test_resolver_never_emits_source_doc_from_other_sections():
    """T21 falsifier: resolver must not cross-section cite — only the tagged section's refs."""
    bundle = _minimal_bundle(
        legal={
            "assessed_count": 1,
            "checklist_total": 11,
            "section_confidence": "high",
            "top_flags": [{"metric": "coc_consent", "value": "required", "source_doc": "MSA Schedule B"}],
            "top_gaps": [],
            "recommended_diligence": [],
        },
        qoe={
            "addback_pct_of_ebitda": "12%",
            "tier_summary": "Tier mix stable.",
            "flags": [{"metric": "tier4_addback", "value": "0", "source_doc": "CIM p.45"}],
        },
    )
    digest = "Addbacks may not survive diligence. [Quality of Earnings]"
    resolved = _resolve_section_tag_citations(digest, bundle)
    assert "MSA Schedule B" not in resolved
    assert resolved == "Addbacks may not survive diligence. [Quality of Earnings: CIM p.45]"


def test_compress_preliminary_digest_applies_citation_resolver():
    """T21: compress_for_tldr projects preliminary_digest with resolved inline citations."""
    bundle = _minimal_bundle(
        executive={
            "in_one_line": "",
            "preliminary_view": {"strengths": [], "concerns": [], "closing": ""},
            "preliminary_digest": "Contracts need consent. [Legal Snapshot]",
        },
        legal={
            "assessed_count": 1,
            "checklist_total": 11,
            "section_confidence": "high",
            "top_flags": [{"metric": "coc_consent", "value": "required", "source_doc": "MSA Schedule B"}],
            "top_gaps": [],
            "recommended_diligence": [],
        },
    )
    tldr = compress_for_tldr(bundle)
    assert tldr["preliminary_digest"] == "Contracts need consent. [Legal Snapshot: MSA Schedule B]"


def test_source_docs_for_section_tag_matches_t20_vocabulary():
    """T21 kill criterion: section tag vocabulary matches T20 fixed set."""
    bundle = _minimal_bundle()
    for tag in (
        "Business Snapshot",
        "Financial Strip",
        "Revenue Quality",
        "KPI Dashboard",
        "Legal Snapshot",
        "Quality of Earnings",
        "Top Risks",
        "Confidence by Area",
    ):
        assert _source_docs_for_section_tag(tag, bundle) == []
    assert _source_docs_for_section_tag("Not A Real Tag", bundle) == []
