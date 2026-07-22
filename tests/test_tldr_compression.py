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
    _resolve_section_tag_citations,
    _source_docs_for_section_tag,
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


def test_compress_for_tldr_omits_retired_projection_keys():
    """Rev3: in_one_line, strengths/concerns, and risks are no longer projected."""
    bundle = _minimal_bundle(
        executive={
            "in_one_line": "Standalone hook.",
            "preliminary_view": {
                "strengths": ["Strength A."],
                "concerns": ["Concern B."],
                "closing": "",
            },
            "preliminary_digest": "Compelling regional platform.",
        },
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
    tldr = compress_for_tldr(bundle)
    for key in ("in_one_line", "show_in_one_line", "strengths", "concerns", "risks"):
        assert key not in tldr
    assert tldr["preliminary_digest"] == "Compelling regional platform."


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


# --- Rev3 Preliminary View collapse + retired sections ---


def test_compressed_template_omits_in_one_line_section():
    tldr = _mock_tldr_view()
    tldr["preliminary_digest"] = "Hook sentence carried by preliminary digest."
    md = _render_compressed_template(_mock_bundle(), tldr)
    assert "## In One Line" not in md
    assert "## Preliminary View" in md
    assert "Hook sentence carried by preliminary digest." in md


def test_compressed_template_preliminary_view_digest_only():
    """Rev3 Flag 1: Strengths/Concerns subsections never render."""
    tldr = _mock_tldr_view()
    tldr["preliminary_digest"] = "Compelling regional platform."
    md = _render_compressed_template(_mock_bundle(), tldr)
    prelim_section = _section_body(md, "## Preliminary View")
    assert "Compelling regional platform." in prelim_section
    assert "### Strengths" not in prelim_section
    assert "### Concerns" not in prelim_section


def test_compressed_template_omits_top_risks_section():
    md = _render_compressed_tldr(
        _volume_test_bundle(
            risks=[
                {
                    "risk": "tier4_addback",
                    "severity": "material",
                    "evidence": "evidence text",
                    "mitigant_or_question": "q",
                    "source_agent": "quality_of_earnings",
                    "confidence": "low",
                    "fill_state": "filled_cited",
                }
            ],
        )
    )
    assert "## Top Risks" not in md
    assert "| Risk | Severity | Evidence |" not in md


def test_revenue_quality_kpi_fold_survives_caregiver_utilization_with_cap_six():
    """T5: KPI substance folds into revenue_quality.lines with total cap of 6."""
    bundle = _volume_test_bundle(
        revenue_quality={
            "scale_narrative": "Scale line 1",
            "concentration": "Scale line 2",
            "end_market_mix": "Scale line 3",
            "retention_notes": "Scale line 4",
        },
        kpi_dashboard=[
            {
                "metric_id": "caregiver_utilization",
                "display_name": "Caregiver utilization",
                "stated_value": "78%",
                "threshold": "",
                "flag": "pass",
                "confidence": "medium",
                "fill_state": "filled_cited",
            },
            {
                "metric_id": "adverse_survey",
                "display_name": "Adverse survey rate",
                "stated_value": "2.1%",
                "threshold": "",
                "flag": "pass",
                "confidence": "medium",
                "fill_state": "filled_cited",
            },
            {
                "metric_id": "census",
                "display_name": "Census",
                "stated_value": "1,200",
                "threshold": "",
                "flag": "pass",
                "confidence": "medium",
                "fill_state": "filled_cited",
            },
        ],
    )
    tldr = compress_for_tldr(bundle)
    lines = tldr["revenue_quality"]["lines"]
    assert len(lines) == 6
    assert "Caregiver utilization: 78%" in lines
    assert "Adverse survey rate: 2.1%" in lines
    assert "Census: 1,200" not in lines
    md = _render_compressed_tldr(bundle)
    rq_section = md.split("## Revenue Quality", maxsplit=1)[1].split("## ", maxsplit=1)[0]
    assert "Caregiver utilization: 78%" in rq_section
    assert "## KPI Dashboard" not in md


# --- T3 compressed template tests ---


def _render_compressed_template(bundle: dict, tldr: dict) -> str:
    env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=False)
    template = env.get_template(_COMPRESSED_TEMPLATE)
    return template.render(bundle=bundle, tldr=tldr)


