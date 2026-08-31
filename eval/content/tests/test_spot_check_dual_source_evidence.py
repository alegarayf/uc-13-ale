"""Tests for exec_summary dual-source evidence wiring in spot_check.py (T8 / item 10).

Ports the ``calibration.py`` analysis-table + chunk-RAG dual-source pattern into the
production ``spot_check.py`` claim enumeration and prepare-packet path, scoped to
``exec_summary`` only.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from eval.content.spot_check import (
    SpotCheckConfig,
    _claim_from_manifest_entry,
    load_claim_enumeration,
    prepare_spot_check,
)
from eval.retrieval.companies import canonical_company_slug


def _registry_yaml() -> str:
    return yaml.safe_dump(
        {
            "schema_version": 1,
            "items": [
                {
                    "id": "CHK-26a",
                    "rung_assignments": {"exec_summary": "human"},
                }
            ],
        }
    )


def _exec_manifest() -> str:
    return """{
  "schema_version": 1,
  "claim_count": 2,
  "claims": [
    {
      "section": "Financial Picture",
      "claim_id": "exec.claim.008",
      "claim_text": "TTM Aug-24 revenue is $46,423K."
    },
    {
      "section": "Business Overview",
      "claim_id": "exec.claim.001",
      "claim_text": "Elder Care Homecare is a private-pay home care company."
    }
  ]
}"""


def _cache_with_revenue_row() -> dict[str, object]:
    return {
        "revenue_trend_json": [
            {
                "source_location": "Historical P&L Summary, Page 49",
                "source_doc": "2024 Elder Care - CIM_vF.pdf",
                "metric": "Pro Forma Adjusted Revenue",
                "value": "46423",
            }
        ],
        "ebitda_json": [],
        "addback_pct_of_ebitda": None,
    }


def _spot_check_tree(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "eval/content").mkdir(parents=True)
    (root / "eval/program").mkdir(parents=True)
    (root / "eval/program/registry.yaml").write_text(_registry_yaml(), encoding="utf-8")
    (root / "eval/content/exec_summary_rubric_claims.json").write_text(
        _exec_manifest(), encoding="utf-8"
    )
    return root


def _config(root: Path, *, surface: str = "exec_summary") -> SpotCheckConfig:
    out = root / ".dev/eval-program/spot-check"
    slug = canonical_company_slug("Elder Care")
    return SpotCheckConfig(
        company="Elder Care",
        surface=surface,
        source="uc13_ale.analysis.diligence_report.executive_summary",
        output_dir=out,
        verdicts_path=out / f"{surface}_{slug}.verdicts.yaml",
        operator_id="operator_a",
        registry_path=root / "eval/program/registry.yaml",
        repo_root=root,
    )


def test_load_claim_enumeration_attaches_analysis_evidence_for_matched_claim(
    tmp_path: Path,
) -> None:
    """exec_summary claim mapped by exec_claim_analysis_evidence gets the analysis record."""
    root = _spot_check_tree(tmp_path)
    cfg = _config(root)
    claims = load_claim_enumeration(cfg, exec_analysis_cache=_cache_with_revenue_row())

    matched = next(c for c in claims if c.claim_id == "exec.claim.008")
    assert matched.analysis_evidence is not None
    assert matched.analysis_evidence["source_type"] == "analysis_table"
    assert matched.analysis_evidence["analysis_table"] == "financial_trends"
    assert matched.analysis_evidence["field"] == "revenue_trend_json"


def test_load_claim_enumeration_analysis_evidence_none_without_cache(
    tmp_path: Path,
) -> None:
    """No exec_analysis_cache supplied ⇒ analysis_evidence stays None (no crash, no fetch)."""
    root = _spot_check_tree(tmp_path)
    cfg = _config(root)
    claims = load_claim_enumeration(cfg)

    assert all(c.analysis_evidence is None for c in claims)


def test_load_claim_enumeration_analysis_evidence_none_for_non_exec_surface(
    tmp_path: Path,
) -> None:
    """Guard is exec_summary-scoped: an unmatched claim_id under cache yields None, not a crash."""
    root = _spot_check_tree(tmp_path)
    cfg = _config(root)
    claims = load_claim_enumeration(cfg, exec_analysis_cache=_cache_with_revenue_row())

    unmatched = next(c for c in claims if c.claim_id == "exec.claim.001")
    assert unmatched.analysis_evidence is None


def test_analysis_evidence_guard_is_exec_summary_scoped() -> None:
    """A claim_id that WOULD match exec_claim_analysis_evidence must stay None off exec_summary.

    Uses ``exec.claim.008`` (a real match key in exec_claim_analysis_evidence's
    financial_trends branch) under ``surface="fta_numeric"`` so a dropped/inverted
    surface guard is observable even though claim_id vocab otherwise overlaps.
    """
    entry = {"claim_id": "exec.claim.008", "claim_text": "TTM Aug-24 revenue is $46,423K."}
    claim = _claim_from_manifest_entry(
        "fta_numeric",
        "uc13_ale.analysis.financial_trends",
        entry,
        company_slug="elder_care",
        exec_analysis_cache=_cache_with_revenue_row(),
    )
    assert claim.analysis_evidence is None


def test_prepare_spot_check_packet_round_trips_analysis_evidence(
    tmp_path: Path,
) -> None:
    """Round trip: exec_analysis_cache-derived field is present in the written YAML packet."""
    root = _spot_check_tree(tmp_path)
    cfg = _config(root)

    result = prepare_spot_check(cfg, exec_analysis_cache=_cache_with_revenue_row())
    payload = yaml.safe_load(result.packet_path.read_text(encoding="utf-8"))
    by_id = {row["claim_id"]: row for row in payload["claims"]}

    matched = by_id["exec.claim.008"]
    assert matched["analysis_evidence"]["source_type"] == "analysis_table"
    assert matched["analysis_evidence"]["field"] == "revenue_trend_json"

    unmatched = by_id["exec.claim.001"]
    assert unmatched["analysis_evidence"] is None
