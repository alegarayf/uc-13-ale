"""Shared SQL utilities for Phase 3 workstream agents."""


def sql_quote(value: str) -> str:
    """Escape a string value for safe inline SQL interpolation.

    Prefer Spark's named-parameter syntax (``spark.sql(..., args={...})``)
    when available.  Use this helper only on runtimes that do not support
    the ``args`` keyword, or for DDL identifiers where parameter markers are
    not accepted.

    Doubles every single quote in *value* so the result is safe to embed
    between surrounding single quotes in a SQL literal, e.g.::

        spark.sql(f"DELETE FROM {table} WHERE company_name = '{sql_quote(name)}'")

    Does NOT add the surrounding quotes — the caller is responsible for those.
    """
    return value.replace("'", "''")
