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


def test_render_rainmaker_has_exactly_three_pages(monkeypatch, tmp_path):
    """Structural non-regression for F4 (Austin: "too expansive for an
    executive summary") — the reference Rainmaker format is 3 pages."""
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load("elder_care")
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"])
    html = Path(result["html"]).read_text(encoding="utf-8")
    assert html.count('class="page') == 3


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
    figures renders the full P&L table + snapshot chart end-to-end through
    render_rainmaker, not just through the pure rainmaker_view unit tests."""
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load("b2b_saas")
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"])
    html = Path(result["html"]).read_text(encoding="utf-8")
    assert "$4.0" in html
    assert "$12.0" in html
    assert "2022A" in html and "2024A" in html
    assert "<svg" in html and "chart-legend" in html


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
    """Stakeholder feedback (round 1): Company Overview <=5, Product & Revenue
    Model exactly <=3, Investment Thesis/Key Watchouts <=4 each, Revenue
    Quality/Diligence Questions <=5 each — regardless of how many bullets the
    LLM or the bundle fallback would otherwise produce."""
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load("elder_care")
    narrative = {
        "one_liner": "One liner.",
        "company_overview": [f"Overview bullet {i}" for i in range(10)],
        "business_model": [f"Business model bullet {i}" for i in range(10)],
        "investment_thesis": {"value_drivers": [f"Driver {i}" for i in range(10)], "why_special": "Why special."},
        "recommendation": "Recommendation sentence.",
        "commercial_revenue_quality": [{"topic": f"Topic {i}", "detail": "Detail."} for i in range(10)],
        "diligence_priorities": [f"Question {i}?" for i in range(10)],
        "synthesis_status": "success",
    }
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"], narrative=narrative)
    html = Path(result["html"]).read_text(encoding="utf-8")

    overview_block = _extract_block(html, "Company Overview")
    assert overview_block.count("Overview bullet") == 5

    business_model_block = _extract_block(html, "Product &amp; Revenue Model")
    assert business_model_block.count("Business model bullet") == 3

    thesis_block = _extract_block(html, "Initial Investment Thesis &amp; Fit")
    assert thesis_block.count("Driver ") == 3

    revqual_block = _extract_block(html, "Revenue Quality &amp; Customer Base")
    assert revqual_block.count("Topic ") == 5

    diligence_block = _extract_block(html, "Priority Diligence Questions")
    assert diligence_block.count("Question ") == 5


def test_render_rainmaker_key_watchouts_capped_at_four(monkeypatch, tmp_path):
    """Key Watchouts is bundle-sourced (not LLM), so it needs its own cap
    independent of narrative — verified against a bundle with >4 watchouts."""
    _patch_volume(monkeypatch, tmp_path)
    bundle = copy.deepcopy(_load("elder_care"))
    bundle["executive"]["key_watchouts"] = [f"Watchout number {i}" for i in range(10)]
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"], narrative=None)
    html = Path(result["html"]).read_text(encoding="utf-8")
    watchouts_block = _extract_block(html, "Key Watchouts")
    assert watchouts_block.count("Watchout number") == 4
