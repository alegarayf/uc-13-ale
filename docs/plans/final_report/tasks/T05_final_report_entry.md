# T05 — `final_report_entry.build_final_report()` + the MPS read-back

**Depends on:** T04 · **Closes:** part of DoD-2 · **Est. size:** large

Read [`../final_report_plan.md`](../final_report_plan.md) §1.2, §3 and
[`tasks/README.md`](README.md) before starting.

## Goal

Create `databricks/agents/exec_summary/final_report_entry.py` — the bridge that
turns a completed agent run into the final report. It is the sibling of
`rainmaker_entry.py` and must read like it: same docstring discipline, the same
"must be called AFTER the agent DAG has completed" contract, the same
catalog-agnostic signature. **It never raises.**

## The contract

```python
def build_final_report(
    company_name: str,
    catalog: str,
    spark: "SparkSession",
    llm_endpoint: str,
    run_mode: str,
    prior_mps_runs: list[dict[str, Any]] | None = None,
    reuse_mps_run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """BundleBuilder → validate → verify_bundle_claims → narrative →
    MPSAgent().score → render_final_report. Never raises."""
```

Reuse, **unchanged**: `BundleBuilder`, `validate_bundle`, `verify_bundle_claims`,
`synthesize_rainmaker_narrative`, `MPSAgent`. Import them inside the function, the
way `rainmaker_entry.py:56-61` does.

`run_mode` is a fact about which branch the *caller* took. Never re-derive it from
`bundle.meta` — `bundle["meta"]` does not carry it (`bundle_builder.py:652-668`).
Pass it through to `MPSAgent().score(...)` and on to `render_final_report(...)`.

Return:

```python
{
    "status": "success" | "degraded" | "failed",
    "html": path | None,
    "pdf": path | None,
    "pdf_degraded": bool,
    "synthesis_status": str | None,
    "mps_status": str | None,
    "error": str | None,
}
```

## Steps

### 1. The happy path

Mirror `rainmaker_entry.build_rainmaker_summary` step for step:

```
bundle = BundleBuilder().build(company_name, catalog, spark, llm_endpoint)
validate_bundle(bundle)
checked = verify_bundle_claims(bundle, spark, catalog, company_name)
narrative = synthesize_rainmaker_narrative(checked, llm_endpoint, spark)
mps = reuse_mps_run or MPSAgent().score(checked, catalog, company_name, spark,
                                        llm_endpoint, run_mode=run_mode)
rendered = render_final_report(checked, catalog, company_name,
                               narrative=narrative, mps=mps,
                               prior_mps=prior_mps_runs, run_mode=run_mode)
```

Print the same one-line status messages the Rainmaker entry prints, prefixed
`[final_report]`.

### 1b. `reuse_mps_run` — decision D-02

When `reuse_mps_run` is supplied, **skip `MPSAgent().score` entirely** and use that
run as the current one. This is Branch B: the ER and the final report are built
from the same bundle with no ingestion and no agent run in between, so re-scoring
would be an extra LLM call over identical data producing a number that can differ
from the one the deal team already downloaded. See plan §3, D-02 — and read it
before implementing, because this is a deliberate deviation from §2.3 of the task
prompt and the docstring must say so.

Requirements:

- Do **not** construct the argument as `reuse_mps_run or score(...)` if that would
  swallow a falsy-but-valid run; a degraded run dict is truthy, but be explicit
  (`if reuse_mps_run is not None`) so the intent survives a future edit.
- Report which path was taken in the return value: add `"mps_source":
  "reused" | "scored"`.
- Print one line naming the source and the run's `run_mode`/`generated_at`, so a
  job log makes the reuse auditable.
- The docstring must state that `reuse_mps_run` is only ever correct when the
  caller knows **no new evidence** entered the bundle since that run was scored.
  Passing it on Branch A would be a bug: the whole point there is that more was
  read.

### 2. `_load_prior_mps_runs()` — read the CIM run back from Delta

`build_rainmaker_summary` returns only `mps_status`; the CIM run dict itself is
discarded (`rainmaker_entry.py:76-80`), and that file is read-only. So the CIM-stage
run is recovered from `{catalog}.analysis.mps_score`, which
`mps_agent.py:454-488` writes append-only with everything needed.

Add a module-level helper:

```python
def _load_prior_mps_runs(
    spark: "SparkSession",
    catalog: str,
    company_name: str,
    run_modes: tuple[str, ...] = ("cim_only",),
) -> list[dict[str, Any]]:
```

