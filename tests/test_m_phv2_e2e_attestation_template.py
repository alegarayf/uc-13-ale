"""Structural contract for M-PHV2 full E2E attestation template — T7."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TEMPLATE = _REPO_ROOT / ".dev" / "attestations" / "TEMPLATE_m-phv2-full-e2e-run.md"

pytestmark = pytest.mark.skipif(
    not _TEMPLATE.exists(),
    reason=f"gitignored attestation template not present in this checkout: {_TEMPLATE}",
)


def _template_text() -> str:
    return _TEMPLATE.read_text(encoding="utf-8")


def test_attestation_template_path_and_heading() -> None:
    text = _template_text()
    assert "M-PHV2 operator attestation" in text
    assert "Cell execution ledger (authoritative)" in text


def test_ledger_disambiguates_both_cell_11_variants() -> None:
    text = _template_text()
    assert "Cell 11 — Reset helpers" in text
    assert "Cell 11 (Business Model Agent)" in text
    assert "| 36 |" in text
    assert "| 42 |" in text


def test_ledger_disambiguates_both_cell_12_variants() -> None:
    text = _template_text()
    assert "Cell 12 — Full pipeline state summary" in text
    assert "Cell 12 (Financial Trends Agent)" in text
    assert "| 37 |" in text
    assert "| 46 |" in text


def test_item_15_scope_excludes_cell_19_and_orchestrator() -> None:
    text = _template_text()
    assert "index **57**" in text or "index 57" in text
    assert "Cell 18" in text
    assert "Cell 19" in text
    assert "out of item-15 scope" in text.lower() or "Out of item-15 scope" in text
    assert "| 58 |" in text
    assert "| 62 |" in text


def test_linear_path_last_step_is_cell_18_index_57() -> None:
    """Falsifier: ledger ends at Cell 17 or includes Cell 19 in the required path."""
    text = _template_text()
    last_row_match = re.search(
        r"\| 33 \| 57 \| Cell 18.*\| \*\*Required\*\*",
        text,
        re.DOTALL,
    )
    assert last_row_match, "Linear E2E path must terminate at step 33 / index 57 / Cell 18"


def test_per_cell_pass_fail_table_present() -> None:
    text = _template_text()
    assert "Per-cell execution record" in text
    assert "PASS / FAIL / SKIP" in text
