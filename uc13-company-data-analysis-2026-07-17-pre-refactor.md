# UC-13 multi-company data analysis dump

**Generated:** 2026-07-17 (warehouse probe + E2E readiness refresh)
**Catalog (primary):** `uc13_ale`
**Also inspected:** `uc13` (prod) — thinner / schema-drifted; VS index exists on `uc13` only
**Interactive canvas (repo root):** `uc13-company-data-analysis.canvas.tsx`
**Raw SQL dumps:** `.dev/tmp_deep_data_analysis.json`, `.dev/tmp_e2e_readiness_probe.json`
**Regen script:** `.dev/tmp_regen_company_analysis.py`

Exploration context and quantitative analyses: docs scan → completeness probe → deep suite (uploads, classification, chunks/embeddings, agents, retrieval) → **E2E readiness follow-up** (volume artifacts, T2 baseline, VS index gap).

---

## 1. Context map (docs + program state)

### 1.1 What UC-13 is

PE diligence pipeline on Databricks: SharePoint data room → upload → LLM classify → parse/chunk/embed → vector index → seven workstream agents → orchestrator bundle → executive summary / one-pager.

SharePoint companies (connector): **Clearsulting, Elder Care, GKF, SPG**.

### 1.2 Doc clusters that matter

| Track | Key artifacts | Status as of probe |
|-------|---------------|--------------------|
| Wed stakeholder sprint (exec summary × 4) | `.dev/specs/uc13-exec-summary-wed-sprint-spec.md`, plan, rationale | Deadline 2026-07-22; baseline = all 4 on compressed pipeline |
| Full notebook e2e | `.dev/attestations/TEMPLATE_m-phv2-full-e2e-run.md` | Cells 0→18 = seven analysis tables; orchestrator beyond that scope |
| Hardening closeout | `my_runbook.md`, PHV3/4 audits | Integration + PHV4 largely closed; formal Phase 3 audit file still open |
| Data-room completeness | Runbook Phase 7 | Still design-only — no scored checklist yet |
| Eval baselines | `eval/retrieval/README.md`, harness ops tables | Strong for Elder Care only (`baseline_1aeb0ace584a`) |

### 1.3 Catalog convention

| Catalog | Role | Companies present at probe |
|---------|------|----------------------------|
| `uc13_ale` | Dev/eval working set | Clearsulting, Elder Care, GKF, SPG — **all four pipeline-complete** |
| `uc13` | Prod script default | Clearsulting, Elder Care only; has `legal_contracts` not `analysis.legal`; no `ops` schema |

Do not mix catalogs when comparing completeness.

### 1.4 Operator T2 baseline log (exec-summary sprint)

Commit pin in log: `81f29ba88a345b8fcee021e3caae7dde5ec561a3` · status: `complete` · verdict: `PASS` · catalog: `uc13_ale`

| Company | ok | mode | words | notes |
|---------|----|------|-------|-------|
| Clearsulting | True | render_only | 847 | PASS (exit 0) |
| Elder Care | True | render_only | 1325 | PASS (exit 0; word_count soft WARN >1200) |
| GKF | True | agents_render | 1070 | PASS (exit 0) |
| SPG | True | agents_render (salvage after full run timed out post-ingestion) | 931 | PASS (exit 0) |

**T2 gate (Wed unconditional fallback): MET** — all four companies render `tldr_one_pager.md`/`.docx` with H1 **Executive Summary** on `uc13_ale` compressed pipeline.

**SPG note:** Full ingestion landed 71,010 chunks/embeddings; agents+render completed via salvage run after prior timeout on missing `uc13_ale.ingestion.embeddings_index` sync.

---

## 2. Analysis A — Pipeline completeness matrix

| Company | Upload | should_parse | Chunks | Profile | BMA | FTA | CQA | KPI | Legal | QoE |
|---------|--------|--------------|--------|---------|-----|-----|-----|-----|-------|-----|
| Clearsulting | 28 | 22 | 2.2k | yes | yes | yes | yes | yes | yes | yes |
| Elder Care | 1386 | 379 | 35.1k | yes | yes | yes | yes | yes | yes | yes |
| GKF | 42 | 40 | 3.0k | yes | yes | yes | yes | yes | yes | yes |
| SPG | 511 | 364 | 71.0k | yes | yes | yes | yes | yes | yes | yes |

### Join integrity (should_parse → chunks)

| Company | should_parse | Present | Missing | % ingested |
|---------|--------------|---------|---------|------------|
| Clearsulting | 22 | 21 | 1 | 95.5% |
| Elder Care | 379 | 197 | 182 | 52.0% |
| GKF | 40 | 40 | 0 | 100.0% |
| SPG | 364 | 323 | 41 | 88.7% |

Elder Care at **52%** means nearly half of classifier-approved files are not in the chunk table — coverage gap even on the gold company (112 FINANCIAL, 38 LEGAL missing). GKF is fully ingested. SPG is **88.7%** ingested (41 files missing, LEGAL-heavy gaps).

---

## 3. Analysis B — Upload corpus (formats, size, folders)

| Company | Files | Distinct | MB | Folders |
|---------|-------|----------|----|---------|
| Clearsulting | 28 | 28 | 37.2 | 9 |
| Elder Care | 1386 | 1223 | 1822.8 | 160 |
| GKF | 42 | 41 | 22.6 | 18 |
| SPG | 511 | 511 | 866.6 | 62 |

