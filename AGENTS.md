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

## Shell (Windows / pwsh)

Agent shell is **PowerShell**, not bash. Do **not** write ad-hoc `_quick_*.py` / `_check_*.py` files for one-off probes. If a probe file is unavoidable, put it under `.dev/scratch/<plan-slug>/` — never `.dev/` root. Layout: **`.dev/README.md`**.

**Multi-line Python** — pipe a single-quoted here-string to stdin (preserves `"` and `'`, including SDK args like `wait_timeout="30s"`):

```powershell
@'
import os
from dotenv import load_dotenv
load_dotenv()
# ...
'@ | python -
```

**One-liner** — wrap `-c` in **PowerShell single quotes** (not `"..."`):

```powershell
python -c 'print("ok")'
```

Forbidden: bash heredocs (`<<'EOF'`), `python -c "..."` with nested double quotes, or temp scripts when the above suffices. Reuse committed helpers (e.g. `eval/program/onboarding_cluster_submit.py`) for repeated workflows.

## `.dev` layout

Honor **`.dev/README.md`**. Do not write one-off scripts or `t*_artifacts/` at `.dev/` root.

- One-offs: `.dev/scratch/<plan-slug>/` (prefer stdin / `python -`)
- Reusable helpers: `.dev/scripts/`
- Program dumps: `.dev/plans/<slug>/artifacts/`
- Closed plans: move the whole tree to `.dev/archive/plans/<slug>/` and delete `.dev/plans/<slug>/` (do not move audits or retros)

Never `git add -f` under `.dev/`. If a test or clone needs a file, it does not belong in `.dev`.

Cited-plan archive is deferred: `.dev/pending/dev-archive-wave3.md`.

## Local limits

- No local `pyspark` — use warehouse SQL or remote job submit.
- `dbutils` and notebook cells require a cluster; prefer SDK + serverless jobs from the laptop.
- `databricks` CLI is optional; SDK is the primary path.

## Safety

Read-only queries by default. Do not `DROP`, truncate, or trigger full ingestion rebuilds without explicit operator approval.

## Merge decisions

Before merging any branch that touches `databricks/agents/workstreams/business_model_agent.py` or other pipeline files, check **`.dev/merge-decisions.md`** for standing decisions that must not be silently reverted-in.

In particular: **BMA extraction must remain a single LLM call** over the full unbounded context — see `.dev/merge-decisions.md` and `databricks/CLAUDE.md` (`_call_llm()` / serving-timeout section).
