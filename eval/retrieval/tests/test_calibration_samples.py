"""Spec §17 item 23b — calibration-sample validators (hermetic)."""

from __future__ import annotations

import copy
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLES_DIR = REPO_ROOT / ".dev" / "eval-program"
REGISTRY_PATH = REPO_ROOT / "eval" / "program" / "registry.yaml"
SAMPLE_GLOB = "calibration_sample_*.yaml"

SURFACES = frozenset({"fta_numeric", "legal_register", "exec_summary"})
NUMERIC_SURFACES = frozenset({"fta_numeric"})
CLAIM_VERDICTS = frozenset({"supported", "contradicted", "unsupported"})
NUMERIC_UNITS = frozenset(
    {"USD", "USD_k", "USD_m", "USD_bn", "percent", "ratio", "count", "days"}
)
MVP_LOCATOR_KINDS = frozenset({"page", "section"})
RESERVED_LOCATOR_KINDS = frozenset({"cell", "char_offset"})
JUDGE_OR_HUMAN_RUNGS = frozenset({"judge", "human"})

FILE_REQUIRED_KEYS = frozenset(
    {"schema_version", "surface", "assessed_by", "assessed_at", "claims"}
)
CLAIM_REQUIRED_KEYS = frozenset({"claim_id", "claim_text", "source_ref", "verdict"})
NUMERIC_CLAIM_REQUIRED_KEYS = CLAIM_REQUIRED_KEYS | frozenset(
    {"expected_value", "expected_span"}
)
EXPECTED_SPAN_KEYS = frozenset({"chunk_id", "locator"})
EXPECTED_VALUE_KEYS = frozenset({"magnitude", "unit"})
LOCATOR_KEYS = frozenset({"kind", "value"})


class _CalibrationLoader(yaml.SafeLoader):
    """YAML loader that materializes floats as exact decimals (HALT-28)."""


def _decimal_float_constructor(loader: yaml.Loader, node: yaml.Node) -> Decimal:
    return Decimal(loader.construct_scalar(node))


_CalibrationLoader.add_constructor(
    "tag:yaml.org,2002:float", _decimal_float_constructor
)


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=_CalibrationLoader)


def _surface_from_filename(path: Path) -> str | None:
    stem = path.stem
    prefix = "calibration_sample_"
    if not stem.startswith(prefix):
        return None
    return stem[len(prefix) :]


def _coerce_magnitude(raw: Any) -> tuple[Decimal | None, str | None]:
    if isinstance(raw, float):
        return None, "magnitude must be an exact decimal, not binary float (HALT-28)"
    if isinstance(raw, Decimal):
        magnitude = raw
    elif isinstance(raw, int) and not isinstance(raw, bool):
        magnitude = Decimal(raw)
    elif isinstance(raw, str):
        try:
            magnitude = Decimal(raw)
        except InvalidOperation:
            return None, f"magnitude {raw!r} does not parse as an exact decimal (HALT-28)"
    else:
        return None, f"magnitude must be numeric, got {type(raw).__name__}"

    text = str(magnitude)
    if any(ch in text for ch in ",_$%"):
        return None, "magnitude must carry no separators or symbols (HALT-28)"
    return magnitude, None


def _validate_locator(
    locator: Any,
    *,
    filepath: str,
    claim_id: str,
) -> list[str]:
    errors: list[str] = []
    if locator is None:
        return errors
    if isinstance(locator, str):
        errors.append(
            f"{filepath} claim_id={claim_id}: expected_span.locator must be a typed "
            f"mapping, not a bare string (HALT-25)"
        )
        return errors
    if not isinstance(locator, dict):
        errors.append(
            f"{filepath} claim_id={claim_id}: expected_span.locator must be a mapping or null"
        )
        return errors
    extra = set(locator) - LOCATOR_KEYS
    missing = LOCATOR_KEYS - set(locator)
    if extra:
        errors.append(
            f"{filepath} claim_id={claim_id}: expected_span.locator carries forbidden keys "
            f"{sorted(extra)} (HALT-25)"
        )
    if missing:
        errors.append(
            f"{filepath} claim_id={claim_id}: expected_span.locator missing keys "
            f"{sorted(missing)} (S-59)"
        )
        return errors

    kind = locator.get("kind")
    value = locator.get("value")
    if kind is None or value is None:
        errors.append(
            f"{filepath} claim_id={claim_id}: non-null locator requires kind and value "
            f"non-null (S-59)"
        )
        return errors

    if kind in RESERVED_LOCATOR_KINDS:
        errors.append(
            f"{filepath} claim_id={claim_id}: locator.kind={kind!r} is reserved with no "
            f"MVP producer (HALT-30)"
        )
    elif kind not in MVP_LOCATOR_KINDS:
        errors.append(
            f"{filepath} claim_id={claim_id}: locator.kind={kind!r} not in MVP-producible "
            f"subset {{page, section}} (HALT-30)"
        )

    if kind == "page":
        if isinstance(value, bool) or not isinstance(value, int):
            errors.append(
                f"{filepath} claim_id={claim_id}: locator.kind=page requires integer value"
            )
    elif kind == "section":
        if not isinstance(value, str) or not value.strip():
            errors.append(
                f"{filepath} claim_id={claim_id}: locator.kind=section requires non-empty string value"
            )
    return errors