### Formats (upload_log)

**Clearsulting:**
- `xlsx`: 17 files (19.5M bytes)
- `pdf`: 10 files (19.4M bytes)
- `docx`: 1 files (125.8k bytes)

**Elder Care:**
- `pdf`: 1099 files (1029.4M bytes)
- `xlsx`: 208 files (864.6M bytes)
- `docx`: 76 files (16.9M bytes)
- `other`: 3 files (409.4k bytes)

**GKF:**
- `xlsx`: 34 files (11.3M bytes)
- `pdf`: 8 files (12.3M bytes)

**SPG:**
- `pdf`: 411 files (786.6M bytes)
- `xlsx`: 100 files (122.1M bytes)

### Top folders (truncated path, top 8)

| Company | Folder | Files |
|---------|--------|-------|
| Clearsulting | `Financial - Accounting` | 12 |
| Clearsulting | `Human Resources` | 4 |
| Clearsulting | `Operations` | 3 |
| Clearsulting | `Sales - Marketing` | 3 |
| Clearsulting | `Corporate - Organizational` | 2 |
| Clearsulting | `Transaction Documents/QoE Access Letter` | 1 |
| Clearsulting | `Transaction Documents/Confidential Information Memorandum` | 1 |
| Clearsulting | `Transaction Documents/Process Letter` | 1 |
| Elder Care | `01. Financial/01d. Bank Statements` | 393 |
| Elder Care | `05. M&A/Unicity` | 269 |
| Elder Care | `01. Financial/01h. Payroll` | 123 |
| Elder Care | `02. Employee Matters/02g. Onboarding` | 121 |
| Elder Care | `05. M&A/Guided Living` | 110 |
| Elder Care | `02. Employee Matters/02f. Benefits` | 77 |
| Elder Care | `02. Employee Matters/02e. Personnel Contracts` | 49 |
| Elder Care | `01. Financial/01e. Billing Data` | 24 |
| GKF | `Financial/Trial Balance Sheet By Location` | 15 |
| GKF | `Financial/Balance Sheets by Location` | 5 |
| GKF | `Financial/Income Statements by Location` | 5 |
| GKF | `Franchise documents` | 4 |
| GKF | `Process, Teaser, and CIM` | 3 |
| GKF | `.` | 2 |
| GKF | `Development Costs` | 1 |
| GKF | `Databook` | 1 |
| SPG | `1_Genera_mation/1.1_Corpora_cuments` | 93 |
| SPG | `3_Tax/3.1_Federal and State Tax Returns` | 59 |
| SPG | `5_Regulatory/5.1_Provider Licenses` | 55 |
| SPG | `6_Property/6.1_Real Property (Leases)` | 44 |
| SPG | `7_Employee/7.5_Doctor Contracts - Employment Agreements` | 40 |
| SPG | `6_Property/6.2_Equipment Loans` | 31 |
| SPG | `2_Financial/2.6_Balance Sheet Items` | 30 |
| SPG | `2_Financial/2.8_General Ledger Reports` | 22 |

---

## 4. Analysis C — Classification (workstreams, confidence, priority)

### Should-parse rates

| Company | Docs | should_parse | % |
|---------|------|--------------|---|
| Clearsulting | 28 | 22 | 78.6% |
| Elder Care | 1386 | 398 | 28.7% |
| GKF | 42 | 41 | 97.6% |
| SPG | 511 | 389 | 76.1% |

### Extraction confidence

| Company | high | medium | low |
|---------|------|--------|-----|
| Clearsulting | 6 | 16 | 6 |
| Elder Care | 184 | 322 | 880 |
| GKF | 9 | 32 | 1 |
| SPG | 45 | 315 | 151 |

### Priority tier

| Company | null/None | tier 1 | tier 2 | tier 3 |
|---------|-----------|--------|--------|--------|
| Clearsulting | 6 | 6 | 12 | 4 |
| Elder Care | 987 | 27 | 179 | 193 |
| GKF | 1 | 6 | 19 | 16 |
| SPG | 117 | 33 | 184 | 177 |

### Workstream matrix (exploded tags)

