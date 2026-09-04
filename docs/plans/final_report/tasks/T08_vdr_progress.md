# T08 — `vdr_progress.py`: the progress emitter and its columns

**Depends on:** nothing (can run in parallel with T01-T07) · **Closes:** part of DoD-6, part of DoD-10 · **Est. size:** large

Read [`../final_report_plan.md`](../final_report_plan.md) §4 and
[`tasks/README.md`](README.md) before starting.

## Goal

Give the UI enough state to render a stage list — without changing anything in
`agents/`, and **without breaking the existing UI**, which knows only
`processing_status` ∈ {`submitted`, `processing`, `done`, `error`}.

Two hard rules:

- **`processing_status` keeps its exact current vocabulary and semantics.** It
  stays `processing` until the whole run finishes. A UI reading only that column
  keeps working unchanged.
- **A progress write must never be able to fail a diligence run.** The emitter
  swallows its own exceptions and prints.

## Step 0 — resolve assumption A-2 before writing code

The target table, `rallyday_partners_llc.default.companies_vdr_history`, is owned
by the UI and holds live records.

Check, against the warehouse (profile `rallyday`), whether
`ALTER TABLE … ADD COLUMNS IF NOT EXISTS` is permitted on it, and whether the four
columns already exist. Record the answer in plan §4.

- **Permitted (expected):** proceed with the columns.
- **Not permitted:** fall back to a separate `uc13_preview.analysis.vdr_progress`
  Delta table keyed by `record_id`, same payload, and record the refusal in plan
  §4. The columns are preferred because they keep the UI to one query.

**Never use the drop-and-recreate pattern the agent tables use** (`_EXPECTED_COLS`
schema-drift guard). That pattern is for tables this pipeline owns. This one holds
live UI records; dropping it destroys them.

## The four columns

| Column | Type | Meaning |
|---|---|---|
| `progress_stage` | STRING | the current stage key |
| `progress_pct` | INT | 0-100 |
| `progress_json` | STRING | the full ordered stage list, per-stage status + timestamps |
| `stage_updated_at` | STRING | ISO timestamp of the last progress write |

All nullable, all additive. A row that never gets a progress write reads `NULL`
across all four, and the existing UI is unaffected.

## Step 1 — `ensure_progress_columns(spark, table_name)`

A module-level function issuing `ALTER TABLE {table} ADD COLUMNS IF NOT EXISTS
(...)`, idempotent, callable at the top of every run. It swallows its own
exceptions and prints — a workspace where the ALTER is refused must still complete
diligence, just without progress. Do not interpolate `table_name` from untrusted
input; it comes from the notebook widget, same as everywhere else in this runner.

## Step 2 — `class Progress`

A thin emitter, **not a framework**.

```python
class Progress:
    def __init__(
        self,
        spark: Any,
        table_name: str,
        record_id: int,
        stages: list[tuple[str, str]],      # ordered (key, human label)
        updater: Callable[..., None] | None = None,
    ) -> None: ...

    def start(self, key: str) -> None: ...
    def complete(self, key: str, artifacts: Any = None) -> None: ...
    def fail(self, key: str, error: str) -> None: ...
    def skip(self, key: str, reason: str | None = None) -> None: ...
    def publish(self, columns: dict[str, Any]) -> None: ...
```

- Each of `start`/`complete`/`fail`/`skip` writes **all four** columns in **one**
  `UPDATE`, through the existing `run_vdr_pipeline._update_vdr_record` (injectable
  via `updater` so tests do not need Spark).
- `publish(columns)` merges extra record columns (e.g. `results_location`) into the
  **same** UPDATE as the current progress write, so publishing the executive review
  early costs no extra round trip.
- **Every public method swallows every exception** and prints
  `[vdr_progress] <what failed>: <exc>`. Nothing propagates. Ever.
- Per-stage payload in `progress_json`: `key`, `label`, `status`
  (`pending`/`processing`/`done`/`failed`/`skipped`), `started_at`, `finished_at`,
  `artifacts`. Stages not yet reached are `pending` with null timestamps — the
  whole ordered list ships on every write so the UI can render the bar without
  knowing the branch in advance.
- `progress_pct` = `round(100 * terminal_stages / total_stages)` where terminal
  means `done`/`failed`/`skipped`, **clamped to never decrease** (keep the last
  value on the instance). Expose a `finish(pct=100)`-style path or simply allow
  `complete()` on the last stage to reach 100 — whichever is simpler, but the
  runner must be able to land on exactly 100 for a fully successful run.
- Timestamps: reuse `run_vdr_pipeline._now_iso()` rather than adding a second time
  format to this codebase.
- An unknown stage key passed to any method is a no-op with a printed warning, not
  a `KeyError`.

## Step 3 — the two stage lists

Define them as module constants so the runner and the tests share one source:

```python
STAGES_CIM = [
    ("cim_detection",          "Scanning the data room for a CIM"),
    ("cim_ingestion",          "Ingesting the CIM"),
    ("cim_agents",             "Running the diligence agents on the CIM"),
    ("executive_review_ready", "Executive review ready"),
    ("vdr_ingestion",          "Ingesting the full data room"),
    ("vdr_agents",             "Running the diligence agents on the full data room"),
    ("final_report",           "Building the final diligence report"),
    ("final_report_ready",     "Final report ready"),
]

STAGES_FULL = [
    ("vdr_scan",               "Scanning the data room"),
    ("vdr_pipeline",           "Ingesting the data room and running the diligence agents"),
    ("executive_review_ready", "Executive review ready"),
    ("final_report",           "Building the final diligence report"),
    ("final_report_ready",     "Final report ready"),
]
```

`STAGES_FULL` collapses ingestion and agents into one stage deliberately — see plan
§4 for the reasoning (the runner makes a single `run_full_pipeline()` call and
cannot observe the boundary from outside; two stages would mean a fabricated
timestamp). Put a short version of that reason in a comment above the constant.

## Step 4 — `tests/test_vdr_progress.py`

Model on `tests/test_run_vdr_rainmaker.py`'s mocking style. Cover:

- a full happy sequence over `STAGES_CIM` produces well-formed `progress_json` at
  every step: valid JSON, all stages present in order, exactly one `processing` at
  a time, statuses transitioning as expected;
- `progress_pct` is **monotonic** across the whole sequence and reaches exactly
  `100` on a fully-completed run;
- `fail()` marks that stage `failed`, leaves earlier stages `done` and later ones
  `pending`, and does not reduce `progress_pct`;
- **a raising spark session / raising updater does not propagate** out of any of
  `start`/`complete`/`fail`/`skip`/`publish` — assert with a mock that raises on
  every call and a sequence that completes normally;
- `ensure_progress_columns` swallows a raising spark;
- an unknown stage key is a no-op, not a `KeyError`;
- `publish()` lands its extra columns in the same update call as the progress
  columns (assert on the single call's payload);
- `progress_json` round-trips through `json.loads` at every step.

## Acceptance criteria

- [ ] A-2 is answered in plan §4, with the evidence.
- [ ] Nothing under `databricks/agents/` imports `vdr_progress`.
- [ ] No drop-and-recreate anywhere near `companies_vdr_history`.
- [ ] Every public method is exception-proof, proven by test.
- [ ] `pytest tests/test_vdr_progress.py -q` passes; `pytest tests/ -q` passes.

## Close out

In [`../final_report_plan.md`](../final_report_plan.md):

- Record the A-2 answer in §4 and tick the A-2 half of **DoD-10**.
- Append the emitter's evidence under **DoD-6** (T09 ticks it).

Commit:

```
feat(vdr): add the vdr_progress emitter and its additive record columns
```
