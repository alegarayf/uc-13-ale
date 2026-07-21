"""Deterministic QoE downstream addback math owned by this fixture (Program Gate G2).

Rules covered:
  - ``_apply_qofe_flags``: Tier-4 ledger items → Red per item; individual addback
    >5% of reported EBITDA without VDR support → Red; total addbacks >20% of
    reported EBITDA → Yellow; total addbacks ≤20% → no flag (``_log_no_flag``);
    missing reported EBITDA base → data-room gap; revenue-quality flags pass
    through at stated severity; ``qofe_report_present == "false"`` → gap.
  - ``_compute_addback_summary``: ``(total_addbacks_pct_of_ebitda, tier4_count)``
    from a known addback ledger; ``base == 0`` or missing → ``total_pct is None``.
  - ``_compute_ebitda_scenarios``: reported / Tier-1+2 / Tier-1-only EBITDA
    scenarios from a known ledger; missing base → degenerate all-``None`` case.

Decision-D exclusion (M2 checklist-fidelity, not unit-tested here):
  ``_load_addback_passthrough`` and Tier-4 *assignment* (LLM classification of
  addbacks as Tier 4) are out of scope — this file asserts only Tier-4's
  downstream Red-flag consequence when ``tier_classification`` is already Tier 4.
"""

from __future__ import annotations

import pytest

from agents.workstreams.quality_of_earnings_agent import QualityOfEarningsAgent


def _build_extracted(
    *,
    base_amount: str | None = "1,000,000",
    ledger: list[dict] | None = None,
    revenue_quality_flags: list[dict] | None = None,
    qofe_report_present: str | None = None,
) -> dict:
    """Shared extracted-dict builder for summary and scenario tests."""
    extracted: dict = {
        "addback_ledger": ledger if ledger is not None else [],
        "reported_ebitda_base": {},
    }
    if base_amount is not None:
        extracted["reported_ebitda_base"] = {
            "amount_dollars": base_amount,
            "source_doc": "ebitda_bridge.pdf",
        }
    if revenue_quality_flags is not None:
        extracted["revenue_quality_flags"] = revenue_quality_flags
    if qofe_report_present is not None:
        extracted["qofe_report_present"] = qofe_report_present
    return extracted


def _standard_ledger() -> list[dict]:
    return [
        {
            "description": "Owner comp normalization",
            "amount_dollars": "50,000",
            "tier_classification": "Tier 1",
            "supporting_doc_in_vdr": "true",
            "source_doc": "qoe_report.pdf",
        },
        {
            "description": "One-time legal fees",
            "amount_dollars": "30,000",
            "tier_classification": "Tier 2",
            "supporting_doc_in_vdr": "true",
            "source_doc": "qoe_report.pdf",
        },
        {
            "description": "Unsupported personal expenses",
            "amount_dollars": "20,000",
            "tier_classification": "Tier 4",
            "supporting_doc_in_vdr": "false",
            "source_doc": "mgmt_schedule.xlsx",
        },
    ]


def test_quality_of_earnings_agent_constructs_without_io():
    agent = QualityOfEarningsAgent()
    assert agent.agent_name == "quality_of_earnings"


def test_compute_ebitda_scenarios_three_paths():
    extracted = _build_extracted(base_amount="1,000,000", ledger=_standard_ledger())
    agent = QualityOfEarningsAgent()

    scenarios = agent._compute_ebitda_scenarios(extracted)

    assert scenarios["reported_ebitda"] == 1_000_000.0
    assert scenarios["tier1_addback_total"] == 50_000.0
    assert scenarios["tier2_addback_total"] == 30_000.0
    assert scenarios["tier1_only_ebitda"] == 1_050_000.0
    assert scenarios["tier1_plus_tier2_ebitda"] == 1_080_000.0
    assert "Three scenarios per spec" in scenarios["note"]