def _validate_expected_value(
    expected_value: Any,
    *,
    filepath: str,
    claim_id: str,
) -> list[str]:
    errors: list[str] = []
    if expected_value is None:
        return errors
    if not isinstance(expected_value, dict):
        errors.append(
            f"{filepath} claim_id={claim_id}: expected_value must be a typed mapping or null "
            f"(HALT-26)"
        )
        return errors
    extra = set(expected_value) - EXPECTED_VALUE_KEYS
    missing = EXPECTED_VALUE_KEYS - set(expected_value)
    if extra:
        errors.append(
            f"{filepath} claim_id={claim_id}: expected_value carries forbidden keys "
            f"{sorted(extra)} (HALT-26)"
        )
    if missing:
        errors.append(
            f"{filepath} claim_id={claim_id}: expected_value missing keys "
            f"{sorted(missing)} (HALT-26)"
        )
        return errors

    unit = expected_value.get("unit")
    if unit not in NUMERIC_UNITS:
        errors.append(
            f"{filepath} claim_id={claim_id}: expected_value.unit={unit!r} not in §16 "
            f"numeric unit vocabulary"
        )

    _, magnitude_error = _coerce_magnitude(expected_value.get("magnitude"))
    if magnitude_error:
        errors.append(f"{filepath} claim_id={claim_id}: {magnitude_error}")
    return errors


def _validate_expected_span(
    expected_span: Any,
    *,
    filepath: str,
    claim_id: str,
) -> list[str]:
    errors: list[str] = []
    if expected_span is None:
        return errors
    if isinstance(expected_span, str):
        errors.append(
            f"{filepath} claim_id={claim_id}: expected_span must be a typed mapping, not a "
            f"scalar or string (HALT-25)"
        )
        return errors
    if not isinstance(expected_span, dict):
        errors.append(
            f"{filepath} claim_id={claim_id}: expected_span must be a mapping or null (HALT-25)"
        )
        return errors

    extra = set(expected_span) - EXPECTED_SPAN_KEYS
    missing = EXPECTED_SPAN_KEYS - set(expected_span)
    if extra:
        errors.append(
            f"{filepath} claim_id={claim_id}: expected_span carries forbidden keys "
            f"{sorted(extra)} (HALT-25)"
        )
    if missing:
        errors.append(
            f"{filepath} claim_id={claim_id}: expected_span missing keys "
            f"{sorted(missing)} (HALT-25)"
        )
        return errors

    chunk_id = expected_span.get("chunk_id")
    if chunk_id is None:
        errors.append(
            f"{filepath} claim_id={claim_id}: non-null expected_span requires non-null chunk_id"
        )

    if "locator" not in expected_span:
        errors.append(
            f"{filepath} claim_id={claim_id}: expected_span must carry present-but-nullable "
            f"locator key (HALT-25)"
        )
    else:
        errors.extend(
            _validate_locator(
                expected_span.get("locator"),
                filepath=filepath,
                claim_id=claim_id,
            )
        )
    return errors


