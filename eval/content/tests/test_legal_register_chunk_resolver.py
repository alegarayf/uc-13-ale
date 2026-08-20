"""Hermetic tests for the legal verifier warehouse chunk-resolution cascade (M4 T5 / C8)."""

from __future__ import annotations

from eval.content.legal_register_verifier import (
    _CASCADE_TIER_FILE_AND_SECTION,
    _CASCADE_TIER_FILE_ONLY,
    _CASCADE_TIER_SECTION_AND_PAGE,
    _cascade_tier_clauses,
    _first_ordered_chunk_row,
    _split_joined_source_docs,
    make_warehouse_chunk_resolver,
)


def _tier_of(sql: str) -> str:
    has_page = "c.page_start =" in sql
    has_section = "c.section_header ILIKE" in sql
    if has_page and has_section:
        return _CASCADE_TIER_SECTION_AND_PAGE
    if has_section:
        return _CASCADE_TIER_FILE_AND_SECTION
    return _CASCADE_TIER_FILE_ONLY


def test_split_joined_source_docs_splits_pipe_join() -> None:
    assert _split_joined_source_docs(
        "Manhattan_Lease_0424.pdf | Long_Island_Lease.pdf"
    ) == ("Manhattan_Lease_0424.pdf", "Long_Island_Lease.pdf")
    assert _split_joined_source_docs("single.pdf") == ("single.pdf",)
    assert _split_joined_source_docs("") == ()
    assert _split_joined_source_docs(
        "Manhattan_Lease_0424.pdf | Long_Island_Lease.pdf | Westchester_Lease.pdf"
    ) == (
        "Manhattan_Lease_0424.pdf",
        "Long_Island_Lease.pdf",
        "Westchester_Lease.pdf",
    )


def test_cascade_tier_clauses_order_is_strict_then_loose() -> None:
    names = [name for name, _ in _cascade_tier_clauses(page=12, section_pattern="H")]
    assert names == [
        _CASCADE_TIER_SECTION_AND_PAGE,
        _CASCADE_TIER_FILE_AND_SECTION,
        _CASCADE_TIER_FILE_ONLY,
    ]
    no_page = [name for name, _ in _cascade_tier_clauses(page=None, section_pattern="H")]
    assert no_page == [
        _CASCADE_TIER_FILE_AND_SECTION,
        _CASCADE_TIER_FILE_ONLY,
    ]
    file_only = [name for name, _ in _cascade_tier_clauses(page=None, section_pattern=None)]
    assert file_only == [_CASCADE_TIER_FILE_ONLY]


def test_first_ordered_chunk_row_is_not_result_position() -> None:
    later = ["chunk-z", "later page", 9, "B"]
    earlier = ["chunk-a", "earlier page", 3, "A"]
    null_page = ["chunk-n", "no page", None, "C"]
    picked = _first_ordered_chunk_row([later, null_page, earlier])
    assert picked is not None
    assert picked[0] == "chunk-a"
    same_page_high = ["chunk-m", "tie", 3, "M"]
    same_page_low = ["chunk-b", "tie", 3, "B"]
    tied = _first_ordered_chunk_row([same_page_high, same_page_low])
    assert tied is not None
    assert tied[0] == "chunk-b"
    assert _first_ordered_chunk_row([]) is None


def test_cascade_prefers_section_and_page_over_file_only() -> None:
    """Stricter tier must win even when a looser query would also match.

    Mutation: invert ``_cascade_tier_clauses`` so file-only is first. This test
    then returns ``chunk-loose`` and fails.
    """
    statements: list[str] = []

    def executor(statement: str) -> list[list[object]]:
        statements.append(statement)
        tier = _tier_of(statement)
        if tier == _CASCADE_TIER_SECTION_AND_PAGE:
            return [["chunk-strict", "indemnity clause", 12, "H. Indemnification"]]
        return [["chunk-loose", "cover page", 1, "Cover"]]

    resolver = make_warehouse_chunk_resolver(
        catalog="uc13_ale",
        company_display="Elder Care",
        sql_executor=executor,
    )
    result = resolver(
        "Manhattan_Lease_0424.pdf",
        "Section: H. Indemnification; page 12",
        "quoted text",
    )
    assert result is not None
    assert result.chunk_id == "chunk-strict"
    assert _tier_of(statements[0]) == _CASCADE_TIER_SECTION_AND_PAGE
    assert all("company_name = 'Elder Care'" in sql for sql in statements)