def test_compute_ebitda_scenarios_missing_base_degenerate():
    extracted = _build_extracted(base_amount=None, ledger=_standard_ledger())
    agent = QualityOfEarningsAgent()

    scenarios = agent._compute_ebitda_scenarios(extracted)

    assert scenarios["reported_ebitda"] is None
    assert scenarios["tier1_plus_tier2_ebitda"] is None
    assert scenarios["tier1_only_ebitda"] is None
    assert scenarios["tier1_addback_total"] == 50_000.0
    assert scenarios["tier2_addback_total"] == 30_000.0


def test_compute_addback_summary_known_ledger():
    extracted = _build_extracted(base_amount="1,000,000", ledger=_standard_ledger())
    agent = QualityOfEarningsAgent()

    total_pct, tier4_count = agent._compute_addback_summary(extracted)

    assert total_pct == 10.0
    assert tier4_count == 1


@pytest.mark.parametrize("base_amount", ["0", None])
def test_compute_addback_summary_zero_or_missing_base_returns_none_pct(base_amount):
    extracted = _build_extracted(base_amount=base_amount, ledger=_standard_ledger())
    agent = QualityOfEarningsAgent()

    total_pct, tier4_count = agent._compute_addback_summary(extracted)

    assert total_pct is None
    assert tier4_count == 1


def test_apply_qofe_flags_tier4_addback_red_per_item():
    extracted = _build_extracted(
        base_amount="1,000,000",
        ledger=[
            {
                "description": "Unsupported personal expenses",
                "amount_dollars": "20,000",
                "tier_classification": "Tier 4",
                "source_doc": "mgmt_schedule.xlsx",
            },
            {
                "description": "Another Tier 4 item",
                "amount_dollars": "15,000",
                "tier_classification": "Tier 4",
                "source_doc": "mgmt_schedule.xlsx",
            },
        ],
    )
    agent = QualityOfEarningsAgent()

    agent._apply_qofe_flags(extracted, total_pct=3.5, tier4_count=2)

    tier4_flags = [f for f in agent._flags_as_dicts() if f["metric"] == "tier4_addback"]
    assert len(tier4_flags) == 2
    assert all(f["severity"] == "Red" for f in tier4_flags)


def test_apply_qofe_flags_large_unsupported_addback_red():
    extracted = _build_extracted(
        base_amount="1,000,000",
        ledger=[
            {
                "description": "Large unsupported normalization",
                "amount_dollars": "60,000",
                "tier_classification": "Tier 2",
                "supporting_doc_in_vdr": "false",
                "source_doc": "mgmt_schedule.xlsx",
            },
        ],
    )
    agent = QualityOfEarningsAgent()

    agent._apply_qofe_flags(extracted, total_pct=6.0, tier4_count=0)

    unsupported = [
        f for f in agent._flags_as_dicts() if f["metric"] == "large_unsupported_addback"
    ]
    assert len(unsupported) == 1
    assert unsupported[0]["severity"] == "Red"
    assert "6.0%" in unsupported[0]["value"]


def test_apply_qofe_flags_exactly_five_percent_unsupported_addback_no_flag():
    """Falsifier: >5% threshold is strict — exactly 5.0% must not trigger Red."""
    extracted = _build_extracted(
        base_amount="1,000,000",
        ledger=[
            {
                "description": "Borderline unsupported normalization",
                "amount_dollars": "50,000",
                "tier_classification": "Tier 2",
                "supporting_doc_in_vdr": "false",
                "source_doc": "mgmt_schedule.xlsx",
            },
        ],
    )
    agent = QualityOfEarningsAgent()

    agent._apply_qofe_flags(extracted, total_pct=5.0, tier4_count=0)

    unsupported = [
        f for f in agent._flags_as_dicts() if f["metric"] == "large_unsupported_addback"
    ]
    assert unsupported == []


def test_apply_qofe_flags_supported_large_addback_no_unsupported_flag():
    extracted = _build_extracted(
        base_amount="1,000,000",
        ledger=[
            {
                "description": "Large but supported normalization",
                "amount_dollars": "60,000",
                "tier_classification": "Tier 2",
                "supporting_doc_in_vdr": "true",
                "source_doc": "qoe_report.pdf",
            },
        ],
    )
    agent = QualityOfEarningsAgent()

    agent._apply_qofe_flags(extracted, total_pct=6.0, tier4_count=0)

    unsupported = [
        f for f in agent._flags_as_dicts() if f["metric"] == "large_unsupported_addback"
    ]
    assert unsupported == []


