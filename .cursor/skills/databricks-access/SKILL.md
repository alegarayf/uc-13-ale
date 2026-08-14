---
name: databricks-access
description: >-
  Query and operate the live Databricks workspace for UC-13 from the developer
  machine using databricks-sdk and repo-root .env. Use when the task needs SQL
  on uc13_ale or uc13, Unity Catalog schema inspection, chunk/embedding counts,
  analysis table reads, vector search probes, serverless job submit, volume
  file download, retrieval harness ops tables, or any live workspace data —
  including when the user says query databricks, check the warehouse, spark,
  unity catalog, Elder Care data, or run something on the cluster.
---

# Databricks access (UC-13)

Load this skill when the task needs **live workspace data or remote execution**. Do not ask the operator to run SQL manually.

## Quick start

1. `load_dotenv()` from **repo root** (`.env` has `DATABRICKS_SERVER_HOSTNAME`, `DATABRICKS_TOKEN`, `DATABRICKS_HTTP_PATH`).
2. Connect with `WorkspaceClient(host=..., token=...)`.
3. **Reads:** `statement_execution.execute_statement` against warehouse id from `DATABRICKS_HTTP_PATH` (last path segment).
4. **Spark / pyspark:** submit a serverless job — no local `pyspark`.

Full copy-paste recipes: **[`.dev/agent-databricks-recipes.md`](../../.dev/agent-databricks-recipes.md)**

## Defaults

| Setting | Value |
|---------|-------|
| Dev/eval catalog | `uc13_ale` |
| Production script default | `uc13` (`get_param("catalog", default="uc13")`) |
| Default company | `Elder Care` |
| SQL warehouse | `rallyday_sql_warehouse` (serverless) |
| Vector index | `uc13_ale.ingestion.embeddings_index` |

## Access paths

| Need | Method |
|------|--------|
| SQL / table inspection | SDK `statement_execution` |
| Vector search | `vector_search_indexes.query_index` |
| Remote Python + Spark | `jobs.submit` + `workspace.import_` — see `.dev/t2_databricks_submit.py` |
| Onboarding Steps 3 & 5 (bootstrap + harness) | `.dev/onboarding_cluster_submit.py` — see [Onboarding cluster steps](../../.dev/agent-databricks-recipes.md#onboarding-cluster-steps-m4-runbook-steps-3--5) in recipes |
| Pipeline code behavior | `databricks/CLAUDE.md` |
| Eval harness ops | `uc13_ale.ops.*` — see `eval/retrieval/README.md` |

## Catalog (uc13_ale)

- **`ingestion`:** `chunks`, `embeddings`, `upload_log`, volume `raw_files`
- **`classification`:** `doc_relevance`, `company_profile`
- **`analysis`:** workstream output tables + volume `reports`
- **`ops`:** retrieval harness / provenance tables

## Safety

- Read-only by default (`SELECT`, `SHOW`, `DESCRIBE`).
- Confirm with operator before: `DROP`, `DELETE`, `TRUNCATE`, full parser rebuild (`ingestion_parser.main()`), workflow runs, schema migrations.
- Never print or commit tokens.

## Local limits

No `dbutils`, no local `pyspark`, no notebook execution from Cursor — use SDK SQL or job submit.

## Operator scripts (reuse, don't reinvent)

- `.dev/t2_databricks_submit.py` — `WorkspaceClient`, import file, submit serverless Python
- `.dev/onboarding_cluster_submit.py` — M4 runbook Steps 3 & 5 (gold bootstrap + harness baseline)
- `.dev/t2_run_all.py` — batch T2 baseline runs
- `eval/retrieval/harness_cli.py` — harness CLI (needs cluster Spark for `--store-backend delta`)
