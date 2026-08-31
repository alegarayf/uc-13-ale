"""T7 — pin PB-exec-summary-t2-artifacts-stale-post-m4 closes_when tokens.

Hermetic contract so T10 cannot close the row against a silently rewritten
closes_when that drops Elder Care, SPG, word counts, volume bytes, or run_ids.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKLOG_PATH = REPO_ROOT / "eval" / "program" / "product_backlog.yaml"
ROW_ID = "PB-exec-summary-t2-artifacts-stale-post-m4"
REGISTRY_REF = "OI-runbook-program-milestones-t2-exec-summary-post-m4-rerender"
REQUIRED_CLOSES_WHEN_TOKENS = (
    "Elder Care",
    "SPG",
    "t2_baseline_run_log",
    "word counts",
    "volume",
    "run_ids",
)


def _row() -> dict:
    payload = yaml.safe_load(BACKLOG_PATH.read_text(encoding="utf-8"))
    items = payload.get("items") or []
    match = next((item for item in items if item.get("id") == ROW_ID), None)
    assert match is not None, f"{ROW_ID} missing from product_backlog.yaml"
    return match


def test_pb_exec_summary_t2_rerender_closes_when_tokens():
    row = _row()
    assert row.get("registry_ref") == REGISTRY_REF
    closes_when = row.get("closes_when") or ""
    missing = [tok for tok in REQUIRED_CLOSES_WHEN_TOKENS if tok not in closes_when]
    assert not missing, f"{ROW_ID} closes_when missing tokens: {missing}"
