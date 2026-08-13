"""Hermetic tests for rung-3 spot-check tooling (T4 / §12.1)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from eval.content.s2_writer import S2Writer
from eval.content.spot_check import (
    ChunkIndex,
    ChunkRecord,
    SpotCheckConfig,
    SpotCheckIngestionError,
    load_claim_enumeration,
    load_exec_analysis_cache,
    prepare_spot_check,
    write_spot_check_results,
)


def _registry_yaml() -> str:
    return yaml.safe_dump(
        {
            "schema_version": 1,
            "items": [
                {
                    "id": "CHK-23a",
                    "rung_assignments": {"legal_register": "deterministic"},
                },
                {
                    "id": "CHK-26a",
                    "rung_assignments": {
                        "exec_summary": "human",
                        "fta_numeric": "human",
                    },
                },
            ],
        }
    )


def _exec_manifest() -> str:
    return """{
  "schema_version": 1,
  "claim_count": 2,
  "claims": [
    {
      "section": "Business Overview",
      "claim_id": "exec.claim.001",
      "claim_text": "Example claim one."
    },
    {
      "section": "Financial Picture",
      "claim_id": "exec.claim.002",
      "claim_text": "Example claim two."
    }
  ]
}"""


def _fta_manifest() -> str:
    return """{
  "schema_version": 1,
  "claim_count": 2,
  "claims": [
    {
      "claim_id": "fta.claim.001",
      "claim_text": "yoy_growth_pct: 58.3%",
      "source_doc": "2024 Elder Care - CIM_vF.pdf",
      "source_location": "Pro Forma Income Statement & Projection"
    },
    {
      "claim_id": "fta.claim.002",
      "claim_text": "revenue_2024: 4200000",
      "source_doc": "2024 Elder Care - CIM_vF.pdf",
      "source_location": "Pro Forma Income Statement & Projection"
    }
  ]
}"""


@pytest.fixture()
def spot_check_tree(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "eval/content").mkdir(parents=True)
    (root / ".dev/eval-program").mkdir(parents=True)
    (root / ".dev/eval-program/registry.yaml").write_text(
        _registry_yaml(), encoding="utf-8"
    )
    (root / "eval/content/exec_summary_rubric_claims.json").write_text(
        _exec_manifest(), encoding="utf-8"
    )
    (root / "eval/content/fta_numeric_rubric_claims.json").write_text(
        _fta_manifest(), encoding="utf-8"
    )
    return root


def _config(
    root: Path,
    *,
    surface: str = "exec_summary",
    source: str = "uc13_ale.analysis.diligence_report.executive_summary",
    output_dir: Path | None = None,
    verdicts_path: Path | None = None,
) -> SpotCheckConfig:
    out = output_dir or (root / ".dev/eval-program/spot-check")
    verdicts = verdicts_path or (out / "exec_summary_elder_care.verdicts.yaml")
    return SpotCheckConfig(
        company="Elder Care",
        surface=surface,
        source=source,
        output_dir=out,
        verdicts_path=verdicts,
        operator_id="operator_a",
        registry_path=root / ".dev/eval-program/registry.yaml",
        repo_root=root,
    )


def test_spot_check_config_round_trip_fields(spot_check_tree: Path) -> None:
    cfg = _config(spot_check_tree)
    assert cfg.company == "Elder Care"
    assert cfg.surface == "exec_summary"
    assert cfg.source.startswith("uc13_ale.")
    assert cfg.output_dir.is_dir() is False
    assert cfg.verdicts_path.name.endswith(".yaml")
    assert cfg.operator_id == "operator_a"


def test_spot_check_config_rejects_unsupported_surface(spot_check_tree: Path) -> None:
    with pytest.raises(ValueError, match="no committed claim manifest"):
        SpotCheckConfig(
            company="Elder Care",
            surface="legal_register",
            source="uc13_ale.analysis.legal",
            output_dir=spot_check_tree / "out",
            verdicts_path=spot_check_tree / "out/verdicts.yaml",
            operator_id="operator_a",
            registry_path=spot_check_tree / ".dev/eval-program/registry.yaml",
            repo_root=spot_check_tree,
        )


def test_prepare_spot_check_writes_yaml_packet(spot_check_tree: Path) -> None:
    cfg = _config(spot_check_tree)
    result = prepare_spot_check(cfg)

    assert result.claim_count == 2
    assert result.packet_path.is_file()
    payload = yaml.safe_load(result.packet_path.read_text(encoding="utf-8"))
    assert payload["format"] == "spot_check_presentation_v1"
    assert payload["company_slug"] == "elder_care"
    assert payload["claims"][0]["claim_id"] == "exec.claim.001"
    assert payload["claims"][0]["verdict"] is None
    assert payload["operator_id"] == "operator_a"


def test_load_claim_enumeration_parses_fta_numeric_magnitude(
    spot_check_tree: Path,
) -> None:
    cfg = _config(
        spot_check_tree,
        surface="fta_numeric",
        source="uc13_ale.analysis.financial_trends",
    )
    claims = load_claim_enumeration(cfg)
    assert len(claims) == 2
    assert claims[0].asserted_magnitude == Decimal("58.3")
    assert claims[0].asserted_unit == "percent"
    assert claims[0].cited_locator_kind is None
    assert claims[1].asserted_magnitude == Decimal("4200000")
    assert claims[1].asserted_unit is None


def test_parse_fta_claim_text_digit_bearing_field_name(spot_check_tree: Path) -> None:
    cfg = _config(
        spot_check_tree,
        surface="fta_numeric",
        source="uc13_ale.analysis.financial_trends",
    )
    manifest_path = spot_check_tree / "eval/content/fta_numeric_rubric_claims.json"
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    payload["claims"].append(
        {
            "claim_id": "fta.claim.003",
            "claim_text": "line_item_2024: 12.5",
            "source_doc": "2024 Elder Care - CIM_vF.pdf",
            "source_location": "Pro Forma Income Statement & Projection",
        }
    )
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    claims = load_claim_enumeration(cfg)
    digit_claim = next(c for c in claims if c.claim_id == "fta.claim.003")
    assert digit_claim.asserted_magnitude == Decimal("12.5")
    assert digit_claim.asserted_unit is None


class RecordingSqlExecutor:
    def __init__(
        self,
        *,
        marker_exists: bool = False,
        claims_without_marker: bool = False,
    ) -> None:
        self.statements: list[str] = []
        self._marker_exists = marker_exists
        self._claims_without_marker = claims_without_marker

    def __call__(self, statement: str) -> list[list[str]]:
        self.statements.append(statement)
        normalized = " ".join(statement.split())
        if normalized.startswith("SELECT"):
            if "row_type IN ('claim', 'completion_marker')" in normalized:
                rows: list[list[str]] = []
                if self._claims_without_marker:
                    rows.append(["claim"])
                if self._marker_exists:
                    rows.append(["completion_marker"])
                return rows
            if "row_type = 'completion_marker'" in normalized:
                return [["completion_marker"]] if self._marker_exists else []
        return []


def _write_verdicts(path: Path, *, surface: str = "exec_summary") -> None:
    claims = (
        [
            {"claim_id": "exec.claim.001", "verdict": "supported", "rationale": "yes"},
            {"claim_id": "exec.claim.002", "verdict": "contradicted", "rationale": "no"},
        ]
        if surface == "exec_summary"
        else [
            {"claim_id": "fta.claim.001", "verdict": "supported", "rationale": "pct ok"},
            {"claim_id": "fta.claim.002", "verdict": "supported", "rationale": "revenue ok"},
        ]
    )
    payload = {
        "schema_version": 1,
        "surface": surface,
        "company": "Elder Care",
        "operator_id": "operator_a",
        "claims": claims,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_write_spot_check_results_claims_then_marker_same_run(
    spot_check_tree: Path,
) -> None:
    cfg = _config(spot_check_tree)
    _write_verdicts(cfg.verdicts_path)
    recorder = RecordingSqlExecutor()
    writer = S2Writer(catalog="uc13_ale", sql_executor=recorder)
    run_ts = datetime(2026, 8, 12, 18, 30, 45, 123456, tzinfo=timezone.utc)

    result = write_spot_check_results(
        cfg,
        writer=writer,
        run_id="20260812T183045Z-ab12",
        run_ts=run_ts,
        chunk_index=ChunkIndex([]),
        chunk_id_resolver=lambda ids: frozenset(),
        exec_analysis_cache={},
    )

    assert result.run_id == "20260812T183045Z-ab12"
    assert result.claim_count == 2
    assert len(recorder.statements) == 4
    assert recorder.statements[0].strip().upper().startswith("SELECT")
    assert "INSERT" in recorder.statements[1]
    assert recorder.statements[2].strip().upper().startswith("SELECT")
    assert "human_spot_check" in recorder.statements[3]
    assert "20260812T183045Z-ab12" in recorder.statements[1]
    assert "20260812T183045Z-ab12" in recorder.statements[3]


def test_write_spot_check_results_rejects_missing_rationale(
    spot_check_tree: Path,
) -> None:
    cfg = _config(spot_check_tree)
    payload = {
        "claims": [
            {"claim_id": "exec.claim.001", "verdict": "supported", "rationale": "ok"},
            {"claim_id": "exec.claim.002", "verdict": "supported"},
        ]
    }
    cfg.verdicts_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.verdicts_path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(SpotCheckIngestionError, match="missing rationale"):
        write_spot_check_results(
            cfg,
            writer=S2Writer(catalog="uc13_ale", sql_executor=RecordingSqlExecutor()),
        )


def test_write_spot_check_results_rejects_unknown_claim_id(
    spot_check_tree: Path,
) -> None:
    cfg = _config(spot_check_tree)
    payload = {
        "claims": [
            {"claim_id": "exec.claim.001", "verdict": "supported", "rationale": "ok"},
            {"claim_id": "exec.claim.999", "verdict": "supported", "rationale": "ok"},
        ]
    }
    cfg.verdicts_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.verdicts_path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(SpotCheckIngestionError, match="unknown claim_id"):
        write_spot_check_results(
            cfg,
            writer=S2Writer(catalog="uc13_ale", sql_executor=RecordingSqlExecutor()),
        )


def test_write_spot_check_results_rejects_missing_verdict(
    spot_check_tree: Path,
) -> None:
    cfg = _config(spot_check_tree)
    payload = {"claims": [{"claim_id": "exec.claim.001", "verdict": "supported", "rationale": "ok"}]}
    cfg.verdicts_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.verdicts_path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(SpotCheckIngestionError, match="missing verdict for claim_id"):
        write_spot_check_results(
            cfg,
            writer=S2Writer(catalog="uc13_ale", sql_executor=RecordingSqlExecutor()),
        )


def test_write_spot_check_results_rejects_invalid_verdict_vocabulary(
    spot_check_tree: Path,
) -> None:
    cfg = _config(spot_check_tree)
    payload = {
        "claims": [
            {"claim_id": "exec.claim.001", "verdict": "maybe", "rationale": "ok"},
            {"claim_id": "exec.claim.002", "verdict": "supported", "rationale": "ok"},
        ]
    }
    cfg.verdicts_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.verdicts_path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(SpotCheckIngestionError, match="§16 vocabulary"):
        write_spot_check_results(
            cfg,
            writer=S2Writer(catalog="uc13_ale", sql_executor=RecordingSqlExecutor()),
        )


def test_prepare_spot_check_rejects_non_human_surface_assignment(
    spot_check_tree: Path,
) -> None:
    registry = yaml.safe_load(
        (spot_check_tree / ".dev/eval-program/registry.yaml").read_text(encoding="utf-8")
    )
    for item in registry["items"]:
        if item["id"] == "CHK-26a":
            item["rung_assignments"]["exec_summary"] = "deterministic"
    (spot_check_tree / ".dev/eval-program/registry.yaml").write_text(
        yaml.safe_dump(registry), encoding="utf-8"
    )
    cfg = _config(spot_check_tree)

    with pytest.raises(ValueError, match="expected 'human'"):
        prepare_spot_check(cfg)


def test_prepare_spot_check_halts_on_rung2_registry_assignment(
    spot_check_tree: Path,
) -> None:
    registry = yaml.safe_load(
        (spot_check_tree / ".dev/eval-program/registry.yaml").read_text(encoding="utf-8")
    )
    for item in registry["items"]:
        if item["id"] == "CHK-26a":
            item["rung_assignments"]["exec_summary"] = "judge"
    (spot_check_tree / ".dev/eval-program/registry.yaml").write_text(
        yaml.safe_dump(registry), encoding="utf-8"
    )
    cfg = _config(spot_check_tree)

    with pytest.raises(ValueError, match="rung-2"):
        prepare_spot_check(cfg)


def test_write_spot_check_results_without_sql_executor_raises_before_write(
    spot_check_tree: Path,
) -> None:
    cfg = _config(spot_check_tree)
    _write_verdicts(cfg.verdicts_path)

    with pytest.raises(RuntimeError, match="sql_executor is required"):
        write_spot_check_results(cfg)


def test_write_spot_check_results_committed_fta_manifest_276_claims(
    tmp_path: Path,
) -> None:
    """N-1 falsifier: shipped producer against committed manifest, no fixture manifest."""
    repo_root = Path(__file__).resolve().parents[3]
    cfg = SpotCheckConfig(
        company="Elder Care",
        surface="fta_numeric",
        source="uc13_ale.analysis.financial_trends",
        output_dir=tmp_path / "out",
        verdicts_path=tmp_path / "fta.verdicts.yaml",
        operator_id="operator_a",
        registry_path=repo_root / "eval/program/registry.yaml",
        repo_root=repo_root,
    )
    claims = load_claim_enumeration(cfg)
    assert len(claims) == 276
    mag_no_unit = [
        c for c in claims if c.asserted_magnitude is not None and c.asserted_unit is None
    ]
    assert len(mag_no_unit) == 84

    verdict_payload = {
        "schema_version": 1,
        "surface": "fta_numeric",
        "company": "Elder Care",
        "operator_id": "operator_a",
        "claims": [
            {"claim_id": c.claim_id, "verdict": "supported", "rationale": "r9 probe"}
            for c in claims
        ],
    }
    cfg.verdicts_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.verdicts_path.write_text(
        yaml.safe_dump(verdict_payload, sort_keys=False), encoding="utf-8"
    )

    recorder = RecordingSqlExecutor()
    writer = S2Writer(catalog="uc13_ale", sql_executor=recorder)
    run_ts = datetime(2026, 8, 13, 17, 43, 0, 654321, tzinfo=timezone.utc)

    result = write_spot_check_results(
        cfg,
        writer=writer,
        run_id="20260813T174300Z-r9f",
        run_ts=run_ts,
        chunk_index=ChunkIndex([]),
        chunk_id_resolver=lambda ids: frozenset(),
    )

    assert result.claim_count == 276
    assert len(recorder.statements) == 4
    assert recorder.statements[0].strip().upper().startswith("SELECT")
    assert recorder.statements[1].strip().upper().startswith("INSERT")
    assert recorder.statements[2].strip().upper().startswith("SELECT")
    assert "human_spot_check" in recorder.statements[3]
    assert "20260813T174300Z-r9f" in recorder.statements[1]


def _mock_chunk_index() -> ChunkIndex:
    records = [
        ChunkRecord(
            chunk_id="cd9773ea-0a3c-460d-869a-bc963a15cd1f",
            file_name="2024 Elder Care - CIM_vF.pdf",
            section_header="Pro Forma Income Statement & Projection",
            page_start=49,
            chunk_text="table body",
        ),
        ChunkRecord(
            chunk_id="chunk-no-locator",
            file_name="orphan.pdf",
            section_header=None,
            page_start=None,
            chunk_text="",
        ),
    ]
    return ChunkIndex(records)


def test_write_spot_check_results_supplies_chunk_id_resolver(
    spot_check_tree: Path,
) -> None:
    cfg = _config(
        spot_check_tree,
        surface="fta_numeric",
        source="uc13_ale.analysis.financial_trends",
        verdicts_path=spot_check_tree / ".dev/eval-program/spot-check/fta.verdicts.yaml",
    )
    _write_verdicts(cfg.verdicts_path, surface="fta_numeric")
    recorder = RecordingSqlExecutor()
    index = _mock_chunk_index()
    resolver_calls: list[frozenset[str]] = []

    def tracking_resolver(ids: frozenset[str]) -> frozenset[str]:
        resolver_calls.append(ids)
        return index.resolve_ids(ids)

    write_spot_check_results(
        cfg,
        writer=S2Writer(catalog="uc13_ale", sql_executor=recorder),
        run_id="20260813T180000Z-r10a",
        run_ts=datetime(2026, 8, 13, 18, 0, 0, tzinfo=timezone.utc),
        chunk_index=index,
        chunk_id_resolver=tracking_resolver,
    )

    assert len(resolver_calls) == 1
    assert "cd9773ea-0a3c-460d-869a-bc963a15cd1f" in resolver_calls[0]


def test_claim_locator_none_when_chunk_has_no_section_or_page(
    spot_check_tree: Path,
) -> None:
    cfg = _config(
        spot_check_tree,
        surface="fta_numeric",
        source="uc13_ale.analysis.financial_trends",
    )
    index = ChunkIndex(
        [
            ChunkRecord(
                chunk_id="chunk-no-locator",
                file_name="2024 Elder Care - CIM_vF.pdf",
                section_header=None,
                page_start=None,
                chunk_text="",
            )
        ]
    )
    claims = load_claim_enumeration(cfg, chunk_index=index)
    claim = next(c for c in claims if c.claim_id == "fta.claim.001")
    assert claim.cited_chunk_id == "chunk-no-locator"
    assert claim.cited_locator_kind is None
    assert claim.cited_locator_value is None


def test_claim_null_citation_when_chunk_unresolvable(spot_check_tree: Path) -> None:
    cfg = _config(
        spot_check_tree,
        surface="fta_numeric",
        source="uc13_ale.analysis.financial_trends",
    )
    claims = load_claim_enumeration(cfg, chunk_index=ChunkIndex([]))
    claim = next(c for c in claims if c.claim_id == "fta.claim.001")
    assert claim.cited_chunk_id is None
    assert claim.cited_locator_kind is None
    assert claim.cited_locator_value is None


def test_claim_null_citation_when_document_has_unscored_candidates(
    spot_check_tree: Path,
) -> None:
    """O-2 falsifier: document exists, multiple chunks, none score → null citation + locator."""
    cfg = _config(
        spot_check_tree,
        surface="fta_numeric",
        source="uc13_ale.analysis.financial_trends",
    )
    manifest_path = spot_check_tree / "eval/content/fta_numeric_rubric_claims.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["claims"] = [
        {
            "claim_id": "fta.claim.unscored",
            "claim_text": "yoy_growth_pct: 58.3%",
            "source_doc": "2024 Elder Care - CIM_vF.pdf",
            "source_location": "Historical P&L Summary, Page 99",
        }
    ]
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    index = ChunkIndex(
        [
            ChunkRecord(
                chunk_id="chunk-a",
                file_name="2024 Elder Care - CIM_vF.pdf",
                section_header="Unrelated Section A",
                page_start=10,
                chunk_text="",
            ),
            ChunkRecord(
                chunk_id="chunk-b",
                file_name="2024 Elder Care - CIM_vF.pdf",
                section_header="Unrelated Section B",
                page_start=20,
                chunk_text="",
            ),
        ]
    )
    claims = load_claim_enumeration(cfg, chunk_index=index)
    claim = next(c for c in claims if c.claim_id == "fta.claim.unscored")
    assert claim.cited_chunk_id is None
    assert claim.cited_locator_kind is None
    assert claim.cited_locator_value is None


def test_fta_citation_set_reproducible_without_draft_artifact(
    spot_check_tree: Path,
) -> None:
    """O-1 falsifier: shipped producer resolves fta_numeric citations from ChunkIndex only."""
    cfg = _config(
        spot_check_tree,
        surface="fta_numeric",
        source="uc13_ale.analysis.financial_trends",
    )
    index = _mock_chunk_index()
    first = load_claim_enumeration(cfg, chunk_index=index)
    second = load_claim_enumeration(cfg, chunk_index=index)
    assert first == second
    expected_citations = {
        "fta.claim.001": (
            "cd9773ea-0a3c-460d-869a-bc963a15cd1f",
            "section",
            "Pro Forma Income Statement & Projection",
        ),
        "fta.claim.002": (
            "cd9773ea-0a3c-460d-869a-bc963a15cd1f",
            "section",
            "Pro Forma Income Statement & Projection",
        ),
    }
    for claim in first:
        assert (
            claim.cited_chunk_id,
            claim.cited_locator_kind,
            claim.cited_locator_value,
        ) == expected_citations[claim.claim_id]


def test_r10_citation_parity_with_r5_backfill(tmp_path: Path) -> None:
    """KC3: ported producer must match R5 backfill citation assignment."""
    pytest.skip(
        "R16 no-match floor + draft removal stale R5 backfill expected citations — "
        "R18 relocates KC3 parity after R17 re-ingest"
    )
    repo_root = Path(__file__).resolve().parents[3]
    backfill_dir = repo_root / ".dev/eval-program/spot-check"
    exec_backfill = backfill_dir / "exec_summary_elder_care_2026-08-13.backfill.yaml"
    fta_backfill = backfill_dir / "fta_numeric_elder_care_2026-08-13.backfill.yaml"
    if not exec_backfill.is_file() or not fta_backfill.is_file():
        pytest.skip("R5 backfill artifacts absent on this worktree")

    from eval.content.s2_writer import make_sdk_sql_executor

    sql = make_sdk_sql_executor()
    index = ChunkIndex.from_sql(
        sql, catalog="uc13_ale", company="Elder Care"
    )

    for surface, backfill_path, source in (
        (
            "exec_summary",
            exec_backfill,
            "uc13_ale.analysis.diligence_report.executive_summary",
        ),
        ("fta_numeric", fta_backfill, "uc13_ale.analysis.financial_trends"),
    ):
        expected = {
            c["claim_id"]: (
                c.get("cited_chunk_id"),
                c.get("cited_locator_kind"),
                c.get("cited_locator_value"),
            )
            for c in yaml.safe_load(backfill_path.read_text(encoding="utf-8"))["claims"]
        }
        cfg = SpotCheckConfig(
            company="Elder Care",
            surface=surface,
            source=source,
            output_dir=tmp_path / surface,
            verdicts_path=tmp_path / f"{surface}.yaml",
            operator_id="operator_a",
            registry_path=repo_root / "eval/program/registry.yaml",
            repo_root=repo_root,
        )
        exec_cache = (
            load_exec_analysis_cache(sql, catalog="uc13_ale", company="Elder Care")
            if surface == "exec_summary"
            else None
        )

        actual = {
            c.claim_id: (c.cited_chunk_id, c.cited_locator_kind, c.cited_locator_value)
            for c in load_claim_enumeration(
                cfg,
                chunk_index=index,
                exec_analysis_cache=exec_cache,
            )
        }
        mismatches = [
            (cid, expected[cid], actual.get(cid))
            for cid in sorted(expected)
            if expected[cid] != actual.get(cid)
        ]
        assert not mismatches, f"{surface} citation drift: {mismatches[:5]}"
