"""Structural contract for M-PHV2 PHV validation README section — T2."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_README = _REPO_ROOT / "eval" / "retrieval" / "README.md"
_HEADING = "## PHV validation"


def test_readme_contains_phv_validation_heading_verbatim() -> None:
    text = _README.read_text(encoding="utf-8")
    assert _HEADING in text


def test_phv_validation_heading_is_markdown_level2_not_fenced() -> None:
    """Falsifier: heading present only inside a code block would satisfy substring check."""
    for line in _README.read_text(encoding="utf-8").splitlines():
        if line.strip() == _HEADING:
            return
    raise AssertionError(f"No bare markdown level-2 line {_HEADING!r} in {_README}")


def test_phv_validation_section_precedes_related_clis() -> None:
    text = _README.read_text(encoding="utf-8")
    phv_idx = text.index(_HEADING)
    related_idx = text.index("## Related CLIs")
    assert phv_idx < related_idx, "PHV validation must be inserted before Related CLIs (T2 anchor)"
