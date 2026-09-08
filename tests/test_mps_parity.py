"""MPS markup parity between the executive review and the final report.

D-01 (plan §5) was approved as Path A: the MPS table markup lives in one
shared partial (``_mps_page.html.j2``), included from both
``rainmaker_opportunity_summary.html.j2`` and ``final_report.html.j2``. This
test is what stops the two documents from drifting apart again — it renders
both from the *same* bundle and the *same* MPS run and asserts the extracted
MPS markup is byte-identical (whitespace-between-tags normalised only).

See also T06 (``docs/plans/final_report/tasks/T06_mps_parity.md``) and the
before/after render diffs recorded in plan §5.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from agents.exec_summary.renderers import render_final_report, render_rainmaker

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

_DRIFT_MESSAGE = (
    "the MPS block has drifted between the executive review and the final "
    "report — see plan §5 / T06."
)


def _load_bundle() -> dict:
    with open(_FIXTURES_DIR / "elder_care_bundle.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _load_mps_run() -> dict:
    with open(_FIXTURES_DIR / "mps_run_verbose.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _patch_volume(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "agents.exec_summary.renderers.reports_volume_dir",
        lambda _catalog, _company: str(tmp_path),
    )


def _extract_mps_block(html: str) -> str:
    """Anchor on ``<table class="mps-table">`` through the closing
    ``mps-footer-note`` div — the exact span the shared partial owns,
    excluding the per-template wrapper (section vs div, running header,
    macro-vs-literal footer) that is *allowed* to differ."""
    start = html.index('<table class="mps-table">')
    footer_marker = html.index('class="mps-footer-note"', start)
    end = html.index("</div>", footer_marker) + len("</div>")
    return html[start:end]


def _normalize_whitespace_between_tags(html: str) -> str:
    """Collapse whitespace runs that sit *entirely* between two tags. Does
    not touch attributes, class names, or cell contents — a run containing
    non-whitespace text is left untouched by construction."""
    return re.sub(r">\s+<", "><", html)


def _render_er_mps_block(monkeypatch, tmp_path, bundle, mps) -> str:
    vol_dir = tmp_path / "er"
    vol_dir.mkdir(parents=True, exist_ok=True)
    _patch_volume(monkeypatch, vol_dir)
    result = render_rainmaker(bundle, "uc13_preview", bundle["meta"]["company_name"], mps=mps)
    html = Path(result["html"]).read_text(encoding="utf-8")
    return _normalize_whitespace_between_tags(_extract_mps_block(html))


def _render_final_report_mps_block(monkeypatch, tmp_path, bundle, mps) -> str:
    vol_dir = tmp_path / "final"
    vol_dir.mkdir(parents=True, exist_ok=True)
    _patch_volume(monkeypatch, vol_dir)
    result = render_final_report(bundle, "uc13_preview", bundle["meta"]["company_name"], mps=mps)
    html = Path(result["html"]).read_text(encoding="utf-8")
    return _normalize_whitespace_between_tags(_extract_mps_block(html))


def test_mps_markup_identical_between_er_and_final_report(monkeypatch, tmp_path):
    bundle = _load_bundle()
    mps = _load_mps_run()

    er_block = _render_er_mps_block(monkeypatch, tmp_path, bundle, mps)
    final_block = _render_final_report_mps_block(monkeypatch, tmp_path, bundle, mps)

    assert er_block == final_block, _DRIFT_MESSAGE


def test_mps_markup_identical_degraded_seven_row_skeleton(monkeypatch, tmp_path):
    bundle = _load_bundle()

    er_block = _render_er_mps_block(monkeypatch, tmp_path, bundle, mps=None)
    final_block = _render_final_report_mps_block(monkeypatch, tmp_path, bundle, mps=None)

    assert er_block == final_block, _DRIFT_MESSAGE
    # Confirm this is genuinely the 7-row unscored skeleton, not an empty table.
    assert er_block.count("<tr>") + er_block.count('<tr class="mps-total-row">') >= 7
