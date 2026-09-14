# T01 — Land the attached inputs in their final locations

**Depends on:** nothing · **Closes:** DoD-8 · **Est. size:** small

Read [`../final_report_plan.md`](../final_report_plan.md) and
[`tasks/README.md`](README.md) before starting.

## Goal

Move the three shipped artifacts from `docs/plans/final_report/inputs/` into the
places the production code will import them from, **without changing their
content**, and prove they import and render-parse cleanly. No wiring yet — nothing
calls them after this task.

## Context you need

- `docs/plans/final_report/inputs/` currently holds:
  `final_report.html.j2`, `final_report_view.py`, `sample_bundle.py`,
  `UC13_Final_Report_TEMPLATE_PREVIEW.html`.
- `inputs/` is the archive of what was delivered. **Do not delete it** — leave the
  originals in place so a later diff can prove the copies are faithful.
- The sample bundle contains **invented data for a fictional company**. It must
  never end up inside the shipped `databricks/` package.

## Steps

1. **Copy** (not move) the template:
   `docs/plans/final_report/inputs/final_report.html.j2`
   → `databricks/agents/exec_summary/templates/final_report.html.j2`
   Byte-identical. Verify with `diff`.

2. **Copy** the view module:
   `docs/plans/final_report/inputs/final_report_view.py`
   → `databricks/agents/exec_summary/final_report_view.py`
   Byte-identical for now. T02 is the only task allowed to edit its field reads.

3. **Copy** the sample bundle to the fixtures directory, renamed so its purpose is
   unmistakable:
   `docs/plans/final_report/inputs/sample_bundle.py`
   → `tests/fixtures/final_report_sample_bundle.py`
   Create `tests/fixtures/__init__.py` **only if** `tests/fixtures/` does not
   already exist as a package; check first and match whatever convention the
   directory already uses.

4. **Do not copy** `UC13_Final_Report_TEMPLATE_PREVIEW.html` anywhere. It is a
   rendered reference for humans and stays in `inputs/`.

5. Add the `.gitignore` negation so this plan and these tasks are tracked. `docs/*`
   is ignored repo-wide (line ~280). **This was already applied when the plan was
   written** — verify it is still there and move on if so; the block below is what
   it should look like:

   ```gitignore
   # docs/* is ignored, but the UC13 final-report plan and its task files are
   # DoD artifacts for feature/uc13-final-report-and-progress — they must survive
   # a fresh clone.
   !docs/plans/
   !docs/plans/final_report/
   !docs/plans/final_report/**
   ```

   Verify with `git check-ignore -v docs/plans/final_report/final_report_plan.md`
   — it must now report **no match** (exit code 1).

6. **Smoke-check** both artifacts. Write nothing permanent for this; run it inline:

   ```bash
   cd databricks && python -c "
   from agents.exec_summary.final_report_view import final_report_view
   from jinja2 import Environment, FileSystemLoader
   env = Environment(loader=FileSystemLoader('agents/exec_summary/templates'))
   env.get_template('final_report.html.j2')   # parses without a syntax error
   print('ok')
   "
   ```

7. **Confirm the `*.html.j2` autoescape predicate covers the new template.**
   `renderers._autoescape_html_templates` returns `True` for any name ending
   `.html.j2` (`renderers.py:20-24`). Read it and confirm — do not change it. Note
   the confirmation in your close-out.

## Acceptance criteria

- [ ] `diff docs/plans/final_report/inputs/final_report.html.j2 databricks/agents/exec_summary/templates/final_report.html.j2` is empty.
- [ ] `diff docs/plans/final_report/inputs/final_report_view.py databricks/agents/exec_summary/final_report_view.py` is empty.
- [ ] `tests/fixtures/final_report_sample_bundle.py` exists.
- [ ] `grep -rn "sample_bundle" databricks/` returns **nothing**.
- [ ] `git check-ignore docs/plans/final_report/final_report_plan.md` exits non-zero.
- [ ] The smoke-check prints `ok`.
- [ ] `pytest tests/ -q` is no worse than it was before this task (record the
      before/after counts).

## Close out

In [`../final_report_plan.md`](../final_report_plan.md) §10:

- Tick **DoD-8** and append the evidence: the fixture path, and the empty result of
  `grep -rn "sample_bundle" databricks/`.

Commit:

```
feat(final-report): land the report template, view module and sample fixture
```
