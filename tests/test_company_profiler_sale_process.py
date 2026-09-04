"""company_profiler: the `sale_process` field (who is bringing the company to
market) and the schema evolution it needs.

`sale_process` is the source for the executive review's "brought to market by
<banker>" line. The column is new, so it has to survive the two ways this
table is created: a fresh catalog (CREATE TABLE) and an existing one, where
`CREATE TABLE IF NOT EXISTS` is a no-op and the upsert is a Delta MERGE that
does not evolve the schema on its own (databricks/CLAUDE.md).
"""

from __future__ import annotations

from pathlib import Path

from jobs.scripts.company_profiler import _ensure_profile_columns

_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "databricks"
    / "jobs"
    / "scripts"
    / "company_profiler.py"
).read_text(encoding="utf-8")


class _StubSpark:
    """Minimal spark double: `table(...).columns` plus a recorded `sql`."""

    def __init__(self, columns: list[str] | None, fail: bool = False) -> None:
        self._columns = columns
        self._fail = fail
        self.statements: list[str] = []

    def table(self, _name: str):
        if self._fail:
            raise RuntimeError("table not readable")
        return type("_Df", (), {"columns": list(self._columns or [])})()

    def sql(self, statement: str):
        self.statements.append(statement)


def test_missing_column_is_added_to_an_existing_table():
    spark = _StubSpark(["company_name", "banked", "banked_note"])
    _ensure_profile_columns(spark, "cat.classification.company_profile")
    assert spark.statements == [
        "ALTER TABLE cat.classification.company_profile ADD COLUMNS (sale_process STRING)"
    ]


def test_no_alter_is_issued_when_the_column_already_exists():
    spark = _StubSpark(["company_name", "sale_process"])
    _ensure_profile_columns(spark, "cat.classification.company_profile")
    assert spark.statements == []


def test_column_check_is_case_insensitive():
    spark = _StubSpark(["COMPANY_NAME", "SALE_PROCESS"])
    _ensure_profile_columns(spark, "cat.classification.company_profile")
    assert spark.statements == []


def test_unreadable_table_never_blocks_profiling():
    spark = _StubSpark(None, fail=True)
    _ensure_profile_columns(spark, "cat.classification.company_profile")
    assert spark.statements == []


def test_sale_process_is_declared_in_the_ddl_prompt_schema_and_write():
    # The four places that must agree, per the MERGE rule in CLAUDE.md.
    assert "sale_process            STRING," in _SOURCE          # CREATE TABLE
    assert '"sale_process": "how the company is being brought to market' in _SOURCE  # LLM template
    assert 'StructField("sale_process",            StringType(),           True),' in _SOURCE
    assert 'sale_process=profile.get("sale_process"),' in _SOURCE  # write Row


def test_prompt_forbids_guessing_an_advisor_name():
    assert "never guess a firm name" in _SOURCE
