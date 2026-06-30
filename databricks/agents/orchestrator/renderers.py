"""UC13 Orchestrator — Jinja markdown renderers (M1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, UndefinedError

from agents.orchestrator.demo_walkthrough import get_param
from agents.orchestrator.paths import reports_volume_dir
from agents.orchestrator.tldr_compress import compress_for_tldr

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_COMPRESSED_TLDR_TEMPLATE = "tldr_one_pager_compressed.md.j2"
_LEGACY_TLDR_TEMPLATE = "tldr_one_pager.md.j2"


class ReportRenderer:
    """Render orchestrator bundle dicts to markdown via Jinja2 templates."""

    def __init__(self, templates_dir: Path | None = None) -> None:
        base = templates_dir or _TEMPLATES_DIR
        self._env = Environment(
            loader=FileSystemLoader(str(base)),
            autoescape=False,
        )

    def render(
        self,
        bundle: dict[str, Any],
        template_path: str | Path,
        tldr: dict[str, Any] | None = None,
    ) -> str:
        """Render *template_path* with ``bundle``; optional ``tldr`` projection (D5-A)."""
        template_name = Path(template_path).name
        try:
            template = self._env.get_template(template_name)
            if tldr is None:
                return template.render(bundle=bundle)
            return template.render(bundle=bundle, tldr=tldr)
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