| Company | Workstream | Docs | should_parse | high | med | low | avg tier |
|---------|------------|------|--------------|------|-----|-----|----------|
| Clearsulting | FINANCIAL | 12 | 12 | 4 | 8 | 0 | 1.67 |
| Clearsulting | BACKGROUND | 6 | 0 | 0 | 0 | 6 | 0 |
| Clearsulting | BUSINESS_MODEL | 5 | 5 | 1 | 4 | 0 | 1.8 |
| Clearsulting | KPI_OPS | 5 | 5 | 1 | 4 | 0 | 2.6 |
| Clearsulting | CUSTOMER | 2 | 2 | 0 | 2 | 0 | 2.0 |
| Clearsulting | FORECAST | 1 | 1 | 1 | 0 | 0 | 1.0 |
| Clearsulting | QUALITY_EARNINGS | 1 | 1 | 1 | 0 | 0 | 1.0 |
| Elder Care | BACKGROUND | 621 | 6 | 124 | 6 | 491 | 3.0 |
| Elder Care | FINANCIAL | 582 | 210 | 43 | 154 | 385 | 2.5 |
| Elder Care | LEGAL | 114 | 113 | 4 | 107 | 3 | 2.28 |
| Elder Care | KPI_OPS | 36 | 36 | 5 | 30 | 1 | 2.64 |
| Elder Care | BUSINESS_MODEL | 26 | 26 | 1 | 25 | 0 | 1.96 |
| Elder Care | CUSTOMER | 9 | 9 | 8 | 1 | 0 | 2.0 |
| Elder Care | QUALITY_EARNINGS | 8 | 8 | 8 | 0 | 0 | 2.0 |
| Elder Care | FORECAST | 3 | 3 | 3 | 0 | 0 | 1.0 |
| GKF | FINANCIAL | 33 | 33 | 5 | 28 | 0 | 2.27 |
| GKF | BUSINESS_MODEL | 5 | 5 | 4 | 1 | 0 | 1.6 |
| GKF | LEGAL | 4 | 4 | 1 | 3 | 0 | 2.5 |
| GKF | QUALITY_EARNINGS | 2 | 2 | 2 | 0 | 0 | 1.0 |
| GKF | BACKGROUND | 1 | 0 | 0 | 0 | 1 | 0 |
| GKF | CUSTOMER | 1 | 1 | 0 | 1 | 0 | 2.0 |
| GKF | KPI_OPS | 1 | 1 | 0 | 1 | 0 | 2.0 |
| GKF | FORECAST | 1 | 1 | 1 | 0 | 0 | 1.0 |
| SPG | LEGAL | 191 | 191 | 0 | 190 | 1 | 2.28 |
| SPG | FINANCIAL | 158 | 155 | 40 | 114 | 4 | 2.32 |
| SPG | BACKGROUND | 132 | 16 | 0 | 0 | 132 | 3.0 |
| SPG | KPI_OPS | 27 | 24 | 5 | 8 | 14 | 2.81 |
| SPG | QUALITY_EARNINGS | 16 | 16 | 7 | 6 | 3 | 1.56 |
| SPG | BUSINESS_MODEL | 3 | 3 | 0 | 3 | 0 | 2.67 |
| SPG | FORECAST | 1 | 1 | 1 | 0 | 0 | 1.0 |

**Standouts:**
- Clearsulting: **0 LEGAL** docs — explains empty legal registers / historical 0/11 checklist.
- SPG: LEGAL-heavy (191) even before parse completes.
- Elder Care: BACKGROUND 621 docs mostly low-conf / not should_parse; FINANCIAL is the bulk of parse load.

---

## 5. Analysis D — Chunk / embedding text volume

### Totals

| Company | Chunks | Files | Total chars | Avg | p50 | p95 | Words | Approx tokens (chars/4) |
|---------|--------|-------|-------------|-----|-----|-----|-------|-------------------------|
| Clearsulting | 2237 | 21 | 4.0M | 1795.5 | 294 | 7374 | 1.0M | 1.0M |
| Elder Care | 35104 | 218 | 179.2M | 5105.7 | 6637 | 7466 | 31.8M | 44.8M |
| GKF | 3038 | 40 | 11.8M | 3887.7 | 3704 | 7381 | 2.1M | 3.0M |

### By source_type

| Company | source_type | Chunks | Chars | Words |
|---------|-------------|--------|-------|-------|
| Clearsulting | vision | 1093 | 290.2k | 40.6k |
| Clearsulting | text | 1054 | 3.6M | 960.7k |
| Clearsulting | table | 90 | 121.0k | 27.2k |
| Elder Care | text | 32273 | 177.4M | 31.5M |
| Elder Care | table | 1490 | 1.4M | 267.0k |
| Elder Care | vision | 1341 | 514.3k | 85.7k |
| GKF | text | 2403 | 11.4M | 2.0M |
| GKF | table | 322 | 280.4k | 53.0k |
| GKF | vision | 313 | 110.1k | 17.0k |

### By file_type

| Company | file_type | Chunks | Files | Chars |
|---------|-----------|--------|-------|-------|
| Clearsulting | pdf | 1620 | 6 | 679.4k |
| Clearsulting | xlsx | 617 | 15 | 3.3M |
| Elder Care | xlsx | 30570 | 105 | 174.6M |
| Elder Care | pdf | 4278 | 97 | 3.9M |
| Elder Care | csv | 136 | 3 | 641.9k |
| Elder Care | docx | 120 | 13 | 115.5k |
| GKF | xlsx | 1801 | 33 | 10.1M |
| GKF | pdf | 1237 | 7 | 1.7M |

### Page / section coverage

| Company | Chunks | With page | Max page | Distinct sections |
|---------|--------|-----------|----------|-------------------|
| Clearsulting | 2237 | 1620 | 82 | 518 |
| Elder Care | 35104 | 4278 | 74 | 1515 |
| GKF | 3038 | 1237 | 484 | 628 |

### Embedded text by workstream (chunks join embeddings)

