"""CI fixture validation for elder_care_slice.json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.retrieval.models import EvalFixtureSlice

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "elder_care_slice.json"
)


def test_elder_care_slice_fixture_loads_and_validates():
    assert FIXTURE_PATH.exists(), "elder_care_slice.json must be committed for T9"
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    fixture = EvalFixtureSlice.model_validate(payload)
    assert fixture.catalog == "uc13_ale"
    assert fixture.company_name == "Elder Care"
    assert len(fixture.intents) >= 3
    assert len(fixture.chunks) >= 3


def test_elder_care_slice_chunk_ids_cover_gold_references():
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    fixture = EvalFixtureSlice.model_validate(payload)
    chunk_ids = {chunk.chunk_id for chunk in fixture.chunks}
    for label in fixture.intents:
        for chunk_id in label.positive_chunk_ids:
            assert chunk_id in chunk_ids, f"missing chunk row for positive {chunk_id}"
        for chunk_id in label.negative_chunk_ids or []:
            assert chunk_id in chunk_ids, f"missing chunk row for negative {chunk_id}"


def test_elder_care_slice_ready_intents_match_committed_gold():
    """Falsifier: fixture drift from gold_labels/elder_care.yaml ready rows."""
    from eval.retrieval.gold.bootstrap import load_gold_labels

    gold_path = Path(__file__).resolve().parents[1] / "gold_labels" / "elder_care.yaml"
    gold_by_intent = {row.intent_id: row for row in load_gold_labels(gold_path)}
    fixture = EvalFixtureSlice.model_validate(
        json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    )
    fixture_by_intent = {row.intent_id: row for row in fixture.intents}

    for intent_id, gold in gold_by_intent.items():
        if gold.gold_status != "ready":
            continue
        assert intent_id in fixture_by_intent, f"ready intent missing from slice: {intent_id}"
        fix = fixture_by_intent[intent_id]
        assert fix.positive_chunk_ids == gold.positive_chunk_ids
        assert fix.negative_chunk_ids == gold.negative_chunk_ids
