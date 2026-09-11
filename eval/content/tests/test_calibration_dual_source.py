"""Hermetic tests for exec_summary dual-source calibration evidence assembly."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from eval.content.calibration import (
    EXEC_JUDGE_CAL_F4_CLAIM_IDS,
    build_exec_dual_source_evidence,
    exec_claim_analysis_evidence,
    format_exec_dual_source_evidence,
    is_stub_verdict_json,
    judge_claim,
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
        "customer_operational_metrics_json": {
            "by_location": [
                {"location": "NYC"},
                {"location": "Long Island"},
                {"location": "Westchester"},
                {"location": "NJ"},
                {"location": "MA"},
                {"location": "CT"},
            ]
        },
        "ebitda_json": [{"period": "TTM Aug-24", "ebitda_dollars": "7730"}],
        "ebitda_scenarios_json": {"reported_ebitda": "7730"},
        "tier4_addback_count": 17,
    }


def _f4_cache() -> dict[str, object]:
    """Cache populated for every cycle-1 F4 judge_cal claim_id."""

    cache = _sample_cache()
    ledger = list(cache["addback_ledger_json"])  # type: ignore[arg-type]
    ledger.append(
        {
            "description": "[D] Cash-to-accrual revenue adjustment",
            "amount": "665000",
            "source_doc": "2024 Elder Care - CIM_vF.pdf",
        }
    )
    cache["addback_ledger_json"] = ledger
    cache["top_10_issues_json"] = [
        {"rank": rank, "issue": f"issue {rank}", "citations": ["CIM.pdf"]}
        for rank in range(1, 11)
    ]
    return cache


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


def test_is_stub_verdict_json_detects_verdict_only_payloads() -> None:
    assert is_stub_verdict_json('{"verdict": "unsupported"}')
    assert is_stub_verdict_json('{"verdict": "contradicted"}')
    assert is_stub_verdict_json('{"verdict": "unsupported", "rationale": "   "}')
    assert not is_stub_verdict_json(
        '{"verdict": "unsupported", "rationale": "analysis_table rank 3 supports the open item."}'
    )
    assert not is_stub_verdict_json("not json")


def test_format_exec_dual_source_does_not_drop_analysis_table() -> None:
    """Falsifier: unused dual-source — analysis_table must stay in the judge payload."""

    evidence = [
        {"source_type": "analysis_table", "payload": {"forecast": "Red"}},
        {"chunk_id": "c1", "chunk_text": "vdr only"},
    ]
    parsed = json.loads(format_exec_dual_source_evidence(evidence))
    assert parsed["analysis_table_evidence"]
    assert parsed["analysis_table_evidence"][0]["payload"]["forecast"] == "Red"
    assert parsed["vdr_chunks"][0]["chunk_id"] == "c1"


def test_f4_claim_class_gets_analysis_table_when_cache_populated(monkeypatch) -> None:
    """Every F4 claim_id must carry analysis-table evidence; chunks stay secondary."""

    chunk_evidence = [{"chunk_id": "vdr-1", "chunk_text": "nearby vdr"}]
    monkeypatch.setattr(
        "eval.content.calibration.retrieve_evidence",
        lambda *_a, **_k: chunk_evidence,
    )
    cache = _f4_cache()
    missing: list[str] = []
    for claim_id in sorted(EXEC_JUDGE_CAL_F4_CLAIM_IDS):
        merged = build_exec_dual_source_evidence(
            MagicMock(),
            claim_id=claim_id,
            claim_text=f"text for {claim_id}",
            cache=cache,
            company_slug="elder_care",
            catalog="uc13_ale",
            company="Elder Care",
        )
        if not merged or merged[0].get("source_type") != "analysis_table":
            missing.append(claim_id)
    assert missing == []


def test_judge_claim_retries_stub_json_for_rationale(monkeypatch) -> None:
    """Falsifier: stub-only JSON must trigger a repair call that supplies rationale."""

    calls: list[str] = []

    def _fake_llm(*, endpoint: str, system_prompt: str, user_prompt: str, retries: int = 3):
        calls.append(user_prompt)
        if len(calls) == 1:
            return '{"verdict": "unsupported"}'
        return (
            '{"verdict": "supported", '
            '"rationale": "analysis_table_evidence confirms the six locations."}'
        )

    monkeypatch.setattr("eval.content.calibration.call_llm_with_retry", _fake_llm)

    output = judge_claim(
        surface="exec_summary",
        claim={"claim_text": "Elder Care operates across six locations."},
        evidence=[
            {
                "source_type": "analysis_table",
                "payload": {"by_location": [{"location": "NYC"}]},
            }
        ],
        endpoint="databricks-claude-sonnet-4-6",
        chunk_meta_by_id={},
    )

    assert len(calls) == 2
    assert "verdict-only JSON is invalid" in calls[1]
    assert "analysis_table_evidence" in calls[0]
    assert output["verdict"] == "supported"
    assert output["rationale"]
    assert not is_stub_verdict_json(output["raw_response"])


def _elder_care_seven_ratings() -> dict[str, str]:
    return {
        "business_model": "Yellow",
        "financial_trends": "Red",
        "customer_quality": "Yellow",
        "kpi": "Red",
        "legal_contracts": "Red",
        "quality_of_earnings": "Red",
        "forecast": "Red",
    }


def test_exec_claim_025_bind_stays_section_confidence() -> None:
    cache = _sample_cache()
    cache["section_confidence_json"] = {
        "business_model": "Medium",
        "financial_trends": "Medium",
        "customer_quality": "Medium",
        "kpi": "Medium",
        "legal_contracts": "Medium",
        "quality_of_earnings": "Medium",
        "forecast": "Medium",
    }
    record = exec_claim_analysis_evidence(
        "exec.claim.025",
        cache,
        company_slug="elder_care",
    )
    assert record is not None
    assert record["field"] == "section_confidence_json"
    assert record["payload"] == cache["section_confidence_json"]
    assert "red_or_yellow_count" not in (record["payload"] or {})


def test_exec_claim_026_bind_is_ratings_census_not_confidence() -> None:
    """026 XOR: judge treated 'five of seven' as a minimum of a 7/7 Red/Yellow table."""

    cache = _sample_cache()
    cache["section_ratings_json"] = _elder_care_seven_ratings()
    cache["section_confidence_json"] = {"overall": "Medium"}
    record = exec_claim_analysis_evidence(
        "exec.claim.026",
        cache,
        company_slug="elder_care",
    )
    assert record is not None
    assert record["field"] == "section_ratings_json"
    payload = record["payload"]
    assert payload["section_ratings_json"] == cache["section_ratings_json"]
    assert payload["total_workstreams"] == 7
    assert payload["red_count"] == 5
    assert payload["yellow_count"] == 2
    assert payload["green_count"] == 0
    assert payload["red_or_yellow_count"] == 7
    assert "section_confidence_json" not in payload