def test_apply_qofe_flags_total_addbacks_over_20_percent_yellow():
    extracted = _build_extracted(base_amount="1,000,000", ledger=[])
    agent = QualityOfEarningsAgent()

    agent._apply_qofe_flags(extracted, total_pct=25.0, tier4_count=0)

    yellow = [
        f for f in agent._flags_as_dicts() if f["metric"] == "total_addbacks_pct_of_ebitda"
    ]
    assert len(yellow) == 1
    assert yellow[0]["severity"] == "Yellow"
    assert yellow[0]["value"] == "25.0%"


def test_apply_qofe_flags_total_addbacks_at_or_below_20_percent_logs_no_flag():
    extracted = _build_extracted(base_amount="1,000,000", ledger=[])
    agent = QualityOfEarningsAgent()

    agent._apply_qofe_flags(extracted, total_pct=15.0, tier4_count=0)

    total_flags = [
        f for f in agent._flags_as_dicts() if f["metric"] == "total_addbacks_pct_of_ebitda"
    ]
    assert total_flags == []
    no_flag_steps = [
        t for t in agent._trace
        if t.get("tool") == "threshold_evaluation"
        and "total_addbacks_pct_of_ebitda" in t.get("input", "")
    ]
    assert len(no_flag_steps) == 1


def test_apply_qofe_flags_missing_ebitda_base_gap():
    extracted = _build_extracted(base_amount="1,000,000", ledger=[])
    agent = QualityOfEarningsAgent()

    agent._apply_qofe_flags(extracted, total_pct=None, tier4_count=0)

    assert any(
        "Cannot compute total addbacks % of EBITDA" in gap
        for gap in agent._data_room_gaps
    )


def test_apply_qofe_flags_revenue_quality_flags_pass_through():
    extracted = _build_extracted(
        base_amount="1,000,000",
        ledger=[],
        revenue_quality_flags=[
            {
                "severity": "Red",
                "evidence": "Deferred revenue spike at period end",
                "flag_type": "deferred_revenue",
                "source_doc": "audit_notes.pdf",
            },
            {
                "severity": "Yellow",
                "evidence": "Bill-and-hold arrangement disclosed",
                "flag_type": "bill_and_hold",
                "source_doc": "footnotes.pdf",
            },
        ],
    )
    agent = QualityOfEarningsAgent()

    agent._apply_qofe_flags(extracted, total_pct=5.0, tier4_count=0)

    rq_flags = [
        f for f in agent._flags_as_dicts() if f["metric"].startswith("revenue_quality_")
    ]
    assert len(rq_flags) == 2
    severities = {f["metric"]: f["severity"] for f in rq_flags}
    assert severities["revenue_quality_deferred_revenue"] == "Red"
    assert severities["revenue_quality_bill_and_hold"] == "Yellow"


def test_apply_qofe_flags_qofe_report_absent_gap():
    extracted = _build_extracted(
        base_amount="1,000,000",
        ledger=[],
        qofe_report_present="false",
    )
    agent = QualityOfEarningsAgent()

    agent._apply_qofe_flags(extracted, total_pct=5.0, tier4_count=0)

    assert any("No QofE report found in VDR" in gap for gap in agent._data_room_gaps)


def test_summary_and_scenarios_share_consistent_extracted_fixture():
    """Mitigation: one helper supplies the same extracted dict to both methods."""
    extracted = _build_extracted(base_amount="2,000,000", ledger=_standard_ledger())
    agent = QualityOfEarningsAgent()

    total_pct, tier4_count = agent._compute_addback_summary(extracted)
    scenarios = agent._compute_ebitda_scenarios(extracted)

    assert total_pct == 5.0
    assert tier4_count == 1
    assert scenarios["reported_ebitda"] == 2_000_000.0
    assert scenarios["tier1_plus_tier2_ebitda"] == 2_080_000.0
