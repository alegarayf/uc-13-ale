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

### 1. Upstream preconditions (§5.15)

- Cell 8c coverage PASS; Vector Search index sync current; join integrity spot-check (R-08).
- Registry intents for this baseline use `catalog: uc13_ale` (not legacy `uc13` default).

### 2. DDL preflight — required before delta baseline

Apply ops DDL **once** per workspace/catalog before the first `DeltaEvalStore` write:

```bash
python eval/retrieval/scripts/apply_ops_ddl.py --catalog uc13
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

```bash
python -m eval.retrieval.harness_cli run \
  --store-backend delta \
  --run-type baseline \
  --company-name "Elder Care" \
  --catalog uc13_ale
```

- **Must** pass `--store-backend delta` on cluster (not sqlite).
- Report written to `eval/retrieval/reports/{run_id}.json`.
- Query manifest: `SELECT * FROM uc13.ops.retrieval_harness_runs WHERE run_id = '<id>'`.

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
  --direction sqlite_to_delta
```

Optional: `--catalog uc13`, `--sqlite-path <path>`. Idempotent on `run_id` when Delta already has a complete run. Does **not** sync Delta → SQLite.

## Related CLIs

| Command | Purpose |
|---------|---------|
| `python eval/retrieval/scripts/apply_ops_ddl.py --catalog uc13` | One-time `uc13.ops` DDL |
| `python -m eval.retrieval.harness_cli run ...` | Harness execution |
| `python -m eval.retrieval.harness_cli validate-baseline ...` | Preflight baseline_ref checks |
| `python -m eval.retrieval.scripts.sync_eval_store --run-id <id> --direction sqlite_to_delta` | SQLite → Delta promotion |
