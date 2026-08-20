"""Unit tests for agents.exec_summary.renderers.render_rainmaker.

Uses the real, most-recent-per-company `orchestrator_bundle.yaml` fixtures
(Elder Care / Clearsulting / GKF — Apéndice A.6) to prove the Rainmaker
template renders across verticals without leaking company-specific literals,
and that a partial (CIM-only-preview-shaped) bundle degrades gracefully
instead of raising.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from agents.exec_summary.renderers import render_rainmaker

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
_COMPANIES = ["elder_care", "clearsulting", "gkf", "b2b_saas"]

_EXPECTED_MARKERS = (
    "Company &amp; Investment Framing",
    "Financial Performance",
    "Priority Diligence Questions",
    "Proprietary &amp; Confidential",
)

# Iteración 2 (plan_raimaker_format.md §0/F1/F4): the Rainmaker format is
# exactly 3 pages, leading with affirmative framing + financial figures —
# the Risk Register / Confidence by Area page from the prior 4-page
# template must never reappear (Austin feedback F1 — "exception report" feel).
_REMOVED_PAGE_4_MARKERS = ("Risk Register", "Confidence by Area")

# Narrative fragments that are specific to Elder Care's business — a marker
# of "Elder-Care-shaped" leakage if they show up when rendering a different
# company's bundle (they legitimately appear only when rendering Elder Care
# itself, via its own bundle content — never hardcoded in the template/view).
_ELDER_CARE_ONLY_LITERALS = ("caregiver", "unicity", "guided living")


def _load(name: str) -> dict:
    with open(_FIXTURES_DIR / f"{name}_bundle.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.fixture(params=_COMPANIES)
def company(request):
    return request.param


def _patch_volume(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "agents.exec_summary.renderers.reports_volume_dir",
        lambda _catalog, _company: str(tmp_path),
    )


def test_render_rainmaker_writes_html_and_returns_paths(monkeypatch, tmp_path, company):
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load(company)

    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"])

    assert "html" in result
    html_path = Path(result["html"])
    assert html_path.exists()
    assert html_path.name == "rainmaker_opportunity_summary.html"
    html = html_path.read_text(encoding="utf-8")
    for marker in _EXPECTED_MARKERS:
        assert marker in html, f"missing marker {marker!r} for {company}"
    for marker in _REMOVED_PAGE_4_MARKERS:
        assert marker not in html, f"removed page-4 marker {marker!r} reappeared for {company}"


def test_render_rainmaker_has_expected_html_sections(monkeypatch, tmp_path):
    """Structural non-regression (round 3, A1): the cover page was dropped —
    the template now has 2 HTML sections (framing, financials), not 3. The
    real PDF page count (which is what actually matters to Austin) is
    asserted separately in test_render_rainmaker_pdf_page_count_within_target
    (A8), since PyMuPDF/WeasyPrint pagination doesn't map 1:1 to these divs."""
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load("elder_care")
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"])
    html = Path(result["html"]).read_text(encoding="utf-8")
    assert html.count('class="page') == 2


def test_render_rainmaker_landscape_orientation(monkeypatch, tmp_path, company):
    """A2: the template is landscape, not portrait."""
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load(company)
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"])
    html = Path(result["html"]).read_text(encoding="utf-8")
    assert "size: A4 landscape" in html


# Ceiling for the real rendered PDF page count (round 3, Part A). The
# baseline before this round was 4/4/4/4/5 pages (session_log.md §9);
# 3 of 5 fixtures already reach the intended 3-page target after A1-A6.
# elder_care and b2b_saas remain at 4 — the residual gap is bullet
# *verbosity*, not bullet count, and is addressed only by A7 (a narrative
# prompt change gated on Hector's separate approval, not yet applied).
_PAGE_COUNT_CEILING = 4


