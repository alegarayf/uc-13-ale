"""UC13 Orchestrator — Jinja markdown renderers (M1)."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, UndefinedError

from agents.exec_summary.demo_walkthrough import get_param
from agents.exec_summary.paths import reports_volume_dir
from agents.exec_summary.tldr_compress import compress_for_tldr

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_COMPRESSED_TLDR_TEMPLATE = "tldr_one_pager_compressed.md.j2"
_LEGACY_TLDR_TEMPLATE = "tldr_one_pager.md.j2"


def _autoescape_html_templates(template_name: str | None) -> bool:
    """Autoescape only ``*.html.j2`` templates (the Rainmaker one); the existing
    ``*.md.j2`` templates render plain Markdown and must stay unescaped —
    changing that would alter every existing report's output."""
    return bool(template_name) and template_name.endswith(".html.j2")


class ReportRenderer:
    """Render orchestrator bundle dicts to markdown/HTML via Jinja2 templates."""

    def __init__(self, templates_dir: Path | None = None) -> None:
        base = templates_dir or _TEMPLATES_DIR
        self._env = Environment(
            loader=FileSystemLoader(str(base)),
            autoescape=_autoescape_html_templates,
        )

    def render(
        self,
        bundle: dict[str, Any],
        template_path: str | Path,
        tldr: dict[str, Any] | None = None,
        rainmaker: dict[str, Any] | None = None,
        narrative: dict[str, Any] | None = None,
        brand_logo_data_uri: str | None = None,
    ) -> str:
        """Render *template_path* with ``bundle``; optional ``tldr`` projection (D5-A),
        ``rainmaker`` projection (Capa A — see rainmaker_view.py), ``narrative``
        (Capa B — see rainmaker_narrative.py), or ``brand_logo_data_uri`` (Rainmaker
        cover logo, base64 data URI)."""
        template_name = Path(template_path).name
        try:
            template = self._env.get_template(template_name)
            context: dict[str, Any] = {"bundle": bundle}
            if tldr is not None:
                context["tldr"] = tldr
            if rainmaker is not None:
                context["rainmaker"] = rainmaker
            if narrative is not None:
                context["narrative"] = narrative
            if brand_logo_data_uri is not None:
                context["brand_logo_data_uri"] = brand_logo_data_uri
            return template.render(**context)
        except UndefinedError as exc:
            raise UndefinedError(f"{template_name}: {exc}") from exc


def render(
    bundle: dict[str, Any],
    template_path: str | Path,
    tldr: dict[str, Any] | None = None,
) -> str:
    """Module-level convenience wrapper for :meth:`ReportRenderer.render`."""
    return ReportRenderer().render(bundle, template_path, tldr=tldr)


def render_to_volume(
    bundle: dict[str, Any],
    catalog: str,
    company_name: str,
) -> dict[str, str]:
    """Render full report + TL;DR markdown files under the reports Volume dir."""
    mode = get_param("TLDR_RENDER_MODE", "compressed")
    print(f"[orchestrator] TLDR_RENDER_MODE={mode}")

    vol_dir = reports_volume_dir(catalog, company_name)
    renderer = ReportRenderer()
    written: dict[str, str] = {}

    full_out = f"{vol_dir}/full_report.md"
    full_md = renderer.render(bundle, _TEMPLATES_DIR / "full_report.md.j2")
    with open(full_out, "w", encoding="utf-8") as fh:
        fh.write(full_md)
    print(f"[orchestrator] render full_report → {full_out}")
    written["full_report"] = full_out

    tldr_out = f"{vol_dir}/tldr_one_pager.md"
    if mode == "legacy":
        tldr_md = renderer.render(bundle, _TEMPLATES_DIR / _LEGACY_TLDR_TEMPLATE)
    else:
        tldr_view = compress_for_tldr(bundle)
        tldr_md = renderer.render(
            bundle,
            _TEMPLATES_DIR / _COMPRESSED_TLDR_TEMPLATE,
            tldr=tldr_view,
        )
    with open(tldr_out, "w", encoding="utf-8") as fh:
        fh.write(tldr_md)
    print(f"[orchestrator] render tldr → {tldr_out}")
    written["tldr"] = tldr_out

    return written


# ---------------------------------------------------------------------------
# Rainmaker "Opportunity Summary" template (CIM-first POC — plan §5, §5.5)
# ---------------------------------------------------------------------------

