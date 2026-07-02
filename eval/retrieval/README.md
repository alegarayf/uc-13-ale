# UC13 RE² — Retrieval Evaluation Package

Offline harness, intent registry, gold labels, and eval store for the UC13 retrieval measurement program (M-RE1).

## Local development

```bash
pip install -r eval/retrieval/requirements.txt
pytest eval/retrieval/tests/
```

`pytest.ini` sets `pythonpath = databricks, .` so production `agents.shared.retrieval` and `eval.retrieval` import together.

## CI fixture

Frozen organic slice: `fixtures/elder_care_slice.json` (`EvalFixtureSlice`). Chunk rows are copied from `uc13_ale` at export time; pytest mocks VS/embed only — it does not invent corpus text.

## Cluster baseline runbook (Elder Care / `uc13_ale`)

Run once per Cell 7 ingestion rebuild or retrieval code change. Charter exit gate G2 (VS `company_name` pushdown) is verified during setup.

**Workspace catalog:** Elder Care baseline uses **`uc13_ale` for everything** — corpus, VS index, gold labels, **and** ops tables (`uc13_ale.ops.*`). The program charter examples use `uc13.ops` for a shared merge target; keep ops in `uc13_ale` until you promote upstream.

### 1. Upstream preconditions (§5.15)

- Cell 8c coverage PASS; Vector Search index sync current; join integrity spot-check (R-08).
- Registry intents for this baseline use `catalog: uc13_ale` (not legacy `uc13` default).

### 2. DDL preflight — required before delta baseline

Apply ops DDL **once** before the first `DeltaEvalStore` write. Use the **same catalog as the harness** (`uc13_ale`).

**Notebook cell** (after Cell 1 — `REPO_ROOT` on `sys.path`):

```python
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from eval.retrieval.scripts.apply_ops_ddl import apply_ops_ddl

OPS_CATALOG = "uc13_ale"
n = apply_ops_ddl(OPS_CATALOG)
print(f"Applied {n} statements → {OPS_CATALOG}.ops")
display(spark.sql(f"SHOW TABLES IN {OPS_CATALOG}.ops"))
```

Shell equivalent (repo root on cluster):

```bash
python eval/retrieval/scripts/apply_ops_ddl.py --catalog uc13_ale
```

HALT: do not attempt `--store-backend delta` baseline until this succeeds. Missing DDL causes `insert_run` failures (blocked, not `invalid`).

### 3. G2 — VS `company_name` pushdown probe (required, log result)

Before the harness baseline, run a single probe query with `company_name` filter on the cluster and **record whether filter pushdown was accepted**.

Example (Databricks notebook or job cell):

```python
from databricks.sdk import WorkspaceClient
from agents.shared.retrieval import semantic_search
from pyspark.sql import SparkSession

spark = SparkSession.getActiveSession()
company = "Elder Care"
catalog = "uc13_ale"

# Capture stdout: semantic_search / _query_vector_index logs pushdown acceptance or fallback.
result = semantic_search(
    query="revenue growth historical financial statements",
    spark=spark,
    company_name=company,
    catalog=catalog,
    top_k=5,
)
print(
    f"[G2 probe] company_name={company!r} catalog={catalog!r} "
    f"mode={result.mode} result_count={len(result.chunks)}"
)
```

**Interpretation (charter G2 / §5.15):**

| Log / outcome | Baseline status |
|---------------|-----------------|
| No `VS filter pushdown unavailable` message; filtered query succeeds | Proceed — valid multi-tenant interpretation |
| `VS filter pushdown unavailable (...)` printed; unfiltered fallback used | Mark baseline `harness_status: invalid` — acceptable per M-RE1 exit gate; document remediation (index schema / admin recreate) before using as `baseline_ref_run_id` |

Save probe output in the job log or PR notes. The harness does not auto-mark invalid on probe failure in v1 — operator responsibility per §5.15.

### 4. Cluster baseline harness

**Notebook cell** (recommended):

