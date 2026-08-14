from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from eval.retrieval.companies import UnnormalizableCompanySlugError
from eval.retrieval.errors import EvalError
from eval.retrieval.exemptions import (
    ExemptionValidationError,
    IntentExemption,
    load_exemptions,
    write_exemption,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMITTED_STORE = _REPO_ROOT / "eval" / "program" / "eval_exemptions.yaml"


def _sample_exemption(**overrides: object) -> IntentExemption:
    base = {
        "company": "Clearsulting",
        "intent_id": "legal.ip_privacy",
        "surface": "legal_register",
        "coverage": "eliminates",
        "reason": "corpus_absent",
        "corpus_evidence": {"legal_docs": 0},
        "approved_by": "operator",
    }
    base.update(overrides)
    return IntentExemption(**base)  # type: ignore[arg-type]


def test_roundtrip_write_then_load(tmp_path: Path) -> None:
    store = tmp_path / "eval_exemptions.yaml"
    store.write_text("schema_version: 1\nexemptions: []\n", encoding="utf-8")
    exemption = _sample_exemption()
    write_exemption(store, exemption)
    loaded = load_exemptions(store)
    assert len(loaded) == 1
    row = loaded[0]
    assert row.company == "clearsulting"
    assert row.intent_id == "legal.ip_privacy"
    assert row.surface == "legal_register"
    assert row.coverage == "eliminates"
    assert row.reason == "corpus_absent"
    assert row.corpus_evidence == {"legal_docs": 0}
    assert row.approved_by == "operator"


def test_write_rejects_unfoldable_company(tmp_path: Path) -> None:
    store = tmp_path / "eval_exemptions.yaml"
    store.write_text("schema_version: 1\nexemptions: []\n", encoding="utf-8")
    with pytest.raises(UnnormalizableCompanySlugError):
        write_exemption(store, _sample_exemption(company="---"))


def test_write_rejects_coverage_surface_mismatch(tmp_path: Path) -> None:
    store = tmp_path / "eval_exemptions.yaml"
    store.write_text("schema_version: 1\nexemptions: []\n", encoding="utf-8")
    with pytest.raises(ExemptionValidationError, match="coverage must be null"):
        write_exemption(
            store,
            _sample_exemption(surface=None, coverage="eliminates"),
        )
    with pytest.raises(ExemptionValidationError, match="coverage is required"):
        write_exemption(
            store,
            _sample_exemption(surface="legal_register", coverage=None),
        )


def test_committed_store_validates() -> None:
    payload = yaml.safe_load(_COMMITTED_STORE.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    loaded = load_exemptions(_COMMITTED_STORE)
    assert len(loaded) == 6
    assert all(row.company == "clearsulting" for row in loaded)
    legal = [row for row in loaded if row.intent_id.startswith("legal.")]
    assert len(legal) == 5
    assert all(row.reason == "corpus_absent" for row in legal)
    overlay = [row for row in loaded if row.intent_id == "kpi.retrieve_bench_and_capacity"]
    assert len(overlay) == 1
    assert overlay[0].reason == "overlay_mismatch"


def test_exemption_validation_error_subclasses_eval_error() -> None:
    assert issubclass(ExemptionValidationError, EvalError)


def test_surface_null_coverage_null_case_roundtrips(tmp_path: Path) -> None:
    store = tmp_path / "eval_exemptions.yaml"
    store.write_text("schema_version: 1\nexemptions: []\n", encoding="utf-8")
    write_exemption(
        store,
        _sample_exemption(
            surface=None,
            coverage=None,
            reason="overlay_mismatch",
            corpus_evidence={"note": "retrieval-only"},
        ),
    )
    row = load_exemptions(store)[0]
    assert row.surface is None
    assert row.coverage is None


def test_surface_narrows_case_roundtrips(tmp_path: Path) -> None:
    store = tmp_path / "eval_exemptions.yaml"
    store.write_text("schema_version: 1\nexemptions: []\n", encoding="utf-8")
    write_exemption(
        store,
        _sample_exemption(coverage="narrows", reason="corpus_thin"),
    )
    row = load_exemptions(store)[0]
    assert row.coverage == "narrows"


def test_load_rejects_invalid_reason(tmp_path: Path) -> None:
    store = tmp_path / "eval_exemptions.yaml"
    store.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "exemptions": [
                    {
                        "company": "clearsulting",
                        "intent_id": "legal.ip_privacy",
                        "surface": "legal_register",
                        "coverage": "eliminates",
                        "reason": "unknown_reason",
                        "corpus_evidence": {"legal_docs": 0},
                        "approved_by": "operator",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ExemptionValidationError, match="reason must be one of"):
        load_exemptions(store)


def test_write_appends_without_deduplication(tmp_path: Path) -> None:
    store = tmp_path / "eval_exemptions.yaml"
    store.write_text("schema_version: 1\nexemptions: []\n", encoding="utf-8")
    exemption = _sample_exemption()
    write_exemption(store, exemption)
    write_exemption(store, exemption)
    assert len(load_exemptions(store)) == 2
