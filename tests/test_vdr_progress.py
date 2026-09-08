"""Unit tests for jobs/scripts/vdr_progress.py — the UI progress emitter.

Mocks Spark/the updater so this runs offline, no cluster needed. Covers: a
full happy sequence, monotonic progress_pct reaching exactly 100, fail()
behaviour, exception-swallowing on every public method (including
ensure_progress_columns), unknown-stage-key no-ops, publish()'s single-UPDATE
merge, and progress_json round-tripping through json.loads at every step.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "databricks" / "jobs" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import vdr_progress as vp  # noqa: E402


class _RecordingUpdater:
    """Stands in for run_vdr_pipeline._update_vdr_record: records every call
    instead of touching Spark."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, spark, table_name, record_id, updates) -> None:
        self.calls.append(dict(updates))


class _RaisingUpdater:
    """An updater that raises on every call — proves the public methods
    swallow the exception instead of propagating it."""

    def __call__(self, spark, table_name, record_id, updates) -> None:
        raise RuntimeError("boom: simulated Spark/UPDATE failure")


def _latest_payload(updates_log: list[dict]) -> dict:
    return updates_log[-1]


def _stages_by_key(payload: dict) -> dict[str, dict]:
    stages = json.loads(payload["progress_json"])
    return {s["key"]: s for s in stages}


def test_happy_sequence_over_stages_cim_is_well_formed_at_every_step():
    updater = _RecordingUpdater()
    progress = vp.Progress(spark=None, table_name="t", record_id=1, stages=vp.STAGES_CIM, updater=updater)

    for key, _label in vp.STAGES_CIM:
        progress.start(key)
        progress.complete(key, artifacts=[f"{key}.txt"])

    assert len(updater.calls) == len(vp.STAGES_CIM) * 2

    expected_order = [key for key, _label in vp.STAGES_CIM]
    for call in updater.calls:
        stages = json.loads(call["progress_json"])  # must always parse
        assert [s["key"] for s in stages] == expected_order
        processing_count = sum(1 for s in stages if s["status"] == "processing")
        assert processing_count <= 1

    final = _stages_by_key(_latest_payload(updater.calls))
    for key, _label in vp.STAGES_CIM:
        assert final[key]["status"] == "done"
        assert final[key]["started_at"] is not None
        assert final[key]["finished_at"] is not None
        assert final[key]["artifacts"] == [f"{key}.txt"]

    assert _latest_payload(updater.calls)["progress_pct"] == 100


def test_progress_pct_is_monotonic_and_reaches_exactly_100():
    updater = _RecordingUpdater()
    progress = vp.Progress(spark=None, table_name="t", record_id=1, stages=vp.STAGES_FULL, updater=updater)

    for key, _label in vp.STAGES_FULL:
        progress.start(key)
        progress.complete(key)

    pcts = [call["progress_pct"] for call in updater.calls]
    assert pcts == sorted(pcts)
    assert pcts[-1] == 100


def test_fail_marks_stage_failed_keeps_earlier_done_later_pending_never_lowers_pct():
    updater = _RecordingUpdater()
    progress = vp.Progress(spark=None, table_name="t", record_id=1, stages=vp.STAGES_FULL, updater=updater)

    keys = [key for key, _label in vp.STAGES_FULL]
    assert len(keys) >= 3

    progress.start(keys[0])
    progress.complete(keys[0])
    pct_before_failure = _latest_payload(updater.calls)["progress_pct"]

    progress.start(keys[1])
    progress.fail(keys[1], "ingestion_parser returned FAILED")

    payload = _latest_payload(updater.calls)
    stages = _stages_by_key(payload)
    assert stages[keys[0]]["status"] == "done"
    assert stages[keys[1]]["status"] == "failed"
    for later_key in keys[2:]:
        assert stages[later_key]["status"] == "pending"
        assert stages[later_key]["started_at"] is None
        assert stages[later_key]["finished_at"] is None

    assert payload["progress_pct"] >= pct_before_failure


