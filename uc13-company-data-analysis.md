# UC-13 multi-company data analysis dump

**Generated:** 2026-08-19 (warehouse probe + E2E readiness refresh)
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
| Clearsulting | 28 | 22 | 2.4k | yes | yes | yes | yes | yes | yes | yes |
| Elder Care | 1386 | 458 | 55.8k | yes | yes | yes | yes | yes | yes | yes |
| GKF | 42 | 40 | 3.1k | yes | yes | yes | yes | yes | yes | yes |
| SPG | 511 | 363 | 44.1k | yes | yes | yes | yes | yes | yes | yes |

### Join integrity (should_parse → chunks)

| Company | should_parse | Present | Missing | % ingested |
|---------|--------------|---------|---------|------------|
| Clearsulting | 22 | 22 | 0 | 100.0% |
| Elder Care | 458 | 450 | 8 | 98.3% |
| GKF | 40 | 40 | 0 | 100.0% |
| SPG | 363 | 363 | 0 | 100.0% |

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

_Folder query failed in first pass; see patched JSON if present._

---

## 4. Analysis C — Classification (workstreams, confidence, priority)

### Should-parse rates

| Company | Docs | should_parse | % |
|---------|------|--------------|---|
| Clearsulting | 28 | 22 | 78.6% |
| Elder Care | 1386 | 475 | 34.3% |
| GKF | 42 | 41 | 97.6% |
| SPG | 511 | 363 | 71.0% |

### Extraction confidence

| Company | high | medium | low |
|---------|------|--------|-----|
| Clearsulting | 6 | 16 | 6 |
| Elder Care | 184 | 341 | 861 |
| GKF | 9 | 32 | 1 |
| SPG | 48 | 299 | 164 |

### Priority tier

| Company | null/None | tier 1 | tier 2 | tier 3 |
|---------|-----------|--------|--------|--------|
| Clearsulting | 6 | 6 | 12 | 4 |
| Elder Care | 909 | 21 | 189 | 267 |
| GKF | 1 | 6 | 19 | 16 |
| SPG | 145 | 32 | 211 | 123 |

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
| Elder Care | BACKGROUND | 604 | 5 | 123 | 5 | 476 | 3.0 |
| Elder Care | FINANCIAL | 587 | 281 | 44 | 162 | 381 | 2.68 |
| Elder Care | LEGAL | 135 | 130 | 12 | 119 | 4 | 2.22 |
| Elder Care | KPI_OPS | 33 | 32 | 4 | 29 | 0 | 2.67 |
| Elder Care | BUSINESS_MODEL | 32 | 32 | 9 | 23 | 0 | 1.94 |
| Elder Care | QUALITY_EARNINGS | 14 | 14 | 2 | 12 | 0 | 1.86 |
| Elder Care | CUSTOMER | 12 | 12 | 0 | 12 | 0 | 2.33 |
| Elder Care | FORECAST | 2 | 2 | 1 | 1 | 0 | 1.5 |
| GKF | FINANCIAL | 33 | 33 | 5 | 28 | 0 | 2.27 |
| GKF | BUSINESS_MODEL | 5 | 5 | 4 | 1 | 0 | 1.6 |
| GKF | LEGAL | 4 | 4 | 1 | 3 | 0 | 2.5 |
| GKF | QUALITY_EARNINGS | 2 | 2 | 2 | 0 | 0 | 1.0 |
| GKF | BACKGROUND | 1 | 0 | 0 | 0 | 1 | 0 |
| GKF | CUSTOMER | 1 | 1 | 0 | 1 | 0 | 2.0 |
| GKF | KPI_OPS | 1 | 1 | 0 | 1 | 0 | 2.0 |
| GKF | FORECAST | 1 | 1 | 1 | 0 | 0 | 1.0 |
| SPG | LEGAL | 181 | 181 | 1 | 180 | 0 | 2.13 |
| SPG | FINANCIAL | 158 | 155 | 40 | 95 | 23 | 2.33 |
| SPG | BACKGROUND | 149 | 4 | 3 | 5 | 141 | 3.0 |
| SPG | KPI_OPS | 19 | 19 | 2 | 17 | 0 | 2.47 |
| SPG | QUALITY_EARNINGS | 16 | 16 | 7 | 6 | 3 | 1.56 |
| SPG | BUSINESS_MODEL | 3 | 3 | 2 | 1 | 0 | 2.0 |
| SPG | FORECAST | 1 | 1 | 1 | 0 | 0 | 1.0 |
| SPG | CUSTOMER | 1 | 1 | 0 | 1 | 0 | 3.0 |

**Standouts:**
- Clearsulting: **0 LEGAL** docs — explains empty legal registers / historical 0/11 checklist.
- SPG: LEGAL-heavy (191) even before parse completes.
- Elder Care: BACKGROUND 621 docs mostly low-conf / not should_parse; FINANCIAL is the bulk of parse load.

---

## 5. Analysis D — Chunk / embedding text volume

### Totals

| Company | Chunks | Files | Total chars | Avg | p50 | p95 | Words | Approx tokens (chars/4) |
|---------|--------|-------|-------------|-----|-----|-----|-------|-------------------------|
| Clearsulting | 2417 | 22 | 4.1M | 1689.8 | 271 | 7362 | 1.0M | 1.0M |
| Elder Care | 55812 | 450 | 287.8M | 5156.9 | 6747 | 7459 | 50.3M | 72.0M |
| GKF | 3107 | 40 | 11.9M | 3827.4 | 3528 | 7387 | 2.1M | 3.0M |
| SPG | 44100 | 395 | 144.6M | 3278.0 | 1902 | 7402 | 22.9M | 36.1M |

### By source_type

| Company | source_type | Chunks | Chars | Words |
|---------|-------------|--------|-------|-------|
| Clearsulting | vision | 1224 | 300.1k | 41.6k |
| Clearsulting | text | 1083 | 3.7M | 973.2k |
| Clearsulting | table | 110 | 93.9k | 17.1k |
| Elder Care | text | 50438 | 283.6M | 49.5M |
| Elder Care | vision | 2699 | 1.0M | 163.7k |
| Elder Care | table | 2675 | 3.2M | 619.5k |
| GKF | text | 2431 | 11.4M | 2.0M |
| GKF | vision | 339 | 119.0k | 18.4k |
| GKF | table | 337 | 343.1k | 67.0k |
| SPG | text | 31020 | 134.2M | 20.9M |
| SPG | table | 8274 | 8.5M | 1.7M |
| SPG | vision | 4789 | 1.8M | 302.6k |

