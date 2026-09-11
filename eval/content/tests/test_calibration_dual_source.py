"""Hermetic tests for exec_summary dual-source calibration evidence assembly."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from eval.content.calibration import (
    EXEC_JUDGE_CAL_F4_CLAIM_IDS,
    EXEC_VERDICT_SYSTEM_PROMPT,
    build_exec_dual_source_evidence,
    exec_claim_analysis_evidence,
    format_exec_dual_source_evidence,
    is_stub_verdict_json,
    judge_claim,
)
from eval.content.spot_check import _EXEC_TOP10_RANK_MAP


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


def test_exec_claim_043_051_bind_live_rank_9_not_rank_7() -> None:
    """Cycle 34: 043/051 rematch to live rank 9 (T4C/CoC); 052 stays on 9."""

    assert _EXEC_TOP10_RANK_MAP["exec.claim.043"] == 9
    assert _EXEC_TOP10_RANK_MAP["exec.claim.051"] == 9
    assert _EXEC_TOP10_RANK_MAP["exec.claim.052"] == 9
    assert _EXEC_TOP10_RANK_MAP["exec.claim.021"] == 3
    assert _EXEC_TOP10_RANK_MAP["exec.claim.039"] == 3
    assert _EXEC_TOP10_RANK_MAP["exec.claim.049"] == 3
    assert _EXEC_TOP10_RANK_MAP["exec.claim.045"] == 10
    assert _EXEC_TOP10_RANK_MAP["exec.claim.050"] == 6
    assert _EXEC_TOP10_RANK_MAP["exec.claim.053"] == 10

    cache = _f4_cache()
    cache["top_10_issues_json"] = [
        {
            "rank": 7,
            "issue": "Guided Living tax returns outstanding",
            "citations": ["tax.pdf"],
        },
        {
            "rank": 9,
            "issue": "T4C / change-of-control in customer contracts (Batistil)",
            "citations": ["legal.pdf"],
        },
    ]
    for claim_id in ("exec.claim.043", "exec.claim.051", "exec.claim.052"):
        record = exec_claim_analysis_evidence(
            claim_id, cache, company_slug="elder_care"
        )
        assert record is not None
        assert record["field"] == "top_10_issues_json"
        assert record["payload"]["rank"] == 9
        assert "change-of-control" in record["payload"]["issue"]
        assert record["payload"]["issue"] != "Guided Living tax returns outstanding"


def _live_shaped_tier4_ledger() -> list[dict[str, str]]:
    """2026-09-01 Elder Care QoE amount_dollars (CIM USD_k; gross ~$6.847M)."""

    amounts = (
        "(0)",
        "182",
        "53",
        "665",
        "(158)",
        "(33)",
        "2,490",
        "94",
        "189",
        "377",
        "1,077",
        "0",
        "0",
        "430",
        "909",
        "190",
        "-",
    )
    letters = "ABCDEFGHIJKLMNOPQ"
    return [
        {
            "description": f"[{letter}] item",
            "amount_dollars": amount,
            "tier_classification": "Tier 4",
        }
        for letter, amount in zip(letters, amounts, strict=True)
    ]


def test_exec_claim_011_bind_is_ledger_approx_sum() -> None:
    """011 XOR: judge treated 'approximately $7.3M' as exact vs live ~$6.8M gross."""

    cache = _sample_cache()
    cache["addback_ledger_json"] = _live_shaped_tier4_ledger()
    cache["tier4_addback_count"] = 17
    record = exec_claim_analysis_evidence(
        "exec.claim.011",
        cache,
        company_slug="elder_care",
    )
    assert record is not None
    assert record["field"] == "addback_ledger_json"
    payload = record["payload"]
    assert payload["tier4_addback_count"] == 17
    assert payload["ledger_item_count"] == 17
    assert payload["ledger_signed_sum_usd"] == 6_465_000
    assert payload["ledger_gross_sum_usd"] == 6_847_000
    assert payload["ledger_gross_sum_usd_m"] == "6.847"
    assert payload["claim_approx_usd_m"] == "7.3"
    assert payload["approx_band_usd_m"] == "6.5-8.0"
    assert payload["approx_7_3m_ok"] is True
    assert payload["addback_ledger_json"] == cache["addback_ledger_json"]


def test_exec_claim_011_approx_ok_false_outside_named_band() -> None:
    cache = _sample_cache()
    cache["addback_ledger_json"] = [
        {
            "description": "[G] Run-rate executive compensation",
            "amount_dollars": "20,000",
            "tier_classification": "Tier 4",
        }
    ]
    cache["tier4_addback_count"] = 1
    record = exec_claim_analysis_evidence(
        "exec.claim.011",
        cache,
        company_slug="elder_care",
    )
    assert record is not None
    payload = record["payload"]
    assert payload["ledger_gross_sum_usd"] == 20_000_000
    assert payload["approx_7_3m_ok"] is False


def test_exec_claim_013_028_031_payload_has_no_011_census() -> None:
    cache = _sample_cache()
    cache["addback_ledger_json"] = _live_shaped_tier4_ledger()
    for claim_id in ("exec.claim.013", "exec.claim.028", "exec.claim.031"):
        record = exec_claim_analysis_evidence(
            claim_id, cache, company_slug="elder_care"
        )
        assert record is not None
        payload = record["payload"]
        if claim_id == "exec.claim.013":
            assert payload == cache["addback_ledger_json"]
            continue
        assert "approx_7_3m_ok" not in payload
        assert "ledger_gross_sum_usd" not in payload
        assert "census_17_five_ok" not in payload
        assert "items_over_5pct_count" not in payload


def _live_ttm_reported_ebitda() -> list[dict[str, str]]:
    """2026-09-01 Elder Care FTA TTM reported (CIM USD_k; $2.773M)."""

    return [
        {
            "period": "TTM Aug-24",
            "label": "Reported EBITDA",
            "version": "reported",
            "ebitda_dollars": "2,773",
        },
        {
            "period": "TTM Aug-24",
            "label": "Pro Forma Adjusted EBITDA",
            "version": "pf_adjusted",
            "ebitda_dollars": "9,239",
        },
    ]


def _048_live_cache() -> dict[str, object]:
    cache = _sample_cache()
    cache["addback_ledger_json"] = _live_shaped_tier4_ledger()
    cache["tier4_addback_count"] = 17
    cache["ebitda_json"] = _live_ttm_reported_ebitda()
    cache["top_10_issues_json"] = [
        {
            "rank": 1,
            "issue": "Total addbacks represent 246.9% of reported EBITDA",
            "citations": ["CIM.pdf"],
        },
        {
            "rank": 3,
            "issue": "NYSDOH citations unresolved",
            "citations": ["CIM.pdf"],
        },
    ]
    return cache


def test_exec_claim_048_bind_is_open_item_census_not_bare_rank() -> None:
    """048 XOR: rank-1 payload alone hid the 17 / five-over-5% census."""

    assert _EXEC_TOP10_RANK_MAP["exec.claim.048"] == 1
    cache = _048_live_cache()
    record = exec_claim_analysis_evidence(
        "exec.claim.048",
        cache,
        company_slug="elder_care",
    )
    assert record is not None
    assert record["field"] == "top_10_issues_json"
    payload = record["payload"]
    assert int(payload["rank_1_issue"]["rank"]) == 1
    assert "246.9%" in payload["rank_1_issue"]["issue"]
    assert payload["tier4_addback_count"] == 17
    assert payload["ledger_item_count"] == 17
    assert payload["ebitda_base_usd"] == 2_773_000
    assert payload["ebitda_base_period"] == "TTM Aug-24"
    assert payload["items_over_5pct_count"] == 10
    assert payload["claim_tier4_count"] == 17
    assert payload["claim_over_5pct_count"] == 5
    assert payload["census_17_ok"] is True
    assert payload["five_items_over_5pct_ok"] is True
    assert payload["census_17_five_ok"] is True
    assert "approx_7_3m_ok" not in payload
    assert "ledger_gross_sum_usd" not in payload
    assert "red_or_yellow_count" not in payload
    assert payload["items_over_5pct_of_ebitda"][0]["description"].startswith("[G]")


def test_exec_claim_048_census_false_when_fewer_than_five_over_5pct() -> None:
    cache = _048_live_cache()
    cache["addback_ledger_json"] = [
        {
            "description": "[G] Run-rate executive compensation",
            "amount_dollars": "2,490",
            "tier_classification": "Tier 4",
        },
        {
            "description": "[K] Unicity pre-acquisition results",
            "amount_dollars": "1,077",
            "tier_classification": "Tier 4",
        },
        {
            "description": "[C] Non-operating transactions",
            "amount_dollars": "53",
            "tier_classification": "Tier 4",
        },
    ]
    cache["tier4_addback_count"] = 3
    record = exec_claim_analysis_evidence(
        "exec.claim.048",
        cache,
        company_slug="elder_care",
    )
    assert record is not None
    payload = record["payload"]
    assert payload["items_over_5pct_count"] == 2
    assert payload["census_17_ok"] is False
    assert payload["five_items_over_5pct_ok"] is False
    assert payload["census_17_five_ok"] is False


def test_exec_claim_011_026_034_payload_has_no_048_census() -> None:
    cache = _048_live_cache()
    cache["section_ratings_json"] = _elder_care_seven_ratings()
    for claim_id in (
        "exec.claim.011",
        "exec.claim.013",
        "exec.claim.026",
        "exec.claim.031",
        "exec.claim.034",
    ):
        record = exec_claim_analysis_evidence(
            claim_id, cache, company_slug="elder_care"
        )
        assert record is not None
        payload = record["payload"]
        if isinstance(payload, list):
            continue
        assert "census_17_five_ok" not in payload
        assert "items_over_5pct_count" not in payload
        assert "rank_1_issue" not in payload


def test_exec_verdict_prompt_has_no_sample_wide_exact_count() -> None:
    """D31: do not re-add sample-wide exact-count / approximately language."""

    lowered = EXEC_VERDICT_SYSTEM_PROMPT.lower()
    assert "material exact figure" not in lowered
    assert "approximately" not in lowered
    assert "exact-count" not in lowered
    assert "exact count" not in lowered
