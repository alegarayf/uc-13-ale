"""Canonical company display-name → slug folding (spec §8.2 write path)."""

from __future__ import annotations

import re

from eval.retrieval.errors import PreconditionError

_NON_ALNUM_RUN = re.compile(r"[^A-Za-z0-9]+")

# Launch default — Elder Care is the program's primary eval company (spec §12.2 S0 domain).
DEFAULT_COMPANY_DISPLAY = "Elder Care"
DEFAULT_COMPANY_SLUG = "elder_care"


class UnnormalizableCompanySlugError(ValueError):
    """Raised when a display name folds to an empty slug (write-path step 4)."""


def canonical_company_slug(name: str) -> str:
    """Fold a company display name to the canonical underscore slug.

    Implements spec §8.2's four-step total function in pinned order:
    (1) maximal non-[A-Za-z0-9] runs → single ``_``;
    (2) ASCII lowercase;
    (3) strip leading/trailing ``_``;
    (4) empty → raise (write path — never return ``__unnormalizable__``).
    """
    if not isinstance(name, str):
        raise TypeError(f"company name must be str, got {type(name).__name__}")
    folded = _NON_ALNUM_RUN.sub("_", name)
    folded = folded.lower().strip("_")
    if not folded:
        raise UnnormalizableCompanySlugError(
            f"company name folds to empty after normalization: {name!r}"
        )
    return folded


def resolve_company_slug(display_name: str) -> str:
    """Resolve a SharePoint / warehouse display name to the canonical slug."""
    return canonical_company_slug(display_name)


def require_folded_company_slug(company_slug: str) -> str:
    """Guard that a ``company_slug``-typed parameter is already canonical.

    Returns ``company_slug`` unchanged when it equals its own fold (per
    ``canonical_company_slug``'s idempotence). Raises ``PreconditionError``
    for any value that is not a str, or that is not already in folded form —
    including a raw display name or a value that folds to empty.
    """
    if not isinstance(company_slug, str):
        raise PreconditionError(
            f"company_slug must be canonical (already folded): {company_slug!r}"
        )
    try:
        folded = canonical_company_slug(company_slug)
    except UnnormalizableCompanySlugError:
        raise PreconditionError(
            f"company_slug must be canonical (already folded): {company_slug!r}"
        ) from None
    if folded != company_slug:
        raise PreconditionError(
            f"company_slug must be canonical (already folded): {company_slug!r}"
        )
    return company_slug
