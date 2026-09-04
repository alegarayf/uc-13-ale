# T02 — Audit the eight bundle fields; wire renames, record the absent

**Depends on:** T01 · **Closes:** DoD-11 · **Est. size:** medium

Read [`../final_report_plan.md`](../final_report_plan.md) §1.4 and
[`tasks/README.md`](README.md) before starting.

## Goal

`final_report_view.py` reads eight bundle fields that a preliminary grep says do
not exist under those names. For each one, decide — **from the code, not from the
name** — whether it is (a) an existing field under a different name with a
compatible shape, in which case the view reads the existing name, or (b) genuinely
absent, in which case the section keeps rendering its "not extracted" state and
the field goes on the follow-up list.

**A page that honestly says a chart could not be built is acceptable. A chart built
from guessed data is not.** Do not invent a field, a default, or a synthesized
value anywhere in this task.

## The eight fields, and where the view reads them

| # | View reads | Read at | Feeds |
|---|---|---|---|
| 1 | `bundle["financials"]["segment_performance"]` (+ `financials.segment_dimension`) | `_performance_by`, `final_report_view.py:569` | Page 3 performance-by-segment table + chart |
| 2 | `bundle["financials"]["forecast_rows"]` | `_forecast`, `:712` | Page 8 plan-vs-history chart |
| 3 | `bundle["financials"]["forecast_assumptions"]` | `_forecast`, `:736` | Page 8 assumptions table |
| 4 | `bundle["financials"]["growth_bridge"]` | `final_report_view.py:516` | Page 4 growth bridge |
| 5 | `bundle["revenue_quality"]["revenue_type_mix"]` | `_mix`, `:553` | Page 3 recurring-vs-project mix bar |
| 6 | `bundle["revenue_quality"]["client_distribution"]` | `_mix`, `:553` | Page 3 clients-by-segment mix bar |
| 7 | `bundle["qoe"]["addbacks"]` | `_quality`, `:663` | Page 7 addback stack |
| 8 | `bundle["diligence_questions"][i]["why_it_matters"]` | `_questions`, `:758` | Page 9 "why it matters" column |

## Candidate existing names found in the preliminary grep

These are **leads, not answers** — verify the shape of each before using it.

- #1 → `revenue_by_segment` (`databricks/agents/exec_summary/field_mapping.py:223`,
  and `segment` / `segment_qualified_label` near `:210`)
- #6 → `clients` (`field_mapping.py:523`)
- #7 → `addback_schedule` (`field_mapping.py:584-586`, alongside `addback_pct`,
  `addback_pct_of_ebitda`)
- #2, #3, #4, #5, #8 → no lead found. Check `forecast_agent.py`'s output columns
  and `populate.py` before concluding — the forecast agent is newer than most of
  `field_mapping.py`.

## Steps

1. For each of the eight, trace the **whole chain**: the agent that would produce
   it (`databricks/agents/workstreams/*.py`) → the Delta column → `field_mapping.py`
   / `populate.py` → the key that lands in the bundle
   (`bundle_builder.py:672-700`).

2. Classify each field as one of:
   - **RENAME** — an existing field carries the same information in a shape
     `final_report_view` can consume as-is or with a trivial key remap.
   - **RESHAPE** — an existing field carries the information but in a different
     shape (e.g. a dict of period→value where the view wants a list of row dicts).
     Treat a reshape as legal **only if it is a pure, lossless projection with no
     invented values**; otherwise classify it ABSENT.
   - **ABSENT** — nothing populates it. Leave the view's read as-is so the section
     renders "not extracted".

3. For every RENAME/RESHAPE, edit `databricks/agents/exec_summary/final_report_view.py`
   and **only** that file. Rules:
   - Extend the read, do not restructure the module. Prefer a small local helper
     that tries the canonical name first and falls back to the existing one:
     `raw = fin.get("segment_performance") or fin.get("revenue_by_segment") or []`.
   - Keep the caps (`CAP_*`) exactly as they are.
   - Keep every `None`-preserving path intact. A missing sub-key still yields
     `None`, never `0`, never `""`.
   - Add a one-line comment at each changed read recording *why* the alias exists
     (which agent writes which name), not what the line does.

4. For every ABSENT field, change nothing in the code.

5. **Implement A-3 from the plan while you are in this file.** Add an additive
   parameter to the public entry point:

   ```python
   def final_report_view(
       bundle: dict[str, Any],
       narrative: dict[str, Any] | None = None,
       run_mode: str | None = None,
   ) -> dict[str, Any]:
   ```

   and use it for the cover's `mode_label`:
   `"CIM-first" if run_mode == "cim_only" else "Full data room"`, falling back to
   the existing `meta.get("run_mode")` read when `run_mode is None` so the function
   stays usable standalone. `bundle["meta"]` has no `run_mode` key
   (`bundle_builder.py:652-668`), so without this every report would read "Full
   data room" — including a CIM-first one. Document the *why* in the docstring:
   `run_mode` is a fact about which branch the caller took and is never re-derived
   from `bundle.meta`.

6. Run the existing suite. Nothing should change: `pytest tests/ -q`.

## Acceptance criteria

- [ ] Every one of the eight fields has a written classification with the file and
      line that justifies it.
- [ ] No new field, default value, placeholder or synthesized figure exists
      anywhere in `final_report_view.py`.
- [ ] No file other than `final_report_view.py` was modified.
- [ ] Caps are unchanged (`git diff` shows no `CAP_*` line touched).
- [ ] `final_report_view()` accepts `run_mode` and still works when it is omitted.
- [ ] `pytest tests/ -q` unchanged.

## Close out

In [`../final_report_plan.md`](../final_report_plan.md):

- Replace **F-2** in §9 with the finished list: every ABSENT field, the section it
  degrades, and the agent that would have to populate it.
- Add a short table under §1.4 recording the RENAME/RESHAPE decisions and their
  justifying line references.
- Tick **DoD-11** in §10.

Commit:

```
feat(final-report): map the report view onto the fields the agents actually emit
```