| Company | Workstream | Embeddings | Chars | Words | Avg chars |
|---------|------------|------------|-------|-------|-----------|
| Clearsulting | FINANCIAL | 590 | 2.4M | 559.1k | 4131.2 |
| Clearsulting | KPI_OPS | 179 | 1.1M | 402.0k | 6089.5 |
| Clearsulting | BUSINESS_MODEL | 1468 | 489.2k | 67.4k | 333.2 |
| Clearsulting | CUSTOMER | 62 | 264.1k | 32.6k | 4259.5 |
| Clearsulting | QUALITY_EARNINGS | 149 | 187.9k | 37.0k | 1261.2 |
| Clearsulting | FORECAST | 4 | 14.1k | 1.8k | 3534.5 |
| Elder Care | FINANCIAL | 23848 | 119.3M | 19.2M | 5002.8 |
| Elder Care | KPI_OPS | 8710 | 54.5M | 11.7M | 6253.6 |
| Elder Care | QUALITY_EARNINGS | 5472 | 30.1M | 4.7M | 5504.3 |
| Elder Care | FORECAST | 1341 | 6.4M | 792.8k | 4780.7 |
| Elder Care | BUSINESS_MODEL | 1198 | 3.2M | 548.9k | 2660.9 |
| Elder Care | LEGAL | 1350 | 2.0M | 320.4k | 1502.8 |
| Elder Care | CUSTOMER | 89 | 489.3k | 83.8k | 5497.7 |
| GKF | FINANCIAL | 1800 | 10.1M | 1.8M | 5629.3 |
| GKF | QUALITY_EARNINGS | 1184 | 7.8M | 1.5M | 6585.2 |
| GKF | LEGAL | 754 | 1.5M | 233.7k | 1927.9 |
| GKF | FORECAST | 230 | 1.0M | 115.9k | 4420.9 |
| GKF | BUSINESS_MODEL | 597 | 681.1k | 119.8k | 1140.9 |
| GKF | CUSTOMER | 1 | 2.7k | 544 | 2689.0 |
| GKF | KPI_OPS | 1 | 2.7k | 544 | 2689.0 |

### Embedding priority tiers

| Company | Tier | Embeddings | Files |
|---------|------|------------|-------|
| Clearsulting | 1 | 1151 | 6 |
| Clearsulting | 2 | 910 | 11 |
| Clearsulting | 3 | 176 | 4 |
| Elder Care | 1 | 3850 | 28 |
| Elder Care | 2 | 31254 | 190 |
| GKF | 1 | 1945 | 5 |
| GKF | 2 | 1043 | 19 |
| GKF | 3 | 50 | 16 |

**Read:** Elder Care is an order of magnitude larger than the others (~32M words). Most of that mass is Excel FINANCIAL/KPI_OPS text, not PDF prose. Clearsulting is vision-chunk-heavy by count but word mass is still text.

---

## 6. Analysis E — Company profiles

| Company | Overlay | Conf | Deal | Banked | Gaps | Desc chars |
|---------|---------|------|------|--------|------|------------|
| Clearsulting | healthcare_services | high | recapitalization | true | 1 | 434 |
| Elder Care | healthcare_services | high | buyout | true | 1 | 325 |
| GKF | healthcare_services | medium | unknown | true | 6 | 348 |

GKF profiler gap list is CIM-centric (6 gaps). Clearsulting/Elder Care each flag missing revenue-model documentation.

---

## 7. Analysis F — Agent output richness and confidence

### Business model (BMA)

| company_name | cim_detected | revenue_model_tag | revenue_durability_flag | flag_confidence | overlay_conflict | n_gaps | products_json_chars | citations_chars | created_at |
|---|---|---|---|---|---|---|---|---|---|
| Clearsulting | true | project_based | Red | medium | true | 6 | 4474 | 2 | 2026-07-07T19:39:09.146Z |
| Elder Care | true | repeat_services | Yellow | high | false | 7 | 2214 | 2 | 2026-07-14T13:43:07.810Z |
| GKF | false | repeat_services | Yellow | medium | false | 4 | 1529 | 3981 | 2026-07-17T14:56:59.999Z |

### Financial trends (FTA)

| company_name | industry_overlay_used | addback_pct_of_ebitda | n_gaps | exec_chars | rev_json_chars | ebitda_json_chars | addback_json_chars | created_at |
|---|---|---|---|---|---|---|---|---|
| Clearsulting | healthcare_services | 45.7 | 1 | 490 | 3351 | 1664 | 4520 | 2026-07-07T19:42:15.923Z |
| Elder Care | healthcare_services | 246.9 | 1 | 428 | 2718 | 3730 | 6139 | 2026-07-16T00:02:50.516Z |
| GKF | healthcare_services | None | 5 | 613 | 2147 | 2026 | 1498 | 2026-07-17T14:58:44.639Z |

### Legal

| company_name | section_confidence | n_gaps | exec_chars | contract_json_chars | employment_json_chars | litigation_json_chars | insurance_json_chars | unable_json_chars | citations_chars | created_at |
|---|---|---|---|---|---|---|---|---|---|---|
| Clearsulting | low | 11 | 264 | 2 | 2 | 2 | 2 | 423 | 2 | 2026-07-07T19:46:28.237Z |
| Elder Care | high | 5 | 221 | 3825 | 2916 | 510 | 2148 | 182 | 6942 | 2026-07-16T00:05:24.943Z |
| GKF | high | 5 | 239 | 1300 | 2 | 2 | 617 | 164 | 3165 | 2026-07-17T15:02:50.915Z |

