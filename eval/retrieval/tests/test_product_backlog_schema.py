"""Spec §4 / T2 — hermetic validation for eval/program/product_backlog.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKLOG_PATH = REPO_ROOT / "eval" / "program" / "product_backlog.yaml"

SURFACES = frozenset(
    {"legal_register", "exec_summary", "fta_numeric", "retrieval", "ingest", "agent"}
)
KINDS = frozenset(
    {
        "claim_failure",
        "extraction_depth",
        "retrieval_scope_gap",
        "corpus_gap",
        "measurement_caveat",
    }
)
SEVERITIES = frozenset({"high", "medium", "low"})
FIX_LANES = frozenset({"product", "eval", "ops"})
REQUIRED_ITEM_KEYS = frozenset(
    {
        "id",
        "company",
        "surface",
        "kind",
        "severity",
        "summary",
        "evidence_refs",
        "fix_lane",
        "closes_when",
    }
)


def _load_backlog() -> dict[str, Any]:
    return yaml.safe_load(BACKLOG_PATH.read_text(encoding="utf-8"))


def _is_repo_path_ref(ref: str) -> bool:
    if ref.startswith(("registry:", "trust:", "s2_scores:", "baseline_")):
        return False
    if ref.startswith("claim.") or ref.startswith("fta.claim."):
        return False
    return "/" in ref or ref.endswith((".md", ".yaml", ".yml", ".py", ".json"))


def _evidence_ref_resolves(ref: str) -> bool:
    if not _is_repo_path_ref(ref):
        return True
    return (REPO_ROOT / ref).is_file()


def validate_product_backlog(backlog: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if backlog.get("schema_version") != 1:
        errors.append("schema_version must be 1")

    items = backlog.get("items") or []
    if not items:
        errors.append("items must be non-empty")
        return errors

    ids = [item.get("id") for item in items]
    if len(ids) != len(set(ids)):
        errors.append("item id uniqueness violated")

    elder_care_with_refs = 0
    for item in items:
        item_id = item.get("id", "<missing-id>")
        missing = REQUIRED_ITEM_KEYS - set(item)
        if missing:
            errors.append(f"{item_id}: missing keys {sorted(missing)}")
            continue

        if item["company"] != "elder_care":
            errors.append(f"{item_id}: company must be elder_care in this ledger slice")
        if item["surface"] not in SURFACES:
            errors.append(f"{item_id}: invalid surface {item['surface']!r}")
        if item["kind"] not in KINDS:
            errors.append(f"{item_id}: invalid kind {item['kind']!r}")
        if item["severity"] not in SEVERITIES:
            errors.append(f"{item_id}: invalid severity {item['severity']!r}")
        if item["fix_lane"] not in FIX_LANES:
            errors.append(f"{item_id}: invalid fix_lane {item['fix_lane']!r}")
        if not item["evidence_refs"]:
            errors.append(f"{item_id}: evidence_refs must be non-empty")
        if not str(item["summary"]).strip():
            errors.append(f"{item_id}: summary must be non-empty")
        if not str(item["closes_when"]).strip():
            errors.append(f"{item_id}: closes_when must be non-empty")

        for ref in item["evidence_refs"]:
            if not _evidence_ref_resolves(str(ref)):
                errors.append(f"{item_id}: evidence_ref does not resolve: {ref!r}")

        if item["company"] == "elder_care" and item["evidence_refs"]:
            elder_care_with_refs += 1

    if elder_care_with_refs < 3:
        errors.append(
            f"expected >=3 elder_care items with evidence_refs, got {elder_care_with_refs}"
        )

    return errors


def test_product_backlog_schema_and_evidence_paths() -> None:
    errors = validate_product_backlog(_load_backlog())
    assert errors == [], "; ".join(errors)


def test_product_backlog_rejects_invalid_severity() -> None:
    backlog = _load_backlog()
    mutated = dict(backlog)
    items = [dict(item) for item in backlog["items"]]
    items[0] = dict(items[0])
    items[0]["severity"] = "critical"
    mutated["items"] = items
    errors = validate_product_backlog(mutated)
    assert any("invalid severity" in err for err in errors)
