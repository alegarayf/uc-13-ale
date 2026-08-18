# exec_summary re-calibration prep — dual-source evidence prototype

**Plan:** eval-multi-company-coverage-expansion · **T7 report (3)**  
**Generated:** 2026-08-18 (design note only — **no production code executed**)

## Question

Would adding `analysis.*` dual-source evidence lookup to the calibration fetch path **plausibly lift judge verdict agreement toward the 0.80 rung threshold** for `exec_summary`?

## Evidence refs

| Ref | Role |
|-----|------|
| `eval/content/spot-check/exec_summary_elder_care_2026-08-12.failure_modes.md` §0 | Dominant `retrieval_scope_gap` root cause |
| `eval/program/registry.yaml` (CHK-26a calibration row) | Baseline `verdict_agreement 0.393 < 0.80` on N=28 sample |
| `eval/content/calibration_samples/calibration_sample_exec_summary.yaml` | N=28 calibration claims |
| `eval/content/spot_check.py` | `load_exec_analysis_cache`, `exec_claim_source` (T3 generalized) |
| `eval/content/calibration.py` | Current `retrieve_evidence` → vector index only |
| `eval/program/product_backlog.yaml` | `PB-exec_summary-retrieval-scope-gap` |

## Current state (two paths diverge)

### Spot-check prepare (partial fix landed — T3)

`prepare_spot_check` / `load_claim_enumeration` already:

1. Calls `load_exec_analysis_cache()` — pulls latest rows from `financial_trends`, `quality_of_earnings`, `kpi`, `business_model`, `diligence_report`, `forecast`.
2. Calls `exec_claim_source(claim_id, cache, company_slug=…)` — maps claim → `(source_doc, source_location)`.
3. Resolves **VDR chunks** via `ChunkIndex.lookup` for presentation packets.

This fixes **citation targeting** in the operator packet but does not inject analysis-table values into evidence shown to a judge.

### Calibration / judge path (still chunk-RAG-only)

`calibration.run_calibration` → per claim:

```python
evidence = retrieve_evidence(w, catalog, company, claim_text=...)
```

`retrieve_evidence` queries `uc13_ale.ingestion.embeddings_index` only (top-k chunk excerpts, **1,200-char truncation**). No `analysis.*` join.

Registry records the outcome: **`verdict_agreement 0.393 < 0.80`** ⇒ `exec_summary` remains on **human** rung.

## Prototype design (calibration sample only)

**Scope flag:** `calibration-sample-only` — prototype for `calibration.py` evidence assembly; **not** a production spot-check or trust-statement change in this subtask.

### Proposed fetch path change

Add `build_exec_dual_source_evidence(claim_id, *, cache, chunk_index, sql_executor, catalog, company)`:

| Step | Source | Output |
|------|--------|--------|
| 1 | `exec_claim_source(claim_id, cache, company_slug)` | Canonical `(source_doc, source_location)` |
| 2a | **Analysis table lookup** | JSON scalar / array slice containing the claim value (e.g. `revenue_trend_json` row, `top_10_issues_json[rank]`, `section_ratings_json[key]`) serialized as an `evidence` record with `source_type: analysis_table` |
| 2b | **Chunk RAG fallback** | Existing `retrieve_evidence(claim_text)` for claims with VDR-only grounding |
| 3 | Merge | Pass **both** records to `judge_claim` as `evidence_json` array; judge prompt addendum: prefer analysis-table record when present |

Reuse existing cache keys from `load_exec_analysis_cache` — no new warehouse tables.

### Claims likely to benefit (from failure_modes §0)

| Category | claim_ids (examples) | analysis source |
|----------|---------------------|-----------------|
| Financial aggregates | 007–013, 031, 034 | `financial_trends.revenue_trend_json`, QoE ledger |
| Ratings / confidence | 019, 025, 046, 047 | `diligence_report.section_ratings_json`, `section_confidence_json` |
| Open items | 021–022, 035–036, 038–045, 048–053 | `diligence_report.top_10_issues_json` |
| KPI / ops | 003–004 | `kpi.healthcare_kpis_json`, `business_model.customer_operational_metrics_json` |

failure_modes §0: **28 of 30** drafted-`unsupported` spot-check claims confirmed via `analysis.*` SQL. Calibration sample N=28 overlaps heavily with this set.

### Plausibility vs 0.80 threshold

| Scenario | Estimated verdict agreement | Basis |
|----------|----------------------------|-------|
| **Current (chunk-only)** | **0.393** | Registry CHK-26a measured outcome |
| **Dual-source (optimistic)** | **≥ 0.80** | If ~22–25/28 calibration claims match operator verdict when judge sees analysis-table evidence instead of wrong-grain chunks |
| **Dual-source (conservative)** | **0.65–0.75** | Excludes chunk_truncation claims (008–010, 018), mandatory probes (027–028), and claim.026 contradicted rollup |

**Assessment:** Dual-source lookup is **plausible** to exceed 0.80 on the **existing N=28 calibration sample**, because the dominant failure mode is wrong evidence store, not judge incapability. Conservative estimate may still fall short of 0.80 if truncation and rollup-count claims remain chunk-bound.

**Not claimed:** Production spot-check agreement, full 53-claim surface, or automatic rung promotion — requires executed re-calibration with operator review.

## Secondary fixes (same backlog, lower lift)

| Issue | claim scope | Fix |
|-------|-------------|-----|
| `source_ref` mislabel | all 53 | Point at `diligence_report.executive_summary` (`PB-exec_summary-source-ref-mislabel`) |
| 1,200-char truncation | 008–010, 018 | Extend evidence excerpt limit (`PB-exec_summary-chunk-truncation`) |

These are orthogonal to dual-source but required for full-surface spot-check, not just calibration sample.

## Recommended next step (operator, out of scope for T7)

1. Implement dual-source helper in `calibration.py` (future subtask — not T7).
2. Re-run: `python -m eval.content.calibration --surface exec_summary --sample eval/content/calibration_samples/calibration_sample_exec_summary.yaml`
3. Compare `verdict_agreement` to 0.80 gate; record in registry CHK-26a row.

**Do not execute in this subtask** — T7 is read-only analysis per packet kill criteria.
