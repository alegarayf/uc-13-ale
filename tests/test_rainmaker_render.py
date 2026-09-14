"""Unit tests for agents.exec_summary.renderers.render_rainmaker.

Uses the real, most-recent-per-company `orchestrator_bundle.yaml` fixtures
(Elder Care / Clearsulting / GKF — Apéndice A.6) to prove the Rainmaker
template renders across verticals without leaking company-specific literals,
and that a partial (CIM-only-preview-shaped) bundle degrades gracefully
instead of raising.
"""

from __future__ import annotations

import copy
import re
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
    """Structural non-regression (round 3, A1; extended T2, plan §8): the
    cover page was dropped and the MPS page was added — the template now has
    3 HTML sections (framing, financials, mps). The real PDF page count
    (which is what actually matters to Austin) is asserted separately in
    test_render_rainmaker_pdf_page_count_within_target (A8), since
    PyMuPDF/WeasyPrint pagination doesn't map 1:1 to these divs."""
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load("elder_care")
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"])
    html = Path(result["html"]).read_text(encoding="utf-8")
    assert html.count('class="page') == 3


def test_render_rainmaker_landscape_orientation(monkeypatch, tmp_path, company):
    """A2: the template is landscape, not portrait."""
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load(company)
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"])
    html = Path(result["html"]).read_text(encoding="utf-8")
    assert "size: A4 landscape" in html


# Ceiling for the real rendered PDF page count. Three content sections
# (framing, financials, mps), of which the MPS page (plan
# docs/plans/mps_score/mps_score_1st_draft.md §8/§8.1, T2) is exactly one
# page by design — all 5 fixtures render at 4 pages today (the committed
# golden baseline moved from pdf_pages=3 to 4 for this reason, tests/
# fixtures/rainmaker_golden_render.json). If the MPS commentary is verbose
# enough to spill onto a 5th page, the fix is tightening the MPS table's
# CSS/length budget (§8.1 steps 2-4), never raising this ceiling.
_PAGE_COUNT_CEILING = 4


def _require_production_pdf_engine() -> None:
    """Page counts are only meaningful under WeasyPrint — the engine that
    actually renders in production. The PyMuPDF Story fallback paginates
    differently (b2b_saas: 5 pages under PyMuPDF vs. 4 under WeasyPrint), so
    asserting a ceiling against it reports a phantom regression on any machine
    where WeasyPrint's system libs (libgobject et al.) are not loadable —
    which happened once already, costing a session's worth of investigation.

    Same guard test_rainmaker_golden_render.py already uses for its own page
    count. On macOS/Homebrew you may need DYLD_LIBRARY_PATH=/opt/homebrew/lib
    for the import below to succeed.
    """
    try:
        import weasyprint  # noqa: F401
    except Exception as exc:  # noqa: BLE001 - any import/dlopen failure means "not the prod engine"
        pytest.skip(f"WeasyPrint (or its system libs) not available in this env: {exc!r}")


@pytest.mark.parametrize("company", ["elder_care", "elder_care_cim_only", "clearsulting", "gkf", "b2b_saas"])
def test_render_rainmaker_pdf_page_count_within_target(monkeypatch, tmp_path, company):
    pytest.importorskip("fitz", reason="PyMuPDF not available in this env")
    _require_production_pdf_engine()
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


