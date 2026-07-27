# SQLite provenance fallback — removal handoff

**Status:** Phase 1+2 done · Phase 3 (cluster wet-run) pending · **Discovered:** 2026-07-27 (hector-ui-pipeline-merge e2e)  
**Owner:** unassigned · **Scope:** remove sqlite from prod/agent paths; keep for local eval  
**Related:** `GOLD_LABEL_BOOTSTRAP_HANDOFF.md` (separate chip; blocked on fresh agent runs for citation backfill)

---

## Update — Phase 1+2 landed (2026-07-27)

Phases 1 (code) and 2 (local tests) are implemented. Cluster validation (Phase 3) is still pending.

### What changed

**Core fix — thread injected `spark` into provenance store resolution**

`open_agent_run()` now accepts an optional `spark=` parameter. Resolution order:

1. Explicit `store=` → use it (tests / harness unchanged)
2. `spark=` provided → `DeltaEvalStore(spark, catalog=catalog)` using the **agent's catalog param** (not `RE2_CATALOG` default)
3. Neither → `resolve_store()` (local harness / pytest only)

This closes the gap where `pipeline.py` injected `spark=` into agent `main()` for Delta writes, but `open_agent_run()` called `resolve_store()` → `getActiveSession()` → `None` on `ThreadPoolExecutor` worker threads → silent `SqliteEvalStore` fallback.

**`resolve_store()` hardened (belt-and-suspenders)**

- `RE2_STORE_BACKEND=delta` without active Spark → **always raises** `ProvenanceEmitError` (removed silent sqlite fallback)
- `DATABRICKS_RUNTIME_VERSION` set without active Spark → **raises** (cluster must not use sqlite)
- `RE2_STORE_BACKEND=sqlite` → unchanged (local harness / pytest)

**7 instrumented call sites wired**

All agents that call `open_agent_run()` now pass the resolved Spark session:

| Agent | File | Change |
|-------|------|--------|
| BMA, CQA, KPI, Legal, QoE, FTA | `databricks/agents/workstreams/*_agent.py` | `open_agent_run(..., spark=spark)` |
| Profiler | `databricks/jobs/scripts/company_profiler.py` | `open_agent_run(..., spark=_spark)` |

**Pipeline env sync**

`pipeline.py::_sync_env()` now mirrors `RE2_CATALOG=self.catalog` and `RE2_STORE_BACKEND=delta` into `os.environ` on each agent wave (defense-in-depth for any code path that still calls `resolve_store()`).

**E2e runner**

`.dev/hector_merge_e2e_runner.py`:

- `_setup_env()` sets `RE2_STORE_BACKEND=delta` and `RE2_CATALOG=uc13_ale`
- Removed `max_parallelism=1` workaround (uses pipeline default `4`)
- `ok` gate tightened: requires FTA `SUCCESS` and QoE/forecast not `SKIPPED` for FTA failure (not just `SUCCESS > 0`)

### What was deliberately not done

- No `SqliteEvalStore` deletion — local harness CLI (`--store-backend sqlite`) and pytest fixtures unchanged
- No API split into `resolve_store_for_harness` / `resolve_store_for_pipeline` — leaner `spark=` param on `open_agent_run()` instead
- No DAG / FTA parallelism changes
- No `set_pipeline_thread` wiring in `pipeline.py` (separate debt)
- No cluster wet-run yet (Phase 3)

### Tests added / updated

```bash
pytest tests/test_run_context.py tests/test_pipeline_agent_run_context.py eval/retrieval/tests/test_provenance_emitter.py -q
# 37 passed
```

| Test | Purpose |
|------|---------|
| `test_open_agent_run_spark_param_builds_delta_store` | Injected spark → Delta even when `getActiveSession()` is `None` |
| `test_open_agent_run_spark_param_from_worker_thread` | Same, from `ThreadPoolExecutor` worker (DAG simulation) |
| `test_resolve_store_delta_without_spark_raises` | `RE2_STORE_BACKEND=delta` without Spark always raises |
| `test_resolve_store_on_cluster_without_spark_raises` | `DATABRICKS_RUNTIME_VERSION` without Spark raises |
| AST guard in `test_pipeline_agent_run_context.py` | All 7 instrumented mains must pass `spark=` or `store=` |

### Files touched

- `databricks/agents/shared/run_context.py`
- `eval/retrieval/provenance.py`
- `databricks/agents/orchestration/pipeline.py`
- `databricks/agents/workstreams/{business_model,financial_trends,customer_quality,kpi,legal_contracts,quality_of_earnings}_agent.py`
- `databricks/jobs/scripts/company_profiler.py`
- `.dev/hector_merge_e2e_runner.py`
- `tests/test_run_context.py`
- `tests/test_pipeline_agent_run_context.py`
- `eval/retrieval/tests/test_provenance_emitter.py`

