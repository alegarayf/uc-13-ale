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
    SpotCheckConfig,
    SpotCheckIngestionError,
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
    assert claims[0].cited_locator_kind == "section"
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