def _load_mps_fixture() -> dict:
    with open(_FIXTURES_DIR / "mps_run_verbose.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.mark.parametrize("company", ["elder_care", "elder_care_cim_only", "clearsulting", "gkf", "b2b_saas"])
def test_render_rainmaker_pdf_page_count_within_target_with_worst_case_mps(monkeypatch, tmp_path, company):
    """Same guard as test_render_rainmaker_pdf_page_count_within_target
    (same ceiling, no new one), but exercised with the hand-written,
    most-verbose-plausible MPS fixture (plan §8.1) — this is what actually
    proves the MPS page's one-page fit before an LLM is generating its text."""
    pytest.importorskip("fitz", reason="PyMuPDF not available in this env")
    _require_production_pdf_engine()
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load(company)
    mps = _load_mps_fixture()
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"], mps=mps)
    if "pdf" not in result:
        pytest.skip("no PDF engine available in this env")

    import fitz

    doc = fitz.open(result["pdf"])
    assert doc.page_count <= _PAGE_COUNT_CEILING, (
        f"{company}: {doc.page_count} pages with worst-case MPS commentary, "
        f"expected <= {_PAGE_COUNT_CEILING}"
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


# ---------------------------------------------------------------------------
# T2 — MPS page (plan §8, §11 tests 14/14a/15).
# ---------------------------------------------------------------------------


def test_render_rainmaker_mps_section_renders_on_all_fixtures_without_data(monkeypatch, tmp_path, company):
    """Test 14: with no MPS run supplied (mps=None, the default — the shape
    every pre-T3/T4 caller uses today), the section still renders with all
    7 rows and the degraded fallback text rather than vanishing (OTH-03)."""
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load(company)
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"])
    html = Path(result["html"]).read_text(encoding="utf-8")
    assert 'class="page mps"' in html
    assert "Minimum Pursuit Score" in html
    assert html.count("Not yet assessed in this preview.") >= 7
    for display_name in (
        "Magical business model",
        "Growth mindset",
        "Growth characteristics",
        "Manageable systemic risk",
        "Untapped growth opportunities",
        "Transformational equity",
        "Financeable",
    ):
        assert display_name in html


def test_render_rainmaker_mps_section_renders_with_verbose_fixture(monkeypatch, tmp_path):
    """Test 14: a populated MPS run renders real scores/commentary, not the
    degraded fallback."""
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load("elder_care")
    mps = _load_mps_fixture()
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"], mps=mps)
    html = Path(result["html"]).read_text(encoding="utf-8")
    mps_section = html[html.index('class="page mps"') :]
    assert "Full data room" in mps_section
    assert "above threshold" in mps_section
    assert "24.0" in mps_section
    # Only the MPS section must be free of the degraded fallback text — other
    # sections of Elder Care's own bundle legitimately fall back elsewhere.
    assert "Not yet assessed in this preview." not in mps_section
    # The evidence-basis legend must appear once a contact_dependent/
    # judgment_over_context row is present (F-8, §8.2).
    assert "assessed from proxies and judgment" in mps_section


@pytest.mark.parametrize("company", ["elder_care", "elder_care_cim_only", "clearsulting", "gkf", "b2b_saas"])
def test_render_rainmaker_mps_section_is_last_page_section(monkeypatch, tmp_path, company):
    """Test 14a: the MPS section is the LAST `<section class="page">` in the
    rendered HTML — the page-count half of the one-page-fit guard is already
    covered by test_render_rainmaker_pdf_page_count_within_target(_with_
    worst_case_mps); this is purely structural."""
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load(company)
    mps = _load_mps_fixture()
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"], mps=mps)
    html = Path(result["html"]).read_text(encoding="utf-8")
    sections = re.findall(r'<section class="page ([a-z]+)">', html)
    assert sections, "no <section class=\"page ...\"> found"
    assert sections[-1] == "mps", f"{company}: last section was {sections[-1]!r}, expected 'mps'"


def test_render_rainmaker_mps_section_never_embeds_bracketed_source_citations(monkeypatch, tmp_path, company):
    """Test 15: extends test_render_rainmaker_body_never_embeds_bracketed_
    source_citations coverage to the MPS section — evidence_refs is always
    empty in v1 (F-7), so no citation column/text should ever render."""
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load(company)
    mps = _load_mps_fixture()
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"], mps=mps)
    html = Path(result["html"]).read_text(encoding="utf-8")
    assert ".pdf" not in html


# ---------------------------------------------------------------------------
# The opening box now carries three core-business lines instead of a single
# hook sentence, and the financial table's unit header is derived from the
# figures rather than hardcoded to "in millions".
# ---------------------------------------------------------------------------


def _render_html(monkeypatch, tmp_path, bundle, **kwargs) -> str:
    _patch_volume(monkeypatch, tmp_path)
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"], **kwargs)
    return Path(result["html"]).read_text(encoding="utf-8")


def test_core_business_lines_replace_the_single_hook_sentence(monkeypatch, tmp_path):
    narrative = {
        "one_liner": "The old single-sentence hook.",
        "core_business": ["What it does.", "How it does it.", "KPI: 42 units."],
    }
    html = _render_html(monkeypatch, tmp_path, _load("gkf"), narrative=narrative)
    assert html.count('class="core-line"') == 3
    for line in narrative["core_business"]:
        assert line in html
    assert "The old single-sentence hook." not in html


def test_one_liner_still_renders_when_the_narrative_has_no_core_business(monkeypatch, tmp_path):
    html = _render_html(
        monkeypatch, tmp_path, _load("gkf"), narrative={"one_liner": "The hook sentence."}
    )
    assert "The hook sentence." in html
    assert 'class="core-line"' not in html


def test_core_business_lines_are_capped_at_three(monkeypatch, tmp_path):
    narrative = {"core_business": [f"Line {i}." for i in range(6)]}
    html = _render_html(monkeypatch, tmp_path, _load("gkf"), narrative=narrative)
    assert html.count('class="core-line"') == 3
    assert "Line 3." not in html


def test_financial_table_unit_header_is_derived_not_hardcoded(monkeypatch, tmp_path):
    bundle = copy.deepcopy(_load("gkf"))
    bundle["headline_metrics"]["ltm_revenue"] = "$23.0mm"
    bundle["financials"]["table_rows"] = [
        {"year": "2023A", "revenue": "$21,403", "gross_profit": None,
         "gross_margin_pct": None, "ebitda": None, "ebitda_margin_pct": None},
        {"year": "2024A", "revenue": "$22,266", "gross_profit": None,
         "gross_margin_pct": None, "ebitda": None, "ebitda_margin_pct": None},
        {"year": "2025B", "revenue": "$23,022", "gross_profit": None,
         "gross_margin_pct": None, "ebitda": None, "ebitda_margin_pct": None},
    ]
    html = _render_html(monkeypatch, tmp_path, bundle)
    assert "($ in thousands)" in html
    assert "in millions" not in html


def test_financial_table_header_states_no_unit_when_there_are_no_figures(monkeypatch, tmp_path):
    html = _render_html(monkeypatch, tmp_path, _load("gkf"))
    assert "($)" in html
    assert "in millions" not in html


# ---------------------------------------------------------------------------
# Page-1 fit. The framing page carries the most variable content on the sheet
# (three core-business lines, four cards, the recommendation band), and it
# overflowed onto a near-empty fifth page on the 2026-09-04 GKF and
# Clearsulting runs. It fitted on the authoring machine and split in the job
# because the Databricks serverless container has none of the template's
# fonts and WeasyPrint falls through to DejaVu Sans, which is wider than
# Helvetica — so a page that merely *fits* locally is not evidence of a fit in
# production. This exercises the worst case the prompt permits (every line at
# its 140-character cap) to keep real slack in the design.
# ---------------------------------------------------------------------------

_MAX_LINE = "W" * 5 + (" Wm" * 44)  # 137 chars of unusually wide glyphs


def _worst_case_narrative() -> dict:
    return {
        "core_business": [_MAX_LINE] * 3,
        "company_overview": [_MAX_LINE] * 4,
        "business_model": [_MAX_LINE] * 4,
        "investment_thesis": {"why_special": _MAX_LINE, "value_drivers": [_MAX_LINE] * 3},
        "key_watchouts": [_MAX_LINE] * 3,
        "recommendation": _MAX_LINE * 2,
        "commercial_revenue_quality": [{"topic": "Topic", "detail": _MAX_LINE}] * 5,
        "diligence_priorities": [_MAX_LINE] * 6,
    }


@pytest.mark.parametrize("company", ["elder_care", "clearsulting", "gkf", "b2b_saas"])
def test_framing_page_does_not_spill_with_a_max_length_narrative(monkeypatch, tmp_path, company):
    pytest.importorskip("fitz", reason="PyMuPDF not available in this env")
    _require_production_pdf_engine()
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load(company)
    result = render_rainmaker(
        bundle,
        "uc13_preview",
        bundle["meta"]["company_name"],
        narrative=_worst_case_narrative(),
        mps=_load_mps_fixture(),
    )
    if "pdf" not in result:
        pytest.skip("no PDF engine available in this env")

    import fitz

    doc = fitz.open(result["pdf"])
    assert doc.page_count <= _PAGE_COUNT_CEILING, (
        f"{company}: {doc.page_count} pages with a max-length narrative, expected "
        f"<= {_PAGE_COUNT_CEILING} — the framing page has run out of vertical slack."
    )
    # A spill shows up as a page whose only content is the framing footer.
    for index, page in enumerate(doc):
        text = " ".join(page.get_text().split())
        assert text.strip() != "Proprietary & Confidential — Not for distribution", (
            f"{company}: page {index + 1} contains nothing but the framing footer — "
            "the framing page overflowed."
        )
