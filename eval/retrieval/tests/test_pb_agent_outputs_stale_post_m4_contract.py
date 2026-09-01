"""T8 — pin PB-agent-outputs-stale-post-m4-ingest closes_when tokens.

Hermetic contract so T10 cannot close the row against a silently rewritten
closes_when that drops the three companies, post-M4 run_ids, or the HTML /
deep-probe match clause.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKLOG_PATH = REPO_ROOT / "eval" / "program" / "product_backlog.yaml"
ROW_ID = "PB-agent-outputs-stale-post-m4-ingest"
REGISTRY_REF = "OI-agent-quality-post-m4-agent-rerun-three-companies"
REQUIRED_CLOSES_WHEN_TOKENS = (
    "Clearsulting",
    "Elder Care",
    "GKF",
    "seven-agent",
    "post-M4",
    "run_ids",
    "company-analysis",
    "HTML agent panels",
    "deep probe",
)


def _row() -> dict:
    payload = yaml.safe_load(BACKLOG_PATH.read_text(encoding="utf-8"))
    items = payload.get("items") or []
    match = next((item for item in items if item.get("id") == ROW_ID), None)
    assert match is not None, f"{ROW_ID} missing from product_backlog.yaml"
    return match


def test_pb_agent_outputs_stale_post_m4_closes_when_tokens():
    row = _row()
    assert row.get("registry_ref") == REGISTRY_REF
    closes_when = row.get("closes_when") or ""
    missing = [tok for tok in REQUIRED_CLOSES_WHEN_TOKENS if tok not in closes_when]
    assert not missing, f"{ROW_ID} closes_when missing tokens: {missing}"
