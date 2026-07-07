"""Structural contract for M-PHV2 record_e2e_linkage README subsection — T6."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_README = _REPO_ROOT / "eval" / "retrieval" / "README.md"
_HEADING = "### record_e2e_linkage invocations"
_SECOND_COMPANY_HEADING = "### Second company selection & run"
_PHV_HEADING = "## PHV validation"
_R02_HEADING = "## R-02 manual A/B"
_FROZEN_CLI_ONE_LINER = (
    "python -m eval.retrieval.scripts.record_e2e_linkage --run-id <...> "
    "--e2e-agent-id <...> --e2e-checklist-score <int> --e2e-checklist-total <int, default 18> "
    "--e2e-snapshot-table <FQN> --store-backend <sqlite|delta> --catalog <...> [--sqlite-path <path>]"
)
_HARNESS_CLI_ONE_LINER = (
    "python -m eval.retrieval.harness_cli run --store-backend <sqlite|delta> "
    "--run-type <...> --company-name <...> --catalog <...> "
    "--baseline-ref-run-id baseline_299063e87806 [--ablation-config <...>]"
)


def _phv_section() -> str:
    text = _README.read_text(encoding="utf-8")
    phv_start = text.index(_PHV_HEADING)
    r02_start = text.index(_R02_HEADING)
    return text[phv_start:r02_start]


def test_readme_contains_record_e2e_linkage_subsection_heading_verbatim() -> None:
    assert _HEADING in _README.read_text(encoding="utf-8")


def test_record_e2e_subsection_is_markdown_level3_under_phv_validation() -> None:
    """Falsifier: heading present only inside a code block would satisfy substring check."""
    section = _phv_section()
    for line in section.splitlines():
        if line.strip() == _HEADING:
            return
    raise AssertionError(f"No bare markdown level-3 line {_HEADING!r} in PHV validation block")


def test_record_e2e_subsection_follows_second_company_and_precedes_r02() -> None:
    text = _README.read_text(encoding="utf-8")
    second_idx = text.index(_SECOND_COMPANY_HEADING)
    record_idx = text.index(_HEADING)
    r02_idx = text.index(_R02_HEADING)
    assert second_idx < record_idx < r02_idx, (
        "T5 → T6 sequencing: second company, then record_e2e_linkage, then R-02 manual A/B"
    )


def test_record_e2e_documents_frozen_cli_surface_verbatim() -> None:
    section = _phv_section()
    assert _FROZEN_CLI_ONE_LINER in section


def test_record_e2e_fta_worked_example_uses_cell_12_and_total_18() -> None:
    section = _phv_section()
    assert "--e2e-agent-id fta" in section
    assert "<from Cell 12 re-score>" in section
    assert "--e2e-checklist-total 18" in section
    assert "financial_trends_eval_snapshot" in section


def test_record_e2e_legal_worked_example_uses_total_11() -> None:
    section = _phv_section()
    assert "--e2e-agent-id legal" in section
    assert "<from Cell 16 re-score>" in section
    assert "--e2e-checklist-total 11" in section
    assert "uc13_ale.analysis.legal" in section


def test_record_e2e_scoping_note_excludes_bma_cqa_kpi_qoe_profiler() -> None:
    """Falsifier: runbook documents record_e2e_linkage for harness-only agents."""
    section = _phv_section()
    assert "not** applicable to BMA, CQA, KPI, QoE, or Profiler" in section
    assert _HARNESS_CLI_ONE_LINER in section
    forbidden = (
        "--e2e-agent-id bma",
        "--e2e-agent-id cqa",
        "--e2e-agent-id kpi",
        "--e2e-agent-id qoe",
        "--e2e-agent-id profiler",
    )
    for phrase in forbidden:
        assert phrase not in section, f"runbook must not invent record_e2e_linkage for harness agents: {phrase!r}"


def test_record_e2e_does_not_invent_cli_flags() -> None:
    """Falsifier: undocumented flag strings in worked examples."""
    section = _phv_section()
    record_start = section.index(_HEADING)
    record_block = section[record_start:]
    assert "--e2e-checklist-total" in record_block
    assert "--vs-metadata-filters" not in record_block
    assert "--legal-checklist-score" not in record_block
