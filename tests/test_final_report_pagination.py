"""Real-engine pagination check for the final diligence report (T07, plan §1.8).

Separate module from ``test_final_report_render.py`` on purpose: this is a
real render through headless Chrome + PyMuPDF, not a unit test, and it needs
to be skippable on a machine without Chrome — following the same
skip-with-reason convention as the 38 pre-existing WeasyPrint-dependent skips
(``test_rainmaker_render.py::_require_production_pdf_engine``). Chrome *is*
present on this machine, so this module must not become a silent skip here.

Why headless Chrome and not WeasyPrint or PyMuPDF Story (plan §1.8):
  * WeasyPrint imports fine but dies on ``write_pdf`` with
    ``OSError: cannot load library 'libgobject-2.0-0'`` on this machine —
    the same missing system library behind the pre-existing skips.
  * PyMuPDF Story (the production fallback for a Serverless container that
    can't install cairo/pango either) honours neither ``@page`` nor flex —
    it reported 16 pages for a document that is really 12. A before/after
    comparison through it is not evidence of anything.
  * Headless Chrome honours ``@page`` and is installed here. It writes the
    PDF and does not exit on its own, so the process is backgrounded, the
    output file polled for a non-empty size, then killed; the page count and
    per-page text come from ``fitz`` (PyMuPDF), used here only as a *reader*.
"""

from __future__ import annotations

import copy
import shutil
import subprocess
import time
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

_CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)


def _find_chrome() -> str | None:
    for candidate in _CHROME_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")


_CHROME = _find_chrome()

pytestmark = pytest.mark.skipif(
    _CHROME is None,
    reason="headless Chrome not found on this machine (plan §1.8) — this is the ONLY engine this "
    "check trusts; do not fall back to WeasyPrint or PyMuPDF Story here, both are ruled out with evidence",
)


def _print_to_pdf(html_path: Path, pdf_path: Path, profile_dir: Path, timeout: float = 20.0) -> None:
    """Chrome writes the PDF and then keeps running — background it, poll
    for the output file, then kill it (plan §1.8's documented pattern)."""
    proc = subprocess.Popen(
        [
            _CHROME,
            "--headless=new",
            "--disable-gpu",
            f"--user-data-dir={profile_dir}",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path}",
            f"file://{html_path}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if pdf_path.exists() and pdf_path.stat().st_size > 0:
                return
            time.sleep(0.2)
        raise TimeoutError(f"headless Chrome did not produce {pdf_path} within {timeout}s")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _render(narrative: dict[str, Any] | None, mps_runs: list[dict[str, Any]] | None) -> str:
    view = final_report_view(BUNDLE, narrative=narrative, run_mode=BUNDLE["meta"]["run_mode"])
    mps_projection = rainmaker_view(BUNDLE, mps_runs=mps_runs)["mps"]
    return ReportRenderer().render(
        BUNDLE,
        _TEMPLATES_DIR / _FINAL_REPORT_TEMPLATE,
        report=view,
        narrative=narrative,
        mps=mps_projection,
    )


def _load_mps_verbose_run() -> dict[str, Any]:
    with open(_FIXTURES_DIR / "mps_run_verbose.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


_CORE_BUSINESS = [
    "Non-medical home care platform across three metro markets, billed hourly to private-pay clients.",
    "1,186 active clients served by 1,888 W-2 caregivers out of 7 branch offices.",
    "Founded 2009, owner-operated; first institutional capital sought in this process.",
]


def test_business_page_core_business_does_not_spill_an_orphan_sheet(tmp_path):
    """The regression this task exists to fix: T11 wired ``core_business``
    onto the business page and it pushed the page's own footer onto a new,
    otherwise-blank page 4 (measured during the T11 review: 11 pages
    without it, 12 with it, page 4 carrying 204 characters of footer and
    nothing else). The fix folds the three lines into the existing "What
    The Business Does" card instead of a second bordered box, plus a small
    amount of CSS tightening elsewhere on the same page — never a raised
    cap, a shrunk font, or dropped content (DoD-16).

    This test renders both with and without ``core_business`` through the
    real engine and asserts, either way, that no page is an orphan (under
    ~250 characters of extracted text and carrying nothing but the running
    header/footer chrome) — the criterion Hector set 2026-09-08, replacing
    the earlier page-count ceiling. Twelve pages would be fine; a sheet with
    only chrome on it is not.
    """
    mps_run = _load_mps_verbose_run()
    footer_fragment = BUNDLE["meta"]["disclaimer_text"]
    fitz = pytest.importorskip("fitz", reason="PyMuPDF not available in this env")

    for label, with_core_business in (("without_core_business", False), ("with_core_business", True)):
        narrative = copy.deepcopy(NARRATIVE)
        if with_core_business:
            narrative["core_business"] = _CORE_BUSINESS
        html = _render(narrative, mps_runs=[mps_run])

        html_path = tmp_path / f"{label}.html"
        html_path.write_text(html, encoding="utf-8")
        pdf_path = tmp_path / f"{label}.pdf"
        _print_to_pdf(html_path, pdf_path, tmp_path / f"{label}-profile")

        doc = fitz.open(str(pdf_path))
        assert [round(v) for v in (doc[0].rect.width, doc[0].rect.height)] == [595, 842]  # A4 portrait

        page_texts = [" ".join(page.get_text().split()) for page in doc]
        counts = [len(t) for t in page_texts]
        # Required by the close-out (plan §1.8 / T07 acceptance criteria):
        # the per-page character counts must be visible, not hidden in a
        # boolean.
        print(f"[T07 pagination] {label}: {doc.page_count} pages, per-page chars: {counts}")

        orphans = [i + 1 for i, t in enumerate(page_texts) if len(t) < 250 and footer_fragment in t]
        assert not orphans, f"{label}: orphan sheet(s) carrying only chrome at page(s) {orphans}: counts {counts}"

        if with_core_business:
            for line in _CORE_BUSINESS:
                assert line in html  # core_business still renders after the fix (DoD-16)