```python
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from eval.retrieval.harness import EvalHarness
from eval.retrieval.store import DeltaEvalStore

CATALOG = "uc13_ale"
harness = EvalHarness()
store = DeltaEvalStore(spark, catalog=CATALOG)

report = harness.run(
    run_type="baseline",
    company_name="Elder Care",
    catalog=CATALOG,
    store=store,
    store_backend="delta",
    spark=spark,
)
print("run_id:", report.manifest.run_id)
print("harness_status:", report.manifest.harness_status)
```

Shell equivalent:

```bash
python -m eval.retrieval.harness_cli run \
  --store-backend delta \
  --run-type baseline \
  --company-name "Elder Care" \
  --catalog uc13_ale
```

- **Must** pass `--store-backend delta` on cluster (not sqlite).
- Report written to `eval/retrieval/reports/{run_id}.json`.
- Query manifest:

```sql
SELECT * FROM uc13_ale.ops.retrieval_harness_runs WHERE run_id = '<id>';
```

**G4 verify** (Elder Care workspace):

```sql
SELECT run_id, harness_status, completed_at
FROM uc13_ale.ops.retrieval_harness_latest_baseline
WHERE company_name = 'Elder Care' AND catalog = 'uc13_ale';
```

If G2 probe failed, set `harness_status: invalid` on the manifest (operator step) and do not use the run as `baseline_ref_run_id`.

### 5. Optional — local sqlite baseline

For laptop iteration without cluster:

```bash
python -m eval.retrieval.harness_cli run \
  --store-backend sqlite \
  --run-type baseline \
  --company-name "Elder Care" \
  --catalog uc13_ale
```

Store path: `eval/retrieval/.local/re2_store.sqlite` (gitignored). Requires active `SparkSession` for live retrieval dispatch unless tests inject `retrieval_dispatch`.

### 6. Promote local run to Delta (after validation)

When a completed sqlite run should be shared on the cluster:

```bash
python -m eval.retrieval.scripts.sync_eval_store \
  --run-id <id> \
  --direction sqlite_to_delta \
  --catalog uc13_ale
```

Optional: `--sqlite-path <path>`. Idempotent on `run_id` when Delta already has a complete run. Does **not** sync Delta → SQLite.

## M-RE2 cluster validation runbook (FTA pipeline)

Operator steps for M-RE2 exit gates **item 18** (fallback rate) and **item 23** (Elder Care FTA 18-field checklist re-score). Requires `test_pipeline.ipynb` Cell 1 (`set_pipeline_thread`, `REPO_ROOT` on `sys.path`) before any agent `main()` — run Cell 12 **after** Cell 1 and snapshot with Cell 12a before switching `retrieval_mode`.

**Control baseline reference:** 16/18 on the RT7 golden checklist (pre-T4 Control arm); M-RE1 harness baseline `baseline_f0f4f68ac7af`. **Item-23 target:** ≥ **16/18** on Elder Care after M-RE2 OPEX context + provenance fixes.

### Item 18 — keyword fallback rate

**Store backend (read this first):** On a Databricks cluster with an active Spark session, `open_agent_run()` writes pipeline manifests and provenance to **`{catalog}.ops.*` Delta tables** (default catalog from Cell 1 → `uc13_ale`). SQLite at `eval/retrieval/.local/re2_store.sqlite` is the **laptop / no-Spark** fallback only.

**Cluster preflight — run every time the DDL file changes, not just once:** `apply_ops_ddl` is safe to re-run. It applies `CREATE TABLE IF NOT EXISTS` (no-op if the table already exists) **and then** additively reconciles any columns your live table is missing vs. the current schema (e.g. `pipeline_thread_id` added in M-RE2 T1) via `ALTER TABLE ADD COLUMNS` — it never drops or rewrites existing rows.

```python
from eval.retrieval.scripts.apply_ops_ddl import apply_ops_ddl
n = apply_ops_ddl("uc13_ale")
print(f"Applied {n} DDL statements")
# Watch stdout for: "[apply_ops_ddl] additive migration on retrieval_harness_runs: added [...]"
```

