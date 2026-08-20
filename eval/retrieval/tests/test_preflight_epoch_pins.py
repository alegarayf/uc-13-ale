"""Unit tests for epoch-pin preflight — M1 W3 T2."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from eval.retrieval.errors import PreconditionError, RunNotFoundError
from eval.retrieval.gold.bootstrap import load_gold_labels
from eval.retrieval.harness import (
    compute_gold_snapshot,
    compute_registry_hash,
    default_registry_path,
)
from eval.retrieval.models import HarnessReport, HarnessRun
from eval.retrieval.scripts.preflight_epoch_pins import (
    PINNED_EPOCH_BASELINES,
    check_epoch_pins,
    format_epoch_pin_line,
)

ELDER_CARE_GOLD = Path("eval/retrieval/gold_labels/elder_care.yaml")


class _ManifestStore:
    def __init__(self, manifests: dict[str, HarnessRun]) -> None:
        self._manifests = manifests

    def get_run(self, run_id: str) -> HarnessReport:
        manifest = self._manifests.get(run_id)
        if manifest is None:
            raise RunNotFoundError(f"run_id not found: {run_id}")
        return HarnessReport(manifest=manifest, results=[], deltas=None)


def _current_elder_care_pins() -> tuple[str, str]:
    registry_hash = compute_registry_hash(default_registry_path())
    gold_labels = [
        label
        for label in load_gold_labels(ELDER_CARE_GOLD)
        if label.company_name == "Elder Care" and label.catalog == "uc13_ale"
    ]
    gold_snapshot = compute_gold_snapshot(gold_labels)
    return gold_snapshot, registry_hash


def _baseline_manifest(
    *,
    run_id: str,
    registry_hash: str,
    gold_snapshot: str,
    run_type: str = "baseline",
    harness_status: str = "complete",
) -> HarnessRun:
    created = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)
    return HarnessRun(
        run_id=run_id,
        run_type=run_type,  # type: ignore[arg-type]
        company_name="Elder Care",
        catalog="uc13_ale",
        ingestion_snapshot="uc13_ale:35034:2026-08-19",
        registry_hash=registry_hash,
        gold_snapshot=gold_snapshot,
        affected_intents=["fta.opex.q1_financial_statements"],
        gated_intents=["fta.opex.q1_financial_statements"],
        store_backend="sqlite",
        harness_status=harness_status,  # type: ignore[arg-type]
        intent_count=1,
        created_at=created,
        completed_at=created if harness_status == "complete" else None,
    )


def test_check_epoch_pins_all_match_for_aligned_baseline() -> None:
    gold_snapshot, registry_hash = _current_elder_care_pins()
    run_id = PINNED_EPOCH_BASELINES["Elder Care"]
    store = _ManifestStore(
        {run_id: _baseline_manifest(run_id=run_id, registry_hash=registry_hash, gold_snapshot=gold_snapshot)}
    )

    result = check_epoch_pins(
        store,
        pins={"Elder Care": run_id},
        gold_path_for_company=lambda _company: ELDER_CARE_GOLD,
    )[0]

    assert result.baseline_valid is True
    assert result.gold_snapshot_match is True
    assert result.registry_hash_match is True
    assert result.harness_status == "complete"


def test_check_epoch_pins_detects_gold_snapshot_drift() -> None:
    _, registry_hash = _current_elder_care_pins()
    run_id = PINNED_EPOCH_BASELINES["Elder Care"]
    store = _ManifestStore(
        {
            run_id: _baseline_manifest(
                run_id=run_id,
                registry_hash=registry_hash,
                gold_snapshot="deadbeef" * 8,
            )
        }
    )

    result = check_epoch_pins(
        store,
        pins={"Elder Care": run_id},
        gold_path_for_company=lambda _company: ELDER_CARE_GOLD,
    )[0]

    assert result.registry_hash_match is True
    assert result.gold_snapshot_match is False
    assert result.baseline_valid is True


def test_check_epoch_pins_detects_registry_hash_drift() -> None:
    gold_snapshot, _ = _current_elder_care_pins()
    run_id = PINNED_EPOCH_BASELINES["Elder Care"]
    store = _ManifestStore(
        {
            run_id: _baseline_manifest(
                run_id=run_id,
                registry_hash="cafebabe" * 8,
                gold_snapshot=gold_snapshot,
            )
        }
    )

    result = check_epoch_pins(
        store,
        pins={"Elder Care": run_id},
        gold_path_for_company=lambda _company: ELDER_CARE_GOLD,
    )[0]

    assert result.gold_snapshot_match is True
    assert result.registry_hash_match is False


def test_check_epoch_pins_incomplete_baseline_not_valid() -> None:
    gold_snapshot, registry_hash = _current_elder_care_pins()
    run_id = PINNED_EPOCH_BASELINES["Elder Care"]
    store = _ManifestStore(
        {
            run_id: _baseline_manifest(
                run_id=run_id,
                registry_hash=registry_hash,
                gold_snapshot=gold_snapshot,
                harness_status="incomplete",
            )
        }
    )

    result = check_epoch_pins(
        store,
        pins={"Elder Care": run_id},
        gold_path_for_company=lambda _company: ELDER_CARE_GOLD,
    )[0]

    assert result.harness_status == "incomplete"
    assert result.baseline_valid is False


def test_check_epoch_pins_wrong_run_type_not_valid() -> None:
    gold_snapshot, registry_hash = _current_elder_care_pins()
    run_id = PINNED_EPOCH_BASELINES["Elder Care"]
    store = _ManifestStore(
        {
            run_id: _baseline_manifest(
                run_id=run_id,
                registry_hash=registry_hash,
                gold_snapshot=gold_snapshot,
                run_type="enhancement",
            )
        }
    )

    result = check_epoch_pins(
        store,
        pins={"Elder Care": run_id},
        gold_path_for_company=lambda _company: ELDER_CARE_GOLD,
    )[0]

    assert result.run_type == "enhancement"
    assert result.baseline_valid is False


def test_check_epoch_pins_missing_run_reports_not_found() -> None:
    result = check_epoch_pins(
        _ManifestStore({}),
        pins={"Elder Care": "baseline_missing"},
        gold_path_for_company=lambda _company: ELDER_CARE_GOLD,
    )[0]

    assert result.harness_status == "not_found"
    assert result.baseline_valid is False
    assert result.gold_snapshot_match is False
    assert result.registry_hash_match is False
    assert result.stored_gold_snapshot is None


def test_format_epoch_pin_line_matches_contract() -> None:
    result = check_epoch_pins(
        _ManifestStore({}),
        pins={"Elder Care": "baseline_2fa3a9056bd0"},
        gold_path_for_company=lambda _company: ELDER_CARE_GOLD,
    )[0]
    line = format_epoch_pin_line(result)

    assert line.startswith("company=Elder Care baseline_run_id=baseline_2fa3a9056bd0")
    assert "harness_status=not_found" in line
    assert "gold_snapshot_match=False" in line
    assert "registry_hash_match=False" in line
    assert result.current_gold_snapshot
    assert result.current_registry_hash


def test_check_epoch_pins_raises_when_gold_labels_missing_for_company(
    tmp_path: Path,
) -> None:
    gold_snapshot, registry_hash = _current_elder_care_pins()
    empty_gold = tmp_path / "empty.yaml"
    empty_gold.write_text("[]\n", encoding="utf-8")
    store = _ManifestStore(
        {
            "baseline_2fa3a9056bd0": _baseline_manifest(
                run_id="baseline_2fa3a9056bd0",
                registry_hash=registry_hash,
                gold_snapshot=gold_snapshot,
            )
        }
    )

    with pytest.raises(PreconditionError, match="no gold labels"):
        check_epoch_pins(
            store,
            pins={"Elder Care": "baseline_2fa3a9056bd0"},
            gold_path_for_company=lambda _company: empty_gold,
        )
