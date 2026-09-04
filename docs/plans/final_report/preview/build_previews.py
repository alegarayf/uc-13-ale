"""Build the two stakeholder artifacts from the shipped template.

    python3 docs/plans/final_report/preview/build_previews.py

Throwaway harness, deliberately outside ``databricks/`` — the production render
path is ``ReportRenderer`` + ``render_final_report()``, not this script. It exists
so the two artifacts can be regenerated after T02 moves panels from "pending" to
"ready", rather than being hand-edited HTML that goes stale the moment the audit
lands.

Produces, in this directory:

``UC13_Final_Report_ANNOTATED_PREVIEW.html``
    The delivered illustrative preview with a per-panel badge — READY / PARTIAL /
    PENDING — and a legend explaining what each means. This is the "design intent,
    honestly labelled" artifact.

``UC13_Final_Report_TODAY_PREVIEW.html``
    The same template rendered from the same illustrative bundle with every field
    that has no producer removed. This is what the document looks like on real
    data today: the layout intact, the unfed panels showing their "not extracted"
    state. Prose and MPS are left in, because both are covered by the plan (T11
    and the existing MPS agent) — the point of this render is to isolate the
    *data* gap, which is the part that needs agent work.
"""

from __future__ import annotations

import copy
import html
import importlib.util
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_INPUTS = _HERE.parent / "inputs"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sample = _load("_sample_bundle", _INPUTS / "sample_bundle.py")
view_mod = _load("_final_report_view", _INPUTS / "final_report_view.py")
coverage = _load("_coverage", _HERE / "coverage.py")


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def _render(bundle: dict, narrative: dict, mps: dict) -> str:
    from jinja2 import Environment, FileSystemLoader

    env = Environment(
        loader=FileSystemLoader(str(_INPUTS)),
        autoescape=True,   # matches renderers._autoescape_html_templates for *.html.j2
    )
    report = view_mod.final_report_view(bundle, narrative=narrative)
    return env.get_template("final_report.html.j2").render(
        bundle=bundle, report=report, narrative=narrative, mps=mps,
    )


def _strip(bundle: dict) -> dict:
    """Remove every bundle path with no producer today (coverage.STRIP_PATHS)."""
    out = copy.deepcopy(bundle)
    for path in coverage.STRIP_PATHS:
        node = out
        for key in path[:-1]:
            node = node.get(key) if isinstance(node, dict) else None
            if node is None:
                break
        if isinstance(node, dict):
            node.pop(path[-1], None)
    for list_key, item_key in coverage.STRIP_ITEM_KEYS:
        for item in out.get(list_key) or []:
            if isinstance(item, dict):
                item.pop(item_key, None)
    return out


# ---------------------------------------------------------------------------
# Annotation
# ---------------------------------------------------------------------------

_BADGE_CSS = """
<style id="ng-annotation">
  .ng-badge { display:inline-block; margin-left:2mm; padding:0.3mm 1.4mm; border-radius:1mm;
              font-size:6.5pt; font-weight:bold; letter-spacing:0.04em; text-transform:uppercase;
              vertical-align:middle; font-family:Arial,Helvetica,sans-serif; }
  .ng-ready   { background:#1E7A46; color:#fff; }
  .ng-partial { background:#C2600D; color:#fff; }
  .ng-pending { background:#9B1C1C; color:#fff; }
  /* Its own light chip rather than inherited colour: several of these headings sit
     on a navy or orange band, where any dark note text disappears. */
  .ng-note    { display:block; margin:0.8mm 0 0 0; padding:0.4mm 1.2mm; border-radius:0.8mm;
                background:rgba(255,255,255,0.9); color:#3A3A3A; font-size:6.8pt;
                font-style:italic; font-family:Arial,Helvetica,sans-serif; font-weight:normal;
                text-transform:none; letter-spacing:0; }
  .ng-legend  { border:0.5pt solid #1F3864; background:#F2F4F7; padding:3mm 4mm; margin:0 0 5mm 0;
                font-family:Arial,Helvetica,sans-serif; font-size:8pt; color:#1A1A1A; }
  .ng-legend h4 { margin:0 0 1.5mm 0; color:#1F3864; font-size:10pt; }
  .ng-legend p  { margin:0 0 1.5mm 0; }
  .ng-legend ul { margin:0; padding-left:5mm; }
</style>
"""