### Next step (Phase 3)

1. Elder Care parallel e2e smoke (`max_parallelism=4`) on serverless
2. Confirm: no sqlite `ProgrammingError`; FTA/QoE/forecast execute; warehouse `created_at` refresh
3. Optional: 4-company batch → G1 re-score → `GOLD_LABEL_BOOTSTRAP_HANDOFF.md`

---

## Situation

Post-merge e2e on Databricks serverless failed `financial_trends` on **every company** (parallel and sequential) with:

```
ProgrammingError: SQLite objects created in a thread can only be used in that same thread
```

**Cascade (all 4 companies, identical manifest):**

| Agent | Result |
|-------|--------|
| business_model, kpi, customer_quality, legal_contracts | SUCCESS |
| financial_trends | **FAILED** (sqlite threading) |
| quality_of_earnings, forecast | **SKIPPED** (hard dep on FTA) |
| cross_analysis | SUCCESS **degraded** (missing FTA/QoE/forecast) |
| orchestrator | SUCCESS (memo from stale upstream rows) |
| T9 exec-summary bridge | Ran (stale FTA/QoE Delta data) |

**Downstream:** `uc13_ale.analysis.forecast` table never created; cross_analysis logs `TABLE_OR_VIEW_NOT_FOUND` for forecast. FTA/QoE `created_at` timestamps unchanged (July 7–22) after both e2e batches.

---

## Will this fix unblock e2e?

**Yes — for the agent-execution failure.** The sqlite→Delta fix is the primary blocker for G1 regression scoring and fresh agent table writes.

Once fixed, expect:

| Gate | After fix |
|------|-----------|
| FTA / QoE / forecast agents execute | ✅ Should run (DAG deps satisfied) |
| `forecast` table created on first success | ✅ Agent `main()` DDL guard |
| Parallel DAG (`max_parallelism=4`) | ✅ Intended production mode |
| G1 golden-checklist re-score (Elder Care) | ✅ Unblocked — needs re-run after fix |
| T9 exec summary uses fresh agent data | ✅ Unblocked |
| Gold-label bootstrap (8 intents) | ✅ Unblocked — needs fresh CQA/KPI citations |

**Not automatically fixed by sqlite removal alone:**

- E2e runner must set `RE2_CATALOG=uc13_ale` (currently missing from `.dev/hector_merge_e2e_runner.py`).
- `open_agent_run()` must receive a `DeltaEvalStore` built from the **injected** `spark` param — not `getActiveSession()` on the worker thread (often `None` under `ThreadPoolExecutor`).
- Re-run e2e after code fix to refresh tables and score baselines.

---

## Root cause (confirmed from logs)

### Layer 1 — `resolve_store()` sqlite fallback

`eval/retrieval/provenance.py::resolve_store()`:

1. If `RE2_STORE_BACKEND` unset and `SparkSession.getActiveSession()` is `None` → **`SqliteEvalStore`**
2. Hector's DAG runs agents in `ThreadPoolExecutor` workers (`pipeline.py`, `max_parallelism=4` default)
3. Spark session injected via `main(spark=...)` is **not** passed into store resolution
4. E2e runner does not set `RE2_STORE_BACKEND=delta` or `RE2_CATALOG=uc13_ale`

### Layer 2 — FTA internal sub-threads (why FTA specifically)

`financial_trends_agent.py` is the only agent that compounds the problem:

1. `main()` calls `open_agent_run()` → `resolve_store()` → may create `SqliteEvalStore` on the DAG worker thread
2. `FinancialTrendsAgent.run()` launches 3 sub-agents via `ThreadPoolExecutor(max_workers=3)` with `contextvars.copy_context()`
3. Sub-threads inherit `_ACTIVE_STORE` (the sqlite connection) from the parent thread
4. **SQLite connections are not portable across threads** → `ProgrammingError`

Other agents (BMA, CQA, KPI, Legal, QoE) open/close their store on a single thread and often succeed even when sqlite is selected — but they should still use Delta on cluster.

### Layer 3 — `max_parallelism=1` is NOT a workaround

Sequential Elder Care re-run (`run_id=649261285633616`) **failed identically** — same 6 SUCCESS / 1 FAILED / 2 SKIPPED manifest, same sqlite error. `ThreadPoolExecutor(max_workers=1)` still dispatches each agent on a pool worker thread; FTA's internal 3-way sub-agent pool still crosses threads.

**Do not treat `max_parallelism=1` as a permanent fix.**

---

## Intent (do / don't)