### By file_type

| Company | file_type | Chunks | Files | Chars |
|---------|-----------|--------|-------|-------|
| Clearsulting | pdf | 1800 | 7 | 747.2k |
| Clearsulting | xlsx | 617 | 15 | 3.3M |
| Elder Care | xlsx | 47572 | 155 | 279.3M |
| Elder Care | pdf | 7768 | 269 | 7.5M |
| Elder Care | docx | 336 | 23 | 331.6k |
| Elder Care | csv | 136 | 3 | 641.9k |
| GKF | xlsx | 1801 | 33 | 10.1M |
| GKF | pdf | 1306 | 7 | 1.8M |
| SPG | pdf | 24246 | 303 | 26.8M |
| SPG | xlsx | 19854 | 92 | 117.8M |

### Page / section coverage

| Company | Chunks | With page | Max page | Distinct sections |
|---------|--------|-----------|----------|-------------------|
| Clearsulting | 2417 | 1800 | 82 | 588 |
| Elder Care | 55812 | 7768 | 102 | 2318 |
| GKF | 3107 | 1306 | 484 | 651 |
| SPG | 44039 | 24185 | 243 | 4519 |

### Embedded text by workstream (chunks join embeddings)

| Company | Workstream | Embeddings | Chars | Words | Avg chars |
|---------|------------|------------|-------|-------|-----------|
| Clearsulting | FINANCIAL | 574 | 2.4M | 547.9k | 4181.7 |
| Clearsulting | KPI_OPS | 179 | 1.1M | 402.0k | 6089.5 |
| Clearsulting | BUSINESS_MODEL | 1644 | 567.8k | 78.1k | 345.4 |
| Clearsulting | CUSTOMER | 62 | 264.1k | 32.6k | 4259.5 |
| Clearsulting | QUALITY_EARNINGS | 133 | 150.8k | 25.7k | 1133.9 |
| Clearsulting | FORECAST | 4 | 14.1k | 1.8k | 3534.5 |
| Elder Care | FINANCIAL | 34443 | 170.5M | 28.7M | 4950.9 |
| Elder Care | KPI_OPS | 17586 | 111.0M | 20.5M | 6314.4 |
| Elder Care | QUALITY_EARNINGS | 5859 | 31.4M | 4.8M | 5364.4 |
| Elder Care | CUSTOMER | 971 | 6.0M | 2.6M | 6134.6 |
| Elder Care | LEGAL | 2469 | 3.5M | 562.0k | 1426.6 |
| Elder Care | BUSINESS_MODEL | 1237 | 3.2M | 545.2k | 2581.9 |
| Elder Care | BACKGROUND | 320 | 302.7k | 46.4k | 945.9 |
| Elder Care | FORECAST | 37 | 176.5k | 26.1k | 4770.1 |
| GKF | FINANCIAL | 1800 | 10.1M | 1.8M | 5629.3 |
| GKF | QUALITY_EARNINGS | 1184 | 7.8M | 1.5M | 6585.2 |
| GKF | LEGAL | 775 | 1.5M | 248.0k | 1960.5 |
| GKF | FORECAST | 230 | 1.0M | 115.9k | 4420.9 |
| GKF | BUSINESS_MODEL | 645 | 696.1k | 122.3k | 1079.2 |
| GKF | CUSTOMER | 1 | 2.7k | 544 | 2689.0 |
| GKF | KPI_OPS | 1 | 2.7k | 544 | 2689.0 |
| SPG | FINANCIAL | 30437 | 111.8M | 17.6M | 3672.9 |
| SPG | QUALITY_EARNINGS | 2636 | 15.5M | 2.7M | 5892.8 |
| SPG | KPI_OPS | 3361 | 14.5M | 2.4M | 4309.4 |
| SPG | LEGAL | 8239 | 13.3M | 2.1M | 1615.6 |
| SPG | FORECAST | 2000 | 9.2M | 1.0M | 4606.1 |
| SPG | BACKGROUND | 1862 | 4.3M | 674.1k | 2285.4 |
| SPG | CUSTOMER | 128 | 688.8k | 119.2k | 5380.9 |
| SPG | BUSINESS_MODEL | 12 | 5.9k | 666 | 493.9 |

### Embedding priority tiers

| Company | Tier | Embeddings | Files |
|---------|------|------------|-------|
| Clearsulting | None | 20 | 1 |
| Clearsulting | 1 | 1276 | 6 |
| Clearsulting | 2 | 945 | 11 |
| Clearsulting | 3 | 176 | 4 |
| Elder Care | None | 2 | 1 |
| Elder Care | 1 | 2583 | 20 |
| Elder Care | 2 | 8010 | 167 |
| Elder Care | 3 | 45217 | 264 |
| GKF | 1 | 1991 | 5 |
| GKF | 2 | 1060 | 19 |
| GKF | 3 | 56 | 16 |
| SPG | 1 | 5729 | 31 |
| SPG | 2 | 15977 | 213 |
| SPG | 3 | 22333 | 151 |

**Read:** Elder Care is an order of magnitude larger than the others (~32M words). Most of that mass is Excel FINANCIAL/KPI_OPS text, not PDF prose. Clearsulting is vision-chunk-heavy by count but word mass is still text.

---

## 6. Analysis E — Company profiles

| Company | Overlay | Conf | Deal | Banked | Gaps | Desc chars |
|---------|---------|------|------|--------|------|------------|
| Clearsulting | healthcare_services | high | recapitalization | true | 1 | 434 |
| Elder Care | healthcare_services | high | recapitalization | true | 2 | 400 |
| GKF | other | low | unknown | true | 7 | None |
| SPG | other | low | unknown | false | 7 | 111 |

GKF profiler gap list is CIM-centric (6 gaps). Clearsulting/Elder Care each flag missing revenue-model documentation.

---

## 7. Analysis F — Agent output richness and confidence

### Business model (BMA)

| company_name | cim_detected | revenue_model_tag | revenue_durability_flag | flag_confidence | overlay_conflict | n_gaps | products_json_chars | citations_chars | created_at |
|---|---|---|---|---|---|---|---|---|---|
| Clearsulting | true | project_based | Green | high | false | 3 | 5342 | 6073 | 2026-07-30T13:42:34.289Z |
| Elder Care | true | repeat_services | Yellow | medium | false | 2 | 1892 | 4494 | 2026-07-28T22:37:56.462Z |
| GKF | true | pure_recurring | Green | medium | false | 2 | 2616 | 4865 | 2026-07-30T13:38:56.643Z |
| SPG | false | hybrid | Yellow | medium | false | 3 | 1784 | 4071 | 2026-07-30T13:49:45.147Z |

