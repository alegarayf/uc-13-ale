"""EvalHarness runner — spec §5.12.1 / §5.12.8 / §5.12.9."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eval.retrieval.companies import (
    UnnormalizableCompanySlugError,
    canonical_company_slug,
    require_folded_company_slug,
)
from eval.retrieval.errors import (
    BaselineInvalidError,
    CoverageError,
    GoldSnapshotMismatchError,
    IngestionSnapshotMismatchError,
    PreconditionError,
    RegistryHashMismatchError,
)
from eval.retrieval.gold.bootstrap import (
    load_gold_labels,
    load_registry,
    validate_ingestion_snapshot_consistency,
)
from eval.retrieval.models import (
    GoldLabel,
    HarnessDelta,
    HarnessReport,
    HarnessResult,
    HarnessRun,
    IntentGateSummary,
    ProvenanceRecord,
    RetrievalIntent,
    VALID_ABLATION_ARMS,
)
from eval.retrieval.provenance import build_provenance_record, normalize_mode
from eval.retrieval.scope_resolver import gate_eligible_intent_ids
from eval.retrieval.store import EvalStore, SqliteEvalStore, derive_agent_id

logger = logging.getLogger(__name__)

GATE_METRICS = ("recall_at_10", "precision_at_10", "basis_conflict_at_10")
AUDIT_METRICS = ("mrr",)

HIGHER_IS_BETTER = frozenset({"recall_at_10", "precision_at_10", "mrr"})
LOWER_IS_BETTER = frozenset({"basis_conflict_at_10"})

_ABLATION_ARM_TO_MERGE_RANK: dict[str, str] = {
    "merge_rank_on": "sim_tier",
    "merge_rank_off": "off",
    "sim_only": "sim_only",
    "tier_only": "tier_only",
}


def resolve_ablation_arm(ablation_config: dict[str, Any] | None) -> str | None:
    """Parse ablation_config arm key; raises PreconditionError when malformed."""
    if ablation_config is None:
        return None
    if not isinstance(ablation_config, dict):
        raise PreconditionError("ablation_config must be a dict")
    arm = ablation_config.get("arm")
    if not isinstance(arm, str):
        raise PreconditionError("ablation_config requires string 'arm' key")
    if arm not in VALID_ABLATION_ARMS:
        raise PreconditionError(f"unknown ablation arm: {arm}")
    return arm


def ablation_arm_to_merge_rank_mode(ablation_arm: str | None) -> str | None:
    """Map harness ablation arm to semantic_search merge_rank_mode kwarg."""
    if ablation_arm is None:
        return None
    if ablation_arm == "vs_filter_pushdown":
        raise PreconditionError(
            "vs_filter_pushdown ablation arm is not dispatchable in M-RE3 scope"
        )
    mode = _ABLATION_ARM_TO_MERGE_RANK.get(ablation_arm)
    if mode is None:
        raise PreconditionError(f"unknown ablation arm: {ablation_arm}")
    return mode


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_registry_path() -> Path:
    return _repo_root() / "eval" / "retrieval" / "intent_registry.yaml"


def default_gold_path(company_slug: str) -> Path:
    require_folded_company_slug(company_slug)
    return _repo_root() / "eval" / "retrieval" / "gold_labels" / f"{company_slug}.yaml"


def default_reports_dir() -> Path:
    return _repo_root() / "eval" / "retrieval" / "reports"


def default_sqlite_path() -> Path:
    return _repo_root() / "eval" / "retrieval" / ".local" / "re2_store.sqlite"


def compute_registry_hash(registry_path: Path) -> str:
    return hashlib.sha256(registry_path.read_bytes()).hexdigest()


def _canonical_gold_row(label: GoldLabel) -> dict[str, Any]:
    negatives = sorted(label.negative_chunk_ids or [])
    return {
        "intent_id": label.intent_id,
        "positive_chunk_ids": sorted(label.positive_chunk_ids),
        "negative_chunk_ids": negatives,
        "gold_status": label.gold_status,
        "ingestion_snapshot": label.ingestion_snapshot,
    }


def compute_gold_snapshot(labels: Sequence[GoldLabel]) -> str:
    """Canonical JSON SHA-256 per spec §5.8."""
    rows = sorted(
        (_canonical_gold_row(label) for label in labels),
        key=lambda row: row["intent_id"],
    )
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _chunk_id_from_row(chunk: Any) -> str:
    if isinstance(chunk, Mapping):
        return str(chunk["chunk_id"])
    return str(chunk.chunk_id)


def uses_fallback_wrapper(intent: RetrievalIntent) -> bool:
    if intent.invocation_path == "with_fallback":
        return True
    if intent.min_results is not None:
        return True
    return bool(intent.file_name_filter)


# Clearsulting-only q4 fallback override (cycle 26). Shared Ajax/tuition
# registry query stays byte-identical (D11). Hash-no: harness-time only.
CS_Q4_FALLBACK_INTENT_ID = "fta.revenue.q4_customer_concentration_fallback"
CS_Q4_FALLBACK_QUERY = (
    "customer concentration top customers revenue by customer largest customers "
    "customer mix payor mix client revenue key customers top 10 customers "
    "customer revenue breakdown revenue by payor revenue by client"
)
CS_Q4_FALLBACK_FILE_NAME_FILTER = ("CIM",)

# Clearsulting-only location override (cycle 27). Shared GKF/SPG healthcare
# tail stays byte-identical (D11). Hash-no: harness-time only.
# Token "CIM" does not substring-match "Confidential Information Memorandum.pdf";
# "Memorandum" is the live filename token. "CIM" is kept as a no-op extra.
CS_LOCATION_INTENT_ID = "bma.retrieve_revenue_by_location_and_metrics"
CS_LOCATION_QUERY = (
    "multinational presence office locations global delivery platform Cleveland "
    "Columbus Chicago Dallas London Toronto United States United Kingdom Canada "
    "Australia full-time employees remote delivery location established total "
    "resources delivery capability revenue by geography"
)
CS_LOCATION_FILE_NAME_FILTER = ("Memorandum", "CIM")

# GKF-only location override (cycle 28 / Arm A). Shared registry healthcare/org
# tail stays byte-identical (D11). Hash-no: harness-time only.
# Live file is Project Ajax CIM vF - Rallyday Partners.pdf. D29: do not copy
# CS Memorandum — that token matches 0 GKF files. CIM / Ajax / Rallyday all
# substring-match the Ajax CIM pdf.
GKF_LOCATION_INTENT_ID = CS_LOCATION_INTENT_ID
GKF_LOCATION_QUERY = (
    "Corporate Organization Current State leadership team DMV Mike Pesi CEO "
    "Ross Flax established leadership team strong presence in the DMV area "
    "expand into new regions Academic Director Teachers and Staff Rockville "
    "Bethesda"
)
GKF_LOCATION_FILE_NAME_FILTER = ("CIM", "Ajax", "Rallyday")

# Clearsulting-only named-zero overrides (cycle 29 / P1). Shared BMA / FTA /
# KPI registry query: strings stay byte-identical (D11). Hash-no: harness-time
# only. D29 live tokens: Memorandum (CIM matches 0 CS files); Employee /
# Attrition (not Pipeline-only). Do not use QuickBooks / QBO / P&L as filters.
CS_VISIBILITY_INTENT_ID = "bma.retrieve_revenue_visibility"
CS_VISIBILITY_QUERY = (
    "Clients and Go-to-Market YTD 2025 Bookings Project Infinity Clearsulting "
    "Go-to-Market Engine Driving Consistent Blue-Chip Client Wins Shift Towards "
    "Fixed-Fee Hybrid Models revenue visibility contracted revenue bookings "
    "historical projected revenue"
)
CS_VISIBILITY_FILE_NAME_FILTER = ("Memorandum",)

CS_Q5_INTENT_ID = "fta.revenue.q5_quickbooks_pl"
CS_Q5_QUERY = (
    "Top Client Revenue Overview total income total revenue reported revenue "
    "diligence adjusted revenue EBITDA Enabling Industry Leading Clients "
    "Metrics historical financial performance income statement financial "
    "highlights"
)
CS_Q5_FILE_NAME_FILTER = ("Memorandum", "Financial")

CS_BENCH_INTENT_ID = "kpi.retrieve_bench_and_capacity"
CS_BENCH_QUERY = (
    "Employee Attrition Analysis Employee Analysis Staff beginning of Year "
    "Hires Terminations Staff at End of Year Employee Count bench size "
    "unassigned headcount non-billable available capacity"
)
CS_BENCH_FILE_NAME_FILTER = ("Employee", "Attrition")

# Clearsulting-only leftover-zero overrides (cycle 30 / P1). Shared CQA /
# KPI registry query: strings stay byte-identical (D11). Hash-no: harness-time
# only. D29 live tokens: Memorandum (CIM / Revenue / ACV / Account match 0
# useful CS files — Revenue admits ledgers); Organizational / Chart (KPI /
# Dashboard / Utilization match 0 files or the wrong Utilization workbook).
# account_size gold is BUSINESS_MODEL-only on Memorandum — the shared
# CUSTOMER/FINANCIAL workstream drops it, so CS also overrides workstream.
CS_ACCOUNT_SIZE_INTENT_ID = "cqa.retrieve_account_size"
CS_ACCOUNT_SIZE_QUERY = (
    "Enabling Industry Leading Clients Metrics 650+ Lifetime Clients 200+ "
    "Active Clients Revenue Per Active Client 350k Net Revenue Retention "
    "Customer Retention Client Win History Go-to-Market Engine Driving "
    "Consistent Blue-Chip Client Wins Fortune 30 Clients Served 160+ New "
    "Clients in 2024"
)
CS_ACCOUNT_SIZE_FILE_NAME_FILTER = ("Memorandum",)
CS_ACCOUNT_SIZE_WORKSTREAM_FILTER = ("BUSINESS_MODEL",)

CS_KPI_DASHBOARD_INTENT_ID = "kpi.retrieve_kpi_dashboard"
CS_KPI_DASHBOARD_QUERY = (
    "Project Infinity Organizational Chart Global CEO North America President "
    "EMEA Heads of Practice Strategic Commercial Delivery Head of New Ventures "
    "Sales Client Relationships Managed Services hierarchical reporting "
    "structures People Experience Business Enablement Integration CoE"
)
CS_KPI_DASHBOARD_FILE_NAME_FILTER = ("Organizational", "Chart")

# Elder Care-only leftover-zero overrides (cycle 36 / P2). Shared BMA /
# legal registry query: strings stay byte-identical (D11). Hash-no:
# harness-time only. D29 live tokens: CIM_vF / CIM (OM / Offering /
# Memorandum are not the only tokens); HIPAA / BAA / Non-Compete /
# Non-Disclosure / Jotform / dropbox (Contract / MSA / SOW are not the
# only tokens). CIM gold is BUSINESS_MODEL on CIM_vF — raise top_k so
# the 26-bag can enter top_k*3 (shared top_k=3 → pool max 3). Legal
# gold is LEGAL-tagged BAA/HIPAA/NDA, not caregiver Contract Agreement
# clones. BACKGROUND is not required: all 15 legal gold rows are LEGAL.
EC_CIM_PRESENCE_INTENT_ID = "bma.detect_cim_presence"
EC_CIM_PRESENCE_QUERY = (
    "Proposed Transaction Overview Key Investment Considerations "
    "Entity Structure CIM_vF confidential information memorandum"
)
EC_CIM_PRESENCE_FILE_NAME_FILTER = ("CIM_vF", "CIM")
EC_CIM_PRESENCE_TOP_K = 10

EC_CONTRACTS_INTENT_ID = "legal.contracts_vendors_platform"
EC_CONTRACTS_QUERY = (
    "HIPAA BAA business associate agreement Non-Compete Non-Solicitation "
    "Non-Disclosure Jotform dropbox PHI confidentiality"
)
EC_CONTRACTS_FILE_NAME_FILTER = (
    "HIPAA",
    "BAA",
    "Non-Compete",
    "Non-Disclosure",
    "Jotform",
    "dropbox",
)

# Wave-3 company-scoped leftover / residual overrides (cycle 37 / P1).
# Shared BMA / CQA / KPI / FTA / legal / QoE registry query: strings stay
# byte-identical (D11). Hash-no: harness-time only. D29 live tokens only.
# Do not destack. Do not invent leftover-zero ranking. Do not raise
# _DASHBOARD_SECTION_BONUS. CS / GKF / Elder Care branches above stay
# byte-intact.

INF_VISIBILITY_INTENT_ID = CS_VISIBILITY_INTENT_ID
INF_VISIBILITY_QUERY = (
    "2026E Revenue Visibility Revenue Bridge Project Orange Crush "
    "historical projected revenue contracted bookings visibility"
)
INF_VISIBILITY_FILE_NAME_FILTER = ("Visibility", "2026E")

INF_BENCH_INTENT_ID = CS_BENCH_INTENT_ID
INF_BENCH_QUERY = (
    "contractor census unassigned headcount billability bench size "
    "non-billable available capacity Employee Contractor Census"
)
INF_BENCH_FILE_NAME_FILTER = ("Contractor",)

INF_PEOPLE_INTENT_ID = "bma.retrieve_people_and_org"
# Cycle-38: CIP filename + CIP / org-overview query, no CUSTOMER workstream.
# Cycle-37 CIP + CUSTOMER stayed gold_in_pool=0 (Datapack flood) — do not
# re-add ("CUSTOMER",). If the first pass is empty, fallback drops CIP and
# kills this arm — revert the people branch only. Do not invent leftover-zero
# ranking. Do not destack.
INF_PEOPLE_QUERY = (
    "CIP Detailed Organizational Overview Project Orange Crush "
    "Winter 2026 organizational structure leadership team"
)
INF_PEOPLE_FILE_NAME_FILTER = ("CIP",)

INF_OVERVIEW_INTENT_ID = "bma.retrieve_business_overview"
# Cycle-39: T-M vs Fixed Fee workbook. Unique T-M token (13 chunks / 1 file).
# workstream_filter=None — shared BUSINESS_MODEL ∩ 0 BM chunks. Do not add
# CIP. Do not add CUSTOMER. If T-M first-pass empties, dispatch retries
# Fixed Fee only — never drop filename (cycle-38 CIP Datapack flood).
# CIP 4/17 stays out; top-10 cap ≈ 10/17. Keep vis/bench byte-intact.
# People constants stay unused.
INF_OVERVIEW_QUERY = (
    "T-M vs Fixed Fee Revenue Project Orange Crush "
    "business overview revenue streams what the company sells"
)
INF_OVERVIEW_FILE_NAME_FILTER = ("T-M",)
INF_OVERVIEW_FILE_NAME_FILTER_FALLBACK = ("Fixed Fee",)

IR_LOCATION_INTENT_ID = CS_LOCATION_INTENT_ID
IR_LOCATION_QUERY = (
    "Revenue Retention Dashboard Cube geography revenue by location "
    "Revenue Retention Dashboard Summary customer cube"
)
IR_LOCATION_FILE_NAME_FILTER = ("Cube",)

IR_HEADCOUNT_INTENT_ID = "kpi.retrieve_headcount_attrition"
IR_HEADCOUNT_QUERY = (
    "CIP Graphs headcount by level role breakdown attrition retention "
    "Staff beginning of Year Hires Terminations"
)
IR_HEADCOUNT_FILE_NAME_FILTER = ("Attrition", "Retention")

# Cycle-38 siblings of the closed location / headcount arms (same gold
# neighborhoods). Shared bench / CQA registry query: strings stay
# byte-identical (D11). Do not destack. Do not invent leftover-zero ranking.
IR_BENCH_INTENT_ID = CS_BENCH_INTENT_ID
IR_BENCH_QUERY = IR_HEADCOUNT_QUERY
IR_BENCH_FILE_NAME_FILTER = IR_HEADCOUNT_FILE_NAME_FILTER

IR_ACCOUNT_SIZE_INTENT_ID = CS_ACCOUNT_SIZE_INTENT_ID
IR_ACCOUNT_SIZE_QUERY = IR_LOCATION_QUERY
IR_ACCOUNT_SIZE_FILE_NAME_FILTER = IR_LOCATION_FILE_NAME_FILTER

NB_VISIBILITY_INTENT_ID = CS_VISIBILITY_INTENT_ID
NB_VISIBILITY_QUERY = (
    "B.4 Revenue by Customer Summary Sheet historical projected revenue "
    "2021 2022 2023 2024 customer revenue visibility"
)
NB_VISIBILITY_FILE_NAME_FILTER = ("B.4.Revenue",)
NB_VISIBILITY_WORKSTREAM_FILTER = (
    "BUSINESS_MODEL",
    "FINANCIAL",
    "KPI_OPS",
    "CUSTOMER",
)

NB_Q3_INTENT_ID = "fta.opex.q3_projected_financials"
NB_Q3_QUERY = (
    "Profit and Loss income statement projected financials historical "
    "operating expenses EBITDA Northbound Consulting"
)
NB_Q3_FILE_NAME_FILTER = ("Profit and Loss (1)",)

STRIDE_CONCENTRATION_INTENT_ID = "cqa.retrieve_customer_concentration"
STRIDE_HEALTH_INTENT_ID = "cqa.retrieve_customer_health"
STRIDE_CQA_QUERY = (
    "Audit Customers customer concentration revenue share top customers "
    "client mix FYE 2021 2022"
)
STRIDE_CQA_FILE_NAME_FILTER = ("2.10",)
STRIDE_CONCENTRATION_WORKSTREAM_FILTER = ("CUSTOMER", "FINANCIAL")

STRIDE_Q4_FALLBACK_INTENT_ID = CS_Q4_FALLBACK_INTENT_ID
# Reuse the primary q4 neighborhood (already 0.571 on Stride). Shared
# Ajax/tuition fallback query stays byte-identical (D11).
STRIDE_Q4_FALLBACK_QUERY = (
    "customer concentration top customers revenue by customer largest customers "
    "customer mix payor mix client revenue key customers top 10 customers "
    "customer revenue breakdown revenue by payor revenue by client"
)
STRIDE_Q4_FALLBACK_FILE_NAME_FILTER = ("12.1", "Presentation")

STRIDE_HEADCOUNT_INTENT_ID = IR_HEADCOUNT_INTENT_ID
STRIDE_HEADCOUNT_QUERY = (
    "EBITDA Adjustment Detail utilization R&D add-back delivery capacity "
    "Deck headcount attrition"
)
STRIDE_HEADCOUNT_FILE_NAME_FILTER = ("12.1",)
STRIDE_HEADCOUNT_WORKSTREAM_FILTER = (
    "KPI_OPS",
    "FINANCIAL",
    "BUSINESS_MODEL",
)

# Cycle-40: Embedded Relationships gold 78055fa3 lives on the Deck
# (12.1_Project Josie - Management Presentation Deck.pdf), BUSINESS_MODEL.
# Analog of F1 (2.10 / Audit Customers) — Stride-only replace-filter, not a
# new CQA registry row (D11). Do not destack. Do not invent leftover-zero
# ranking. Do not append Josie. Keep F1–F3 byte-intact.
# D35: skip semantic_search_with_fallback so filename never drops (cycle-38
# CIP death / Inf overview T-M). Empty 12.1 retries Presentation only.
STRIDE_REVENUE_TYPE_INTENT_ID = "cqa.retrieve_revenue_type_and_renewals"
STRIDE_REVENUE_TYPE_QUERY = (
    "Embedded Relationships with Attractive Clients revenue type renewals "
    "recurring project one-time retainer ARR Deck Presentation"
)
STRIDE_REVENUE_TYPE_FILE_NAME_FILTER = ("12.1",)
STRIDE_REVENUE_TYPE_FILE_NAME_FILTER_FALLBACK = ("Presentation",)
STRIDE_REVENUE_TYPE_WORKSTREAM_FILTER = ("BUSINESS_MODEL",)

# Cycle-42: Stride-only kpi_dashboard. Shared KPI registry query: stays
# byte-identical (D11 GL / spreadsheet / utilization). Hash-no:
# harness-time only. D29 live file is 2.24_Project Josie - Backlog -
# Pipeline 7.13.2026.xlsx (gold fea17b3f / 8f49f289). Analog of closed
# revenue_type (12.1 then Presentation). workstream_filter=None —
# filename-only; skip semantic_search_with_fallback (D35) so filename
# never drops onto Bill Rate xlsx (exam pool n=11 is already that
# miss). Empty 2.24 retries Pipeline only. Keep F1–F3 + revenue_type
# byte-intact. CS Organizational / Chart stays slug-isolated. Do not
# destack. Do not invent leftover-zero ranking.
STRIDE_KPI_DASHBOARD_INTENT_ID = CS_KPI_DASHBOARD_INTENT_ID
STRIDE_KPI_DASHBOARD_QUERY = (
    "Backlog & Pipeline 7.13 Data Historical Backlog Pipe Rev "
    "pipeline backlog weighted pipeline bookings"
)
STRIDE_KPI_DASHBOARD_FILE_NAME_FILTER = ("2.24",)
STRIDE_KPI_DASHBOARD_FILE_NAME_FILTER_FALLBACK = ("Pipeline",)

# Cycle-43: Stride-only revenue_visibility. Shared BMA registry query
# stays byte-identical (D11 Ajax / 86.6 million / 24 schools). Hash-no:
# harness-time only. D29 live files: 2.24 Backlog 7.13 (fea17b3f /
# 8f49f289), 2.19 Backlog 6.30 (f6dea57b / 0a54c2c5), 12.1 Deck
# Embedded Relationships (78055fa3). Analog of closed kpi_dashboard
# (2.24 then Pipeline) / revenue_type (12.1 then Presentation).
# First-pass ("2.24", "2.19"); empty first-pass retries ("12.1",)
# only. workstream_filter=None — filename-only; skip
# semantic_search_with_fallback (D35) so filename never drops onto
# Financial Model / Bill Rate (exam pool n=12 is already that miss).
# Do not add Model / KPI / Metrics / CIM. Keep F1–F3 + revenue_type
# + kpi_dashboard byte-intact. CS / Inf / NB / Solvd visibility
# stay slug-isolated. Do not destack. Do not invent leftover-zero
# ranking.
STRIDE_VISIBILITY_INTENT_ID = CS_VISIBILITY_INTENT_ID
STRIDE_VISIBILITY_QUERY = (
    "Backlog & Pipeline 7.13 Backlog & Pipeline 6.30 "
    "Embedded Relationships with Attractive Clients "
    "historical projected revenue contracted bookings visibility"
)
STRIDE_VISIBILITY_FILE_NAME_FILTER = ("2.24", "2.19")
STRIDE_VISIBILITY_FILE_NAME_FILTER_FALLBACK = ("12.1",)

SHERPA_SALES_INTENT_ID = "bma.retrieve_sales_and_customers"
SHERPA_SALES_QUERY = (
    "Enterprise Adopters Turning Use Cases Into Expansion go to market "
    "customer acquisition sales motion"
)
SHERPA_SALES_FILE_NAME_FILTER = ("Memorandum", "Confidential")

SHERPA_QOFE_INTENT_ID = "qoe.retrieve_qofe_report"
SHERPA_QOFE_QUERY = (
    "quality of earnings Financial Package adjusted EBITDA addback "
    "due diligence accounting"
)
SHERPA_QOFE_FILE_NAME_FILTER = ("Financial", "Package")
SHERPA_QOFE_WORKSTREAM_FILTER = ("QUALITY_EARNINGS", "FINANCIAL")

SOLVD_Q2_INTENT_ID = "fta.revenue.q2_revenue_by_segment"
SOLVD_Q2_QUERY = (
    "FINANCIAL HIGHLIGHT YE- December 2022 2023 2024 2025 2026F "
    "revenue by segment financial highlights"
)
SOLVD_Q2_FILE_NAME_FILTER = ("CIM",)

SOLVD_Q3_INTENT_ID = NB_Q3_INTENT_ID
SOLVD_Q3_QUERY = (
    "Income Statement CY22A CY23A CY24A CY25A CY26F CYxxA "
    "historical income statement projected financials"
)
SOLVD_Q3_FILE_NAME_FILTER = ("CIM",)

SOLVD_CONCENTRATION_INTENT_ID = STRIDE_CONCENTRATION_INTENT_ID
SOLVD_CONCENTRATION_QUERY = (
    "Key Highlight client mix customer concentration revenue share "
    "top customers"
)
SOLVD_CONCENTRATION_WORKSTREAM_FILTER = (
    "CUSTOMER",
    "BUSINESS_MODEL",
    "FINANCIAL",
)

SOLVD_CONTRACT_INTENT_ID = "cqa.retrieve_contract_terms"
SOLVD_CONTRACT_QUERY = (
    "Revenue Retention Managed Services Client contract terms "
    "renewal retention"
)
SOLVD_CONTRACT_FILE_NAME_FILTER = ("CIM",)
SOLVD_CONTRACT_WORKSTREAM_FILTER = ("BUSINESS_MODEL",)

# Cycle-41: Solvd-only BMA trio. Shared BMA registry query: stays
# byte-identical (D11 Ajax / 24 schools / 86.6 million). Hash-no:
# harness-time only. D29 live CIM tokens: Revenue Retention /
# Managed Services Client; Subscription-First Economic; AI-Native
# Operating MODEL / Executive Leadership. file_name_filter=("CIM",)
# is the analog of closed q2/q3. workstream_filter=None — skip
# semantic_search_with_fallback (D35) so CIM never drops (cycle-38
# CIP death / Inf overview T-M). Keep q2/q3/concentration/contract
# byte-intact. Do not destack. Do not invent leftover-zero ranking.
SOLVD_VISIBILITY_INTENT_ID = CS_VISIBILITY_INTENT_ID
SOLVD_VISIBILITY_QUERY = (
    "Revenue Retention Managed Services Client AI-Native Operating MODEL "
    "historical projected revenue contracted bookings visibility"
)
SOLVD_VISIBILITY_FILE_NAME_FILTER = ("CIM",)

SOLVD_OVERVIEW_INTENT_ID = INF_OVERVIEW_INTENT_ID
SOLVD_OVERVIEW_QUERY = (
    "Subscription-First Economic subscription-based fixed monthly pricing "
    "business overview revenue streams what the company sells"
)
SOLVD_OVERVIEW_FILE_NAME_FILTER = ("CIM",)

SOLVD_MODEL_CHANGES_INTENT_ID = "bma.retrieve_model_changes_and_dependencies"
SOLVD_MODEL_CHANGES_QUERY = (
    "AI-Native Operating MODEL Executive Leadership Subscription-First "
    "Economic business model change recent initiative"
)
SOLVD_MODEL_CHANGES_FILE_NAME_FILTER = ("CIM",)


def apply_company_intent_overrides(
    intent: RetrievalIntent,
    *,
    company_name: str,
) -> RetrievalIntent:
    """Apply company-scoped query/filter overrides without mutating the registry.

    Clearsulting q4 fallback uses the proven primary-q4 CIM neighborhood so
    golds e22211ae / 5f569542 / 96db4e1f can enter the top_k*3 window.
    Clearsulting location uses the Memorandum office-locations neighborhood so
    golds c7ad6845 / 22d42b52 / 11fb91be can enter the top_k*3 window.
    Clearsulting visibility / q5 / bench use Memorandum and Employee/Attrition
    neighborhoods so in-corpus named-zero gold can enter those pools.
    Clearsulting account_size / kpi_dashboard use Memorandum (BUSINESS_MODEL)
    and Organizational Chart neighborhoods so leftover-zero gold can enter
    those pools. GKF location uses the Ajax CIM corp-org / leadership / DMV
    neighborhood so gold 7ea35a9a can enter the location pool.     Elder Care
    leftover CIM / contracts use CIM_vF section tokens plus a top_k raise,
    and HIPAA/BAA/NDA filename tokens, so those leftover bags can enter
    their pools. Wave-3 slugs (infinitive / integrity_risk / northbound /
    stride / project_sherpa / solvd) use D29 live filename and workstream
    tokens so in-corpus first-cut gold can enter those pools. SPG keeps
    the shared registry healthcare/org tail.
    Shared BMA / CQA / KPI / legal query: stays byte-identical (D11).
    """
    try:
        slug = canonical_company_slug(company_name)
    except (TypeError, UnnormalizableCompanySlugError):
        return intent
    if slug == "clearsulting":
        if intent.intent_id == CS_Q4_FALLBACK_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": CS_Q4_FALLBACK_QUERY,
                    "file_name_filter": list(CS_Q4_FALLBACK_FILE_NAME_FILTER),
                }
            )
        if intent.intent_id == CS_LOCATION_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": CS_LOCATION_QUERY,
                    "file_name_filter": list(CS_LOCATION_FILE_NAME_FILTER),
                }
            )
        if intent.intent_id == CS_VISIBILITY_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": CS_VISIBILITY_QUERY,
                    "file_name_filter": list(CS_VISIBILITY_FILE_NAME_FILTER),
                }
            )
        if intent.intent_id == CS_Q5_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": CS_Q5_QUERY,
                    "file_name_filter": list(CS_Q5_FILE_NAME_FILTER),
                }
            )
        if intent.intent_id == CS_BENCH_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": CS_BENCH_QUERY,
                    "file_name_filter": list(CS_BENCH_FILE_NAME_FILTER),
                }
            )
        if intent.intent_id == CS_ACCOUNT_SIZE_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": CS_ACCOUNT_SIZE_QUERY,
                    "file_name_filter": list(CS_ACCOUNT_SIZE_FILE_NAME_FILTER),
                    "workstream_filter": list(CS_ACCOUNT_SIZE_WORKSTREAM_FILTER),
                }
            )
        if intent.intent_id == CS_KPI_DASHBOARD_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": CS_KPI_DASHBOARD_QUERY,
                    "file_name_filter": list(CS_KPI_DASHBOARD_FILE_NAME_FILTER),
                }
            )
        return intent
    if slug == "gkf" and intent.intent_id == GKF_LOCATION_INTENT_ID:
        return intent.model_copy(
            update={
                "query": GKF_LOCATION_QUERY,
                "file_name_filter": list(GKF_LOCATION_FILE_NAME_FILTER),
            }
        )
    if slug == "elder_care":
        if intent.intent_id == EC_CIM_PRESENCE_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": EC_CIM_PRESENCE_QUERY,
                    "file_name_filter": list(EC_CIM_PRESENCE_FILE_NAME_FILTER),
                    "top_k": EC_CIM_PRESENCE_TOP_K,
                }
            )
        if intent.intent_id == EC_CONTRACTS_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": EC_CONTRACTS_QUERY,
                    "file_name_filter": list(EC_CONTRACTS_FILE_NAME_FILTER),
                }
            )
        return intent
    if slug == "infinitive":
        if intent.intent_id == INF_VISIBILITY_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": INF_VISIBILITY_QUERY,
                    "file_name_filter": list(INF_VISIBILITY_FILE_NAME_FILTER),
                }
            )
        if intent.intent_id == INF_BENCH_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": INF_BENCH_QUERY,
                    "file_name_filter": list(INF_BENCH_FILE_NAME_FILTER),
                }
            )
        if intent.intent_id == INF_OVERVIEW_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": INF_OVERVIEW_QUERY,
                    "file_name_filter": list(INF_OVERVIEW_FILE_NAME_FILTER),
                    "workstream_filter": None,
                }
            )
        # people_and_org: cycle-38 CIP filename + no CUSTOMER first-cut
        # first-pass emptied (CIP not in fetch window); fallback dropped CIP
        # and flooded Datapack / pipeline. Dead leftover — revert. Do not
        # re-add ("CUSTOMER",). Do not invent leftover-zero ranking.
        # Visibility + bench still carry Infinitive.
        return intent
    if slug == "integrity_risk":
        if intent.intent_id == IR_LOCATION_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": IR_LOCATION_QUERY,
                    "file_name_filter": list(IR_LOCATION_FILE_NAME_FILTER),
                }
            )
        if intent.intent_id == IR_HEADCOUNT_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": IR_HEADCOUNT_QUERY,
                    "file_name_filter": list(IR_HEADCOUNT_FILE_NAME_FILTER),
                }
            )
        if intent.intent_id == IR_BENCH_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": IR_BENCH_QUERY,
                    "file_name_filter": list(IR_BENCH_FILE_NAME_FILTER),
                }
            )
        if intent.intent_id == IR_ACCOUNT_SIZE_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": IR_ACCOUNT_SIZE_QUERY,
                    "file_name_filter": list(IR_ACCOUNT_SIZE_FILE_NAME_FILTER),
                }
            )
        return intent
    if slug == "northbound":
        if intent.intent_id == NB_VISIBILITY_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": NB_VISIBILITY_QUERY,
                    "file_name_filter": list(NB_VISIBILITY_FILE_NAME_FILTER),
                    "workstream_filter": list(NB_VISIBILITY_WORKSTREAM_FILTER),
                }
            )
        if intent.intent_id == NB_Q3_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": NB_Q3_QUERY,
                    "file_name_filter": list(NB_Q3_FILE_NAME_FILTER),
                }
            )
        return intent
    if slug == "stride":
        if intent.intent_id == STRIDE_CONCENTRATION_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": STRIDE_CQA_QUERY,
                    "file_name_filter": list(STRIDE_CQA_FILE_NAME_FILTER),
                    "workstream_filter": list(STRIDE_CONCENTRATION_WORKSTREAM_FILTER),
                }
            )
        if intent.intent_id == STRIDE_HEALTH_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": STRIDE_CQA_QUERY,
                    "file_name_filter": list(STRIDE_CQA_FILE_NAME_FILTER),
                }
            )
        if intent.intent_id == STRIDE_Q4_FALLBACK_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": STRIDE_Q4_FALLBACK_QUERY,
                    "file_name_filter": list(STRIDE_Q4_FALLBACK_FILE_NAME_FILTER),
                }
            )
        if intent.intent_id == STRIDE_HEADCOUNT_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": STRIDE_HEADCOUNT_QUERY,
                    "file_name_filter": list(STRIDE_HEADCOUNT_FILE_NAME_FILTER),
                    "workstream_filter": list(STRIDE_HEADCOUNT_WORKSTREAM_FILTER),
                }
            )
        if intent.intent_id == STRIDE_REVENUE_TYPE_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": STRIDE_REVENUE_TYPE_QUERY,
                    "file_name_filter": list(STRIDE_REVENUE_TYPE_FILE_NAME_FILTER),
                    "workstream_filter": list(STRIDE_REVENUE_TYPE_WORKSTREAM_FILTER),
                }
            )
        if intent.intent_id == STRIDE_KPI_DASHBOARD_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": STRIDE_KPI_DASHBOARD_QUERY,
                    "file_name_filter": list(STRIDE_KPI_DASHBOARD_FILE_NAME_FILTER),
                    "workstream_filter": None,
                }
            )
        if intent.intent_id == STRIDE_VISIBILITY_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": STRIDE_VISIBILITY_QUERY,
                    "file_name_filter": list(STRIDE_VISIBILITY_FILE_NAME_FILTER),
                    "workstream_filter": None,
                }
            )
        return intent
    if slug == "project_sherpa":
        if intent.intent_id == SHERPA_SALES_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": SHERPA_SALES_QUERY,
                    "file_name_filter": list(SHERPA_SALES_FILE_NAME_FILTER),
                }
            )
        if intent.intent_id == SHERPA_QOFE_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": SHERPA_QOFE_QUERY,
                    "file_name_filter": list(SHERPA_QOFE_FILE_NAME_FILTER),
                    "workstream_filter": list(SHERPA_QOFE_WORKSTREAM_FILTER),
                }
            )
        return intent
    if slug == "solvd":
        if intent.intent_id == SOLVD_Q2_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": SOLVD_Q2_QUERY,
                    "file_name_filter": list(SOLVD_Q2_FILE_NAME_FILTER),
                }
            )
        if intent.intent_id == SOLVD_Q3_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": SOLVD_Q3_QUERY,
                    "file_name_filter": list(SOLVD_Q3_FILE_NAME_FILTER),
                }
            )
        if intent.intent_id == SOLVD_CONCENTRATION_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": SOLVD_CONCENTRATION_QUERY,
                    "workstream_filter": list(SOLVD_CONCENTRATION_WORKSTREAM_FILTER),
                }
            )
        if intent.intent_id == SOLVD_CONTRACT_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": SOLVD_CONTRACT_QUERY,
                    "file_name_filter": list(SOLVD_CONTRACT_FILE_NAME_FILTER),
                    "workstream_filter": list(SOLVD_CONTRACT_WORKSTREAM_FILTER),
                }
            )
        if intent.intent_id == SOLVD_VISIBILITY_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": SOLVD_VISIBILITY_QUERY,
                    "file_name_filter": list(SOLVD_VISIBILITY_FILE_NAME_FILTER),
                    "workstream_filter": None,
                }
            )
        if intent.intent_id == SOLVD_OVERVIEW_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": SOLVD_OVERVIEW_QUERY,
                    "file_name_filter": list(SOLVD_OVERVIEW_FILE_NAME_FILTER),
                    "workstream_filter": None,
                }
            )
        if intent.intent_id == SOLVD_MODEL_CHANGES_INTENT_ID:
            return intent.model_copy(
                update={
                    "query": SOLVD_MODEL_CHANGES_QUERY,
                    "file_name_filter": list(SOLVD_MODEL_CHANGES_FILE_NAME_FILTER),
                    "workstream_filter": None,
                }
            )
        return intent
    return intent


def build_search_kwargs(
    intent: RetrievalIntent,
    *,
    company_name: str,
    spark: Any,
) -> dict[str, Any]:
    intent = apply_company_intent_overrides(intent, company_name=company_name)
    kwargs: dict[str, Any] = {
        "query": intent.query,
        "spark": spark,
        "company_name": company_name,
        "top_k": intent.top_k,
        "workstream_filter": intent.workstream_filter,
        "file_name_filter": intent.file_name_filter,
        "catalog": intent.catalog,
    }
    if intent.min_chunk_length is not None:
        kwargs["min_chunk_length"] = intent.min_chunk_length
    if intent.tier_filter is not None:
        kwargs["tier_filter"] = intent.tier_filter
    if intent.source_type_priority is not None:
        kwargs["source_type_priority"] = intent.source_type_priority
    if intent.source_type_filter is not None:
        kwargs["source_type_filter"] = intent.source_type_filter
    return kwargs


def _fallback_kwargs_from_intent(
    intent: RetrievalIntent,
    *,
    company_name: str,
    spark: Any,
) -> dict[str, Any]:
    """Kwargs for ``fallback.semantic_search_with_fallback`` — mirrors FTA production path."""
    intent = apply_company_intent_overrides(intent, company_name=company_name)
    min_results = intent.min_results if intent.min_results is not None else 3
    min_chunk_length = intent.min_chunk_length if intent.min_chunk_length is not None else 150
    kwargs: dict[str, Any] = {
        "company_name": company_name,
        "spark": spark,
        "query": intent.query,
        "workstream_filter": intent.workstream_filter,
        "top_k": intent.top_k,
        "file_name_filter": intent.file_name_filter,
        "min_chunk_length": min_chunk_length,
        "min_results": min_results,
        "catalog": intent.catalog,
        "source_type_priority": bool(intent.source_type_priority),
        "intent_id": intent.intent_id,
    }
    if intent.source_type_filter is not None:
        kwargs["source_type_filter"] = intent.source_type_filter
    return kwargs


def _is_infinitive_overview(intent: RetrievalIntent, company_name: str) -> bool:
    try:
        slug = canonical_company_slug(company_name)
    except (TypeError, UnnormalizableCompanySlugError):
        return False
    return slug == "infinitive" and intent.intent_id == INF_OVERVIEW_INTENT_ID


def _is_stride_revenue_type(intent: RetrievalIntent, company_name: str) -> bool:
    try:
        slug = canonical_company_slug(company_name)
    except (TypeError, UnnormalizableCompanySlugError):
        return False
    return slug == "stride" and intent.intent_id == STRIDE_REVENUE_TYPE_INTENT_ID


def _is_stride_kpi_dashboard(intent: RetrievalIntent, company_name: str) -> bool:
    try:
        slug = canonical_company_slug(company_name)
    except (TypeError, UnnormalizableCompanySlugError):
        return False
    return slug == "stride" and intent.intent_id == STRIDE_KPI_DASHBOARD_INTENT_ID


def _is_stride_visibility(intent: RetrievalIntent, company_name: str) -> bool:
    try:
        slug = canonical_company_slug(company_name)
    except (TypeError, UnnormalizableCompanySlugError):
        return False
    return slug == "stride" and intent.intent_id == STRIDE_VISIBILITY_INTENT_ID


def _is_solvd_bma_trio(intent: RetrievalIntent, company_name: str) -> bool:
    try:
        slug = canonical_company_slug(company_name)
    except (TypeError, UnnormalizableCompanySlugError):
        return False
    return slug == "solvd" and intent.intent_id in {
        SOLVD_VISIBILITY_INTENT_ID,
        SOLVD_OVERVIEW_INTENT_ID,
        SOLVD_MODEL_CHANGES_INTENT_ID,
    }


def dispatch_retrieval(
    intent: RetrievalIntent,
    *,
    company_name: str,
    spark: Any,
    ablation_arm: str | None = None,
) -> Any:
    """Production-faithful retrieval dispatch — imports migrated semantic_search."""
    from agents.shared.retrieval import semantic_search

    kwargs = build_search_kwargs(intent, company_name=company_name, spark=spark)
    merge_rank_mode = ablation_arm_to_merge_rank_mode(ablation_arm)

    # Infinitive overview: T-M first, Fixed Fee if empty. Never drop
    # filename — shared fallback floods Datapack when workstream is None
    # (cycle-38 CIP death). Not leftover-zero ranking. Not people.
    if _is_infinitive_overview(intent, company_name):
        if merge_rank_mode is not None:
            kwargs["merge_rank_mode"] = merge_rank_mode
        result = semantic_search(**kwargs)
        if len(getattr(result, "chunks", None) or []) == 0:
            result = semantic_search(
                **{
                    **kwargs,
                    "file_name_filter": list(INF_OVERVIEW_FILE_NAME_FILTER_FALLBACK),
                }
            )
        return result

    # Stride revenue_type: 12.1 first, Presentation if empty. Never drop
    # filename — shared fallback unions / drops 12.1 and floods CIM /
    # Revenue / Model (cycle-38 CIP death). Not leftover-zero ranking.
    # F1–F3 stay on the shared fallback path.
    if _is_stride_revenue_type(intent, company_name):
        if merge_rank_mode is not None:
            kwargs["merge_rank_mode"] = merge_rank_mode
        result = semantic_search(**kwargs)
        if len(getattr(result, "chunks", None) or []) == 0:
            result = semantic_search(
                **{
                    **kwargs,
                    "file_name_filter": list(STRIDE_REVENUE_TYPE_FILE_NAME_FILTER_FALLBACK),
                }
            )
        return result

    # Stride kpi_dashboard: 2.24 first, Pipeline if empty. Never drop
    # filename — shared fallback unions / drops 2.24 and floods Bill
    # Rate xlsx (exam pool n=11 / D35). Not leftover-zero ranking.
    # F1–F3 + revenue_type stay on their existing paths. CS
    # Organizational / Chart stays slug-isolated.
    if _is_stride_kpi_dashboard(intent, company_name):
        if merge_rank_mode is not None:
            kwargs["merge_rank_mode"] = merge_rank_mode
        result = semantic_search(**kwargs)
        if len(getattr(result, "chunks", None) or []) == 0:
            result = semantic_search(
                **{
                    **kwargs,
                    "file_name_filter": list(STRIDE_KPI_DASHBOARD_FILE_NAME_FILTER_FALLBACK),
                }
            )
        return result

    # Stride visibility: 2.24+2.19 first, 12.1 if empty. Never drop
    # filename — shared fallback unions / drops 2.24 and floods
    # Financial Model / Bill Rate (exam pool n=12 / D35). Not
    # leftover-zero ranking. F1–F3 + revenue_type + kpi_dashboard
    # stay on their existing paths. CS / Inf / NB / Solvd visibility
    # stay slug-isolated.
    if _is_stride_visibility(intent, company_name):
        if merge_rank_mode is not None:
            kwargs["merge_rank_mode"] = merge_rank_mode
        result = semantic_search(**kwargs)
        if len(getattr(result, "chunks", None) or []) == 0:
            result = semantic_search(
                **{
                    **kwargs,
                    "file_name_filter": list(STRIDE_VISIBILITY_FILE_NAME_FILTER_FALLBACK),
                }
            )
        return result

    # Solvd BMA trio: CIM only. Never drop filename — shared fallback
    # unions / drops CIM and floods Pipeline / Databook (cycle-38 CIP
    # death). workstream_filter=None so D35 skip is mandatory. Closed
    # q2/q3/CQA stay on the shared fallback path.
    if _is_solvd_bma_trio(intent, company_name):
        if merge_rank_mode is not None:
            kwargs["merge_rank_mode"] = merge_rank_mode
        return semantic_search(**kwargs)

    if uses_fallback_wrapper(intent):
        min_results = intent.min_results if intent.min_results is not None else 3
        if merge_rank_mode is None:
            from agents.shared.fallback import semantic_search_with_fallback

            result, _used_fallback = semantic_search_with_fallback(
                **_fallback_kwargs_from_intent(
                    intent,
                    company_name=company_name,
                    spark=spark,
                )
            )
            return result

        # Ablation-only: ``fallback.py`` does not accept ``merge_rank_mode`` — retain
        # inline retry so merge-rank arms keep threading through ``semantic_search``.
        kwargs["merge_rank_mode"] = merge_rank_mode
        result = semantic_search(**kwargs)
        if len(result.chunks) < min_results and intent.file_name_filter:
            result = semantic_search(**{**kwargs, "file_name_filter": None})
        return result

    if merge_rank_mode is not None:
        kwargs["merge_rank_mode"] = merge_rank_mode
    result = semantic_search(**kwargs)
    # Empty-path: direct intents (CQA/KPI) skip the fallback wrapper, but a
    # workstream/filename filter that yields 0 cannot admit gold. Re-enter
    # fallback.py so it can drop those filters. Non-empty direct stays direct.
    if (
        merge_rank_mode is None
        and len(getattr(result, "chunks", None) or []) == 0
        and (intent.workstream_filter or intent.file_name_filter)
    ):
        from agents.shared.fallback import semantic_search_with_fallback

        result, _used_fallback = semantic_search_with_fallback(
            **_fallback_kwargs_from_intent(
                intent,
                company_name=company_name,
                spark=spark,
            )
        )
    return result


def compute_mrr(positive_ids: set[str], ranked_ids: Sequence[str]) -> float:
    for index, chunk_id in enumerate(ranked_ids, start=1):
        if chunk_id in positive_ids:
            return 1.0 / index
    return 0.0


def compute_metrics(
    intent: RetrievalIntent,
    gold: GoldLabel,
    route_result: Any,
) -> HarnessResult:
    """Metric math per spec §5.8."""
    if (
        gold.aggregate_exclude
        or gold.gold_status == "bootstrap_failed"
        or not gold.positive_chunk_ids
    ):
        return HarnessResult(
            intent_id=intent.intent_id,
            eval_status="skipped_bootstrap_failed",
            result_count=0,
        )

    ranked_ids = [_chunk_id_from_row(chunk) for chunk in route_result.chunks]
    result_count = len(ranked_ids)
    eval_k = min(10, intent.top_k)
    effective_k = min(eval_k, result_count)
    positives = set(gold.positive_chunk_ids)
    negatives = set(gold.negative_chunk_ids or [])

    top_eval = ranked_ids[:eval_k]
    top_effective = ranked_ids[:effective_k]

    recall = len(positives & set(top_eval)) / len(positives) if positives else 0.0
    if result_count == 0:
        recall = 0.0

    precision_at_10 = None
    if negatives and result_count > 0:
        conflict_count = len(negatives & set(top_effective))
        precision_at_10 = (effective_k - conflict_count) / effective_k

    basis_conflict_at_10 = None
    if (
        gold.negative_method == "basis_rule"
        and negatives
        and result_count > 0
    ):
        basis_conflict_at_10 = len(negatives & set(top_effective)) / effective_k

    negatives_in_top_3 = len(negatives & set(ranked_ids[:3])) if negatives else None

    return HarnessResult(
        intent_id=intent.intent_id,
        eval_status="evaluated",
        eval_k=eval_k,
        effective_k=effective_k,
        recall_at_10=recall,
        precision_at_10=precision_at_10,
        basis_conflict_at_10=basis_conflict_at_10,
        mrr=compute_mrr(positives, ranked_ids),
        result_count=result_count,
        mode=normalize_mode(route_result.mode),
        negatives_in_top_3=negatives_in_top_3,
    )


def metric_gate_pass(metric: str, before: float, after: float) -> bool:
    if metric in LOWER_IS_BETTER:
        return after <= before
    if metric in HIGHER_IS_BETTER:
        return after >= before
    raise ValueError(f"unknown gate metric: {metric}")


def _metric_value(result: HarnessResult, metric: str) -> float | None:
    return getattr(result, metric)


def build_harness_deltas(
    *,
    run_id: str,
    baseline_ref_run_id: str,
    intent_id: str,
    baseline: HarnessResult,
    current: HarnessResult,
    in_gated_scope: bool,
) -> list[HarnessDelta]:
    deltas: list[HarnessDelta] = []
    for metric in (*GATE_METRICS, *AUDIT_METRICS):
        before = _metric_value(baseline, metric)
        after = _metric_value(current, metric)
        if before is None or after is None:
            continue
        delta = after - before
        deltas.append(
            HarnessDelta(
                run_id=run_id,
                baseline_ref_run_id=baseline_ref_run_id,
                intent_id=intent_id,
                metric=metric,  # type: ignore[arg-type]
                before=before,
                after=after,
                delta=delta,
                gate_pass=metric_gate_pass(metric, before, after),
                in_gated_scope=in_gated_scope,
            )
        )
    return deltas


def build_intent_gate_summary(
    intent_id: str,
    *,
    baseline: HarnessResult | None,
    current: HarnessResult,
    deltas: Sequence[HarnessDelta],
    in_gated_scope: bool,
) -> IntentGateSummary:
    if current.eval_status == "skipped_bootstrap_failed":
        return IntentGateSummary(
            intent_id=intent_id,
            intent_gate_pass=True,
            in_gated_scope=False,
            eval_status="skipped_bootstrap_failed",
        )

    gate_deltas = [
        row
        for row in deltas
        if row.metric in GATE_METRICS and row.in_gated_scope
    ]
    intent_gate_pass = all(row.gate_pass for row in gate_deltas) if gate_deltas else True

    metric_results = {
        row.metric: {
            "before": row.before,
            "after": row.after,
            "delta": row.delta,
            "gate_pass": row.gate_pass,
        }
        for row in deltas
    }

    return IntentGateSummary(
        intent_id=intent_id,
        intent_gate_pass=intent_gate_pass,
        in_gated_scope=in_gated_scope,
        eval_status=current.eval_status,
        metric_results=metric_results or None,
    )


def compare_results(
    *,
    run_id: str,
    baseline_ref_run_id: str,
    gated_intents: Sequence[str],
    baseline_results: Mapping[str, HarnessResult],
    current_results: Mapping[str, HarnessResult],
) -> tuple[list[HarnessDelta], list[IntentGateSummary]]:
    """Pure compare aggregation — golden gate tests target this function."""
    deltas: list[HarnessDelta] = []
    intent_gates: list[IntentGateSummary] = []

    for intent_id in sorted(gated_intents):
        current = current_results[intent_id]
        baseline = baseline_results[intent_id]
        in_scope = True
        intent_deltas = build_harness_deltas(
            run_id=run_id,
            baseline_ref_run_id=baseline_ref_run_id,
            intent_id=intent_id,
            baseline=baseline,
            current=current,
            in_gated_scope=in_scope,
        )
        deltas.extend(intent_deltas)
        intent_gates.append(
            build_intent_gate_summary(
                intent_id,
                baseline=baseline,
                current=current,
                deltas=intent_deltas,
                in_gated_scope=in_scope,
            )
        )

    for intent_id, current in sorted(current_results.items()):
        if intent_id in gated_intents:
            continue
        if current.eval_status != "skipped_bootstrap_failed":
            continue
        intent_gates.append(
            IntentGateSummary(
                intent_id=intent_id,
                intent_gate_pass=True,
                in_gated_scope=False,
                eval_status="skipped_bootstrap_failed",
            )
        )

    return deltas, intent_gates


def rollup_by_agent(
    results: Sequence[HarnessResult],
) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[HarnessResult]] = {}
    for result in results:
        if result.eval_status != "evaluated":
            continue
        agent_id = derive_agent_id(result.intent_id)
        buckets.setdefault(agent_id, []).append(result)

    rollup: dict[str, dict[str, Any]] = {}
    for agent_id, rows in sorted(buckets.items()):
        recall_vals = [row.recall_at_10 for row in rows if row.recall_at_10 is not None]
        precision_vals = [
            row.precision_at_10 for row in rows if row.precision_at_10 is not None
        ]
        basis_vals = [
            row.basis_conflict_at_10
            for row in rows
            if row.basis_conflict_at_10 is not None
        ]
        evaluated = len(rows)
        fallback = sum(1 for row in rows if row.mode == "keyword")
        empty = sum(1 for row in rows if row.result_count == 0)
        rollup[agent_id] = {
            "intent_count": evaluated,
            "recall_at_10_avg": sum(recall_vals) / len(recall_vals) if recall_vals else None,
            "precision_at_10_avg": (
                sum(precision_vals) / len(precision_vals) if precision_vals else None
            ),
            "basis_conflict_at_10_avg": (
                sum(basis_vals) / len(basis_vals) if basis_vals else None
            ),
            "fallback_rate": fallback / evaluated if evaluated else None,
            "empty_rate": empty / evaluated if evaluated else None,
        }
    return rollup


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _git_sha() -> str | None:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=_repo_root(),
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except (OSError, subprocess.CalledProcessError):
        return None


def _write_report_atomic(path: Path, report: HarnessReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    payload = report.model_dump(mode="json")
    temp_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temp_path.replace(path)


class EvalHarness:
    """Offline harness runner with store dual-write."""

    def __init__(
        self,
        *,
        registry_path: Path | None = None,
        gold_path: Path | None = None,
        company_slug: str | None = None,
        reports_dir: Path | None = None,
        retrieval_dispatch: Callable[..., Any] | None = None,
    ) -> None:
        self.registry_path = registry_path or default_registry_path()
        if gold_path is not None:
            self.gold_path = gold_path
        elif company_slug is not None:
            self.gold_path = default_gold_path(company_slug)
        else:
            raise PreconditionError(
                "EvalHarness requires gold_path or company_slug; "
                "no silent Elder Care fallback"
            )
        self.reports_dir = reports_dir or default_reports_dir()
        self._retrieval_dispatch = retrieval_dispatch or dispatch_retrieval

    def _load_intent_map(self) -> dict[str, RetrievalIntent]:
        intents = load_registry(self.registry_path)
        return {intent.intent_id: intent for intent in intents}

    def _load_gold_map(
        self,
        *,
        company_name: str,
        catalog: str,
    ) -> dict[str, GoldLabel]:
        labels = [
            label
            for label in load_gold_labels(self.gold_path)
            if label.company_name == company_name and label.catalog == catalog
        ]
        return {label.intent_id: label for label in labels}

    def _resolve_scope(
        self,
        *,
        run_type: str,
        registry_map: Mapping[str, RetrievalIntent],
        gold_map: Mapping[str, GoldLabel],
        company_name: str,
        catalog: str,
        affected_intents: Sequence[str] | None,
        gated_intents: Sequence[str] | None,
    ) -> tuple[list[str], list[str]]:
        if affected_intents is None:
            if run_type == "enhancement":
                raise PreconditionError(
                    "run_type enhancement requires explicit affected_intents"
                )
            affected = sorted(registry_map.keys())
        else:
            affected = sorted(affected_intents)

        if gated_intents is None:
            eligible = set(
                gate_eligible_intent_ids(
                    gold_map.values(),
                    company_name=company_name,
                    catalog=catalog,
                )
            )
            gated = sorted(intent_id for intent_id in affected if intent_id in eligible)
        else:
            gated = sorted(gated_intents)

        return affected, gated

    def validate_baseline_ref(
        self,
        store: EvalStore,
        baseline_run_id: str,
        *,
        gated_intents: Sequence[str],
        current_manifest: HarnessRun,
    ) -> None:
        """Preflight baseline checks — spec §5.12.8 steps 2–6."""
        baseline_report = store.get_run(baseline_run_id)
        baseline = baseline_report.manifest

        if baseline.harness_status != "complete":
            raise BaselineInvalidError(
                f"baseline run not complete: {baseline_run_id} ({baseline.harness_status})"
            )
        if baseline.run_type != "baseline":
            raise BaselineInvalidError(
                f"baseline_ref_run_id must reference run_type baseline, got {baseline.run_type}"
            )

        baseline_by_intent = {row.intent_id: row for row in baseline_report.results}
        missing = [
            intent_id
            for intent_id in gated_intents
            if baseline_by_intent.get(intent_id) is None
            or baseline_by_intent[intent_id].eval_status != "evaluated"
        ]
        if missing:
            raise CoverageError(
                f"baseline missing evaluated rows for gated intents: {missing}"
            )

        if baseline.gold_snapshot != current_manifest.gold_snapshot:
            raise GoldSnapshotMismatchError(
                "gold_snapshot mismatch between baseline and current manifest"
            )
        if baseline.registry_hash != current_manifest.registry_hash:
            raise RegistryHashMismatchError(
                "registry_hash mismatch between baseline and current manifest"
            )
        if baseline.ingestion_snapshot != current_manifest.ingestion_snapshot:
            raise IngestionSnapshotMismatchError(
                "ingestion_snapshot mismatch between baseline and current manifest"
            )

    def compare(
        self,
        store: EvalStore,
        baseline_run_id: str,
        current_run_id: str,
        *,
        gated_intents: Sequence[str] | None = None,
    ) -> tuple[list[HarnessDelta], list[IntentGateSummary]]:
        current_report = store.get_run(current_run_id)
        current_manifest = current_report.manifest
        scope = (
            list(gated_intents)
            if gated_intents is not None
            else list(current_manifest.gated_intents)
        )

        self.validate_baseline_ref(
            store,
            baseline_run_id,
            gated_intents=scope,
            current_manifest=current_manifest,
        )

        baseline_report = store.get_run(baseline_run_id)
        baseline_by_intent = {row.intent_id: row for row in baseline_report.results}
        current_by_intent = {row.intent_id: row for row in current_report.results}

        return compare_results(
            run_id=current_run_id,
            baseline_ref_run_id=baseline_run_id,
            gated_intents=scope,
            baseline_results=baseline_by_intent,
            current_results=current_by_intent,
        )

    def run(
        self,
        *,
        run_type: str,
        company_name: str,
        catalog: str,
        store: EvalStore,
        store_backend: str,
        baseline_ref_run_id: str | None = None,
        affected_intents: Sequence[str] | None = None,
        gated_intents: Sequence[str] | None = None,
        ablation_config: dict[str, Any] | None = None,
        spark: Any | None = None,
        run_id: str | None = None,
        skip_retrieval: bool = False,
    ) -> HarnessReport:
        registry_map = self._load_intent_map()
        gold_labels = [
            label
            for label in load_gold_labels(self.gold_path)
            if label.company_name == company_name and label.catalog == catalog
        ]
        if not gold_labels:
            raise PreconditionError(
                f"no gold labels for company_name={company_name!r} catalog={catalog!r}"
            )

        ingestion_snapshot = validate_ingestion_snapshot_consistency(gold_labels)
        registry_hash = compute_registry_hash(self.registry_path)
        gold_snapshot = compute_gold_snapshot(gold_labels)
        gold_map = {label.intent_id: label for label in gold_labels}

        resolved_ablation_arm = resolve_ablation_arm(ablation_config)
        merge_rank_mode_for_run = ablation_arm_to_merge_rank_mode(resolved_ablation_arm)

        resolved_affected, resolved_gated = self._resolve_scope(
            run_type=run_type,
            registry_map=registry_map,
            gold_map=gold_map,
            company_name=company_name,
            catalog=catalog,
            affected_intents=affected_intents,
            gated_intents=gated_intents,
        )

        for intent_id in resolved_affected:
            if intent_id not in registry_map:
                raise PreconditionError(f"unknown intent_id in scope: {intent_id}")
            if intent_id not in gold_map:
                raise PreconditionError(f"missing gold label for intent_id: {intent_id}")

        if run_type in {"enhancement", "ablation"} and not baseline_ref_run_id:
            baseline_ref_run_id = store.get_latest_baseline(company_name, catalog)
            if baseline_ref_run_id is None:
                raise BaselineInvalidError("no complete baseline run found for tenant")

        manifest = HarnessRun(
            run_id=run_id or f"{run_type}_{uuid.uuid4().hex[:12]}",
            run_type=run_type,  # type: ignore[arg-type]
            company_name=company_name,
            catalog=catalog,
            ingestion_snapshot=ingestion_snapshot,
            registry_hash=registry_hash,
            gold_snapshot=gold_snapshot,
            git_sha=_git_sha(),
            git_branch=os.environ.get("GIT_BRANCH"),
            affected_intents=resolved_affected,
            gated_intents=resolved_gated,
            ablation_config=ablation_config,
            ablation_arm=resolved_ablation_arm if run_type == "ablation" else None,
            baseline_ref_run_id=baseline_ref_run_id,
            store_backend=store_backend,  # type: ignore[arg-type]
            harness_status="incomplete",
            intent_count=len(resolved_affected),
            created_at=_utc_now(),
        )

        if baseline_ref_run_id and run_type in {"enhancement", "ablation"}:
            self.validate_baseline_ref(
                store,
                baseline_ref_run_id,
                gated_intents=resolved_gated,
                current_manifest=manifest,
            )

        store.insert_run(manifest)
        results: list[HarnessResult] = []
        provenance_records: list[ProvenanceRecord] = []

        active_spark = spark
        if not skip_retrieval and active_spark is None:
            try:
                from pyspark.sql import SparkSession

                active_spark = SparkSession.getActiveSession()
            except ImportError:
                active_spark = None
            if active_spark is None:
                raise PreconditionError(
                    "SparkSession required for live retrieval dispatch"
                )

        for intent_id in resolved_affected:
            intent = registry_map[intent_id]
            gold = gold_map[intent_id]
            result_ablation_arm = resolved_ablation_arm if run_type == "ablation" else None
            if (
                gold.aggregate_exclude
                or gold.gold_status == "bootstrap_failed"
                or not gold.positive_chunk_ids
            ):
                result_count = 0
                if not skip_retrieval:
                    route_result = self._retrieval_dispatch(
                        intent,
                        company_name=company_name,
                        spark=active_spark,
                        ablation_arm=resolved_ablation_arm,
                    )
                    result_count = len(route_result.chunks)
                    provenance_records.append(
                        build_provenance_record(
                            intent,
                            company_name=company_name,
                            route_result=route_result,
                            run_id=manifest.run_id,
                        )
                    )
                result = HarnessResult(
                    intent_id=intent_id,
                    eval_status="skipped_bootstrap_failed",
                    result_count=result_count,
                    ablation_arm=result_ablation_arm,
                )
                results.append(result)
                logger.info(
                    "intent_id=%s mode=skipped result_count=%s eval_status=skipped_bootstrap_failed "
                    "ablation_arm=%s merge_rank_mode=%s",
                    intent_id,
                    result_count,
                    result_ablation_arm,
                    merge_rank_mode_for_run,
                )
                continue

            if skip_retrieval:
                raise PreconditionError("skip_retrieval set but intent is gate-eligible")

            route_result = self._retrieval_dispatch(
                intent,
                company_name=company_name,
                spark=active_spark,
                ablation_arm=resolved_ablation_arm,
            )
            result = compute_metrics(intent, gold, route_result)
            result = result.model_copy(update={"ablation_arm": result_ablation_arm})
            results.append(result)
            provenance_records.append(
                build_provenance_record(
                    intent,
                    company_name=company_name,
                    route_result=route_result,
                    run_id=manifest.run_id,
                )
            )
            logger.info(
                "intent_id=%s mode=%s result_count=%s eval_status=%s "
                "ablation_arm=%s merge_rank_mode=%s",
                intent_id,
                result.mode,
                result.result_count,
                result.eval_status,
                result_ablation_arm,
                merge_rank_mode_for_run,
            )

        store.append_results(manifest.run_id, results)
        if provenance_records:
            store.append_provenance(manifest.run_id, provenance_records)

        deltas: list[HarnessDelta] | None = None
        intent_gates: list[IntentGateSummary] | None = None
        gate_pass: bool | None = None

        if run_type in {"enhancement", "ablation"} and baseline_ref_run_id:
            deltas, intent_gates = self.compare(
                store,
                baseline_ref_run_id,
                manifest.run_id,
                gated_intents=resolved_gated,
            )
            store.append_deltas(manifest.run_id, deltas)
            evaluated_gates = [
                gate
                for gate in intent_gates
                if gate.in_gated_scope and gate.eval_status == "evaluated"
            ]
            gate_pass = (
                all(gate.intent_gate_pass for gate in evaluated_gates)
                if evaluated_gates
                else None
            )

        agent_rollup = rollup_by_agent(results)
        evaluated_rows = [row for row in results if row.eval_status == "evaluated"]
        fallback_rate = None
        empty_rate = None
        if evaluated_rows:
            fallback_rate = sum(
                1 for row in evaluated_rows if row.mode == "keyword"
            ) / len(evaluated_rows)
            empty_rate = sum(
                1 for row in evaluated_rows if row.result_count == 0
            ) / len(evaluated_rows)

        report = HarnessReport(
            manifest=manifest,
            results=results,
            intent_gates=intent_gates,
            rollup_by_agent=agent_rollup,
            deltas=deltas,
            provenance_sample=provenance_records[:5] or None,
        )

        _write_report_atomic(self.reports_dir / f"{manifest.run_id}.json", report)

        if isinstance(store, SqliteEvalStore):
            store.set_report_extras(
                manifest.run_id,
                intent_gates=intent_gates,
                rollup_by_agent=agent_rollup,
                provenance_sample=report.provenance_sample,
            )

        finalized = store.finalize_run(
            manifest.run_id,
            gate_pass=gate_pass,
            fallback_rate=fallback_rate,
            empty_rate=empty_rate,
        )
        report.manifest = finalized
        return report