### Customer quality (CQA)

| company_name | n_gaps | n_triggers | exec_chars | top_cust_chars | citations_chars | created_at |
|---|---|---|---|---|---|---|
| Clearsulting | 3 | 1 | 773 | 4102 | 5571 | 2026-07-07T19:44:42.770Z |
| Elder Care | 0 | 0 | 738 | 2 | 1668 | 2026-07-08T17:03:46.291Z |
| GKF | 1 | 0 | 774 | 2 | 1996 | 2026-07-17T14:59:52.254Z |

### KPI

| company_name | overlay_confirmed | n_gaps | exec_chars | healthcare_kpi_chars | missing_kpi_chars | citations_chars | created_at |
|---|---|---|---|---|---|---|---|
| Clearsulting | tech_services | 10 | 829 | 479 | 3761 | 3320 | 2026-07-07T19:46:00.148Z |
| Elder Care | healthcare_services | 9 | 719 | 2643 | 3593 | 4377 | 2026-07-08T17:05:37.000Z |
| GKF | healthcare_services | 9 | 827 | 1076 | 3865 | 5288 | 2026-07-17T15:01:17.588Z |

### Quality of earnings (QoE)

| company_name | qofe_report_present | total_addbacks_pct_of_ebitda | tier4_addback_count | n_gaps | exec_chars | ledger_chars | citations_chars | created_at |
|---|---|---|---|---|---|---|---|---|
| Clearsulting | true | 45.7 | 9 | 0 | 841 | 7381 | 4934 | 2026-07-07T19:48:32.907Z |
| Elder Care | false | 246.9 | 17 | 1 | 908 | 9787 | 3063 | 2026-07-08T17:10:16.460Z |
| GKF | true | None | 3 | 1 | 996 | 9616 | 6368 | 2026-07-17T15:05:37.753Z |

**Agent standouts:**
- Legal Clearsulting: `section_confidence=low`, 11 retrieval gaps, empty registers (`json_chars=2`).
- Legal Elder Care / GKF: `high` with populated contract/insurance JSON.
- BMA: LLM truncation gaps on all three completed companies; GKF `cim_detected=false`.
- FTA Elder Care: addbacks **246.9%** of EBITDA; GKF margins/addbacks not computed.
- KPI Clearsulting: `overlay_confirmed=tech_services` vs profiler `healthcare_services` — conflict.
- QoE: Clearsulting + GKF report present; Elder Care flagged no QofE in VDR.

---

## 8. Analysis G — Retrieval intents, harness, provenance

### Harness runs by company

| Company | Run type | Status | Runs | Last run | Avg intents | Fallback | Empty |
|---------|----------|--------|------|----------|-------------|----------|-------|
| Clearsulting | pipeline | complete | 6 | 2026-07-07 | 7.0 | 0 | 0 |
| Elder Care | pipeline | complete | 19 | 2026-07-16 | 9.8 | 0 | 0 |
| Elder Care | baseline | complete | 11 | 2026-07-15 | 49.0 | 0 | 0.063 |
| Elder Care | enhancement | complete | 2 | 2026-07-15 | 49.0 | 0 | 0.035 |
| Elder Care | ablation | complete | 4 | 2026-07-03 | 49.0 | 0 | 0.093 |
| GKF | pipeline | complete | 8 | 2026-07-17 | 7.5 | 1.0 | 0 |

### Provenance coverage

| Company | Runs | Distinct intents | Rows | Avg sim | Avg chars alloc |
|---------|------|------------------|------|---------|-----------------|
| Clearsulting | 5 | 16 | 305 | 0.527 | 1456.9 |
| Elder Care | 35 | 54 | 6581 | 0.573 | 1462.8 |
| GKF | 6 | 17 | 218 | 0.0 | 1106.3 |

### Provenance by source_type

| Company | source_type | Hits | Avg sim |
|---------|-------------|------|---------|
| Clearsulting | text | 196 | 0.502 |
| Clearsulting | vision | 56 | 0.557 |
| Clearsulting | table | 53 | 0.589 |
| Elder Care | text | 3366 | 0.539 |
| Elder Care | vision | 1747 | 0.618 |
| Elder Care | table | 1468 | 0.598 |
| GKF | text | 208 | 0.0 |
| GKF | table | 9 | 0.0 |
| GKF | vision | 1 | 0.0 |

### Elder Care baseline intent rollup (`baseline_1aeb0ace584a`)

Eval status dist: evaluated=43, skipped_bootstrap_failed=6. Gold-label intent scoring is **Elder Care only**.

| Agent | Intents | Avg recall@10 | Avg MRR | Avg results | Empty |
|-------|---------|---------------|---------|-------------|-------|
| bma | 9 | 0.01 | 1.0 | 11.8 | 0 |
| cqa | 5 | 0.0 | 0.0 | 1.6 | 3 |
| fta.ebitda | 4 | 0.051 | 0.083 | 7.0 | 0 |
| fta.opex | 3 | 0.192 | 0.5 | 6.7 | 0 |
| fta.revenue | 6 | 0.092 | 0.2 | 6.2 | 0 |
| kpi | 5 | 0.029 | 0.867 | 6.6 | 0 |
| legal | 5 | 0.129 | 0.6 | 8.2 | 0 |
| profiler | 7 | 0.006 | 0.857 | 4.3 | 1 |
| qoe | 5 | 0.002 | 1.0 | 6.0 | 1 |