### Financial trends (FTA)

| company_name | industry_overlay_used | addback_pct_of_ebitda | n_gaps | exec_chars | rev_json_chars | ebitda_json_chars | addback_json_chars | created_at |
|---|---|---|---|---|---|---|---|---|
| Clearsulting | healthcare_services | 45.4 | 1 | 515 | 3450 | 1664 | 6224 | 2026-07-30T13:40:00.329Z |
| Elder Care | healthcare_services | 246.9 | 1 | 735 | 2894 | 3595 | 5986 | 2026-07-28T22:35:53.492Z |
| GKF | other | 569.3 | 2 | 627 | 693 | 1505 | 3291 | 2026-07-30T13:37:19.954Z |
| SPG | other | None | 3 | 430 | 714 | 2 | 2 | 2026-08-19T12:43:10.299Z |

### Legal

| company_name | section_confidence | n_gaps | exec_chars | contract_json_chars | employment_json_chars | litigation_json_chars | insurance_json_chars | unable_json_chars | citations_chars | created_at |
|---|---|---|---|---|---|---|---|---|---|---|
| Clearsulting | low | 11 | 264 | 2 | 2 | 2 | 2 | 423 | 2 | 2026-07-30T13:43:19.644Z |
| Elder Care | high | 5 | 246 | 5789 | 2796 | 510 | 2093 | 165 | 8098 | 2026-07-28T22:40:23.502Z |
| GKF | high | 5 | 239 | 6226 | 3265 | 2 | 4822 | 145 | 8398 | 2026-07-30T13:41:13.335Z |
| SPG | medium | 8 | 246 | 2847 | 930 | 1622 | 1027 | 287 | 8550 | 2026-07-30T13:51:44.593Z |

### Customer quality (CQA)

| company_name | n_gaps | n_triggers | exec_chars | top_cust_chars | citations_chars | created_at |
|---|---|---|---|---|---|---|
| Clearsulting | 5 | 1 | 699 | 6568 | 6483 | 2026-07-30T13:40:26.234Z |
| Elder Care | 3 | 0 | 823 | 6511 | 2601 | 2026-07-28T22:35:47.998Z |
| GKF | 2 | 0 | 703 | 2481 | 2289 | 2026-07-30T13:36:35.501Z |
| SPG | 2 | 0 | 738 | 6492 | 5971 | 2026-07-30T13:47:43.943Z |

### KPI

| company_name | overlay_confirmed | n_gaps | exec_chars | healthcare_kpi_chars | missing_kpi_chars | citations_chars | created_at |
|---|---|---|---|---|---|---|---|
| Clearsulting | tech_services | 14 | 852 | 842 | 4720 | 6511 | 2026-07-30T13:40:10.370Z |
| Elder Care | healthcare_services | 11 | 800 | 4847 | 4122 | 6857 | 2026-07-28T22:36:13.009Z |
| GKF | consumer | 10 | 691 | 914 | 4296 | 3983 | 2026-07-30T13:36:49.066Z |
| SPG | healthcare_services | 10 | 852 | 2908 | 3940 | 3312 | 2026-07-30T13:47:29.021Z |

### Quality of earnings (QoE)

| company_name | qofe_report_present | total_addbacks_pct_of_ebitda | tier4_addback_count | n_gaps | exec_chars | ledger_chars | citations_chars | created_at |
|---|---|---|---|---|---|---|---|---|
| Clearsulting | true | 45.4 | 12 | 1 | 903 | 9895 | 6258 | 2026-07-30T13:45:31.932Z |
| Elder Care | false | 88.7 | 17 | 2 | 877 | 9622 | 1967 | 2026-07-28T22:39:53.527Z |
| GKF | true | 0.1 | 10 | 1 | 1114 | 6704 | 5457 | 2026-07-30T13:41:18.360Z |
| SPG | false | None | 2 | 3 | 654 | 1549 | 2182 | 2026-07-30T13:51:27.444Z |

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
| Clearsulting | baseline | complete | 2 | 2026-08-14 | 57.0 | 0 | 0.042 |
| Clearsulting | baseline | incomplete | 4 | 2026-08-14 | 57.0 | 0 | 0 |
| Clearsulting | pipeline | complete | 12 | 2026-07-30 | 7.7 | 0 | 0 |
| Elder Care | enhancement | complete | 4 | 2026-08-11 | 53.0 | 0 | 0.056 |
| Elder Care | baseline | complete | 15 | 2026-08-11 | 51.1 | 0 | 0.07 |
| Elder Care | baseline | incomplete | 8 | 2026-08-11 | 57.0 | 0 | 0 |
| Elder Care | pipeline | complete | 52 | 2026-07-28 | 8.6 | 0.17 | 0 |
| Elder Care | ablation | complete | 4 | 2026-07-03 | 49.0 | 0 | 0.093 |
| GKF | baseline | complete | 1 | 2026-08-19 | 57.0 | 0 | 0.062 |
| GKF | pipeline | complete | 20 | 2026-07-30 | 7.6 | 0.62 | 0 |
| SPG | pipeline | complete | 19 | 2026-08-19 | 8.2 | 0.32 | 0 |
| SPG | baseline | complete | 1 | 2026-08-19 | 57.0 | 0 | 0.188 |

### Provenance coverage

| Company | Runs | Distinct intents | Rows | Avg sim | Avg chars alloc |
|---------|------|------------------|------|---------|-----------------|
|  | 1 | 1 | 16 | 0.482 | None |
| Clearsulting | 12 | 53 | 1447 | 0.522 | 1336.8 |
| Elder Care | 70 | 62 | 10398 | 0.514 | 1252.8 |
| GKF | 17 | 57 | 992 | 0.378 | 959.2 |
| SPG | 20 | 49 | 1159 | 0.377 | 788.2 |

### Provenance by source_type

