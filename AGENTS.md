# Agent instructions (UC-13)

## Databricks access

This repository has **live Databricks workspace access** from the developer machine.

- Credentials live in the **repo-root `.env`** (never print or commit tokens).
- Use Python **`databricks-sdk`** (`WorkspaceClient`) — load env with `load_dotenv()` from the repo root before connecting.
- **Do not ask the operator to run SQL or inspect tables manually** when you can query the warehouse yourself.
- **Default catalog:** `uc13_ale` (dev/eval). Production script defaults use `uc13` — see `databricks/CLAUDE.md`.
- **Default company:** `Elder Care` unless the task specifies another.

When a task needs SQL, schema inspection, vector search, job submission, or volume files:

1. **Load the `databricks-access` skill** (`.cursor/skills/databricks-access/SKILL.md`), or
2. Read **`.dev/agent-databricks-recipes.md`** for copy-paste patterns.

For pipeline implementation rules (ingestion, notebooks, agent code), read **`databricks/CLAUDE.md`**.

## Local limits

- No local `pyspark` — use warehouse SQL or remote job submit.
- `dbutils` and notebook cells require a cluster; prefer SDK + serverless jobs from the laptop.
- `databricks` CLI is optional; SDK is the primary path.

## Safety

Read-only queries by default. Do not `DROP`, truncate, or trigger full ingestion rebuilds without explicit operator approval.