_LEGEND = """
<div class="ng-legend">
  <h4>Reading this preview</h4>
  <p><strong>The data in this document is invented.</strong> It describes a fictional company and exists to
  show the format, the layout and the analytical structure of the final diligence report — not the output of a
  real run.</p>
  <p>Each panel carries a badge saying whether the pipeline can fill it from real data today:</p>
  <ul>
    <li><span class="ng-badge ng-ready">Ready</span> an agent populates this field today.</li>
    <li><span class="ng-badge ng-partial">Partial</span> the panel renders, but one of its sub-fields has no producer yet.</li>
    <li><span class="ng-badge ng-pending">Pending data</span> no agent populates this field yet. On a real run the
    panel renders its "not extracted" state — the report says plainly that it could not build the chart rather
    than drawing one from guessed numbers.</li>
  </ul>
  <p>Counts: __COUNTS__. The companion file
  <code>UC13_Final_Report_TODAY_PREVIEW.html</code> shows the same template rendered with every
  <em>pending</em> field removed — i.e. what this document looks like on today's agent output.</p>
</div>
"""


def _annotate(source_html: str) -> str:
    out = source_html
    unmatched: list[str] = []

    for _page, heading, status, path, note in coverage.PANELS:
        # Most panels are titled by an h2/h3/h4. The cover's recommendation block
        # is titled by a <span class="label"> instead, so fall back to that.
        patterns = (
            r"(<(h[234])(?![^>]*ng-annotated)[^>]*>)((?:(?!</\2>).)*?"
            + re.escape(heading)
            + r"(?:(?!</\2>).)*?)(</\2>)",
            r'(<(span) class="label">)(' + re.escape(heading) + r")(</\2>)",
        )
        match = None
        for raw in patterns:
            match = re.compile(raw, re.DOTALL).search(out)
            if match:
                break
        if not match:
            unmatched.append(heading)
            continue
        label = {"ready": "Ready", "partial": "Partial", "pending": "Pending data"}[status]
        detail = html.escape(f"{path}{' — ' + note if note else ''}")
        badge = f'<span class="ng-badge ng-{status}">{label}</span>'
        annotated = (
            f"{match.group(1)}{match.group(3)}{badge}"
            f'<span class="ng-note">{detail}</span>{match.group(4)}'
        )
        out = out[: match.start()] + annotated + out[match.end():]

    counts = coverage.counts()
    legend = _LEGEND.replace(
        "__COUNTS__",
        f"{counts['ready']} ready · {counts['partial']} partial · {counts['pending']} pending",
    )

    out = out.replace("</head>", _BADGE_CSS + "</head>", 1)
    body = re.search(r"<body[^>]*>", out)
    if body:
        out = out[: body.end()] + legend + out[body.end():]

    if unmatched:
        print("  [warn] headings not found in the render, badge skipped:")
        for heading in unmatched:
            print(f"         · {heading}")
    return out


# ---------------------------------------------------------------------------

def main() -> None:
    full_html = _render(sample.BUNDLE, sample.NARRATIVE, sample.MPS)

    annotated = _annotate(full_html)
    annotated_path = _HERE / "UC13_Final_Report_ANNOTATED_PREVIEW.html"
    annotated_path.write_text(annotated, encoding="utf-8")
    print(f"  annotated → {annotated_path}")

    today_html = _render(_strip(sample.BUNDLE), sample.NARRATIVE, sample.MPS)
    today_path = _HERE / "UC13_Final_Report_TODAY_PREVIEW.html"
    today_path.write_text(today_html, encoding="utf-8")
    print(f"  today     → {today_path}")

    counts = coverage.counts()
    print(f"  panels: {counts['ready']} ready · {counts['partial']} partial · {counts['pending']} pending")


if __name__ == "__main__":
    main()
