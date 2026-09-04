# T03 — `test_final_report_view.py`: the numeric contract

**Depends on:** T02 · **Closes:** — (evidence for DoD-2/DoD-3) · **Est. size:** medium

Read [`../final_report_plan.md`](../final_report_plan.md) and
[`tasks/README.md`](README.md) before starting.

## Goal

The view layer is where the risk is: it is the only place in this feature that
does arithmetic. Write `tests/test_final_report_view.py` covering the numeric
contract. These tests must fail loudly if anyone later "fixes" a `None` into a `0`.

Model the file on `tests/test_rainmaker_view.py` — same imports, same style, same
level of mocking (this module is pure; it needs none).

## What to test

### 1. `None` never becomes `0`

- An absent figure produces `None` and never `0`, at every layer: `parse_money`,
  `parse_percent`, the P&L row values, the chart bar percentages, the headline
  tiles.
- A bundle where a whole section is `{}` or missing produces the section's
  "not extracted" shape, not a zero-filled one.
- Explicitly: a bar whose value is `None` must have `bar1_pct is None`, not `0`.
  Assert on `is None`, not on falsiness — `0 == None` is False but `not 0` is True,
  and a truthiness assertion would pass on the bug this test exists to catch.

### 2. `scale()`

- `scale([None, None])` → all `None`.
- A `None` inside a populated list stays `None` while its siblings scale.
- No output ever exceeds `100`.
- The largest input maps to `100` (or to the explicit `max_value` when one is
  passed).
- A negative or zero `max_value` does not raise and does not produce `inf`/`nan`.

### 3. `_calc_column()`

- Returns `None` rather than a bogus CAGR when a period is missing.
- Returns `None` when the starting value is zero or negative (a CAGR off a
  non-positive base is meaningless, not large).
- Returns `None` when `n_periods` is `0` or `1`.
- Produces a correct value on a known-good case — pick one you can verify by hand
  and assert the exact formatted string.

### 4. Threshold screens (`_SCREENS`, `_kpi_scorecard`, `_retention_rows`)

- A `min`-direction screen flags when the value is **below** the threshold and not
  when it is above.
- A `max`-direction screen flags on the opposite side.
- Both behaviours hold for **both** sectors present in `_SCREENS` — parametrize
  over the sectors actually defined in the module rather than hardcoding names.
- A metric with no screen for the active sector is not flagged and does not raise.
- A value exactly equal to the threshold: assert whichever side the implementation
  takes, and add a one-line comment saying the boundary is pinned deliberately.

### 5. Caps

- For each of `CAP_TILES`, `CAP_THESIS`, `CAP_WATCHOUTS`, `CAP_BULLETS`,
  `CAP_SEGMENTS`, `CAP_TOP_CUSTOMERS`, `CAP_KPIS`, `CAP_RISKS`, `CAP_QUESTIONS`,
  `CAP_GAPS`: feed the agent output `cap + 3` items and assert exactly `cap` come
  out. Read the constants from the module — never hardcode the numbers, so raising
  a cap breaks the intent, not the test.

### 6. P&L rows

- A row absent from **every** period is dropped, not rendered empty.
- A row present in some periods and absent in others is kept, with `None` in the
  missing cells.

### 7. Deduplication and `why_it_matters`

- `_questions` dedupes case-insensitively on question text and respects
  `CAP_QUESTIONS`.
- A question with no `why_it_matters` yields `why=None` (T02 may have confirmed
  this field is absent — the test pins the honest behaviour either way).

## Fixtures

Use `tests/fixtures/final_report_sample_bundle.py` for the "populated" case, and
build minimal literal dicts inline for the edge cases. Do not add new fixture
files. Do not import anything from `docs/`.

## Acceptance criteria

- [ ] `pytest tests/test_final_report_view.py -q` passes.
- [ ] `pytest tests/ -q` passes with no new failures.
- [ ] Every cap assertion reads its constant from the module.
- [ ] Every "is not zero" assertion uses `is None`, not truthiness.
- [ ] No test mocks `final_report_view` internals — it is a pure module and is
      tested through its public surface.

## Close out

In [`../final_report_plan.md`](../final_report_plan.md) §10: append the test count
and the pass line as evidence under DoD-2 (do not tick DoD-2 — T07/T09 close it).

Commit:

```
test(final-report): pin the view layer's numeric contract
```