@pytest.mark.parametrize("company", ["elder_care", "elder_care_cim_only", "clearsulting", "gkf", "b2b_saas"])
def test_render_rainmaker_pdf_page_count_within_target(monkeypatch, tmp_path, company):
    pytest.importorskip("fitz", reason="PyMuPDF not available in this env")
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load(company)
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"])
    if "pdf" not in result:
        pytest.skip("no PDF engine available in this env")

    import fitz

    doc = fitz.open(result["pdf"])
    assert doc.page_count <= _PAGE_COUNT_CEILING, (
        f"{company}: {doc.page_count} pages, expected <= {_PAGE_COUNT_CEILING}"
    )


def test_render_rainmaker_no_cover_page(monkeypatch, tmp_path, company):
    """A1: the standalone cover page (logo/title/Purpose-Basis-Status
    callouts) is gone entirely — the company name now heads the framing
    page instead."""
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load(company)
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"])
    html = Path(result["html"]).read_text(encoding="utf-8")
    assert 'class="page cover"' not in html
    assert "Purpose" not in html
    assert "callout" not in html


def test_render_rainmaker_company_name_in_h1(monkeypatch, tmp_path, company):
    """A1: the company name is promoted to a prominent header on page 1."""
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load(company)
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"])
    html = Path(result["html"]).read_text(encoding="utf-8")
    assert f"<h1>{bundle['meta']['company_name']}</h1>" in html


def test_render_rainmaker_disclaimer_survives_cover_removal(monkeypatch, tmp_path, company):
    """A1: dropping the cover page must not drop the legal disclaimer
    (metadata.status) — it's relocated to the last page's footer."""
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load(company)
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"])
    html = Path(result["html"]).read_text(encoding="utf-8")
    status = bundle.get("meta", {}).get("disclaimer_text") or ""
    if status:
        assert status in html
    assert "Synthesized from the available data room" in html


def test_render_rainmaker_body_never_embeds_bracketed_source_citations(monkeypatch, tmp_path, company):
    """F5 (Austin: bracketed inline citations are distracting) — the 3-page
    body must never render raw evidence/citation text inline. Removing the
    Risk Register page (F1) already achieves this; this test locks it in."""
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load(company)
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"])
    html = Path(result["html"]).read_text(encoding="utf-8")
    assert ".pdf" not in html


def test_render_rainmaker_does_not_mutate_bundle(monkeypatch, tmp_path, company):
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load(company)
    snapshot = copy.deepcopy(bundle)
    render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"])
    assert bundle == snapshot


def test_render_rainmaker_no_cross_company_literal_leakage(monkeypatch, tmp_path):
    """Rendering Clearsulting/GKF must never contain Elder-Care-only terms —
    proves the template/view are data-driven, not Elder-Care-shaped (plan §0.5)."""
    for company in ("clearsulting", "gkf"):
        _patch_volume(monkeypatch, tmp_path / company)
        (tmp_path / company).mkdir(exist_ok=True)
        bundle = _load(company)
        result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"])
        html = Path(result["html"]).read_text(encoding="utf-8").lower()
        for literal in _ELDER_CARE_ONLY_LITERALS:
            assert literal not in html, f"{company} render leaked Elder Care literal {literal!r}"


def test_render_rainmaker_uses_pdf_engine_when_available(monkeypatch, tmp_path):
    # WeasyPrint raises OSError (not ImportError) when its system libs
    # (cairo/pango/gdk-pixbuf) are missing — pytest.importorskip only catches
    # ImportError, so this is a manual skip covering both failure modes. This
    # is the expected/common case (Apéndice A.5/R1: Databricks Serverless
    # cannot install those system libs at all).
    try:
        import weasyprint  # noqa: F401
    except Exception as exc:
        pytest.skip(f"WeasyPrint (or its system libs) not available in this env: {exc!r}")
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load("elder_care")
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"])
    assert "pdf" in result
    pdf_path = Path(result["pdf"])
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0