_RAINMAKER_TEMPLATE = "rainmaker_opportunity_summary.html.j2"


def _html_to_pdf(html: str, pdf_path: str) -> str | None:
    """Render *html* to *pdf_path*, trying WeasyPrint first (best CSS
    fidelity — page-break, flexbox, web fonts) and falling back to PyMuPDF
    Story (already a pipeline dependency; no extra system libraries needed —
    Apéndice A.5/R1 note WeasyPrint requires cairo/pango, which Databricks
    Serverless compute cannot install). Returns the engine name used, or
    ``None`` if neither is available/succeeds — callers should still ship
    the HTML output in that case.
    """
    try:
        import weasyprint  # noqa: PLC0415

        weasyprint.HTML(string=html).write_pdf(pdf_path)
        return "weasyprint"
    except Exception as exc:  # pragma: no cover - depends on system libs
        print(f"[rainmaker] WeasyPrint unavailable/failed ({exc!r}); falling back to PyMuPDF Story")

    try:
        import fitz  # noqa: PLC0415  (PyMuPDF)

        story = fitz.Story(html=html)
        writer = fitz.DocumentWriter(pdf_path)
        page_rect = fitz.paper_rect("a4")
        more = 1
        while more:
            device = writer.begin_page(page_rect)
            more, _ = story.place(page_rect)
            story.draw(device)
            writer.end_page()
        writer.close()
        return "pymupdf"
    except Exception as exc:  # pragma: no cover - depends on pymupdf availability
        print(f"[rainmaker] PyMuPDF Story also failed ({exc!r}); shipping HTML only")
        return None


_BRAND_LOGO_PATH = _TEMPLATES_DIR / "assets" / "rallyday_logo.jpeg"


def _logo_data_uri(logo_path: Path = _BRAND_LOGO_PATH) -> str | None:
    """Base64 data URI for the Rallyday cover logo (plan §3.5) — a filesystem
    ``src`` path is not reliable across WeasyPrint/PyMuPDF on Serverless, so
    the asset is embedded inline. Tolerant of a missing/unreadable asset:
    returns ``None`` rather than raising, so the cover simply omits the logo
    (never fabricates a placeholder)."""
    try:
        data = logo_path.read_bytes()
    except OSError as exc:
        print(f"[rainmaker] brand logo unavailable ({exc!r}); rendering cover without it")
        return None
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def render_rainmaker(
    bundle: dict[str, Any],
    catalog: str,
    company_name: str,
    narrative: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Render the Rainmaker "Opportunity Summary" (HTML + PDF, 3 pages).

    Unlike :func:`render_to_volume` (the Rev3 prose bridge), this produces
    ONLY the visual summary — no ``full_report`` — matching the CIM-first
    preview's scope (no Cross-Analysis/Orchestrator memo; plan §5.5).

    ``narrative`` is Capa B's output (see ``rainmaker_narrative.synthesize_
    rainmaker_narrative``) — computed by the caller (entry point) so this
    function stays render-only and never makes an LLM call itself. Pass
    ``None`` (default) to render with the deterministic bundle fallbacks
    only (no prose synthesis) — this never breaks the render.

    Returns ``{"html": path}`` plus ``{"pdf": path}`` when a PDF engine
    succeeded.
    """
    from agents.exec_summary.rainmaker_view import rainmaker_view as _rainmaker_view

    vol_dir = reports_volume_dir(catalog, company_name)
    renderer = ReportRenderer()
    view = _rainmaker_view(bundle)
    logo_data_uri = _logo_data_uri()

    html_out = f"{vol_dir}/rainmaker_opportunity_summary.html"
    html = renderer.render(
        bundle,
        _TEMPLATES_DIR / _RAINMAKER_TEMPLATE,
        rainmaker=view,
        narrative=narrative,
        brand_logo_data_uri=logo_data_uri,
    )
    with open(html_out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"[rainmaker] render html → {html_out}")

    written: dict[str, str] = {"html": html_out}

    pdf_out = f"{vol_dir}/executive_summary.pdf"
    engine = _html_to_pdf(html, pdf_out)
    if engine:
        written["pdf"] = pdf_out
        print(f"[rainmaker] render pdf → {pdf_out} (engine={engine})")

    return written