### All 49 baseline intents (detail)

| Agent | Intent | Status | Recall@10 | MRR | Results | Mode |
|-------|--------|--------|-----------|-----|---------|------|
| bma | bma.detect_cim_presence | evaluated | 0.006 | 1.0 | 3 | semantic |
| bma | bma.retrieve_business_overview | evaluated | 0.0199 | 1.0 | 11 | semantic |
| bma | bma.retrieve_model_changes_and_dependencies | evaluated | 0.0183 | 1.0 | 18 | semantic |
| bma | bma.retrieve_people_and_org | evaluated | 0.0199 | 1.0 | 15 | semantic |
| bma | bma.retrieve_pricing_and_margins | evaluated | 0.0016 | 1.0 | 6 | semantic |
| bma | bma.retrieve_revenue_by_location_and_metrics | evaluated | 0.0026 | 1.0 | 15 | semantic |
| bma | bma.retrieve_revenue_visibility | evaluated | 0.0026 | 1.0 | 12 | semantic |
| bma | bma.retrieve_sales_and_customers | evaluated | 0.0183 | 1.0 | 11 | semantic |
| bma | bma.retrieve_workforce_and_capacity | evaluated | 0.0026 | 1.0 | 15 | semantic |
| cqa | cqa.retrieve_account_size | evaluated | 0.0 | 0.0 | 0 | empty |
| cqa | cqa.retrieve_customer_concentration | skipped_bootstrap_failed | None | None | 0 | None |
| cqa | cqa.retrieve_customer_tenure | evaluated | 0.0 | 0.0 | 0 | empty |
| cqa | cqa.retrieve_payor_mix | evaluated | 0.0 | 0.0 | 6 | semantic |
| cqa | cqa.retrieve_retention_metrics | skipped_bootstrap_failed | None | None | 2 | None |
| fta.ebitda | fta.ebitda.q1_financial_statements | skipped_bootstrap_failed | None | None | 10 | None |
| fta.ebitda | fta.ebitda.q2_ebitda_and_margins | evaluated | 0.1538 | 0.25 | 8 | semantic |
| fta.ebitda | fta.ebitda.q3_working_capital | evaluated | 0.0 | 0.0 | 4 | semantic |
| fta.ebitda | fta.ebitda.q4_addback_schedule | evaluated | 0.0 | 0.0 | 6 | semantic |
| fta.opex | fta.opex.q1_financial_statements | skipped_bootstrap_failed | None | None | 8 | None |
| fta.opex | fta.opex.q2_working_capital | evaluated | 0.0 | 0.0 | 4 | semantic |
| fta.opex | fta.opex.q3_projected_financials | evaluated | 0.3846 | 1.0 | 8 | semantic |
| fta.revenue | fta.revenue.q1_financial_statements | skipped_bootstrap_failed | None | None | 10 | None |
| fta.revenue | fta.revenue.q2_revenue_by_segment | evaluated | 0.0 | 0.0 | 5 | semantic |
| fta.revenue | fta.revenue.q3_revenue_by_geography | evaluated | 0.0 | 0.0 | 6 | semantic |
| fta.revenue | fta.revenue.q4_customer_concentration | evaluated | 0.0 | 0.0 | 2 | semantic |
| fta.revenue | fta.revenue.q4_customer_concentration_fallback | evaluated | 0.0 | 0.0 | 6 | semantic |
| fta.revenue | fta.revenue.q5_quickbooks_pl | evaluated | 0.4615 | 1.0 | 8 | semantic |
| kpi | kpi.retrieve_delivery_model | evaluated | 0.0018 | 1.0 | 1 | semantic |
| kpi | kpi.retrieve_headcount_attrition | evaluated | 0.0018 | 1.0 | 6 | semantic |
| kpi | kpi.retrieve_healthcare_ops | evaluated | 0.0003 | 1.0 | 8 | semantic |
| kpi | kpi.retrieve_kpi_dashboard | evaluated | 0.1395 | 0.333 | 10 | semantic |
| kpi | kpi.retrieve_pipeline_backlog | evaluated | 0.0024 | 1.0 | 8 | semantic |
| legal | legal.contracts_vendors_platform | evaluated | 0.0 | 0.0 | 14 | semantic |
| legal | legal.employment | evaluated | 0.0 | 0.0 | 6 | semantic |
| legal | legal.insurance | evaluated | 0.1176 | 1.0 | 6 | semantic |
| legal | legal.ip_privacy | evaluated | 0.4706 | 1.0 | 8 | semantic |
| legal | legal.litigation | evaluated | 0.0588 | 1.0 | 7 | semantic |
| profiler | profiler.banked_vs_nonbanked | evaluated | 0.002 | 1.0 | 5 | semantic |
| profiler | profiler.business_description | evaluated | 0.01 | 1.0 | 5 | semantic |
| profiler | profiler.company_size_indicators | evaluated | 0.0013 | 1.0 | 5 | semantic |
| profiler | profiler.deal_type | evaluated | 0.01 | 1.0 | 5 | semantic |
| profiler | profiler.industry_overlay | evaluated | 0.01 | 1.0 | 5 | semantic |
| profiler | profiler.revenue_model | evaluated | 0.0 | 0.0 | 0 | empty |
| profiler | profiler.vertical_subsector | evaluated | 0.01 | 1.0 | 5 | semantic |
| qoe | qoe.retrieve_ebitda_bridge | evaluated | 0.0031 | 1.0 | 10 | semantic |
| qoe | qoe.retrieve_owner_comp_support | evaluated | 0.0018 | 1.0 | 6 | semantic |
| qoe | qoe.retrieve_qofe_report | skipped_bootstrap_failed | None | None | 0 | None |
| qoe | qoe.retrieve_revenue_footnotes | evaluated | 0.0018 | 1.0 | 6 | semantic |
| qoe | qoe.retrieve_revenue_quality | evaluated | 0.0025 | 1.0 | 8 | semantic |

