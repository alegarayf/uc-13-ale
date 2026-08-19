"""Gold label bootstrap — spec §5.12.2 / Appendix A.

Two-pass bootstrap:
  Pass 1 — positives via citation backfill, section-range rules, filename closure.
  Pass 2 — negatives via basis_rule, section_rule, cross_intent_positive.

Pinned ILIKE patterns (Surface 8) live in module constants below.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import yaml

from eval.retrieval.errors import PreconditionError
from eval.retrieval.models import EXCLUDE_REASON_VOCABULARY, GoldLabel, RetrievalIntent

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

POSITIVE_FALLBACK_CHAIN: tuple[str, ...] = (
    "citation_backfill",
    "section_range",
    "filename_closure",
)

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
_EXCEL_SHEET_RE = re.compile(r"Sheet:\s*(.+)", re.IGNORECASE)
_EXCEL_DATA_ROWS_RE = re.compile(
    r"Sheet:\s*([^,]+),\s*Data Rows",
    re.IGNORECASE,
)
_EXCEL_SECTION_SUFFIX_RE = re.compile(
    r"\s*(?:,\s*|\s*/\s*)Section:",
    re.IGNORECASE,
)

KPI_ITEM12_INTENT_IDS: frozenset[str] = frozenset(
    {
        "kpi.retrieve_bench_and_capacity",
        "kpi.retrieve_bill_rates_and_margins",
        "kpi.retrieve_headcount_attrition",
        "kpi.retrieve_healthcare_labor_market",
        "kpi.retrieve_healthcare_ops",
        "kpi.retrieve_healthcare_revenue_per_unit",
        "kpi.retrieve_pipeline_backlog",
    }
)

KPI_CLAIM_INTENT_MAP_PATH = Path(__file__).resolve().parent / "kpi_claim_intent_map.yaml"
GOLD_EXCLUSIONS_PATH = Path(__file__).resolve().parent / "gold_exclusions.yaml"

CitationRef = tuple[str, str | None, str | None]


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


_KPI_PDF_PAGE_SUFFIX_RE = re.compile(r",\s*page\s*\d+\s*$", re.IGNORECASE)


def _normalize_kpi_pdf_location(location: str) -> str:
    """Strip KPI PDF citation prefixes/suffixes before section ILIKE matching."""
    cleaned = re.sub(r"^section:\s*", "", location.strip(), flags=re.IGNORECASE)
    cleaned = _KPI_PDF_PAGE_SUFFIX_RE.sub("", cleaned)
    return cleaned.strip()


def _is_excel_shaped_location(location: str | None) -> bool:
    if not location:
        return False
    return _EXCEL_SHEET_RE.search(location) is not None


def _excel_tab_from_data_rows_location(location: str) -> str | None:
    match = _EXCEL_DATA_ROWS_RE.search(location)
    if not match:
        return None
    return match.group(1).strip()


def _excel_tab_candidate_from_location(location: str) -> str:
    match = _EXCEL_SHEET_RE.search(location)
    if not match:
        raise PreconditionError(f"Location is not Excel-shaped: {location!r}")
    raw = match.group(1).strip()
    section_match = _EXCEL_SECTION_SUFFIX_RE.search(raw)
    if section_match:
        raw = raw[: section_match.start()].strip()
    return raw.split(",", 1)[0].strip()


def _tabs_matching_excel_candidate(tabs: Sequence[str], candidate: str) -> list[str]:
    exact_matches = [tab for tab in tabs if tab == candidate]
    if exact_matches:
        return exact_matches
    return [tab for tab in tabs if tab.startswith(candidate)]


def load_kpi_claim_intent_map(
    path: Path = KPI_CLAIM_INTENT_MAP_PATH,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Load fail-closed KPI claim→intent mapping (Contract T2-a)."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PreconditionError(
            f"KPI claim→intent map must be a mapping at {path}"
        )
    claims = payload.get("claims")
    intents = payload.get("intents")
    if not isinstance(claims, dict):
        raise PreconditionError(
            f"KPI claim→intent map missing claims mapping at {path}"
        )
    if not isinstance(intents, dict):
        raise PreconditionError(
            f"KPI claim→intent map missing intents totality block at {path}"
        )

    claim_map = {str(key): str(value) for key, value in claims.items()}
    intent_block = {str(key): value for key, value in intents.items()}

    missing_intents = KPI_ITEM12_INTENT_IDS - set(intent_block)
    if missing_intents:
        raise PreconditionError(
            "KPI claim→intent map missing item-12 intents: "
            f"{sorted(missing_intents)}"
        )
    extra_intents = set(intent_block) - KPI_ITEM12_INTENT_IDS
    if extra_intents:
        raise PreconditionError(
            "KPI claim→intent map has unknown item-12 intents: "
            f"{sorted(extra_intents)}"
        )

    mapped_targets = set(claim_map.values())
    unknown_targets = mapped_targets - KPI_ITEM12_INTENT_IDS
    if unknown_targets:
        raise PreconditionError(
            "KPI claim→intent map targets unknown intents: "
            f"{sorted(unknown_targets)}"
        )

    return claim_map, intent_block


def load_gold_exclusions(
    path: Path = GOLD_EXCLUSIONS_PATH,
    *,
    company_slug: str,
) -> dict[str, str]:
    """Load company-scoped aggregate-exclusion population (Contract T3-b / T13)."""
    if not company_slug or not str(company_slug).strip():
        raise PreconditionError(
            "company_slug is required for load_gold_exclusions"
        )
    from eval.retrieval.companies import require_folded_company_slug

    require_folded_company_slug(company_slug)
    slug = str(company_slug).strip()
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PreconditionError(
            f"Gold exclusions artifact must be a mapping at {path}"
        )
    companies = payload.get("companies")
    if not isinstance(companies, dict):
        raise PreconditionError(
            f"Gold exclusions artifact missing companies mapping at {path}"
        )
    company_block = companies.get(slug)
    if company_block is None:
        return {}
    if not isinstance(company_block, dict):
        raise PreconditionError(
            f"Gold exclusions company block for {slug!r} must be a mapping at {path}"
        )
    excluded = company_block.get("excluded")
    if excluded is None:
        return {}
    if not isinstance(excluded, list):
        raise PreconditionError(
            f"Gold exclusions excluded list for {slug!r} must be a list at {path}"
        )
    mapping: dict[str, str] = {}
    for index, entry in enumerate(excluded):
        if not isinstance(entry, dict):
            raise PreconditionError(
                f"Gold exclusions entry {index} for {slug!r} must be a mapping at {path}"
            )
        intent_id = entry.get("intent_id")
        exclude_reason = entry.get("exclude_reason")
        if not intent_id or not exclude_reason:
            raise PreconditionError(
                f"Gold exclusions entry {index} for {slug!r} missing intent_id or "
                f"exclude_reason at {path}"
            )
        intent_key = str(intent_id)
        if intent_key in mapping:
            raise PreconditionError(
                f"Duplicate gold exclusion for intent {intent_key!r} "
                f"under {slug!r} at {path}"
            )
        mapping[intent_key] = str(exclude_reason)
    return mapping


def _validate_exclude_reason_membership(label: GoldLabel) -> None:
    if label.exclude_reason is None:
        return
    if label.exclude_reason not in EXCLUDE_REASON_VOCABULARY:
        raise PreconditionError(
            f"exclude_reason {label.exclude_reason!r} for {label.intent_id} "
            f"is not in closed vocabulary {sorted(EXCLUDE_REASON_VOCABULARY)}"
        )


def _walk_json_for_source_refs(value: Any, refs: list[CitationRef]) -> None:
    if isinstance(value, dict):
        doc = value.get("source_doc") or value.get("document")
        loc = value.get("source_location") or value.get("location")
        claim_raw = value.get("claim")
        claim = str(claim_raw) if claim_raw is not None else None
        if doc:
            refs.append((str(doc), str(loc) if loc else None, claim))
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
        self._kpi_claim_map_cache: tuple[dict[str, str], dict[str, Any]] | None = None
        self._gold_exclusions_cache: dict[str, str] | None = None
        self._gold_exclusions_cache_slug: str | None = None
        self._last_excel_citation_notes: dict[str, str] = {}

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
        self._last_excel_citation_notes.pop(intent.intent_id, None)
        exclude_reason = self._gold_exclusions().get(intent.intent_id)
        if exclude_reason is not None:
            return GoldLabel(
                intent_id=intent.intent_id,
                company_name=self.company_name,
                catalog=self.catalog,
                gold_status="bootstrap_failed",
                positive_chunk_ids=[],
                gold_method="citation_backfill",
                ingestion_snapshot=snapshot,
                confidence="low",
                aggregate_exclude=True,
                exclude_reason=exclude_reason,
                notes=(
                    f"aggregate_exclude: {exclude_reason} "
                    f"(gold_exclusions.yaml; no citation source)"
                ),
            )

        result = self._try_positive_methods(intent, POSITIVE_FALLBACK_CHAIN)
        if result is None:
            kpi_notes = self._last_excel_citation_notes.pop(intent.intent_id, None)
            notes = "Pass 1 found zero positives"
            if kpi_notes:
                notes = f"{notes}; {kpi_notes}"
            return GoldLabel(
                intent_id=intent.intent_id,
                company_name=self.company_name,
                catalog=self.catalog,
                gold_status="bootstrap_failed",
                positive_chunk_ids=[],
                gold_method="citation_backfill",
                ingestion_snapshot=snapshot,
                confidence="low",
                notes=notes,
            )

        positives, gold_method, confidence = result
        gold_status = "partial" if gold_method == "filename_closure" else "ready"
        notes = self._last_excel_citation_notes.pop(intent.intent_id, None)
        return GoldLabel(
            intent_id=intent.intent_id,
            company_name=self.company_name,
            catalog=self.catalog,
            gold_status=gold_status,
            positive_chunk_ids=positives,
            gold_method=gold_method,
            ingestion_snapshot=snapshot,
            confidence=confidence,
            notes=notes,
        )

    def _fallback_methods_after(self, method: str) -> tuple[str, ...]:
        try:
            index = POSITIVE_FALLBACK_CHAIN.index(method)
        except ValueError:
            return ()
        return POSITIVE_FALLBACK_CHAIN[index + 1 :]

    def _positives_for_method(
        self, intent: RetrievalIntent, method: str
    ) -> list[str]:
        if method == "citation_backfill":
            return self._positives_from_citations(intent)
        if method == "section_range":
            return self._positives_from_section_range(intent)
        if method == "filename_closure":
            return self._positives_from_filename_closure(intent)
        raise ValueError(f"Unknown positive method: {method!r}")

    def _try_positive_methods(
        self,
        intent: RetrievalIntent,
        methods: Sequence[str],
        *,
        negative_ids: frozenset[str] | None = None,
    ) -> tuple[list[str], str, str] | None:
        excluded = negative_ids or frozenset()
        for method in methods:
            candidates = self._positives_for_method(intent, method)
            survivors = [
                chunk_id for chunk_id in candidates if chunk_id not in excluded
            ]
            if survivors:
                confidence = "medium" if method == "filename_closure" else "high"
                return survivors, method, confidence
        return None

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

        negative_set = set(negatives)
        positives = [
            chunk_id
            for chunk_id in base.positive_chunk_ids
            if chunk_id not in negative_set
        ]

        updates: dict[str, Any] = {
            "positive_chunk_ids": positives,
            "negative_chunk_ids": negatives or None,
            "negative_method": negative_method,
            "negative_rule": negative_rule,
            "negative_confidence": negative_confidence,
        }

        if not positives:
            fallback_methods = self._fallback_methods_after(base.gold_method)
            fallback = self._try_positive_methods(
                intent,
                fallback_methods,
                negative_ids=frozenset(negative_set),
            )
            if fallback is not None:
                fb_positives, fb_method, fb_confidence = fallback
                updates.update(
                    {
                        "positive_chunk_ids": fb_positives,
                        "gold_method": fb_method,
                        "gold_status": (
                            "partial" if fb_method == "filename_closure" else "ready"
                        ),
                        "confidence": fb_confidence,
                        "notes": (
                            f"Pass 1 {base.gold_method} zeroed by pass-2 negatives; "
                            f"fallback {fb_method} engaged"
                        ),
                    }
                )
            else:
                updates.update(
                    {
                        "positive_chunk_ids": [],
                        "gold_status": "bootstrap_failed",
                        "confidence": "low",
                        "notes": (
                            f"Pass 2 zeroed all pass-1 {base.gold_method} positives; "
                            "no fallback survivors"
                        ),
                    }
                )

        label = base.model_copy(update=updates)
        if label.gold_status in {"ready", "partial"} and not label.positive_chunk_ids:
            raise PreconditionError(
                f"Bootstrap invariant violated for {intent.intent_id}: "
                f"{label.gold_status!r} with empty positive_chunk_ids"
            )
        return label

    def _kpi_claim_intent_map(self) -> tuple[dict[str, str], dict[str, Any]]:
        if self._kpi_claim_map_cache is None:
            self._kpi_claim_map_cache = load_kpi_claim_intent_map()
        return self._kpi_claim_map_cache

    def _gold_exclusions(self) -> dict[str, str]:
        from eval.retrieval.companies import canonical_company_slug

        company_slug = canonical_company_slug(self.company_name)
        if (
            self._gold_exclusions_cache is None
            or self._gold_exclusions_cache_slug != company_slug
        ):
            self._gold_exclusions_cache = load_gold_exclusions(
                company_slug=company_slug,
            )
            self._gold_exclusions_cache_slug = company_slug
        return self._gold_exclusions_cache

    def _validate_kpi_citation_refs(self, refs: Sequence[CitationRef]) -> None:
        claim_map, _intent_block = self._kpi_claim_intent_map()
        for document, _location, claim in refs:
            if not claim:
                raise PreconditionError(
                    f"KPI citation ref missing claim for document={document!r}"
                )
            if claim not in claim_map:
                raise PreconditionError(f"Unmapped KPI claim: {claim!r}")

    def _resolve_excel_tab(self, document: str, location: str) -> str:
        exact_tab = _excel_tab_from_data_rows_location(location)
        if exact_tab is not None:
            return exact_tab

        candidate = _excel_tab_candidate_from_location(location)
        tabs = self._distinct_tabs_for_file(document)
        matches = _tabs_matching_excel_candidate(tabs, candidate)
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise PreconditionError(
                "Excel tab resolution found zero candidates for "
                f"document={document!r}, location={location!r}, candidate={candidate!r}"
            )
        raise PreconditionError(
            "Excel tab resolution is ambiguous for "
            f"document={document!r}, location={location!r}, candidate={candidate!r}: "
            f"{sorted(matches)}"
        )

    def _distinct_tabs_for_file(self, document: str) -> list[str]:
        company_lit = _sql_literal(self.company_name)
        doc_lit = _sql_literal(document)
        query = f"""
            SELECT DISTINCT c.tab
            FROM {self.catalog}.ingestion.chunks c
            WHERE c.company_name = {company_lit}
              AND c.tab IS NOT NULL
              AND (
                c.file_name = {doc_lit}
                OR c.file_name ILIKE {_sql_literal('%' + document[-40:] + '%')}
              )
        """
        rows = _collect_rows(self.spark.sql(query))
        tabs: list[str] = []
        for row in rows:
            tab = _row_value(row, "tab")
            if tab:
                tabs.append(str(tab))
        return tabs

    def _chunks_for_file_and_tab(self, document: str, tab: str) -> list[str]:
        company_lit = _sql_literal(self.company_name)
        doc_lit = _sql_literal(document)
        tab_lit = _sql_literal(tab)
        query = f"""
            SELECT c.chunk_id
            FROM {self.catalog}.ingestion.chunks c
            WHERE c.company_name = {company_lit}
              AND c.tab = {tab_lit}
              AND (
                c.file_name = {doc_lit}
                OR c.file_name ILIKE {_sql_literal('%' + document[-40:] + '%')}
              )
        """
        return _chunk_ids_from_sql(self.spark, query)

    def _positives_from_citations(self, intent: RetrievalIntent) -> list[str]:
        refs = self._citation_refs_for_agent(intent.agent_id)
        if intent.agent_id == "kpi":
            return self._positives_from_kpi_citations(intent, refs)

        chunk_ids: list[str] = []
        company_lit = _sql_literal(self.company_name)
        for document, location, _claim in refs:
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

    def _chunks_for_kpi_pdf_citation(
        self, document: str, location: str
    ) -> list[str]:
        normalized = _normalize_kpi_pdf_location(location)
        company_lit = _sql_literal(self.company_name)
        doc_lit = _sql_literal(document)
        page = _parse_page_from_location(location)
        section_pattern = _section_pattern_from_location(normalized)
        page_clause = f"AND c.page_start = {page}" if page is not None else ""
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
        return _chunk_ids_from_sql(self.spark, query)

    def _positives_from_kpi_citations(
        self,
        intent: RetrievalIntent,
        refs: Sequence[CitationRef],
    ) -> list[str]:
        claim_map, _intent_block = self._kpi_claim_intent_map()
        self._validate_kpi_citation_refs(refs)

        chunk_ids: list[str] = []
        excel_note_parts: list[str] = []
        pdf_note_parts: list[str] = []
        pdf_unresolved_parts: list[str] = []
        for document, location, claim in refs:
            assert claim is not None
            if claim_map[claim] != intent.intent_id:
                continue
            if not location:
                raise PreconditionError(
                    f"KPI claim {claim!r} has missing location for document={document!r}"
                )
            if _is_excel_shaped_location(location):
                tab = self._resolve_excel_tab(document, location)
                matched = self._chunks_for_file_and_tab(document, tab)
                if not matched:
                    raise PreconditionError(
                        "Zero chunks for KPI Excel citation "
                        f"(document={document!r}, tab={tab!r}, claim={claim!r})"
                    )
                chunk_ids.extend(matched)
                excel_note_parts.append(f"claim={claim}; tab={tab}")
            else:
                matched = self._chunks_for_kpi_pdf_citation(document, location)
                if not matched:
                    pdf_unresolved_parts.append(
                        f"claim={claim}; location={location}"
                    )
                    continue
                chunk_ids.extend(matched)
                pdf_note_parts.append(f"claim={claim}")

        note_segments: list[str] = []
        if excel_note_parts:
            note_segments.append("excel_branch: " + "; ".join(excel_note_parts))
        if pdf_note_parts:
            note_segments.append("pdf_branch: " + "; ".join(pdf_note_parts))
        if pdf_unresolved_parts:
            note_segments.append(
                "pdf_branch_unresolved: " + "; ".join(pdf_unresolved_parts)
            )
        if note_segments:
            self._last_excel_citation_notes[intent.intent_id] = "; ".join(
                note_segments
            )
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

    def _citation_refs_for_agent(self, agent_id: str) -> list[CitationRef]:
        table = AGENT_ANALYSIS_TABLE.get(agent_id)
        if not table:
            return []
        row = self._latest_analysis_row(table)
        if not row:
            return []
        refs: list[CitationRef] = []
        citations = _parse_json_field(row.get("citations"))
        if isinstance(citations, list):
            for cite in citations:
                if not isinstance(cite, dict):
                    continue
                doc = cite.get("document") or cite.get("source_doc")
                loc = cite.get("location") or cite.get("source_location")
                claim_raw = cite.get("claim")
                claim = str(claim_raw) if claim_raw is not None else None
                if doc:
                    refs.append((str(doc), str(loc) if loc else None, claim))
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
    refs: list[CitationRef],
) -> list[CitationRef]:
    seen: set[CitationRef] = set()
    ordered: list[CitationRef] = []
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
    for label in labels:
        _validate_exclude_reason_membership(label)
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eval.retrieval.gold.bootstrap")
    parser.add_argument(
        "--company",
        default=DEFAULT_COMPANY_NAME,
        help=f"Company display name (default: {DEFAULT_COMPANY_NAME!r})",
    )
    parser.add_argument(
        "--catalog",
        default=DEFAULT_CATALOG,
        help=f"Unity Catalog (default: {DEFAULT_CATALOG})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Gold YAML output path "
            "(default: eval/retrieval/gold_labels/<canonical_slug>.yaml)"
        ),
    )
    return parser


def _resolved_output_path(args: argparse.Namespace) -> Path:
    if args.output is not None:
        return args.output
    from eval.retrieval.companies import canonical_company_slug
    from eval.retrieval.harness import default_gold_path

    return default_gold_path(canonical_company_slug(args.company))


def main(argv: list[str] | None = None) -> int:
    import sys

    from pyspark.sql import SparkSession

    from eval.retrieval.companies import canonical_company_slug
    from eval.retrieval.errors import PreconditionError

    args = build_parser().parse_args(argv)

    try:
        company_slug = canonical_company_slug(args.company)
        output_path = _resolved_output_path(args)
    except ValueError as exc:
        print(f"gold bootstrap: {exc}", file=sys.stderr)
        return 1

    repo_root = Path(__file__).resolve().parents[3]
    registry_path = repo_root / "eval" / "retrieval" / "intent_registry.yaml"

    spark = SparkSession.getActiveSession()
    if spark is None:
        print(
            "Active SparkSession required — run on Databricks cluster after Cell 7",
            file=sys.stderr,
        )
        return 1

    try:
        intents = load_registry(registry_path)
        bootstrap = GoldLabelBootstrap(
            spark,
            catalog=args.catalog,
            company_name=args.company,
        )
        labels = bootstrap.bootstrap(intents)
        write_gold_labels(output_path, labels)
    except (PreconditionError, ValueError) as exc:
        print(f"gold bootstrap: {exc}", file=sys.stderr)
        return 1

    ready = sum(1 for label in labels if label.gold_status != "bootstrap_failed")
    print(
        f"Wrote {len(labels)} gold labels to {output_path} "
        f"for company={company_slug} catalog={args.catalog} "
        f"(ready/partial={ready}, snapshot={bootstrap.ingestion_snapshot})"
    )
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main())
