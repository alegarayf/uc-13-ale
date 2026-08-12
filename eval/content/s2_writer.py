"""S2 score-table writer — spec §8.8 / §9 shared storage foundation."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Literal, Protocol

logger = logging.getLogger(__name__)

TABLE_SUFFIX = "eval.s2_scores"

SURFACES = frozenset({"fta_numeric", "legal_register", "exec_summary"})
ROW_TYPES = frozenset({"claim", "completion_marker"})
CLAIM_VERDICTS = frozenset({"supported", "contradicted", "unsupported"})
WRITERS = frozenset({"deterministic_verifier", "judge_harness", "human_spot_check"})
LOCATOR_KINDS = frozenset({"page", "section", "cell", "char_offset"})
NUMERIC_UNITS = frozenset(
    {"USD", "USD_k", "USD_m", "USD_bn", "percent", "ratio", "count", "days"}
)

# Time-sortable run_id: compact UTC timestamp + short suffix (§9.1).
_RUN_ID_RE = re.compile(r"^\d{8}T\d{6}Z-[a-z0-9]+$")


class SqlExecutor(Protocol):
    """Minimal warehouse SQL surface (mocked in unit tests)."""

    def __call__(self, statement: str) -> list[list[Any]]: ...


@dataclass(frozen=True)
class S2ScoreRow:
    """Logical §8.8 claim row; completion markers use ``from_completion_marker``."""

    company: str
    surface: str
    run_id: str
    run_ts: datetime
    row_type: Literal["claim", "completion_marker"]
    claim_id: str | None = None
    verdict: str | None = None
    rationale: str | None = None
    writer: str | None = None
    asserted_magnitude: Decimal | None = None
    asserted_unit: str | None = None
    extracted_magnitude: Decimal | None = None
    extracted_unit: str | None = None
    cited_chunk_id: str | None = None
    cited_locator_kind: str | None = None
    cited_locator_value: str | None = None
    judge_verdict_advisory: str | None = None

    @classmethod
    def from_completion_marker(
        cls,
        *,
        company: str,
        surface: str,
        run_id: str,
        run_ts: datetime,
        writer: str,
    ) -> S2ScoreRow:
        return cls(
            company=company,
            surface=surface,
            run_id=run_id,
            run_ts=run_ts,
            row_type="completion_marker",
            writer=writer,
        )


def _ensure_utc_microsecond(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    else:
        ts = ts.astimezone(timezone.utc)
    if ts.microsecond == 0 and ts.strftime("%f") == "000000":
        return ts
    return ts.replace(microsecond=ts.microsecond)


def _sql_str(value: str) -> str:
    return value.replace("'", "''")


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        ts = _ensure_utc_microsecond(value)
        return f"TIMESTAMP '{ts.strftime('%Y-%m-%d %H:%M:%S.%f')}'"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return f"'{_sql_str(str(value))}'"


def _validate_run_id(run_id: str) -> None:
    if not _RUN_ID_RE.match(run_id):
        raise ValueError(
            "run_id must be time-sortable: YYYYMMDDTHHMMSSZ-<suffix> "
            f"(got {run_id!r})"
        )


def _validate_magnitude_unit_pair(
    magnitude: Decimal | None,
    unit: str | None,
    *,
    field_prefix: str,
) -> None:
    if (magnitude is None) != (unit is None):
        raise ValueError(
            f"{field_prefix} magnitude and unit must both be set or both null"
        )
    if unit is not None and unit not in NUMERIC_UNITS:
        raise ValueError(f"{field_prefix} unit {unit!r} not in §16 numeric unit vocabulary")


def _validate_claim_row(row: S2ScoreRow) -> None:
    if row.row_type != "claim":
        raise ValueError("expected claim row")
    if row.writer is not None:
        raise ValueError("claim rows must not carry writer")
    if row.claim_id is None or not row.claim_id.strip():
        raise ValueError("claim rows require claim_id")
    if row.verdict not in CLAIM_VERDICTS:
        raise ValueError(f"claim verdict {row.verdict!r} not in §16 vocabulary")
    _validate_magnitude_unit_pair(
        row.asserted_magnitude, row.asserted_unit, field_prefix="asserted"
    )
    _validate_magnitude_unit_pair(
        row.extracted_magnitude, row.extracted_unit, field_prefix="extracted"
    )
    if row.cited_locator_kind is not None and row.cited_locator_kind not in LOCATOR_KINDS:
        raise ValueError(
            f"cited_locator_kind {row.cited_locator_kind!r} not in §16 vocabulary"
        )
    if row.judge_verdict_advisory is not None and row.judge_verdict_advisory not in CLAIM_VERDICTS:
        raise ValueError(
            f"judge_verdict_advisory {row.judge_verdict_advisory!r} not in §16 vocabulary"
        )


def _validate_marker_row(row: S2ScoreRow) -> None:
    if row.row_type != "completion_marker":
        raise ValueError("expected completion_marker row")
    if row.writer not in WRITERS:
        raise ValueError(f"marker writer {row.writer!r} not in §16 vocabulary")
    nullable_claim_fields = (
        row.claim_id,
        row.verdict,
        row.rationale,
        row.asserted_magnitude,
        row.asserted_unit,
        row.extracted_magnitude,
        row.extracted_unit,
        row.cited_chunk_id,
        row.cited_locator_kind,
        row.cited_locator_value,
        row.judge_verdict_advisory,
    )
    if any(v is not None for v in nullable_claim_fields):
        raise ValueError("completion_marker rows must have null claim columns")


def _row_to_insert_values(row: S2ScoreRow) -> str:
    columns = (
        "company",
        "surface",
        "run_id",
        "run_ts",
        "row_type",
        "claim_id",
        "verdict",
        "rationale",
        "writer",
        "asserted_magnitude",
        "asserted_unit",
        "extracted_magnitude",
        "extracted_unit",
        "cited_chunk_id",
        "cited_locator_kind",
        "cited_locator_value",
        "judge_verdict_advisory",
    )
    values = (
        _sql_literal(row.company),
        _sql_literal(row.surface),
        _sql_literal(row.run_id),
        _sql_literal(row.run_ts),
        _sql_literal(row.row_type),
        _sql_literal(row.claim_id),
        _sql_literal(row.verdict),
        _sql_literal(row.rationale),
        _sql_literal(row.writer),
        _sql_literal(row.asserted_magnitude),
        _sql_literal(row.asserted_unit),
        _sql_literal(row.extracted_magnitude),
        _sql_literal(row.extracted_unit),
        _sql_literal(row.cited_chunk_id),
        _sql_literal(row.cited_locator_kind),
        _sql_literal(row.cited_locator_value),
        _sql_literal(row.judge_verdict_advisory),
    )
    return f"({', '.join(values)})"


class S2Writer:
    """Append-only writer for ``{catalog}.eval.s2_scores``."""

    def __init__(
        self,
        *,
        catalog: str = "uc13_ale",
        sql_executor: SqlExecutor | None = None,
    ) -> None:
        self.catalog = catalog
        self._table = f"{catalog}.{TABLE_SUFFIX}"
        self._sql = sql_executor

    @property
    def table_fqn(self) -> str:
        return self._table

    def _execute(self, statement: str) -> list[list[Any]]:
        if self._sql is None:
            raise RuntimeError("sql_executor is required for warehouse writes")
        return self._sql(statement)

    def _guard_no_completion_marker(
        self,
        *,
        company: str,
        surface: str,
        run_id: str,
    ) -> None:
        statement = f"""
            SELECT 1
            FROM {self._table}
            WHERE company = '{_sql_str(company)}'
              AND surface = '{_sql_str(surface)}'
              AND run_id = '{_sql_str(run_id)}'
              AND row_type = 'completion_marker'
            LIMIT 1
        """
        if self._execute(statement):
            raise ValueError(
                f"completion marker already exists for "
                f"({company!r}, {surface!r}, {run_id!r})"
            )

    def _validate_run_header(
        self,
        *,
        company: str,
        surface: str,
        run_id: str,
        run_ts: datetime,
    ) -> None:
        if surface not in SURFACES:
            raise ValueError(f"surface {surface!r} not in §16 vocabulary")
        _validate_run_id(run_id)
        _ensure_utc_microsecond(run_ts)

    def write_claims(
        self,
        company: str,
        surface: str,
        run_id: str,
        run_ts: datetime,
        rows: list[S2ScoreRow],
    ) -> None:
        """Append claim rows after the completion-marker guard query."""
        self._validate_run_header(
            company=company, surface=surface, run_id=run_id, run_ts=run_ts
        )
        self._guard_no_completion_marker(company=company, surface=surface, run_id=run_id)

        if not rows:
            logger.info(
                "s2_write_claims_skipped",
                extra={
                    "event": "s2_write_claims_skipped",
                    "company": company,
                    "surface": surface,
                    "run_id": run_id,
                    "n_claims": 0,
                },
            )
            return

        normalized: list[S2ScoreRow] = []
        for row in rows:
            if (
                row.company != company
                or row.surface != surface
                or row.run_id != run_id
            ):
                raise ValueError("claim row run header mismatch")
            _validate_claim_row(row)
            normalized.append(
                S2ScoreRow(
                    company=row.company,
                    surface=row.surface,
                    run_id=row.run_id,
                    run_ts=_ensure_utc_microsecond(row.run_ts),
                    row_type="claim",
                    claim_id=row.claim_id,
                    verdict=row.verdict,
                    rationale=row.rationale,
                    writer=None,
                    asserted_magnitude=row.asserted_magnitude,
                    asserted_unit=row.asserted_unit,
                    extracted_magnitude=row.extracted_magnitude,
                    extracted_unit=row.extracted_unit,
                    cited_chunk_id=row.cited_chunk_id,
                    cited_locator_kind=row.cited_locator_kind,
                    cited_locator_value=row.cited_locator_value,
                    judge_verdict_advisory=row.judge_verdict_advisory,
                )
            )

        values_sql = ",\n".join(_row_to_insert_values(r) for r in normalized)
        insert_sql = f"""
            INSERT INTO {self._table} (
                company, surface, run_id, run_ts, row_type,
                claim_id, verdict, rationale, writer,
                asserted_magnitude, asserted_unit,
                extracted_magnitude, extracted_unit,
                cited_chunk_id, cited_locator_kind, cited_locator_value,
                judge_verdict_advisory
            ) VALUES
            {values_sql}
        """
        self._execute(insert_sql)
        logger.info(
            "s2_write_claims",
            extra={
                "event": "s2_write_claims",
                "company": company,
                "surface": surface,
                "run_id": run_id,
                "n_claims": len(normalized),
            },
        )

    def write_completion_marker(
        self,
        company: str,
        surface: str,
        run_id: str,
        run_ts: datetime,
        writer: str,
    ) -> None:
        """Append the run's completion marker (written last per §9)."""
        self._validate_run_header(
            company=company, surface=surface, run_id=run_id, run_ts=run_ts
        )
        marker = S2ScoreRow.from_completion_marker(
            company=company,
            surface=surface,
            run_id=run_id,
            run_ts=_ensure_utc_microsecond(run_ts),
            writer=writer,
        )
        _validate_marker_row(marker)

        dup_check = f"""
            SELECT 1
            FROM {self._table}
            WHERE company = '{_sql_str(company)}'
              AND surface = '{_sql_str(surface)}'
              AND run_id = '{_sql_str(run_id)}'
              AND row_type = 'completion_marker'
            LIMIT 1
        """
        if self._execute(dup_check):
            raise ValueError(
                f"completion marker already exists for "
                f"({company!r}, {surface!r}, {run_id!r})"
            )

        insert_sql = f"""
            INSERT INTO {self._table} (
                company, surface, run_id, run_ts, row_type,
                claim_id, verdict, rationale, writer,
                asserted_magnitude, asserted_unit,
                extracted_magnitude, extracted_unit,
                cited_chunk_id, cited_locator_kind, cited_locator_value,
                judge_verdict_advisory
            ) VALUES
            {_row_to_insert_values(marker)}
        """
        self._execute(insert_sql)
        logger.info(
            "s2_write_completion_marker",
            extra={
                "event": "s2_write_completion_marker",
                "company": company,
                "surface": surface,
                "run_id": run_id,
                "n_claims": 0,
            },
        )


