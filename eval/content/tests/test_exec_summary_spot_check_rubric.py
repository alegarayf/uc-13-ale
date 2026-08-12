"""Hermetic guards for exec_summary spot-check rubric claim enumeration."""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
RUBRIC = REPO / "eval/content/exec_summary_spot_check_rubric.md"
MANIFEST = REPO / "eval/content/exec_summary_rubric_claims.json"
SAMPLE = REPO / ".dev/eval-program/calibration_sample_exec_summary.yaml"


def _parse_rubric_exec_rows() -> dict[str, tuple[str, str]]:
    text = RUBRIC.read_text(encoding="utf-8")
    section = "## 1. Claim enumeration — `exec_summary`"
    fta_section = "## 2. Claim enumeration — `fta_numeric`"
    block = text.split(section, 1)[1].split(fta_section, 1)[0]
    rows: dict[str, tuple[str, str]] = {}
    for match in re.finditer(
        r"\| ([^|]+) \| (exec\.claim\.\d+) \| ([^|]+) \|",
        block,
    ):
        rows[match.group(2).strip()] = (
            match.group(1).strip(),
            match.group(3).strip(),
        )
    return rows


def test_manifest_and_rubric_exec_claim_tables_match() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rubric_rows = _parse_rubric_exec_rows()
    assert manifest["claim_count"] == len(manifest["claims"])
    assert len(rubric_rows) == manifest["claim_count"]
    for claim in manifest["claims"]:
        cid = claim["claim_id"]
        assert cid in rubric_rows
        section, text = rubric_rows[cid]
        assert section == claim["section"]
        assert text == claim["claim_text"]


def test_calibration_sample_ids_001_028_match_rubric_verbatim() -> None:
    sample = yaml.safe_load(SAMPLE.read_text(encoding="utf-8"))
    rubric_rows = _parse_rubric_exec_rows()
    for row in sample["claims"]:
        cid = row["claim_id"]
        assert cid in rubric_rows, cid
        _, text = rubric_rows[cid]
        assert text == row["claim_text"], cid


def test_exec_claim_ids_are_dense_from_001() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    nums = [int(c["claim_id"].rsplit(".", 1)[-1]) for c in manifest["claims"]]
    assert nums == list(range(1, len(nums) + 1))


def test_calibration_probes_marked_in_manifest() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    by_id = {c["claim_id"]: c for c in manifest["claims"]}
    assert by_id["exec.claim.027"]["origin"] == "calibration_probe"
    assert by_id["exec.claim.028"]["origin"] == "calibration_probe"