| Company | source_type | Hits | Avg sim |
|---------|-------------|------|---------|
|  | text | 12 | 0.463 |
|  | table | 3 | 0.53 |
|  | vision | 1 | 0.565 |
| Clearsulting | text | 984 | 0.497 |
| Clearsulting | vision | 246 | 0.568 |
| Clearsulting | table | 217 | 0.581 |
| Elder Care | text | 5970 | 0.475 |
| Elder Care | vision | 2347 | 0.571 |
| Elder Care | table | 2081 | 0.56 |
| GKF | text | 836 | 0.355 |
| GKF | vision | 85 | 0.58 |
| GKF | table | 71 | 0.402 |
| SPG | text | 871 | 0.353 |
| SPG | table | 256 | 0.459 |
| SPG | vision | 32 | 0.361 |

### Elder Care baseline intent rollup (`baseline_1aeb0ace584a`)

Eval status dist: evaluated=43, skipped_bootstrap_failed=6. Gold-label intent scoring is **Elder Care only**.

| Agent | Intents | Avg recall@10 | Avg MRR | Avg results | Empty |
|-------|---------|---------------|---------|-------------|-------|
| bma | 9 | 0.017 | 0.093 | 9.1 | 3 |
| bma | 9 | 0.022 | 0.356 | 14.0 | 0 |
| bma | 9 | 0.062 | 0.398 | 9.1 | 0 |
| bma | 9 | 0.029 | 0.217 | 9.2 | 0 |
| cqa | 9 | 0.0 | 0.0 | 3.4 | 5 |
| cqa | 9 | 0.003 | 0.429 | 3.3 | 3 |
| cqa | 9 | 0.011 | 0.056 | 4.8 | 2 |
| cqa | 9 | 0.005 | 1.0 | 5.4 | 2 |
| fta.ebitda | 4 | 0.0 | 0.667 | 8.0 | 0 |
| fta.ebitda | 4 | 0.167 | 0.438 | 7.0 | 0 |
| fta.ebitda | 4 | 0.093 | 0.425 | 8.0 | 0 |
| fta.ebitda | 4 | 0.001 | 0.25 | 8.0 | 0 |
| fta.opex | 3 | 0.032 | 0.389 | 6.3 | 0 |
| fta.opex | 3 | 0.0 | 0.0 | 6.7 | 0 |
| fta.opex | 3 | 0.001 | 0.5 | 6.7 | 0 |
| fta.opex | 3 | 0.167 | 0.417 | 5.7 | 0 |
| fta.revenue | 6 | 0.083 | 0.25 | 2.8 | 1 |
| fta.revenue | 6 | 0.083 | 0.139 | 6.5 | 0 |
| fta.revenue | 6 | 0.001 | 0.167 | 6.8 | 0 |
| fta.revenue | 6 | 0.0 | 0.2 | 5.7 | 0 |
| kpi | 9 | 0.014 | 0.525 | 5.6 | 3 |
| kpi | 9 | 0.134 | 0.25 | 8.2 | 0 |
| kpi | 9 | 0.041 | 0.6 | 8.0 | 0 |
| kpi | 9 | 0.014 | 0.352 | 7.2 | 0 |
| legal | 5 | None | None | 0.0 | 5 |
| legal | 5 | None | None | 9.0 | 0 |
| legal | 5 | 0.1 | 0.417 | 9.2 | 0 |
| legal | 5 | 0.027 | 0.2 | 7.6 | 1 |
| profiler | 7 | 0.004 | 1.0 | 4.6 | 0 |
| profiler | 7 | 0.0 | 0.0 | 4.0 | 1 |
| profiler | 7 | 0.0 | 0.0 | 2.0 | 4 |
| profiler | 7 | 0.005 | 0.857 | 3.6 | 0 |
| qoe | 5 | 0.006 | 1.0 | 8.4 | 0 |
| qoe | 5 | 0.001 | 0.6 | 6.0 | 1 |
| qoe | 5 | 0.013 | 0.3 | 8.4 | 0 |
| qoe | 5 | 0.011 | 0.5 | 6.2 | 0 |

### All 49 baseline intents (detail)

