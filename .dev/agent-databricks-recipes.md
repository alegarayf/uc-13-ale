# Databricks agent recipes (UC-13)

Copy-paste patterns for Cursor agents. Load repo-root `.env` first. Never print tokens.

## Bootstrap

```python
import os
from dotenv import load_dotenv

load_dotenv()  # repo root — run shell commands from repository root

from databricks.sdk import WorkspaceClient

def workspace_client() -> WorkspaceClient:
    return WorkspaceClient(
        host=os.environ["DATABRICKS_SERVER_HOSTNAME"],
        token=os.environ["DATABRICKS_TOKEN"],
    )

def warehouse_id() -> str:
  # DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/<id>
    return os.environ["DATABRICKS_HTTP_PATH"].rstrip("/").split("/")[-1]
```

**Env vars (canonical):**

| Variable | Purpose |
|----------|---------|
| `DATABRICKS_SERVER_HOSTNAME` | Workspace host (`adb-….azuredatabricks.net`) |
| `DATABRICKS_TOKEN` | PAT or OAuth token |
| `DATABRICKS_HTTP_PATH` | SQL warehouse HTTP path |
| `DATABRICKS_CATALOG` | Optional default catalog |
| `DATABRICKS_SCHEMA` | Optional default schema |

Legacy: `databricks/agents/ingestion/tools/uploader.py` uses `DATABRICKS_HOST` — prefer `DATABRICKS_SERVER_HOSTNAME` for new code.

**Defaults:** catalog `uc13_ale`, company `Elder Care`, warehouse `rallyday_sql_warehouse` (serverless).

---

## SQL query (preferred for reads)

```python
w = workspace_client()
stmt = w.statement_execution.execute_statement(
    warehouse_id=warehouse_id(),
    statement="""
        SELECT COUNT(*) AS n
        FROM uc13_ale.ingestion.chunks
        WHERE company_name = 'Elder Care'
    """,
    wait_timeout="30s",
)
assert stmt.status.state.value == "SUCCEEDED", stmt.status
rows = stmt.result.data_array if stmt.result else []
print(rows)
```

**List schemas / tables:**

```sql
SHOW SCHEMAS IN uc13_ale;
SHOW TABLES IN uc13_ale.ingestion;
DESCRIBE TABLE uc13_ale.analysis.financial_trends;
```

---

## Catalog map (`uc13_ale`)

| Schema | Tables / volumes |
|--------|------------------|
| `ingestion` | `chunks`, `embeddings`, `upload_log`; volume `raw_files` |
| `classification` | `doc_relevance`, `company_profile` |
| `analysis` | `business_model`, `financial_trends`, `financial_trends_eval_snapshot`, `customer_quality`, `kpi`, `legal`, `legal_contracts` (view), `quality_of_earnings`; volume `reports` |
| `ops` | `retrieval_harness_runs`, `retrieval_harness_results`, `retrieval_harness_deltas`, `retrieval_harness_latest_baseline`, `retrieval_provenance`, … |

**Vector index:** `uc13_ale.ingestion.embeddings_index`

**Production catalog `uc13`:** same schema layout; production `main()` defaults use `get_param("catalog", default="uc13")`. Do not mix catalogs in one comparison without stating it.

---

## Vector search

```python
w = workspace_client()
resp = w.vector_search_indexes.query_index(
    index_name="uc13_ale.ingestion.embeddings_index",
    columns=["chunk_id", "chunk_text", "company_name", "workstream"],
    query_text="revenue by segment EBITDA",
    num_results=5,
    filters_json='{"company_name": "Elder Care"}',
)
print(resp.result)
```

See `databricks/agents/shared/retrieval.py` for production `semantic_search()` behavior.

---

## Remote Spark / Python (serverless job submit)

Local machine has no `pyspark`. Submit scripts to the workspace and poll via SDK.

**Existing helpers:** `.dev/t2_databricks_submit.py`, `.dev/t2_run_all.py`

```python
# Minimal pattern (see t2_databricks_submit.py for full poll + logs)
from databricks.sdk.service.compute import Environment
from databricks.sdk.service.jobs import JobEnvironment, SparkPythonTask, SubmitTask

w = workspace_client()
me = w.current_user.me().user_name
workspace_script = f"/Users/{me}/my_script.py"

run = w.jobs.submit(
    run_name="agent-probe",
    timeout_seconds=3600,
    environments=[
        JobEnvironment(
            environment_key="default",
            spec=Environment(client="1", dependencies=["pyyaml"]),
        )
    ],
    tasks=[
        SubmitTask(
            task_key="main",
            environment_key="default",
            spark_python_task=SparkPythonTask(
                python_file=workspace_script,
                parameters=["--catalog", "uc13_ale", "--company", "Elder Care"],
            ),
        )
    ],
)
print("run_id", run.run_id)
```

