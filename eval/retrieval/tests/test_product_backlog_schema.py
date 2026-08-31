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
COMPANIES = frozenset({"elder_care", "clearsulting", "gkf", "spg"})
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
CLOSED_TARGET_IDS = frozenset(
    {
        "PB-spg-ingest-borderline-completeness",
        "PB-gkf-retrieval-bloated-filename-closure",
        "PB-spg-retrieval-bloated-filename-closure",
        "PB-multi-company-retrieval-baseline-stale-post-m4",
        "PB-exec_summary-chunk-truncation",
        "PB-fta_numeric-chunk-truncation",
        "PB-fta_numeric-broken-chunk-repoint",
        "PB-fta_numeric-page46-vision-reextract",
        "PB-fta_numeric-segment-json-dedupe",
        "PB-fta_numeric-segment-source-location",
        "PB-legal_register-corpus-gap-platform",
        "PB-legal_register-locator-chunk-resolution",
        # iterate-pack-now-slice T9-bis (R2 amendment): closed on live/hermetic
        # evidence in .dev/plans/iterate-pack-now-slice/artifacts/T9-rescore-evidence.md.
        "PB-agent-kpi-overlay-scorer-healthcare-hardcode",
        "PB-agent-spg-kpi-scorer-empty-fields",
        "PB-legal_register-retrieval-ip",
        "PB-exec_summary-008-locator-mismatch",
        "PB-exec_summary-retrieval-scope-gap",
    }
)
# Retired by iterate-pack-now-slice T9-bis (R2 amendment): this row closed via
# T7's live-verified locator fix; the "open handoff" designation no longer
# applies. See CLOSED_TARGET_IDS above and T9-rescore-evidence.md.
OPEN_HANDOFF_ID = "PB-exec_summary-008-locator-mismatch"
M8_T6_NEW_IDS = frozenset(
    {
        "PB-legal_register-claim-failure-gkf",
        "PB-legal_register-claim-failure-spg",
    }
)
ITERATE_PACK_T1_NEW_IDS = frozenset(
    {
        "PB-agent-kpi-overlay-scorer-healthcare-hardcode",
        "PB-legal_register-elder-care-founder-privacy-extract",
        "PB-legal_register-spg-legal-extract-gap",
        "PB-agent-spg-kpi-scorer-empty-fields",
    }
)
ITERATE_PACK_T1_ROW_SHAPE = {
    "PB-agent-kpi-overlay-scorer-healthcare-hardcode": {
        "company": "clearsulting",
        "surface": "agent",
        "kind": "measurement_caveat",
        "severity": "high",
    },
    "PB-legal_register-elder-care-founder-privacy-extract": {
        "company": "elder_care",
        "surface": "legal_register",
        "kind": "extraction_depth",
        "severity": "high",
    },
    "PB-legal_register-spg-legal-extract-gap": {
        "company": "spg",
        "surface": "legal_register",
        "kind": "extraction_depth",
        "severity": "high",
    },
    "PB-agent-spg-kpi-scorer-empty-fields": {
        "company": "spg",
        "surface": "agent",
        "kind": "measurement_caveat",
        "severity": "medium",
    },
}