| Agent | Intent | Status | Recall@10 | MRR | Results | Mode |
|-------|--------|--------|-----------|-----|---------|------|
| bma | bma.detect_cim_presence | evaluated | 0.0 | 0.0 | 3 | semantic |
| bma | bma.detect_cim_presence | evaluated | 0.0 | 0.0 | 3 | semantic |
| bma | bma.detect_cim_presence | evaluated | 0.0 | 0.0 | 3 | semantic |
| bma | bma.detect_cim_presence | evaluated | 0.0 | 0.0 | 0 | empty |
| bma | bma.retrieve_business_overview | evaluated | 0.0741 | 1.0 | 5 | semantic |
| bma | bma.retrieve_business_overview | evaluated | 0.04 | 0.5 | 18 | semantic |
| bma | bma.retrieve_business_overview | evaluated | 0.1111 | 1.0 | 12 | semantic |
| bma | bma.retrieve_business_overview | evaluated | 0.0 | 0.0 | 0 | empty |
| bma | bma.retrieve_model_changes_and_dependencies | evaluated | 0.037 | 0.25 | 4 | semantic |
| bma | bma.retrieve_model_changes_and_dependencies | evaluated | 0.02 | 0.2 | 18 | semantic |
| bma | bma.retrieve_model_changes_and_dependencies | evaluated | 0.0556 | 0.333 | 3 | semantic |
| bma | bma.retrieve_model_changes_and_dependencies | evaluated | 0.0282 | 0.333 | 10 | semantic |
| bma | bma.retrieve_people_and_org | evaluated | 0.0741 | 0.2 | 15 | semantic |
| bma | bma.retrieve_people_and_org | evaluated | 0.04 | 1.0 | 15 | semantic |
| bma | bma.retrieve_people_and_org | evaluated | 0.0 | 0.0 | 15 | semantic |
| bma | bma.retrieve_people_and_org | evaluated | 0.0 | 0.0 | 0 | empty |
| bma | bma.retrieve_pricing_and_margins | evaluated | 0.0 | 0.0 | 15 | semantic |
| bma | bma.retrieve_pricing_and_margins | evaluated | 0.07 | 1.0 | 15 | semantic |
| bma | bma.retrieve_pricing_and_margins | evaluated | 0.2222 | 1.0 | 15 | semantic |
| bma | bma.retrieve_pricing_and_margins | evaluated | 0.0 | 0.0 | 15 | semantic |
| bma | bma.retrieve_revenue_by_location_and_metrics | evaluated | 0.0741 | 0.5 | 10 | semantic |
| bma | bma.retrieve_revenue_by_location_and_metrics | evaluated | 0.0 | 0.0 | 15 | semantic |
| bma | bma.retrieve_revenue_by_location_and_metrics | evaluated | 0.0 | 0.0 | 4 | semantic |
| bma | bma.retrieve_revenue_by_location_and_metrics | evaluated | 0.0141 | 0.167 | 15 | semantic |
| bma | bma.retrieve_revenue_visibility | evaluated | 0.0 | 0.0 | 9 | semantic |
| bma | bma.retrieve_revenue_visibility | evaluated | 0.0 | 0.0 | 12 | semantic |
| bma | bma.retrieve_revenue_visibility | evaluated | 0.0556 | 0.25 | 5 | semantic |
| bma | bma.retrieve_revenue_visibility | evaluated | 0.1127 | 0.333 | 12 | semantic |
| bma | bma.retrieve_sales_and_customers | evaluated | 0.0 | 0.0 | 7 | semantic |
| bma | bma.retrieve_sales_and_customers | evaluated | 0.0 | 0.0 | 15 | semantic |
| bma | bma.retrieve_sales_and_customers | evaluated | 0.1111 | 1.0 | 10 | semantic |
| bma | bma.retrieve_sales_and_customers | evaluated | 0.0 | 0.0 | 15 | semantic |
| bma | bma.retrieve_workforce_and_capacity | evaluated | 0.0 | 0.0 | 15 | semantic |
| bma | bma.retrieve_workforce_and_capacity | evaluated | 0.03 | 0.5 | 15 | semantic |
| bma | bma.retrieve_workforce_and_capacity | evaluated | 0.0 | 0.0 | 15 | semantic |
| bma | bma.retrieve_workforce_and_capacity | evaluated | 0.0 | 0.0 | 15 | semantic |
| cqa | cqa.retrieve_account_size | evaluated | 0.0 | 0.0 | 0 | empty |
| cqa | cqa.retrieve_account_size | evaluated | 0.0 | 0.0 | 3 | semantic |
| cqa | cqa.retrieve_account_size | skipped_bootstrap_failed | None | None | 0 | None |
| cqa | cqa.retrieve_account_size | evaluated | 0.0 | 0.0 | 0 | empty |
| cqa | cqa.retrieve_cohort_data | evaluated | 0.0 | 0.0 | 8 | semantic |
| cqa | cqa.retrieve_cohort_data | evaluated | 0.0 | 0.0 | 0 | empty |
| cqa | cqa.retrieve_cohort_data | evaluated | 0.0034 | 1.0 | 4 | semantic |
| cqa | cqa.retrieve_cohort_data | evaluated | 0.0 | 0.0 | 0 | empty |
| cqa | cqa.retrieve_contract_terms | evaluated | 0.0 | 0.0 | 10 | semantic |
| cqa | cqa.retrieve_contract_terms | skipped_bootstrap_failed | None | None | 0 | None |
| cqa | cqa.retrieve_contract_terms | skipped_bootstrap_failed | None | None | 10 | None |
| cqa | cqa.retrieve_contract_terms | evaluated | 0.0 | 0.0 | 10 | semantic |
| cqa | cqa.retrieve_customer_concentration | evaluated | 0.0 | 0.0 | 2 | semantic |
| cqa | cqa.retrieve_customer_concentration | skipped_bootstrap_failed | None | None | 3 | None |
| cqa | cqa.retrieve_customer_concentration | skipped_bootstrap_failed | None | None | 0 | None |
| cqa | cqa.retrieve_customer_concentration | evaluated | 0.0 | 0.0 | 0 | empty |
| cqa | cqa.retrieve_customer_health | evaluated | 0.0 | 0.0 | 0 | empty |
| cqa | cqa.retrieve_customer_health | evaluated | 0.0157 | 1.0 | 8 | semantic |
| cqa | cqa.retrieve_customer_health | evaluated | 0.0054 | 1.0 | 8 | semantic |
| cqa | cqa.retrieve_customer_health | evaluated | 0.0 | 0.0 | 0 | empty |
| cqa | cqa.retrieve_customer_tenure | evaluated | 0.0 | 0.0 | 1 | semantic |
| cqa | cqa.retrieve_customer_tenure | evaluated | 0.0018 | 1.0 | 2 | semantic |
| cqa | cqa.retrieve_customer_tenure | evaluated | 0.0052 | 1.0 | 5 | semantic |
| cqa | cqa.retrieve_customer_tenure | evaluated | 0.0 | 0.0 | 0 | empty |
| cqa | cqa.retrieve_payor_mix | evaluated | 0.0 | 0.0 | 6 | semantic |
| cqa | cqa.retrieve_payor_mix | evaluated | 0.0052 | 1.0 | 6 | semantic |
| cqa | cqa.retrieve_payor_mix | evaluated | 0.0041 | 1.0 | 6 | semantic |
| cqa | cqa.retrieve_payor_mix | evaluated | 0.0 | 0.0 | 6 | semantic |
| cqa | cqa.retrieve_retention_metrics | evaluated | 0.0 | 0.0 | 8 | semantic |
| cqa | cqa.retrieve_retention_metrics | evaluated | 0.0 | 0.0 | 0 | empty |
| cqa | cqa.retrieve_retention_metrics | evaluated | 0.0068 | 1.0 | 8 | semantic |
| cqa | cqa.retrieve_retention_metrics | evaluated | 0.0 | 0.0 | 7 | semantic |
| cqa | cqa.retrieve_revenue_type_and_renewals | evaluated | 0.1 | 0.5 | 8 | semantic |
| cqa | cqa.retrieve_revenue_type_and_renewals | evaluated | 0.0 | 0.0 | 8 | semantic |
| cqa | cqa.retrieve_revenue_type_and_renewals | evaluated | 0.004 | 1.0 | 8 | semantic |
| cqa | cqa.retrieve_revenue_type_and_renewals | evaluated | 0.0 | 0.0 | 8 | semantic |
| fta.ebitda | fta.ebitda.q1_financial_statements | evaluated | 0.3333 | 0.25 | 10 | semantic |
| fta.ebitda | fta.ebitda.q1_financial_statements | evaluated | 0.0071 | 1.0 | 10 | semantic |
| fta.ebitda | fta.ebitda.q1_financial_statements | evaluated | 0.005 | 1.0 | 10 | semantic |
| fta.ebitda | fta.ebitda.q1_financial_statements | skipped_bootstrap_failed | None | None | 10 | None |
| fta.ebitda | fta.ebitda.q2_ebitda_and_margins | evaluated | 0.1667 | 1.0 | 8 | semantic |
| fta.ebitda | fta.ebitda.q2_ebitda_and_margins | evaluated | 0.2727 | 0.5 | 8 | semantic |
| fta.ebitda | fta.ebitda.q2_ebitda_and_margins | evaluated | 0.0 | 0.0 | 8 | semantic |
| fta.ebitda | fta.ebitda.q2_ebitda_and_margins | evaluated | 0.0 | 0.0 | 8 | semantic |
| fta.ebitda | fta.ebitda.q3_working_capital | evaluated | 0.0 | 0.0 | 4 | semantic |
| fta.ebitda | fta.ebitda.q3_working_capital | evaluated | 0.0 | 0.0 | 4 | semantic |
| fta.ebitda | fta.ebitda.q3_working_capital | evaluated | 0.0 | 0.0 | 4 | semantic |
| fta.ebitda | fta.ebitda.q3_working_capital | evaluated | 0.0005 | 1.0 | 4 | semantic |
| fta.ebitda | fta.ebitda.q4_addback_schedule | evaluated | 0.1667 | 0.5 | 6 | semantic |
| fta.ebitda | fta.ebitda.q4_addback_schedule | evaluated | 0.0909 | 0.2 | 10 | semantic |
| fta.ebitda | fta.ebitda.q4_addback_schedule | evaluated | 0.0 | 0.0 | 10 | semantic |
| fta.ebitda | fta.ebitda.q4_addback_schedule | evaluated | 0.0005 | 1.0 | 10 | semantic |
| fta.opex | fta.opex.q1_financial_statements | evaluated | 0.0 | 0.0 | 8 | semantic |
| fta.opex | fta.opex.q1_financial_statements | evaluated | 0.0063 | 1.0 | 8 | semantic |
| fta.opex | fta.opex.q1_financial_statements | evaluated | 0.002 | 1.0 | 5 | semantic |
| fta.opex | fta.opex.q1_financial_statements | skipped_bootstrap_failed | None | None | 8 | None |
| fta.opex | fta.opex.q2_working_capital | evaluated | 0.0 | 0.0 | 4 | semantic |
| fta.opex | fta.opex.q2_working_capital | evaluated | 0.0 | 0.0 | 4 | semantic |
| fta.opex | fta.opex.q2_working_capital | evaluated | 0.0 | 0.0 | 4 | semantic |
| fta.opex | fta.opex.q2_working_capital | evaluated | 0.0 | 0.0 | 4 | semantic |
| fta.opex | fta.opex.q3_projected_financials | evaluated | 0.0 | 0.0 | 8 | semantic |
| fta.opex | fta.opex.q3_projected_financials | evaluated | 0.0909 | 0.167 | 7 | semantic |
| fta.opex | fta.opex.q3_projected_financials | evaluated | 0.5 | 0.25 | 8 | semantic |
| fta.opex | fta.opex.q3_projected_financials | evaluated | 0.0014 | 1.0 | 8 | semantic |
| fta.revenue | fta.revenue.q1_financial_statements | evaluated | 0.3333 | 0.333 | 10 | semantic |
| fta.revenue | fta.revenue.q1_financial_statements | evaluated | 0.0063 | 1.0 | 10 | semantic |
| fta.revenue | fta.revenue.q1_financial_statements | evaluated | 0.0005 | 1.0 | 2 | semantic |
| fta.revenue | fta.revenue.q1_financial_statements | skipped_bootstrap_failed | None | None | 4 | None |
| fta.revenue | fta.revenue.q2_revenue_by_segment | evaluated | 0.0 | 0.0 | 5 | semantic |
| fta.revenue | fta.revenue.q2_revenue_by_segment | evaluated | 0.0 | 0.0 | 5 | semantic |
| fta.revenue | fta.revenue.q2_revenue_by_segment | evaluated | 0.0 | 0.0 | 5 | semantic |
| fta.revenue | fta.revenue.q2_revenue_by_segment | evaluated | 0.0 | 0.0 | 5 | semantic |
| fta.revenue | fta.revenue.q3_revenue_by_geography | evaluated | 0.0 | 0.0 | 6 | semantic |
| fta.revenue | fta.revenue.q3_revenue_by_geography | evaluated | 0.0 | 0.0 | 6 | semantic |
| fta.revenue | fta.revenue.q3_revenue_by_geography | evaluated | 0.0 | 0.0 | 6 | semantic |
| fta.revenue | fta.revenue.q3_revenue_by_geography | evaluated | 0.0002 | 1.0 | 6 | semantic |
| fta.revenue | fta.revenue.q4_customer_concentration | evaluated | 0.0 | 0.0 | 4 | semantic |
| fta.revenue | fta.revenue.q4_customer_concentration | evaluated | 0.0 | 0.0 | 6 | semantic |
| fta.revenue | fta.revenue.q4_customer_concentration | evaluated | 0.0 | 0.0 | 2 | semantic |
| fta.revenue | fta.revenue.q4_customer_concentration | evaluated | 0.0 | 0.0 | 6 | semantic |
| fta.revenue | fta.revenue.q4_customer_concentration_fallback | evaluated | 0.0 | 0.0 | 6 | semantic |
| fta.revenue | fta.revenue.q4_customer_concentration_fallback | evaluated | 0.0 | 0.0 | 6 | semantic |
| fta.revenue | fta.revenue.q4_customer_concentration_fallback | evaluated | 0.0 | 0.0 | 0 | empty |
| fta.revenue | fta.revenue.q4_customer_concentration_fallback | evaluated | 0.0 | 0.0 | 6 | semantic |
| fta.revenue | fta.revenue.q5_quickbooks_pl | evaluated | 0.1667 | 0.5 | 8 | semantic |
| fta.revenue | fta.revenue.q5_quickbooks_pl | evaluated | 0.0 | 0.0 | 8 | semantic |
| fta.revenue | fta.revenue.q5_quickbooks_pl | evaluated | 0.5 | 0.5 | 2 | semantic |
| fta.revenue | fta.revenue.q5_quickbooks_pl | evaluated | 0.0 | 0.0 | 7 | semantic |
| kpi | kpi.retrieve_bench_and_capacity | evaluated | 0.0027 | 1.0 | 8 | semantic |
| kpi | kpi.retrieve_bench_and_capacity | evaluated | 0.0 | 0.0 | 8 | semantic |
| kpi | kpi.retrieve_bench_and_capacity | evaluated | 0.0 | 0.0 | 8 | semantic |
| kpi | kpi.retrieve_bench_and_capacity | evaluated | 0.0014 | 1.0 | 8 | semantic |
| kpi | kpi.retrieve_bill_rates_and_margins | skipped_bootstrap_failed | None | None | 10 | None |
| kpi | kpi.retrieve_bill_rates_and_margins | evaluated | 0.875 | 1.0 | 10 | semantic |
| kpi | kpi.retrieve_bill_rates_and_margins | evaluated | 0.0882 | 0.2 | 10 | semantic |
| kpi | kpi.retrieve_bill_rates_and_margins | evaluated | 0.0002 | 1.0 | 10 | semantic |
| kpi | kpi.retrieve_delivery_model | evaluated | 0.0 | 0.0 | 4 | semantic |
| kpi | kpi.retrieve_delivery_model | evaluated | 0.0 | 0.0 | 6 | semantic |
| kpi | kpi.retrieve_delivery_model | evaluated | 0.0 | 0.0 | 0 | empty |
| kpi | kpi.retrieve_delivery_model | evaluated | 0.0 | 0.0 | 1 | semantic |
| kpi | kpi.retrieve_headcount_attrition | skipped_bootstrap_failed | None | None | 6 | None |
| kpi | kpi.retrieve_headcount_attrition | evaluated | 0.2 | 1.0 | 6 | semantic |
| kpi | kpi.retrieve_headcount_attrition | evaluated | 0.0 | 0.0 | 0 | empty |
| kpi | kpi.retrieve_headcount_attrition | evaluated | 0.0 | 0.0 | 6 | semantic |
| kpi | kpi.retrieve_healthcare_labor_market | skipped_bootstrap_failed | None | None | 8 | None |
| kpi | kpi.retrieve_healthcare_labor_market | skipped_bootstrap_failed | None | None | 8 | None |
| kpi | kpi.retrieve_healthcare_labor_market | evaluated | 0.004 | 1.0 | 8 | semantic |
| kpi | kpi.retrieve_healthcare_labor_market | evaluated | 0.0 | 0.0 | 8 | semantic |
| kpi | kpi.retrieve_healthcare_ops | evaluated | 0.05 | 1.0 | 8 | semantic |
| kpi | kpi.retrieve_healthcare_ops | evaluated | 0.0 | 0.0 | 8 | semantic |
| kpi | kpi.retrieve_healthcare_ops | evaluated | 0.0054 | 1.0 | 8 | semantic |
| kpi | kpi.retrieve_healthcare_ops | evaluated | 0.125 | 0.167 | 8 | semantic |
| kpi | kpi.retrieve_healthcare_revenue_per_unit | evaluated | 0.1509 | 1.0 | 8 | semantic |
| kpi | kpi.retrieve_healthcare_revenue_per_unit | evaluated | 0.0 | 0.0 | 8 | semantic |
| kpi | kpi.retrieve_healthcare_revenue_per_unit | evaluated | 0.0054 | 1.0 | 8 | semantic |
| kpi | kpi.retrieve_healthcare_revenue_per_unit | evaluated | 0.0 | 0.0 | 4 | semantic |
| kpi | kpi.retrieve_kpi_dashboard | evaluated | 0.0 | 0.0 | 12 | semantic |
| kpi | kpi.retrieve_kpi_dashboard | evaluated | 0.0 | 0.0 | 12 | semantic |
| kpi | kpi.retrieve_kpi_dashboard | skipped_bootstrap_failed | None | None | 0 | None |
| kpi | kpi.retrieve_kpi_dashboard | evaluated | 0.0 | 0.0 | 12 | semantic |
| kpi | kpi.retrieve_pipeline_backlog | skipped_bootstrap_failed | None | None | 8 | None |
| kpi | kpi.retrieve_pipeline_backlog | evaluated | 0.0 | 0.0 | 8 | semantic |
| kpi | kpi.retrieve_pipeline_backlog | evaluated | 0.0054 | 1.0 | 8 | semantic |
| kpi | kpi.retrieve_pipeline_backlog | evaluated | 0.0014 | 1.0 | 8 | semantic |
| legal | legal.contracts_vendors_platform | evaluated | 0.0 | 0.0 | 14 | semantic |
| legal | legal.contracts_vendors_platform | skipped_bootstrap_failed | None | None | 0 | None |
| legal | legal.contracts_vendors_platform | skipped_bootstrap_failed | None | None | 14 | None |
| legal | legal.contracts_vendors_platform | evaluated | 0.0 | 0.083 | 14 | semantic |
| legal | legal.employment | evaluated | 0.1333 | 1.0 | 10 | semantic |
| legal | legal.employment | skipped_bootstrap_failed | None | None | 0 | None |
| legal | legal.employment | skipped_bootstrap_failed | None | None | 10 | None |
| legal | legal.employment | evaluated | 0.0 | 0.0 | 10 | semantic |
| legal | legal.insurance | evaluated | 0.0 | 0.0 | 6 | semantic |
| legal | legal.insurance | skipped_bootstrap_failed | None | None | 0 | None |
| legal | legal.insurance | skipped_bootstrap_failed | None | None | 6 | None |
| legal | legal.insurance | evaluated | 0.375 | 1.0 | 6 | semantic |
| legal | legal.ip_privacy | evaluated | 0.0 | 0.0 | 0 | empty |
| legal | legal.ip_privacy | skipped_bootstrap_failed | None | None | 0 | None |
| legal | legal.ip_privacy | skipped_bootstrap_failed | None | None | 7 | None |
| legal | legal.ip_privacy | evaluated | 0.125 | 1.0 | 8 | semantic |
| legal | legal.litigation | evaluated | 0.0 | 0.0 | 8 | semantic |
| legal | legal.litigation | skipped_bootstrap_failed | None | None | 0 | None |
| legal | legal.litigation | skipped_bootstrap_failed | None | None | 8 | None |
| legal | legal.litigation | evaluated | 0.0 | 0.0 | 8 | semantic |
| profiler | profiler.banked_vs_nonbanked | evaluated | 0.0 | 0.0 | 5 | semantic |
| profiler | profiler.banked_vs_nonbanked | evaluated | 0.0037 | 1.0 | 5 | semantic |
| profiler | profiler.banked_vs_nonbanked | evaluated | 0.0 | 0.0 | 2 | semantic |
| profiler | profiler.banked_vs_nonbanked | skipped_bootstrap_failed | None | None | 0 | None |
| profiler | profiler.business_description | evaluated | 0.0 | 0.0 | 3 | semantic |
| profiler | profiler.business_description | evaluated | 0.0046 | 1.0 | 5 | semantic |
| profiler | profiler.business_description | evaluated | 0.0087 | 1.0 | 5 | semantic |
| profiler | profiler.business_description | skipped_bootstrap_failed | None | None | 5 | None |
| profiler | profiler.company_size_indicators | skipped_bootstrap_failed | None | None | 5 | None |
| profiler | profiler.company_size_indicators | skipped_bootstrap_failed | None | None | 5 | None |
| profiler | profiler.company_size_indicators | evaluated | 0.0015 | 1.0 | 3 | semantic |
| profiler | profiler.company_size_indicators | evaluated | 0.0 | 0.0 | 5 | semantic |
| profiler | profiler.deal_type | evaluated | 0.0 | 0.0 | 5 | semantic |
| profiler | profiler.deal_type | evaluated | 0.0046 | 1.0 | 5 | semantic |
| profiler | profiler.deal_type | evaluated | 0.0052 | 1.0 | 3 | semantic |
| profiler | profiler.deal_type | skipped_bootstrap_failed | None | None | 0 | None |
| profiler | profiler.industry_overlay | evaluated | 0.0 | 0.0 | 5 | semantic |
| profiler | profiler.industry_overlay | evaluated | 0.0046 | 1.0 | 5 | semantic |
| profiler | profiler.industry_overlay | evaluated | 0.0087 | 1.0 | 5 | semantic |
| profiler | profiler.industry_overlay | skipped_bootstrap_failed | None | None | 4 | None |
| profiler | profiler.revenue_model | evaluated | 0.0 | 0.0 | 0 | empty |
| profiler | profiler.revenue_model | evaluated | 0.0018 | 1.0 | 2 | semantic |
| profiler | profiler.revenue_model | evaluated | 0.0035 | 1.0 | 2 | semantic |
| profiler | profiler.revenue_model | skipped_bootstrap_failed | None | None | 0 | None |
| profiler | profiler.vertical_subsector | evaluated | 0.0 | 0.0 | 5 | semantic |
| profiler | profiler.vertical_subsector | evaluated | 0.0046 | 1.0 | 5 | semantic |
| profiler | profiler.vertical_subsector | evaluated | 0.0087 | 1.0 | 5 | semantic |
| profiler | profiler.vertical_subsector | skipped_bootstrap_failed | None | None | 0 | None |
| qoe | qoe.retrieve_ebitda_bridge | evaluated | 0.0139 | 1.0 | 10 | semantic |
| qoe | qoe.retrieve_ebitda_bridge | evaluated | 0.0 | 0.0 | 10 | semantic |
| qoe | qoe.retrieve_ebitda_bridge | evaluated | 0.0068 | 1.0 | 10 | semantic |
| qoe | qoe.retrieve_ebitda_bridge | evaluated | 0.0017 | 1.0 | 10 | semantic |
| qoe | qoe.retrieve_owner_comp_support | evaluated | 0.0 | 0.0 | 6 | semantic |
| qoe | qoe.retrieve_owner_comp_support | evaluated | 0.0 | 0.0 | 6 | semantic |
| qoe | qoe.retrieve_owner_comp_support | evaluated | 0.0041 | 1.0 | 6 | semantic |
| qoe | qoe.retrieve_owner_comp_support | evaluated | 0.001 | 1.0 | 6 | semantic |
| qoe | qoe.retrieve_qofe_report | evaluated | 0.0139 | 1.0 | 1 | semantic |
| qoe | qoe.retrieve_qofe_report | evaluated | 0.0125 | 0.5 | 12 | semantic |
| qoe | qoe.retrieve_qofe_report | evaluated | 0.0084 | 1.0 | 12 | semantic |
| qoe | qoe.retrieve_qofe_report | evaluated | 0.0 | 0.0 | 0 | empty |
| qoe | qoe.retrieve_revenue_footnotes | evaluated | 0.0 | 0.0 | 6 | semantic |
| qoe | qoe.retrieve_revenue_footnotes | evaluated | 0.0 | 0.0 | 6 | semantic |
| qoe | qoe.retrieve_revenue_footnotes | evaluated | 0.0041 | 1.0 | 6 | semantic |
| qoe | qoe.retrieve_revenue_footnotes | evaluated | 0.0 | 0.0 | 6 | semantic |
| qoe | qoe.retrieve_revenue_quality | evaluated | 0.0278 | 0.5 | 8 | semantic |
| qoe | qoe.retrieve_revenue_quality | evaluated | 0.05 | 1.0 | 8 | semantic |
| qoe | qoe.retrieve_revenue_quality | evaluated | 0.0054 | 1.0 | 8 | semantic |
| qoe | qoe.retrieve_revenue_quality | evaluated | 0.0014 | 1.0 | 8 | semantic |

