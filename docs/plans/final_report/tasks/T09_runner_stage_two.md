# T09 — Stage 2 in the runner: `_run_final_report_stage()`

**Depends on:** T05, T08 · **Closes:** DoD-2, DoD-5, DoD-6, part of DoD-10 · **Est. size:** large

Read [`../final_report_plan.md`](../final_report_plan.md) §2, §4, §6 and
[`tasks/README.md`](README.md) before starting. Read `databricks/CLAUDE.md`'s "VDR
pipeline (UI-triggered)" section — several of its warnings were earned from real
outages and two of them apply directly to this task.

## Goal

Both branches of `databricks/jobs/scripts/run_vdr_rainmaker.py` continue past the
executive review into a second stage that produces the final report — **without
ever being able to take the executive review away.**

## Non-negotiables

1. **Stage 1 does not change.** Same CIM detection, same scoped ingestion, same
   agents, same `build_rainmaker_summary(run_mode="cim_only")`, same two output
   files, same strict parse guard that raises. Your diff on those lines should be
   limited to inserting progress calls around them.
2. **Do not add job or task parameters** to the VDR job. The UI triggers `run-now`
   with notebook params; fixed parameters block it. This was a real outage.
3. **A stage-2 failure must not fail the run.** The ER is already on disk and
   already copied to the VDR volume by then.
4. **Keep the strict parse guard in stage 2** — a non-`SUCCESS` `ingestion_parser`
   still refuses to build on stale chunks — but it marks the stage failed and
   returns instead of raising.
5. The ER filenames are unchanged (`executive_summary.pdf`,
   `rainmaker_opportunity_summary.html`) — the UI resolves them by name. The new
   files are `final_report.pdf` and `final_report.html` in the same timestamped
   dir.

## Step 1 — one shared stage-2 helper

Extract the stage-2 body into a single function; do **not** duplicate it across the
branches. The branches differ only in `run_mode`, in whether ingestion/agents still
have work, and in whether prior MPS runs exist.

```python
def _run_final_report_stage(
    spark,
    table_name: str,
    record_id: int,
    company_name: str,
    output_dir: str,
    progress,                      # vdr_progress.Progress
    run_mode: str,
    run_ingest: bool,
    run_agents: bool,
    prior_run_modes: tuple[str, ...],
    llm_endpoint: str,
    vision_endpoint: str,
) -> dict:
    """Stage 2: full-room ingestion (Branch A only) → agents → final report.

    Never raises: the executive review is already delivered by the time this
    runs, and a stage-2 failure must leave it intact. Returns
    {"status": "success"|"failed", "stage": str|None, "error": str|None,
     "files": [...]}.
    """
```

Body:

1. `if run_ingest:` — `progress.start("vdr_ingestion")`, then
   ```python
   run_ingestion_pipeline(
       company_name=company_name,
       catalog=VDR_CATALOG,
       vision_endpoint=vision_endpoint,
       parse_priority_tiers="1,2",     # runner default; NOT "all" — see plan A-5
       # no file_whitelist, no force → incremental: docs the CIM pass already
       # parsed are skipped (parse_manifest.py:350-370)
   )
   ```
   Apply the same strict guard the branches use today — build the same
   phase-breakdown message — but on failure call `progress.fail("vdr_ingestion",
   msg)` and **return** `{"status": "failed", ...}`. Do not raise.
2. `if run_agents:` — `progress.start("vdr_agents")`,
   `run_pipeline(company_name, catalog=VDR_CATALOG, llm_endpoint=llm_endpoint,
   run_orchestrator=False)`, `progress.complete("vdr_agents")`.
3. `progress.start("final_report")`, then
   ```python
   prior = _load_prior_mps_runs(spark, VDR_CATALOG, company_name, prior_run_modes) if prior_run_modes else []
   built = build_final_report(company_name, VDR_CATALOG, spark, llm_endpoint,
                              run_mode=run_mode, prior_mps_runs=prior or None)
   ```
   `build_final_report` never raises; inspect `built["status"]`.
4. Copy `built["pdf"]` → `{output_dir}/final_report.pdf` and `built["html"]` →
   `{output_dir}/final_report.html`, each only if the source exists. Follow the
   existing `shutil.copy2` pattern.
5. If neither file was produced → `progress.fail("final_report", …)` and return
   failed. If `built["pdf_degraded"]` is set, print a clear warning and keep going
   — a degraded PDF plus an honest HTML is still a delivery.
6. `progress.complete("final_report", artifacts=files)`, then
   `progress.complete("final_report_ready", artifacts=files)`.
7. Wrap the whole body in `try/except Exception` → `progress.fail(<current stage>,
   …)` and return failed. Track the current stage key in a local so the except
   block can name it.

## Step 2 — Branch A

In `run_vdr_rainmaker()`, after the ER files are copied:

