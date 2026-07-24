"""UC13 Orchestrator — jsonschema validate-or-HALT (M1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_SCHEMA_DIR = Path(__file__).resolve().parent
_DEFAULT_SCHEMA = _SCHEMA_DIR / "orchestrator_bundle.schema.yaml"


class BundleValidationError(ValueError):
    """Raised when orchestrator bundle fails JSON Schema validation."""


def _load_schema(schema_path: Path) -> dict[str, Any]:
    with open(schema_path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def validate_bundle(bundle: dict[str, Any], schema_path: str | None = None) -> None:
    """Validate *bundle* against orchestrator_bundle.schema.yaml.

    Raises :class:`BundleValidationError` on failure (HALT before render).
    """
    import jsonschema

    path = Path(schema_path) if schema_path else _DEFAULT_SCHEMA
    schema = _load_schema(path)
    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(bundle), key=lambda e: e.path)
    if errors:
        messages = [e.message for e in errors]
        raise BundleValidationError("; ".join(messages))
