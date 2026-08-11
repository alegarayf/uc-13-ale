from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from eval.retrieval.companies import (
    DEFAULT_COMPANY_SLUG,
    UnnormalizableCompanySlugError,
    canonical_company_slug,
    resolve_company_slug,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_VECTORS_PATH = _REPO_ROOT / ".dev" / "eval-program" / "company_slug_vectors.yaml"

GOLDEN_VECTOR_CLASSES = frozenset(
    {
        "bounding_punctuation",
        "internal_runs",
        "whitespace",
        "mixed_case",
        "non_ascii",
        "fold_to_empty",
    }
)


def _load_vectors() -> list[dict[str, str]]:
    if not _VECTORS_PATH.is_file():
        pytest.skip(
            f"company_slug_vectors.yaml absent at {_VECTORS_PATH} — M0 item 10a not landed",
            allow_module_level=True,
        )
    payload = yaml.safe_load(_VECTORS_PATH.read_text(encoding="utf-8"))
    return list(payload["vectors"])


_VECTORS = _load_vectors()


@pytest.mark.parametrize("vector", _VECTORS, ids=[v["display"] for v in _VECTORS])
def test_canonical_company_slug_matches_write_expected(vector: dict[str, str]) -> None:
    display = vector["display"]
    write_expected = vector["write_expected"]
    if write_expected == "error":
        with pytest.raises(UnnormalizableCompanySlugError):
            canonical_company_slug(display)
        return
    assert canonical_company_slug(display) == write_expected


def test_golden_vector_classes_cover_full_vocabulary() -> None:
    classes = {row["class"] for row in _VECTORS}
    assert classes == GOLDEN_VECTOR_CLASSES


def test_resolve_company_slug_delegates_to_canonical_fold() -> None:
    assert resolve_company_slug("Elder Care") == DEFAULT_COMPANY_SLUG


def test_hyphen_slug_form_is_not_produced_for_elder_care() -> None:
    assert canonical_company_slug("Elder Care") == "elder_care"
    assert canonical_company_slug("Elder Care") != "elder-care"
