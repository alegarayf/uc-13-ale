"""
vdr_progress.py — the UI progress signal for the VDR runner.

Gives the Project Lighthouse UI enough state to render a stage list, without
changing `processing_status`'s existing vocabulary/semantics and without
touching anything under `agents/`. Progress lives in four additive, nullable
columns on `rallyday_partners_llc.default.companies_vdr_history`:
`progress_stage`, `progress_pct`, `progress_json`, `stage_updated_at`. A row
that never gets a progress write reads NULL across all four, so an unmodified
UI reading only `processing_status` is unaffected.

**T08 Step 0 (A-2), answered against the warehouse (profile `rallyday`,
2026-09-08):** `ALTER TABLE ... ADD COLUMNS (...)` IS permitted on
`companies_vdr_history` — confirmed live: the four columns above were added to
the real table and now show up in `DESCRIBE TABLE`. But the `IF NOT EXISTS`
clause the plan assumed is not valid syntax on this SQL engine — it raises
`PARSE_SYNTAX_ERROR` unconditionally (regardless of whether the columns
already exist), both as `ADD COLUMNS IF NOT EXISTS (...)` and as the singular
`ADD COLUMN IF NOT EXISTS col type`. So idempotency cannot come from the SQL
text; `ensure_progress_columns` gets it by issuing a bare `ADD COLUMNS` and
swallowing the resulting `FIELD_ALREADY_EXISTS` (SQLSTATE 42710) on every call
after the first, same as it swallows a genuine permission refusal. The
columns path did not need the `uc13_preview.analysis.vdr_progress` fallback
described in the plan.

**Never the drop-and-recreate pattern.** Several Phase 3 agents guard schema
drift with an `_EXPECTED_COLS` check that drops and recreates their table
(`databricks/CLAUDE.md`, "Schema changes in analysis tables"). That pattern is
for tables this pipeline owns outright. `companies_vdr_history` is owned by
the UI and holds live records — this module only ever adds columns or updates
one row by `id`, never drops or recreates the table.

A progress write must never be able to fail a diligence run: every public
function and method here swallows its own exceptions and prints
`[vdr_progress] <what failed>: <exc>` instead of raising.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from run_vdr_pipeline import _now_iso, _update_vdr_record

# Branch A (a CIM exists) — one stage per externally observable step.
STAGES_CIM: list[tuple[str, str]] = [
    ("cim_detection",          "Scanning the data room for a CIM"),
    ("cim_ingestion",          "Ingesting the CIM"),
    ("cim_agents",             "Running the diligence agents on the CIM"),
    ("executive_review_ready", "Executive review ready"),
    ("vdr_ingestion",          "Ingesting the full data room"),
    ("vdr_agents",             "Running the diligence agents on the full data room"),
    ("final_report",           "Building the final diligence report"),
    ("final_report_ready",     "Final report ready"),
]

# Branch B (no CIM) — deliberately collapses ingestion + agents into ONE
# `vdr_pipeline` stage. The no-CIM branch makes a single run_full_pipeline()
# call that does both internally and only returns when both are finished; the
# runner cannot observe that inner boundary from outside. Splitting it into
# two stages here would mean either fabricating a `finished_at` timestamp for
# `vdr_ingestion` or back-filling both stages as done at the same instant — a
# bar that sits still for the whole run and then jumps two steps. One honest
# stage beats two dishonest ones (plan §4).
STAGES_FULL: list[tuple[str, str]] = [
    ("vdr_scan",               "Scanning the data room"),
    ("vdr_pipeline",           "Ingesting the data room and running the diligence agents"),
    ("executive_review_ready", "Executive review ready"),
    ("final_report",           "Building the final diligence report"),
    ("final_report_ready",     "Final report ready"),
]

_STATUS_PENDING = "pending"
_STATUS_PROCESSING = "processing"
_STATUS_DONE = "done"
_STATUS_FAILED = "failed"
_STATUS_SKIPPED = "skipped"

_TERMINAL_STATUSES = frozenset({_STATUS_DONE, _STATUS_FAILED, _STATUS_SKIPPED})


def ensure_progress_columns(spark: Any, table_name: str) -> None:
    """Idempotently add the four progress columns to `table_name`.

    Issues a bare `ALTER TABLE ... ADD COLUMNS (...)` (no `IF NOT EXISTS` —
    see the module docstring for why) and swallows the failure, whether that
    failure is "columns already exist" (the expected steady state after the
    first successful call) or an outright permission refusal. Either way a
    workspace that can't take the ALTER must still complete diligence, just
    without progress. `table_name` is trusted, notebook-widget input — same
    assumption every other f-string SQL statement in this runner already
    makes.
    """
    try:
        spark.sql(
            f"ALTER TABLE {table_name} ADD COLUMNS ("
            "progress_stage STRING, progress_pct INT, "
            "progress_json STRING, stage_updated_at STRING)"
        )
    except Exception as exc:  # noqa: BLE001 - must never fail a diligence run
        print(f"[vdr_progress] ensure_progress_columns: {exc}")


class Progress:
    """A thin progress emitter, not a framework.

    Holds the ordered stage list in memory and re-serializes the whole thing
    into `progress_json` on every write, so the UI can render the bar without
    knowing which branch (CIM vs full-room) produced it.
    """

    def __init__(
        self,
        spark: Any,
        table_name: str,
        record_id: int,
        stages: list[tuple[str, str]],
        updater: Callable[..., None] | None = None,
    ) -> None:
        self._spark = spark
        self._table_name = table_name
        self._record_id = record_id
        self._updater = updater or _update_vdr_record
        self._order: list[str] = [key for key, _label in stages]
        self._stages: dict[str, dict[str, Any]] = {
            key: {
                "key": key,
                "label": label,
                "status": _STATUS_PENDING,
                "started_at": None,
                "finished_at": None,
                "artifacts": None,
            }
            for key, label in stages
        }
        self._current_key: str | None = None
        self._last_pct = 0

    def start(self, key: str) -> None:
        try:
            self._transition(key, _STATUS_PROCESSING)
        except Exception as exc:  # noqa: BLE001 - must never fail a diligence run
            print(f"[vdr_progress] start({key!r}): {exc}")

    def complete(self, key: str, artifacts: Any = None) -> None:
        try:
            self._transition(key, _STATUS_DONE, artifacts=artifacts)
        except Exception as exc:  # noqa: BLE001 - must never fail a diligence run
            print(f"[vdr_progress] complete({key!r}): {exc}")

    def fail(self, key: str, error: str) -> None:
        try:
            self._transition(key, _STATUS_FAILED, error=error)
        except Exception as exc:  # noqa: BLE001 - must never fail a diligence run
            print(f"[vdr_progress] fail({key!r}): {exc}")

    def skip(self, key: str, reason: str | None = None) -> None:
        try:
            self._transition(key, _STATUS_SKIPPED, error=reason)
        except Exception as exc:  # noqa: BLE001 - must never fail a diligence run
            print(f"[vdr_progress] skip({key!r}): {exc}")

    def publish(self, columns: dict[str, Any]) -> None:
        """Merge extra record columns (e.g. `results_location`) into the
        same UPDATE as the current progress write, so publishing the
        executive review early costs no extra round trip."""
        try:
            self._write(extra_columns=columns)
        except Exception as exc:  # noqa: BLE001 - must never fail a diligence run
            print(f"[vdr_progress] publish: {exc}")

    # -- internals ----------------------------------------------------

    def _transition(
        self,
        key: str,
        status: str,
        *,
        artifacts: Any = None,
        error: str | None = None,
    ) -> None:
        stage = self._stages.get(key)
        if stage is None:
            print(f"[vdr_progress] unknown stage key {key!r}, ignoring")
            return
        now = _now_iso()
        if status == _STATUS_PROCESSING:
            stage["started_at"] = now
        elif status in _TERMINAL_STATUSES:
            if stage["started_at"] is None:
                stage["started_at"] = now
            stage["finished_at"] = now
            if artifacts is not None:
                stage["artifacts"] = artifacts
            if error is not None:
                stage["error"] = error
        stage["status"] = status
        self._current_key = key
        self._write()

    def _pct(self) -> int:
        total = len(self._order)
        terminal = sum(1 for s in self._stages.values() if s["status"] in _TERMINAL_STATUSES)
        pct = round(100 * terminal / total) if total else 0
        pct = max(pct, self._last_pct)
        self._last_pct = pct
        return pct

    def _stage_list(self) -> list[dict[str, Any]]:
        return [self._stages[key] for key in self._order]

    def _write(self, extra_columns: dict[str, Any] | None = None) -> None:
        columns: dict[str, Any] = {
            "progress_stage": self._current_key,
            "progress_pct": self._pct(),
            "progress_json": json.dumps(self._stage_list()),
            "stage_updated_at": _now_iso(),
        }
        if extra_columns:
            columns.update(extra_columns)
        self._updater(self._spark, self._table_name, self._record_id, columns)
