"""Static contract tests for M-RE1 architecture doc surfaces (T10)."""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ARCH = _REPO_ROOT / ".dev" / "architecture" / "rallyday"


def _arch_text(name: str) -> str:
    return (_ARCH / name).read_text(encoding="utf-8")


def test_inventory_semantic_search_returns_route_result_not_list_row():
    """Kill criterion: no stale semantic_search → list[Row] in inventory."""
    text = _arch_text("public-interface-inventory.md")
    semantic_rows = [
        line
        for line in text.splitlines()
        if "`semantic_search`" in line and "databricks/agents/shared/retrieval.py" in line
    ]
    assert semantic_rows, "semantic_search row missing from public-interface-inventory.md"
    assert all("RouteResult" in line for line in semantic_rows)
    assert not any("list[Row]" in line for line in semantic_rows)


def test_inventory_route_chunks_not_production_surface():
    """Kill criterion: Route A not listed as active production surface post-T3."""
    text = _arch_text("public-interface-inventory.md")
    route_rows = [
        line
        for line in text.splitlines()
        if "`route_chunks`" in line and line.strip().startswith("|")
    ]
    assert route_rows == [], f"route_chunks still listed as inventory surface: {route_rows}"


def test_inventory_includes_re2_eval_symbols():
    text = _arch_text("public-interface-inventory.md")
    for symbol in ("EvalHarness", "EvalStore", "IntentScopeResolver"):
        assert symbol in text


def test_module_map_lists_eval_retrieval_package():
    text = _arch_text("module-map.md")
    eval_row = next(
        line for line in text.splitlines() if line.startswith("| `eval/retrieval/`")
    )
    assert "EvalHarness" in eval_row or "harness.py" in eval_row
    assert "route_chunks.py" not in eval_row


def test_module_map_shared_row_excludes_route_chunks():
    text = _arch_text("module-map.md")
    shared_row = next(
        line for line in text.splitlines() if line.startswith("| `databricks/agents/shared`")
    )
    assert "route_chunks" not in shared_row


def test_data_contract_route_result_mode_vocab_post_t3():
    text = _arch_text("data-contract-registry.md")
    route_block = re.search(
        r"Contract:\s+RouteResult.*?Last changed:\s+2026-07-01",
        text,
        flags=re.DOTALL,
    )
    assert route_block is not None
    block = route_block.group(0)
    assert '"semantic"' in block and '"keyword"' in block and '"empty"' in block
    assert '"routed"' not in block
    assert "list[float]" in block or "scores: list[float]" in block


def test_known_coupling_surfaces_catalog_split_documented():
    text = _arch_text("known-coupling-surfaces.md")
    assert "uc13_ale" in text
    assert "_default_catalog()" in text or "uc13_ale" in text
    assert "route_chunks join keys" not in text


def test_architecture_changelog_records_m_re1_t10():
    text = _arch_text("changelog.md")
    assert "M-RE1" in text
    assert "route_chunks" in text.lower() or "Route A" in text