- Query `{catalog}.analysis.mps_score` for `company_name` and `run_mode IN (...)`,
  newest `generated_at` first, take **one row per run_mode** (the newest), and
  return them ordered oldest-first so the caller can append the current run last.
- Rehydrate each row into the shape `_mps_table` consumes:
  `{"run_mode", "generated_at", "categories": json.loads(categories_json),
  "threshold", "mps_status", "total", "verdict"}`.
- `generated_at` is a `TIMESTAMP` column; `_mps_column_header`
  (`rainmaker_view.py:674-679`) slices `str(...)[:10]`, so an ISO-ish string is
  required — convert explicitly, do not rely on the driver's `str()`.
- **Never raise.** A missing table, an empty result, a malformed
  `categories_json` → return `[]` and print why. A missing prior column is a
  cosmetic loss; a crash here would cost the whole final report.
- Use parameterized SQL (`spark.sql(..., args={...})`), matching
  `run_vdr_pipeline._read_vdr_record`.

This one helper serves both uses: Branch A reads `("cim_only",)` for the *prior*
column, Branch B reads `("full_vdr_no_cim",)` for the run it will *reuse*. Same
query, different caller intent — say that in the docstring.

**The D-02 fallback.** If `reuse_mps_run` was requested but the read-back returned
nothing or a malformed row (missing table, an ER whose MPS never persisted), fall
back to a fresh `MPSAgent().score` call and print why. Report it as
`"mps_source": "scored_fallback"`. An MPS page with a number beats an empty one;
the fallback is a degraded path and must be visible in stdout.

Note in the docstring that `degraded_reason` is not a persisted column, so a
rehydrated run carries `None` for it — harmless, because `_mps_table` reads that
field only from `mps_runs[-1]` and a prior run is never last.

### 3. The run-mode label — the one permitted edit to `rainmaker_view.py`

Add exactly one entry to `_MPS_RUN_MODE_LABELS` (`rainmaker_view.py:652-655`):

```python
"full_vdr_after_cim": "Full data room",
```

Deliberately the same human label as `full_vdr_no_cim`: the column header already
carries the date, and the reader is being told *what was scored*, not which
internal branch produced it. **Change nothing else in that file.** A second edit
there breaks DoD-4.

### 4. Never raises

Wrap the whole body in `try/except Exception`. On failure: print the exception and
a bounded traceback (follow `run_vdr_rainmaker.py:439-444`'s style), and return
`{"status": "failed", "error": f"{type(exc).__name__}: {exc}", "html": None,
"pdf": None, ...}`. Do not catch `KeyboardInterrupt`/`SystemExit`.

### 5. Tests

Add `tests/test_final_report_entry.py`, modelled on
`tests/test_rainmaker_entry.py` (mock every heavy dependency; no cluster):

- the happy path calls the six collaborators in order, with `run_mode` threaded
  through to **both** `MPSAgent().score` and `render_final_report`;
- `prior_mps_runs` reaches `render_final_report` as `prior_mps`, and the current
  run is **last** in whatever list reaches `_mps_table`;
- a raising `BundleBuilder`, a raising narrative, and a raising renderer each
  produce `status="failed"` and **no exception escapes**;
- `_load_prior_mps_runs` returns `[]` on a raising spark, on an empty result, and
  on malformed `categories_json`;
- `_load_prior_mps_runs` returns runs oldest-first;
- **D-02:** when `reuse_mps_run` is supplied, `MPSAgent.score` is **never called**,
  and the supplied run is what reaches `render_final_report` as `mps`;
  `mps_source == "reused"`;
- **D-02 fallback:** when reuse was requested but the read-back yielded nothing,
  `MPSAgent.score` *is* called and `mps_source == "scored_fallback"`.

## Acceptance criteria

- [ ] `build_final_report` never raises — proven by the three failure tests.
- [ ] `rainmaker_view.py`'s diff is exactly one added dictionary line.
- [ ] `rainmaker_entry.py`, `mps_agent.py`, `bundle_builder.py`, `validate.py`,
      `absence_check.py`, `rainmaker_narrative.py` have zero diff.
- [ ] `pytest tests/ -q` passes.

## Close out

In [`../final_report_plan.md`](../final_report_plan.md) §10: append evidence under
**DoD-2** (the entry point exists, threads `run_mode`, and orders the MPS runs
`[cim, full]`) and under **DoD-12** (the `reuse_mps_run` path never calls
`MPSAgent.score`). Do not tick either — T09 closes both.

Commit:

```
feat(final-report): add build_final_report with the CIM-stage MPS read-back
```
