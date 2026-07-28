# Databricks notebook source
# MAGIC %md
# MAGIC # VDR Diligence Pipeline — job entry notebook
# MAGIC
# MAGIC Thin notebook the **VDR Diligence Pipeline** job runs. It exists so the VDR
# MAGIC UI can trigger the job by passing run parameters that arrive as widgets
# MAGIC (`table_name`, `id`) — the pattern the frontend uses. There are **no**
# MAGIC parameters declared on the task itself; the UI supplies them at call time.
# MAGIC
# MAGIC It reads the two widgets and delegates to
# MAGIC `jobs/scripts/run_vdr_pipeline.py:run_vdr_pipeline()`, which owns the full
# MAGIC Phase 1-5 pipeline + VDR record lifecycle.

# COMMAND ----------

# Parameters supplied by the caller (VDR UI run-now → notebook params → widgets).
# The UI sends the record id as "record_id"; "id" is accepted as a fallback for
# manual runs.
dbutils.widgets.text("table_name", "", "The name of the table where the vdr record lives")
dbutils.widgets.text("record_id", "", "The id of the record to process within the table")
dbutils.widgets.text("id", "", "Alias for record_id (manual runs)")

# COMMAND ----------

import os
import sys
from pathlib import Path

table_name = dbutils.widgets.get("table_name") or "rallyday_partners_llc.default.companies_vdr_history"
record_id = dbutils.widgets.get("record_id") or dbutils.widgets.get("id")
if not record_id:
    raise ValueError(
        "Widget 'record_id' (or 'id') is required — the companies_vdr_history "
        "record id to process."
    )

# Mirror into env so imported script modules resolve the same values via their
# get_param()/os.environ fallback (dbutils.widgets is not a global inside modules).
os.environ["tableName"] = table_name
os.environ["id"] = str(record_id)

# COMMAND ----------

# Put databricks/ (agents package) and jobs/scripts on sys.path so the runner and
# the agent packages import cleanly regardless of the Git-folder checkout path.
_start = Path(os.getcwd())
_scripts_dir = None
for _base in [_start, *_start.parents]:
    if (_base / "databricks" / "jobs" / "scripts").exists():
        _scripts_dir = _base / "databricks" / "jobs" / "scripts"
        break
    if (_base / "jobs" / "scripts").exists():
        _scripts_dir = _base / "jobs" / "scripts"
        break
if _scripts_dir is None:
    raise RuntimeError(f"Could not locate databricks/jobs/scripts from cwd={_start}")
_repo_root = _scripts_dir.parent.parent  # → .../databricks (contains the agents package)
for _p in (str(_repo_root), str(_scripts_dir)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# COMMAND ----------

from run_vdr_pipeline import run_vdr_pipeline

result = run_vdr_pipeline(table_name, int(record_id))
print(f"VDR pipeline {result.get('status')} — {result.get('company_name')} → {result.get('output_dir')}")

# COMMAND ----------

# Surface the result to the job run output.
dbutils.notebook.exit(str(result.get("status")))
