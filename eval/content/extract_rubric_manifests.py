"""One-shot: extract committed rubric tables into eval/content manifest JSON files."""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUBRIC = REPO / "eval/content/exec_summary_spot_check_rubric.md"
EXEC_META = REPO / "eval/content/fixtures/exec_summary_enumeration_source.meta.json"
EXEC_MANIFEST = REPO / "eval/content/exec_summary_rubric_claims.json"
FTA_MANIFEST = REPO / "eval/content/fta_numeric_rubric_claims.json"

CALIBRATION_PROBE_IDS = frozenset({"exec.claim.027", "exec.claim.028"})


def _exec_section(text: str) -> str:
    marker = "## 1. Claim enumeration — `exec_summary`"
    fta_marker = "## 2. Claim enumeration — `fta_numeric`"
    return text.split(marker, 1)[1].split(fta_marker, 1)[0]


def _fta_section(text: str) -> str:
    marker = "## 2. Claim enumeration — `fta_numeric`"
    return text.split(marker, 1)[1].split("\n---\n", 1)[0]


def extract_exec_claims(text: str) -> list[dict]:
    claims: list[dict] = []
    for match in re.finditer(
        r"\| ([^|]+) \| (exec\.claim\.\d+) \| ([^|]+) \|",
        _exec_section(text),
    ):
        cid = match.group(2).strip()
        num = int(cid.rsplit(".", 1)[-1])
        if cid in CALIBRATION_PROBE_IDS:
            origin = "calibration_probe"
        elif num <= 28:
            origin = "calibration_sample"
        else:
            origin = "source_extension"
        claims.append(
            {
                "section": match.group(1).strip(),
                "claim_id": cid,
                "claim_text": match.group(3).strip(),
                "origin": origin,
            }
        )
    return claims


def extract_fta_claims(text: str) -> list[dict]:
    claims: list[dict] = []
    for match in re.finditer(
        r"\| (fta\.claim\.\d+) \| ([^|]+) \| ([^|]+) \| ([^|]*) \|",
        _fta_section(text),
    ):
        loc = match.group(4).strip()
        claims.append(
            {
                "claim_id": match.group(1).strip(),
                "claim_text": match.group(2).strip(),
                "source_doc": match.group(3).strip(),
                "source_location": loc or None,
            }
        )
    return claims


def write_exec_manifest(text: str) -> Path:
    meta = json.loads(EXEC_META.read_text(encoding="utf-8"))
    claims = extract_exec_claims(text)
    if len(claims) != 53:
        raise SystemExit(f"expected 53 exec claims, got {len(claims)}")
    payload = {
        "schema_version": 1,
        "source_query": meta["source_query"],
        "created_at": meta["created_at"],
        "generator": "eval/content/extract_rubric_manifests.py",
        "calibration_sample": ".dev/eval-program/calibration_sample_exec_summary.yaml",
        "claim_count": len(claims),
        "claims": claims,
    }
    EXEC_MANIFEST.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return EXEC_MANIFEST


def main() -> None:
    text = RUBRIC.read_text(encoding="utf-8")
    claims = extract_fta_claims(text)
    if len(claims) != 276:
        raise SystemExit(f"expected 276 fta claims, got {len(claims)}")
    payload = {
        "schema_version": 1,
        "surface": "fta_numeric",
        "source_query": (
            "SELECT * FROM uc13_ale.analysis.financial_trends "
            "WHERE company_name = 'Elder Care' ORDER BY created_at DESC LIMIT 1"
        ),
        "probe_report": (
            ".dev/plans/eval-consolidation-m2-s2-preplan-assessments/t2_fta_probe_report.json"
        ),
        "claim_count": len(claims),
        "claims": claims,
    }
    out = FTA_MANIFEST
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(REPO)} ({len(claims)} claims)")


if __name__ == "__main__":
    main()
