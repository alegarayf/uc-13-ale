# Databricks notebook source
# MAGIC %md
# MAGIC # VDR Rainmaker — job entry notebook
# MAGIC
# MAGIC Thin notebook the **VDR Diligence Pipeline** job runs (`617196299594076`).
# MAGIC Same widget-based invocation pattern (`table_name`, `record_id`), plus an
# MAGIC optional `special_folder` widget and a `no_cim_mode` kill switch.
# MAGIC
# MAGIC It reads the widgets and delegates to
# MAGIC `jobs/scripts/run_vdr_rainmaker.py:run_vdr_rainmaker()`, which makes the
# MAGIC one decision this job needs: if a CIM is found in the data room, run a
# MAGIC CIM-scoped diligence pass and render the Rainmaker "Opportunity Summary"
# MAGIC PDF; otherwise (when `no_cim_mode="full"`, the default) run the full
# MAGIC Phase 1-5 pipeline over the whole data room and render the SAME
# MAGIC Rainmaker-format executive review, plus the full diligence memo
# MAGIC (`full_report.docx`). Set `no_cim_mode="noop"` to restore the old
# MAGIC message-only behavior without a code change. See
# MAGIC `docs/plans/connect-all-vdr-er.md`.

# COMMAND ----------

dbutils.widgets.text("table_name", "", "The name of the table where the vdr record lives")
dbutils.widgets.text("record_id", "", "The id of the record to process within the table")
dbutils.widgets.text("id", "", "Alias for record_id (manual runs)")
dbutils.widgets.text(
    "special_folder", "",
    "Optional data-room folder to use for CIM detection",
)
dbutils.widgets.text(
    "no_cim_mode", "full",
    "What to do when no CIM is found: 'full' (run Phase 1-5) or 'noop'",
)
dbutils.widgets.text(
    "vision_endpoint", "databricks-claude-haiku-4-5",
    "Vision LLM endpoint for figure/scanned CIM pages ('' to disable)",
)

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

os.environ["tableName"] = table_name
os.environ["id"] = str(record_id)
os.environ["special_folder"] = dbutils.widgets.get("special_folder")
os.environ["no_cim_mode"] = dbutils.widgets.get("no_cim_mode") or "full"
os.environ["vision_endpoint"] = dbutils.widgets.get("vision_endpoint")

# COMMAND ----------

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

from run_vdr_rainmaker import run_vdr_rainmaker

result = run_vdr_rainmaker(
    table_name,
    int(record_id),
    special_folder=os.environ.get("special_folder", ""),
    no_cim_mode=os.environ.get("no_cim_mode", "full"),
)
print(f"VDR Rainmaker {result.get('status')} ({result.get('mode', 'n/a')}) — {result.get('company_name')}")

# COMMAND ----------

dbutils.notebook.exit(str(result.get("status")))