def validate_product_backlog_closure_shape(items: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for item in items:
        item_id = item.get("id", "<missing-id>")
        if "status" in item:
            errors.append(f"{item_id}: status field is not permitted")
        closed_at = item.get("closed_at")
        closed_evidence_refs = item.get("closed_evidence_refs")
        if closed_at is None:
            if closed_evidence_refs is not None:
                errors.append(
                    f"{item_id}: closed_evidence_refs must be absent when closed_at is absent"
                )
        else:
            if not str(closed_at).strip():
                errors.append(f"{item_id}: closed_at must be non-empty when set")
            if not closed_evidence_refs:
                errors.append(
                    f"{item_id}: closed_evidence_refs must be non-empty when closed_at is set"
                )
    return errors


def _load_backlog() -> dict[str, Any]:
    return yaml.safe_load(BACKLOG_PATH.read_text(encoding="utf-8"))


def _is_repo_path_ref(ref: str) -> bool:
    if ref.startswith(("registry:", "trust:", "s2_scores:", "baseline_")):
        return False
    if ref.startswith("claim.") or ref.startswith("fta.claim."):
        return False
    path = ref.split("#", 1)[0]
    if path.startswith(".dev/"):
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

        if item["company"] not in COMPANIES:
            errors.append(
                f"{item_id}: company {item['company']!r} not in allowed set {sorted(COMPANIES)}"
            )
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

    errors.extend(validate_product_backlog_closure_shape(items))

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


def test_product_backlog_closed_row_set() -> None:
    backlog = _load_backlog()
    items = backlog["items"]
    assert len(items) == 27
    closed_ids = {item["id"] for item in items if item.get("closed_at") is not None}
    assert closed_ids == CLOSED_TARGET_IDS
    # OPEN_HANDOFF_ID (PB-exec_summary-008-locator-mismatch) was retired into
    # CLOSED_TARGET_IDS by T9-bis (R2 amendment) -- no longer asserted open.


def test_m8_t6_legal_register_rows_match_t3_field_set() -> None:
    """New M8 T6 rows must use the existing legal_register field set and id convention."""
    backlog = _load_backlog()
    items = backlog["items"]
    by_id = {item["id"]: item for item in items}
    assert M8_T6_NEW_IDS <= set(by_id)
    for item_id in M8_T6_NEW_IDS:
        item = by_id[item_id]
        assert set(item) == REQUIRED_ITEM_KEYS, f"{item_id}: extra or missing keys {set(item) ^ REQUIRED_ITEM_KEYS}"
        assert item["surface"] == "legal_register"
        assert item["kind"] == "claim_failure"
        assert item["company"] in {"gkf", "spg"}
        assert item_id == f"PB-legal_register-claim-failure-{item['company']}"
        assert item.get("closed_at") is None
        assert item_id not in CLOSED_TARGET_IDS
    assert not any(
        item["company"] == "clearsulting" and item["surface"] == "legal_register"
        for item in items
    )


def test_iterate_pack_t1_new_rows_match_field_set() -> None:
    """Iterate-pack T1 rows must use frozen ids, enums, and registry_ref A-09."""
    backlog = _load_backlog()
    by_id = {item["id"]: item for item in backlog["items"]}
    assert ITERATE_PACK_T1_NEW_IDS <= set(by_id)
    for item_id in ITERATE_PACK_T1_NEW_IDS:
        item = by_id[item_id]
        expected = ITERATE_PACK_T1_ROW_SHAPE[item_id]
        assert item["company"] == expected["company"]
        assert item["surface"] == expected["surface"]
        assert item["kind"] == expected["kind"]
        assert item["severity"] == expected["severity"]
        assert item["fix_lane"] == "product"
        assert item["registry_ref"] == "A-09"
        # T9-bis (R2 amendment): closure permitted only via the authoritative
        # CLOSED_TARGET_IDS set (never silent) -- see T9-rescore-evidence.md.
        assert item.get("closed_at") is None or item_id in CLOSED_TARGET_IDS
        assert "horizon-map.md" in item["evidence_refs"]
        assert "registry:A-09" in item["evidence_refs"]
    ip_row = by_id["PB-legal_register-retrieval-ip"]
    assert ip_row["kind"] == "extraction_depth"


def test_product_backlog_rejects_orphan_closed_evidence_refs() -> None:
    backlog = _load_backlog()
    mutated = dict(backlog)
    items = [dict(item) for item in backlog["items"]]
    open_item = next(item for item in items if item["id"] not in CLOSED_TARGET_IDS)
    poisoned = dict(open_item)
    poisoned["closed_evidence_refs"] = ["registry:orphan-closure-evidence"]
    for index, item in enumerate(items):
        if item["id"] == open_item["id"]:
            items[index] = poisoned
            break
    mutated["items"] = items
    errors = validate_product_backlog(mutated)
    assert any("closed_evidence_refs must be absent when closed_at is absent" in err for err in errors)
