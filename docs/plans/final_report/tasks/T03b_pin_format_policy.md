# T03b — Pin the caps and the screens as policy, not as derived values

**Depends on:** T03 · **Closes:** DoD-17 · **Est. size:** small

Read [`../final_report_plan.md`](../final_report_plan.md) and
[`tasks/README.md`](README.md) before starting.

## Why this task exists

T03 delivered 55 tests and they are good: a mutation pass over
`final_report_view.py` during review killed five of seven deliberate defects,
including the important one (turning a `None` into `0.0` fails 20 tests).

**Two mutants survived, and both for the same reason.** T03's instructions told
the author to read expectations from the module — which is correct for testing
*enforcement* and wrong as the only assertion, because a test that derives its
expectation from the constant it is testing moves when that constant moves:

| Deliberate defect | Tests that failed |
|---|---|
| `CAP_QUESTIONS = 8` → `12` | **none** |
| `_SCREENS` entry `nrr_pct` `"dir": "min"` → `"max"` | **none** |

Both are **policy**, not implementation detail. The plan says caps "are part of
the format… do not raise them to fit more content in", and the screens encode how
Rallyday screens a sector — *NRR below 90 gets flagged* is a business rule. Policy
with no literal test is policy that can be edited by accident.

This task adds the missing assertions. It changes **no production code**.

## Steps

### 1. Pin the cap values literally

Add to `tests/test_final_report_view.py`, in its own clearly-titled section:

```python
# These numbers are FORMAT POLICY (plan §2.2: "caps are part of the format").
# This test is meant to fail when one changes — that is the point. If a cap
# genuinely should move, change it here too, in the same commit, with the reason
# in the commit message. Do not "fix" this test by reading the constant.
_EXPECTED_CAPS = {
    "CAP_TILES": 6,
    ...
}
```

Cover **every** `CAP_*` constant in the module. Read the current values from the
source rather than from memory, and assert `getattr(frv, name) == expected` for
each. Add an assertion that the set of `CAP_*` names in the module is exactly the
set of keys here, so a **new** cap cannot be added without landing in this test.

Keep T03's existing enforcement tests untouched — they test a different thing and
both are wanted.

### 2. Pin the screen definitions literally

Same file, same treatment. `_SCREENS` is a tuple of 14 dicts of
`(key, name, threshold, dir, sector)`. Pin the whole table as a literal — a set or
sorted list of `(sector, key, threshold, dir)` tuples compared against what the
module declares.

Verbose is correct here. The point is that changing any threshold or direction
produces a failing test that a human has to look at and agree with.

### 3. Add a behavioural screen test with a hardcoded threshold

The literal pin catches an edited definition. This catches a broken *mechanism*
without borrowing the module's own `dir`:

- a bundle with `nrr_pct = 85` (below the 90 `min` screen) → **flagged**;
- the same with `nrr_pct = 95` → **not flagged**;
- one `max`-direction case, hardcoded the same way — `top1_pct = 30` against the
  25 `max` screen for `tech_services` → **flagged**; `top1_pct = 20` → not.

Write the thresholds as literals in the test, with a comment pointing at
`_SCREENS`. If a future change makes these fail legitimately, the fix is to update
them deliberately.

### 4. Prove the new tests discriminate

This is the acceptance evidence, not a nicety. For each of the two surviving
mutants, apply it, confirm your new test **fails**, then restore:

```bash
V=databricks/agents/exec_summary/final_report_view.py
git status --porcelain          # must be clean before you start

sed -i '' 's/^CAP_QUESTIONS = 8$/CAP_QUESTIONS = 12/' $V
pytest tests/test_final_report_view.py -q    # MUST fail now
git checkout -- $V

sed -i '' 's/"key": "nrr_pct", "name": "Net revenue retention", "threshold": 90, "dir": "min"/"key": "nrr_pct", "name": "Net revenue retention", "threshold": 90, "dir": "max"/' $V
pytest tests/test_final_report_view.py -q    # MUST fail now
git checkout -- $V

git status --porcelain          # must be clean again
```

Paste both failure summaries into your close-out. **If either mutant still
passes, the task is not done** — a test that cannot fail is worse than no test,
because it reads as coverage.

Restore the file after each mutant and verify the tree is clean before committing.
Never commit a mutated source file.

## Acceptance criteria

- [ ] Every `CAP_*` constant has a literal expected value, and a new cap cannot be
      added without appearing in the test.
- [ ] All 14 `_SCREENS` entries are pinned literally.
- [ ] The behavioural screen tests use hardcoded thresholds, not `_SCREENS`.
- [ ] Both surviving mutants now fail, with the output pasted in the close-out.
- [ ] `git status --porcelain` is empty before the commit — no mutated source.
- [ ] No production code changed: `git diff --stat` shows nothing under
      `databricks/`.
- [ ] `pytest tests/ -q` passes.

## Close out

In [`../final_report_plan.md`](../final_report_plan.md) §10: tick **DoD-17** with
the two mutant failure summaries as evidence.

Commit:

```
test(final-report): pin the format caps and screening thresholds as policy
```
