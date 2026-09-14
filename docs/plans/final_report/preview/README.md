# Stakeholder preview — two artifacts

Generated from the shipped template and the illustrative bundle:

```bash
databricks/.venv/bin/python docs/plans/final_report/preview/build_previews.py
```

| File | What it is | Use it for |
|---|---|---|
| `UC13_Final_Report_ANNOTATED_PREVIEW.html` | The delivered preview, unchanged, plus a per-panel **Ready / Partial / Pending data** badge and a legend | Showing the design and being explicit about what is already wired |
| `UC13_Final_Report_TODAY_PREVIEW.html` | The same template rendered with every field that has no producer removed | Showing what a real run produces today, side by side with the above |
| `coverage.py` | The panel-by-panel audit both artifacts are built from | The work list |
| `build_previews.py` | The harness | Regenerating after T02 moves panels from pending to ready |

## The harness is validated

`build_previews.py` reproduces the delivered
`inputs/UC13_Final_Report_TEMPLATE_PREVIEW.html` **byte for byte** from
`sample_bundle.py` + `final_report_view.py` + `final_report.html.j2`. That is worth
more than a preview: it proves the template and the view module integrate through
the exact wiring the production renderer will use — `report=` for the projection,
`mps=` for the MPS page, `narrative=` for the prose, autoescape on for `*.html.j2`.
T04 is implementing a path that already demonstrably works.

## What the two documents are honest about

**The data is invented.** Both files describe a fictional home-care company. They
show format and analytical structure, not the output of a real run.

**The layout is real.** The template is copied into the package unchanged (T01),
so every line, chart and page break a stakeholder sees here is what ships.

**The gap is the data plumbing, not the design.** Of 34 panels, most are backed by
agents today. The pending ones fall into three groups:

1. **Probable renames** — `segment_performance` ≈ `revenue_by_segment`,
   `client_distribution` ≈ `clients`, `qoe.addbacks` ≈ `addback_schedule`. T02
   checks the shapes; if compatible, these light up with no agent work.
2. **The forecast page** — decision **D-03**. `forecast_agent` already extracts
   the plan rows and assumptions into `analysis.forecast`, but `BundleBuilder`
   reads six agent tables and forecast is not one of them, so the data never
   reaches the bundle. Recoverable cheaply; needs a decision.
3. **Genuinely absent** — `revenue_type_mix`, `growth_bridge`, `top_customers`,
   `customer_tenure`, `why_it_matters`, `coc_consent_count`, `meta.manifest`. Each
   needs an agent change to populate. Until then the panel says so.

**A pending panel is not a broken panel.** The report renders "not extracted from
the data room — see the gap list on the appendix page" and moves on. That is the
design rule: a page that honestly says a chart could not be built is acceptable; a
chart built from guessed data is not.

## Reading the difference

Open both side by side. The `TODAY` render is the same eleven pages — nothing is
missing, nothing collapses — with the unfed panels showing their empty state. The
distance between the two files is exactly the follow-up list in
[`../final_report_plan.md`](../final_report_plan.md) §9, and it shrinks as T02 and
D-03 land.

## Keeping this current

`coverage.py` is a snapshot of a verification done on 2026-09-03 against
`field_mapping.py`, `bundle_builder.py`, `populate.py` and `constants.py`. **T02
re-runs that audit properly** and is allowed to move entries from `pending` to
`ready` — when it does, update `coverage.py` and regenerate both files in the same
commit, so the artifact a stakeholder was shown never drifts from what the
pipeline actually does.
