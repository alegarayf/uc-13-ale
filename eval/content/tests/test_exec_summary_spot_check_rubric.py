"""Hermetic guards for exec_summary spot-check rubric claim enumeration."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
RUBRIC = REPO / "eval/content/exec_summary_spot_check_rubric.md"
EXEC_MANIFEST = REPO / "eval/content/exec_summary_rubric_claims.json"
FTA_MANIFEST = REPO / "eval/content/fta_numeric_rubric_claims.json"
SAMPLE = REPO / ".dev/eval-program/calibration_sample_exec_summary.yaml"
SOURCE_FIXTURE = REPO / "eval/content/fixtures/exec_summary_enumeration_source.md"
SOURCE_META = REPO / "eval/content/fixtures/exec_summary_enumeration_source.meta.json"


def _normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[\u2014\u2013\-–—]", "-", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


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


def _parse_rubric_fta_rows() -> dict[str, tuple[str, str, str]]:
    text = RUBRIC.read_text(encoding="utf-8")
    section = "## 2. Claim enumeration — `fta_numeric`"
    block = text.split(section, 1)[1].split("\n---\n", 1)[0]
    rows: dict[str, tuple[str, str, str]] = {}
    for match in re.finditer(
        r"\| (fta\.claim\.\d+) \| ([^|]+) \| ([^|]+) \| ([^|]*) \|",
        block,
    ):
        rows[match.group(1).strip()] = (
            match.group(2).strip(),
            match.group(3).strip(),
            match.group(4).strip(),
        )
    return rows


def test_manifest_and_rubric_exec_claim_tables_match() -> None:
    manifest = json.loads(EXEC_MANIFEST.read_text(encoding="utf-8"))
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
    if not SAMPLE.exists():
        pytest.skip(
            f"{SAMPLE} is operator-local (gitignored .dev/ per Option C) — "
            "calibration sample cross-check requires a populated working tree"
        )
    sample = yaml.safe_load(SAMPLE.read_text(encoding="utf-8"))
    rubric_rows = _parse_rubric_exec_rows()
    for row in sample["claims"]:
        cid = row["claim_id"]
        assert cid in rubric_rows, cid
        _, text = rubric_rows[cid]
        assert text == row["claim_text"], cid


def test_exec_claim_ids_are_dense_from_001() -> None:
    manifest = json.loads(EXEC_MANIFEST.read_text(encoding="utf-8"))
    nums = [int(c["claim_id"].rsplit(".", 1)[-1]) for c in manifest["claims"]]
    assert nums == list(range(1, len(nums) + 1))


def test_calibration_probes_marked_in_manifest() -> None:
    manifest = json.loads(EXEC_MANIFEST.read_text(encoding="utf-8"))
    by_id = {c["claim_id"]: c for c in manifest["claims"]}
    assert by_id["exec.claim.027"]["origin"] == "calibration_probe"
    assert by_id["exec.claim.028"]["origin"] == "calibration_probe"


def _claims_cover_phrases(claims: list[dict], phrases: list[str]) -> list[str]:
    blob = _normalize_text(" ".join(c["claim_text"] for c in claims))
    return [p for p in phrases if _normalize_text(p) not in blob]


def test_enumeration_covers_pinned_source_anchor_phrases() -> None:
    """HALT-15 falsifier: non-probe union must cover distinctive pinned source phrases."""
    manifest = json.loads(EXEC_MANIFEST.read_text(encoding="utf-8"))
    meta = json.loads(SOURCE_META.read_text(encoding="utf-8"))
    assert manifest["created_at"] == meta["created_at"]
    non_probe = [
        c for c in manifest["claims"] if c.get("origin") != "calibration_probe"
    ]
    anchors = [
        "private-pay home care company",
        "352 active clients",
        "2,123 registered caregivers",
        "Guided Living and Unicity",
        "Connecticut de novo",
        "Pro Forma Adjusted Revenue reached $46.4M",
        "17 discrete Tier 4 items",
        "approximately 247% of reported EBITDA",
        "NYSDOH survey citations in May 2023",
        "April 30, 2025 to pursue collection of patient receivables",
        "anti-assignment covenant",
        "five of seven workstreams carry a Red rating",
        "location-level P&L and operational KPIs",
        "4.2x increase",
        "termination-for-convenience provisions",
    ]
    missing = _claims_cover_phrases(non_probe, anchors)
    assert not missing, missing


def test_fta_manifest_and_rubric_tables_match() -> None:
    manifest = json.loads(FTA_MANIFEST.read_text(encoding="utf-8"))
    rubric_rows = _parse_rubric_fta_rows()
    assert manifest["claim_count"] == 276
    assert len(rubric_rows) == 276
    for claim in manifest["claims"]:
        cid = claim["claim_id"]
        assert cid in rubric_rows
        text, doc, loc = rubric_rows[cid]
        assert text == claim["claim_text"]
        assert doc == claim["source_doc"]
        assert loc == (claim.get("source_location") or "")


def test_fta_claim_ids_are_dense_from_001_to_276() -> None:
    manifest = json.loads(FTA_MANIFEST.read_text(encoding="utf-8"))
    nums = [int(c["claim_id"].rsplit(".", 1)[-1]) for c in manifest["claims"]]
    assert nums == list(range(1, 277))


def test_rubric_documents_rung3_write_path_contract() -> None:
    text = RUBRIC.read_text(encoding="utf-8")
    assert "## 3. Spot-check procedure" in text
    assert "## 4. Write-path contract" in text
    assert "human_spot_check" in text
    for verdict in ("supported", "contradicted", "unsupported"):
        assert verdict in text
