"""Hermetic tests for legal register deterministic verifier (T3 / item 25)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from eval.content.legal_register_verifier import (
    ChunkResolution,
    _display_name_for_slug,
    build_claim_rows,
    verify_legal_register,
)
from eval.content.s2_writer import S2Writer


def _run_ts() -> datetime:
    return datetime(2026, 9, 14, 12, 0, 0, 123456, tzinfo=timezone.utc)


def _sample_registers() -> dict[str, list[dict]]:
    quote = (
        "Contractor shall defend, indemnify and hold harmless the property owner, "
        "property manager, and their agents from any liability, loss or other claim"
    )
    return {
        "contract_register": [
            {
                "counterparty_name": "Landlord",
                "source_doc": "Manhattan_Lease_0424.pdf",
                "source_location": "Section: H. Contractor Indemnification Agreement",
                "raw_quote": quote,
            },
            {
                "counterparty_name": "Derived summary",
                "source_doc": "",
                "source_location": "",
                "raw_quote": "",
            },
        ],
        "vendor_register": [],
    }


def _chunk_with_quote(quote: str) -> ChunkResolution:
    return ChunkResolution(
        chunk_id="chunk-lease-001",
        chunk_text=f"Preamble. {quote} trailing text.",
        page_start=12,
        section_header="H. Contractor Indemnification Agreement",
    )


class RecordingSqlExecutor:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def __call__(self, statement: str) -> list[list[str]]:
        self.statements.append(statement)
        normalized = " ".join(statement.split())
        if "row_type = 'completion_marker'" in normalized and normalized.startswith(
            "SELECT"
        ):
            return []
        if "FROM uc13_ale.ingestion.chunks" in normalized and "chunk_id IN" in normalized:
            return [["chunk-lease-001"]]
        return []


def test_build_claim_rows_skips_rows_without_source_doc() -> None:
    rows = build_claim_rows(
        "elder_care",
        registers=_sample_registers(),
        run_id="20260914T120000Z-legal",
        run_ts=_run_ts(),
        resolve_chunk=lambda *_: None,
    )
    assert len(rows) == 1
    assert rows[0].claim_id == "legal.contract_register.0000"


def test_build_claim_rows_supported_when_quote_in_chunk() -> None:
    quote = _sample_registers()["contract_register"][0]["raw_quote"]
    rows = build_claim_rows(
        "elder_care",
        registers=_sample_registers(),
        run_id="20260914T120000Z-legal",
        run_ts=_run_ts(),
        resolve_chunk=lambda *_: _chunk_with_quote(str(quote)),
    )
    assert rows[0].verdict == "supported"
    assert rows[0].cited_chunk_id == "chunk-lease-001"
    assert rows[0].cited_locator_kind == "section"
    assert rows[0].cited_locator_value == "H. Contractor Indemnification Agreement"


def test_build_claim_rows_unsupported_when_quote_missing_from_primary_chunk() -> None:
    rows = build_claim_rows(
        "elder_care",
        registers=_sample_registers(),
        run_id="20260914T120000Z-legal",
        run_ts=_run_ts(),
        resolve_chunk=lambda *_: ChunkResolution(
            chunk_id="chunk-lease-001",
            chunk_text="Unrelated indemnity language only.",
            page_start=3,
            section_header=None,
        ),
    )
    assert rows[0].verdict == "unsupported"
    assert rows[0].cited_chunk_id == "chunk-lease-001"
    assert rows[0].cited_locator_kind == "page"
    assert rows[0].cited_locator_value == "3"


def test_build_claim_rows_unsupported_when_chunk_unresolved() -> None:
    rows = build_claim_rows(
        "elder_care",
        registers=_sample_registers(),
        run_id="20260914T120000Z-legal",
        run_ts=_run_ts(),
        resolve_chunk=lambda *_: None,
    )
    assert rows[0].verdict == "unsupported"
    assert rows[0].cited_chunk_id is None
    assert rows[0].cited_locator_kind is None


def test_build_claim_rows_rejects_non_list_register_payload() -> None:
    with pytest.raises(ValueError, match="must be a list"):
        build_claim_rows(
            "elder_care",
            registers={"contract_register": {"not": "a list"}},  # type: ignore[arg-type]
            run_id="20260914T120000Z-legal",
            run_ts=_run_ts(),
            resolve_chunk=lambda *_: None,
        )


def test_build_claim_rows_skips_non_object_register_entries() -> None:
    """``unable_to_assess`` stores display-name strings, not traceable row objects."""
    rows = build_claim_rows(
        "elder_care",
        registers={
            "unable_to_assess": [
                "Customer contracts — termination for convenience",
                "Change-of-control clauses",
            ],
            "contract_register": _sample_registers()["contract_register"],
        },
        run_id="20260914T120000Z-legal",
        run_ts=_run_ts(),
        resolve_chunk=lambda *_: None,
    )
    assert len(rows) == 1
    assert rows[0].claim_id == "legal.contract_register.0000"


def test_verify_legal_register_writes_claims_then_marker() -> None:
    recorder = RecordingSqlExecutor()
    legal_payload = {
        column: _sample_registers().get(register, [])
        for column, register in (
            ("contract_register_json", "contract_register"),
            ("vendor_register_json", "vendor_register"),
        )
    }

    def loader(_display: str) -> dict:
        return legal_payload

    n_claims = verify_legal_register(
        "elder_care",
        "20260914T120000Z-legal",
        sql_executor=recorder,
        legal_row_loader=loader,
        chunk_resolver=lambda *_: _chunk_with_quote(
            str(_sample_registers()["contract_register"][0]["raw_quote"])
        ),
        run_ts=_run_ts(),
    )

    assert n_claims == 1
    assert len(recorder.statements) == 5
    assert recorder.statements[0].strip().upper().startswith("SELECT")
    assert "chunk_id IN" in recorder.statements[1]
    assert "INSERT" in recorder.statements[2].upper()
    assert recorder.statements[3].strip().upper().startswith("SELECT")
    assert "completion_marker" in recorder.statements[4]
    assert "deterministic_verifier" in recorder.statements[4]


def test_verify_legal_register_propagates_invalid_json_as_value_error() -> None:
    recorder = RecordingSqlExecutor()

    def loader(_display: str) -> dict:
        return {"contract_register_json": "{not-json"}

    with pytest.raises(ValueError, match="invalid JSON"):
        verify_legal_register(
            "elder_care",
            "20260914T120000Z-legal",
            sql_executor=recorder,
            legal_row_loader=loader,
            chunk_resolver=lambda *_: None,
        )

    assert len(recorder.statements) == 0


def test_s2_writer_accepts_verifier_claim_row_shape() -> None:
    quote = str(_sample_registers()["contract_register"][0]["raw_quote"])
    row = build_claim_rows(
        "elder_care",
        registers=_sample_registers(),
        run_id="20260914T120000Z-legal",
        run_ts=_run_ts(),
        resolve_chunk=lambda *_: _chunk_with_quote(quote),
    )[0]
    recorder = RecordingSqlExecutor()
    writer = S2Writer(catalog="uc13_ale", sql_executor=recorder)
    writer.write_claims(
        "elder_care",
        "legal_register",
        "20260914T120000Z-legal",
        _run_ts(),
        [row],
        chunk_id_resolver=lambda ids: ids,
    )
    assert len(recorder.statements) == 2


def test_build_claim_rows_locator_null_when_chunk_carries_neither_grain() -> None:
    """HALT-31 third branch: claim source_location must not fabricate a locator."""
    rows = build_claim_rows(
        "elder_care",
        registers={
            "contract_register": [
                {
                    "counterparty_name": "Landlord",
                    "source_doc": "Manhattan_Lease_0424.pdf",
                    "source_location": "page 7",
                    "raw_quote": "some quoted clause text here",
                }
            ]
        },
        run_id="20260914T120000Z-legal",
        run_ts=_run_ts(),
        resolve_chunk=lambda *_: ChunkResolution(
            chunk_id="chunk-no-grain",
            chunk_text="some quoted clause text here",
            page_start=None,
            section_header=None,
        ),
    )
    assert rows[0].verdict == "supported"
    assert rows[0].cited_chunk_id == "chunk-no-grain"
    assert rows[0].cited_locator_kind is None
    assert rows[0].cited_locator_value is None


def test_build_claim_rows_supported_when_quote_in_sibling_chunk() -> None:
    quote = str(_sample_registers()["contract_register"][0]["raw_quote"])
    primary = ChunkResolution(
        chunk_id="chunk-primary",
        chunk_text="Unrelated indemnity language only.",
        page_start=3,
        section_header=None,
    )
    sibling = ChunkResolution(
        chunk_id="chunk-sibling",
        chunk_text=f"Preamble. {quote} trailing text.",
        page_start=4,
        section_header="H. Contractor Indemnification Agreement",
    )

    rows = build_claim_rows(
        "elder_care",
        registers=_sample_registers(),
        run_id="20260914T120000Z-legal",
        run_ts=_run_ts(),
        resolve_chunk=lambda *_: primary,
        enumerate_document_chunks=lambda _doc: [primary, sibling],
    )
    assert rows[0].verdict == "supported"
    assert rows[0].cited_chunk_id == "chunk-sibling"
    assert rows[0].cited_locator_kind == "section"
    assert rows[0].cited_locator_value == "H. Contractor Indemnification Agreement"


def test_build_claim_rows_contradicted_when_prefix_matches_but_full_quote_does_not() -> None:
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
                "Contractor shall defend indemnify and hold harmless the property owner "
                "from a completely different obligation"
            ),
            page_start=12,
            section_header="H",
        ),
        enumerate_document_chunks=lambda _doc: [],
    )
    assert rows[0].verdict == "contradicted"
    assert rows[0].cited_chunk_id == "chunk-prefix-only"


def test_build_claim_rows_requires_full_quote_not_prefix_anchor() -> None:
    quote = (
        "Contractor shall defend indemnify and hold harmless the property owner "
        "property manager and their agents from any liability loss or other claim"
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
                "Contractor shall defend indemnify and hold harmless the property owner "
                "property manager and their agents only"
            ),
            page_start=12,
            section_header="H",
        ),
    )
    assert rows[0].verdict == "contradicted"


def test_display_name_for_slug_maps_elder_care() -> None:
    assert _display_name_for_slug("elder_care") == "Elder Care"


def test_display_name_for_slug_maps_clearsulting() -> None:
    assert _display_name_for_slug("clearsulting") == "Clearsulting"


def test_display_name_for_slug_maps_gkf_not_title_case() -> None:
    assert _display_name_for_slug("gkf") == "GKF"
    assert _display_name_for_slug("gkf") != "Gkf"


def test_display_name_for_slug_maps_spg_not_title_case() -> None:
    assert _display_name_for_slug("spg") == "SPG"
    assert _display_name_for_slug("spg") != "Spg"


def test_build_claim_rows_canonicalizes_gkf_without_space() -> None:
    rows = build_claim_rows(
        "GKF",
        registers=_sample_registers(),
        run_id="20260914T120000Z-legal",
        run_ts=_run_ts(),
        resolve_chunk=lambda *_: None,
    )
    assert rows[0].company == "gkf"


def test_verify_legal_register_canonicalizes_gkf_without_space() -> None:
    recorder = RecordingSqlExecutor()
    legal_payload = {
        column: _sample_registers().get(register, [])
        for column, register in (
            ("contract_register_json", "contract_register"),
            ("vendor_register_json", "vendor_register"),
        )
    }
    seen_displays: list[str] = []

    def loader(display: str) -> dict:
        seen_displays.append(display)
        return legal_payload

    n_claims = verify_legal_register(
        "GKF",
        "20260914T120000Z-legal",
        sql_executor=recorder,
        legal_row_loader=loader,
        chunk_resolver=lambda *_: None,
        run_ts=_run_ts(),
    )

    assert n_claims == 1
    assert seen_displays == ["GKF"]
    inserts = [stmt for stmt in recorder.statements if "INSERT" in stmt.upper()]
    assert inserts
    assert all("'gkf'" in stmt for stmt in inserts)
    assert all("'GKF'" not in stmt for stmt in inserts)


def test_verify_legal_register_folded_gkf_slug_maps_warehouse_display() -> None:
    """Already-folded ``gkf`` must resolve warehouse ``GKF``, not title-case ``Gkf``."""
    recorder = RecordingSqlExecutor()
    legal_payload = {
        column: _sample_registers().get(register, [])
        for column, register in (
            ("contract_register_json", "contract_register"),
            ("vendor_register_json", "vendor_register"),
        )
    }
    seen_displays: list[str] = []

    def loader(display: str) -> dict:
        seen_displays.append(display)
        return legal_payload

    verify_legal_register(
        "gkf",
        "20260914T120000Z-legal",
        sql_executor=recorder,
        legal_row_loader=loader,
        chunk_resolver=lambda *_: None,
        run_ts=_run_ts(),
    )

    assert seen_displays == ["GKF"]
    inserts = [stmt for stmt in recorder.statements if "INSERT" in stmt.upper()]
    assert inserts
    assert all("'gkf'" in stmt for stmt in inserts)