def test_every_public_method_swallows_a_raising_updater_and_a_normal_sequence_still_completes(capsys):
    raising = vp.Progress(spark=None, table_name="t", record_id=1, stages=vp.STAGES_FULL, updater=_RaisingUpdater())

    key0 = vp.STAGES_FULL[0][0]
    # None of these may raise, despite the updater raising on every call.
    raising.start(key0)
    raising.complete(key0, artifacts=["x"])
    raising.fail(key0, "err")
    raising.skip(key0, "reason")
    raising.publish({"results_location": "/vol/x"})

    printed = capsys.readouterr().out
    assert "[vdr_progress]" in printed

    updater = _RecordingUpdater()
    normal = vp.Progress(spark=None, table_name="t", record_id=1, stages=vp.STAGES_FULL, updater=updater)
    for key, _label in vp.STAGES_FULL:
        normal.start(key)
        normal.complete(key)
    assert _latest_payload(updater.calls)["progress_pct"] == 100


def test_ensure_progress_columns_swallows_a_raising_spark(capsys):
    class _RaisingSpark:
        def sql(self, *_args, **_kwargs):
            raise RuntimeError("PARSE_SYNTAX_ERROR or FIELD_ALREADY_EXISTS or refused")

    vp.ensure_progress_columns(_RaisingSpark(), "rallyday_partners_llc.default.companies_vdr_history")
    assert "[vdr_progress]" in capsys.readouterr().out


def test_ensure_progress_columns_issues_a_bare_add_columns_without_if_not_exists():
    calls: list[str] = []

    class _Spark:
        def sql(self, statement, *_args, **_kwargs):
            calls.append(statement)

    vp.ensure_progress_columns(_Spark(), "some.table")
    assert len(calls) == 1
    assert "ADD COLUMNS" in calls[0]
    assert "IF NOT EXISTS" not in calls[0]


def test_unknown_stage_key_is_a_noop_with_a_warning_not_a_keyerror(capsys):
    updater = _RecordingUpdater()
    progress = vp.Progress(spark=None, table_name="t", record_id=1, stages=vp.STAGES_FULL, updater=updater)

    progress.start("not_a_real_stage")
    progress.complete("not_a_real_stage")
    progress.fail("not_a_real_stage", "err")
    progress.skip("not_a_real_stage")

    assert updater.calls == []
    assert "unknown stage key" in capsys.readouterr().out


def test_publish_merges_extra_columns_into_the_same_update_as_progress_columns():
    updater = _RecordingUpdater()
    progress = vp.Progress(spark=None, table_name="t", record_id=1, stages=vp.STAGES_CIM, updater=updater)

    key0 = vp.STAGES_CIM[0][0]
    progress.start(key0)
    progress.complete(key0, artifacts=["executive_summary.pdf"])

    calls_before = len(updater.calls)
    progress.publish({"results_location": "/Volumes/rallyday_partners_llc/default/vdr/co/ts/"})

    assert len(updater.calls) == calls_before + 1
    payload = _latest_payload(updater.calls)
    assert payload["results_location"] == "/Volumes/rallyday_partners_llc/default/vdr/co/ts/"
    assert "progress_stage" in payload
    assert "progress_pct" in payload
    assert "progress_json" in payload
    assert "stage_updated_at" in payload
    json.loads(payload["progress_json"])  # still valid JSON in the merged call


def test_progress_json_round_trips_through_json_loads_at_every_step():
    updater = _RecordingUpdater()
    progress = vp.Progress(spark=None, table_name="t", record_id=1, stages=vp.STAGES_CIM, updater=updater)

    for key, _label in vp.STAGES_CIM:
        progress.start(key)
        progress.complete(key)

    for call in updater.calls:
        stages = json.loads(call["progress_json"])
        assert isinstance(stages, list)
        for stage in stages:
            assert set(stage) >= {"key", "label", "status", "started_at", "finished_at", "artifacts"}


def test_nothing_under_agents_imports_vdr_progress():
    agents_dir = Path(__file__).resolve().parents[1] / "databricks" / "agents"
    offenders = []
    for path in agents_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "vdr_progress" in text:
            offenders.append(str(path))
    assert offenders == [], f"vdr_progress imported under agents/: {offenders}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
