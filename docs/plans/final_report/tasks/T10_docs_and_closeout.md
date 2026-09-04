# T10 — Documentation, the read-only proof, and closing the DoD

**Depends on:** every other task · **Closes:** DoD-1, DoD-4, DoD-7 · **Est. size:** medium

Read [`../final_report_plan.md`](../final_report_plan.md) and
[`tasks/README.md`](README.md) before starting.

## Goal

Leave the repo describing what it now does, and prove that nothing that was
supposed to stay still moved.

## Step 1 — `databricks/CLAUDE.md` (required, not optional)

Someone reading **only** that file must end up with an accurate picture. Update:

- **"VDR pipeline (UI-triggered)"** — the run is now two stages. Describe: stage 1
  produces the executive review exactly as before and publishes it to the record
  as soon as it exists; stage 2 continues to a final diligence report over the
  whole data room. Say plainly that a stage-2 failure leaves the ER intact and the
  run partially complete.
- The **new deliverables** in `/Volumes/rallyday_partners_llc/default/vdr/{company}/{ts}/`:
  `final_report.pdf` and `final_report.html`, alongside the unchanged ER
  filenames. Note that the UI resolves ER files by name and those names did not
  change.
- The **progress columns** — the four additive nullable columns, that
  `processing_status` keeps its exact existing vocabulary and stays `processing`
  until the whole run ends, and that a UI reading only that column is unaffected.
- The **stage vocabulary** — both branch lists, and the one-line reason Branch B
  collapses ingestion+agents into `vdr_pipeline`.
- The repository-layout block: add `vdr_progress.py`, `final_report_entry.py`,
  `final_report_view.py`, `templates/final_report.html.j2` (and `_mps_page.html.j2`
  if D-01 landed) with one-line descriptions in the existing style.
- The **MPS** note: the final report's MPS is a fresh `MPSAgent().score` over the
  complete bundle, `run_mode="full_vdr_after_cim"` on Branch A; on that branch the
  page carries two score columns, the CIM-stage run being read back from
  `{catalog}.analysis.mps_score`.
- Re-state the two standing warnings in their existing spots if the new flow makes
  them more load-bearing: no job/task parameters on the VDR job, and one Git
  folder feeds both VDR jobs.

Match the file's existing voice: comments and notes that record *why*, warnings
marked as earned from incidents, no restating of code.

## Step 2 — the workflow YAML

`databricks/workflows/vdr_rainmaker_poc.yml`: update the **description only**, if
it now misdescribes what runs. **Add no parameters** — fixed parameters block the
UI's `run-now` trigger.

If `tests/test_vdr_rainmaker_poc_yml.py` asserts on the description, update the
test in the same commit.

## Step 3 — the read-only proof (DoD-4)

```bash
git diff --stat $(git merge-base HEAD feature/anthropic-sdk-migration)..HEAD -- \
  databricks/agents/exec_summary/rainmaker_view.py \
  databricks/agents/exec_summary/rainmaker_narrative.py \
  databricks/agents/workstreams/mps_agent.py \
  databricks/agents/exec_summary/mps_rubric.py \
  databricks/agents/exec_summary/bundle_builder.py \
  databricks/agents/exec_summary/validate.py \
  databricks/agents/exec_summary/absence_check.py \
  databricks/agents/exec_summary/templates/rainmaker_opportunity_summary.html.j2
```

Expected: **empty**, except for

- `rainmaker_view.py` — exactly `1 insertion(+)`, the `_MPS_RUN_MODE_LABELS` entry;
- `rainmaker_opportunity_summary.html.j2` — only if D-01 was approved, and only the
  block→include swap.

Paste the actual output into plan §7. If anything else moved, revert it or — if it
genuinely had to change — write the reason into plan §9 and flag it for Hector
rather than quietly keeping it.

## Step 4 — full suite

```bash
pytest tests/ -q
```

Record the count. Also confirm the two convention gates still pass, since this
change touched the runner and added a module:

```bash
pytest tests/test_llm_gateway_convention.py tests/test_catalog_convention.py -q
```

## Step 5 — close the DoD

Walk plan §10 top to bottom. Every box must be either ticked **with evidence
named** or explicitly left open with a reason. Specifically:

- **DoD-1** — tick only after re-reading the plan against the shipped code and
  correcting anything the implementation decided differently. A plan that no longer
  matches what was built is worse than no plan.
- **DoD-4** — tick with Step 3's pasted output.
- **DoD-7** — tick with the section names you edited.

Then add a short **"What shipped"** section at the end of the plan: the two
deliverables per run, the stage vocabulary actually implemented, the answers to
A-1/A-2/D-01, and the follow-up list (F-1, F-2, F-3) as it finally stands.

## Step 6 — end-to-end verification is an operator step, not a test

Nothing in this task run proves the flow works on a live data room — the suite
mocks Spark, the agents and the renderers. State that plainly in your report and
hand Hector the checklist for a real run:

- trigger the VDR job for a CIM-bearing company and confirm two deliverables land
  in the timestamped volume dir;
- confirm the record's `results_location` is populated **before** the run finishes;
- confirm the final report's MPS page shows two score columns;
- trigger a no-CIM company and confirm one score column and five stages;
- check `progress_json` renders a sensible stage list at a few points mid-run.

Do not tick any DoD box on the strength of a run you did not observe.

## Acceptance criteria

- [ ] `databricks/CLAUDE.md` describes the two-stage flow, the deliverables, the
      progress columns and the stage vocabulary accurately.
- [ ] The YAML description matches what runs; no parameters added.
- [ ] Step 3's diff is empty except for the two documented exceptions.
- [ ] `pytest tests/ -q` passes.
- [ ] Plan §10 has no silently-unticked box.

Commit:

```
docs(vdr): document the two-stage VDR flow, deliverables and progress signal
```
