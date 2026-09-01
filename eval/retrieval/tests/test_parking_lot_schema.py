"""Hermetic validation for eval/program/parking_lot.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
PARKING_LOT_PATH = REPO_ROOT / "eval" / "program" / "parking_lot.yaml"

STATUSES = frozenset({"awaiting_confirm", "accepted", "rejected"})
WAITING_ON = frozenset({"team", "stakeholder", "both"})
TOPICS = frozenset({"catalogs", "beta", "prompts", "product", "ingest", "eval", "models"})
REQUIRED_ITEM_KEYS = frozenset(
    {
        "id",
        "title",
        "status",
        "waiting_on",
        "topic",
        "parked_at",
        "decision_needed",
        "current_state",
        "source_refs",
        "notes",
        "related",
        "closes_when",
        "rationale",
        "decided_at",
        "decided_by",
    }
)
RELATED_KEYS = frozenset({"registry", "backlog"})
NAMED_IDS = frozenset(
    {
        "PL-catalog-eval-obvs-prod",
        "PL-beta-wiring",
        "PL-prompt-identity",
        "PL-langfuse-aiops",
    }
)


def _load() -> dict[str, Any]:
    return yaml.safe_load(PARKING_LOT_PATH.read_text(encoding="utf-8"))


def _is_repo_path_ref(ref: str) -> bool:
    if ref.startswith(("registry:", "trust:", "s2_scores:")):
        return False
    path = ref.split("#", 1)[0]
    if path.startswith(".dev/"):
        return False
    return "/" in ref or ref.endswith((".md", ".yaml", ".yml", ".py", ".json", ".sql"))


def _source_ref_resolves(ref: str) -> bool:
    if not _is_repo_path_ref(ref):
        return True
    return (REPO_ROOT / ref).is_file()


def validate_parking_lot(doc: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if doc.get("schema_version") != 1:
        errors.append("schema_version must be 1")

    items = doc.get("items") or []
    if not items:
        errors.append("items must be non-empty")
        return errors

    ids = [item.get("id") for item in items]
    if len(ids) != len(set(ids)):
        errors.append("item id uniqueness violated")

    for item in items:
        item_id = item.get("id", "<missing-id>")
        missing = REQUIRED_ITEM_KEYS - set(item)
        if missing:
            errors.append(f"{item_id}: missing keys {sorted(missing)}")
            continue

        if not str(item_id).startswith("PL-"):
            errors.append(f"{item_id}: id must start with PL-")
        if item["status"] not in STATUSES:
            errors.append(f"{item_id}: invalid status {item['status']!r}")
        if item["waiting_on"] not in WAITING_ON:
            errors.append(f"{item_id}: invalid waiting_on {item['waiting_on']!r}")
        if item["topic"] not in TOPICS:
            errors.append(f"{item_id}: invalid topic {item['topic']!r}")
        if not str(item["title"]).strip():
            errors.append(f"{item_id}: title must be non-empty")
        if not str(item["decision_needed"]).strip():
            errors.append(f"{item_id}: decision_needed must be non-empty")
        if not str(item["current_state"]).strip():
            errors.append(f"{item_id}: current_state must be non-empty")
        if not str(item["closes_when"]).strip():
            errors.append(f"{item_id}: closes_when must be non-empty")
        if not str(item["parked_at"]).strip():
            errors.append(f"{item_id}: parked_at must be non-empty")

        related = item.get("related")
        if not isinstance(related, dict) or set(related) != RELATED_KEYS:
            errors.append(f"{item_id}: related must have exactly keys {sorted(RELATED_KEYS)}")
        elif not isinstance(related["registry"], list) or not isinstance(related["backlog"], list):
            errors.append(f"{item_id}: related.registry and related.backlog must be lists")

        if not isinstance(item.get("source_refs"), list):
            errors.append(f"{item_id}: source_refs must be a list")
        else:
            for ref in item["source_refs"]:
                if not _source_ref_resolves(str(ref)):
                    errors.append(f"{item_id}: source_ref does not resolve: {ref!r}")

        if not isinstance(item.get("notes"), list):
            errors.append(f"{item_id}: notes must be a list")

        options = item.get("options")
        if options is not None:
            if not isinstance(options, list) or not options:
                errors.append(f"{item_id}: options must be a non-empty list when set")
            else:
                seen_opt: set[str] = set()
                for opt in options:
                    if not isinstance(opt, dict) or "id" not in opt or "label" not in opt:
                        errors.append(f"{item_id}: each option needs id and label")
                        continue
                    if opt["id"] in seen_opt:
                        errors.append(f"{item_id}: duplicate option id {opt['id']!r}")
                    seen_opt.add(opt["id"])

        status = item["status"]
        rationale = item.get("rationale")
        decided_at = item.get("decided_at")
        decided_by = item.get("decided_by")
        if status == "awaiting_confirm":
            if rationale is not None:
                errors.append(f"{item_id}: rationale must be null while awaiting_confirm")
            if decided_at is not None:
                errors.append(f"{item_id}: decided_at must be null while awaiting_confirm")
            if decided_by is not None:
                errors.append(f"{item_id}: decided_by must be null while awaiting_confirm")
        else:
            if not rationale or not str(rationale).strip():
                errors.append(f"{item_id}: rationale required when status is {status}")
            if not decided_at or not str(decided_at).strip():
                errors.append(f"{item_id}: decided_at required when status is {status}")

    return errors


def test_parking_lot_schema_valid() -> None:
    errors = validate_parking_lot(_load())
    assert errors == [], errors


def test_named_operator_examples_present() -> None:
    ids = {item["id"] for item in _load()["items"]}
    missing = NAMED_IDS - ids
    assert not missing, f"operator-named examples missing: {sorted(missing)}"


def test_awaiting_rows_have_no_decision_fields() -> None:
    awaiting = [item for item in _load()["items"] if item["status"] == "awaiting_confirm"]
    assert awaiting, "parking lot must have at least one awaiting_confirm row"
    for item in awaiting:
        assert item["rationale"] is None
        assert item["decided_at"] is None


def test_mutation_accepted_without_rationale_fails() -> None:
    doc = _load()
    row = next(item for item in doc["items"] if item["status"] == "awaiting_confirm")
    row["status"] = "accepted"
    errors = validate_parking_lot(doc)
    assert any("rationale required" in err for err in errors)


def test_mutation_bad_status_fails() -> None:
    doc = _load()
    doc["items"][0]["status"] = "parked"
    errors = validate_parking_lot(doc)
    assert any("invalid status" in err for err in errors)
