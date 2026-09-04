# T07 — `test_final_report_render.py`: four scenarios

**Depends on:** T05, T06 · **Closes:** DoD-3, evidence for DoD-2 · **Est. size:** medium

Read [`../final_report_plan.md`](../final_report_plan.md) and
[`tasks/README.md`](README.md) before starting.

## Goal

Prove the template renders — without raising, without a missing page, and without a
fabricated figure — across the four bundle/MPS combinations that matter. Model the
file on `tests/test_rainmaker_render.py`.

Render through `ReportRenderer` (the production path), not through a bespoke Jinja
environment: the autoescape predicate and the template search path are part of what
is being tested. Do not invoke a PDF engine — assert on the HTML.

## The four scenarios

### (a) The illustrative bundle

`tests/fixtures/final_report_sample_bundle.py` + a full seven-category MPS run.
Renders without raising. Spot-assert that a handful of known fixture values appear
in the output (pick figures that only the fixture could have produced, so the test
fails if the projection silently stops feeding the page).

### (b) A nearly empty bundle

A bundle with `meta` and nothing else meaningful. Assert:

- it renders without raising;
- **no page is missing** — every one of the eleven pages' anchors is present. Count
  `class="page` occurrences, or assert on each section's heading text; pick one and
  say in a comment why that anchor was chosen;
- every section that has no data shows its "not extracted" state;
- **no `0` was fabricated**: assert the absence of a zero-height bar and of a
  literal `$0` / `0%` that the fixture never supplied. Be specific — assert on the
  markup a `None` bar would produce if someone "fixed" it to `0`.

### (c) No MPS run

`mps=None`, `prior_mps=None`. Assert:

- the MPS page is **rendered, not omitted**;
- it shows the seven-row unscored skeleton (seven `<tr>` in the MPS table body);
- the degraded footer note is present;
- no score column header is rendered.

### (d) Two MPS runs

`prior_mps=[cim_run]`, `mps=full_run`. Assert:

- exactly **two** score column headers, in the order CIM-first then full-room —
  the current run must be last, because `_mps_table` takes the verdict, threshold
  and commentary from `mps_runs[-1]` (`rainmaker_view.py:786-789`);
- exactly **two** total cells;
- every rubric row has exactly two score cells;
- the verdict, threshold and commentary shown belong to the **full-room** run —
  construct the two runs with different totals and thresholds so this is
  distinguishable.

## The MPS appears exactly once

In every scenario, assert the rendered final report contains exactly **one**
MPS section (one `<table class="mps-table">`) and that no MPS score, gauge or
headline appears on the cover or anywhere else. This is DoD-3 and it is easy to
regress by "helpfully" adding a summary tile.

## Acceptance criteria

- [ ] All four scenarios pass.
- [ ] The one-MPS-section assertion runs in all four.
- [ ] `pytest tests/ -q` passes.
- [ ] No test writes into a Volume path; render to a tmp dir
      (`tmp_path` / monkeypatched `reports_volume_dir`), following whatever
      `tests/test_rainmaker_render.py` already does.

## Close out

In [`../final_report_plan.md`](../final_report_plan.md) §10:

- Tick **DoD-3** with the scenario-(c)/(d) assertions as evidence.
- Append the two-column assertion as evidence under **DoD-2** (T09 ticks it).

Commit:

```
test(final-report): cover the four render scenarios and MPS column behaviour
```
