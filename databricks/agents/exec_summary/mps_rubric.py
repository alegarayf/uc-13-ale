"""MPS (Minimum Pursuit Score) rubric loader and pure scoring arithmetic.

Import-graph leaf: this module imports nothing from `workstreams/` and nothing
from `rainmaker_view.py`, so both sides of the codebase may depend on it
without creating a cycle (docs/plans/mps_score/mps_score_1st_draft.md §6.1).

There is no module-level score threshold constant. The threshold always comes
from the loaded rubric YAML (`rubric["threshold"]`). If the YAML fails to
load, callers must degrade the MPS result rather than fall back to a
hardcoded value (§6.2).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_RUBRIC_PATH = Path(__file__).with_name("mps_rubric.yaml")

_ALLOWED_EVIDENCE_BASIS = {"document_derived", "judgment_over_context", "contact_dependent"}
_REQUIRED_ANCHOR_KEYS = {"1", "3", "5"}

# The /1000 divisor in mps_total() is calibrated to exactly this many 1-5
# category scores. This is the one place 7 may be hardcoded — everywhere
# else, the category count must come from the loaded rubric
# (docs/plans/mps_score/mps_score_1st_draft.md §6.2, §13).
_CATEGORY_COUNT = 7


class RubricError(ValueError):
    """Raised when the rubric YAML is missing, malformed, or fails validation."""


def load_rubric(path: str | Path | None = None) -> dict[str, Any]:
    """Load and validate the MPS rubric YAML.

    Raises RubricError on any structural problem. Callers (MPSAgent) must
    treat that as a signal to degrade the MPS result, not as a hardcoded
    threshold fallback.
    """
    rubric_path = Path(path) if path is not None else _RUBRIC_PATH
    try:
        with open(rubric_path, "r", encoding="utf-8") as fh:
            rubric = yaml.safe_load(fh)
    except OSError as exc:
        raise RubricError(f"could not read rubric file {rubric_path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise RubricError(f"rubric file {rubric_path} is not valid YAML: {exc}") from exc

    _validate_rubric(rubric)
    return rubric


def _validate_rubric(rubric: Any) -> None:
    if not isinstance(rubric, dict):
        raise RubricError("rubric root must be a mapping")

    if not isinstance(rubric.get("rubric_version"), str) or not rubric["rubric_version"]:
        raise RubricError("rubric_version must be a non-empty string")

    threshold = rubric.get("threshold")
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
        raise RubricError("threshold must be a number")

    scale = rubric.get("scale")
    if not isinstance(scale, dict) or "min" not in scale or "max" not in scale:
        raise RubricError("scale must be a mapping with min/max")

    categories = rubric.get("categories")
    if not isinstance(categories, list) or len(categories) != _CATEGORY_COUNT:
        raise RubricError(f"rubric must define exactly {_CATEGORY_COUNT} categories")

    seen_keys: set[str] = set()
    for entry in categories:
        if not isinstance(entry, dict):
            raise RubricError("each category must be a mapping")

        key = entry.get("key")
        if not isinstance(key, str) or not key:
            raise RubricError("each category must have a non-empty string key")
        if key in seen_keys:
            raise RubricError(f"duplicate category key: {key}")
        seen_keys.add(key)

        if not isinstance(entry.get("display_name"), str) or not entry["display_name"]:
            raise RubricError(f"category {key!r} must have a non-empty display_name")

        definition = entry.get("definition")
        if not isinstance(definition, str) or not definition.strip():
            raise RubricError(f"category {key!r} must have a non-empty definition")

        evidence_basis = entry.get("evidence_basis")
        if evidence_basis not in _ALLOWED_EVIDENCE_BASIS:
            raise RubricError(
                f"category {key!r} has invalid evidence_basis {evidence_basis!r}; "
                f"must be one of {sorted(_ALLOWED_EVIDENCE_BASIS)}"
            )

        anchors = entry.get("anchors")
        if not isinstance(anchors, dict) or not _REQUIRED_ANCHOR_KEYS.issubset(anchors.keys()):
            raise RubricError(f"category {key!r} must have anchors for {sorted(_REQUIRED_ANCHOR_KEYS)}")
        for anchor_key in _REQUIRED_ANCHOR_KEYS:
            if not isinstance(anchors[anchor_key], str) or not anchors[anchor_key].strip():
                raise RubricError(f"category {key!r} anchor {anchor_key!r} must be a non-empty string")

        required_commentary = entry.get("required_commentary")
        if not isinstance(required_commentary, dict):
            raise RubricError(f"category {key!r} must have a required_commentary mapping")
        if not isinstance(required_commentary.get("sub_axes"), list):
            raise RubricError(f"category {key!r} required_commentary.sub_axes must be a list")


def mps_total(scores: list[int | None]) -> float | None:
    """product(scores) / 1000. Returns None if the product is not computable.

    Not computable means: the wrong number of scores, or any score is None.
    A partial product is meaningless under a multiplicative formula — never
    substitute a default score to complete it.
    """
    if len(scores) != _CATEGORY_COUNT or any(s is None for s in scores):
        return None
    product = 1
    for s in scores:
        product *= int(s)
    return product / 1000


def mps_verdict(total: float | None, threshold: float) -> str | None:
    """Compare a total against threshold. None in, None out."""
    if total is None:
        return None
    return (
        "above threshold"
        if total >= threshold
        else "below threshold — requires explicit override rationale to advance"
    )