def validate_calibration_sample(
    data: dict[str, Any],
    *,
    filepath: str,
) -> list[str]:
    """Return human-readable validation errors; empty list means pass."""
    errors: list[str] = []

    if not isinstance(data, dict):
        return [f"{filepath}: root must be a mapping"]

    surface = data.get("surface")
    filename_surface = _surface_from_filename(Path(filepath))

    missing_file_keys = FILE_REQUIRED_KEYS - set(data)
    if missing_file_keys:
        errors.append(
            f"{filepath}: missing required file keys {sorted(missing_file_keys)} (§8.7)"
        )

    if data.get("schema_version") != 1:
        errors.append(
            f"{filepath}: schema_version must be 1, got {data.get('schema_version')!r}"
        )

    if surface not in SURFACES:
        errors.append(
            f"{filepath}: surface={surface!r} not in §16 surface vocabulary"
        )
    elif filename_surface is not None and surface != filename_surface:
        errors.append(
            f"{filepath}: surface={surface!r} must equal filename suffix "
            f"{filename_surface!r}"
        )

    if data.get("assessed_by") != "operator":
        errors.append(
            f"{filepath}: assessed_by must be 'operator', got {data.get('assessed_by')!r}"
        )

    if not data.get("assessed_at"):
        errors.append(f"{filepath}: assessed_at is required (§8.7)")

    claims = data.get("claims")
    if claims is None:
        return errors
    if not isinstance(claims, list):
        errors.append(f"{filepath}: claims must be a list")
        return errors

    is_numeric = surface in NUMERIC_SURFACES
    seen_claim_ids: set[str] = set()

    for claim in claims:
        if not isinstance(claim, dict):
            errors.append(f"{filepath}: each claims entry must be a mapping")
            continue

        claim_id = str(claim.get("claim_id", "<missing-claim-id>"))
        if claim_id in seen_claim_ids:
            errors.append(
                f"{filepath} claim_id={claim_id}: claim_id must be unique within the file"
            )
        seen_claim_ids.add(claim_id)

        required_keys = NUMERIC_CLAIM_REQUIRED_KEYS if is_numeric else CLAIM_REQUIRED_KEYS
        missing_claim_keys = required_keys - set(claim)
        if missing_claim_keys:
            errors.append(
                f"{filepath} claim_id={claim_id}: missing required claim keys "
                f"{sorted(missing_claim_keys)} (§8.7)"
            )

        verdict = claim.get("verdict")
        if verdict not in CLAIM_VERDICTS:
            errors.append(
                f"{filepath} claim_id={claim_id}: verdict={verdict!r} not in §16 "
                f"claim-verdict vocabulary"
            )

        expected_span = claim.get("expected_span") if "expected_span" in claim else None
        expected_value = claim.get("expected_value") if "expected_value" in claim else None

        if is_numeric:
            if expected_span is None and expected_value is not None:
                errors.append(
                    f"{filepath} claim_id={claim_id}: expected_span: null requires "
                    f"expected_value: null (S-70 one-directional coupling)"
                )
            errors.extend(
                _validate_expected_span(
                    expected_span,
                    filepath=filepath,
                    claim_id=claim_id,
                )
            )
            errors.extend(
                _validate_expected_value(
                    expected_value,
                    filepath=filepath,
                    claim_id=claim_id,
                )
            )
        else:
            if expected_span is not None:
                errors.extend(
                    _validate_expected_span(
                        expected_span,
                        filepath=filepath,
                        claim_id=claim_id,
                    )
                )
            if expected_value is not None:
                errors.extend(
                    _validate_expected_value(
                        expected_value,
                        filepath=filepath,
                        claim_id=claim_id,
                    )
                )

    return errors


def derive_judge_human_surfaces(registry: dict[str, Any]) -> set[str]:
    """Surfaces assigned judge or human in any registry row (HALT-32 derivation)."""
    population: set[str] = set()
    items = registry.get("items") or []
    if not isinstance(items, list):
        raise ValueError("registry items must be a list")

    for item in items:
        if not isinstance(item, dict):
            continue
        rung_assignments = item.get("rung_assignments") or {}
        if not isinstance(rung_assignments, dict):
            raise ValueError(
                f"registry row {item.get('id', '<missing-id>')}: rung_assignments unparseable"
            )
        for surface, rung in rung_assignments.items():
            if rung in JUDGE_OR_HUMAN_RUNGS:
                population.add(surface)
    return population


def validate_sample_presence(
    registry: dict[str, Any],
    samples_dir: Path = SAMPLES_DIR,
) -> list[str]:
    population = derive_judge_human_surfaces(registry)
    errors: list[str] = []
    for surface in sorted(population):
        expected = samples_dir / f"calibration_sample_{surface}.yaml"
        if not expected.exists():
            errors.append(
                f"calibration_sample_{surface}.yaml: required for surface {surface!r} "
                f"assigned judge/human in rung_assignments (item 23b presence half)"
            )
    return errors