- `progress.complete("executive_review_ready", artifacts=[…])` **and** publish
  `results_location = output_dir + "/"` onto the record at that moment
  (`progress.publish({...})`) — the deal team gets a downloadable executive review
  while stage 2 is still running. This is a new write; the terminal write at the
  end still sets it too, harmlessly.
- Call `_run_final_report_stage(..., run_mode="full_vdr_after_cim",
  run_ingest=True, run_agents=True, prior_run_modes=("cim_only",))`.
- Then the terminal `_update_vdr_record` (§ Step 4).

## Step 3 — Branch B

In `_run_full_room_flow()`, after the three ER files are copied:

- same early `results_location` publish + `progress.complete("executive_review_ready")`;
- `_run_final_report_stage(..., run_mode="full_vdr_no_cim", run_ingest=False,
  run_agents=False, prior_run_modes=())` — the room is already ingested and the
  agents have already run inside `run_full_pipeline()`;
- then the terminal update.

Branch B's earlier stages: `progress.start/complete("vdr_scan")` around the
`_detect_cim_files` call that returned `[]`, and `vdr_pipeline` around the single
`run_full_pipeline()` call. Do not try to split `vdr_pipeline` into two stages —
plan §4 explains why.

## Step 4 — the terminal record state

| Outcome | `processing_status` | `completion_status` | `results_location` |
|---|---|---|---|
| Everything succeeded | `done` | `success` | the run's output dir |
| ER ok, stage 2 failed | `done` | `partial` | still the ER dir |
| Stage 1 failed | `error` | `failure` | unset (unchanged behaviour) |

On the partial path also set `error_message` to the stage-2 error (truncated as
today, `[:4000]`) and leave `progress_json` showing exactly which stage failed.
`progress_pct` is **not** forced to 100 on a partial run.

**Resolve assumption A-1 before you write `"partial"`.** The only values this repo
writes today are `success` and `failure`. Check the live table for a CHECK
constraint on `completion_status`, and check whether the UI switches on the value.
If `partial` is not acceptable, use `completion_status="success"` with
`error_message` set and the failed stage visible in `progress_json` — and record
the substitution in plan §6.

## Step 5 — top of the runner

Call `ensure_progress_columns(spark, table_name)` once, immediately after reading
the record and before the first `_update_vdr_record`. It swallows its own
exceptions, so a workspace where the ALTER is refused still runs diligence.

## Step 6 — tests

Extend `tests/test_run_vdr_rainmaker.py` (same mocking style — Spark, ingestion,
the DAG, the full pipeline, BundleBuilder and the renderers are all mocked):

- **Branch A, both stages succeed:** stage 1's calls are unchanged and in order;
  stage 2 calls ingestion **without** `file_whitelist` and **without** `force`;
  `build_final_report` is called with `run_mode="full_vdr_after_cim"` and prior
  runs from `("cim_only",)`; both `final_report.*` files are copied; terminal
  record is `done`/`success`.
- **Branch A, stage-2 ingestion fails:** no exception escapes `run_vdr_rainmaker`;
  `results_location` still points at the ER dir; terminal `completion_status` is
  the partial value; `error_message` is set; the ER files are still listed.
  **This is the DoD-5 test.**
- **Branch A, `build_final_report` returns `status="failed"`:** same expectations.
- **Branch B:** stage 2 runs with `run_ingest=False`, `run_agents=False`,
  `run_mode="full_vdr_no_cim"`, `prior_run_modes=()`; `run_ingestion_pipeline` and
  `run_pipeline` are **not** called a second time.
- **Branch B `no_cim_mode="noop"`:** unchanged — no stage 2, no progress stages
  beyond the scan.
- **Stage 1 failure:** unchanged — still raises, still flips the record to
  `error`/`failure`, and stage 2 never runs.
- **`processing_status` never takes a value outside {`processing`, `done`,
  `error`}** in any of the above. Assert across every `_update_vdr_record` call
  recorded by the mock. **This is the DoD-6 test.**
- **A raising `Progress`** (every method raising) does not change any outcome above
  — progress is never load-bearing.

## Acceptance criteria

- [ ] A-1 answered and recorded in plan §6.
- [ ] Stage 1's call sequence is untouched (verify by reading the diff, not by
      assuming).
- [ ] No job/task parameters added to any YAML in this task.
- [ ] Exactly one stage-2 helper; no duplicated body across the branches.
- [ ] `pytest tests/test_run_vdr_rainmaker.py -q` and `pytest tests/ -q` pass.

## Close out

In [`../final_report_plan.md`](../final_report_plan.md) §10:

- Tick **DoD-2**, **DoD-5**, **DoD-6**, and the A-1 half of **DoD-10**, each with
  the name of the test that proves it.
- Record the A-1 answer in §6.

Commit:

```
feat(vdr): continue both branches into the final report stage with progress
```
