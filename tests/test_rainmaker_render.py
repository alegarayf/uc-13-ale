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
_COMPANIES = ["elder_care", "clearsulting", "gkf"]

_EXPECTED_MARKERS = (
    "Company &amp; Investment Framing",
    "Operating Data",
    "Risk Register",
    "Confidence by Area",
    "Proprietary &amp; Confidential",
)

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
    assert "Risk Register" in html
    assert "Company &amp; Investment Framing" in html