def make_sdk_sql_executor() -> SqlExecutor:
    """Build a warehouse SQL executor from repo-root ``.env`` credentials."""
    import os

    from dotenv import load_dotenv

    load_dotenv()

    def _executor(statement: str) -> list[list[Any]]:
        from databricks.sdk import WorkspaceClient

        host = os.environ.get("DATABRICKS_SERVER_HOSTNAME")
        if host and not os.environ.get("DATABRICKS_HOST"):
            os.environ["DATABRICKS_HOST"] = host
        w = WorkspaceClient(
            host=os.environ["DATABRICKS_SERVER_HOSTNAME"],
            token=os.environ["DATABRICKS_TOKEN"],
        )
        warehouse_id = os.environ["DATABRICKS_HTTP_PATH"].rstrip("/").split("/")[-1]
        stmt = w.statement_execution.execute_statement(
            warehouse_id=warehouse_id,
            statement=statement,
            wait_timeout="50s",
        )
        state = stmt.status.state.value if stmt.status else "UNKNOWN"
        if state != "SUCCEEDED":
            message = stmt.status.error.message if stmt.status and stmt.status.error else state
            raise RuntimeError(f"SQL failed ({state}): {message}")
        return stmt.result.data_array if stmt.result else []

    return _executor


def apply_s2_scores_ddl(*, catalog: str = "uc13_ale", sql_executor: SqlExecutor | None = None) -> None:
    """Execute ``databricks/ddl/s2_scores.sql`` against the pinned catalog."""
    from pathlib import Path

    sql_path = Path(__file__).resolve().parents[2] / "databricks" / "ddl" / "s2_scores.sql"
    text = sql_path.read_text(encoding="utf-8").replace("{catalog}", catalog)
    executor = sql_executor or make_sdk_sql_executor()
    # Split on semicolon boundaries (tolerate Windows CRLF in the DDL file).
    import re

    for raw in re.split(r";\s*\r?\n", text):
        statement = raw.strip()
        if not statement or statement.startswith("--"):
            continue
        executor(statement)
