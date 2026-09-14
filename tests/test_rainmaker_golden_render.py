"""Golden-render regression test for the Rainmaker template (round 3, A8.3).

Captures the round-3 baseline (docs/plans/rainmaker-format-round3.md) as a
committed digest per fixture — HTML sha256 (deterministic, environment
independent) plus the real rendered PDF page count (WeasyPrint, when
available). A silent diff here means the next formatting change altered the
artifact without anyone noticing; update
tests/fixtures/rainmaker_golden_render.json deliberately (re-run the golden
render) when a change is intentional, never to make a red test pass without
looking at what changed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from agents.exec_summary.renderers import render_rainmaker

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
_GOLDEN_PATH = _FIXTURES_DIR / "rainmaker_golden_render.json"
_COMPANIES = ["elder_care", "elder_care_cim_only", "clearsulting", "gkf", "b2b_saas"]


def _load_bundle(name: str) -> dict:
    with open(_FIXTURES_DIR / f"{name}_bundle.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _load_golden() -> dict:
    with open(_GOLDEN_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _patch_volume(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "agents.exec_summary.renderers.reports_volume_dir",
        lambda _catalog, _company: str(tmp_path),
    )


@pytest.mark.parametrize("company", _COMPANIES)
def test_golden_render_html_matches_committed_digest(monkeypatch, tmp_path, company):
    golden = _load_golden()[company]
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load_bundle(company)
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"])
    html_bytes = Path(result["html"]).read_bytes()
    actual_sha = hashlib.sha256(html_bytes).hexdigest()
    assert actual_sha == golden["html_sha256"], (
        f"{company}: rendered HTML digest changed — if this is an intentional "
        f"formatting change, regenerate {_GOLDEN_PATH.name} deliberately "
        "rather than pasting in the new hash."
    )


@pytest.mark.parametrize("company", _COMPANIES)
def test_golden_render_pdf_page_count_matches_committed_baseline(monkeypatch, tmp_path, company):
    try:
        import weasyprint  # noqa: F401
    except Exception as exc:
        pytest.skip(f"WeasyPrint (or its system libs) not available in this env: {exc!r}")
    golden = _load_golden()[company]
    _patch_volume(monkeypatch, tmp_path)
    bundle = _load_bundle(company)
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"])
    assert "pdf" in result

    import fitz

    doc = fitz.open(result["pdf"])
    assert doc.page_count == golden["pdf_pages"], (
        f"{company}: PDF page count changed ({doc.page_count} vs committed "
        f"{golden['pdf_pages']}) — verify this is an intentional change before "
        f"updating {_GOLDEN_PATH.name}."
    )
