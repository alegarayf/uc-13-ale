"""sync_eval_store CLI contract tests."""

from __future__ import annotations

import pytest

from eval.retrieval.errors import SyncError
from eval.retrieval.scripts import sync_eval_store as sync_module
from eval.retrieval.store import SqliteEvalStore


def test_build_parser_requires_run_id_and_direction():
    parser = sync_module.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
    args = parser.parse_args(
        ["--run-id", "baseline_local_001", "--direction", "sqlite_to_delta"]
    )
    assert args.run_id == "baseline_local_001"
    assert args.direction == "sqlite_to_delta"
    assert args.catalog == "uc13"


def test_sync_eval_store_rejects_unknown_direction():
    with pytest.raises(ValueError, match="unsupported direction"):
        sync_module.sync_eval_store("run_1", direction="delta_to_sqlite")


def test_sync_eval_store_requires_spark_session(monkeypatch):
    monkeypatch.setattr(
        sync_module,
        "DeltaEvalStore",
        lambda *args, **kwargs: pytest.fail("DeltaEvalStore should not be constructed"),
    )

    class _SparkModule:
        @staticmethod
        def getActiveSession():
            return None

    monkeypatch.setitem(
        __import__("sys").modules,
        "pyspark.sql",
        type("m", (), {"SparkSession": _SparkModule})(),
    )
    with pytest.raises(RuntimeError, match="Active SparkSession required"):
        sync_module.sync_eval_store("run_1", direction="sqlite_to_delta")


def test_main_returns_nonzero_on_sync_error(monkeypatch):
    def _raise(*_args, **_kwargs):
        raise SyncError("sqlite source missing run_id: missing")

    monkeypatch.setattr(sync_module, "sync_eval_store", _raise)
    assert sync_module.main(["--run-id", "missing", "--direction", "sqlite_to_delta"]) == 1


def test_promote_sqlite_run_requires_delta_backend(tmp_path):
    store = SqliteEvalStore(tmp_path / "local.sqlite")
    with pytest.raises(SyncError):
        store.promote_sqlite_run("baseline_test")
    store.close()