def _mock_tldr_view() -> dict:
    return {
        "business_snapshot": None,
        "business_snapshot_narrative": None,
        "thesis_bullets": None,
        "key_watchouts": None,
        "mitigants_digest": None,
        "confidence_rationale": None,
        "preliminary_digest": None,
        "financial": {"rows": [], "observations": [], "show": False},
        "revenue_quality": {"lines": [], "show": False},
        "questions": [
            {
                "category": "legal",
                "question": "Request and review Healthcare Referral Agreements",
                "priority": "high",
            }
        ],
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


def test_compressed_template_omits_hidden_sections():
    tldr = _mock_tldr_view()
    tldr["preliminary_digest"] = "Regional home health provider with stable census."
    md = _render_compressed_template(_mock_bundle(), tldr)
    assert "_No " not in md
    assert "## Financial Strip" not in md
    assert "## KPI Dashboard" not in md
    assert "## Legal Snapshot" not in md
    assert "## Quality of Earnings" not in md
    assert "## Open Items / Data Requests" not in md
    assert "## Confidence by Area" not in md
    assert "## Top Risks" not in md
    assert "| Metric | Value |" not in md


def test_compressed_template_renders_thesis_and_watchouts_sections():
    tldr = _mock_tldr_view()
    tldr["thesis_bullets"] = ["Attractive regional platform with payer diversification."]
    tldr["key_watchouts"] = ["Founder concentration remains a key-person risk."]
    md = _render_compressed_template(_mock_bundle(), tldr)
    thesis_section = _section_body(md, "## Initial Thesis & Fit")
    watchouts_section = _section_body(md, "## Key Watchouts")
    assert "- Attractive regional platform with payer diversification." in thesis_section
    assert "- Founder concentration remains a key-person risk." in watchouts_section


def test_compressed_template_omits_vertical_header():
    bundle = _mock_bundle()
    bundle["meta"]["vertical_overlay"] = "healthcare"
    tldr = _mock_tldr_view()
    tldr["preliminary_digest"] = "Platform overview."
    md = _render_compressed_template(bundle, tldr)
    assert "**Vertical:**" not in md
    assert "healthcare" not in md.split("## ", maxsplit=1)[0]


def test_compressed_template_section_order_rainmaker_default():
    """Rev3: Rainmaker section order after One Line/Top Risks/Risk Mitigation removal."""
    tldr = _mock_tldr_view()
    tldr["preliminary_digest"] = "Regional home health platform."
    tldr["business_snapshot_narrative"] = "Regional home health platform."
    tldr["thesis_bullets"] = ["Thesis bullet."]
    tldr["key_watchouts"] = ["Watchout bullet."]
    tldr["revenue_quality"] = {"lines": ["Payer mix is diversified."], "show": True}
    tldr["confidence_rationale"] = "CIM supports financial trends."
    md = _render_compressed_template(_mock_bundle(), tldr)
    headers = [line.strip().removeprefix("## ") for line in md.splitlines() if line.startswith("## ")]
    assert headers == [
        "Preliminary View",
        "Business Snapshot",
        "Initial Thesis & Fit",
        "Key Watchouts",
        "Revenue Quality",
        "Priority Diligence Questions",
        "Analysis Notes",
        "Closing",
    ]


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
    assert tldr["thesis_bullets"] is None
    assert tldr["key_watchouts"] is None
    for key in ("legal_digest", "qoe_digest", "kpi_digest", "open_items_digest"):
        assert key not in tldr
    for key in ("headline", "kpi", "legal", "qoe", "open_items", "confidence_by_area", "show_confidence_table"):
        assert key not in tldr


def test_compress_thesis_bullets_and_key_watchouts_project_from_executive():
    bundle = _minimal_bundle(
        executive={
            "in_one_line": "",
            "preliminary_view": {"strengths": [], "concerns": [], "closing": ""},
            "thesis_bullets": ["  Regional platform with payer diversification. ", ""],
            "key_watchouts": ["Founder concentration risk."],
        },
    )
    tldr = compress_for_tldr(bundle)
    assert tldr["thesis_bullets"] == ["Regional platform with payer diversification."]
    assert tldr["key_watchouts"] == ["Founder concentration risk."]


def test_compress_thesis_bullets_absent_when_blank():
    bundle = _minimal_bundle(
        executive={
            "in_one_line": "",
            "preliminary_view": {"strengths": [], "concerns": [], "closing": ""},
            "thesis_bullets": [],
            "key_watchouts": ["  ", "—"],
        },
    )
    tldr = compress_for_tldr(bundle)
    assert tldr["thesis_bullets"] is None
    assert tldr["key_watchouts"] is None


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
    """Rev3 Flag 3: Risk Mitigation block removed; Analysis Notes still presence-gated."""
    tldr = _mock_tldr_view()
    tldr["preliminary_digest"] = "Overview."
    tldr["mitigants_digest"] = "Payer diversification and branch footprint offset concentration."
    tldr["confidence_rationale"] = None
    md_absent_confidence = _render_compressed_template(_mock_bundle(), tldr)
    assert "## Risk Mitigation" not in md_absent_confidence
    assert "Payer diversification and branch footprint offset concentration." not in md_absent_confidence
    assert "## Analysis Notes" not in md_absent_confidence
    assert "## Confidence & Data Gaps" not in md_absent_confidence
    assert "## Mitigants Digest" not in md_absent_confidence
    assert "## Confidence Rationale" not in md_absent_confidence

    tldr["confidence_rationale"] = "Financial trends and legal flags are well supported."
    md_present = _render_compressed_template(_mock_bundle(), tldr)
    assert "## Risk Mitigation" not in md_present
    assert "## Analysis Notes" in md_present
    assert "Financial trends and legal flags are well supported." in md_present


def test_analysis_notes_precedes_closing_without_confidence_table():
    """T5: Analysis Notes precedes Closing; Confidence by Area table removed."""
    tldr = _mock_tldr_view()
    tldr["preliminary_digest"] = "Overview."
    tldr["confidence_rationale"] = "CIM supports financial trends; referral agreements missing."
    md = _render_compressed_template(_mock_bundle(), tldr)
    assert "## Confidence by Area" not in md
    notes_idx = md.index("## Analysis Notes")
    closing_idx = md.index("## Closing")
    assert notes_idx < closing_idx


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
        "business_snapshot",
        "revenue_quality",
    ):
        assert with_digests[key] == baseline[key], key
    assert with_digests["preliminary_digest"] is not None
    for key in ("legal_digest", "qoe_digest", "kpi_digest", "open_items_digest"):
        assert key not in with_digests


