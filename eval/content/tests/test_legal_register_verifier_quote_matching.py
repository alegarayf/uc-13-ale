"""Hermetic tests for legal_register quote-vs-chunk matching (T6, iterate-pack-now-slice;
extended by T3, ledger-close-now-slice).

Covers the live failure shapes found in the GKF and SPG ``legal_register``
verifier runs (``.dev/plans/eval-signal-foldback-m8-root-cause/artifacts/T3-*``
and the ``20260828T114034Z-711c`` / ``20260828T114102Z-9dbd`` re-runs):

1. GKF: PDF-extracted ``chunk_text`` carries Unicode curly quotes/apostrophes
   and inline "DocuSign Envelope ID: <guid>" page-break watermarks that an
   ASCII, watermark-free ``raw_quote`` cannot literally contain.
2. GKF/SPG: ``raw_quote`` is a verbatim mid-sentence truncation of the source
   with a spurious trailing period appended (the real sentence continues past
   the quoted span).
3. GKF (T3): ``raw_quote`` reproduces a markdown-table row (e.g.
   ``insurance_register.0002``, run ``20260828T114034Z-711c``) as flat text,
   while ``chunk_text`` still carries the ``|`` cell delimiters.
4. SPG (T3): ``raw_quote`` transcribes a source-quoted defined term with a
   different quote-mark style than the source uses (e.g.
   ``privacy_security_register.0000``, run ``20260828T114102Z-9dbd`` —
   ``raw_quote`` uses ``'Agreement'``, the source PDF uses ``"Agreement"``).

Also proves the fail-closed guarantee (S-61) still holds: a quote that is
genuinely absent from the chunk — including one that merely looks close via
noise stripped by this fix, or one that elides real content mid-quote
(a dropped connective word, a dropped sentence, or a dropped inline
parenthetical) — must not be admitted. T3's remaining GKF/SPG unresolved
claims (``employment_register.0001`` GKF, ``insurance_register.0008`` GKF,
``insurance_register.0000`` SPG, ``ip_register.0000`` SPG) are exactly this
shape and are intentionally left unresolved — see
``.dev/plans/ledger-close-now-slice/decision-logs/T3.md``.
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
# Positive path — T3 (ledger-close-now-slice) shape: markdown-table pipes.
# ---------------------------------------------------------------------------


def test_markdown_table_pipes_stripped_for_matching() -> None:
    """GKF ``insurance_register.0002`` (run ``20260828T114034Z-711c``): raw_quote
    reproduces a table row as flat text; chunk_text keeps the ``|`` delimiters.

    Mutation check performed while developing this fix: reverting the
    ``folded.replace("|", " ")`` line in ``_normalize_quote`` makes this test
    fail, confirming the pipe fold — not incidental whitespace collapsing —
    is what admits the match.
    """
    quote = "Premises Medical Expense At least $15,000"
    chunk_text = (
        "| Coverage | Minimum Limits |\n"
        "|---|---|\n"
        "| Premises Medical Expense | At least $15,000 |\n"
        "| Employment Practices Liability | In an amount not less than "
        "$1,000,000 per claim/$1,000,000 aggregate |"
    )
    assert _quote_supported_by_chunk(quote, chunk_text)


# ---------------------------------------------------------------------------
# Positive path — T3 (ledger-close-now-slice) shape: quote-mark-style fold.
# ---------------------------------------------------------------------------


def test_quote_mark_style_mismatch_folds_to_same_match() -> None:
    """SPG ``privacy_security_register.0000`` (run ``20260828T114102Z-9dbd``):
    raw_quote transcribes a source-quoted defined term with single quotes;
    the source PDF itself uses double quotes around the same term.

    Mutation check performed while developing this fix: reverting the
    ``folded.replace('"', "'")`` line in ``_normalize_quote`` makes this test
    fail, confirming the quote-mark fold is load-bearing here (the quote is
    otherwise a verbatim prefix of the chunk).
    """
    quote = (
        "This Business Associate Agreement ('Agreement') is entered into the "
        "[XX] day of [MONTH], [YEAR] between Shared Practices Group, LLC"
    )
    chunk_text = (
        'This Business Associate Agreement ("Agreement") is entered into the '
        "[XX] day of [MONTH], [YEAR] between Shared Practices Group, LLC, and "
        "[Contractor Company and/or Full Name]."
    )
    assert _quote_supported_by_chunk(quote, chunk_text)


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


def test_dropped_connective_word_stays_unsupported() -> None:
    """GKF ``employment_register.0001`` (run ``20260828T114034Z-711c``): the
    source reads "...and *that* nothing...", raw_quote drops the connective
    "that". Left unresolved deliberately (see T3 decision log) rather than
    folding stray connective words — that lever is unbounded and risks
    admitting genuine paraphrase, not just formatting noise.
    """
    quote = (
        "Developer shall be an independent contractor, and nothing in this "
        "Agreement is intended to constitute either party an agent, legal "
        "representative, subsidiary, joint venturer, partner, employee or "
        "servant."
    )
    chunk_text = (
        "It is understood and agreed by the parties hereto that this "
        "Agreement does not create a fiduciary relationship between them, "
        "that Developer shall be an independent contractor, and that "
        "nothing in this Agreement is intended to constitute either party "
        "an agent, legal representative, subsidiary, joint venturer, "
        "partner, employee or servant of the other for any purpose "
        "whatsoever, and Developer covenants not to assert otherwise in "
        "any forum."
    )
    assert not _quote_supported_by_chunk(quote, chunk_text)


def test_dropped_middle_sentence_without_ellipsis_stays_unsupported() -> None:
    """GKF ``insurance_register.0008`` (run ``20260828T114034Z-711c``): raw_quote
    splices two non-adjacent sentences with the middle sentence dropped and no
    ellipsis marker — a real elision, not just noise, and must stay unsupported.
    """
    quote = (
        "Policy limits and coverages may not be shared across different "
        "operating entities or schools. All policies, except for Workers' "
        "Compensation, must be written on a primary and non-contributory "
        "basis."
    )
    chunk_text = (
        "Policy limits and coverages may not be shared across different "
        "operating entities or schools. All required policies are to be "
        "written on an occurrence basis except for Employment Practices "
        "Liability, Cyber Liability and Media Liability, which may be "
        "written on a claims made basis. All policies, except for Workers' "
        "Compensation, must be written on a primary and non-contributory "
        "basis and provide a waiver of subrogation for the entities listed "
        "below."
    )
    assert not _quote_supported_by_chunk(quote, chunk_text)


def test_dropped_inline_parenthetical_stays_unsupported() -> None:
    """SPG ``ip_register.0000`` (run ``20260828T114102Z-9dbd``): raw_quote drops
    an inline defined-term parenthetical (``(the "Disclosing Party")``) that
    the source inserts mid-clause. Left unresolved deliberately: folding
    inline parentheticals generically would risk admitting quotes that elide
    substantive qualifying content, not just an aside.
    """
    quote = (
        "each party, and its respective agents (the 'Recipient'), will have "
        "personal access to and knowledge of the other party's information "
        "of a proprietary and confidential nature"
    )
    chunk_text = (
        'LMP and Client each hereby acknowledge that, during the term of '
        'this Agreement, each party, and its respective agents (the '
        '"Recipient"), will have personal access to and knowledge of the '
        'other party\'s (the "Disclosing Party") information of a '
        "proprietary and confidential nature and not otherwise part of the "
        "public domain."
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
