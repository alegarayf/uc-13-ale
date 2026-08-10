"""run_ingestion_pipeline param surface tests (M2 T4)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = _REPO_ROOT / "databricks" / "jobs" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import run_ingestion_pipeline as rip  # noqa: E402


@pytest.fixture
def mock_pipeline(monkeypatch):
    monkeypatch.setattr(rip, "_find_scripts_dir", lambda: str(_SCRIPTS_DIR))
    monkeypatch.setattr(rip, "_find_repo_root", lambda _scripts_dir: str(_REPO_ROOT))

    def _fake_import(module_name: str, scripts_dir: str):
        mod = MagicMock()
        mod.main = MagicMock(return_value=None)
        return mod

    monkeypatch.setattr(rip, "_import_script", _fake_import)


def test_skip_sync_sync_only_mirrored_to_environ(mock_pipeline):
    """Falsifier: skip_sync/sync_only kwargs must mirror to os.environ as true/false strings."""
    keys = ("skip_sync", "sync_only")
    saved = {k: os.environ.get(k) for k in keys}
    try:
        rip.run_ingestion_pipeline(
            company_name="Elder Care",
            skip_download=True,
            skip_sync=True,
            sync_only=False,
        )
        assert os.environ["skip_sync"] == "true"
        assert os.environ["sync_only"] == "false"
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_no_coverage_backfill_phase_key_in_summary(mock_pipeline):
    """Falsifier: Phase 2c removal must drop coverage_backfill from the phases dict entirely."""
    summary = rip.run_ingestion_pipeline(
        company_name="Elder Care",
        skip_download=True,
    )
    assert "coverage_backfill" not in summary["phases"]
    assert "ingestion_parser" in summary["phases"]
    assert "company_profiler" in summary["phases"]