### Top retrieved files (provenance)

| Company | File | Hits | Avg sim |
|---------|------|------|---------|
| Clearsulting | `Project Infinity - Draft Financial Diligence Report - August 29, 2025_redacted.pdf` | 120 | 0.602 |
| Clearsulting | `Project Infinity  - Confidential Information Memorandum.pdf` | 66 | 0.574 |
| Clearsulting | `Project Infinity - Revenue by Client (2016-YTD May 2025).xlsx` | 35 | 0.408 |
| Clearsulting | `Project Infinity - Backlog - Pipeline with 2025 Revenue Waterfall (September 2025).xlsx` | 21 | 0.627 |
| Clearsulting | `Project Infinity - Go-to-Market Strategy Deep Dive.pdf` | 16 | 0.423 |
| Clearsulting | `Project Infinity - Utilization Analysis (Monthly Jan 2023 - May 2025).xlsx` | 12 | 0.237 |
| Clearsulting | `Project Infinity - Employee Attrition Analysis (9.30.2025).xlsx` | 11 | 0.232 |
| Clearsulting | `Project Infinity - Revenue by Project (2016 - YTD May 2025).xlsx` | 8 | 0.399 |
| Clearsulting | `Project Infinity - Revenue Masterfile (Monthly Jan 2020 - Aug 2025).xlsx` | 8 | 0.407 |
| Clearsulting | `Project Infinity - Revenue and Gross Margin Forecast by Practice (2025E - 2030F).xlsx` | 7 | 0.611 |
| Elder Care | `2024 Elder Care - CIM_vF.pdf` | 3822 | 0.609 |
| Elder Care | `Elder Care Projection Model Refresh_vF.xlsx` | 424 | 0.608 |
| Elder Care | `Elder Care Projection Model_vUPLOAD.xlsx` | 349 | 0.612 |
| Elder Care | `Manhattan_Lease_0424.pdf` | 252 | 0.391 |
| Elder Care | `Caregiver Demand Forecasting and KPI Dashboard SAMPLE.xlsx` | 232 | 0.599 |
| Elder Care | `ELDER CARE HOMECARE, INC._TAX RETURN _CLIENT COPY - V1_2020_Redacted.pdf` | 194 | 0.608 |
| Elder Care | `Eastern Bank Statements 2023.pdf` | 90 | 0.368 |
| Elder Care | `EC_0125-0325.xlsx` | 86 | 0.401 |
| Elder Care | `Guided Living - Asset Purchase Agreement - 02.07.24 - Execution Version with Exhibits, Lease, and BOS - signed (1).pdf` | 84 | 0.53 |
| Elder Care | `Elder Care NY COI.pdf` | 82 | 0.467 |
| GKF | `Project Ajax - Financial Due Diligence Databook - 12.22.25.xlsx` | 175 | 0.0 |
| GKF | `Goddard FDD 2025.pdf` | 28 | 0.0 |
| GKF | `Project Ajax IOI Process Letter_vE.pdf` | 6 | 0.0 |
| GKF | `Project Ajax Databook.xlsx` | 5 | 0.0 |
| GKF | `Project Ajax Teaser vF.pdf` | 4 | 0.0 |

**Retrieval standouts:**
- GKF pipeline harness `fallback_rate=1.0` and provenance `avg_sim=0` — semantic path not scoring; agents still wrote.
- No multi-company gold intent matrix yet (Clearsulting/GKF/SPG lack baseline-style scored intents).
- CQA empties on Elder Care baseline: `cqa.retrieve_account_size`, `cqa.retrieve_customer_tenure` mode=`empty`.

---

## 9. Analysis H — `uc13` prod catalog (secondary)

At probe time:
- Companies: Clearsulting, Elder Care only (no GKF/SPG).
- Schemas: ingestion, classification, analysis — **no `ops`**.
- Analysis tables include `legal_contracts`, `cross_analysis`, `diligence_report`, `forecast` — **no `analysis.legal`**.
- Elder Care chunks ~11k vs ~35k in `uc13_ale` — different ingestion depth.
- Join integrity: Clearsulting 100% present; Elder Care 228/479 (~47.6%) present.

Treat `uc13_ale` as the multi-company source of truth for this analysis dump.

---

## 10. E2E readiness matrix (follow-up probe)

Five-layer gate check per company. Probe: `.dev/tmp_e2e_readiness_probe.py`.

### Layer 1 — Ingestion

