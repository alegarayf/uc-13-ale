# T10b — Assert that page 8 actually renders the forecast

**Depends on:** T07, T10 · **Closes:** DoD-19 · **Est. size:** small

> **Read the plan selectively.** Only **§1.5** (D-03, how the forecast reaches the
> bundle) and **§10** (DoD-15 / DoD-19) apply here. Locate them with
> `grep -n "^## " ../final_report_plan.md` — do not read the file whole.

Read [`README.md`](README.md) (it is short) before starting.

## Why this task exists

DoD-15 says: *"Page 8 renders the plan-vs-history chart and the assumptions table
from `{catalog}.analysis.forecast` (D-03), and degrades to 'not extracted' when
that table is absent or empty."*

It was ticked during T10 on the evidence that existed — T05's tests for
`_load_forecast` (the **reader**) and T02/T05's tests for the §1.7 footnote.
**Nothing asserts the render.** `tests/test_final_report_render.py` mentions
"forecast" once, and only inside a narrative take string.

The behaviour is correct: verified by hand during the T10 review, injecting
`financials.forecast_rows` and `forecast_assumptions` into a bundle and rendering
through `render_final_report` — the plan period `2026P`, the assumption text, its
`Stretch` verdict and its test all reach the HTML. So this task pins working
behaviour rather than fixing a defect. Without it, a regression on the most
data-starved page in the report would be silent, and the DoD box that is supposed
to catch that is already ticked.

## Steps

### 1. One render test for the populated case

Add to `tests/test_final_report_render.py`, using its existing fixtures and
render path (through `ReportRenderer` / `render_final_report`, not a bespoke
Jinja environment):

- Build a bundle with `financials.forecast_rows` — at least two plan periods with
  a `year` and a `revenue`, and **no** `ebitda_margin_pct` (that is §1.7: the
  agent never projects margin) — and `financials.forecast_assumptions` with at
  least one entry carrying an `assumption`, a `support` of `Stretch`, and a
  `test`.
- Assert the rendered HTML contains: each plan period's label, the assumption
  text, the `test` text, and the severity class that
  `_ASSUMPTION_SUPPORT_CLASS` maps `Stretch` to. Assert on the **mapped class**,
  not just the word "Stretch" — the mapping is the part that could silently
  break.
- Assert the §1.7 footnote clause is present, since these plan rows carry no
  margin.

### 2. One render test for the absent case

Same bundle with `forecast_rows` and `forecast_assumptions` removed entirely:

- the page still renders and is not missing;
- its "not extracted" state is shown;
- **no plan period label and no fabricated zero** appears — assert on the markup
  a `None → 0` bug would produce, the way T07's nearly-empty-bundle test does,
  not on truthiness.

### 3. Prove both tests discriminate

Two mutations, applied one at a time, each of which must make a test fail:

```bash
V=databricks/agents/exec_summary/final_report_view.py
git status --porcelain          # clean first

# (a) make _forecast ignore the plan rows entirely
#     (drop forecast_rows from the rows it charts)
PYTHONDONTWRITEBYTECODE=1 pytest tests/test_final_report_render.py -q -p no:cacheprovider
#     ^ MUST fail
git checkout -- $V

# (b) make the Supported/Plausible/Stretch mapping return a constant class
PYTHONDONTWRITEBYTECODE=1 pytest tests/test_final_report_render.py -q -p no:cacheprovider
#     ^ MUST fail
git checkout -- $V

find databricks -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
git status --porcelain          # clean again
```

Paste both failure summaries into the close-out. If either mutation still passes,
the corresponding assertion is not testing what it claims.

### 4. Tests only

`git diff --stat` must show nothing under `databricks/`. If writing these reveals
a real defect in the forecast render path, **stop and report it** — do not fix it
here.

## Acceptance criteria

- [ ] Populated-case test asserts plan periods, assumption text, `test` text, the
      **mapped** severity class, and the §1.7 footnote clause.
- [ ] Absent-case test asserts the page renders, shows "not extracted", and
      fabricates no zero and no plan label.
- [ ] Both mutations fail, with output in the close-out.
- [ ] Nothing under `databricks/` changed; working tree clean before the commit.
- [ ] `pytest tests/ -q` passes; counts from `pytest --collect-only -q`.

## Close out

In [`../final_report_plan.md`](../final_report_plan.md) §10:

- Tick **DoD-19** with both mutation failure summaries.
- Append one line to **DoD-15**'s evidence noting that its render half is closed
  by DoD-19, and that when it was originally ticked the evidence covered the
  reader and the footnote only. Leave DoD-15 ticked — do not rewrite history.

Commit:

```
test(final-report): assert page 8 renders the forecast it is given
```
