"""Hermetic pins for the 2026-08-31 FTA numeric persist-vs-resolve re-run (T9)."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
SPOT_CHECK = REPO / "eval" / "content" / "spot-check"
PERSIST = SPOT_CHECK / "fta_numeric_elder_care_2026-08-31.persist_vs_resolve.yaml"
PRESENTATION = SPOT_CHECK / "fta_numeric_elder_care_2026-08-31.presentation.yaml"

RETIRED_PREFIXES = ("027ec667", "cd9773ea", "b1feca18", "871ba744", "5fa7f39b")
BROKEN_PLACEHOLDER_NOW = "aee7745d-e270-4abf-8fc5-c60dd4f13bcc"
PAGE46_IDS = {f"fta.claim.{n:03d}" for n in list(range(62, 68)) + list(range(199, 205))}


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_persist_vs_resolve_covers_276_claims_on_post_m4_corpus() -> None:
    payload = _load(PERSIST)
    assert payload["surface"] == "fta_numeric"
    assert payload["company"] == "Elder Care"
    assert payload["corpus_chunk_count"] >= 55812
    assert len(payload["claims"]) == 276
    ids = [c["claim_id"] for c in payload["claims"]]
    assert len(set(ids)) == 276


def test_resolved_rows_do_not_cite_retired_or_broken_placeholder() -> None:
    """Falsifier: a resolved_* row that still cites 027ec667… / b1feca18… / aee7745d…."""
    payload = _load(PERSIST)
    for claim in payload["claims"]:
        cited = claim.get("current_cited_chunk_id") or ""
        assert not cited.startswith(RETIRED_PREFIXES), claim["claim_id"]
        if claim["status"].startswith("resolved"):
            assert cited != BROKEN_PLACEHOLDER_NOW, claim["claim_id"]
            assert claim["cites_retired_id"] is False, claim["claim_id"]
            assert claim["cites_broken_placeholder"] is False, claim["claim_id"]


def test_page46_family_all_resolved_relocation() -> None:
    payload = _load(PERSIST)
    page46 = [c for c in payload["claims"] if c["claim_id"] in PAGE46_IDS]
    assert len(page46) == 12
    for claim in page46:
        assert claim["prior_family"] == "page46_b1feca18_not_verbatim", claim["claim_id"]
        assert claim["status"] == "resolved_relocation", claim["claim_id"]
        assert claim["current_cited_chunk_id"] == payload["page46_now"]
        assert claim["current_verbatim"] is True


def test_presentation_packet_has_276_claims_and_proforma_sibling() -> None:
    packet = _load(PRESENTATION)
    assert packet["format"] == "spot_check_presentation_v1"
    assert packet["claim_count"] == 276
    assert len(packet["claims"]) == 276
    proforma = [
        c
        for c in packet["claims"]
        if c.get("source_location") == "Pro Forma Income Statement & Projection"
    ]
    assert proforma
    sibling = _load(PERSIST)["proforma_sibling_now"]
    for claim in proforma:
        assert claim["cited_chunk_id"] == sibling, claim["claim_id"]
