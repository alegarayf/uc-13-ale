"""Structural contract for M-PHV2 R-02 manual A/B README hub — T3."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_README = _REPO_ROOT / "eval" / "retrieval" / "README.md"
_HEADING = "## R-02 manual A/B"
_CHARTER_HUB_SUFFIX = "R-02 manual A/B"
_PHV_HEADING = "## PHV validation"
_BASELINE_REF = "baseline_299063e87806"


def test_readme_contains_r02_manual_ab_heading_verbatim() -> None:
    text = _README.read_text(encoding="utf-8")
    assert _HEADING in text


def test_r02_heading_matches_charter_hub_registry_byte_for_byte() -> None:
    """Charter §4 hub: eval/retrieval/README.md § R-02 manual A/B."""
    assert _HEADING == f"## {_CHARTER_HUB_SUFFIX}"


def test_r02_heading_is_markdown_level2_not_fenced() -> None:
    """Falsifier: heading present only inside a code block would satisfy substring check."""
    for line in _README.read_text(encoding="utf-8").splitlines():
        if line.strip() == _HEADING:
            return
    raise AssertionError(f"No bare markdown level-2 line {_HEADING!r} in {_README}")


def test_r02_section_follows_phv_validation_and_precedes_related_clis() -> None:
    text = _README.read_text(encoding="utf-8")
    phv_idx = text.index(_PHV_HEADING)
    r02_idx = text.index(_HEADING)
    related_idx = text.index("## Related CLIs")
    assert phv_idx < r02_idx < related_idx, (
        "T2 → T3 sequencing: PHV validation, then R-02 manual A/B, then Related CLIs"
    )


def test_r02_documents_ablation_dispatch_precondition_error_not_cli_flag() -> None:
    """Falsifier: missing PreconditionError note or harness_cli presented as kwarg carrier."""
    section = _README.read_text(encoding="utf-8").split(_HEADING, 1)[1].split("## Related CLIs", 1)[0]
    assert "ablation_arm_to_merge_rank_mode" in section
    assert "PreconditionError" in section
    assert "vs_filter_pushdown" in section
    assert "Do not invent a CLI flag" in section
    assert "retrieval_dispatch" in section


def test_r02_documents_baseline_ref_and_decision_14_numeric_bar() -> None:
    section = _README.read_text(encoding="utf-8").split(_HEADING, 1)[1].split("## Related CLIs", 1)[0]
    assert _BASELINE_REF in section
    assert "5 percentage points" in section
    assert "Aggregate recall@10" in section
    assert "must not be the operator who ran the A/B" in section
    assert "activation does not proceed to M-PHV4" in section