Upload local file first via `workspace.import_` (see `import_text_file` in `.dev/t2_databricks_submit.py`).

**Eval harness on cluster:** `python -m eval.retrieval.harness_cli run --store-backend delta --catalog uc13_ale ...` requires an active `SparkSession` (cluster or submitted job).

---

## Onboarding cluster steps (M4 runbook Steps 3 & 5)

Steps 3 (gold bootstrap) and 5 (harness baseline) in `eval/program/onboarding_runbook.md` need an active `SparkSession`. The workspace is serverless-only — use **`.dev/onboarding_cluster_submit.py`** instead of running those CLIs locally.

**What the helper does:**

1. Loads repo-root `.env` (never prints tokens).
2. Syncs **`eval/retrieval/`** and **`databricks/agents/`** to `/Workspace/Users/<you>/uc-13-ale/`.
3. Submits a serverless `jobs.submit` task with pip deps: `pyyaml`, `pydantic>=2.0`, `mlflow`.
4. Sets **`PYTHONPATH`** to include `databricks/` (harness imports agent shared code) plus repo root.
5. Polls the run, prints `run_id`, exits non-zero on failure.

**Frozen CLI equivalents (run on cluster via the script):**

| Step | Local module invocation |
|------|-------------------------|
| 3 | `python -m eval.retrieval.gold.bootstrap --company "<Display Name>" --catalog uc13_ale` |
| 5 | `python -m eval.retrieval.harness_cli run --store-backend delta --run-type baseline --company-name "<Display Name>" --catalog uc13_ale` |

**Example — Clearsulting pilot (`uc13_ale`):**

```bash
# Step 3 — gold bootstrap (sync + submit + poll)
python .dev/onboarding_cluster_submit.py bootstrap --company "Clearsulting" --catalog uc13_ale

# Step 5 — harness baseline (re-syncs by default)
python .dev/onboarding_cluster_submit.py harness-baseline --company "Clearsulting" --catalog uc13_ale

# Upload only (no job)
python .dev/onboarding_cluster_submit.py sync
```

**Notes:**

- Run from **repository root** so relative paths in synced YAML resolve correctly on the driver.
- Use `--no-sync` only when the workspace copy is already fresh.
- Step 3 gold output lands on the workspace driver; pull `eval/retrieval/gold_labels/<slug>.yaml` back via `workspace.export` or signoff workflow if committing locally.
- Harness success may print a `baseline_<hash>` run_id even when Databricks reports `INTERNAL_ERROR` on clean `SystemExit(0)` — the script checks logs for a baseline id (T9 quirk).

**Related:** `.dev/t2_databricks_submit.py` (generic submit pattern), `eval/program/onboarding_runbook.md` (full eight-step walk).

---

## Files / volumes

Volume paths: `/Volumes/uc13_ale/ingestion/raw_files/{company}/`

```python
# Download via Files API (example)
w = workspace_client()
path = "/Volumes/uc13_ale/analysis/reports/Elder_Care/legal_report.yaml"
data = w.files.download(path)
print(data.contents.read().decode()[:500])
```

---

## Genie (optional)

If `DATABRICKS_GENIE_SPACE_ID` is set, `backend-ai` can route NL queries through Genie. Prefer warehouse SQL for agent debugging unless the task is Genie-specific.

---

## What does not work from the laptop

| Capability | Where it runs |
|------------|----------------|
| `dbutils` | Databricks notebook/cluster only |
| `SparkSession.getActiveSession()` | Cluster or submitted job |
| `test_pipeline.ipynb` cells | Interactive cluster |
| `databricks` CLI | Install separately if desired; SDK is primary |

---

## Safety

- **Default:** `SELECT`, `SHOW`, `DESCRIBE`, `COUNT` — read-only.
- **Ask first:** `DROP`, `DELETE`, `TRUNCATE`, `ingestion_parser.main()` full rebuild, `ensure_coverage` bulk append, workflow triggers, schema migrations.
- **Never:** print or commit tokens; paste secrets into chat or code.

---

## Related docs

- Pipeline rules: `databricks/CLAUDE.md`
- Eval / ops SQL examples: `eval/retrieval/README.md`
- Operator T2 submit: `.dev/t2_databricks_submit.py`
- Onboarding Steps 3 & 5: `.dev/onboarding_cluster_submit.py`
