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
from agents.orchestrator.tldr_compress import compress_for_tldr

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


# --- T3 compressed template tests ---


def _render_compressed_template(bundle: dict, tldr: dict) -> str:
    env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=False)
    template = env.get_template(_COMPRESSED_TEMPLATE)
    return template.render(bundle=bundle, tldr=tldr)


def _mock_tldr_view() -> dict:
    return {
        "headline": {"metrics": [{"label": "LTM Revenue", "value": "$12M"}], "fallback_note": None},
        "in_one_line": "Regional home health provider with stable census.",
        "strengths": ["Strength 1"],
        "concerns": ["Concern 1"],
        "business_snapshot": None,
        "financial": {"rows": [], "observations": [], "show": False},
        "revenue_quality": {"lines": [], "show": False},
        "kpi": {"rows": [], "show": False},
        "legal": {
            "assessed_label": "7 / 11",
            "section_confidence": "medium",
            "bullets": ["Sample legal bullet."],
            "show": True,
        },
        "qoe": {"summary": "", "bullets": [], "show": False},
        "risks": [
            {
                "risk": "tier4_addback",
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


def test_compressed_template_omits_hidden_sections_and_uses_mitigant():
    md = _render_compressed_template(_mock_bundle(), _mock_tldr_view())
    assert "Request support" in md
    assert "Mitigant" in md
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
    assert "Request support" in md
    assert "Regional home health provider" in md


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
    for line in md.splitlines():
        if line.strip() == "## Top Risks":
            in_risks = True
            continue
        if in_risks and line.startswith("## "):
            break
        if in_risks and line.startswith("| tier4_addback"):
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
    "db16711f44880b5a0ef5305d3b080f4f43ab59d51429836ea217878539ac1ef1"
)


def test_full_report_unaffected(elder_care_bundle: dict):
    renderer = ReportRenderer()
    md = renderer.render(elder_care_bundle, _TEMPLATES_DIR / _FULL_REPORT_TEMPLATE)
    digest = hashlib.sha256(md.encode("utf-8")).hexdigest()
    assert digest == _FULL_REPORT_BASELINE_SHA256