| Do | Don't |
|----|-------|
| Keep `SqliteEvalStore` for local pytest + harness CLI (`--store-backend sqlite`) | Delete sqlite store implementation entirely |
| Make cluster/agent paths **require Delta** when Spark is available | Break existing `eval/retrieval/tests/*` that use tmp sqlite |
| Pass injected `spark` into `open_agent_run(store=DeltaEvalStore(...))` from agent `main()` | Rely on `getActiveSession()` inside worker threads |
| Fail closed (clear error) if Delta unavailable on cluster | Silently fall back to sqlite from agent/pipeline code |
| Set `RE2_CATALOG` + `RE2_STORE_BACKEND=delta` in e2e runner / notebook Cell 1 | Change Hector DAG parallelism as the permanent fix |
| Re-run parallel DAG e2e after fix; confirm FTA/QoE/forecast SUCCESS + timestamp refresh | Assume sequential mode validates regression |

---

## File map

### Prod / agent hot path (change these)

| File | Role |
|------|------|
| `eval/retrieval/provenance.py` | `resolve_store()` — **decision point**: sqlite vs delta (`RE2_STORE_BACKEND`, spark probe) |
| `databricks/agents/shared/run_context.py` | `open_agent_run()` / `close_agent_run()` — calls `_resolve_store()` → `resolve_store()`; stores connection in `ContextVar` |
| `databricks/agents/shared/retrieval.py` | `ProvenanceEmitter.emit()` on every `semantic_search()` via `_ACTIVE_STORE` |
| `databricks/agents/orchestration/pipeline.py` | Parallel DAG (`max_parallelism=4`); `_invoke()` injects `spark=` into `main()` |
| `databricks/agents/workstreams/financial_trends_agent.py` | **FTA-specific:** internal 3-thread sub-agent pool + `open_agent_run()` at `main()` (~L1759) |
| `databricks/agents/workstreams/*_agent.py` | All 6 workstream agents call `open_agent_run()` at `main()` entry |
| `databricks/jobs/scripts/company_profiler.py` | 7th instrumented agent (`profiler`) |
| `.dev/hector_merge_e2e_runner.py` | E2e runner — add `RE2_STORE_BACKEND` / `RE2_CATALOG`; remove `max_parallelism=1` workaround after fix |

### Eval store implementation (keep, narrow usage)

| File | Role |
|------|------|
| `eval/retrieval/store.py` | `SqliteEvalStore` + `DeltaEvalStore` + `retry_on_delta_conflict()` |
| `eval/retrieval/harness.py` | Harness runner; `default_sqlite_path()` for local runs |
| `eval/retrieval/harness_cli.py` | CLI `--store-backend sqlite\|delta` |
| `eval/retrieval/scripts/record_e2e_linkage.py` | Promotion gate CLI |
| `eval/retrieval/scripts/sync_eval_store.py` | `sqlite_to_delta` sync for promoting local runs |
| `eval/retrieval/promotion_gate.py` | `evaluate_promotion()` |

### Docs / ops / evidence

| File | Role |
|------|------|
| `eval/retrieval/README.md` | Authoritative: cluster **must** use `--store-backend delta` |
| `.dev/hector_merge_e2e_run_ids.json` | Parallel e2e run IDs (attempt 2, all 4 companies) |
| `.dev/hector_merge_e2e_results.json` | Parallel batch summaries (all `ok=true` structurally, all 6/1/2 DAG) |
| `.dev/hector_merge_e2e_Elder_Care_sequential.json` | Sequential re-run summary |
| `.dev/hector_merge_e2e_Elder_Care_sequential.log` | **Full stdout** — manifest line ~680, FTA traceback, forecast table errors |
| `.dev/plans/hector-ui-pipeline-merge/CLUSTER_GATES.md` | G1 agent re-scores blocked until this fix |

### Tests (keep sqlite; update if resolve logic changes)

| File | Role |
|------|------|
| `eval/retrieval/tests/test_provenance_emitter.py` | `resolve_store` behavior + emit tests |
| `eval/retrieval/tests/test_promotion_gate.py` | Gate logic via tmp sqlite |
| `tests/test_run_context.py` | `open_agent_run` lifecycle |
| `tests/test_retrieval.py` | Provenance emit from `semantic_search` |

---

## Prior related fixes (context, not duplicate work)

- **FTA thread contextvars (M-RE2 T4)** — `copy_context().run` for sub-agents so `agent_run_id` propagates; fixed silent provenance no-op but **exposes sqlite cross-thread use** when store is sqlite
- **Delta concurrent append** — `retry_on_delta_conflict()` + provenance write lock for FTA's 3 parallel sub-agents writing Delta (works when store is Delta, not sqlite)
- **T1 post-landing** — `_resolve_store()` was adjusted to prefer Delta on cluster (CHANGELOG) — worker-thread `getActiveSession()` gap + sqlite fallback remain

---

## Suggested implementation

### A. Pipeline store resolution (required)