def _minimal_numeric_sample(*, claim_id: str = "mut.claim.001") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "surface": "fta_numeric",
        "assessed_by": "operator",
        "assessed_at": "2026-08-12",
        "claims": [
            {
                "claim_id": claim_id,
                "claim_text": "Sample claim",
                "source_ref": "cite://example.pdf#Section",
                "verdict": "supported",
                "expected_value": {"magnitude": "4.2", "unit": "USD_m"},
                "expected_span": {
                    "chunk_id": "chunk-001",
                    "locator": {"kind": "section", "value": "Section A"},
                },
            }
        ],
    }


@pytest.fixture(scope="module")
def registry_doc() -> dict[str, Any]:
    if not REGISTRY_PATH.exists():
        pytest.skip(
            f"{REGISTRY_PATH} missing — registry-backed presence half requires "
            "tracked eval/program/registry.yaml"
        )
    return _load_yaml(REGISTRY_PATH)


@pytest.fixture(scope="module")
def committed_sample_paths() -> list[Path]:
    return sorted(SAMPLES_DIR.glob(SAMPLE_GLOB))


def test_committed_calibration_samples_pass_schema(committed_sample_paths):
    if not committed_sample_paths:
        pytest.skip("no calibration_sample_*.yaml files present yet")
    for path in committed_sample_paths:
        data = _load_yaml(path)
        errors = validate_calibration_sample(data, filepath=str(path))
        assert errors == [], "\n".join(errors)


def test_sample_presence_half(registry_doc):
    population = derive_judge_human_surfaces(registry_doc)
    if not population:
        pytest.skip(
            "presence half skipped: no judge/human rung_assignments recorded yet — "
            "item 26a has not run; T7 must re-run this suite after 26a closes"
        )
    errors = validate_sample_presence(registry_doc)
    assert errors == [], "\n".join(errors)


def test_mutation_locator_kind_cell_fails():
    sample = _minimal_numeric_sample()
    sample["claims"][0]["expected_span"]["locator"] = {"kind": "cell", "value": "r12c4"}
    errors = validate_calibration_sample(sample, filepath="mutation_cell.yaml")
    assert any("HALT-30" in error for error in errors)


def test_mutation_permissive_null_value_with_span_passes():
    sample = _minimal_numeric_sample()
    sample["claims"][0]["expected_value"] = None
    errors = validate_calibration_sample(sample, filepath="mutation_s70_pass.yaml")
    assert errors == []


def test_mutation_strict_coupling_span_null_value_non_null_fails():
    sample = _minimal_numeric_sample()
    sample["claims"][0]["expected_span"] = None
    errors = validate_calibration_sample(sample, filepath="mutation_s70_fail.yaml")
    assert any("S-70" in error for error in errors)


def test_mutation_bare_scalar_expected_value_fails():
    sample = _minimal_numeric_sample()
    sample["claims"][0]["expected_value"] = 4.2
    errors = validate_calibration_sample(sample, filepath="mutation_scalar_value.yaml")
    assert any("HALT-26" in error for error in errors)


def test_mutation_duplicate_claim_id_fails():
    sample = _minimal_numeric_sample()
    sample["claims"].append(copy.deepcopy(sample["claims"][0]))
    errors = validate_calibration_sample(sample, filepath="mutation_dup_id.yaml")
    assert any("unique" in error for error in errors)


def test_mutation_out_of_vocabulary_verdict_fails():
    sample = _minimal_numeric_sample()
    sample["claims"][0]["verdict"] = "Supported"
    errors = validate_calibration_sample(sample, filepath="mutation_verdict.yaml")
    assert any("claim-verdict vocabulary" in error for error in errors)


def test_mutation_float_magnitude_fails():
    sample = _minimal_numeric_sample()
    sample["claims"][0]["expected_value"]["magnitude"] = float(Decimal("4.2"))
    errors = validate_calibration_sample(sample, filepath="mutation_float.yaml")
    assert any("HALT-28" in error for error in errors)


def test_presence_population_requires_missing_sample(tmp_path):
    registry = {
        "schema_version": 1,
        "items": [
            {
                "id": "SYN-26A",
                "rung_assignments": {"exec_summary": "judge", "fta_numeric": "human"},
            }
        ],
    }
    errors = validate_sample_presence(registry, samples_dir=tmp_path)
    assert len(errors) == 2
    assert all("calibration_sample_" in error for error in errors)


def test_registry_rung_assignments_unparseable_halts_shape():
    registry = {"schema_version": 1, "items": [{"id": "BAD", "rung_assignments": "not-a-map"}]}
    with pytest.raises(ValueError, match="rung_assignments unparseable"):
        derive_judge_human_surfaces(registry)
