"""Unit tests for the final diligence report render path (T07, plan §7).

Renders through :class:`agents.exec_summary.renderers.ReportRenderer` — the
production path — exactly as ``final_report_view.py`` + ``rainmaker_view.py``
feed it in ``renderers.render_final_report``. No bespoke Jinja environment,
no PDF engine: everything here asserts on the produced HTML string. The
real-engine pagination/spill check lives separately in
``test_final_report_pagination.py`` (plan §1.8 — it needs headless Chrome).

Four scenarios (task brief):
  (a) the illustrative bundle + a full seven-category MPS run
  (b) a nearly empty bundle (meta only)
  (c) no MPS run at all (mps=None, prior_mps=None)
  (d) two MPS runs (CIM-stage, then full-room)

Every scenario also asserts the MPS section appears exactly once and that no
score/gauge/headline leaks onto the cover (DoD-3) — the executive review and
this report must never start showing two different numbers.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from agents.exec_summary.final_report_view import final_report_view
from agents.exec_summary.rainmaker_view import rainmaker_view
from agents.exec_summary.renderers import ReportRenderer

from tests.fixtures.final_report_sample_bundle import BUNDLE, NARRATIVE

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "databricks" / "agents" / "exec_summary" / "templates"
_FINAL_REPORT_TEMPLATE = "final_report.html.j2"
_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# Same six take-box sites test_final_report_view.py exercises at the view
# layer (_ALL_SIX_TAKES_NARRATIVE/_DEGRADED_NARRATIVE) — duplicated here
# (small, no cross-test-module imports elsewhere in this repo) because this
# module proves the *template* guard actually suppresses the box, not just
# that the view dict comes back falsy.
_ALL_SIX_TAKES = {
    "business_take": "b", "financial_take": "f", "customer_take": "c",
    "kpi_take": "k", "quality_take": "q", "forecast_take": "fc",
}
_DEGRADED_TAKES = {key: None for key in _ALL_SIX_TAKES}


def _render(
    bundle: dict[str, Any],
    narrative: dict[str, Any] | None = None,
    mps_runs: list[dict[str, Any]] | None = None,
    run_mode: str | None = None,
) -> str:
    """Render exactly as ``render_final_report`` does, minus the file writes
    and the PDF engine (plan §7, task goal): same view, same MPS projection
    (``rainmaker_view``'s ``_mps_table`` — the one the executive review also
    uses), same ``ReportRenderer``."""
    view = final_report_view(bundle, narrative=narrative, run_mode=run_mode)
    mps_projection = rainmaker_view(bundle, mps_runs=mps_runs)["mps"]
    return ReportRenderer().render(
        bundle,
        _TEMPLATES_DIR / _FINAL_REPORT_TEMPLATE,
        report=view,
        narrative=narrative,
        mps=mps_projection,
    )


def _load_mps_verbose_run() -> dict[str, Any]:
    """The raw MPSAgent().score()-shaped run (plan §4) already used by the
    Rainmaker render tests for worst-case-plausible commentary — total 24.0,
    threshold 15, run_mode full_vdr_no_cim (above threshold)."""
    with open(_FIXTURES_DIR / "mps_run_verbose.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _cim_stage_mps_run(full_run: dict[str, Any]) -> dict[str, Any]:
    """A second, deliberately-low-scoring run standing in for the CIM-stage
    MPS pass — same 7 rubric keys as ``full_run`` (read off it rather than
    hardcoded, so a rubric change can't silently desync the two fixtures),
    every category scored 2 (product/1000 = 0.128, well under its own
    threshold of 10) so its total and threshold are both visibly different
    from the full-room run's (24.0 / 15) — the two runs must be
    distinguishable for the ordering assertions in scenario (d)."""
    keys = [c["key"] for c in full_run["categories"]]
    return {
        "mps_status": "success",
        "threshold": 10,
        "run_mode": "cim_only",
        "generated_at": "2026-08-01T00:00:00Z",
        "degraded_reason": None,
        "categories": [
            {
                "key": key,
                "display_name": key.replace("_", " ").title(),
                "score": 2,
                "rationale": "CIM-stage rationale, ahead of the full data room.",
                "counter_evidence": None,
                "sub_axis_notes": [],
                "evidence_basis": "document_derived",
                "evidence_refs": [],
                "confidence": "low",
            }
            for key in keys
        ],
    }


def _pages(html: str) -> list[str]:
    """Split the rendered document into its top-level ``<div class="page...">``
    blocks. Safe because these divs are siblings in final_report.html.j2,
    never nested — verified structurally: eleven such divs, one per page,
    matching the plan's eleven-page figure without core_business (§1.8)."""
    starts = [m.start() for m in re.finditer(r'<div class="page(?: mps-page)?">', html)]
    assert starts, "no top-level page div found"
    starts.append(len(html))
    return [html[starts[i] : starts[i + 1]] for i in range(len(starts) - 1)]


def _assert_single_mps_section(html: str) -> None:
    """DoD-3: the MPS appears exactly once, and nowhere else — no summary
    tile, no score, no gauge on the cover or any other page. Checked
    structurally (the table + its score/total markup), not by searching for
    the phrase "Minimum Pursuit Score" — that phrase legitimately also
    appears in the table-of-contents row naming the section."""
    assert html.count('<table class="mps-table">') == 1
    pages = _pages(html)
    mps_page_indices = [i for i, p in enumerate(pages) if "mps-table" in p]
    assert len(mps_page_indices) == 1
    for i, page in enumerate(pages):
        if i in mps_page_indices:
            continue
        assert "mps-table" not in page
        assert "mps-score-col" not in page
        assert "mps-total-row" not in page


# =========================================================================
# (a) The illustrative bundle + a full seven-category MPS run.
# =========================================================================


def test_final_report_render_illustrative_bundle_renders_known_fixture_values():
    mps_run = _load_mps_verbose_run()
    html = _render(BUNDLE, narrative=NARRATIVE, mps_runs=[mps_run], run_mode=BUNDLE["meta"]["run_mode"])

    # Figures only this fixture could have produced — the projection must
    # still be feeding them onto the page, not silently degrading.
    assert "Northwind Care Partners (ILLUSTRATIVE SAMPLE)" in html
    assert "$48.2M" in html  # headline_metrics.ltm_revenue tile
    assert "1,186" in html  # revenue_quality.client_count tile
    assert "Caregiver turnover at 38% sits above our 30% screen" in html  # executive.key_watchouts[0]
    assert "24.0" in html  # the verbose MPS run's own total
    assert "above threshold" in html

    _assert_single_mps_section(html)


# =========================================================================
# (b) A nearly empty bundle: meta and nothing else meaningful.
# =========================================================================

_EMPTY_BUNDLE = {
    "meta": {
        "company_name": "Empty Co (TEST FIXTURE)",
        "generated_at": "2026-09-08T00:00:00Z",
        "overall_confidence": "low",
        "vertical_overlay": "tech_services",
        "run_mode": "cim_only",
        "disclaimer_text": "NEARLY EMPTY BUNDLE — for T07 degradation coverage only.",
    }
}


def test_final_report_render_nearly_empty_bundle_omits_no_page_and_fabricates_nothing():
    html = _render(_EMPTY_BUNDLE, narrative=None, mps_runs=None, run_mode="cim_only")

    # No page is missing: all eleven page anchors present. Counting
    # `class="page` (not each section's heading text) because two of the
    # eleven pages (quality of earnings + legal) share one heading-less
    # page div — the div count is the actual page count, headings are not.
    assert html.count('<div class="page') == 11

    # Every section with no data shows its own "not extracted" state rather
    # than vanishing or rendering blank.
    for expected in (
        "Business overview not extracted.",
        "Revenue model not extracted.",
        "P&amp;L — not extracted from the data room.",
        "Concentration — not extracted from the data room.",
        "Retention metrics — not extracted from the data room.",
        "Operating KPIs — not extracted from the data room.",
        "QoE flags — not extracted from the data room.",
        "Legal flags — not extracted from the data room.",
        "Forecast assumptions — not extracted from the data room.",
        "Value creation levers — not extracted from the data room.",
        "Risk register — not extracted from the data room.",
        "Diligence questions — not extracted from the data room.",
    ):
        assert expected in html, f"missing not-extracted state: {expected!r}"

    # No zero was fabricated. Assert on the literal markup a None-converted-
    # to-0 bug would produce, not on truthiness: a fabricated bar would be an
    # SVG <rect> with a real (nonzero) width and a height of exactly "0" (or
    # vice-versa for a horizontal bar), and a fabricated headline figure
    # would show up as a bare "$0" or a standalone "0%" (as opposed to
    # "100%", "30%", etc., which are legitimate figures elsewhere). None of
    # the chart macros in final_report.html.j2 render *any* mark for a `None`
    # value — they call the `nodata()` macro instead — so this bundle, which
    # has no chartable data at all, must show none of these signatures.
    body = html[html.index("<body>") :]
    assert not re.search(r'<rect[^>]*\bwidth="0(?:\.0+)?"', body)
    assert not re.search(r'<rect[^>]*\bheight="0(?:\.0+)?"', body)
    assert "$0" not in body
    assert re.search(r"\b0%", body) is None

    _assert_single_mps_section(html)


# =========================================================================
# (c) No MPS run at all.
# =========================================================================


def test_final_report_render_no_mps_run_shows_unscored_skeleton():
    html = _render(BUNDLE, narrative=NARRATIVE, mps_runs=None, run_mode=BUNDLE["meta"]["run_mode"])

    # Rendered, not omitted.
    assert 'class="page mps-page"' in html
    assert html.count('<table class="mps-table">') == 1

    # Seven-row unscored skeleton: category rows use a bare `<tr>`, the total
    # row uses `<tr class="mps-total-row">` — a distinct string — so counting
    # bare `<tr>` inside <tbody> isolates the seven category rows.
    tbody = html[html.index("<tbody>") : html.index("</tbody>")]
    assert tbody.count("<tr>") == 7

    # Degraded footer note, no score column header rendered.
    assert '<div class="mps-footer-note">Not yet assessed in this preview.</div>' in html
    assert '<th class="mps-score-col"' not in html

    _assert_single_mps_section(html)


# =========================================================================
# (d) Two MPS runs: CIM-stage first, full data room last.
# =========================================================================


def test_final_report_render_two_mps_runs_orders_cim_first_full_room_last():
    full_run = _load_mps_verbose_run()
    cim_run = _cim_stage_mps_run(full_run)
    html = _render(BUNDLE, narrative=NARRATIVE, mps_runs=[cim_run, full_run], run_mode=BUNDLE["meta"]["run_mode"])

    assert html.count('<th class="mps-score-col"') == 2  # two column headers

    tbody = html[html.index("<tbody>") : html.index("</tbody>")]
    row_blocks = re.findall(r"<tr>(.*?)</tr>", tbody, flags=re.DOTALL)
    assert len(row_blocks) == 7
    for block in row_blocks:
        assert block.count('<td class="mps-score-col">') == 2  # every rubric row: two score cells

    total_block = re.search(r'<tr class="mps-total-row">(.*?)</tr>', tbody, flags=re.DOTALL).group(1)
    assert total_block.count('<td class="mps-score-col">') == 2  # exactly two total cells

    # The verdict/threshold/commentary shown belong to the full-room run
    # (rainmaker_view._mps_table takes them from mps_runs[-1]), not the
    # CIM-stage one — the two runs were built with different totals (0.1 vs
    # 24.0) and thresholds (10 vs 15) specifically so this is distinguishable.
    assert "0.1" in total_block
    assert "24.0" in total_block
    assert '<div class="mps-footer-note">Threshold 15 · above threshold</div>' in html
    assert "Threshold 10" not in html

    _assert_single_mps_section(html)


# =========================================================================
# T11 prose layer — added to scenarios (a) and (b).
# =========================================================================


def test_final_report_render_full_narrative_shows_six_takes_and_the_real_verdict():
    narrative = copy.deepcopy(NARRATIVE)
    narrative.update(_ALL_SIX_TAKES)
    mps_run = _load_mps_verbose_run()
    html = _render(BUNDLE, narrative=narrative, mps_runs=[mps_run], run_mode=BUNDLE["meta"]["run_mode"])

    assert html.count('class="take"') == 6
    assert "Pursue — proceed to management meetings, underwrite to run-rate not to plan" in html
    assert "Not yet concluded" not in html


def test_final_report_render_degraded_narrative_shows_zero_takes_and_no_missing_page():
    narrative = copy.deepcopy(_DEGRADED_TAKES)
    narrative["recommendation"] = None
    html = _render(_EMPTY_BUNDLE, narrative=narrative, mps_runs=None, run_mode="cim_only")

    assert html.count('class="take"') == 0
    assert "Not yet concluded" in html
    assert html.count('<div class="page') == 11  # a quieter report, not a broken one


def test_final_report_render_stray_take_for_an_empty_section_does_not_break_the_render():
    """A narrative that (incorrectly) supplies quality_take when the bundle
    has no qoe data at all must not crash the render. The template does not
    suppress this case — suppressing a take for a section with nothing to
    back it is T11's prompt-side responsibility (the LLM should not have
    produced quality_take here), not something final_report.html.j2 is
    expected to guard against. This test only proves the render survives it."""
    bundle = copy.deepcopy(_EMPTY_BUNDLE)
    narrative = {"quality_take": "Stray take with no qoe data behind it."}
    html = _render(bundle, narrative=narrative, mps_runs=None, run_mode="cim_only")

    assert "Stray take with no qoe data behind it." in html
    assert html.count('<div class="page') == 11


# =========================================================================
# T10b — page 8's *render* (plan §1.5 D-03, DoD-19): the forecast populated
# case puts plan periods / assumption / mapped severity class / footnote
# into the HTML, and the absent case degrades to "not extracted" with no
# fabricated zero. T07's tests never exercised report.forecast beyond the
# nearly-empty bundle's blanket "not extracted" assertions.
# =========================================================================

_FORECAST_BUNDLE = {
    "meta": _EMPTY_BUNDLE["meta"],
    "financials": {
        "currency": "$",
        "unit": "millions",
        "forecast_rows": [
            {"year": "FY2027", "revenue": "55.4"},
            {"year": "FY2028", "revenue": "64.1"},
        ],
        "forecast_assumptions": [
            {
                "assumption": "15% revenue growth, against an 8.4% three-year actual",
                "support": "Stretch",
                "test": "Reconcile to branch-level capacity and caregiver hiring plan",
            },
        ],
    },
}


def test_final_report_render_forecast_populated_renders_plan_periods_and_mapped_severity():
    html = _render(_FORECAST_BUNDLE, narrative=None, mps_runs=None, run_mode="cim_only")

    # Plan periods (both marked "P" since there is no historical table_rows
    # to distinguish them from) reach the chart.
    assert "FY2027P" in html
    assert "FY2028P" in html

    # Assumption text and test text reach the assumptions table.
    assert "15% revenue growth, against an 8.4% three-year actual" in html
    assert "Reconcile to branch-level capacity and caregiver hiring plan" in html

    # The MAPPED severity class, not just the word "Stretch" — the mapping
    # in _ASSUMPTION_SUPPORT_CLASS is the part that can silently break while
    # the word "Stretch" still renders fine.
    assert 'class="chip high">Stretch</span>' in html

    # §1.7: no plan period carries a projected EBITDA margin, so the
    # footnote states that as a fact about the plan.
    assert "The plan does not state a projected EBITDA margin." in html


def test_final_report_render_forecast_absent_shows_not_extracted_and_fabricates_nothing():
    bundle = copy.deepcopy(_EMPTY_BUNDLE)
    assert "financials" not in bundle

    html = _render(bundle, narrative=None, mps_runs=None, run_mode="cim_only")

    # The page still renders — it is not missing.
    assert html.count('<div class="page') == 11

    # "Not extracted" state, for both the chart and the assumptions table.
    assert "Revenue (P = plan) — not extracted from the data room." in html
    assert "Forecast assumptions — not extracted from the data room." in html

    # No plan period label, and no fabricated zero (a None-converted-to-0
    # bug would produce a bare "$0" or a standalone "0%", or an SVG <rect>
    # with a real width and a height of exactly "0" — none of which the
    # chart macro emits when it has no series at all).
    body = html[html.index("<body>") :]
    assert "FY20" not in body
    assert not re.search(r'<rect[^>]*\bwidth="0(?:\.0+)?"', body)
    assert not re.search(r'<rect[^>]*\bheight="0(?:\.0+)?"', body)
    assert "$0" not in body
    assert re.search(r"\b0%", body) is None
