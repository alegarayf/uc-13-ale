"""UC13 Orchestrator — Jinja markdown renderers (M1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, UndefinedError

from agents.orchestrator.paths import reports_volume_dir

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


class ReportRenderer:
    """Render orchestrator bundle dicts to markdown via Jinja2 templates."""

    def __init__(self, templates_dir: Path | None = None) -> None:
        base = templates_dir or _TEMPLATES_DIR
        self._env = Environment(
            loader=FileSystemLoader(str(base)),
            autoescape=False,
        )

    def render(self, bundle: dict[str, Any], template_path: str | Path) -> str:
        """Render *template_path* with root context ``bundle`` only."""
        template_name = Path(template_path).name
        try:
            template = self._env.get_template(template_name)
            return template.render(bundle=bundle)
        except UndefinedError as exc:
            raise UndefinedError(f"{template_name}: {exc}") from exc


def render(bundle: dict[str, Any], template_path: str | Path) -> str:
    """Module-level convenience wrapper for :meth:`ReportRenderer.render`."""
    return ReportRenderer().render(bundle, template_path)


def render_to_volume(
    bundle: dict[str, Any],
    catalog: str,
    company_name: str,
) -> dict[str, str]:
    """Render full report + TL;DR markdown files under the reports Volume dir."""
    vol_dir = reports_volume_dir(catalog, company_name)
    renderer = ReportRenderer()
    written: dict[str, str] = {}

    for log_key, template_file, out_file in (
        ("full_report", "full_report.md.j2", "full_report.md"),
        ("tldr", "tldr_one_pager.md.j2", "tldr_one_pager.md"),
    ):
        out_path = f"{vol_dir}/{out_file}"
        md = renderer.render(bundle, _TEMPLATES_DIR / template_file)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(md)
        print(f"[orchestrator] render {log_key} → {out_path}")
        written[log_key] = out_path

    return written
