"""Hermetic tests for legal_register quote-vs-chunk matching (T6, iterate-pack-now-slice).

Covers the two live failure shapes found in the GKF and SPG ``legal_register``
verifier runs (``.dev/plans/eval-signal-foldback-m8-root-cause/artifacts/T3-*``):

1. GKF: PDF-extracted ``chunk_text`` carries Unicode curly quotes/apostrophes
   and inline "DocuSign Envelope ID: <guid>" page-break watermarks that an
   ASCII, watermark-free ``raw_quote`` cannot literally contain.
2. GKF/SPG: ``raw_quote`` is a verbatim mid-sentence truncation of the source
   with a spurious trailing period appended (the real sentence continues past
   the quoted span).

Also proves the fail-closed guarantee (S-61) still holds: a quote that is
genuinely absent from the chunk — including one that merely looks close via
noise stripped by this fix — must not be admitted.
"""

from __future__ import annotations

from eval.content.legal_register_verifier import (
    ChunkResolution,
    _quote_prefix_anchor_in_chunk,
    _quote_supported_by_chunk,
    build_claim_rows,
)


def _run_ts():
    from datetime import datetime, timezone

    return datetime(2026, 9, 14, 12, 0, 0, 123456, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Positive path — GKF failure shape: curly quotes + DocuSign envelope stamp.
# ---------------------------------------------------------------------------


def test_curly_apostrophe_quote_supported_by_ascii_chunk() -> None:
    """SPG shape: PDF apostrophes are Unicode curly quotes; raw_quote is ASCII."""
    quote = (
        "any individual's Protected Health Information that comes within "
        "Contractor's custody, exposure, possession or knowledge"
    )
    chunk_text = (
        "Contractor agrees and acknowledges that any individual\u2019s Protected "
        "Health Information that comes within Contractor\u2019s custody, exposure, "
        "possession or knowledge or is created, maintained, retained, "
        "transmitted, derived, developed, compiled, prepared or used by "
        "Contractor in the course of services under this Agreement."
    )
    assert _quote_supported_by_chunk(quote, chunk_text)


def test_docusign_envelope_watermark_stripped_from_chunk_for_matching() -> None:
    """GKF shape: a DocuSign page-break stamp splits an otherwise verbatim quote."""
    quote = (
        "you shall not, during or after the term of this Preliminary Agreement, "
        "communicate, divulge or use for your benefit or for any other person "
        "or entity any of our trade secrets or other confidential or "
        "proprietary information"
    )
    chunk_text = (
        "you shall not, during or after the term of this Preliminary Agreement, "
        "communicate, divulge or use for your benefit or for any other person "
        "or entity any of our trade secrets or other confidential or\n"
        "DocuSign Envelope ID: 5A93DB35-2CE2-4ED4-B31E-4A9DE7C7B03D\n"
        "proprietary information or compilations, any material in which we "
        "claim copyright protection."
    )
    assert _quote_supported_by_chunk(quote, chunk_text)


# ---------------------------------------------------------------------------
# Positive path — GKF/SPG shared shape: verbatim truncation with a spurious
# trailing period.
# ---------------------------------------------------------------------------


def test_truncated_quote_with_spurious_trailing_period_is_supported() -> None:
    """GKF shape: raw_quote closes with '.' where the source sentence continues."""
    quote = (
        "Any Sub-processor engaged by Franchisee must be approved in advance "
        "by Franchisor. Franchisee shall enter into a written agreement with "
        "each approved Sub-processor containing data protection obligations "
        "not less protective than those in this DPA."
    )
    chunk_text = (
        "7. Sub-processors. Any Sub-processor engaged by Franchisee must be "
        "approved in advance by Franchisor. Franchisee shall enter into a "
        "written agreement with each approved Sub-processor containing data "
        "protection obligations not less protective than those in this DPA "
        "and that complies with Data Protection Laws."
    )
    assert _quote_supported_by_chunk(quote, chunk_text)


def test_build_claim_rows_supported_for_gkf_docusign_and_period_shapes() -> None:
    """End-to-end through build_claim_rows for both companies' failure shapes."""
    registers = {
        "privacy_security_register": [
            {
                "counterparty_name": "Goddard Franchisor LLC",
                "source_doc": "Goddard FDD 2025.pdf",
                "source_location": "Section: 1. Definitions",
                "raw_quote": (
                    "Any Sub-processor engaged by Franchisee must be approved in "
                    "advance by Franchisor. Franchisee shall enter into a written "
                    "agreement with each approved Sub-processor containing data "
                    "protection obligations not less protective than those in "
                    "this DPA."
                ),
            }
        ],
    }
    chunk = ChunkResolution(
        chunk_id="chunk-dpa-326",
        chunk_text=(
            "7. Sub-processors. Any Sub-processor engaged by Franchisee must be "
            "approved in advance by Franchisor. Franchisee shall enter into a "
            "written agreement with each approved Sub-processor containing data "
            "protection obligations not less protective than those in this DPA "
            "and that complies with Data Protection Laws."
        ),
        page_start=326,
        section_header="1. Definitions",
    )
    rows = build_claim_rows(
        "gkf",
        registers=registers,
        run_id="20260826T171705Z-ea6b",
        run_ts=_run_ts(),
        resolve_chunk=lambda *_: chunk,
    )
    assert rows[0].verdict == "supported"
    assert rows[0].cited_chunk_id == "chunk-dpa-326"


# ---------------------------------------------------------------------------
# Negative path / no-regression — S-61 fail-closed must still hold.
# ---------------------------------------------------------------------------


def test_genuinely_unsupported_quote_stays_unsupported_after_normalization() -> None:
    """A quote absent from the chunk must not be admitted by the new folding.

    Mutation check performed manually while developing this fix: reverting
    the trailing-period fallback in ``_quote_supported_by_chunk`` to always
    return ``True`` (instead of requiring the trimmed quote to be contained)
    makes this test fail, confirming it actually exercises the guard.
    """
    quote = "this exact clause language never appears anywhere in the source document"
    chunk_text = (
        "Contractor agrees and acknowledges that any individual\u2019s Protected "
        "Health Information that comes within Contractor\u2019s custody is "
        "confidential.\n"
        "DocuSign Envelope ID: 5A93DB35-2CE2-4ED4-B31E-4A9DE7C7B03D\n"
        "Unrelated trailing boilerplate."
    )
    assert not _quote_supported_by_chunk(quote, chunk_text)
    assert not _quote_prefix_anchor_in_chunk(quote, chunk_text)


def test_trailing_period_fallback_does_not_admit_absent_quote() -> None:
    """Falsifier for the trailing-period fallback specifically.

    Mutation check performed while developing this fix: relaxing the
    fallback branch in ``_quote_supported_by_chunk`` to ``if trimmed: return
    True`` (dropping the ``trimmed in normalized_chunk`` containment check)
    makes this test fail — confirming the containment check, not just the
    period-ending shape, is load-bearing.
    """
    quote = "this exact clause language never appears anywhere in the source."
    chunk_text = (
        "Contractor agrees and acknowledges that any individual\u2019s Protected "
        "Health Information that comes within Contractor\u2019s custody is "
        "confidential and unrelated to the quoted clause."
    )
    assert not _quote_supported_by_chunk(quote, chunk_text)


def test_omitted_middle_sentence_with_ellipsis_stays_unsupported() -> None:
    """A quote that elides real content (ellipsis) is not a verbatim match.

    This mirrors the GKF ``contract_register.0001`` failure shape: the
    extraction condensed two non-adjacent clauses with '...'. That quote is
    not present verbatim anywhere and must remain unsupported — the fix in
    this subtask only folds extraction *noise* (encoding/watermarks/trailing
    punctuation), not elided content.
    """
    quote = (
        "If you give us notice of termination... you cannot be required to "
        "prospectively assent to a release, assignment, novation, waiver or "
        "estoppel which purports to relieve us from liability"
    )
    chunk_text = (
        "the addition of the following language to the end of the second "
        "sentence beginning \u201cIf you give us notice of termination\u201d of "
        "Section 5B: provided that you cannot be required to prospectively "
        "assent to a release, assignment, novation, waiver or estoppel which "
        "purports to relieve us from liability under Indiana Code 23-2-2.7."
    )
    assert not _quote_supported_by_chunk(quote, chunk_text)


def test_build_claim_rows_supported_when_quote_in_chunk_still_passes() -> None:
    """No-regression: an exact, noise-free quote match is unaffected."""
    quote = (
        "Contractor shall defend, indemnify and hold harmless the property "
        "owner, property manager, and their agents from any liability, loss "
        "or other claim"
    )
    rows = build_claim_rows(
        "elder_care",
        registers={
            "contract_register": [
                {
                    "counterparty_name": "Landlord",
                    "source_doc": "Manhattan_Lease_0424.pdf",
                    "source_location": "Section: H",
                    "raw_quote": quote,
                }
            ]
        },
        run_id="20260914T120000Z-legal",
        run_ts=_run_ts(),
        resolve_chunk=lambda *_: ChunkResolution(
            chunk_id="chunk-lease-001",
            chunk_text=f"Preamble. {quote} trailing text.",
            page_start=12,
            section_header="H",
        ),
    )
    assert rows[0].verdict == "supported"


def test_build_claim_rows_still_contradicted_for_prefix_only_match() -> None:
    """No-regression: the existing prefix-anchor 'contradicted' path is untouched."""
    quote = (
        "Contractor shall defend indemnify and hold harmless the property owner "
        "from any liability loss or other claim arising from negligence"
    )
    rows = build_claim_rows(
        "elder_care",
        registers={
            "contract_register": [
                {
                    "counterparty_name": "Landlord",
                    "source_doc": "Manhattan_Lease_0424.pdf",
                    "source_location": "Section: H",
                    "raw_quote": quote,
                }
            ]
        },
        run_id="20260914T120000Z-legal",
        run_ts=_run_ts(),
        resolve_chunk=lambda *_: ChunkResolution(
            chunk_id="chunk-prefix-only",
            chunk_text=(
                "Contractor shall defend indemnify and hold harmless the property "
                "owner from a completely different obligation"
            ),
            page_start=12,
            section_header="H",
        ),
        enumerate_document_chunks=lambda _doc: [],
    )
    assert rows[0].verdict == "contradicted"
