"""Spec §17 item 2a — registry and source_manifest validators (hermetic)."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
REGISTRY_PATH = REPO_ROOT / "eval" / "program" / "registry.yaml"
MANIFEST_PATH = REPO_ROOT / "eval" / "program" / "source_manifest.yaml"
MUTATION_MANIFEST_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "eval_program_registry_mutation_base.yaml"
)

FROZEN_RATIFICATION_COUNT = 4
FROZEN_ACC_COUNT = 2

DISPOSITIONS = frozenset({"staged", "deferred", "rejected", "accepted"})
STATUSES = frozenset({"pending", "in_progress", "closed", "descoped", "n/a"})
STAGED_STATUSES = frozenset({"pending", "in_progress", "closed", "descoped"})
SURFACES = frozenset({"fta_numeric", "legal_register", "exec_summary", "null"})
RUNGS = frozenset({"deterministic", "judge", "human", "null"})
NUMERIC_SURFACES = frozenset({"fta_numeric"})
JUDGE_OR_HUMAN_RUNGS = frozenset({"judge", "human"})


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _registry_by_id(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in registry.get("items", [])}


def _required_metric_names(surface: str, metrics: dict[str, float]) -> set[str]:
    if surface in NUMERIC_SURFACES:
        required = {
            "resolved_value_fraction",
            "resolved_span_fraction",
            "locator_labelled_fraction",
        }
        if metrics.get("resolved_value_fraction", 0) > 0:
            required.add("value_agreement")
        if metrics.get("resolved_span_fraction", 0) > 0:
            required.add("span_agreement")
        return required
    return {"verdict_agreement"}


def _forbidden_metric_names(surface: str) -> set[str]:
    if surface in NUMERIC_SURFACES:
        return {"verdict_agreement"}
    return {
        "value_agreement",
        "span_agreement",
        "resolved_value_fraction",
        "resolved_span_fraction",
        "locator_labelled_fraction",
    }


def validate_registry_manifest(
    registry: dict[str, Any],
    manifest: dict[str, Any],
) -> list[str]:
    """Return human-readable validation errors; empty list means pass."""
    errors: list[str] = []
    items = registry.get("items") or []
    sources = manifest.get("sources") or []

    ids = [item.get("id") for item in items]
    if len(ids) != len(set(ids)):
        errors.append("registry item id uniqueness violated")

    manifest_ids = [source.get("id") for source in sources]
    if len(manifest_ids) != len(set(manifest_ids)):
        errors.append("manifest source id uniqueness violated")

    by_id = _registry_by_id(registry)
    manifest_id_set = set(manifest_ids)

    for item in items:
        row_id = item.get("id", "<missing-id>")
        disposition = item.get("disposition")
        status = item.get("status")

        if disposition not in DISPOSITIONS:
            errors.append(f"{row_id}: disposition {disposition!r} not in §16 vocabulary")
            continue

        if status not in STATUSES:
            errors.append(f"{row_id}: status {status!r} not in §16 vocabulary")
            continue

        if disposition == "staged":
            if status not in STAGED_STATUSES:
                errors.append(
                    f"{row_id}: staged disposition requires staged status, got {status!r}"
                )
            if not item.get("stage"):
                errors.append(f"{row_id}: staged disposition requires non-empty stage")
        elif disposition == "deferred":
            if status != "n/a":
                errors.append(f"{row_id}: deferred disposition requires status n/a")
            if not item.get("trigger"):
                errors.append(f"{row_id}: deferred disposition requires trigger")
        elif disposition in {"rejected", "accepted"}:
            if status != "n/a":
                errors.append(
                    f"{row_id}: {disposition} disposition requires status n/a"
                )
            if not item.get("rationale"):
                errors.append(f"{row_id}: {disposition} disposition requires rationale")

        if status == "closed" and not item.get("evidence_refs"):
            errors.append(f"{row_id}: closed status requires non-empty evidence_refs")

    for source_id in manifest_id_set:
        matches = [item for item in items if item.get("source_id") == source_id]
        if len(matches) != 1:
            errors.append(
                f"manifest id {source_id!r} must map to exactly one registry row via source_id, "
                f"found {len(matches)}"
            )

    for item in items:
        source_id = item.get("source_id")
        if source_id is None:
            continue
        if source_id not in manifest_id_set:
            errors.append(
                f"{item['id']}: source_id {source_id!r} missing from manifest sources"
            )

    ratifications = manifest.get("ratifications")
    if ratifications is None:
        errors.append("manifest ratifications block missing")
    else:
        if len(ratifications) != FROZEN_RATIFICATION_COUNT:
            errors.append(
                f"manifest ratifications must contain exactly {FROZEN_RATIFICATION_COUNT} entries, "
                f"found {len(ratifications)}"
            )
        for entry in ratifications:
            rides = entry.get("rides")
            row = by_id.get(rides)
            if row is None:
                errors.append(f"ratification rides target {rides!r} not found in registry")
            elif not row.get("rationale"):
                errors.append(
                    f"ratification rides target {rides!r} requires non-empty rationale"
                )

    acc_count = sum(1 for source in sources if str(source.get("id", "")).startswith("ACC-"))
    if acc_count != FROZEN_ACC_COUNT:
        errors.append(
            f"manifest sources must contain exactly {FROZEN_ACC_COUNT} ACC- ids, found {acc_count}"
        )

    surface_assignments: dict[str, list[str]] = {}
    for item in items:
        row_id = item.get("id", "<missing-id>")
        rung_assignments = item.get("rung_assignments") or {}
        if not isinstance(rung_assignments, dict):
            errors.append(f"{row_id}: rung_assignments must be a map")
            continue
        for surface, rung in rung_assignments.items():
            if surface is None or surface == "null":
                errors.append(f"{row_id}: rung_assignments key {surface!r} must be non-null surface")
            elif surface not in SURFACES:
                errors.append(f"{row_id}: rung_assignments key {surface!r} not in §16 surface vocabulary")
            if rung is None or rung == "null":
                errors.append(f"{row_id}: rung_assignments[{surface!r}] must be non-null rung")
            elif rung not in RUNGS:
                errors.append(f"{row_id}: rung_assignments[{surface!r}]={rung!r} not in §16 rung vocabulary")
            surface_assignments.setdefault(surface, []).append(row_id)

    for surface, row_ids in surface_assignments.items():
        if len(row_ids) > 1:
            errors.append(
                f"surface {surface!r} appears in rung_assignments on multiple rows: {row_ids}"
            )

    for item in items:
        row_id = item.get("id", "<missing-id>")
        assessment_metrics = item.get("assessment_metrics") or {}
        if not isinstance(assessment_metrics, dict):
            errors.append(f"{row_id}: assessment_metrics must be a map")
            continue
        for surface, figures in assessment_metrics.items():
            if surface is None or surface == "null":
                errors.append(f"{row_id}: assessment_metrics key {surface!r} must be non-null surface")
                continue
            if surface not in SURFACES:
                errors.append(
                    f"{row_id}: assessment_metrics key {surface!r} not in §16 surface vocabulary"
                )
            if not isinstance(figures, dict):
                errors.append(f"{row_id}: assessment_metrics[{surface!r}] must be a figure map")
                continue
            for figure_name, value in figures.items():
                if not isinstance(value, (int, float)):
                    errors.append(
                        f"{row_id}: assessment_metrics[{surface!r}][{figure_name}] must be numeric"
                    )
                elif not 0 <= float(value) <= 1:
                    errors.append(
                        f"{row_id}: assessment_metrics[{surface!r}][{figure_name}] must be in [0, 1]"
                    )
            required = _required_metric_names(surface, figures)
            forbidden = _forbidden_metric_names(surface)
            actual = set(figures)
            missing = required - actual
            if missing:
                errors.append(
                    f"{row_id}: assessment_metrics[{surface!r}] missing required figures {sorted(missing)}"
                )
            extra_forbidden = actual & forbidden
            if extra_forbidden:
                errors.append(
                    f"{row_id}: assessment_metrics[{surface!r}] carries forbidden figures "
                    f"{sorted(extra_forbidden)} for surface class"
                )

    trigger_fires = any(
        rung in JUDGE_OR_HUMAN_RUNGS
        for item in items
        for rung in (item.get("rung_assignments") or {}).values()
    )
    if trigger_fires:
        metric_rows = [item for item in items if item.get("assessment_metrics")]
        if len(metric_rows) != 1:
            errors.append(
                "when any row assigns judge/human, exactly one row must carry assessment_metrics, "
                f"found {len(metric_rows)}"
            )
        else:
            row = metric_rows[0]
            rung_keys = set((row.get("rung_assignments") or {}).keys())
            metric_keys = set((row.get("assessment_metrics") or {}).keys())
            missing = rung_keys - metric_keys
            if missing:
                errors.append(
                    f"assessment_metrics row {row['id']} missing metrics for rung_assignments keys "
                    f"{sorted(missing)}"
                )

    return errors


def _artifact_presence() -> tuple[bool, bool]:
    return REGISTRY_PATH.exists(), MANIFEST_PATH.exists()


_registry_exists, _manifest_exists = _artifact_presence()
if not _registry_exists and not _manifest_exists:
    pytest.skip(
        "registry.yaml and source_manifest.yaml both absent — S0 import (T1) has not run",
        allow_module_level=True,
    )


@pytest.fixture(scope="module")
def populated_artifacts() -> tuple[dict[str, Any], dict[str, Any]]:
    assert REGISTRY_PATH.exists(), "registry.yaml missing while source_manifest.yaml present"
    assert MANIFEST_PATH.exists(), "source_manifest.yaml missing while registry.yaml present"
    return _load_yaml(REGISTRY_PATH), _load_yaml(MANIFEST_PATH)


@pytest.fixture
def synthetic_valid_pair() -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = _load_yaml(MUTATION_MANIFEST_PATH)
    registry = {
        "schema_version": 1,
        "items": [
            {
                "id": "ROW-1",
                "title": "Synthetic row one",
                "source_refs": ["OPEN_ITEMS.md#open--half-open"],
                "source_id": "ROW-1",
                "disposition": "accepted",
                "stage": None,
                "status": "n/a",
                "trigger": None,
                "rationale": "Synthetic ratification rationale",
                "tshirt": None,
                "evidence_refs": [],
                "rung_assignments": {},
                "assessment_metrics": {},
            },
            {
                "id": "ACC-synthetic-orphan-a",
                "title": "Synthetic ACC orphan A",
                "source_refs": [".dev/eval_state_of_affairs_2026-08-03.md#8.4"],
                "source_id": "ACC-synthetic-orphan-a",
                "disposition": "accepted",
                "stage": None,
                "status": "n/a",
                "trigger": None,
                "rationale": "Synthetic accepted orphan A",
                "tshirt": None,
                "evidence_refs": [],
                "rung_assignments": {},
                "assessment_metrics": {},
            },
            {
                "id": "ACC-synthetic-orphan-b",
                "title": "Synthetic ACC orphan B",
                "source_refs": [".dev/eval_state_of_affairs_2026-08-03.md#8.4"],
                "source_id": "ACC-synthetic-orphan-b",
                "disposition": "accepted",
                "stage": None,
                "status": "n/a",
                "trigger": None,
                "rationale": "Synthetic accepted orphan B",
                "tshirt": None,
                "evidence_refs": [],
                "rung_assignments": {},
                "assessment_metrics": {},
            },
        ],
    }
    return registry, manifest


def test_artifact_paths_not_mixed():
    reg_exists, man_exists = _artifact_presence()
    assert reg_exists == man_exists, (
        "mixed artifact state: registry.yaml and source_manifest.yaml must both be present or both absent"
    )


def test_populated_artifacts_pass_item_2a_validators(populated_artifacts):
    registry, manifest = populated_artifacts
    errors = validate_registry_manifest(registry, manifest)
    assert errors == [], "\n".join(errors)


def test_synthetic_valid_pair_passes(synthetic_valid_pair):
    registry, manifest = synthetic_valid_pair
    assert validate_registry_manifest(registry, manifest) == []


def test_duplicate_registry_id_mutation_fails(synthetic_valid_pair):
    registry, manifest = synthetic_valid_pair
    broken = copy.deepcopy(registry)
    broken["items"].append(copy.deepcopy(broken["items"][0]))
    errors = validate_registry_manifest(broken, manifest)
    assert any("id uniqueness" in error for error in errors)


def test_staged_missing_stage_mutation_fails(synthetic_valid_pair):
    registry, manifest = synthetic_valid_pair
    broken = copy.deepcopy(registry)
    broken["items"][0].update(
        {
            "disposition": "staged",
            "status": "pending",
            "stage": None,
            "rationale": None,
        }
    )
    errors = validate_registry_manifest(broken, manifest)
    assert any("requires non-empty stage" in error for error in errors)


def test_closed_without_evidence_mutation_fails(synthetic_valid_pair):
    registry, manifest = synthetic_valid_pair
    broken = copy.deepcopy(registry)
    broken["items"][0].update(
        {
            "disposition": "staged",
            "status": "closed",
            "stage": "S0",
            "evidence_refs": [],
        }
    )
    errors = validate_registry_manifest(broken, manifest)
    assert any("evidence_refs" in error for error in errors)


def test_manifest_forward_join_mutation_fails(synthetic_valid_pair):
    registry, manifest = synthetic_valid_pair
    broken = copy.deepcopy(registry)
    broken["items"][0]["source_id"] = "MISSING-MANIFEST-ID"
    errors = validate_registry_manifest(broken, manifest)
    assert any("missing from manifest sources" in error for error in errors)


def test_manifest_reverse_join_mutation_fails(synthetic_valid_pair):
    registry, manifest = synthetic_valid_pair
    removed = manifest["sources"][-1]["id"]
    broken = copy.deepcopy(manifest)
    broken["sources"] = broken["sources"][:-1]
    errors = validate_registry_manifest(registry, broken)
    assert any(
        f"source_id {removed!r} missing from manifest sources" in error for error in errors
    )


def test_ratification_count_mutation_fails(synthetic_valid_pair):
    registry, manifest = synthetic_valid_pair
    broken = copy.deepcopy(manifest)
    broken["ratifications"] = broken["ratifications"][:3]
    errors = validate_registry_manifest(registry, broken)
    assert any("ratifications must contain exactly" in error for error in errors)


def test_ratification_missing_rationale_mutation_fails(synthetic_valid_pair):
    registry, manifest = synthetic_valid_pair
    broken = copy.deepcopy(registry)
    broken["items"][0]["rationale"] = None
    errors = validate_registry_manifest(broken, manifest)
    assert any("requires non-empty rationale" in error for error in errors)


def test_acc_count_mutation_fails(synthetic_valid_pair):
    registry, manifest = synthetic_valid_pair
    broken = copy.deepcopy(manifest)
    broken["sources"] = [s for s in broken["sources"] if not s["id"].startswith("ACC-")]
    errors = validate_registry_manifest(registry, broken)
    assert any("ACC- ids" in error for error in errors)


def test_rung_assignments_invalid_surface_mutation_fails(synthetic_valid_pair):
    registry, manifest = synthetic_valid_pair
    broken = copy.deepcopy(registry)
    broken["items"][0]["rung_assignments"] = {"not_a_surface": "deterministic"}
    errors = validate_registry_manifest(broken, manifest)
    assert any("surface vocabulary" in error for error in errors)


def test_rung_assignments_cross_row_duplicate_mutation_fails(synthetic_valid_pair):
    registry, manifest = synthetic_valid_pair
    broken = copy.deepcopy(registry)
    broken["items"][0]["rung_assignments"] = {"fta_numeric": "deterministic"}
    broken["items"][1]["rung_assignments"] = {"fta_numeric": "judge"}
    errors = validate_registry_manifest(broken, manifest)
    assert any("multiple rows" in error for error in errors)


def test_assessment_metrics_non_numeric_required_name_mutation_fails(synthetic_valid_pair):
    registry, manifest = synthetic_valid_pair
    broken = copy.deepcopy(registry)
    broken["items"][0]["assessment_metrics"] = {
        "exec_summary": {"value_agreement": 0.5},
    }
    errors = validate_registry_manifest(broken, manifest)
    assert any("missing required figures" in error for error in errors)


def test_assessment_metrics_numeric_coverage_conditional_mutation_fails(synthetic_valid_pair):
    registry, manifest = synthetic_valid_pair
    broken = copy.deepcopy(registry)
    broken["items"][0]["assessment_metrics"] = {
        "fta_numeric": {
            "resolved_value_fraction": 0.4,
            "resolved_span_fraction": 0.0,
            "locator_labelled_fraction": 0.2,
        }
    }
    errors = validate_registry_manifest(broken, manifest)
    assert any("missing required figures ['value_agreement']" in error for error in errors)


def test_assessment_metrics_trigger_and_containment_synthetic_branch():
    registry = {
        "schema_version": 1,
        "items": [
            {
                "id": "ITEM-23",
                "title": "item 23 synthetic",
                "source_refs": [],
                "source_id": None,
                "disposition": "staged",
                "stage": "S2",
                "status": "pending",
                "trigger": None,
                "rationale": None,
                "tshirt": None,
                "evidence_refs": [],
                "rung_assignments": {},
                "assessment_metrics": {},
            },
            {
                "id": "ITEM-26A",
                "title": "item 26a synthetic",
                "source_refs": [],
                "source_id": None,
                "disposition": "staged",
                "stage": "S2",
                "status": "pending",
                "trigger": None,
                "rationale": None,
                "tshirt": None,
                "evidence_refs": [],
                "rung_assignments": {
                    "exec_summary": "human",
                    "fta_numeric": "judge",
                },
                "assessment_metrics": {
                    "exec_summary": {"verdict_agreement": 0.9},
                },
            },
        ],
    }
    manifest = {"schema_version": 1, "sources": [], "ratifications": [{}, {}, {}, {}]}
    errors = validate_registry_manifest(registry, manifest)
    assert any("missing metrics for rung_assignments keys ['fta_numeric']" in error for error in errors)


def test_assessment_metrics_trigger_requires_exactly_one_carrier_mutation_fails():
    registry = {
        "schema_version": 1,
        "items": [
            {
                "id": "A",
                "title": "a",
                "source_refs": [],
                "source_id": None,
                "disposition": "staged",
                "stage": "S2",
                "status": "pending",
                "trigger": None,
                "rationale": None,
                "tshirt": None,
                "evidence_refs": [],
                "rung_assignments": {"exec_summary": "judge"},
                "assessment_metrics": {"exec_summary": {"verdict_agreement": 0.8}},
            },
            {
                "id": "B",
                "title": "b",
                "source_refs": [],
                "source_id": None,
                "disposition": "staged",
                "stage": "S2",
                "status": "pending",
                "trigger": None,
                "rationale": None,
                "tshirt": None,
                "evidence_refs": [],
                "rung_assignments": {},
                "assessment_metrics": {"legal_register": {"verdict_agreement": 0.7}},
            },
        ],
    }
    manifest = {"schema_version": 1, "sources": [], "ratifications": [{}, {}, {}, {}]}
    errors = validate_registry_manifest(registry, manifest)
    assert any("exactly one row must carry assessment_metrics" in error for error in errors)


def test_production_default_registry_paths_resolve_to_tracked_files() -> None:
    """Falsifier: defaults must not depend on gitignored .dev/eval-program/."""
    from eval.content.spot_check import DEFAULT_REGISTRY_PATH
    from eval.retrieval.trust_statement import _DEFAULT_REGISTRY

    for label, path in (
        ("spot_check.DEFAULT_REGISTRY_PATH", DEFAULT_REGISTRY_PATH),
        ("trust_statement._DEFAULT_REGISTRY", _DEFAULT_REGISTRY),
    ):
        assert ".dev" not in path.as_posix(), f"{label} must not reference gitignored .dev/"
        resolved = (REPO_ROOT / path).resolve()
        assert resolved.is_file(), f"{label} must resolve to tracked file at {resolved}"


_OFFLINE_SCRIPT_ALLOWLIST = frozenset(
    {
        "extract_rubric_manifests.py",
    }
)


def test_production_modules_do_not_embed_gitignored_dev_runtime_paths() -> None:
    """O-5 falsifier: S2 runtime modules must not reference gitignored .dev/ paths."""
    violations: list[str] = []
    for package_root in (REPO_ROOT / "eval" / "content", REPO_ROOT / "eval" / "retrieval"):
        for path in package_root.rglob("*.py"):
            rel = path.relative_to(package_root)
            if rel.parts[0:1] == ("tests",) or path.name.startswith("test_"):
                continue
            if path.name in _OFFLINE_SCRIPT_ALLOWLIST:
                continue
            for line_no, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if ".dev/" in line and not line.strip().startswith("#"):
                    violations.append(f"{path.relative_to(REPO_ROOT)}:{line_no}: {line.strip()}")
    assert not violations, "gitignored .dev/ runtime dependencies:\n" + "\n".join(violations)
