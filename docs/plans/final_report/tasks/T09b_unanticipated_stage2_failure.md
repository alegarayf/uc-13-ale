# T09b — Prove the stage-2 safety net catches what nobody anticipated

**Depends on:** T09 · **Closes:** DoD-18 · **Est. size:** small

> **Read the plan selectively.** Only **§6** (how a stage-2 failure degrades)
> applies here. Locate it with `grep -n "^## " ../final_report_plan.md` and read
> that range — do not read the file whole.

Read [`README.md`](README.md) (it is short) before starting.

## Why this task exists

T09's stage-2 failure tests are good but they all exercise **handled** paths:

- `run_ingestion_pipeline` returning a non-`SUCCESS` parse phase → explicit early
  return;
- `build_final_report` returning `status="failed"` → explicit early return.

Both leave `_run_final_report_stage` through a `return`, never through its
`except Exception`. Every other raising mock in that area is a *negative*
assertion (`side_effect=AssertionError("must not run …")`) proving a path is not
taken.

So the `try/except` that wraps the whole helper — **the net for an exception
nobody predicted** — is never exercised. Proven during the T09 review: adding a
bare `raise` as the first statement of that `except` block left all 20 tests
green.

That is the wrong thing to leave untested. DoD-5 says a stage-2 failure must
leave the executive review intact, and its most valuable case is the failure mode
nobody wrote a branch for. As it stands, a future edit that deletes the
`try/except` passes CI.

## Realistic ways stage 2 raises today

Pick from these — they are all reachable, none is contrived:

- **`run_pipeline` raises.** The Phase 3-5 DAG raises on catastrophic failure;
  stage 2 calls it on Branch A with `run_agents=True`.
- **`shutil.copy2` raises.** Copying `final_report.pdf` to the VDR volume can fail
  on a permission or quota error.
- **`os.makedirs` raises** on the output dir.

## Steps

### 1. One test per raising collaborator (two is enough, three is fine)

Add to `tests/test_run_vdr_rainmaker.py`, alongside T09's stage-2 tests and using
the same fixtures and mocking style. For each:

- Branch A, CIM found, **stage 1 succeeds normally**.
- One stage-2 collaborator raises a plain `RuntimeError` — not an
  `AssertionError`, which reads as a negative assertion in this file and would
  confuse the next reader.
- Assert **all** of:
  - `run_vdr_rainmaker()` returns normally — **no exception escapes**;
  - the record's final `results_location` still points at the ER output dir;
  - the final `processing_status` is `"done"` (not `"error"`);
  - `error_message` is set and mentions the failure;
  - `progress_json` on the last update shows the stage that failed as `failed`;
  - the ER's two filenames are still among the copied files.

Name them so the distinction from T09's tests is unmistakable — e.g.
`test_branch_a_stage2_unanticipated_exception_keeps_er_intact`.

### 2. Prove the tests discriminate — this is the acceptance evidence

The whole point is to close a hole a mutation walked through. Verify the same
mutation is now caught:

```bash
R=databricks/jobs/scripts/run_vdr_rainmaker.py
git status --porcelain          # clean before you start
cp $R /tmp/t09b_runner.bak

# make the helper's generic except re-raise instead of degrading
# (insert `raise` as the first statement of the `except Exception` block
#  inside _run_final_report_stage)
PYTHONDONTWRITEBYTECODE=1 pytest tests/test_run_vdr_rainmaker.py -q -p no:cacheprovider
#   ^ MUST fail now. Before this task it passed.

cp /tmp/t09b_runner.bak $R
find databricks -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
git status --porcelain          # clean again
```

Paste the failure summary into your close-out. **If the mutation still passes, the
task is not done.**

### 3. Do not change production code

This task adds tests only. `run_vdr_rainmaker.py` must show **zero diff**. If
writing the tests reveals a real defect in the degradation path, stop and report
it rather than fixing it here — that is a separate decision.

## Acceptance criteria

- [ ] At least two tests, each with a different stage-2 collaborator raising a
      `RuntimeError`.
- [ ] Each asserts no exception escapes, `results_location` still points at the
      ER, `processing_status == "done"`, `error_message` set, and the failing
      stage marked `failed` in `progress_json`.
- [ ] The re-raise mutation now **fails**, with the output in the close-out.
- [ ] `git diff --stat` shows nothing under `databricks/`.
- [ ] `git status --porcelain` is empty before the commit — no mutated source.
- [ ] `pytest tests/ -q` passes; counts from `pytest --collect-only -q`.

## Close out

In [`../final_report_plan.md`](../final_report_plan.md) §10: tick **DoD-18** with
the mutation failure summary as evidence.

Commit:

```
test(vdr): prove stage 2 degrades on an unanticipated exception
```
