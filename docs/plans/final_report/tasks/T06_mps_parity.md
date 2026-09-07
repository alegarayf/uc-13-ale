# T06 — MPS markup: one copy, and the test that keeps it one

**Depends on:** T04 (**D-01 approved 2026-09-07 — Path A**) · **Closes:** DoD-9 · **Est. size:** medium

Read [`../final_report_plan.md`](../final_report_plan.md) §5 and
[`tasks/README.md`](README.md) before starting.

> **D-01 is APPROVED (Hector, 2026-09-07): take Path A, the shared partial.**
> Path B below is now the **fallback**, used only if Step 1's evidence fails —
> i.e. if any of the three before/after render diffs comes back non-empty. In that
> case, stop, keep the replica, ship the parity test, and record why in plan §5.
> Do not edit the template to force a clean diff.

## The problem

`final_report.html.j2` carries a faithful **replica** of the executive review's
`mps-table` block and its CSS (ER original at
`rainmaker_opportunity_summary.html.j2:94-110` for the CSS and `:323-380` for the
section). Two copies of the same markup drift. Whichever path is taken, the parity
test ships.

---

## Step 1 — the evidence for D-01 (do this first, either way)

Produce a before/after diff proving the include swap changes nothing:

1. Write a throwaway script under the scratchpad (**not** in the repo) that renders
   `rainmaker_opportunity_summary.html.j2` from
   `tests/fixtures/final_report_sample_bundle.py` plus a synthetic MPS run
   covering all seven rubric rows, and saves the HTML as `before.html`.
2. Perform the extraction on a scratch copy of the templates directory.
3. Render again from the scratch copy → `after.html`.
4. `diff before.html after.html` must be **empty**.
5. Repeat with the **degraded** MPS case (`mps_runs=[]` → 7 unscored rows) and the
   **two-run** case. All three diffs must be empty.

Write the result — the three diffs and the exact commands — into plan §5 under
D-01, and stop for the decision if you do not already have it.

---

## Path A — D-01 approved: extract the shared partial

1. Create `databricks/agents/exec_summary/templates/_mps_page.html.j2` containing
   the MPS `<section class="page mps">` block. Decide explicitly whether the CSS
   moves with it:
   - If both templates' surrounding CSS is compatible, move the `table.mps-table`
     rules into the partial inside a `<style>` block **only if** that produces
     byte-identical output in Step 1's diff. Otherwise leave the CSS duplicated in
     each template's head and extract the markup only — and say so in a comment at
     the top of the partial, because a reader will ask.
2. In **both** `final_report.html.j2` and `rainmaker_opportunity_summary.html.j2`,
   replace the block with `{% include "_mps_page.html.j2" %}`.
3. The edit to `rainmaker_opportunity_summary.html.j2` must be **exactly** the
   block→include swap. Nothing else in that file may change — it is otherwise
   read-only, and this is the one authorised exception.
4. Re-run Step 1's diffs against the real templates. All three must be empty.
5. Run `pytest tests/test_rainmaker_render.py tests/test_rainmaker_golden_render.py -q`
   — the golden render test is the strongest guard here and must pass unchanged.

## Path B — D-01 refused: keep the replica

Change no template. The parity test below is then the only thing standing between
the two copies and drift, so write it strictly.

---

## Both paths — the parity test

Add to `tests/test_final_report_render.py` (or a dedicated
`tests/test_mps_parity.py` if that reads better alongside the existing files):

- Render **both** documents from the **same** bundle and the **same single** MPS
  run.
- Extract the MPS section from each rendered HTML — anchor on
  `<section class="page mps">` … its closing `</section>`, or on the
  `<table class="mps-table">` element. Do not regex loosely across the whole file.
- Normalise only whitespace between tags. Do **not** normalise attributes, class
  names, or cell contents — those are exactly what drift looks like.
- Assert the two extracts are identical.
- Add a second case with the **degraded** run (`mps=None`) asserting both documents
  render the same 7-row unscored skeleton.
- The failure message must say what to do: *"the MPS block has drifted between the
  executive review and the final report — see plan §5 / T06."*

## Acceptance criteria

- [ ] Step 1's three diffs are recorded in plan §5, empty, with the commands used.
- [ ] Path A only: `git diff databricks/agents/exec_summary/templates/rainmaker_opportunity_summary.html.j2`
      shows **only** the block→include swap.
- [ ] Path A only: `pytest tests/test_rainmaker_golden_render.py -q` passes with no
      golden file regenerated.
- [ ] The parity test fails if you deliberately edit one copy of the block (try it,
      then revert — a parity test that cannot fail is not a parity test).
- [ ] `pytest tests/ -q` passes.

## Close out

In [`../final_report_plan.md`](../final_report_plan.md):

- Record under §5 which path was taken and who decided.
- Tick **DoD-9** in §10 with that record as evidence.

Commit (pick the one that matches the path taken):

```
refactor(final-report): extract the MPS page into a shared template partial
```
```
test(final-report): assert MPS markup parity between the two documents
```