def test_render_rainmaker_falls_back_when_weasyprint_import_fails(monkeypatch, tmp_path):
    """If WeasyPrint raises on import/render, render_rainmaker must fall back
    to PyMuPDF Story rather than propagate — the HTML must still be produced
    either way (Apéndice A.5/R1 contingency)."""
    pytest.importorskip("fitz", reason="PyMuPDF not available in this env")
    _patch_volume(monkeypatch, tmp_path)

    import builtins

    real_import = builtins.__import__

    def _blocked_import(name, *args, **kwargs):
        if name == "weasyprint":
            raise ImportError("simulated: weasyprint not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocked_import)

    bundle = _load("elder_care")
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"])
    assert "html" in result
    assert "pdf" in result
    assert Path(result["pdf"]).stat().st_size > 0


def test_render_rainmaker_partial_bundle_degrades_without_raising(monkeypatch, tmp_path):
    """A CIM-only preview bundle (meta.status='partial', several sections
    empty) must still render — mirrors BundleBuilder's tolerance for missing
    agents (plan §2)."""
    _patch_volume(monkeypatch, tmp_path)
    bundle = copy.deepcopy(_load("elder_care"))
    bundle["meta"]["status"] = "partial"
    bundle["meta"]["agents_present"] = {k: False for k in bundle["meta"]["agents_present"]}
    bundle["qoe"] = {"addback_pct_of_ebitda": "", "tier_summary": "", "flags": []}
    bundle["risks"] = []
    bundle["kpi_dashboard"] = []
    bundle["data_room_gaps"] = []
    bundle["diligence_questions"] = []
    bundle["company_framing"]["overview_bullets"] = []
    bundle["legal"] = {
        "assessed_count": 0,
        "checklist_total": 11,
        "section_confidence": "low",
        "top_flags": [],
        "top_gaps": [],
        "recommended_diligence": [],
    }

    result = render_rainmaker(bundle, "uc13_preview", "Elder Care")
    html = Path(result["html"]).read_text(encoding="utf-8")
    assert "Not yet assessed in this preview." in html
    assert "Company &amp; Investment Framing" in html


def test_render_rainmaker_narrative_none_falls_back_to_bundle_bullets(monkeypatch, tmp_path):
    """Paso 6 gate: narrative=None (default) must render deterministically
    from the bundle's own bullets — never break, never require an LLM call."""
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load("elder_care")
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"], narrative=None)
    html = Path(result["html"]).read_text(encoding="utf-8")
    for bullet in bundle["company_framing"]["overview_bullets"]:
        assert bullet in html


def test_render_rainmaker_narrative_degraded_falls_back_like_none(monkeypatch, tmp_path):
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load("elder_care")
    degraded = {
        "one_liner": None, "company_overview": None, "business_model": None,
        "investment_thesis": None, "recommendation": None,
        "commercial_revenue_quality": None, "diligence_priorities": None,
        "synthesis_status": "degraded",
    }
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"], narrative=degraded)
    html = Path(result["html"]).read_text(encoding="utf-8")
    for bullet in bundle["company_framing"]["overview_bullets"]:
        assert bullet in html


def test_render_rainmaker_narrative_populated_uses_prose_not_bundle_bullets(monkeypatch, tmp_path):
    """Paso 6 gate: with narrative populated, the template uses the LLM
    prose instead of the raw bundle bullets."""
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load("elder_care")
    narrative = {
        "one_liner": "A synthesized one-liner distinct from the bundle default.",
        "company_overview": ["Synthesized overview bullet — not in the bundle."],
        "business_model": ["Synthesized business model bullet."],
        "investment_thesis": {"value_drivers": ["Synthesized value driver."], "why_special": "Synthesized why-special sentence."},
        "recommendation": "This appears worthy of additional pursuit because of A, B and C, subject primarily to proving X, Y and Z.",
        "commercial_revenue_quality": [{"topic": "Synthesized Topic", "detail": "Synthesized detail."}],
        "diligence_priorities": ["Synthesized diligence priority question."],
        "synthesis_status": "success",
    }
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"], narrative=narrative)
    html = Path(result["html"]).read_text(encoding="utf-8")
    assert "A synthesized one-liner distinct from the bundle default." in html
    assert "Synthesized overview bullet — not in the bundle." in html
    assert "This appears worthy of additional pursuit" in html
    assert "Synthesized diligence priority question." in html


def test_render_rainmaker_includes_brand_logo_when_asset_present(monkeypatch, tmp_path):
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load("elder_care")
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"])
    html = Path(result["html"]).read_text(encoding="utf-8")
    assert "data:image/jpeg;base64," in html


def test_render_rainmaker_renders_dollar_pnl_table_on_diverse_overlay(monkeypatch, tmp_path):
    """Anti-overfit (P2): a different overlay (b2b_saas) with populated $
    figures renders the full P&L table (with its growth column, A3)
    end-to-end through render_rainmaker, not just through the pure
    rainmaker_view unit tests."""
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load("b2b_saas")
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"])
    html = Path(result["html"]).read_text(encoding="utf-8")
    assert "$4.0" in html
    assert "$12.0" in html
    assert "2022A" in html and "2024A" in html
    assert "growth-col" in html


def test_render_rainmaker_no_bar_chart_or_cagr_circles(monkeypatch, tmp_path, company):
    """A4: the financial snapshot bar chart and the CAGR circles are gone —
    the growth column (A3) and the Rule-of-X band (A5) replace them."""
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load(company)
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"])
    html = Path(result["html"]).read_text(encoding="utf-8")
    assert "<svg" not in html
    assert "cagr-circle" not in html
    assert "chart-legend" not in html


def test_render_rainmaker_rule_of_x_band_present_when_computable(monkeypatch, tmp_path):
    """A5: b2b_saas has both growth and EBITDA margin extracted for
    consecutive periods, so the Rule-of-X band must render."""
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load("b2b_saas")
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"])
    html = Path(result["html"]).read_text(encoding="utf-8")
    assert 'class="rule-band"' in html
    assert "Rule of" in html


def test_render_rainmaker_rule_of_x_band_absent_without_placeholder(monkeypatch, tmp_path):
    """A5: no fabrication — a business without both growth and EBITDA margin
    extracted must render no band at all, not an empty/placeholder one."""
    _patch_volume(monkeypatch, tmp_path)
    bundle = copy.deepcopy(_load("elder_care"))
    for row in bundle["financials"]["table_rows"]:
        row["ebitda_margin_pct"] = ""
        row["ebitda"] = ""
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"])
    html = Path(result["html"]).read_text(encoding="utf-8")
    assert 'class="rule-band"' not in html


# ---------------------------------------------------------------------------
# Stakeholder review round 1 fixes (cover overlap + bullet-count discipline).
# ---------------------------------------------------------------------------


def test_render_rainmaker_cover_callouts_not_absolutely_positioned(monkeypatch, tmp_path):
    """Regression guard: `.callout-row { position: absolute; }` rendered the
    Purpose/Basis/Status cards on top of the title under the real production
    PDF engine (WeasyPrint) — reported by the stakeholder against a real
    run. Must stay in normal flow."""
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load("elder_care")
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"])
    html = Path(result["html"]).read_text(encoding="utf-8")
    assert "position: absolute" not in html


def _extract_block(html: str, start_marker: str, end_marker: str = "</div>\n    </div>") -> str:
    start = html.index(start_marker)
    return html[start : start + 4000]


def test_render_rainmaker_bullet_counts_stay_within_stakeholder_caps(monkeypatch, tmp_path):
    """Stakeholder feedback (round 1 + round 3 Austin re-tightening/re-loosening):
    Company Overview/Product & Revenue Model <=4 each, Investment Thesis <=4
    total (why_special + up to 3 value_drivers when why_special is present),
    Key Watchouts <=3 (now narrative-compacted), Revenue Quality <=5,
    Diligence Questions <=6 (round 2, Part B/B3 — one question per
    thesis-testing archetype, see rainmaker_narrative.py) — regardless of how
    many bullets the LLM or the bundle fallback would otherwise produce."""
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load("elder_care")
    narrative = {
        "one_liner": "One liner.",
        "company_overview": [f"Overview bullet {i}" for i in range(10)],
        "business_model": [f"Business model bullet {i}" for i in range(10)],
        "investment_thesis": {"value_drivers": [f"Driver {i}" for i in range(10)], "why_special": "Why special."},
        "key_watchouts": [f"Watchout {i}" for i in range(10)],
        "recommendation": "Recommendation sentence.",
        "commercial_revenue_quality": [{"topic": f"Topic {i}", "detail": "Detail."} for i in range(10)],
        "diligence_priorities": [f"Question {i}?" for i in range(10)],
        "synthesis_status": "success",
    }
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"], narrative=narrative)
    html = Path(result["html"]).read_text(encoding="utf-8")

    overview_block = _extract_block(html, "Company Overview")
    assert overview_block.count("Overview bullet") == 4

    business_model_block = _extract_block(html, "Product &amp; Revenue Model")
    assert business_model_block.count("Business model bullet") == 4

    thesis_block = _extract_block(html, "Initial Investment Thesis &amp; Fit")
    assert thesis_block.count("Driver ") == 3  # why_special present -> +3 drivers, 4 lines total
    assert "Why special." in thesis_block

    watchouts_block = _extract_block(html, "Key Watchouts")
    assert watchouts_block.count("Watchout ") == 3

    revqual_block = _extract_block(html, "Revenue Quality &amp; Customer Base")
    assert revqual_block.count("Topic ") == 5

    diligence_block = _extract_block(html, "Priority Diligence Questions")
    assert diligence_block.count("Question ") == 6


def test_render_rainmaker_investment_thesis_caps_at_four_without_why_special(monkeypatch, tmp_path):
    """When the LLM omits why_special, the card falls back to exactly 4
    value_drivers (still 4 lines total, matching the with-why_special path)."""
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load("elder_care")
    narrative = {
        "one_liner": "One liner.",
        "company_overview": ["A", "B", "C"],
        "business_model": ["A", "B", "C"],
        "investment_thesis": {"value_drivers": [f"Driver {i}" for i in range(10)], "why_special": ""},
        "recommendation": "Recommendation sentence.",
        "commercial_revenue_quality": [{"topic": "T", "detail": "D."}],
        "diligence_priorities": ["Q?"],
        "synthesis_status": "success",
    }
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"], narrative=narrative)
    html = Path(result["html"]).read_text(encoding="utf-8")
    thesis_block = _extract_block(html, "Initial Investment Thesis &amp; Fit")
    assert thesis_block.count("Driver ") == 4


def test_render_rainmaker_key_watchouts_capped_at_three(monkeypatch, tmp_path):
    """Key Watchouts falls back to the bundle's own field (capped at 3) when
    no narrative is available — verified against a bundle with >3 watchouts."""
    _patch_volume(monkeypatch, tmp_path)
    bundle = copy.deepcopy(_load("elder_care"))
    bundle["executive"]["key_watchouts"] = [f"Watchout number {i}" for i in range(10)]
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"], narrative=None)
    html = Path(result["html"]).read_text(encoding="utf-8")
    watchouts_block = _extract_block(html, "Key Watchouts")
    assert watchouts_block.count("Watchout number") == 3


def test_render_rainmaker_key_watchouts_prefers_narrative_compaction(monkeypatch, tmp_path):
    """Round 3 (Austin): Key Watchouts overflowed because it never went
    through the narrative layer's brevity caps. narrative.key_watchouts (a
    compacted rewrite of the bundle's own watchouts) must take priority over
    the raw bundle field when present."""
    _patch_volume(monkeypatch, tmp_path)
    bundle = copy.deepcopy(_load("elder_care"))
    bundle["executive"]["key_watchouts"] = ["Verbose original bundle watchout that the narrative should replace."]
    narrative = {
        "one_liner": None, "company_overview": None, "business_model": None,
        "investment_thesis": None, "recommendation": None,
        "commercial_revenue_quality": None, "diligence_priorities": None,
        "key_watchouts": ["Compact watchout one.", "Compact watchout two.", "Compact watchout three."],
        "synthesis_status": "partial",
    }
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"], narrative=narrative)
    html = Path(result["html"]).read_text(encoding="utf-8")
    watchouts_block = _extract_block(html, "Key Watchouts")
    assert "Compact watchout one." in watchouts_block
    assert "Compact watchout three." in watchouts_block
    assert "Verbose original bundle watchout" not in watchouts_block