1. **Split resolve paths:**
   - `resolve_store_for_harness()` — sqlite ok (local pytest, harness CLI)
   - `resolve_store_for_pipeline(spark, catalog)` — **delta only**; raise `ProvenanceEmitError` if spark missing
2. **`open_agent_run()`** — add optional `spark` param; when present, build `DeltaEvalStore(spark, catalog=catalog)` directly (skip `resolve_store()` sqlite path).
3. **All agent `main(spark=None)`** — after resolving spark, call:
   ```python
   open_agent_run(..., store=DeltaEvalStore(spark, catalog=catalog))
   ```
4. **Env guard:** when `DATABRICKS_RUNTIME_VERSION` is set, `resolve_store()` must never return `SqliteEvalStore` (belt-and-suspenders).

### B. E2e runner hygiene (required for validation)

In `.dev/hector_merge_e2e_runner.py` `_setup_env()`:

```python
os.environ["RE2_STORE_BACKEND"] = "delta"
os.environ["RE2_CATALOG"] = CATALOG  # uc13_ale
```

Restore `max_parallelism=4` (or omit — use pipeline default) after code fix.

### C. Tests

1. Falsifier: simulate DAG worker thread with injected spark, no `getActiveSession()` → must use Delta, never sqlite.
2. Falsifier: FTA sub-thread with copied context + Delta store → provenance emit succeeds (mock or integration).
3. Optional static guard: no `SqliteEvalStore` reachable from `databricks/agents/**` at runtime on cluster.

### D. Validation sequence

1. Fix code (A + B).
2. Re-run parallel e2e on **Elder Care** first (smoke).
3. Confirm manifest: **9 SUCCESS, 0 FAILED, 0 SKIPPED** (or document expected soft-failures).
4. Confirm warehouse: `financial_trends`, `quality_of_earnings`, `forecast` `created_at` updated today.
5. Re-run all 4 companies parallel.
6. G1 golden-checklist re-score on Elder Care.
7. Proceed to `GOLD_LABEL_BOOTSTRAP_HANDOFF.md`.

---

## Acceptance criteria

- [ ] Parallel DAG (`max_parallelism=4`) completes all 9 agents without sqlite errors on serverless
- [ ] `uc13_ale.analysis.financial_trends` / `quality_of_earnings` / `forecast` rows refresh on e2e re-run
- [ ] `uc13_ale.analysis.forecast` table exists after first successful forecast run
- [x] Local `pytest tests/test_run_context.py eval/retrieval/tests/ -q` still green with tmp sqlite (37 passed in targeted suite)
- [x] Agent paths pass injected `spark=` to `open_agent_run()` (AST guard + 7 call sites)
- [x] `resolve_store()` fail-closed on cluster and `RE2_STORE_BACKEND=delta` without Spark
- [x] E2e runner sets `RE2_STORE_BACKEND=delta` and `RE2_CATALOG=uc13_ale`

---

## Evidence log

| Run | run_id | Mode | DAG | FTA error | Notes |
|-----|--------|------|-----|-----------|-------|
| Parallel batch (attempt 1) | `441895094012314` etc. | `max_parallelism=4` | 6/1/2 | repo root not found | Fixed with `os.chdir(REPO_DB)` |
| Parallel batch (attempt 2) | `1035140483912663` etc. | `max_parallelism=4` | 6/1/2 | sqlite threading | All 4 `ok=true` structurally |
| Sequential Elder Care | `649261285633616` | `max_parallelism=1` | 6/1/2 | **same sqlite error** | Proves parallelism setting is not the fix |
| Sequential log | — | — | — | lines 142–182, 680–688 | `.dev/hector_merge_e2e_Elder_Care_sequential.log` |

**Elder Care sequential outputs (stale upstream):**

- Memo: `final_diligence_memo_Elder_Care_20260727_1635.md`
- Exec summary: 1,416 words (+72 vs 1,344 baseline)
- `diligence_report`: 2 rows; `forecast`: 0 rows

---

## Agent pickup checklist

- [x] Read `.dev/hector_merge_e2e_Elder_Care_sequential.log` (failure evidence)
- [x] Implement §Suggested implementation A (pipeline Delta-only store) — via `spark=` on `open_agent_run()`
- [x] Implement §B (e2e runner env vars)
- [x] Add §C tests
- [ ] Re-run Elder Care parallel e2e
- [ ] Confirm acceptance criteria §above (cluster items)
- [ ] Close G1 in `CLUSTER_GATES.md` with fresh golden-checklist scores
- [ ] Hand off to `GOLD_LABEL_BOOTSTRAP_HANDOFF.md`

---

*Last updated: 2026-07-27 — Phase 1+2 landed (code + local tests); Phase 3 cluster wet-run pending.*
