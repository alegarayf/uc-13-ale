"""Hermetic tests for rung-3 spot-check tooling (T4 / §12.1)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from eval.content.s2_writer import S2Writer
from eval.retrieval.companies import canonical_company_slug
from eval.content.spot_check import (
    ChunkIndex,
    ChunkRecord,
    LOCATION_CHUNK_OVERRIDE,
    SpotCheckConfig,
    SpotCheckIngestionError,
    _CACHE_FREE_TRUNCATION_SOURCES,
    exec_claim_source,
    load_claim_enumeration,
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
    (root / "eval/program").mkdir(parents=True)
    (root / "eval/program/registry.yaml").write_text(
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
    company: str = "Elder Care",
    surface: str = "exec_summary",
    source: str = "uc13_ale.analysis.diligence_report.executive_summary",
    output_dir: Path | None = None,
    verdicts_path: Path | None = None,
) -> SpotCheckConfig:
    out = output_dir or (root / ".dev/eval-program/spot-check")
    slug = canonical_company_slug(company)
    verdicts = verdicts_path or (out / f"{surface}_{slug}.verdicts.yaml")
    return SpotCheckConfig(
        company=company,
        surface=surface,
        source=source,
        output_dir=out,
        verdicts_path=verdicts,
        operator_id="operator_a",
        registry_path=root / "eval/program/registry.yaml",
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
            registry_path=spot_check_tree / "eval/program/registry.yaml",
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
        (spot_check_tree / "eval/program/registry.yaml").read_text(encoding="utf-8")
    )
    for item in registry["items"]:
        if item["id"] == "CHK-26a":
            item["rung_assignments"]["exec_summary"] = "deterministic"
    (spot_check_tree / "eval/program/registry.yaml").write_text(
        yaml.safe_dump(registry), encoding="utf-8"
    )
    cfg = _config(spot_check_tree)

    with pytest.raises(ValueError, match="expected 'human'"):
        prepare_spot_check(cfg)


def test_prepare_spot_check_halts_on_rung2_registry_assignment(
    spot_check_tree: Path,
) -> None:
    registry = yaml.safe_load(
        (spot_check_tree / "eval/program/registry.yaml").read_text(encoding="utf-8")
    )
    for item in registry["items"]:
        if item["id"] == "CHK-26a":
            item["rung_assignments"]["exec_summary"] = "judge"
    (spot_check_tree / "eval/program/registry.yaml").write_text(
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
    """O-1 override-branch falsifier: LOCATION_CHUNK_OVERRIDE resolves citations without scoring."""
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


def _scored_branch_chunk_index() -> ChunkIndex:
    """Multi-candidate index where only the winner scores via section-pattern term."""
    return ChunkIndex(
        [
            ChunkRecord(
                chunk_id="chunk-scored-winner",
                file_name="2024 Elder Care - CIM_vF.pdf",
                section_header="Revenue Analysis & Projections",
                page_start=99,
                chunk_text="winner body",
            ),
            ChunkRecord(
                chunk_id="chunk-scored-loser",
                file_name="2024 Elder Care - CIM_vF.pdf",
                section_header="Unrelated Section",
                page_start=10,
                chunk_text="loser body",
            ),
        ]
    )


def test_fta_citation_resolves_via_general_scoring_branch(
    spot_check_tree: Path,
) -> None:
    """O-1 general-scoring falsifier: multi-candidate lookup via page/section scoring."""
    source_location = "Section: Revenue Analysis"
    assert source_location not in LOCATION_CHUNK_OVERRIDE

    cfg = _config(
        spot_check_tree,
        surface="fta_numeric",
        source="uc13_ale.analysis.financial_trends",
    )
    manifest_path = spot_check_tree / "eval/content/fta_numeric_rubric_claims.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["claims"] = [
        {
            "claim_id": "fta.claim.scored",
            "claim_text": "yoy_growth_pct: 58.3%",
            "source_doc": "2024 Elder Care - CIM_vF.pdf",
            "source_location": source_location,
        }
    ]
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    index = _scored_branch_chunk_index()
    claims = load_claim_enumeration(cfg, chunk_index=index)
    claim = next(c for c in claims if c.claim_id == "fta.claim.scored")

    winner = index.record("chunk-scored-winner")
    assert winner is not None
    assert claim.cited_chunk_id == winner.chunk_id
    assert claim.cited_locator_kind == "section"
    assert claim.cited_locator_value == winner.section_header


def test_exec_claim_source_elder_care_uses_static_map() -> None:
    """Elder Care regression: static PDF map wins over empty cache."""
    doc, loc = exec_claim_source("exec.claim.001", {}, company_slug="elder_care")
    assert doc == "2024 Elder Care - CIM_vF.pdf"
    assert loc == "Elder Care by the Numbers"


def test_exec_claim_source_clearsulting_resolves_from_cache() -> None:
    """Multi-company: non-Elder Care resolves from analysis cache, not static map."""
    cache = {
        "top_10_issues_json": [
            {
                "rank": 1,
                "citations": ["Clearsulting CIM 2024.pdf"],
            }
        ],
        "addback_ledger_json": [
            {
                "description": "[G] Management addback",
                "source_doc": "Clearsulting QoE.xlsx",
                "source_location": "Addbacks",
            }
        ],
    }
    doc, loc = exec_claim_source("exec.claim.038", cache, company_slug="clearsulting")
    assert doc == "Clearsulting CIM 2024.pdf"
    assert loc is None

    doc, loc = exec_claim_source("exec.claim.014", cache, company_slug="clearsulting")
    assert doc == "Clearsulting QoE.xlsx"
    assert loc == "Addbacks"


def test_exec_claim_source_non_elder_care_skips_hardcoded_elder_docs() -> None:
    """Falsifier: non-Elder Care must not emit Elder Care-only hardcoded doc names."""
    cache: dict[str, object] = {}
    doc, _loc = exec_claim_source("exec.claim.001", cache, company_slug="clearsulting")
    assert doc is None

    doc, _loc = exec_claim_source("exec.claim.019", cache, company_slug="clearsulting")
    assert doc is None
    assert "Elder Care" not in str(doc)


def test_load_claim_enumeration_exec_summary_uses_company_cache(
    spot_check_tree: Path,
) -> None:
    """Integration: exec_summary citations derive from cache for non-Elder Care."""
    cfg = _config(spot_check_tree, company="Clearsulting")
    cache = {
        "top_10_issues_json": [
            {"rank": 1, "citations": ["Clearsulting CIM 2024.pdf"]},
        ],
    }
    manifest_path = spot_check_tree / "eval/content/exec_summary_rubric_claims.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["claims"] = [
        {
            "section": "Issues",
            "claim_id": "exec.claim.038",
            "claim_text": "Top issue one.",
        }
    ]
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    claims = load_claim_enumeration(cfg, exec_analysis_cache=cache)
    assert len(claims) == 1
    assert claims[0].source_doc == "Clearsulting CIM 2024.pdf"


_CLAIM_009_CHUNK_ID = "chunk-009-diligence-adjusted"
_FETCHED_CHUNK_BODY = (
    "Diligence Adjusted Income Statement full numeric body including 9239 and 19.9%."
)


class _FetchTextSqlExecutor:
    """Warehouse stub that answers ``fetch_text`` with full ``chunk_text``."""

    def __init__(self, texts: dict[str, str]) -> None:
        self._texts = texts
        self.statements: list[str] = []

    def __call__(self, statement: str) -> list[list[str]]:
        self.statements.append(statement)
        return [
            [cid, text] for cid, text in self._texts.items() if cid in statement
        ]


def _write_truncation_row_manifest(root: Path) -> None:
    """exec.claim.009 (in the cache-free table) plus unresolved exec.claim.001."""
    payload = {
        "schema_version": 1,
        "claim_count": 2,
        "claims": [
            {
                "section": "Financial Picture",
                "claim_id": "exec.claim.009",
                "claim_text": (
                    "Pro Forma Adjusted EBITDA was $9,239K representing a "
                    "19.9% margin on a pro forma basis."
                ),
            },
            {
                "section": "Business Overview",
                "claim_id": "exec.claim.001",
                "claim_text": "Example claim one.",
            },
        ],
    }
    (root / "eval/content/exec_summary_rubric_claims.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def _claim_009_index(
    *,
    sql_executor: _FetchTextSqlExecutor | None = None,
    chunk_text: str = "",
) -> ChunkIndex:
    return ChunkIndex(
        [
            ChunkRecord(
                chunk_id=_CLAIM_009_CHUNK_ID,
                file_name="2024 Elder Care - CIM_vF.pdf",
                section_header="Diligence Adjusted Income Statement",
                page_start=42,
                chunk_text=chunk_text,
            )
        ],
        sql_executor=sql_executor,
        catalog="uc13_ale",
        company="Elder Care",
    )


def test_prepare_spot_check_packet_carries_fetched_chunk_text(
    spot_check_tree: Path,
) -> None:
    """F-6: prepared YAML carries post-fetch_text chunk_text for a resolved claim."""
    _write_truncation_row_manifest(spot_check_tree)
    cfg = _config(spot_check_tree)
    executor = _FetchTextSqlExecutor({_CLAIM_009_CHUNK_ID: _FETCHED_CHUNK_BODY})
    index = _claim_009_index(sql_executor=executor, chunk_text="")

    result = prepare_spot_check(cfg, chunk_index=index)
    payload = yaml.safe_load(result.packet_path.read_text(encoding="utf-8"))
    by_id = {row["claim_id"]: row for row in payload["claims"]}

    resolved = by_id["exec.claim.009"]
    assert resolved["cited_chunk_id"] == _CLAIM_009_CHUNK_ID
    assert resolved["chunk_text"] == _FETCHED_CHUNK_BODY
    assert any("SELECT" in stmt and "chunk_text" in stmt for stmt in executor.statements)
    assert _CLAIM_009_CHUNK_ID in executor.statements[0]

    unresolved = by_id["exec.claim.001"]
    assert unresolved["cited_chunk_id"] is None
    assert unresolved["chunk_text"] is None


def test_cache_free_truncation_sources_reachable_on_prepare_without_cache(
    spot_check_tree: Path,
) -> None:
    """F-5: prepare(chunk_index=..., no cache) consults _CACHE_FREE_TRUNCATION_SOURCES."""
    assert frozenset(_CACHE_FREE_TRUNCATION_SOURCES) == frozenset(
        {
            "exec.claim.008",
            "exec.claim.009",
            "exec.claim.010",
            "exec.claim.018",
        }
    )
    _write_truncation_row_manifest(spot_check_tree)
    cfg = _config(spot_check_tree)
    index = _claim_009_index(chunk_text="preloaded body")

    result = prepare_spot_check(cfg, chunk_index=index)
    claim = next(c for c in result.claims if c.claim_id == "exec.claim.009")
    expected_doc, expected_loc = _CACHE_FREE_TRUNCATION_SOURCES["exec.claim.009"]
    assert claim.source_doc == expected_doc
    assert claim.source_location == expected_loc
    assert claim.cited_chunk_id == _CLAIM_009_CHUNK_ID
    unresolved = next(c for c in result.claims if c.claim_id == "exec.claim.001")
    assert unresolved.source_doc is None
    assert unresolved.cited_chunk_id is None

