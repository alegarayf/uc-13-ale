# T04 — `render_final_report()` and the `report=` context key

**Depends on:** T01 · **Closes:** — · **Est. size:** medium

Read [`../final_report_plan.md`](../final_report_plan.md) §7 and
[`tasks/README.md`](README.md) before starting.

## Goal

Add the render entry point for the final report to
`databricks/agents/exec_summary/renderers.py`, mirroring `render_rainmaker` exactly
in shape and discipline. This function renders; it never calls an LLM, never calls
`MPSAgent`, and never computes a projection it was not handed.

## Steps

### 1. `ReportRenderer.render()` — one additive keyword

Add `report: dict[str, Any] | None = None` to the signature
(`renderers.py:37-46`), defaulting to `None`, injected into the context as
`context["report"] = report` when not `None` — exactly like the existing `tldr` /
`rainmaker` / `narrative` / `mps` keys. **Additive: no existing caller changes
behaviour.** Extend the docstring with one clause naming the new key and pointing
at `final_report_view.py`.

Confirm (read, do not change) that `_autoescape_html_templates`
(`renderers.py:20-24`) already returns `True` for `final_report.html.j2`.

### 2. The PyMuPDF fallback page rect

`_html_to_pdf` (`renderers.py:125-161`) hardcodes `fitz.paper_rect("a4-l")` —
landscape, because the Rainmaker template is landscape. **The final report template
is A4 portrait** (`final_report.html.j2:46`: `@page { size: A4 portrait; … }`).

Add an optional `page_rect_spec: str = "a4-l"` parameter to `_html_to_pdf` and pass
`"a4"` from `render_final_report`. Keep the existing default so `render_rainmaker`
is untouched. Add a comment recording that PyMuPDF Story does not read the CSS
`@page` size, which is why the caller has to say it.

### 3. `render_final_report()`

```python
def render_final_report(
    bundle: dict[str, Any],
    catalog: str,
    company_name: str,
    narrative: dict[str, Any] | None = None,
    mps: dict[str, Any] | None = None,
    prior_mps: list[dict[str, Any]] | None = None,
    run_mode: str | None = None,
) -> dict[str, str]:
```

Behaviour, mirroring `render_rainmaker` (`renderers.py:182-238`):

1. `vol_dir = reports_volume_dir(catalog, company_name)`.
2. Build the report projection:
   `view = final_report_view(bundle, narrative=narrative, run_mode=run_mode)`.
   Import it **inside the function**, matching how `render_rainmaker` imports
   `rainmaker_view`.
3. Build the MPS projection from the **same** function the executive review uses —
   `rainmaker_view(bundle, mps_runs=[*(prior_mps or []), mps] if mps else (prior_mps or None))["mps"]`.
   Write this as a short, readable local; the ordering rule is what matters:
   **prior runs first, the current run last**, because `_mps_table` takes the
   verdict, threshold and commentary from `mps_runs[-1]`
   (`rainmaker_view.py:786-789`). Never build a second MPS projection of your own —
   that is how the two documents start disagreeing.
4. Render to `f"{vol_dir}/final_report.html"`, passing `report=view`,
   `narrative=narrative`, `mps=<the projection>` and
   `brand_logo_data_uri=_logo_data_uri()` (the template uses it at
   `final_report.html.j2:376`).
5. Write the HTML, print `[final_report] render html → …`.
6. Try `_html_to_pdf(html, f"{vol_dir}/final_report.pdf", page_rect_spec="a4")`.
7. Return `{"html": path}`, plus `{"pdf": path}` when an engine succeeded, plus
   `{"pdf_engine": engine}`.

### 4. The degraded-PDF contract — say it in the return value

WeasyPrint is the primary engine. **The PyMuPDF Story fallback honours neither SVG
nor flex layout**, so a PDF produced on that path is visually degraded. Do not ship
it silently:

- when `engine == "pymupdf"`, also return `"pdf_degraded": True` and print a clear
  warning naming the HTML as the faithful artifact;
- when no engine succeeded, return HTML only (no `pdf` key) — the existing
  behaviour.

Document this in the docstring so the caller knows the returned dict, not the file
system, is the source of truth about fidelity.

## Acceptance criteria

- [ ] `ReportRenderer.render()` gained exactly one optional kwarg; every existing
      call site is untouched.
- [ ] `render_rainmaker`'s behaviour is byte-identical — verify by running
      `pytest tests/test_rainmaker_render.py tests/test_rainmaker_golden_render.py -q`.
- [ ] `render_final_report` makes no LLM call and constructs no MPS projection of
      its own.
- [ ] The fallback engine renders the final report on a **portrait** rect.
- [ ] `pytest tests/ -q` passes.

## Close out

Nothing to tick yet — T07 supplies the render evidence. Append a one-line note to
plan §7 confirming the `report=` kwarg and the portrait rect landed.

Commit:

```
feat(final-report): add render_final_report and the report template context key
```
