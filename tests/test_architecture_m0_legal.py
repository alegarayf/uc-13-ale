"""Static contract tests for M0 architecture doc surfaces (T5)."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ARCH = _REPO_ROOT / ".dev" / "architecture" / "rallyday"


def _arch_text(name: str) -> str:
    return (_ARCH / name).read_text(encoding="utf-8")


def test_data_contract_registry_includes_analysis_legal():
    text = _arch_text("data-contract-registry.md")
    assert "uc13_ale.analysis.legal" in text
    assert "legal_contracts" in text
    assert "compat VIEW" in text


def test_public_interface_inventory_legal_agent_and_extraction_endpoint():
    text = _arch_text("public-interface-inventory.md")
    assert "LegalContractsAgent" in text
    assert "legal_contracts_agent.main" in text
    assert "extraction_endpoint" in text


def test_module_map_keeps_legal_contracts_agent_not_renamed_module():
    """Falsifier: workstreams row must bind legal_contracts_agent.py, not legal_agent.py."""
    text = _arch_text("module-map.md")
    workstreams_row = next(
        line for line in text.splitlines() if line.startswith("| `databricks/agents/workstreams`")
    )
    assert "legal_contracts_agent.py" in workstreams_row
    assert "legal_agent.py" not in workstreams_row


def test_known_coupling_surfaces_table_view_migration_and_cqa_optional():
    text = _arch_text("known-coupling-surfaces.md")
    assert "analysis.legal" in text
    assert "legal_contracts" in text
    assert "contract_trigger_list" in text


def test_architecture_changelog_records_m0_and_a2_rename_waiver():
    text = _arch_text("changelog.md")
    assert "M0" in text
    assert "A2 rename waiver" in text


def test_claude_md_documents_analysis_legal_and_compat_view():
    text = (_REPO_ROOT / "databricks" / "CLAUDE.md").read_text(encoding="utf-8")
    assert "analysis.legal" in text
    assert "legal_contracts" in text
    assert "compat VIEW" in text