def _section_body(md: str, header: str) -> str:
    return md.split(header, maxsplit=1)[1].split("\n## ", maxsplit=1)[0]


def test_compressed_template_digest_lead_ins_gate_and_preserve_detail():
    """Rev3: preliminary_digest renders alone in Preliminary View — no Strengths/Concerns."""
    tldr = _mock_tldr_view()
    tldr["preliminary_digest"] = "Compelling regional platform with manageable risks."

    md = _render_compressed_template(_mock_bundle(), tldr)

    assert "## Legal Snapshot" not in md
    assert "## KPI Dashboard" not in md
    assert "## Quality of Earnings" not in md
    assert "## Open Items / Data Requests" not in md

    prelim_section = _section_body(md, "## Preliminary View")
    assert "Compelling regional platform with manageable risks." in prelim_section
    assert "### Strengths" not in prelim_section
    assert "### Concerns" not in prelim_section


def test_compressed_template_digest_absent_sections_byte_identical():
    """T17 falsifier: absent preliminary_digest must not alter other gated section bodies."""
    tldr = _mock_tldr_view()
    tldr["business_snapshot_narrative"] = "Deterministic business snapshot body."
    tldr["preliminary_digest"] = None
    baseline_md = _render_compressed_template(_mock_bundle(), tldr)

    tldr_with_key_removed = copy.deepcopy(tldr)
    tldr_with_key_removed.pop("preliminary_digest", None)
    assert _render_compressed_template(_mock_bundle(), tldr) == _render_compressed_template(
        _mock_bundle(), tldr_with_key_removed
    )

    snapshot_section = _section_body(baseline_md, "## Business Snapshot")
    assert "Deterministic business snapshot body." in snapshot_section
    assert "## Preliminary View" not in baseline_md


# --- T4 renderers mode switch tests ---


def test_report_renderer_legacy_context_bundle_only():
    renderer = ReportRenderer()
    md = renderer.render(_volume_test_bundle(), _TEMPLATES_DIR / "tldr_one_pager.md.j2")
    assert "Further diligence recommended." in md


def test_report_renderer_compressed_context_includes_tldr():
    renderer = ReportRenderer()
    tldr = _mock_tldr_view()
    tldr["preliminary_digest"] = "Regional home health provider with stable census."
    md = renderer.render(
        _mock_bundle(),
        _TEMPLATES_DIR / _COMPRESSED_TEMPLATE,
        tldr=tldr,
    )
    assert "Regional home health provider with stable census." in md
    assert "## Top Risks" not in md


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
    assert "## In One Line" not in md
    assert "| Metric | Value |" not in md


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


def test_tldr_quality_check_registry_excludes_risk_raw_metric_keys(tmp_path, monkeypatch, capsys):
    """Rev3: Top Risks removal retires the risk_raw_metric_keys gate from the registry."""
    vol_dir = tmp_path / "reports" / "Elder_Care"
    _write_tldr_md(
        vol_dir,
        "# TL;DR\n\n## Top Risks\n\n| tier4_addback | critical | sample evidence |\n",
    )
    monkeypatch.setattr(tqc, "reports_volume_dir", lambda _c, _n: str(vol_dir))

    exit_code = tqc.run(company_name="Elder Care", catalog="uc13_ale")

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "risk_raw_metric_keys" not in out
    assert out.count("| word_count") + out.count("word_count |") >= 1
    assert out.count("| dict_leak") + out.count("dict_leak |") >= 1
    assert out.count("| operator_gaps") + out.count("operator_gaps |") >= 1


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


def test_rendered_output_omits_top_risks_table(elder_care_bundle: dict):
    md = _render_compressed_tldr(elder_care_bundle)
    assert "## Top Risks" not in md
    assert "| Risk | Severity | Evidence |" not in md


def test_empty_financial_omitted(elder_care_bundle: dict):
    md = _render_compressed_tldr(elder_care_bundle)
    assert "## Financial Strip" not in md


def test_flag_formatting(elder_care_bundle: dict):
    md = _render_compressed_tldr(elder_care_bundle)
    assert "change-of-control consent templates for top MSAs" in md
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
