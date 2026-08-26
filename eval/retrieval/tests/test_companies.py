from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from eval.retrieval.companies import (
    DEFAULT_COMPANY_SLUG,
    UnnormalizableCompanySlugError,
    _SLUG_TO_DISPLAY,
    canonical_company_slug,
    display_name_for_slug,
    require_folded_company_slug,
    resolve_company_slug,
)
from eval.retrieval.errors import PreconditionError

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


@pytest.mark.parametrize("slug", ["elder_care", "clearsulting", "acme_corp"])
def test_require_folded_company_slug_accepts_folded_slug(slug: str) -> None:
    assert require_folded_company_slug(slug) == slug


def test_require_folded_company_slug_rejects_display_name() -> None:
    with pytest.raises(PreconditionError, match="company_slug must be canonical"):
        require_folded_company_slug("Elder Care")


def test_require_folded_company_slug_rejects_empty() -> None:
    with pytest.raises(PreconditionError, match="company_slug must be canonical"):
        require_folded_company_slug("")


_ONBOARDING_QUEUE_PATH = _REPO_ROOT / "eval" / "program" / "onboarding_queue.yaml"
_ONBOARDING_SLUGS = ("elder_care", "clearsulting", "gkf", "spg")


@pytest.mark.parametrize("slug", _ONBOARDING_SLUGS)
def test_display_name_for_slug_round_trips_to_canonical_slug(slug: str) -> None:
    assert canonical_company_slug(display_name_for_slug(slug)) == slug


def test_slug_to_display_matches_onboarding_queue_pairs() -> None:
    payload = yaml.safe_load(_ONBOARDING_QUEUE_PATH.read_text(encoding="utf-8"))
    expected = {row["slug"]: row["display_name"] for row in payload["companies"]}
    assert _SLUG_TO_DISPLAY == expected


def test_slug_to_display_is_the_four_frozen_pairs() -> None:
    assert _SLUG_TO_DISPLAY == {
        "gkf": "GKF",
        "clearsulting": "Clearsulting",
        "spg": "SPG",
        "elder_care": "Elder Care",
    }


def test_display_name_for_slug_unknown_falls_back_to_title_case() -> None:
    assert display_name_for_slug("acme_corp") == "Acme Corp"
