"""Verification pass between ``BundleBuilder.build()`` and the Rainmaker
narrative synthesis — never assert a data room lacks something without
checking for evidence first (docs/plans/connect-all-vdr-er.md Part B, B2).

Root cause this exists for (B1, confirmed against a real run): the Elder
Care executive summary said "Top referral source ... percentages are not
stated in available materials" even though the CIM's "Referral Source Mix"
page WAS ingested — the narrative LLM was correctly following its own
non-fabrication rule over an empty ``revenue_quality.concentration`` field,
but that field is empty because ``customer_quality_agent``'s extraction
schema has no place to put a referral-source mix (it has ``payor_mix_json``,
a different concept). The narrative LLM cannot see chunks it was never
handed, so it has no way to know the difference between "the data room has
nothing on this" and "our schema has nowhere to put what the data room has".

This module closes that gap deterministically, BEFORE the narrative call:
for a small set of narrow, extraction-schema-shaped bundle fields, an empty
value is checked against one cheap company-scoped semantic search. A field
that stays empty on a real check is left alone (a genuine gap). A field with
supporting chunks is reclassified from a blank ("say nothing found") to an
explicit "material exists but wasn't extracted" marker, which the narrative
prompt is instructed to render as such — never as a fabricated figure.

Design constraints (binding): deterministic-first (retrieval + string
matching only — no LLM judge in the default path), catalog-agnostic (works
identically for the CIM-scoped and full-room VDR branches), and this module
must NEVER raise — any internal failure degrades to leaving the bundle
exactly as ``BundleBuilder`` produced it, logged but not fatal.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from agents.exec_summary.bundle_builder import _get_by_path, _is_field_empty

# (bundle path, semantic-search query) — string fields that feed the
# Rainmaker narrative digest (rainmaker_narrative._build_narrative_digest)
# and are prone to reading as a false absence claim when a workstream
# agent's extraction schema has no field for the underlying concept. Extend
# this list as new false negatives are diagnosed (plan Part B, B1) — do NOT
# widen a workstream agent's own schema for a single vertical's field name;
# that is company/vertical-specific, this check is not.
_CHECKED_FIELDS: tuple[tuple[str, str], ...] = (
    ("revenue_quality.concentration", "customer concentration referral source mix top customers"),
    ("revenue_quality.retention_notes", "customer retention churn rate"),
    ("revenue_quality.end_market_mix", "end market segment mix"),
    ("company_framing.revenue_model.note", "revenue model pricing structure"),
)

_MIN_SUPPORTING_CHUNKS = 1
_SEARCH_TOP_K = 3
_MIN_CHUNK_LENGTH = 40

RECLASSIFIED_PREFIX = "[DATA ROOM MATERIAL NOT YET EXTRACTED]"


def _reclassified_marker(n_chunks: int, files: list[str]) -> str:
    where = ", ".join(files) if files else "the data room"
    return (
        f"{RECLASSIFIED_PREFIX} {n_chunks} matching passage(s) found in {where} — "
        "present in the data room but not captured by the current extraction; "
        "flagged for manual review rather than reported as absent."
    )


def _set_by_path(obj: dict, path: str, value: Any) -> None:
    """Set a plain dotted path (no `[]`/`.*` suffixes — the whitelist above
    only ever uses simple nested dict paths)."""
    parts = path.split(".")
    cur = obj
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value


def verify_bundle_claims(
    bundle: dict[str, Any],
    spark: Any,
    catalog: str,
    company_name: str,
    embedding_endpoint: str = "databricks-bge-large-en",
) -> dict[str, Any]:
    """Return a copy of ``bundle`` with false-absence fields reclassified.

    Checks only the fields in ``_CHECKED_FIELDS`` that are currently empty —
    a populated field is never touched or second-guessed. Never raises: any
    failure (retrieval error, missing index, etc.) leaves that field, and on
    an unexpected top-level error the whole bundle, exactly as passed in.
    """
    result = deepcopy(bundle)

    try:
        from agents.shared.retrieval import semantic_search
    except Exception as exc:  # pragma: no cover - import failure only
        print(f"[absence_check] retrieval unavailable, skipping verification: {exc!r}")
        return result

    for path, query in _CHECKED_FIELDS:
        try:
            if not _is_field_empty(result, path):
                continue  # a real value is already present — nothing to verify

            chunks = semantic_search(
                query=query,
                spark=spark,
                top_k=_SEARCH_TOP_K,
                company_name=company_name,
                catalog=catalog,
                min_chunk_length=_MIN_CHUNK_LENGTH,
                embedding_endpoint=embedding_endpoint,
            ).chunks
            if len(chunks) < _MIN_SUPPORTING_CHUNKS:
                continue  # genuinely nothing found — leave the absence claim as-is

            files = sorted({
                str(getattr(c, "file_name", "") or "")
                for c in chunks
                if getattr(c, "file_name", "")
            })
            marker = _reclassified_marker(len(chunks), files)
            _set_by_path(result, path, marker)
            print(
                f"[absence_check] demoted: {path} ← {len(chunks)} chunk(s) "
                f"in {', '.join(files) or 'unknown file'}"
            )
        except Exception as exc:  # noqa: BLE001 - must never raise (module contract)
            print(f"[absence_check] check failed for {path!r}, leaving unchanged: {exc!r}")
            continue

    return result