def test_joined_source_doc_tries_each_part_independently() -> None:
    statements: list[str] = []

    def executor(statement: str) -> list[list[object]]:
        statements.append(statement)
        if "Long_Island_Lease.pdf" in statement and _tier_of(statement) == (
            _CASCADE_TIER_SECTION_AND_PAGE
        ):
            return [["chunk-li", "lease body", 5, "Assignment"]]
        return []

    resolver = make_warehouse_chunk_resolver(
        catalog="uc13_ale",
        company_display="Elder Care",
        sql_executor=executor,
    )
    result = resolver(
        "Manhattan_Lease_0424.pdf | Long_Island_Lease.pdf",
        "Section: Assignment; page 5",
        "quoted text",
    )
    assert result is not None
    assert result.chunk_id == "chunk-li"
    assert not any("file_name = 'Manhattan_Lease_0424.pdf | Long_Island_Lease.pdf'" in s for s in statements)
    assert any("file_name = 'Manhattan_Lease_0424.pdf'" in s for s in statements)
    assert any("file_name = 'Long_Island_Lease.pdf'" in s for s in statements)


def test_file_and_section_tried_before_file_only_when_page_absent() -> None:
    statements: list[str] = []

    def executor(statement: str) -> list[list[object]]:
        statements.append(statement)
        if _tier_of(statement) == _CASCADE_TIER_FILE_AND_SECTION:
            return [["chunk-section", "section body", 8, "COI"]]
        return [["chunk-file", "other", 1, "Other"]]

    resolver = make_warehouse_chunk_resolver(
        catalog="uc13_ale",
        company_display="Elder Care",
        sql_executor=executor,
    )
    result = resolver("COI.pdf", "Section: COI table", "quoted text")
    assert result is not None
    assert result.chunk_id == "chunk-section"
    assert _tier_of(statements[0]) == _CASCADE_TIER_FILE_AND_SECTION
    assert "c.page_start =" not in statements[0]


def test_file_only_fallback_still_filters_by_company() -> None:
    statements: list[str] = []

    def executor(statement: str) -> list[list[object]]:
        statements.append(statement)
        return [["chunk-file", "body", 2, None]]

    resolver = make_warehouse_chunk_resolver(
        catalog="uc13_ale",
        company_display="Elder Care",
        sql_executor=executor,
    )
    result = resolver("Retainer.pdf", "", "quoted text")
    assert result is not None
    assert result.chunk_id == "chunk-file"
    assert len(statements) == 1
    assert _tier_of(statements[0]) == _CASCADE_TIER_FILE_ONLY
    assert "company_name = 'Elder Care'" in statements[0]
    assert "ORDER BY c.page_start NULLS LAST, c.chunk_id" in statements[0]
    assert "SPG" not in statements[0]
    assert "Clearsulting" not in statements[0]


def test_resolver_picks_ordered_row_not_first_returned() -> None:
    """C8: selection is page_start then chunk_id, not result-set position / unordered LIMIT 1."""

    def executor(_statement: str) -> list[list[object]]:
        return [
            ["chunk-z", "later page", 9, "B"],
            ["chunk-a", "earlier page", 3, "A"],
        ]

    resolver = make_warehouse_chunk_resolver(
        catalog="uc13_ale",
        company_display="Elder Care",
        sql_executor=executor,
    )
    result = resolver("Retainer.pdf", "", "quoted text")
    assert result is not None
    assert result.chunk_id == "chunk-a"


def test_resolver_returns_none_when_no_tier_matches() -> None:
    resolver = make_warehouse_chunk_resolver(
        catalog="uc13_ale",
        company_display="Elder Care",
        sql_executor=lambda _sql: [],
    )
    assert resolver("Missing.pdf", "Section: X; page 1", "quoted") is None
    assert resolver("", "page 1", "quoted") is None