If `open_agent_run()` / `fta.main()` fails with `DELTA_METADATA_MISMATCH`, it means your `uc13_ale.ops.retrieval_harness_runs` (or `retrieval_provenance`) table predates a schema change and is missing a column that current code writes. Re-running `apply_ops_ddl` after pulling latest closes this — `CREATE TABLE IF NOT EXISTS` alone does **not**, since it is a no-op on an existing table.

No migration is needed for SQLite — `SqliteEvalStore` creates tables on first write and additively `ALTER TABLE`s new columns on open.

After FTA `main()` completes (`open_agent_run` / `close_agent_run` inside `fta.main()`), read `fallback_rate` from Delta:

```sql
SELECT run_id, harness_status, run_type, fallback_rate, empty_rate, completed_at
FROM uc13_ale.ops.retrieval_harness_runs
WHERE run_type = 'pipeline'
ORDER BY completed_at DESC
LIMIT 5;
```

**Do not** build the sqlite path from `REPO_ROOT` in Cell 1 — that variable points at `databricks/`, not the git repo root. If you must inspect sqlite (local only), use:

```python
from eval.retrieval.provenance import default_sqlite_path
print(default_sqlite_path())
```

### Provenance verify

Confirm provenance rows landed for the FTA `agent_run_id`:

```sql
SELECT COUNT(*) AS provenance_rows
FROM uc13_ale.ops.retrieval_provenance
WHERE run_id = '<fta_agent_run_id>';
```

Expect `provenance_rows > 0` after a full FTA pipeline run with M-RE2 wiring.

**If `harness_status: complete` but `provenance_rows = 0` and `fallback_rate`/`empty_rate` are both `NULL`:** you are hitting a fixed bug, not a config gap — confirm you have pulled the commit containing the `contextvars.copy_context()` fix in `FinancialTrendsAgent.run()`. `ThreadPoolExecutor.submit()` does not inherit the main thread's `agent_run_id` ContextVar by default, so the three FTA sub-agents (Revenue/EBITDA/OPEX) silently skipped provenance emission before this fix. See `.dev/decision-logs/T4-m-re2-threadpool-context-propagation.md`.

### Item 23 — Elder Care E2E checklist re-score

1. Run Cell 12 (Financial Trends Agent) on Elder Care with `catalog=uc13_ale`.
2. Score the 18-field FTA golden checklist (RT7 scorecard); target ≥ **16/18** (Control baseline **16/18**).
3. Run Cell 12a to snapshot the eval arm before changing `retrieval_mode`.
4. Link the checklist score to the pipeline manifest:

```bash
python -m eval.retrieval.scripts.record_e2e_linkage \
  --run-id <fta_agent_run_id> \
  --e2e-agent-id fta \
  --e2e-checklist-score <n> \
  --e2e-checklist-total 18 \
  --e2e-snapshot-table uc13_ale.analysis.financial_trends_eval_snapshot \
  --store-backend delta \
  --catalog uc13_ale
```

Verify linkage:

```sql
SELECT run_id, e2e_agent_id, e2e_checklist_score, e2e_checklist_total, e2e_snapshot_table
FROM uc13_ale.ops.retrieval_harness_runs
WHERE run_id = '<fta_agent_run_id>';
```

Item 23 is **runtime-armed only** — not CI-gated.

## Related CLIs

| Command | Purpose |
|---------|---------|
| `python eval/retrieval/scripts/apply_ops_ddl.py --catalog uc13_ale` | One-time `uc13_ale.ops` DDL (Elder Care workspace) |
| `python -m eval.retrieval.harness_cli run ...` | Harness execution |
| `python -m eval.retrieval.harness_cli validate-baseline ...` | Preflight baseline_ref checks |
| `python -m eval.retrieval.scripts.sync_eval_store --run-id <id> --direction sqlite_to_delta` | SQLite → Delta promotion |
| `python -m eval.retrieval.scripts.record_e2e_linkage --run-id <id> --e2e-agent-id fta --e2e-checklist-score <n> ...` | Link FTA E2E checklist to pipeline manifest |
