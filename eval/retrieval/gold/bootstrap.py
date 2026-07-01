"""Gold label bootstrap — spec §5.12.2 / Appendix A.

Two-pass bootstrap:
  Pass 1 — positives via citation backfill, section-range rules, filename closure.
  Pass 2 — negatives via basis_rule, section_rule, cross_intent_positive.

Pinned ILIKE patterns (Surface 8) live in module constants below.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import yaml

from eval.retrieval.errors import PreconditionError
from eval.retrieval.models import GoldLabel, RetrievalIntent

DEFAULT_COMPANY_NAME = "Elder Care"
DEFAULT_CATALOG = "uc13_ale"

# Appendix A2 — CIM financial section anchors (pinned).
CIM_FILENAME_PATTERN = "%CIM%"
SECTION_RANGE_PAGE_START = 45
SECTION_RANGE_PAGE_END = 50
SECTION_RANGE_SECTION_PATTERNS: tuple[str, ...] = (
    "%Historical P&L%",
    "%EBITDA Adjustment%",
    "%Diligence Adjusted%",
)

# Appendix A4 — basis-rule negatives (pinned).
BASIS_NEGATIVE_SECTION_PATTERNS: tuple[str, ...] = (
    "%Projection%",
    "%Pro Forma Income%",
    "%Forecast%",
)

SECTION_RANGE_INTENT_SUFFIXES: frozenset[str] = frozenset(
    {
        "q1_financial_statements",
        "q2_working_capital",
        "q2_revenue_by_segment",
        "q2_ebitda_and_margins",
        "q4_addback_schedule",
    }
)

HISTORICAL_BASIS_INTENT_IDS: frozenset[str] = frozenset(
    {
        "fta.opex.q1_financial_statements",
        "fta.revenue.q1_financial_statements",
        "fta.ebitda.q1_financial_statements",
    }
)

SECTION_RULE_INTENT_SUFFIXES: frozenset[str] = frozenset({"q1_financial_statements"})

CROSS_INTENT_NEGATIVE_PAIRS: dict[str, str] = {
    "fta.opex.q1_financial_statements": "fta.opex.q3_projected_financials",
    "fta.revenue.q1_financial_statements": "fta.revenue.q3_revenue_by_geography",
    "fta.ebitda.q1_financial_statements": "fta.ebitda.q4_addback_schedule",
}

AGENT_ANALYSIS_TABLE: dict[str, str] = {
    "kpi": "kpi",
    "cqa": "customer_quality",
    "qoe": "quality_of_earnings",
    "bma": "business_model",
    "legal": "legal",
    "fta.opex": "financial_trends",
    "fta.revenue": "financial_trends",
    "fta.ebitda": "financial_trends",
}

_PAGE_RE = re.compile(r"(?:p(?:age)?\.?\s*|page\s*)(\d+)", re.IGNORECASE)


class SparkSessionLike(Protocol):
    def sql(self, query: str) -> Any:
        ...


def format_ingestion_snapshot(
    catalog: str,
    chunk_count: int,
    ingestion_date: date | str,
) -> str:
    """Normative company-level pin — spec §5.8 / Appendix A7."""
    if isinstance(ingestion_date, date):
        date_str = ingestion_date.isoformat()
    else:
        date_str = str(ingestion_date)
    return f"{catalog}:{chunk_count}:{date_str}"


def _row_value(row: Any, key: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(key)
    return getattr(row, key, None)


def _collect_rows(result: Any) -> list[Any]:
    if result is None:
        return []
    if isinstance(result, list):
        return result
    collect = getattr(result, "collect", None)
    if callable(collect):
        return list(collect())
    return list(result)


def _chunk_ids_from_sql(spark: SparkSessionLike, query: str) -> list[str]:
    rows = _collect_rows(spark.sql(query))
    ids: list[str] = []
    for row in rows:
        chunk_id = _row_value(row, "chunk_id")
        if chunk_id:
            ids.append(str(chunk_id))
    return ids


def _dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _parse_page_from_location(location: str | None) -> int | None:
    if not location:
        return None
    match = _PAGE_RE.search(location)
    if match:
        return int(match.group(1))
    return None


def _section_pattern_from_location(location: str | None) -> str | None:
    if not location:
        return None
    cleaned = location.strip()
    if not cleaned:
        return None
    if len(cleaned) > 80:
        cleaned = cleaned[:80]
    return f"%{cleaned}%"


def _walk_json_for_source_refs(value: Any, refs: list[tuple[str, str | None]]) -> None:
    if isinstance(value, dict):
        doc = value.get("source_doc") or value.get("document")
        loc = value.get("source_location") or value.get("location")
        if doc:
            refs.append((str(doc), str(loc) if loc else None))
        for nested in value.values():
            _walk_json_for_source_refs(nested, refs)
    elif isinstance(value, list):
        for item in value:
            _walk_json_for_source_refs(item, refs)


def _parse_json_field(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    text = str(raw).strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


class GoldLabelBootstrap:
    """Programmatic gold label bootstrap for one company/catalog pair."""

    def __init__(
        self,
        spark: SparkSessionLike,
        *,
        catalog: str = DEFAULT_CATALOG,
        company_name: str = DEFAULT_COMPANY_NAME,
        ingestion_date: date | None = None,
    ) -> None:
        self.spark = spark
        self.catalog = catalog
        self.company_name = company_name
        self.ingestion_date = ingestion_date or datetime.now(timezone.utc).date()
        self._ingestion_snapshot: str | None = None
        self._analysis_row_cache: dict[str, dict[str, Any] | None] = {}

    def compute_ingestion_snapshot(self) -> str:
        """Compute single company-level ingestion_snapshot (Cell 7 normative)."""
        company_lit = _sql_literal(self.company_name)
        count_query = f"""
            SELECT COUNT(*) AS chunk_count
            FROM {self.catalog}.ingestion.chunks
            WHERE company_name = {company_lit}
        """
        rows = _collect_rows(self.spark.sql(count_query))
        if not rows:
            raise PreconditionError(
                f"No chunk count returned for {self.company_name!r} in {self.catalog}"
            )
        chunk_count = int(_row_value(rows[0], "chunk_count") or 0)
        snapshot = format_ingestion_snapshot(
            self.catalog,
            chunk_count,
            self.ingestion_date,
        )
        self._ingestion_snapshot = snapshot
        return snapshot

    @property
    def ingestion_snapshot(self) -> str:
        if self._ingestion_snapshot is None:
            return self.compute_ingestion_snapshot()
        return self._ingestion_snapshot

    def bootstrap(self, intents: Sequence[RetrievalIntent]) -> list[GoldLabel]:
        """Run two-pass bootstrap; every row shares one ingestion_snapshot."""
        snapshot = self.ingestion_snapshot
        pass1: dict[str, GoldLabel] = {}
        for intent in intents:
            pass1[intent.intent_id] = self._bootstrap_pass1(intent, snapshot)

        labels: list[GoldLabel] = []
        for intent in intents:
            base = pass1[intent.intent_id]
            labels.append(self._bootstrap_pass2(intent, base, pass1))
        self._assert_single_ingestion_snapshot(labels, snapshot)
        return labels

    def _bootstrap_pass1(self, intent: RetrievalIntent, snapshot: str) -> GoldLabel:
        positives: list[str] = []
        gold_method: str = "citation_backfill"
        confidence: str = "high"

        citation_ids = self._positives_from_citations(intent)
        if citation_ids:
            positives = citation_ids
            gold_method = "citation_backfill"
            confidence = "high"
        else:
            section_ids = self._positives_from_section_range(intent)
            if section_ids:
                positives = section_ids
                gold_method = "section_range"
                confidence = "high"
            else:
                closure_ids = self._positives_from_filename_closure(intent)
                if closure_ids:
                    positives = closure_ids
                    gold_method = "filename_closure"
                    confidence = "medium"

        if not positives:
            return GoldLabel(
                intent_id=intent.intent_id,
                company_name=self.company_name,
                catalog=self.catalog,
                gold_status="bootstrap_failed",
                positive_chunk_ids=[],
                gold_method="citation_backfill",
                ingestion_snapshot=snapshot,
                confidence="low",
                notes="Pass 1 found zero positives",
            )

        gold_status = "partial" if gold_method == "filename_closure" else "ready"
        return GoldLabel(
            intent_id=intent.intent_id,
            company_name=self.company_name,
            catalog=self.catalog,
            gold_status=gold_status,
            positive_chunk_ids=positives,
            gold_method=gold_method,
            ingestion_snapshot=snapshot,
            confidence=confidence,
        )

    def _bootstrap_pass2(
        self,
        intent: RetrievalIntent,
        base: GoldLabel,
        pass1: Mapping[str, GoldLabel],
    ) -> GoldLabel:
        if base.gold_status == "bootstrap_failed":
            return base

        negatives: list[str] = []
        negative_method = None
        negative_rule = None
        negative_confidence = None

        if intent.intent_id in HISTORICAL_BASIS_INTENT_IDS:
            basis_ids = self._negatives_from_basis_rule()
            if basis_ids:
                negatives.extend(basis_ids)
                negative_method = "basis_rule"
                negative_rule = (
                    "section_header ILIKE '%Projection%' OR '%Pro Forma Income%' "
                    "OR '%Forecast%' on CIM"
                )
                negative_confidence = "medium"

        if _intent_suffix(intent.intent_id) in SECTION_RULE_INTENT_SUFFIXES:
            section_ids = self._negatives_from_section_rule()
            if section_ids:
                negatives = _dedupe_preserve_order([*negatives, *section_ids])
                negative_method = negative_method or "section_rule"
                negative_rule = negative_rule or (
                    "section_header ILIKE '%Tax Return%' OR file_name ILIKE '%Tax%'"
                )
                negative_confidence = negative_confidence or "medium"

        sibling_id = CROSS_INTENT_NEGATIVE_PAIRS.get(intent.intent_id)
        if sibling_id:
            sibling = pass1.get(sibling_id)
            if sibling and sibling.positive_chunk_ids:
                negatives = _dedupe_preserve_order(
                    [*negatives, *sibling.positive_chunk_ids]
                )
                negative_method = "cross_intent_positive"
                negative_rule = (
                    f"Positives from {sibling_id} are basis negatives for "
                    f"{intent.intent_id}"
                )
                negative_confidence = "high"

        positives = [
            chunk_id
            for chunk_id in base.positive_chunk_ids
            if chunk_id not in set(negatives)
        ]
        return base.model_copy(
            update={
                "positive_chunk_ids": positives,
                "negative_chunk_ids": negatives or None,
                "negative_method": negative_method,
                "negative_rule": negative_rule,
                "negative_confidence": negative_confidence,
            }
        )

    def _positives_from_citations(self, intent: RetrievalIntent) -> list[str]:
        refs = self._citation_refs_for_agent(intent.agent_id)
        chunk_ids: list[str] = []
        company_lit = _sql_literal(self.company_name)
        for document, location in refs:
            doc_lit = _sql_literal(document)
            page = _parse_page_from_location(location)
            section_pattern = _section_pattern_from_location(location)
            page_clause = (
                f"AND c.page_start = {page}" if page is not None else ""
            )
            section_clause = (
                f"AND c.section_header ILIKE {_sql_literal(section_pattern)}"
                if section_pattern
                else ""
            )
            query = f"""
                SELECT c.chunk_id
                FROM {self.catalog}.ingestion.chunks c
                WHERE c.company_name = {company_lit}
                  AND (c.file_name = {doc_lit} OR c.file_name ILIKE {_sql_literal('%' + document[-40:] + '%')})
                  {page_clause}
                  {section_clause}
            """
            chunk_ids.extend(_chunk_ids_from_sql(self.spark, query))
        return _dedupe_preserve_order(chunk_ids)

    def _positives_from_section_range(self, intent: RetrievalIntent) -> list[str]:
        if _intent_suffix(intent.intent_id) not in SECTION_RANGE_INTENT_SUFFIXES:
            return []
        company_lit = _sql_literal(self.company_name)
        section_clauses = " OR ".join(
            f"c.section_header ILIKE {_sql_literal(pattern)}"
            for pattern in SECTION_RANGE_SECTION_PATTERNS
        )
        query = f"""
            SELECT c.chunk_id
            FROM {self.catalog}.ingestion.chunks c
            WHERE c.company_name = {company_lit}
              AND c.file_name ILIKE {_sql_literal(CIM_FILENAME_PATTERN)}
              AND c.page_start BETWEEN {SECTION_RANGE_PAGE_START} AND {SECTION_RANGE_PAGE_END}
              AND ({section_clauses})
        """
        return _dedupe_preserve_order(_chunk_ids_from_sql(self.spark, query))

    def _positives_from_filename_closure(self, intent: RetrievalIntent) -> list[str]:
        if not intent.workstream_filter:
            return []
        company_lit = _sql_literal(self.company_name)
        workstreams = ", ".join(_sql_literal(ws) for ws in intent.workstream_filter)
        query = f"""
            SELECT c.chunk_id
            FROM {self.catalog}.ingestion.chunks c
            JOIN {self.catalog}.classification.doc_relevance r
              ON c.file_name = r.filename AND c.company_name = r.company_name
            LATERAL VIEW explode(r.workstream) ws AS workstream_tag
            WHERE c.company_name = {company_lit}
              AND r.priority_tier = 1
              AND workstream_tag IN ({workstreams})
        """
        return _dedupe_preserve_order(_chunk_ids_from_sql(self.spark, query))

    def _negatives_from_basis_rule(self) -> list[str]:
        company_lit = _sql_literal(self.company_name)
        section_clauses = " OR ".join(
            f"c.section_header ILIKE {_sql_literal(pattern)}"
            for pattern in BASIS_NEGATIVE_SECTION_PATTERNS
        )
        query = f"""
            SELECT c.chunk_id
            FROM {self.catalog}.ingestion.chunks c
            WHERE c.company_name = {company_lit}
              AND c.file_name ILIKE {_sql_literal(CIM_FILENAME_PATTERN)}
              AND ({section_clauses})
        """
        return _dedupe_preserve_order(_chunk_ids_from_sql(self.spark, query))

    def _negatives_from_section_rule(self) -> list[str]:
        company_lit = _sql_literal(self.company_name)
        query = f"""
            SELECT c.chunk_id
            FROM {self.catalog}.ingestion.chunks c
            WHERE c.company_name = {company_lit}
              AND (
                c.section_header ILIKE '%Tax Return%'
                OR c.file_name ILIKE '%Tax%'
              )
        """
        return _dedupe_preserve_order(_chunk_ids_from_sql(self.spark, query))

    def _citation_refs_for_agent(self, agent_id: str) -> list[tuple[str, str | None]]:
        table = AGENT_ANALYSIS_TABLE.get(agent_id)
        if not table:
            return []
        row = self._latest_analysis_row(table)
        if not row:
            return []
        refs: list[tuple[str, str | None]] = []
        citations = _parse_json_field(row.get("citations"))
        if isinstance(citations, list):
            for cite in citations:
                if not isinstance(cite, dict):
                    continue
                doc = cite.get("document") or cite.get("source_doc")
                loc = cite.get("location") or cite.get("source_location")
                if doc:
                    refs.append((str(doc), str(loc) if loc else None))
        for value in row.values():
            parsed = _parse_json_field(value)
            if parsed is not None:
                _walk_json_for_source_refs(parsed, refs)
        return _dedupe_preserve_order_refs(refs)

    def _latest_analysis_row(self, table: str) -> dict[str, Any] | None:
        if table in self._analysis_row_cache:
            return self._analysis_row_cache[table]
        company_lit = _sql_literal(self.company_name)
        query = f"""
            SELECT *
            FROM {self.catalog}.analysis.{table}
            WHERE company_name = {company_lit}
            ORDER BY created_at DESC
            LIMIT 1
        """
        rows = _collect_rows(self.spark.sql(query))
        if not rows:
            self._analysis_row_cache[table] = None
            return None
        row = rows[0]
        if isinstance(row, Mapping):
            payload = dict(row)
        else:
            payload = {
                key: _row_value(row, key)
                for key in (
                    "citations",
                    "contract_register_json",
                    "vendor_register_json",
                    "employment_register_json",
                    "litigation_register_json",
                    "privacy_security_register_json",
                    "insurance_register_json",
                    "revenue_trend_json",
                    "opex_breakdown_json",
                    "ebitda_bridge_json",
                    "addback_schedule_json",
                    "kpi_dashboard_json",
                    "created_at",
                )
                if _row_value(row, key) is not None
            }
        self._analysis_row_cache[table] = payload
        return payload

    @staticmethod
    def _assert_single_ingestion_snapshot(
        labels: Sequence[GoldLabel],
        expected: str,
    ) -> None:
        snapshots = {label.ingestion_snapshot for label in labels}
        if len(snapshots) != 1:
            raise PreconditionError(
                "Multi-value ingestion_snapshot in single bootstrap pass: "
                f"{sorted(snapshots)}"
            )
        if expected not in snapshots:
            raise PreconditionError(
                f"Bootstrap ingestion_snapshot mismatch: expected {expected!r}, "
                f"got {snapshots!r}"
            )
        if any(not label.ingestion_snapshot for label in labels):
            raise PreconditionError("Gold row missing ingestion_snapshot")


def _intent_suffix(intent_id: str) -> str:
    return intent_id.rsplit(".", 1)[-1]


def _dedupe_preserve_order_refs(
    refs: list[tuple[str, str | None]],
) -> list[tuple[str, str | None]]:
    seen: set[tuple[str, str | None]] = set()
    ordered: list[tuple[str, str | None]] = []
    for ref in refs:
        if ref in seen:
            continue
        seen.add(ref)
        ordered.append(ref)
    return ordered


def load_registry(path: Path) -> list[RetrievalIntent]:
    rows = yaml.safe_load(path.read_text(encoding="utf-8"))
    intents = [RetrievalIntent.model_validate(row) for row in rows]
    intents.sort(key=lambda item: item.intent_id)
    return intents


def write_gold_labels(path: Path, labels: Sequence[GoldLabel]) -> None:
    snapshots = {label.ingestion_snapshot for label in labels}
    if len(snapshots) != 1:
        raise PreconditionError(
            f"Refusing to write gold labels with multiple ingestion_snapshot values: "
            f"{sorted(snapshots)}"
        )
    if any(not label.ingestion_snapshot for label in labels):
        raise PreconditionError("Refusing to write gold row missing ingestion_snapshot")
    payload = [label.model_dump(mode="json", exclude_none=True) for label in labels]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def load_gold_labels(path: Path) -> list[GoldLabel]:
    rows = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [GoldLabel.model_validate(row) for row in rows]


def validate_ingestion_snapshot_consistency(labels: Sequence[GoldLabel]) -> str:
    """Return the single ingestion_snapshot or raise PreconditionError."""
    snapshots = {label.ingestion_snapshot for label in labels if label.ingestion_snapshot}
    if not snapshots:
        raise PreconditionError("No ingestion_snapshot values in gold labels")
    if len(snapshots) > 1:
        raise PreconditionError(
            "Loaded GoldLabel rows disagree on ingestion_snapshot: "
            f"{sorted(snapshots)}"
        )
    return next(iter(snapshots))


def main() -> None:
    from pyspark.sql import SparkSession

    repo_root = Path(__file__).resolve().parents[3]
    registry_path = repo_root / "eval" / "retrieval" / "intent_registry.yaml"
    output_path = repo_root / "eval" / "retrieval" / "gold_labels" / "elder_care.yaml"

    spark = SparkSession.getActiveSession()
    if spark is None:
        raise RuntimeError(
            "Active SparkSession required — run on Databricks cluster after Cell 7"
        )

    intents = load_registry(registry_path)
    bootstrap = GoldLabelBootstrap(spark)
    labels = bootstrap.bootstrap(intents)
    write_gold_labels(output_path, labels)
    ready = sum(1 for label in labels if label.gold_status != "bootstrap_failed")
    print(
        f"Wrote {len(labels)} gold labels to {output_path} "
        f"(ready/partial={ready}, snapshot={bootstrap.ingestion_snapshot})"
    )


if __name__ == "__main__":
    main()
