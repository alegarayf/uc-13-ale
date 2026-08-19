"""Hermetic tests for exec_summary dual-source calibration evidence assembly."""

from __future__ import annotations

from unittest.mock import MagicMock

from eval.content.calibration import (
    build_exec_dual_source_evidence,
    exec_claim_analysis_evidence,
)


def _sample_cache() -> dict[str, object]:
    return {
        "revenue_trend_json": [
            {
                "source_location": "Historical P&L Summary, Page 49",
                "source_doc": "2024 Elder Care - CIM_vF.pdf",
                "metric": "Pro Forma Adjusted Revenue",
                "value": "46423",
            }
        ],
        "section_ratings_json": {"forecast": "Red", "kpi": "Red"},
        "section_confidence_json": {"overall": "Medium"},
        "top_10_issues_json": [
            {"rank": 3, "issue": "NYSDOH citations unresolved", "citations": ["CIM.pdf"]}
        ],
        "addback_ledger_json": [
            {
                "description": "[G] Run-rate executive compensation",
                "amount": "2490000",
                "source_doc": "2024 Elder Care - CIM_vF.pdf",
            }
        ],
        "healthcare_kpis_json": {"active_clients_q2_2025": 352},
    }


def test_exec_claim_analysis_evidence_returns_analysis_table_record() -> None:
    record = exec_claim_analysis_evidence(
        "exec.claim.019",
        _sample_cache(),
        company_slug="elder_care",
    )
    assert record is not None
    assert record["source_type"] == "analysis_table"
    assert record["analysis_table"] == "diligence_report"
    assert record["field"] == "section_ratings_json"
    assert record["payload"] == {"forecast": "Red", "kpi": "Red"}


def test_exec_claim_analysis_evidence_top10_rank_slice() -> None:
    record = exec_claim_analysis_evidence(
        "exec.claim.021",
        _sample_cache(),
        company_slug="elder_care",
    )
    assert record is not None
    assert record["field"] == "top_10_issues_json"
    assert record["payload"]["rank"] == 3


def test_build_exec_dual_source_evidence_prepends_analysis_before_chunks(
    monkeypatch,
) -> None:
    chunk_evidence = [{"chunk_id": "abc", "excerpt": "chunk text"}]

    def _fake_retrieve(*_args, **_kwargs):
        return chunk_evidence

    monkeypatch.setattr(
        "eval.content.calibration.retrieve_evidence",
        _fake_retrieve,
    )

    merged = build_exec_dual_source_evidence(
        MagicMock(),
        claim_id="exec.claim.014",
        claim_text="Run-rate executive compensation addback is $2,490K.",
        cache=_sample_cache(),
        company_slug="elder_care",
        catalog="uc13_ale",
        company="Elder Care",
    )

    assert len(merged) == 2
    assert merged[0]["source_type"] == "analysis_table"
    assert merged[1] == chunk_evidence[0]


def test_build_exec_dual_source_evidence_chunk_only_when_no_analysis_slice(
    monkeypatch,
) -> None:
    chunk_evidence = [{"chunk_id": "xyz", "excerpt": "only chunk"}]
    monkeypatch.setattr(
        "eval.content.calibration.retrieve_evidence",
        lambda *_a, **_k: chunk_evidence,
    )

    merged = build_exec_dual_source_evidence(
        MagicMock(),
        claim_id="exec.claim.001",
        claim_text="Elder Care Homecare is a private-pay home care company.",
        cache={},
        company_slug="elder_care",
        catalog="uc13_ale",
        company="Elder Care",
    )

    assert merged == chunk_evidence
