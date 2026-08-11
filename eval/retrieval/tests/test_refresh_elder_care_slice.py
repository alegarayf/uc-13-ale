"""Hermetic tests for refresh_elder_care_slice helpers (operator script seam)."""

from __future__ import annotations

from pathlib import Path

import pytest

from eval.retrieval.errors import PreconditionError
from eval.retrieval.models import GoldLabel
from eval.retrieval.scripts.refresh_elder_care_slice import (
    EXPECTED_GOLD_METHOD,
    SLICE_INTENT_IDS,
    assert_slice_gold_methods,
    build_fixture_slice,
    build_mock_vs_scores,
    collect_slice_chunk_ids,
    load_slice_labels,
)


def _sample_label(
    intent_id: str,
    *,
    positives: list[str],
    method: str = EXPECTED_GOLD_METHOD,
) -> GoldLabel:
    return GoldLabel(
        intent_id=intent_id,
        company_name="Elder Care",
        catalog="uc13_ale",
        gold_status="ready",
        positive_chunk_ids=positives,
        gold_method=method,  # type: ignore[arg-type]
        ingestion_snapshot="uc13_ale:55812:2026-08-11",
        confidence="high",
    )


def test_load_slice_labels_reads_committed_gold():
    gold_path = Path(__file__).resolve().parents[1] / "gold_labels" / "elder_care.yaml"
    labels = load_slice_labels(gold_path)
    assert [label.intent_id for label in labels] == list(SLICE_INTENT_IDS)
    assert all(label.gold_method == EXPECTED_GOLD_METHOD for label in labels)


def test_assert_slice_gold_methods_halts_on_method_change():
    labels = [_sample_label("fta.opex.q3_projected_financials", positives=["a"], method="filename_closure")]
    with pytest.raises(PreconditionError, match="gold_method"):
        assert_slice_gold_methods(labels)


def test_collect_slice_chunk_ids_preserves_first_seen_order():
    labels = [
        _sample_label("fta.opex.q3_projected_financials", positives=["a", "b"]),
        _sample_label("legal.contracts_vendors_platform", positives=["b", "c"]),
    ]
    assert collect_slice_chunk_ids(labels) == ["a", "b", "c"]


def test_build_fixture_slice_fails_when_live_rows_missing():
    labels = [_sample_label("fta.opex.q3_projected_financials", positives=["missing-id"])]
    with pytest.raises(PreconditionError, match="missing from live corpus"):
        build_fixture_slice(labels, [])


def test_build_fixture_slice_has_no_35104_epoch_strings():
    labels = [
        _sample_label("fta.opex.q3_projected_financials", positives=["id-1"]),
        _sample_label("legal.contracts_vendors_platform", positives=["id-2"]),
        _sample_label("cqa.retrieve_customer_concentration", positives=["id-3"]),
    ]
    rows = [
        {
            "chunk_id": "id-1",
            "file_name": "CIM.pdf",
            "section_header": "Historical P&L",
            "page_start": 45,
            "source_type": "text",
            "priority_tier": 1,
            "chunk_text": "Revenue trend detail.",
        },
        {
            "chunk_id": "id-2",
            "file_name": "MSA.pdf",
            "section_header": "Vendor terms",
            "page_start": 2,
            "source_type": "text",
            "priority_tier": 1,
            "chunk_text": "Platform agreement.",
        },
        {
            "chunk_id": "id-3",
            "file_name": "CIM.pdf",
            "section_header": "Customers",
            "page_start": 12,
            "source_type": "table",
            "priority_tier": 2,
            "chunk_text": "Top customer mix.",
        },
    ]
    fixture = build_fixture_slice(labels, rows)
    payload = fixture.model_dump(mode="json")
    encoded = str(payload)
    assert "35104" not in encoded
    assert fixture.ingestion_snapshot == "uc13_ale:55812:2026-08-11"


def test_build_mock_vs_scores_top_five_only():
    positives = [f"id-{idx}" for idx in range(8)]
    labels = [_sample_label("fta.opex.q3_projected_financials", positives=positives)]
    scores = build_mock_vs_scores(labels)
    assert list(scores["fta.opex.q3_projected_financials"]) == positives[:5]
