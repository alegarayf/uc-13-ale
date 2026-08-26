"""Hermetic pins on the generated Wave-4 trust statement (M8 T7 Flag-1 / Flag-2)."""

from __future__ import annotations

from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_GENERATED = _REPO_ROOT / "eval" / "program" / "trust_statement.md"
_T3_SPG_RUN = "20260826T171712Z-3975"


def _generated_text() -> str:
    return _GENERATED.read_text(encoding="utf-8")


def _rows() -> list[dict[str, object]]:
    text = _generated_text()
    start = text.index("```yaml\n") + len("```yaml\n")
    end = text.index("```", start)
    payload = yaml.safe_load(text[start:end])
    assert isinstance(payload, list)
    return payload


def _legal_register_row(company: str) -> dict[str, object]:
    matches = [
        row
        for row in _rows()
        if row.get("company") == company
        and row.get("layer") == "content_correctness"
        and row.get("surface") == "legal_register"
    ]
    assert len(matches) == 1, matches
    return matches[0]


def test_clearsulting_and_gkf_legal_register_remain_known_gap() -> None:
    """Flag-1: eliminates exemptions stay; regen must not flip these to attested/partial."""
    for company, reason in (("clearsulting", "corpus_absent"), ("gkf", "corpus_thin")):
        row = _legal_register_row(company)
        assert row["attestation"] == "known_gap"
        assert row["attestation"] not in {"attested", "partial"}
        assert row["reason"] == reason


def test_generated_trust_statement_has_no_title_case_gkf_spg() -> None:
    """Flag-2: dormant title-case inverse must not leak Gkf/Spg into the rollup."""
    text = _generated_text()
    assert "Gkf" not in text
    assert "Spg" not in text


def test_spg_legal_register_cites_t3_verifier_run() -> None:
    """Whole-catalog regen must surface T3's first SPG legal_register S2 evidence."""
    row = _legal_register_row("spg")
    assert row["attestation"] == "partial"
    refs = row.get("evidence_refs") or []
    assert f"s2_scores:{_T3_SPG_RUN}" in refs