| Company | Chunks | Embeddings | C=E | Join % |
|---------|--------|------------|-----|--------|
| Clearsulting | 2,237 | 2,237 | ✅ | 95.5% |
| Elder Care | 35,104 | 35,104 | ✅ | 52.0% |
| GKF | 3,038 | 3,038 | ✅ | 100.0% |
| SPG | 71,010 | 71,010 | ✅ | 88.7% |

### Layer 2 — Vector index / retrieval

| Index | Status |
|-------|--------|
| `uc13_ale.ingestion.embeddings_index` | **MISSING** (ResourceDoesNotExist) |
| `uc13.ingestion.embeddings_index` | exists, ready, ~15,080 rows (stale vs ale Delta) |

| Company | Pipeline fallback | Provenance avg_sim |
|---------|-------------------|-------------------|
| Clearsulting | 0.0 | 0.527 |
| Elder Care | 0.0 | 0.573 |
| GKF | 1.0 | 0.0 |
| SPG | 1.0 | 0.0 |

**Root cause:** GKF and SPG agents ran on keyword fallback because no VS index serves `uc13_ale` embeddings. Run `setup_vector_search` / notebook Cell 2b for `catalog=uc13_ale`, confirm `✓ Index ready`, then re-run harness pipeline.

### Layer 3 — Agents

All four companies: profile + BMA + FTA + CQA + KPI + Legal + QoE = 1 row each ✅

### Layer 4 — Orchestrator volumes

| Company | bundle.yaml | tldr.md | tldr.docx | H1 |
|---------|-------------|---------|-----------|-----|
| Clearsulting | ✅ | ✅ | ✅ | # Clearsulting — Executive Summary |
| Elder Care | ✅ | ✅ | ✅ | # Elder Care — Executive Summary |
| GKF | ✅ | ✅ | ✅ | # GKF — Executive Summary |
| SPG | ✅ | ✅ | ✅ | # SPG — Executive Summary |

### Layer 5 — Wed sprint T2

| Phase | Status |
|-------|--------|
| T1 Rename → Executive Summary | ✅ templates + all 4 volumes |
| T2 Baseline all 4 | ✅ `PASS` — see §1.4 |
| T3–T7 Expanded synthesis | Not probed (feature branch) |

### Diligence readiness (pipeline ≠ diligence-ready)

| Company | LEGAL docs (classified) | Retrieval | Diligence-ready? |
|---------|-------------------------|-----------|------------------|
| Clearsulting | 0 | sim=0.527 | **No** (0 LEGAL tags; legal agent hollow) |
| Elder Care | 112 | sim=0.573 | Partial (gold baselines; 52% ingest) |
| GKF | 4 | sim=0.0 | Partial (keyword-only retrieval) |
| SPG | 181 | sim=0.0 | Partial (fresh agents, unvalidated retrieval) |

---

## 11. Synthesis — what this means for UC-13 e2e / Wed sprint

### Minimal DB path for agents e2e (M-PHV2 cells 0→18)
1. `upload_log` rows
2. `doc_relevance` with workstream coverage
3. chunks ≈ embeddings + index sync
4. `company_profile`
5. six analysis tables (BMA/FTA/CQA/KPI/Legal/QoE) > 0

**Done on ale:** Clearsulting, Elder Care, GKF, **SPG** (all four).

**Open infra gap:** create + sync `uc13_ale.ingestion.embeddings_index` before trusting semantic retrieval on GKF/SPG.

### Minimal path for Wed exec-summary e2e
Above **plus** bundle build → compress → `tldr_one_pager` titled Executive Summary.

### Data-pool size (Phase C ascending after Elder Care)
Clearsulting (~2.2k chunks) → GKF (~3.0k) → Elder Care (35k) → **SPG (~71k, largest)**.

### Completeness design gap (Phase 7 still open)
Pipeline-green ≠ diligence-ready. Clearsulting is the canonical example: all agents wrote, LEGAL doc count = 0, legal confidence low. Need a scored checklist over workstream presence + ingest % + agent gap counts — not just table row existence.

### Immediate follow-ups
- **P0:** Create/sync `uc13_ale.ingestion.embeddings_index`; re-run GKF + SPG harness pipeline
- Elder Care ingest gap — Cell 8c/8d on 182 missing should_parse files (112 FINANCIAL)
- Formal minimal completeness scorecard (runbook Phase 7)
- Multi-company harness baselines (currently Elder-only gold)
- Clearsulting: flag 0 LEGAL docs in stakeholder narrative

---

## 12. Method notes

- Warehouse: `rallyday_sql_warehouse` via `databricks-sdk` + repo-root `.env`.
- Words = `size(split(chunk_text, whitespace))` across all chunks.
- Tokens ≈ `sum(char_count)/4` (heuristic, not tokenizer).
- Workstream explosion uses `LATERAL VIEW explode(workstream)`.
- Join integrity joins `doc_relevance.filename` ↔ `chunks.file_name` for `should_parse=true`.
- Read-only; no DROP/TRUNCATE/rebuild.

Probe scripts: `.dev/tmp_deep_data_analysis.py`, `.dev/tmp_e2e_readiness_probe.py`, `.dev/tmp_regen_company_analysis.py`.

Companion interactive view: `uc13-company-data-analysis.canvas.tsx` (repo root).
