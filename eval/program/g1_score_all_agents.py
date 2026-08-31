"""Full G1 scoring — all golden-checklist agents vs fresh e2e rows (multi-company)."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

_REPO_ROOT = Path(__file__).resolve().parents[2]
import sys

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from eval.retrieval.companies import canonical_company_slug  # noqa: E402
from databricks.sdk import WorkspaceClient  # noqa: E402

w = WorkspaceClient(
    host=os.environ["DATABRICKS_SERVER_HOSTNAME"],
    token=os.environ["DATABRICKS_TOKEN"],
)
WH = os.environ["DATABRICKS_HTTP_PATH"].rstrip("/").split("/")[-1]
E2E_RUN = "827597669988464"  # post-fix closeout 2026-07-28 (Elder Care reference)

_AGENTS = ("bma", "cqa", "kpi", "qoe", "fta", "legal", "profiler")

# (floor, total, gate_str) per agent, or None = no golden floor — informational only.
_ELDER_CARE_BASELINES: dict[str, tuple[int, int, str] | None] = {
    "bma": (7, 7, ">=7/7"),
    "cqa": (3, 6, ">=3/6"),
    "kpi": (3, 3, "3/3"),
    "qoe": (5, 6, ">=5/6"),
    "fta": (16, 18, ">=16/18"),
    "legal": (9, 11, ">=9/11"),
    "profiler": (7, 7, ">=7/7"),
}

BASELINES: dict[str, dict[str, tuple[int, int, str] | None]] = {
    "elder_care": _ELDER_CARE_BASELINES,
    "clearsulting": dict.fromkeys(_AGENTS),
    "gkf": dict.fromkeys(_AGENTS),
    "spg": dict.fromkeys(_AGENTS),
}


def company_slug(company_name: str) -> str:
    return canonical_company_slug(company_name)


def q(sql: str) -> tuple[list[str], list]:
    stmt = w.statement_execution.execute_statement(
        warehouse_id=WH, statement=sql, wait_timeout="50s"
    )
    if stmt.status.state.value != "SUCCEEDED":
        raise RuntimeError(f"SQL failed: {stmt.status}")
    cols = [c.name for c in stmt.manifest.schema.columns]
    return cols, stmt.result.data_array or []


def jl(s: str | None) -> object:
    if not s:
        return None
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return s


def nonempty(v: object) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, list):
        return len(v) > 0
    if isinstance(v, dict):
        return len(v) > 0
    return True


def count_pass(verdicts: dict) -> int:
    return sum(1 for v in verdicts.values() if v == "pass")


def fetch_analysis(table: str, cols: list[str], company_name: str) -> dict:
    col_sql = ", ".join(cols)
    c, rows = q(
        f"SELECT CAST(created_at AS STRING) AS ts, {col_sql} "
        f"FROM uc13_ale.analysis.{table} "
        f"WHERE company_name='{company_name}' ORDER BY created_at DESC LIMIT 1"
    )
    if not rows:
        return {}
    return dict(zip(c, rows[0]))


def fetch_profiler(company_name: str) -> dict:
    c, rows = q(
        f"""
        SELECT CAST(created_at AS STRING) AS ts,
          industry_overlay, overlay_confidence, revenue_model, revenue_model_note,
          business_description, deal_type, banked, banked_note, vertical_subsector,
          data_room_gaps
        FROM uc13_ale.classification.company_profile
        WHERE company_name='{company_name}' ORDER BY created_at DESC LIMIT 1
        """
    )
    return dict(zip(c, rows[0])) if rows else {}


def score_bma(d: dict) -> tuple[int, dict]:
    v = {}
    ps = jl(d.get("products_services_json"))
    po = jl(d.get("people_and_org_json"))
    cp = jl(d.get("customer_profile_json"))
    sm_tag = d.get("sales_motion_tag")
    sm = jl(d.get("sales_motion_json"))
    kd = jl(d.get("key_dependencies_json"))
    gaps = jl(d.get("data_room_gaps"))
    oc = d.get("overlay_conflict")

    v["products_services"] = "pass" if nonempty(ps) else "partial"
    v["people_org"] = "pass" if nonempty(po) else "partial"
    v["customer_profile"] = "pass" if nonempty(cp) else "partial"
    v["sales_motion"] = (
        "pass" if sm_tag and nonempty(sm) else "partial" if sm_tag or sm else "gap-correct"
    )
    v["key_dependencies"] = "pass" if nonempty(kd) else "partial"
    v["data_room_gaps"] = "pass" if isinstance(gaps, list) else "partial"
    v["overlay_conflict"] = (
        "pass" if str(oc).lower() in ("false", "0") else "partial"
    )
    return count_pass(v), v


def score_cqa(d: dict) -> tuple[int, dict]:
    v = {}
    top = jl(d.get("top_customers_json"))
    ret = jl(d.get("retention_json"))
    tenure = jl(d.get("customer_tenure_json"))
    payor = jl(d.get("payor_mix_json"))
    disc = jl(d.get("discrepancies_json"))
    gaps = jl(d.get("data_room_gaps"))

    v["concentration"] = "pass" if isinstance(top, list) and top else "gap-correct"
    ret_null = isinstance(ret, dict) and all(
        ret.get(k) is None for k in ("nrr_pct", "grr_pct", "logo_churn_pct")
    )
    v["retention"] = "gap-correct" if ret_null and disc else "pass" if not ret_null else "partial"
    v["customer_tenure"] = (
        "pass"
        if isinstance(tenure, dict) and nonempty(tenure.get("tenure_distribution_note"))
        else "partial"
    )
    if isinstance(payor, list):
        has_vals = any(
            isinstance(p, dict) and p.get("pct_of_revenue") is not None for p in payor
        )
        v["payor_mix"] = "pass" if has_vals else "partial"
    elif isinstance(payor, dict):
        v["payor_mix"] = "partial" if any(x is not None for x in payor.values()) else "gap-correct"
    else:
        v["payor_mix"] = "gap-correct"
    v["discrepancies_json"] = "pass" if isinstance(disc, list) and len(disc) >= 3 else "partial"
    v["data_room_gaps"] = "pass" if isinstance(gaps, list) else "partial"
    return count_pass(v), v


_OVERLAY_TO_KPI_COLUMN: dict[str, str] = {
    "tech_services": "tech_services_kpis_json",
    "healthcare_services": "healthcare_kpis_json",
    "b2b_saas": "saas_kpis_json",
    "industrial": "industrial_kpis_json",
    "consumer": "consumer_kpis_json",
}

# Overlay-specific field name per sibling KPI column. Used only to gauge
# non-empty population depth (5+ populated fields = pass) — the field lists
# below are a representative subset of each block's schema, not exhaustive.
_OVERLAY_BLOCK_FIELDS: dict[str, list[str]] = {
    "healthcare_kpis_json": [
        "census_or_patient_panel", "caregiver_headcount", "clinician_headcount",
        "utilization_or_productivity_note", "compliance_incidents",
        "credentialing_status_note", "site_level_visibility",
    ],
    "tech_services_kpis_json": [
        "utilization_rate_pct", "utilization_period", "average_bill_rate_dollars",
        "contractor_pct_of_workforce", "delivery_geography_note",
        "average_acv_dollars", "bookings_stated", "backlog_months_of_revenue",
        "pipeline_coverage_months",
    ],
    "saas_kpis_json": [
        "nrr_pct", "grr_pct", "logo_churn_pct", "cac_payback_months",
        "rule_of_40_stated", "arr_per_fte_dollars", "magic_number_stated",
    ],
    "industrial_kpis_json": [
        "backlog_months", "capacity_utilization_pct", "on_time_delivery_pct",
        "aftermarket_revenue_pct", "inventory_turns", "capex_pct_revenue",
    ],
    "consumer_kpis_json": [
        "repeat_rate_12mo_pct", "contribution_margin_pct", "return_rate_pct",
        "ltv_cac_ratio", "blended_cac_trend_note", "channel_mix_note",
        "platform_concentration_note",
    ],
}


def score_kpi(d: dict) -> tuple[int, dict]:
    v = {}
    overlay = d.get("overlay_confirmed")
    missing = jl(d.get("missing_kpis_json"))

    v["overlay_confirmed"] = (
        "pass" if overlay in _OVERLAY_TO_KPI_COLUMN else "partial"
    )

    resolved_col = _OVERLAY_TO_KPI_COLUMN.get(overlay)
    if resolved_col is not None:
        block = jl(d.get(resolved_col))
        block_fields = _OVERLAY_BLOCK_FIELDS[resolved_col]
        if isinstance(block, dict):
            pop = sum(1 for f in block_fields if nonempty(block.get(f)))
            v["overlay_block_fields"] = "pass" if pop >= 5 else "partial"
        else:
            v["overlay_block_fields"] = "partial"
    else:
        # overlay is "unknown", None, or an unrecognized value — no sibling
        # column to resolve, so the block-fields check cannot be evaluated.
        v["overlay_block_fields"] = "partial"

    v["missing_kpis_json"] = (
        "pass" if isinstance(missing, list) and len(missing) >= 5 else "partial"
    )
    return count_pass(v), v


def score_qoe(d: dict) -> tuple[int, dict]:
    v = {}
    rev = jl(d.get("revenue_quality_flags_json"))
    scenarios = jl(d.get("ebitda_scenarios_json"))
    scope = jl(d.get("pre_qofe_scope_items_json"))
    qofe = d.get("qofe_report_present")
    ledger = jl(d.get("addback_ledger_json"))
    gaps = jl(d.get("data_room_gaps"))
    tier4 = d.get("tier4_addback_count")

    v["revenue_quality_flags"] = "pass" if isinstance(rev, list) and len(rev) >= 3 else "partial"
    v["ebitda_scenarios"] = "pass" if isinstance(scenarios, dict) and scenarios else "partial"
    v["pre_qofe_scope"] = "pass" if isinstance(scope, list) and len(scope) >= 5 else "partial"
    v["qofe_report_present"] = (
        "gap-correct" if str(qofe).lower() in ("false", "0") else "partial"
    )
    if isinstance(ledger, list) and ledger:
        v["tier_classification_fidelity"] = (
            "pass" if str(tier4) == str(len(ledger)) else "partial"
        )
    else:
        v["tier_classification_fidelity"] = "partial"
    v["data_room_gaps"] = "pass" if isinstance(gaps, list) else "partial"
    return count_pass(v), v


def score_fta(d: dict) -> tuple[float, dict]:
    """18-field rubric from scorecard_7_03 (pass=1, partial=0.5, miss=0)."""
    rev = jl(d.get("revenue_trend_json"))
    gm = jl(d.get("gross_margin_json"))
    ebitda = jl(d.get("ebitda_json"))
    wc = jl(d.get("working_capital_json"))
    opex = jl(d.get("opex_breakdown_json"))
    segments = jl(d.get("revenue_by_segment_json"))
    addbacks = jl(d.get("addback_schedule_json"))
    bva = jl(d.get("budget_vs_actual_json"))
    flags = jl(d.get("flags"))
    gaps = jl(d.get("data_room_gaps"))
    citations = jl(d.get("citations"))
    exec_sum = d.get("executive_summary")
    addback_pct = d.get("addback_pct_of_ebitda")

    v = {}

    rev_list = rev if isinstance(rev, list) else []
    v["1_revenue_trend"] = "pass" if len(rev_list) >= 8 else "partial" if rev_list else "miss"

    has_yoy = any(
        isinstance(r, dict) and (r.get("yoy_pct") is not None or r.get("growth_pct") is not None)
        for r in rev_list
    )
    v["2_revenue_cagr_yoy"] = "pass" if has_yoy or len(rev_list) >= 5 else "partial"

    gm_list = gm if isinstance(gm, list) else []
    v["3_gross_margin"] = "pass" if len(gm_list) >= 5 else "partial" if gm_list else "miss"

    ebitda_list = ebitda if isinstance(ebitda, list) else []
    reported = [e for e in ebitda_list if isinstance(e, dict) and e.get("ebitda_type") == "reported"]
    pf_adj = [e for e in ebitda_list if isinstance(e, dict) and "adjusted" in str(e.get("ebitda_type", "")).lower()]
    v["4_ebitda_reported"] = "pass" if len(reported) >= 3 or len(ebitda_list) >= 5 else "partial"
    v["5_ebitda_pf_margin"] = "pass" if pf_adj or len(ebitda_list) >= 5 else "partial"

    ab_list = addbacks if isinstance(addbacks, list) else []
    v["6_ebitda_bridge"] = "pass" if len(ab_list) >= 10 else "partial" if ab_list else "miss"
    v["7_addback_pct"] = "pass" if addback_pct is not None else "partial"

    wc_dict = wc if isinstance(wc, dict) else {}
    wc_null = all(wc_dict.get(k) is None for k in ("dso_days", "dpo_days", "ar_aging_note"))
    v["8_working_capital"] = "miss" if wc_null and wc_dict else "partial" if wc_null else "pass"

    opex_list = opex if isinstance(opex, list) else []
    v["9_opex_breakdown"] = "pass" if len(opex_list) >= 3 else "partial" if opex_list else "miss"

    seg_list = segments if isinstance(segments, list) else []
    v["10_revenue_by_segment"] = "pass" if len(seg_list) >= 10 else "partial" if seg_list else "miss"

    bva_list = bva if isinstance(bva, list) else []
    has_proj = len(rev_list) > 0 and any(
        isinstance(r, dict) and "2024" in str(r.get("period", "")) for r in rev_list
    )
    v["11_projected_financials"] = "partial" if has_proj and not bva_list else "pass" if has_proj else "miss"

    v["12_executive_summary"] = "pass" if exec_sum and len(str(exec_sum)) >= 200 else "partial"
    v["13_threshold_flags"] = "pass" if isinstance(flags, list) and len(flags) >= 1 else "miss"
    disc = [f for f in (flags or []) if isinstance(f, dict)]
    v["14_discrepancies"] = "pass" if len(disc) >= 2 else "partial"
    v["15_data_room_gaps"] = "pass" if isinstance(gaps, list) and len(gaps) >= 1 else "miss"

    rev_cited = rev_list and all(
        isinstance(r, dict) and r.get("source_doc") for r in rev_list[:3]
    )
    v["16_citation_revenue"] = "pass" if rev_cited else "partial"
    ebitda_cited = ebitda_list and all(
        isinstance(e, dict) and e.get("source_doc") for e in ebitda_list[:3]
    )
    v["17_citation_ebitda"] = "pass" if ebitda_cited else "partial"
    v["18_runtime"] = "pass"  # row exists post-successful e2e

    points = sum(
        1.0 if x == "pass" else 0.5 if x == "partial" else 0.0 for x in v.values()
    )
    return points, v


def score_legal(d: dict) -> tuple[int, dict]:
    contracts = jl(d.get("contract_register_json")) or []
    vendor = jl(d.get("vendor_register_json")) or []
    platform = jl(d.get("platform_dependency_register_json")) or []
    employment = jl(d.get("employment_register_json")) or []
    litigation = jl(d.get("litigation_register_json")) or []
    privacy = jl(d.get("privacy_security_register_json")) or []
    ip = jl(d.get("ip_register_json")) or []
    insurance = jl(d.get("insurance_register_json")) or []

    v = {}

    t4c_pass = any(
        isinstance(c, dict)
        and str(c.get("termination_for_convenience", {}).get("present", "")).lower() == "true"
        for c in contracts
    )
    v["t4c"] = "pass" if t4c_pass else "gap-correct"

    coc_pass = any(
        isinstance(c, dict)
        and str(c.get("change_of_control", {}).get("clause_present", "")).lower() == "true"
        for c in contracts
    )
    v["coc"] = "pass" if coc_pass else "gap-correct"

    restrictive_pass = any(
        isinstance(c, dict)
        and str(c.get("restrictive_covenants", {}).get("present", "")).lower() == "true"
        for c in contracts
    )
    v["restrictive"] = "pass" if restrictive_pass else "gap-correct"

    v["vendor"] = "pass" if len(vendor) >= 1 else "partial"
    v["platform"] = "gap-correct" if len(platform) == 0 else "pass"
    emp = [e for e in employment if isinstance(e, dict) and e.get("agreement_class") == "employee"]
    v["employment"] = "pass" if len(emp) >= 2 else "partial" if employment else "gap-correct"
    founder = [e for e in employment if isinstance(e, dict) and e.get("agreement_class") == "founder_key"]
    v["founder"] = "pass" if founder else "partial"
    v["litigation"] = "pass" if len(litigation) >= 1 else "gap-correct"
    v["privacy"] = "pass" if len(privacy) >= 5 else "partial"
    v["ip"] = "gap-correct" if len(ip) == 0 else "pass"
    v["insurance"] = "pass" if len(insurance) >= 3 else "partial"

    return count_pass(v), v


def score_profiler(d: dict) -> tuple[int, dict]:
    v = {}
    v["industry_overlay"] = (
        "pass" if d.get("industry_overlay") == "healthcare_services" else "partial"
    )
    v["revenue_model"] = "pass" if d.get("revenue_model") else "partial"
    v["business_description"] = "pass" if nonempty(d.get("business_description")) else "partial"
    v["deal_type"] = "pass" if d.get("deal_type") else "partial"
    v["banked"] = "pass" if str(d.get("banked")).lower() in ("true", "1") else "partial"
    v["vertical_subsector"] = "pass" if d.get("vertical_subsector") else "partial"
    gaps = jl(d.get("data_room_gaps"))
    v["data_room_gaps"] = "pass" if isinstance(gaps, list) else "partial"
    return count_pass(v), v


def report(
    name: str,
    ts: str,
    passes: float,
    total: int,
    verdicts: dict,
    slug: str,
) -> str:
    baseline = BASELINES[slug][name]
    score_str = f"{int(passes)}/{total}" if passes == int(passes) else f"{passes:.1f}/{total}"
    if baseline is None:
        status = "INFO"
        score_line = f"Score: {score_str} (no golden floor — informational only) -> {status}"
    else:
        bp, bt, gate = baseline
        if name == "fta":
            ok = passes >= 16
        else:
            ok = passes >= bp
        status = "PASS" if ok else "REGRESSION"
        score_line = f"Score: {score_str} (baseline {bp}/{bt}, gate {gate}) -> {status}"
    lines = [
        f"\n{'='*60}",
        f"{name.upper()} @ {ts}",
        score_line,
    ]
    for k, ver in verdicts.items():
        lines.append(f"  {k}: {ver}")
    return "\n".join(lines)


def main(company_name: str = "Elder Care") -> None:
    slug = company_slug(company_name)
    if slug not in BASELINES:
        raise SystemExit(f"Unknown company {company_name!r} (slug {slug!r})")

    e2e_ref = E2E_RUN if slug == "elder_care" else "n/a"
    print(f"Full G1 scoring — {company_name} e2e run {e2e_ref}")
    results: list[tuple[str, float, int, tuple[int, int, str] | None]] = []

    bma = fetch_analysis(
        "business_model",
        [
            "products_services_json", "people_and_org_json", "customer_profile_json",
            "sales_motion_tag", "sales_motion_json", "key_dependencies_json",
            "data_room_gaps", "overlay_conflict",
        ],
        company_name,
    )
    p, v = score_bma(bma)
    print(report("bma", bma.get("ts", "?"), p, 7, v, slug))
    results.append(("BMA", p, 7, BASELINES[slug]["bma"]))

    cqa = fetch_analysis(
        "customer_quality",
        [
            "top_customers_json", "retention_json", "customer_tenure_json",
            "payor_mix_json", "discrepancies_json", "data_room_gaps",
        ],
        company_name,
    )
    p, v = score_cqa(cqa)
    print(report("cqa", cqa.get("ts", "?"), p, 6, v, slug))
    results.append(("CQA", p, 6, BASELINES[slug]["cqa"]))

    kpi = fetch_analysis(
        "kpi",
        [
            "overlay_confirmed", "missing_kpis_json", "healthcare_kpis_json",
            "tech_services_kpis_json", "saas_kpis_json", "industrial_kpis_json",
            "consumer_kpis_json",
        ],
        company_name,
    )
    p, v = score_kpi(kpi)
    print(report("kpi", kpi.get("ts", "?"), p, 3, v, slug))
    results.append(("KPI", p, 3, BASELINES[slug]["kpi"]))

    qoe = fetch_analysis(
        "quality_of_earnings",
        [
            "revenue_quality_flags_json", "ebitda_scenarios_json",
            "pre_qofe_scope_items_json", "qofe_report_present",
            "addback_ledger_json", "data_room_gaps", "tier4_addback_count",
        ],
        company_name,
    )
    p, v = score_qoe(qoe)
    print(report("qoe", qoe.get("ts", "?"), p, 6, v, slug))
    results.append(("QoE", p, 6, BASELINES[slug]["qoe"]))

    fta = fetch_analysis(
        "financial_trends",
        [
            "revenue_trend_json", "gross_margin_json", "ebitda_json",
            "working_capital_json", "opex_breakdown_json", "revenue_by_segment_json",
            "addback_schedule_json", "budget_vs_actual_json", "flags",
            "data_room_gaps", "citations", "executive_summary", "addback_pct_of_ebitda",
        ],
        company_name,
    )
    pts, v = score_fta(fta)
    print(report("fta", fta.get("ts", "?"), pts, 18, v, slug))
    results.append(("FTA", pts, 18, BASELINES[slug]["fta"]))

    legal = fetch_analysis(
        "legal",
        [
            "contract_register_json", "vendor_register_json",
            "platform_dependency_register_json", "employment_register_json",
            "litigation_register_json", "privacy_security_register_json",
            "ip_register_json", "insurance_register_json",
        ],
        company_name,
    )
    p, v = score_legal(legal)
    print(report("legal", legal.get("ts", "?"), p, 11, v, slug))
    results.append(("Legal", p, 11, BASELINES[slug]["legal"]))

    prof = fetch_profiler(company_name)
    p, v = score_profiler(prof)
    print(report("profiler", prof.get("ts", "?"), p, 7, v, slug))
    results.append(("Profiler", p, 7, BASELINES[slug]["profiler"]))

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'Agent':<10} {'Fresh':>8} {'Baseline':>10} {'Gate':>6}")
    all_ok = True
    gated = False
    for name, score, total, baseline in results:
        if name == "FTA":
            s = f"{score:.1f}/{total}"
        else:
            s = f"{int(score)}/{total}"
        if baseline is None:
            print(f"{name:<10} {s:>8} {'—':>10} {'INFO':>6}")
            continue
        gated = True
        bp, _, _ = baseline
        ok = score >= bp
        gate = "PASS" if ok else "FAIL"
        if not ok:
            all_ok = False
        print(f"{name:<10} {s:>8} {bp}/{total:<6} {gate:>6}")
    if not gated:
        print(f"\nOverall G1: INFORMATIONAL (no golden floor for {company_name})")
    else:
        print(f"\nOverall G1: {'ALL PASS' if all_ok else 'REGRESSION(S) DETECTED'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Full G1 golden-checklist scoring")
    parser.add_argument(
        "--company",
        default="Elder Care",
        help='Company name (default: "Elder Care")',
    )
    args = parser.parse_args()
    main(args.company)
