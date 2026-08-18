# Clearsulting ex-bloat retrieval sanity — `baseline_7174e0399e29`

**Plan:** eval-multi-company-coverage-expansion · **T7 report (1)**  
**Generated:** 2026-08-18 (read-only warehouse SQL; no cluster runs)

## Question

Which Clearsulting retrieval intents are **meaningful to interpret** once the 12 `filename_closure` debt-cohort intents are excluded?

## Evidence refs

| Ref | Role |
|-----|------|
| `run_id:baseline_7174e0399e29` | Harness baseline (`uc13_ale.ops.retrieval_harness_results`) |
| `eval/program/eval_debt/eval_debt.yaml` | 12 `clearsulting:global:bloated_fc_*` debt rows |
| `eval/retrieval/gold_labels/clearsulting.yaml` | Gold corpus (57 labels; bloated rows use `gold_method: filename_closure`) |
| `eval/eval_program_playbook.md` §2.1 | Clearsulting pilot framing |

## Debt-cohort exclusion set (12 intents)

Sourced from `eval_debt.yaml` `kind` → intent_id mapping:

| intent_id | debt id |
|-----------|---------|
| `cqa.retrieve_customer_tenure` | `clearsulting:global:bloated_fc_cqa_retrieve_customer_tenure` |
| `cqa.retrieve_revenue_type_and_renewals` | `clearsulting:global:bloated_fc_cqa_retrieve_revenue_type_and_renewals` |
| `fta.ebitda.q1_financial_statements` | `clearsulting:global:bloated_fc_fta_ebitda_q1_financial_statements` |
| `fta.opex.q1_financial_statements` | `clearsulting:global:bloated_fc_fta_opex_q1_financial_statements` |
| `fta.revenue.q1_financial_statements` | `clearsulting:global:bloated_fc_fta_revenue_q1_financial_statements` |
| `kpi.retrieve_delivery_model` | `clearsulting:global:bloated_fc_kpi_retrieve_delivery_model` |
| `profiler.banked_vs_nonbanked` | `clearsulting:global:bloated_fc_profiler_banked_vs_nonbanked` |
| `profiler.business_description` | `clearsulting:global:bloated_fc_profiler_business_description` |
| `profiler.deal_type` | `clearsulting:global:bloated_fc_profiler_deal_type` |
| `profiler.industry_overlay` | `clearsulting:global:bloated_fc_profiler_industry_overlay` |
| `profiler.revenue_model` | `clearsulting:global:bloated_fc_profiler_revenue_model` |
| `profiler.vertical_subsector` | `clearsulting:global:bloated_fc_profiler_vertical_subsector` |

These 12 carry 1,000+ positive labels each via filename closure (T11 disposition) and are **not per-intent interpretable** until re-bootstrapped with `citation_backfill` or `aggregate_exclude`.

## Ex-bloat rollup

| Metric | All 57 intents | Ex-bloat (45 intents) | Debt cohort (12) |
|--------|----------------|----------------------|------------------|
| Harness rows | 57 | 45 | 12 |
| `eval_status=evaluated` | 48 | 36 | 12 |
| `eval_status=skipped_bootstrap_failed` | 9 | 9 | 0 |
| Mean `recall@10` (evaluated only) | 0.039 | **0.050** | ~0.007 (dominated by bloated positives) |
| Zero-recall evaluated intents | 24 | **22** | — |
| `recall@10 ≥ 0.25` | 1 | **2** | — |

**Headline:** Ex-bloat Clearsulting retrieval is **thin but not uniformly zero** — two KPI intents show signal; most FTA/BMA/CQA intents remain near-zero on a 2,417-chunk corpus.

## Per-intent ex-bloat table (evaluated intents only)

Sorted by `recall@10` descending. Skipped intents listed separately.

### Meaningful signal (recall@10 > 0)

| intent_id | recall@10 | mrr | Notes |
|-----------|-----------|-----|-------|
| `kpi.retrieve_bill_rates_and_margins` | **0.875** | 1.0 | Strongest ex-bloat intent; consulting KPI workbook grounding |
| `fta.ebitda.q2_ebitda_and_margins` | **0.273** | 0.5 | Partial FTA EBITDA recall without bloated q1 intent |
| `kpi.retrieve_headcount_attrition` | **0.200** | 1.0 | Moderate headcount signal |
| `fta.ebitda.q4_addback_schedule` | 0.091 | 0.2 | Low but non-zero |
| `fta.opex.q3_projected_financials` | 0.091 | 0.17 | Low but non-zero |
| `bma.retrieve_pricing_and_margins` | 0.070 | 1.0 | Sparse BMA signal |
| `qoe.retrieve_revenue_quality` | 0.050 | 1.0 | Sparse QoE signal |
| `bma.retrieve_business_overview` | 0.040 | 0.5 | Sparse |
| `bma.retrieve_people_and_org` | 0.040 | 1.0 | Sparse |
| `bma.retrieve_workforce_and_capacity` | 0.030 | 0.5 | Sparse |
| `bma.retrieve_model_changes_and_dependencies` | 0.020 | 0.2 | Sparse |
| `cqa.retrieve_customer_health` | 0.016 | 1.0 | Sparse |
| `qoe.retrieve_qofe_report` | 0.013 | 0.5 | Sparse |
| `cqa.retrieve_payor_mix` | 0.005 | 1.0 | Sparse |

### Zero recall (evaluated, ex-bloat)

22 intents at `recall@10 = 0.0`, including all remaining FTA revenue/opex/ebitda working-capital paths, all BMA detect/revenue-location intents, CQA account/cohort/retention, and most KPI dashboard/pipeline intents. These are **honest near-misses** on a thin corpus — not filename-closure artifacts.

### Skipped (bootstrap failed; ex-bloat)

9 intents never evaluated because gold bootstrap failed (no honest positives):  
`cqa.retrieve_contract_terms`, `cqa.retrieve_customer_concentration`, `kpi.retrieve_healthcare_labor_market`, all five `legal.*` intents, `profiler.company_size_indicators`.

Aligns with playbook note: **0 LEGAL-classified docs** → legal intents correctly skipped.

## Interpretation

1. **Do not read aggregate baseline recall** across all 57 intents — 12 debt rows dominate denominator noise.
2. **Promotion readiness** still blocked on `clearsulting:global:promotion_inputs` eval debt; ex-bloat sanity shows retrieval is usable for KPI billing/headcount and partial FTA EBITDA, not platform-wide.
3. **Next operator action:** Re-bootstrap the 12 bloated intents (T11 `closes_when`) before using q1 financial-statement or profiler intents in regression compare.
