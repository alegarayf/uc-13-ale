"""BasisCrossCheck (Option D) — projection vs historical source mismatch detection.

Compares ``opex_breakdown`` and ``revenue_trend`` record citations
(``source_doc`` + ``source_location``, case-insensitive) to detect when OPEX
figures come from projection / pro-forma / model sources while revenue figures
come from historical / reported sources, or the reverse.

Detection patterns (case-insensitive substring match on combined doc + location):

  Projection / model basis:
    projection, pro forma, pro-forma, forecast, financial model, projected,
    model assumptions

  Historical / reported basis:
    historical, reported, audited, actual, management accounts, diligence adjusted,
    p&l summary

Ambiguous strings matching both pattern groups are treated as ``unknown`` to limit
false positives on labels like "Historical Pro Forma bridge".

Output shape matches LLM ``discrepancies_found`` entries with
``metric: "basis_mismatch"``. Callers append results; existing LLM discrepancies
must not be overwritten (D6).
"""

from __future__ import annotations

_BASIS_PROJECTION_PATTERNS: tuple[str, ...] = (
    "projection",
    "pro forma",
    "pro-forma",
    "proforma",
    "forecast",
    "financial model",
    "projected",
    "model assumptions",
)

_BASIS_HISTORICAL_PATTERNS: tuple[str, ...] = (
    "historical",
    "reported",
    "audited",
    "actual",
    "management accounts",
    "diligence adjusted",
    "p&l summary",
)

# Filename hints when section headers are sparse.
_PROJECTION_DOC_HINTS: tuple[str, ...] = (
    "model",
    "projection",
    "forecast",
)

_HISTORICAL_DOC_HINTS: tuple[str, ...] = (
    "p&l",
    "profit",
    "loss",
    "financials",
    "accounts",
    "audited",
    "tax return",
)


def _citation_text(record: dict) -> str:
    doc = (record.get("source_doc") or "").strip()
    loc = (record.get("source_location") or "").strip()
    return f"{doc} {loc}".strip().lower()


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in text for pattern in patterns)


def classify_basis(record: dict) -> str:
    """Classify a single record citation as projection, historical, or unknown."""
    text = _citation_text(record)
    if not text:
        return "unknown"

    is_projection = _matches_any(text, _BASIS_PROJECTION_PATTERNS)
    is_historical = _matches_any(text, _BASIS_HISTORICAL_PATTERNS)

    doc_only = (record.get("source_doc") or "").strip().lower()
    if not is_projection and doc_only:
        is_projection = _matches_any(doc_only, _PROJECTION_DOC_HINTS)
    if not is_historical and doc_only:
        is_historical = _matches_any(doc_only, _HISTORICAL_DOC_HINTS)

    if is_projection and is_historical:
        return "unknown"
    if is_projection:
        return "projection"
    if is_historical:
        return "historical"
    return "unknown"


def _records_by_basis(records: list[dict], basis: str) -> list[dict]:
    return [rec for rec in records if classify_basis(rec) == basis]


def _format_citation(record: dict) -> str:
    doc = (record.get("source_doc") or "unknown doc").strip()
    loc = (record.get("source_location") or "unknown location").strip()
    return f"{doc} ({loc})"


def _discrepancy_blob(discrepancy: dict) -> str:
    parts = [
        str(discrepancy.get("metric") or ""),
        str(discrepancy.get("note") or ""),
    ]
    for value in discrepancy.get("conflicting_values") or []:
        parts.append(str(value))
    return " ".join(parts).lower()


def _docs_from_conflicting_values(conflicting_values: list) -> tuple[str, str]:
    docs: list[str] = []
    for value in conflicting_values or []:
        text = str(value).split(":", 1)[-1].strip()
        doc = text.split(" (", 1)[0].strip()
        if doc:
            docs.append(doc)
    if len(docs) >= 2:
        return docs[0], docs[1]
    if len(docs) == 1:
        return docs[0], ""
    return "", ""


def is_duplicate_basis_discrepancy(
    candidate: dict,
    existing_discrepancies: list[dict],
) -> bool:
    """Return True when an existing LLM discrepancy already flags the same file pair."""
    opex_doc, revenue_doc = _docs_from_conflicting_values(
        candidate.get("conflicting_values") or []
    )
    opex_key = opex_doc.lower()
    revenue_key = revenue_doc.lower()
    if not opex_key or not revenue_key:
        return False

    for existing in existing_discrepancies:
        blob = _discrepancy_blob(existing)
        if opex_key in blob and revenue_key in blob:
            return True

    candidate_blob = _discrepancy_blob(candidate)
    for existing in existing_discrepancies:
        if _discrepancy_blob(existing) == candidate_blob:
            return True
    return False


def basis_cross_check(
    opex_breakdown: list[dict],
    revenue_trend: list[dict],
) -> list[dict]:
    """Detect projection vs historical basis mismatch across OPEX and revenue.

    Returns zero or one ``basis_mismatch`` discrepancy dicts for the caller to
    append to ``discrepancies_found``. Does not mutate inputs.
    """
    if not opex_breakdown or not revenue_trend:
        return []

    opex_projection = _records_by_basis(opex_breakdown, "projection")
    opex_historical = _records_by_basis(opex_breakdown, "historical")
    revenue_projection = _records_by_basis(revenue_trend, "projection")
    revenue_historical = _records_by_basis(revenue_trend, "historical")

    opex_rec: dict | None = None
    revenue_rec: dict | None = None

    if opex_projection and revenue_historical:
        opex_rec = opex_projection[0]
        revenue_rec = revenue_historical[0]
        direction = "OPEX from projection/model sources vs revenue from historical/reported sources"
    elif opex_historical and revenue_projection:
        opex_rec = opex_historical[0]
        revenue_rec = revenue_projection[0]
        direction = "OPEX from historical/reported sources vs revenue from projection/model sources"
    else:
        return []

    opex_cite = _format_citation(opex_rec)
    revenue_cite = _format_citation(revenue_rec)

    return [
        {
            "metric": "basis_mismatch",
            "conflicting_values": [
                f"OPEX: {opex_cite}",
                f"Revenue: {revenue_cite}",
            ],
            "note": (
                f"{direction}. Cross-check OPEX and revenue accounting basis before "
                "comparing margins or growth."
            ),
        }
    ]