### Top retrieved files (provenance)

{'error': 'FAILED: [MISSING_GROUP_BY] The query does not include a GROUP BY clause. Add GROUP BY or turn it into the window functions using OVER clauses. SQLSTATE: 42803; line 2 pos 8'}

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
| Clearsulting | 2,417 | 2,417 | ✅ | 100.0% |
| Elder Care | 55,812 | 55,812 | ✅ | 98.3% |
| GKF | 3,107 | 3,107 | ✅ | 100.0% |
| SPG | 44,085 | 44,085 | ✅ | 100.0% |

### Layer 2 — Vector index / retrieval

| Index | Status |
|-------|--------|
| `uc13_ale.ingestion.embeddings_index` | **MISSING** (ResourceDoesNotExist) |
| `uc13.ingestion.embeddings_index` | exists, ready, ~15,080 rows (stale vs ale Delta) |

| Company | Pipeline fallback | Provenance avg_sim |
|---------|-------------------|-------------------|
| Clearsulting | 0.0 | 0.522 |
| Elder Care | 0.167 | 0.514 |
| GKF | 0.625 | 0.378 |
| SPG | 0.316 | 0.377 |

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
| Clearsulting | 0 | sim=0.522 | **No** (0 LEGAL tags; legal agent hollow) |
| Elder Care | 133 | sim=0.514 | Partial (gold baselines; 52% ingest) |
| GKF | 4 | sim=0.378 | Partial (keyword-only retrieval) |
| SPG | 181 | sim=0.377 | Partial (fresh agents, unvalidated retrieval) |

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
