"""Hermetic tests for C6 trust-statement generator v0 — spec §17 item 10 / T9."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from eval.content.s2_writer import S2ScoreRow, S2Writer
from eval.content.spot_check import SpotCheckConfig, write_spot_check_results
from eval.retrieval.exemptions import IntentExemption, load_exemptions
from eval.retrieval.companies import canonical_company_slug
from eval.retrieval.trust_statement import (
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
    display_name_from_company_slug,
    fetch_s2_score_rows,
    load_epoch_context_from_baseline_report,
    merge_exemption_companies_into_domain,
    registry_gap_titles_for_company,
    render_trust_statement_markdown,
    run_ingest_probe,
    validate_row,
    validate_rows,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMITTED_EXEMPTIONS = _REPO_ROOT / "eval" / "program" / "eval_exemptions.yaml"

_ELDER = CompanyDomainRow(company="elder_care", catalog="uc13_ale", display_name="Elder Care")
_EMPTY_S2: list[S2ScoreRow] = []


def _derive_company_rows(domain: CompanyDomainRow, **kwargs: object) -> list[TrustStatementRow]:
    if "s2_rows" not in kwargs and "s2_client" not in kwargs:
        kwargs["s2_rows"] = _EMPTY_S2
    return derive_rows_for_company(domain, **kwargs)  # type: ignore[arg-type]


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


def test_derive_company_rows_emits_seven_rows() -> None:
    rows = _derive_company_rows(
        _ELDER,
        ingest_probe=_probe_measured(completeness=0.52, denominator=412),
        registry_gap_titles=[],
    )
    assert len(rows) == 7


def test_measured_partial_maps_incomplete_corpus_with_method() -> None:
    rows = _derive_company_rows(
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
    rows = _derive_company_rows(
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
    rows = _derive_company_rows(_ELDER, ingest_probe=probe)
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
    rows = _derive_company_rows(_ELDER, ingest_probe=probe)
    ingest = next(r for r in rows if r.layer == "ingest_completeness")
    assert ingest.reason == "denominator_undefined"
    assert ingest.method is None


def test_sentinel_company_skips_probe_and_halts_all_layers() -> None:
    rows = _derive_company_rows(
        CompanyDomainRow(company="__unnormalizable__", catalog="uc13_ale"),
        ingest_probe=None,
    )
    assert len(rows) == 7
    assert all(row.reason == "unnormalizable_company" for row in rows)
    assert all(row.method is None for row in rows)


def test_non_ingest_layers_default_to_no_completed_run() -> None:
    rows = _derive_company_rows(
        _ELDER,
        ingest_probe=_probe_measured(completeness=1.0, denominator=10),
    )
    others = [r for r in rows if r.layer != "ingest_completeness"]
    assert len(others) == 6
    assert all(r.attestation == "not_attested" for r in others)
    assert all(r.reason == "no_completed_run" for r in others)
    assert all(r.rung is None for r in others)


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
    rows = _derive_company_rows(
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
    rows = derive_rows(
        domain,
        ingest_probes=probes,
        s2_rows_by_company={"elder_care": [], "acme_corp": []},
    )
    assert len(rows) == 14


def test_assert_row_set_total_fails_when_layer_row_missing() -> None:
    rows = _derive_company_rows(
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
    rows = _derive_company_rows(
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
    rows = _derive_company_rows(
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


def test_derive_content_rows_not_attested_when_no_completed_run() -> None:
    rows = derive_content_rows("elder_care", "uc13_ale", s2_rows=[])
    assert len(rows) == 3
    assert all(row.attestation == "not_attested" for row in rows)
    assert all(row.reason == "no_completed_run" for row in rows)
    assert all(row.rung is None for row in rows)
    assert all(row.content_surface in {"fta_numeric", "legal_register", "exec_summary"} for row in rows)


def test_validate_row_rejects_retired_waived_attestation() -> None:
    row = TrustStatementRow(
        company="elder_care",
        layer=LAYER_CONTENT_CORRECTNESS,
        surface="exec_summary",
        content_surface="exec_summary",
        attestation="waived",
        reason="no_completed_run",
        method=None,
        rung=None,
    )
    with pytest.raises(TrustStatementGenerationError, match="out-of-vocabulary attestation"):
        validate_row(row)


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


def test_derive_company_rows_threads_content_surface_through_full_row_set() -> None:
    rows = _derive_company_rows(
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


def test_derive_content_rows_fail_closed_without_s2_dependency() -> None:
    with pytest.raises(ValueError, match="S2 dependency required"):
        derive_content_rows("elder_care", "uc13_ale")


def _warehouse_row_from_s2(row: S2ScoreRow) -> list[str | None]:
    run_ts = row.run_ts.isoformat()
    return [
        row.company,
        row.surface,
        row.run_id,
        run_ts,
        row.row_type,
        row.claim_id,
        row.verdict,
        row.rationale,
        row.writer,
        str(row.asserted_magnitude) if row.asserted_magnitude is not None else None,
        row.asserted_unit,
        str(row.extracted_magnitude) if row.extracted_magnitude is not None else None,
        row.extracted_unit,
        row.cited_chunk_id,
        row.cited_locator_kind,
        row.cited_locator_value,
        row.judge_verdict_advisory,
    ]


def test_fetch_s2_score_rows_preserves_magnitude_unit_columns() -> None:
    source = S2ScoreRow(
        company="elder_care",
        surface="fta_numeric",
        run_id="20260813T151817Z-mag",
        run_ts=_run_ts(),
        row_type="claim",
        claim_id="fta.claim.001",
        verdict="supported",
        asserted_magnitude=Decimal("58.3"),
        asserted_unit="percent",
        extracted_magnitude=Decimal("58.30"),
        extracted_unit="percent",
    )

    class _Client:
        def execute_sql(self, _sql: str) -> list[list[str | None]]:
            return [_warehouse_row_from_s2(source)]

    fetched = fetch_s2_score_rows("elder_care", "uc13_ale", client=_Client())
    assert len(fetched) == 1
    assert fetched[0].asserted_magnitude == Decimal("58.3")
    assert fetched[0].asserted_unit == "percent"
    assert fetched[0].extracted_magnitude == Decimal("58.30")
    assert fetched[0].extracted_unit == "percent"


def test_fetch_s2_score_rows_parses_sdk_three_digit_fractional_run_ts() -> None:
    sdk_ts = "2026-08-13T18:30:00.481Z"
    source = S2ScoreRow(
        company="elder_care",
        surface="fta_numeric",
        run_id="20260813T183000Z-probe",
        run_ts=datetime(2026, 8, 13, 18, 30, 0, 481000, tzinfo=timezone.utc),
        row_type="claim",
        claim_id="fta.claim.001",
        verdict="supported",
    )
    warehouse_row = _warehouse_row_from_s2(source)
    warehouse_row[3] = sdk_ts

    class _Client:
        def execute_sql(self, _sql: str) -> list[list[str | None]]:
            return [warehouse_row]

    fetched = fetch_s2_score_rows("elder_care", "uc13_ale", client=_Client())
    assert len(fetched) == 1
    assert fetched[0].run_ts == datetime(2026, 8, 13, 18, 30, 0, 481000, tzinfo=timezone.utc)


def test_fetch_s2_score_rows_raises_on_short_row() -> None:
    class _Client:
        def execute_sql(self, _sql: str) -> list[list[str | None]]:
            return [
                [
                    "elder_care",
                    "legal_register",
                    "20260813T120000Z-x",
                    "2026-08-13T12:00:00.000Z",
                    "claim",
                ]
            ]

    with pytest.raises(ValueError, match="expected 17"):
        fetch_s2_score_rows("elder_care", "uc13_ale", client=_Client())


def test_derive_content_rows_supersedes_older_marker_on_same_surface() -> None:
    older_ts = datetime(2026, 8, 13, 12, 0, 0, 0, tzinfo=timezone.utc)
    newer_ts = datetime(2026, 8, 13, 13, 0, 0, 0, tzinfo=timezone.utc)
    s2_rows = [
        S2ScoreRow(
            company="elder_care",
            surface="legal_register",
            run_id="20260813T120000Z-old",
            run_ts=older_ts,
            row_type="claim",
            claim_id="legal.claim.001",
            verdict="contradicted",
        ),
        S2ScoreRow.from_completion_marker(
            company="elder_care",
            surface="legal_register",
            run_id="20260813T120000Z-old",
            run_ts=older_ts,
            writer="deterministic_verifier",
        ),
        S2ScoreRow(
            company="elder_care",
            surface="legal_register",
            run_id="20260813T130000Z-new",
            run_ts=newer_ts,
            row_type="claim",
            claim_id="legal.claim.001",
            verdict="supported",
        ),
        S2ScoreRow.from_completion_marker(
            company="elder_care",
            surface="legal_register",
            run_id="20260813T130000Z-new",
            run_ts=newer_ts,
            writer="deterministic_verifier",
        ),
    ]

    rows = derive_content_rows("elder_care", "uc13_ale", s2_rows=s2_rows)
    legal = next(
        row
        for row in rows
        if row.layer == LAYER_CONTENT_CORRECTNESS and row.content_surface == "legal_register"
    )
    assert legal.attestation == "attested"
    assert legal.evidence_refs == ["s2_scores:20260813T130000Z-new"]


def test_derive_content_rows_fail_closed_on_truncated_run_ts_tie() -> None:
    tied_ts = datetime(2026, 8, 13, 18, 30, 0, 481000, tzinfo=timezone.utc)
    s2_rows = [
        S2ScoreRow.from_completion_marker(
            company="elder_care",
            surface="exec_summary",
            run_id="20260813T183000Z-aaaa",
            run_ts=tied_ts,
            writer="human_spot_check",
        ),
        S2ScoreRow.from_completion_marker(
            company="elder_care",
            surface="exec_summary",
            run_id="20260813T183000Z-bbbb",
            run_ts=tied_ts,
            writer="human_spot_check",
        ),
    ]

    with pytest.raises(ValueError, match="ambiguous latest marker"):
        derive_content_rows("elder_care", "uc13_ale", s2_rows=s2_rows)


def test_derive_rows_seam_threads_s2_client_to_content_rows() -> None:
    s2_fixture = [
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
    ]

    class _Client:
        def execute_sql(self, sql: str) -> list[list[str | None]]:
            if "eval.s2_scores" in sql:
                return [_warehouse_row_from_s2(row) for row in s2_fixture]
            return []

    rows = derive_rows(
        [_ELDER],
        ingest_probes={
            "elder_care": _probe_measured(completeness=1.0, denominator=10),
        },
        s2_client=_Client(),
    )
    legal = next(
        row
        for row in rows
        if row.layer == LAYER_CONTENT_CORRECTNESS and row.content_surface == "legal_register"
    )
    assert legal.attestation == "attested"
    assert legal.rung == "deterministic"


def _spot_check_registry_yaml() -> str:
    return yaml.safe_dump(
        {
            "schema_version": 1,
            "items": [
                {"id": "CHK-26a", "rung_assignments": {"exec_summary": "human"}},
            ],
        }
    )


def test_content_rows_compose_with_spot_check_writer_fixtures(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "eval/content").mkdir(parents=True)
    (root / "eval/program").mkdir(parents=True)
    (root / "eval/program/registry.yaml").write_text(
        _spot_check_registry_yaml(), encoding="utf-8"
    )
    manifest = """{
  "schema_version": 1,
  "claim_count": 1,
  "claims": [
    {"section": "Overview", "claim_id": "exec.claim.001", "claim_text": "Example."}
  ]
}"""
    (root / "eval/content/exec_summary_rubric_claims.json").write_text(manifest, encoding="utf-8")
    verdicts = root / ".dev/eval-program/spot-check/verdicts.yaml"
    verdicts.parent.mkdir(parents=True, exist_ok=True)
    verdicts.write_text(
        yaml.safe_dump(
            {
                "claims": [
                    {
                        "claim_id": "exec.claim.001",
                        "verdict": "supported",
                        "rationale": "confirmed",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    cfg = SpotCheckConfig(
        company="Elder Care",
        surface="exec_summary",
        source="uc13_ale.analysis.diligence_report.executive_summary",
        catalog="uc13_ale",
        output_dir=root / ".dev/eval-program/spot-check",
        verdicts_path=verdicts,
        operator_id="operator_a",
        registry_path=root / "eval/program/registry.yaml",
        repo_root=root,
    )

    captured_claims: list[S2ScoreRow] = []
    run_ts = datetime(2026, 8, 12, 18, 30, 45, 123456, tzinfo=timezone.utc)
    writer = S2Writer(catalog="uc13_ale", sql_executor=lambda _sql: [])
    original_write_claims = writer.write_claims

    def _capture_claims(
        company: str,
        surface: str,
        run_id: str,
        ts: datetime,
        rows: list[S2ScoreRow],
        **write_kwargs: object,
    ) -> None:
        captured_claims.extend(rows)
        original_write_claims(company, surface, run_id, ts, rows, **write_kwargs)

    writer.write_claims = _capture_claims  # type: ignore[method-assign]

    result = write_spot_check_results(
        cfg,
        writer=writer,
        run_id="20260812T183045Z-ab12",
        run_ts=run_ts,
    )
    s2_rows = captured_claims + [
        S2ScoreRow.from_completion_marker(
            company="elder_care",
            surface="exec_summary",
            run_id=result.run_id,
            run_ts=result.run_ts,
            writer="human_spot_check",
        )
    ]
    content = derive_content_rows("elder_care", "uc13_ale", s2_rows=s2_rows)
    exec_row = next(row for row in content if row.content_surface == "exec_summary")
    assert exec_row.attestation == "attested"
    assert exec_row.rung == "human"


def _sample_exemption(**overrides: object) -> IntentExemption:
    base = {
        "company": "clearsulting",
        "intent_id": "legal.ip_privacy",
        "surface": "legal_register",
        "coverage": "eliminates",
        "reason": "corpus_absent",
        "corpus_evidence": {"legal_docs": 0},
        "approved_by": "operator",
    }
    base.update(overrides)
    return IntentExemption(**base)  # type: ignore[arg-type]


def test_empty_exemptions_preserves_elder_care_rows_dg10() -> None:
    """DG-10: committed empty store must not alter Elder Care row set."""
    epoch = TrustEpochContext(
        baseline_id="baseline_acf58bcc4968",
        ingestion_snapshot="uc13_ale:55812:2026-08-11",
        gold_ready_summary=_GOLD_READY_SUMMARY,
    )
    kwargs = {
        "ingest_probe": _probe_measured(completeness=467 / 475, denominator=475),
        "registry_gap_titles": ["Elder Care ingest gap"],
        "epoch_context": epoch,
        "s2_rows": [
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
    }
    baseline = _derive_company_rows(_ELDER, **kwargs)
    with_empty_list = derive_rows_for_company(_ELDER, exemptions=[], **kwargs)  # type: ignore[arg-type]
    with_committed_store = derive_rows_for_company(
        _ELDER,
        exemptions=load_exemptions(_COMMITTED_EXEMPTIONS),
        **kwargs,  # type: ignore[arg-type]
    )
    baseline_payload = [row.as_dict() for row in baseline]
    assert baseline_payload == [row.as_dict() for row in with_empty_list]
    assert baseline_payload == [row.as_dict() for row in with_committed_store]


def test_eliminates_exemption_emits_known_gap_row() -> None:
    rows = derive_rows_for_company(
        CompanyDomainRow(company="clearsulting", catalog="uc13_ale"),
        ingest_probe=_probe_measured(completeness=1.0, denominator=10),
        s2_rows=_EMPTY_S2,
        exemptions=[_sample_exemption()],
    )
    legal = next(
        row
        for row in rows
        if row.layer == LAYER_CONTENT_CORRECTNESS and row.content_surface == "legal_register"
    )
    assert legal.attestation == "known_gap"
    assert legal.reason == "corpus_absent"
    assert legal.rung is None


def test_eliminates_severity_precedence_on_same_surface() -> None:
    exemptions = [
        _sample_exemption(intent_id="gap.overlay", reason="overlay_mismatch"),
        _sample_exemption(intent_id="gap.absent", reason="corpus_absent"),
        _sample_exemption(intent_id="gap.thin", reason="corpus_thin"),
    ]
    rows = derive_rows_for_company(
        CompanyDomainRow(company="clearsulting", catalog="uc13_ale"),
        ingest_probe=_probe_measured(completeness=1.0, denominator=10),
        s2_rows=_EMPTY_S2,
        exemptions=exemptions,
    )
    legal = next(
        row
        for row in rows
        if row.layer == LAYER_CONTENT_CORRECTNESS and row.content_surface == "legal_register"
    )
    assert legal.attestation == "known_gap"
    assert legal.reason == "corpus_absent"


def test_narrows_relabels_partial_only_on_exempted_surface() -> None:
    s2_rows = [
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
        _claim_row(
            surface="legal_register",
            run_id="20260813T120000Z-legal",
            claim_id="legal.claim.001",
            verdict="contradicted",
        ),
        _marker_row(
            surface="legal_register",
            run_id="20260813T120000Z-legal",
            writer="deterministic_verifier",
        ),
    ]
    exemptions = [
        _sample_exemption(
            company="elder_care",
            surface="exec_summary",
            coverage="narrows",
            reason="corpus_thin",
        )
    ]
    rows = derive_rows_for_company(
        _ELDER,
        ingest_probe=_probe_measured(completeness=1.0, denominator=10),
        s2_rows=s2_rows,
        exemptions=exemptions,
    )
    exec_row = next(row for row in rows if row.content_surface == "exec_summary")
    legal_row = next(row for row in rows if row.content_surface == "legal_register")
    assert exec_row.attestation == "partial"
    assert exec_row.reason == "exempted_corpus_failures"
    assert legal_row.attestation == "partial"
    assert legal_row.reason == "claim_failures"


def test_surface_null_exemption_does_not_affect_content_rows() -> None:
    kwargs = {
        "ingest_probe": _probe_measured(completeness=1.0, denominator=10),
        "s2_rows": _EMPTY_S2,
    }
    baseline = _derive_company_rows(_ELDER, **kwargs)
    with_null_scope = derive_rows_for_company(
        _ELDER,
        exemptions=[
            _sample_exemption(
                company="elder_care",
                surface=None,
                coverage=None,
                reason="corpus_thin",
                intent_id="retrieval.scope",
            )
        ],
        **kwargs,  # type: ignore[arg-type]
    )
    assert [row.as_dict() for row in baseline] == [row.as_dict() for row in with_null_scope]


def test_merge_exemption_companies_into_domain_unions_new_slug() -> None:
    merged = merge_exemption_companies_into_domain(
        [_ELDER],
        [_sample_exemption(company="clearsulting")],
        catalog="uc13_ale",
    )
    slugs = {entry.company for entry in merged}
    assert slugs == {"elder_care", "clearsulting"}
    clearsulting = next(entry for entry in merged if entry.company == "clearsulting")
    assert clearsulting.catalog == "uc13_ale"
    assert clearsulting.display_name == "Clearsulting"


def test_display_name_from_slug_round_trips_domain_companies() -> None:
    """F-10: inverse display label must round-trip via canonical_company_slug."""
    domain_slugs = ("elder_care", "clearsulting")
    for slug in domain_slugs:
        display = display_name_from_company_slug(slug)
        assert canonical_company_slug(display) == slug
    merged = merge_exemption_companies_into_domain(
        [_ELDER],
        [_sample_exemption(company="clearsulting")],
        catalog="uc13_ale",
    )
    for entry in merged:
        assert canonical_company_slug(entry.display_name or "") == entry.company


def test_run_ingest_probe_delegates_to_preflight_contract() -> None:
    calls: list[str] = []

    def _execute(sql: str) -> list[list[str | None]]:
        calls.append(sql)
        if "GROUP BY e.doc_type" in sql:
            return [["FINANCIAL", "10", "8"]]
        return [["10", "8"]]

    probe = run_ingest_probe(
        _execute,
        company_slug="elder_care",
        catalog="uc13_ale",
        company_display="Elder Care",
    )
    assert probe.status == "measured"
    assert probe.backend == "sql_chunk_count"
    assert probe.completeness == 0.8
    assert len(calls) == 2
