"""Hermetic tests for C6 trust-statement generator v0 — spec §17 item 10 / T9."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from eval.content.s2_writer import S2ScoreRow
from eval.retrieval.trust_statement import (
    ATTESTATION_WAIVED,
    CompanyDomainRow,
    IngestProbeResult,
    LAYER_CONTENT_CORRECTNESS,
    TrustEpochContext,
    TrustStatementGenerationError,
    TrustStatementRow,
    _GOLD_READY_SUMMARY,
    _rows_per_company,
    assert_row_set_total,
    derive_content_rows,
    derive_rows,
    derive_rows_for_company,
    load_epoch_context_from_baseline_report,
    registry_gap_titles_for_company,
    render_trust_statement_markdown,
    run_ingest_probe,
    validate_row,
    validate_rows,
)

_ELDER = CompanyDomainRow(company="elder_care", catalog="uc13_ale", display_name="Elder Care")


def _probe_measured(*, completeness: float, denominator: int) -> IngestProbeResult:
    ingested = round(completeness * denominator)
    return IngestProbeResult(
        company="elder_care",
        catalog="uc13_ale",
        backend="sql_chunk_count",
        status="measured",
        completeness=completeness,
        denominator=denominator,
        per_doc_type={"FINANCIAL": {"expected": denominator, "ingested": ingested}},
    )


def test_rows_per_company_is_total_over_layers_and_surfaces() -> None:
    keys = _rows_per_company("elder_care")
    assert len(keys) == 7
    assert sum(1 for layer, _ in keys if layer == "content_correctness") == 3


def test_derive_rows_for_company_emits_seven_rows() -> None:
    rows = derive_rows_for_company(
        _ELDER,
        ingest_probe=_probe_measured(completeness=0.52, denominator=412),
        registry_gap_titles=[],
    )
    assert len(rows) == 7


def test_measured_partial_maps_incomplete_corpus_with_method() -> None:
    rows = derive_rows_for_company(
        _ELDER,
        ingest_probe=_probe_measured(completeness=467 / 475, denominator=475),
        registry_gap_titles=["Elder Care ingest gap"],
    )
    ingest = next(r for r in rows if r.layer == "ingest_completeness")
    assert ingest.attestation == "partial"
    assert ingest.reason == "incomplete_corpus"
    assert ingest.method == "sql_chunk_count"
    assert ingest.rung is None
    assert any("98%" in gap for gap in ingest.known_gaps)
    assert "Elder Care ingest gap" in ingest.known_gaps


def test_measured_full_completeness_is_attested() -> None:
    rows = derive_rows_for_company(
        _ELDER,
        ingest_probe=_probe_measured(completeness=1.0, denominator=100),
    )
    ingest = next(r for r in rows if r.layer == "ingest_completeness")
    assert ingest.attestation == "attested"
    assert ingest.reason is None
    assert ingest.method == "sql_chunk_count"


def test_probe_failed_maps_probe_unavailable_without_method() -> None:
    probe = IngestProbeResult(
        company="elder_care",
        catalog="uc13_ale",
        backend="sql_chunk_count",
        status="probe_failed",
    )
    rows = derive_rows_for_company(_ELDER, ingest_probe=probe)
    ingest = next(r for r in rows if r.layer == "ingest_completeness")
    assert ingest.attestation == "not_attested"
    assert ingest.reason == "probe_unavailable"
    assert ingest.method is None


def test_denominator_undefined_maps_without_method() -> None:
    probe = IngestProbeResult(
        company="elder_care",
        catalog="uc13_ale",
        backend="sql_chunk_count",
        status="denominator_undefined",
    )
    rows = derive_rows_for_company(_ELDER, ingest_probe=probe)
    ingest = next(r for r in rows if r.layer == "ingest_completeness")
    assert ingest.reason == "denominator_undefined"
    assert ingest.method is None


def test_sentinel_company_skips_probe_and_halts_all_layers() -> None:
    rows = derive_rows_for_company(
        CompanyDomainRow(company="__unnormalizable__", catalog="uc13_ale"),
        ingest_probe=None,
    )
    assert len(rows) == 7
    assert all(row.reason == "unnormalizable_company" for row in rows)
    assert all(row.method is None for row in rows)


def test_non_ingest_layers_default_to_no_completed_run() -> None:
    rows = derive_rows_for_company(
        _ELDER,
        ingest_probe=_probe_measured(completeness=1.0, denominator=10),
    )
    others = [r for r in rows if r.layer != "ingest_completeness"]
    content = [r for r in others if r.layer == LAYER_CONTENT_CORRECTNESS]
    non_content = [r for r in others if r.layer != LAYER_CONTENT_CORRECTNESS]
    assert len(content) == 3
    assert all(r.attestation == ATTESTATION_WAIVED for r in content)
    assert all(r.reason == "no_completed_run" for r in content)
    assert len(non_content) == 3
    assert all(r.attestation == "not_attested" for r in non_content)
    assert all(r.reason == "no_completed_run" for r in non_content)


def test_validate_row_rejects_reasonless_not_attested() -> None:
    row = TrustStatementRow(
        company="elder_care",
        layer="retrieval",
        surface=None,
        attestation="not_attested",
        reason=None,
        method=None,
        rung=None,
    )
    with pytest.raises(TrustStatementGenerationError, match="reason required"):
        validate_row(row)


def test_validate_row_rejects_out_of_vocabulary_reason() -> None:
    row = TrustStatementRow(
        company="elder_care",
        layer="retrieval",
        surface=None,
        attestation="not_attested",
        reason="made_up_reason",
        method=None,
        rung=None,
    )
    with pytest.raises(TrustStatementGenerationError, match="out-of-vocabulary reason"):
        validate_row(row)


def test_validate_rows_rejects_duplicate_keys() -> None:
    row = TrustStatementRow(
        company="elder_care",
        layer="retrieval",
        surface=None,
        attestation="not_attested",
        reason="no_completed_run",
        method=None,
        rung=None,
    )
    with pytest.raises(TrustStatementGenerationError, match="duplicate row key"):
        validate_rows([row, row])


def test_run_ingest_probe_never_raises_on_executor_failure() -> None:
    def _boom(_sql: str) -> list[list[str | None]]:
        raise RuntimeError("warehouse down")

    probe = run_ingest_probe(
        _boom,
        company_slug="elder_care",
        catalog="uc13_ale",
        company_display="Elder Care",
    )
    assert probe.status == "probe_failed"


def test_run_ingest_probe_zero_denominator_is_denominator_undefined() -> None:
    def _execute(_sql: str) -> list[list[str | None]]:
        return [["0", "0"]]

    probe = run_ingest_probe(
        _execute,
        company_slug="elder_care",
        catalog="uc13_ale",
        company_display="Elder Care",
    )
    assert probe.status == "denominator_undefined"


def test_registry_gap_titles_include_staged_ingest_gap() -> None:
    registry = {
        "items": [
            {
                "id": "OI-data-ingest-quality-elder-care-ingest-gap",
                "title": "Elder Care ingest gap",
                "disposition": "staged",
            },
            {
                "id": "O-11",
                "title": "O-11 / GKF–SPG fallback re-verify",
                "disposition": "staged",
            },
        ]
    }
    titles = registry_gap_titles_for_company(registry, company_slug="elder_care")
    assert titles == ["Elder Care ingest gap"]


def test_render_markdown_contains_yaml_rows_block() -> None:
    rows = derive_rows_for_company(
        _ELDER,
        ingest_probe=_probe_measured(completeness=1.0, denominator=10),
    )
    text = render_trust_statement_markdown(rows, catalog="uc13_ale")
    assert "# Trust statement" in text
    assert "layer: ingest_completeness" in text
    assert "```yaml" in text


def test_derive_rows_merges_multiple_companies() -> None:
    domain = [
        _ELDER,
        CompanyDomainRow(company="acme_corp", catalog="uc13_ale", display_name="Acme Corp"),
    ]
    probes = {
        "elder_care": _probe_measured(completeness=1.0, denominator=10),
        "acme_corp": _probe_measured(completeness=1.0, denominator=5),
    }
    rows = derive_rows(domain, ingest_probes=probes)
    assert len(rows) == 14


def test_assert_row_set_total_fails_when_layer_row_missing() -> None:
    rows = derive_rows_for_company(
        _ELDER,
        ingest_probe=_probe_measured(completeness=1.0, denominator=10),
    )
    truncated = [row for row in rows if row.layer != "e2e"]
    with pytest.raises(TrustStatementGenerationError, match="row set non-total"):
        assert_row_set_total(truncated, ["elder_care"])


def test_v1_retrieval_row_attested_with_epoch_context() -> None:
    epoch = TrustEpochContext(
        baseline_id="baseline_acf58bcc4968",
        ingestion_snapshot="uc13_ale:55812:2026-08-11",
        gold_ready_summary=_GOLD_READY_SUMMARY,
        refresh_event_refs=["signoffs/T5-baseline.md"],
    )
    rows = derive_rows_for_company(
        _ELDER,
        ingest_probe=_probe_measured(completeness=1.0, denominator=10),
        epoch_context=epoch,
    )
    retrieval = next(r for r in rows if r.layer == "retrieval")
    assert retrieval.attestation == "attested"
    assert retrieval.reason is None
    assert "baseline_acf58bcc4968" in retrieval.evidence_refs
    assert "uc13_ale:55812:2026-08-11" in retrieval.evidence_refs
    assert _GOLD_READY_SUMMARY in retrieval.known_gaps[0]
    assert "35104" not in " ".join(retrieval.evidence_refs)


def test_load_epoch_context_rejects_stale_snapshot(tmp_path) -> None:
    report = tmp_path / "stale.json"
    report.write_text(
        '{"manifest": {"run_id": "baseline_old", "ingestion_snapshot": "uc13_ale:35104:2026-07-30"}}',
        encoding="utf-8",
    )
    with pytest.raises(TrustStatementGenerationError, match="35104-epoch"):
        load_epoch_context_from_baseline_report(report)


def test_render_markdown_v1_includes_epoch_header() -> None:
    epoch = TrustEpochContext(
        baseline_id="baseline_acf58bcc4968",
        ingestion_snapshot="uc13_ale:55812:2026-08-11",
        gold_ready_summary=_GOLD_READY_SUMMARY,
    )
    rows = derive_rows_for_company(
        _ELDER,
        ingest_probe=_probe_measured(completeness=1.0, denominator=10),
        epoch_context=epoch,
    )
    text = render_trust_statement_markdown(rows, catalog="uc13_ale", epoch_context=epoch)
    assert "Generator: v1" in text
    assert "baseline_acf58bcc4968" in text
    assert _GOLD_READY_SUMMARY in text
    assert "35104" not in text


def _run_ts() -> datetime:
    return datetime(2026, 8, 13, 12, 49, 47, 123456, tzinfo=timezone.utc)


def _claim_row(
    *,
    surface: str,
    run_id: str,
    claim_id: str,
    verdict: str,
) -> S2ScoreRow:
    return S2ScoreRow(
        company="elder_care",
        surface=surface,
        run_id=run_id,
        run_ts=_run_ts(),
        row_type="claim",
        claim_id=claim_id,
        verdict=verdict,
    )


def _marker_row(*, surface: str, run_id: str, writer: str) -> S2ScoreRow:
    return S2ScoreRow.from_completion_marker(
        company="elder_care",
        surface=surface,
        run_id=run_id,
        run_ts=_run_ts(),
        writer=writer,
    )


def test_derive_content_rows_waived_when_no_completed_run() -> None:
    rows = derive_content_rows("elder_care", "uc13_ale", s2_rows=[])
    assert len(rows) == 3
    assert all(row.attestation == ATTESTATION_WAIVED for row in rows)
    assert all(row.reason == "no_completed_run" for row in rows)
    assert all(row.rung is None for row in rows)


def test_derive_content_rows_rung_from_marker_writer() -> None:
    rows = derive_content_rows(
        "elder_care",
        "uc13_ale",
        s2_rows=[
            _claim_row(
                surface="legal_register",
                run_id="20260813T120000Z-legal",
                claim_id="legal.claim.001",
                verdict="supported",
            ),
            _marker_row(
                surface="legal_register",
                run_id="20260813T120000Z-legal",
                writer="deterministic_verifier",
            ),
        ],
    )
    legal = next(row for row in rows if row.content_surface == "legal_register")
    assert legal.attestation == "attested"
    assert legal.rung == "deterministic"


def test_derive_content_rows_human_spot_check_maps_to_human_rung() -> None:
    rows = derive_content_rows(
        "elder_care",
        "uc13_ale",
        s2_rows=[
            _claim_row(
                surface="exec_summary",
                run_id="20260813T124947Z-9a9e",
                claim_id="exec.claim.001",
                verdict="supported",
            ),
            _marker_row(
                surface="exec_summary",
                run_id="20260813T124947Z-9a9e",
                writer="human_spot_check",
            ),
        ],
    )
    exec_row = next(row for row in rows if row.content_surface == "exec_summary")
    assert exec_row.attestation == "attested"
    assert exec_row.rung == "human"
    assert exec_row.reason is None


def test_derive_content_rows_partial_on_claim_failures() -> None:
    rows = derive_content_rows(
        "elder_care",
        "uc13_ale",
        s2_rows=[
            _claim_row(
                surface="exec_summary",
                run_id="20260813T124947Z-9a9e",
                claim_id="exec.claim.001",
                verdict="contradicted",
            ),
            _marker_row(
                surface="exec_summary",
                run_id="20260813T124947Z-9a9e",
                writer="human_spot_check",
            ),
        ],
    )
    exec_row = next(row for row in rows if row.content_surface == "exec_summary")
    assert exec_row.attestation == "partial"
    assert exec_row.reason == "claim_failures"
    assert exec_row.rung == "human"


def test_derive_content_rows_fail_closed_on_unknown_writer() -> None:
    with pytest.raises(ValueError, match="marker writer"):
        derive_content_rows(
            "elder_care",
            "uc13_ale",
            s2_rows=[
                _marker_row(
                    surface="fta_numeric",
                    run_id="20260813T151817Z-bad",
                    writer="made_up_writer",
                )
            ],
        )


def test_derive_content_rows_zero_claim_run_is_not_attested() -> None:
    rows = derive_content_rows(
        "elder_care",
        "uc13_ale",
        s2_rows=[
            _marker_row(
                surface="fta_numeric",
                run_id="20260813T151817Z-empty",
                writer="human_spot_check",
            )
        ],
    )
    fta = next(row for row in rows if row.content_surface == "fta_numeric")
    assert fta.attestation == "not_attested"
    assert fta.reason == "zero_claim_run"
    assert fta.rung is None


def test_validate_row_rejects_content_surface_on_non_content_layer() -> None:
    with pytest.raises(ValueError, match="content_surface must be null"):
        TrustStatementRow(
            company="elder_care",
            layer="retrieval",
            surface=None,
            content_surface="exec_summary",
            attestation="not_attested",
            reason="no_completed_run",
            method=None,
            rung=None,
        )


def test_derive_rows_for_company_threads_content_surface_through_full_row_set() -> None:
    rows = derive_rows_for_company(
        _ELDER,
        ingest_probe=_probe_measured(completeness=1.0, denominator=10),
        s2_rows=[
            _claim_row(
                surface="legal_register",
                run_id="20260813T120000Z-legal",
                claim_id="legal.claim.001",
                verdict="supported",
            ),
            _marker_row(
                surface="legal_register",
                run_id="20260813T120000Z-legal",
                writer="deterministic_verifier",
            ),
        ],
    )
    legal = next(
        row
        for row in rows
        if row.layer == LAYER_CONTENT_CORRECTNESS and row.content_surface == "legal_register"
    )
    assert legal.attestation == "attested"
    assert legal.surface == "legal_register"
