"""Regression guard for committed exec_summary presentation packet source metadata."""
from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
ELDER_CARE_PRESENTATION = (
    REPO / "eval/content/spot-check/exec_summary_elder_care_presentation.yaml"
)
CORRECT_SOURCE = "uc13_ale.analysis.diligence_report.executive_summary"
WRONG_SOURCE = "uc13_ale.analysis.legal.executive_summary"


def _load_presentation() -> dict:
    return yaml.safe_load(ELDER_CARE_PRESENTATION.read_text(encoding="utf-8"))


def test_elder_care_exec_summary_presentation_source_is_diligence_report() -> None:
    payload = _load_presentation()
    assert payload["surface"] == "exec_summary"
    assert payload["source"] == CORRECT_SOURCE
    assert payload["claim_count"] == len(payload["claims"])

    for claim in payload["claims"]:
        source_ref = claim["source_ref"]
        assert WRONG_SOURCE not in source_ref, claim["claim_id"]
        assert source_ref.startswith(f"source://{CORRECT_SOURCE}#"), claim["claim_id"]
