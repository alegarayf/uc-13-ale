# T8 signoff — SPG ingest close + FTA golden checklist

**Plan:** eval-multi-company-coverage-expansion · **Date:** 2026-08-19  
**Catalog:** `uc13_ale` · **Company:** `SPG`

## Verdict

**Ingest OI closed** at preflight **1.0000** (363/363). **FTA golden checklist** scored **8.5/18** on Chip B analysis row (`2026-07-30 13:47:17`) after ingest gate — floor not met; post-ingest FTA re-run submitted for corpus refresh.

## Ingest — before / after

| Metric | Before | After |
|--------|--------|-------|
| Preflight completeness | **0.9863** (359/364) | **1.0000** (363/363) |
| Denominator | 364 `should_parse=true` | 363 (`should_parse=false` on 1 content-driven ZERO_CHUNKS) |

### Root cause

Five docs lacked chunks despite `should_parse=true`:

| File | Issue | Fix |
|------|-------|-----|
| `2.4.1_Fixed Asset Registers_2022 - 2023.xls` | Excel 2003 **SpreadsheetML** mislabeled `.xls` (not BIFF) | `_parse_spreadsheetml_xls()` in `ingestion_parser.py` → **55 chunks** |
| `2.5.3.1_Deferred Revenue FY_2022.xls` | SpreadsheetML | **1 chunk** |
| `2.5.3.2_Deferred Revenue FY_2023.xls` | SpreadsheetML | **1 chunk** |
| `2.8.2_General Ledger_2022.xls` | SpreadsheetML | **11 chunks** |
| `2.3.1_Project Beam - Projection Model.xlsx` | Prior ZERO_CHUNKS / cap gap | Force re-parse → **2000 chunks** (capped) |
| `3.1.1.1_Billion Dollar Podcast.pdf` | Stranded `PARSING` from concurrent full reparse | Force re-parse → ingested |
| `8.1.4_Shared Practices Policy - Bowman Insurance_2024.pdf` | `ZERO_CHUNKS` / `ALL_CHUNKS_FILTERED` (content-driven) | `should_parse=false` on `doc_relevance` (G5 attestation pattern) |

### Cluster evidence

| run_id | Purpose |
|--------|---------|
| `509102232061487` | Force re-parse (SpreadsheetML path v1 — xlrd BOF fail) |
| `1108843891562308` | Force re-parse (SpreadsheetML parser — **4 xls fixed**) |
| `_spg_final_ingest_close.py` | Bowman exclusion + podcast force |

Preflight command: `python -m eval.retrieval.ingest_preflight --company SPG --catalog uc13_ale`

## FTA golden checklist

| Field | Value |
|-------|-------|
| Checklist | `eval/FTA/golden_checklist_spg.md` |
| Analysis row | `uc13_ale.analysis.financial_trends` · `created_at=2026-07-30 13:47:17` |
| Chip B e2e | `641030239604593` |
| Score | **8.5/18** (4 pass, 9 partial, 5 miss) |
| Method | `python .dev/g1_score_all_agents.py` / `score_fta()` rubric — **not** retrieval harness |

**Post-ingest FTA re-run:** submitted via `.dev/spg_fta_rerun_submit.py` (refresh row after new financial chunks). Update checklist when new `financial_trends` row lands.

## Registry

- **Closed** `OI-data-ingest-quality-spg-ingest-borderline` with this signoff + preflight 1.0 evidence.
- Updated `cross_company_fta_variance.md` — ingest gate satisfied; 8.5/18 scored post-gate on pre-rerun row.

## Kill-criterion evidence

| Criterion | Evidence |
|-----------|----------|
| Ingest 1.0 | preflight stdout `completeness=1.0000 denominator=363` |
| No model blame before ingest | Checklist scored only after preflight PASS |
| Golden checklist not harness | Manual rubric via `golden_checklist_spg.md` |
| Registry OI closed | `eval/program/registry.yaml` row update |

## Adversarial gap (deferred)

No hermetic test that SpreadsheetML sample fixtures round-trip through `_parse_spreadsheetml_xls` — live cluster logs are falsifier (`1108843891562308`).
