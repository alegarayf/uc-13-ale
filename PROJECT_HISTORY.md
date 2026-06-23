# Rallyday — Project History, Story Digest & Status Diagnosis

> Generated: 2026-06-20  
> Source: full `git log --all` (88 commits), branch topology, diff vs `develop`, and `.dev/architecture/` notes.

---

## Story Digest (TL;DR)

Rallyday is a **dual-track monorepo** for Rallyday Partners:

1. **Garden application** — a React UI for portfolio companies (“My Garden”) and configurable diligence rules (“Garden Rules”), backed by an Express API, a FastAPI NL-rules AI service, and Databricks SQL for production data.
2. **UC13 diligence pipeline** — a Databricks-native PE data-room pipeline: SharePoint → Unity Catalog volumes → document classification → chunked embeddings → six workstream agents that write structured analysis to `uc13.analysis.*` Delta tables.

**The narrative arc in one paragraph:** Matt Crysler bootstrapped the Garden app (frontend, rules CRUD, NL rule generation via AI). Hector Corro built the UC13 ingestion stack on a parallel branch, merged via PR #1 in early June, then forked intensive agent work onto `feature/databricks-financial-bussines-agents`. That feature branch absorbed ~6 weeks of iterative hardening — especially financial extraction (token truncation, vision OCR for image P&L pages, financial sub-agents, EBITDA/P&L schema work) — while `develop` received a chatbot widget that never landed on the feature branch. The repo today sits **42 commits ahead of develop on agents/ingestion**, **3 commits behind on Garden UI chat**, with UC13 analysis outputs **not yet wired into the Garden UI**.

---

## Current Diagnosis

### Where we are

| Dimension | State |
|-----------|-------|
| **Active branch** | `feature/databricks-financial-bussines-agents` (tracks `origin/`) |
| **Latest commit** | `1aed882` — *fix: financial subagents and kpis retrievers* (2026-06-19) |
| **vs `develop`** | **+42 commits** (agents, ingestion, financial sub-agents) / **−3 commits** (chatbot, merge hygiene, AI-first finalize on develop) |
| **vs `main`** | Feature branch is far ahead; `main` appears stale relative to active work |
| **Working tree** | Clean except untracked `.dev/architecture/` (local architecture docs, not committed) |
| **Timeline** | ~6 weeks of active development (2026-05-07 → 2026-06-19) |

### What was implemented

#### Garden application (`frontend`, `backend-api`, `backend-ai`)

| Capability | Status | Key commits / notes |
|------------|--------|---------------------|
| React SPA scaffold (Vite, TypeScript) | ✅ Done | `fbf2328` Initial frontend concept |
| Rules REST API + Databricks SQL store | ✅ Done | `987d773` rules table APIs |
| My Garden company view | ✅ Done | `f35adc0` company view for assigned companies |
| NL → Python rule generation (AI-first) | ✅ Done | `9cca922`, `8f56103`, `7b191f6` |
| Rules search bar | ✅ Done | `ee33d42` |
| AI rule row shows config filename | ✅ Done | `1dff51a` |
| PascalCase field refs in generated Python | ✅ Done | `7b191f6` |
| Databricks `app.yml` | ✅ Done | `6ad2dfc` |
| **Genie data chatbot widget** | ✅ on `develop` only | `e3ebd9a` — **removed/reverted on feature branch** |
| Rule execution at runtime against `opportunity_silver` | ❌ Not built | Open question in architecture docs |

#### UC13 ingestion pipeline (`databricks/jobs`, `databricks/workflows`)

| Phase | Capability | Status | Key commits |
|-------|------------|--------|-------------|
| **1** | SharePoint connector + UC Volume upload | ✅ Done | `142a1ee`, `9e70e9e`, `8704b3b` (1,241 files ingested) |
| **1** | Client-credentials auth | ✅ Done | `58cd2f7` |
| **1** | Company-scoped volume paths + dedup | ✅ Done | `18e682a`, `ebd25c2` |
| **2a** | Document classifier (workstream tags, priority tiers) | ✅ Done | `6d1b3e2` productive scripts push |
| **2b** | Ingestion parser (PDF/Excel/Word/CSV → chunks + embeddings) | ✅ Done, heavily iterated | `edf4137` → `3f66a29` ingestion 2.1 |
| **2b** | Vision extraction for image/chart pages | ✅ Done | `20a8611`, `e3c675e`, `3068acf`–`4524a99` |
| **2c** | `ensure_coverage.py` incremental gap filler | ✅ Done | `12af382` |
| **2b** | Company profiler (industry overlay detection) | ✅ Done | `company_profiler.py` |
| **Infra** | Vector search setup, UC schema creation | ✅ Done | `7916561`, `957dcad` |
| **Infra** | Workflow YAML (`uc13_ingestion_pipeline.yml`) | ✅ Done | evolved across May–June |

#### UC13 workstream agents (`databricks/agents`)

| Agent | File | Status |
|-------|------|--------|
| Business Model (BMA) | `business_model_agent.py` | ✅ Built; 7 enhancement iterations (Jun 10) |
| Financial Trends (FTA) | `financial_trends_agent.py` | ✅ Built; most active — 6+ enhancement rounds + sub-agents |
| Customer Quality | `customer_quality_agent.py` | ✅ Scaffolded (`b3bbec9`) |
| KPI | `kpi_agent.py` | ✅ Scaffolded; retriever fixes (`1aed882`) |
| Legal Contracts | `legal_contracts_agent.py` | ✅ Scaffolded |
| Quality of Earnings | `quality_of_earnings_agent.py` | ✅ Scaffolded |
| Financial sub-agents | `revenue_sub_agent`, `ebitda_sub_agent`, `opex_sub_agent` | ✅ Added Jun 16–17 (`2ff08db`, `1aed882`) |
| Agent coverage script | `ensure_coverage.py` | ✅ `12af382` |
| MD → Word export | `md_to_word.py` | ✅ `032fadb` |

#### Shared agent infrastructure

- `agent_base.py` — WorkstreamAgent base, LLM calls, trace infrastructure
- `retrieval.py` — `semantic_search()` with source-type priority/filter for financial retrieval
- Two-LLM pattern: Sonnet for extraction, Sonnet/Haiku for narrative/vision (documented in `databricks/CLAUDE.md`)

---

### Blockers & pain points (inferred from commit history)

These recurring themes drove the majority of fix commits on the feature branch:

| Blocker | Manifestation | Resolution path (commits) |
|---------|---------------|---------------------------|
| **LLM output truncation** | Large JSON schemas (EBITDA, FTA) exceeded model token ceilings | Switched Haiku → Sonnet for extraction (`c47e747`, `989cc39`); explicit `max_tokens` overrides; schema reordering (`b8ec7f5`, `a51acb5`) |
| **Haiku 8K token cap** | Silent flooring of requested max_tokens | Documented in `CLAUDE.md`; Sonnet 4.6 required for 10–16K output |
| **Image-only financial PDF pages** | `ai_parse_document` returned no text for scanned P&L | Vision pipeline + sparse-page detection without header match (`3068acf`–`4524a99`) |
| **`ai_parse_document` v2.0 API change** | `page_id` lived on `bbox[0]`, not element root | `4524a99` |
| **Chunking / embedding quality** | Bad boundaries, wrong vector fields, retrieval misses | `10cb778`, `ca97c3c`, `957dcad`, `0ca5a05`, `09a0388` |
| **Excel merged cells** | `read_only=True` hid merged header values | `_expand_merged_cells()` pattern (see `CLAUDE.md`) |
| **Databricks runtime friction** | Spark session, dbutils in modules, UC volume paths | `9a413af`, `48541a0`, `7916561`, `710ef5b` |
| **Upload / SharePoint connectivity** | Early connection bugs, dynamic company selection | `710ef5b`, `0094e72`, `7d667e2` |
| **Performance** | Slow retrieval / agent runs | Haiku for auxiliary calls (`e1a687c`); sub-agent decomposition (`2ff08db`) |
| **Branch divergence** | Garden chatbot landed on `develop` while agent work continued on feature branch | **Unresolved** — 3 commits on develop not in feature branch |

---

### Pending items

#### High priority (integration / merge)

- [ ] **Merge `feature/databricks-financial-bussines-agents` → `develop`** — reconcile chatbot removal vs develop additions (`DataChatWidget`, `dataChat.ts`, ~400 lines CSS)
- [ ] **Decide fate of Genie chatbot** — on develop (`e3ebd9a`), absent on feature branch
- [ ] **End-to-end validation** — run `test_pipeline.ipynb` cells per `databricks/CLAUDE.md` after merge

#### Product / architecture (from `.dev/architecture/rallyday/open-questions.md`)

- [ ] **Garden rules execution** — where/when `python_source` rules run against `opportunity_silver`
- [ ] **UC13 → Garden UI** — surface `uc13.analysis.*` outputs in My Garden or a new diligence view
- [ ] **Production auth** — frontend → API/AI auth model (SSO, gateway, VPN-only)
- [ ] **Catalog/schema convention** — confirm `garden` catalog for rules vs `uc13` for pipeline
- [ ] **Deployment topology** — Databricks Apps vs containers vs static CDN for each service
- [ ] **Shared types package** — Rule/Company types duplicated across frontend, API, AI

#### Agent / pipeline maturity

- [ ] **Non-financial agents** — BMA enhanced heavily; CQA, Legal, QoE, KPI likely need similar iteration depth
- [ ] **Financial agent production hardening** — P&L/EBITDA/addbacks work is recent (Jun 17–19); needs validation on additional companies
- [ ] **Workflow scheduling** — jobs defined in YAML but not auto-run with `npm run dev`; production scheduling TBD
- [ ] **Architecture docs completion** — `architectural-patterns.md`, `failure-taxonomy.md` pending user interview (Phase 8)

#### Repository hygiene

- [ ] Commit or gitignore `.dev/architecture/` (currently untracked)
- [ ] `main` branch sync — appears behind `develop` and feature work

---

## Contributors

| Author | Commits | Primary focus |
|--------|---------|---------------|
| Hector Corro / HecCorro | ~75 | UC13 pipeline, ingestion, agents, Databricks infra |
| Matt Crysler / Matt C | ~13 | Garden frontend, rules API, NL rules, chatbot |

---

## Branch Topology

```
main ───────────────────────────── (stale relative to active work)
  │
develop ─── PR#1 merge ─── chatbot, AI-first finalize
  │              │
  │              └── setup-databricks-uc13 (merged 2026-06-02)
  │
feature/databricks-financial-bussines-agents  ← YOU ARE HERE
  └── 42 commits: agents, ingestion 2.1, vision, financial sub-agents, md_to_word
```

**Merge base with develop:** `2ee1040` (Merge pull request #1 — 2026-06-02)

---

## Chronological Phases

### Phase 0 — Repo bootstrap (May 7–14)

| Date | Commit | Message |
|------|--------|---------|
| 2026-05-07 | `c45692c` | Initial commit (Matt C) |
| 2026-05-14 | `9328ed2` | Initial commit (Matt Crysler) |

### Phase 1 — Garden app foundation (May 15–26)

| Date | Commit | Author | Message |
|------|--------|--------|---------|
| 2026-05-15 | `142a1ee` | Hector | feat: add ingestion tools - connector and uploader |
| 2026-05-18 | `fbf2328` | Matt | Initial frontend concept |
| 2026-05-18 | `58cd2f7` | Hector | feat: swap connector auth to client credentials flow |
| 2026-05-18 | `edf4137` | HecCorro | feat: add parse and index notebook phase 1 |
| 2026-05-18 | `6ad2dfc` | Matt | Adding app.yml file for databricks |
| 2026-05-18 | `9e70e9e` | HecCorro | feat: listing files from sharepoint |
| 2026-05-18 | `18e682a` | Hector | feat: company scoping, deduplication and excel chunking fix |
| 2026-05-19 | `27076eb` | HecCorro | fix: update notebook with to_json pdf fix and company-scoped volume path |
| 2026-05-19 | `ebd25c2` | HecCorro | fix: pdf to_json fix, excel batching, company-scoped volume path |
| 2026-05-19 | `8704b3b` | HecCorro | feat: complete phase 1 - full corpus ingested 1241 files to UC volume |
| 2026-05-20 | `987d773` | Matt | Implementing initial set of APIs to interact with the rules table |
| 2026-05-21 | `8f77543` | HecCorro | feature: agents notebook creation and first retrieval techniques |
| 2026-05-22 | `f35adc0` | Matt | Beginning to add a company view for assigned companies in the garden |
| 2026-05-26 | `9cca922` | Matt | Implementing first pass NL rule creation with AI generation |
| 2026-05-26 | `1dff51a` | Matt | Updating AI rule rows to include rule config filename |
| 2026-05-26 | `ee33d42` | Matt | Adding a search bar for rules |
| 2026-05-26 | `7b191f6` | Matt | AI-first rule approach; PascalCase field names in generated Python |

### Phase 2 — UC13 ingestion hardening + PR merge (May 27 – Jun 4)

| Date | Commit | Author | Message |
|------|--------|--------|---------|
| 2026-05-27 | `6d1b3e2` | Hector | pushing productive scripts |
| 2026-05-27 | `8cb3e93` | Hector | modyfing tables for dynamic company selection |
| 2026-05-27 | `4079922` | Hector | renaming scripts for pipeline |
| 2026-05-27 | `61fefe4` | Hector | modifying testing notebook |
| 2026-05-27 | `48541a0` | Hector | modyfing dbutils usage |
| 2026-05-27 | `d3d59fc` | Hector | updating dependencies for cluster |
| 2026-05-27 | `0094e72` | Hector | addin dynamic company selection into sharepoint |
| 2026-05-28 | `710ef5b` | Hector | uploading and connection fixes |
| 2026-05-28 | `7d667e2` | Hector | upload bug fixing |
| 2026-05-28 | `7916561` | Hector | adding UC volume creation |
| 2026-05-28 | `9a413af` | Hector | fixing spark session within python scripts |
| 2026-05-28 | `7e2f20a` | Hector | creating schemas if missing |
| 2026-05-28 | `b40930b` | Hector | fixing doc prompt and mlflow import |
| 2026-05-28 | `c7ae3b3` | Hector | adding packages into cluster for doc classifier |
| 2026-05-28 | `a510434` | Hector | modyfing files destination |
| 2026-05-28 | `09a0388` | Hector | fixing priority tiers order |
| 2026-05-28 | `0ca5a05` | Hector | fixing retrieval query |
| 2026-05-28 | `957dcad` | Hector | fixing vector search fields |
| 2026-05-28 | `13035cd` | Hector | ingestion parser fix |
| 2026-05-28 | `10cb778` | Hector | fixing chunking strategy and ingestion embedding |
| 2026-05-28 | `ca97c3c` | Hector | fixing chunking boundaries |
| 2026-06-02 | `62a0a4f` | Hector | modifying logging for connector.py |
| 2026-06-02 | `b3cfa41` | Hector | Merge develop into setup-databricks-uc13 |
| 2026-06-02 | `2ee1040` | HecCorro | **Merge pull request #1** from Nimble-Gravity/setup-databricks-uc13 |
| 2026-06-04 | `8f56103` | Matt | Finalizing changes to AI-first rule creation approach |
| 2026-06-04 | `087cc0b` | Matt | Merge branch 'develop' |
| 2026-06-05 | `e3ebd9a` | Matt | Adding a chatbot to the site *(develop only)* |

### Phase 3 — Workstream agents (Jun 2 – Jun 9)

| Date | Commit | Message |
|------|--------|---------|
| 2026-06-02 | `6306c68` | adding 1st draft of bussines and financial agents |
| 2026-06-02 | `e2dd2d9` | adding file download from agent response |
| 2026-06-03 | `0ac8b4f` | fixing financial agents kpis |
| 2026-06-08 | `b3bbec9` | creating more workstream agents |
| 2026-06-09 | `12af382` | adding coverage script for all agents |

### Phase 4 — Agent enhancement iterations (Jun 10 – Jun 15)

**Financial agent (FTA):** `3d73c93` → `3ee6c10` (1st through 2_f enhancements)

**Business agent (BMA):** `81d4ed1` → `6f39911` (1st through 2_e enhancements)

| Date | Commit | Message |
|------|--------|---------|
| 2026-06-15 | `44c4a17` | refactoring enhancements for retrieval agents |
| 2026-06-15 | `20a8611` | refactoring vision model usage |
| 2026-06-15 | `3f66a29` | modifying ingestion 2_1 |
| 2026-06-16 | `e3c675e` | Adding extras to widget vision |

### Phase 5 — Ingestion vision + token/performance fixes (Jun 15 – Jun 16)

| Date | Commit | Message |
|------|--------|---------|
| 2026-06-15 | `3068acf` | detect image-only PDF pages without requiring financial section header match |
| 2026-06-15 | `6fb9400` | count only meaningful element types for image-page detection |
| 2026-06-16 | `4524a99` | extract page_id from bbox[0] not element root (ai_parse_document v2.0) |
| 2026-06-16 | `afc585c` | fix regex for CIM and business model truncate token max |
| 2026-06-16 | `c47e747` | changing to claude-sonnet and haiku for better performance |
| 2026-06-16 | `e1a687c` | speeding up retrieval with haiku agents LLM calling |
| 2026-06-16 | `b8ec7f5` | financial reordering schema and truncate problem |
| 2026-06-16 | `a51acb5` | fixing truncate json from schema for ebitda |
| 2026-06-16 | `7d9c167` | enhancing financial agent for more coverage |
| 2026-06-16 | `989cc39` | using sonet for extracting content for financials |
| 2026-06-16 | `155bf01` | using sonet for extracting content for financials and reorder schema |

### Phase 6 — Financial sub-agents + P&L/EBITDA depth (Jun 16 – Jun 19)

| Date | Commit | Message |
|------|--------|---------|
| 2026-06-17 | `2ff08db` | feature: financial subagents creation for best assessment |
| 2026-06-17 | `c50a8ec` | fix: increasing revenue tokens agent |
| 2026-06-17 | `032fadb` | feature: create md converter script to word |
| 2026-06-17 | `2dfa110` | fix: using tmp folder to store word docs |
| 2026-06-17 | `7f97189` | fix: P&L table synthesis and enhancement |
| 2026-06-17 | `a653df7` | fix: EBITDA table enhancements with costs |
| 2026-06-17 | `79ee1b5` | fix: ebitda addbacks adding and concepts |
| 2026-06-19 | `1aed882` | fix: financial subagents and kpis retrievers |

---

## Full Commit Log (newest first)

| SHA (short) | Date | Author | Subject |
|-------------|------|--------|---------|
| `1aed882` | 2026-06-19 | Hector Corro | fix: financial subagents and kpis retrievers |
| `79ee1b5` | 2026-06-17 | Hector Corro | fix: ebitda addbacks adding and concepts |
| `a653df7` | 2026-06-17 | Hector Corro | fix: EBITDA table enhancements with costs |
| `7f97189` | 2026-06-17 | Hector Corro | fix: P&L table synthesis and enhancement |
| `2dfa110` | 2026-06-17 | Hector Corro | fix: using tmp folder to store word docs |
| `032fadb` | 2026-06-17 | Hector Corro | feature: create md converter script to word |
| `c50a8ec` | 2026-06-17 | Hector Corro | fix: increasing revenue tokens agent |
| `2ff08db` | 2026-06-17 | Hector Corro | feature: financial subagents creation for best assessment |
| `155bf01` | 2026-06-16 | Hector Corro | fix: using sonet for extracting content for financials and reorder schema |
| `989cc39` | 2026-06-16 | Hector Corro | fix: using sonet for extracting content for financials |
| `7d9c167` | 2026-06-16 | Hector Corro | fix: enhancing financial agent for more coverage |
| `a51acb5` | 2026-06-16 | Hector Corro | fix: fixing truncate json from schema for ebitda |
| `b8ec7f5` | 2026-06-16 | Hector Corro | fix: financial reordering schema and truncate problem |
| `e1a687c` | 2026-06-16 | Hector Corro | fix: speeding up retrieval with haiku agents LLM calling |
| `c47e747` | 2026-06-16 | Hector Corro | fix: changing to claude-sonnet and haiku for better performance |
| `afc585c` | 2026-06-16 | Hector Corro | fix: fix regex for CIM and business model truncate token max |
| `4524a99` | 2026-06-16 | Hector Corro | fix: extract page_id from bbox[0] not element root (ai_parse_document v2.0) |
| `6fb9400` | 2026-06-15 | Hector Corro | fix: count only meaningful element types for image-page detection |
| `3068acf` | 2026-06-15 | Hector Corro | fix: detect image-only PDF pages without requiring financial section header match |
| `3f66a29` | 2026-06-15 | Hector Corro | modifying ingestion 2_1 |
| `20a8611` | 2026-06-15 | Hector Corro | refactoring vision model usage |
| `e3c675e` | 2026-06-16 | HecCorro | Adding extras to widget vision |
| `44c4a17` | 2026-06-15 | Hector Corro | refactoring enhancements for retrieval agents |
| `6f39911` | 2026-06-10 | Hector Corro | addin 2_e enhancement for business agent |
| `883a17c` | 2026-06-10 | Hector Corro | addin 2_d enhancement for business agent |
| `ff20bf2` | 2026-06-10 | Hector Corro | addin 2_c enhancement for business agent |
| `40663f5` | 2026-06-10 | Hector Corro | addin 2_b enhancement for business agent |
| `64164fa` | 2026-06-10 | Hector Corro | addin 2_a enhancement for business agent |
| `81d4ed1` | 2026-06-10 | Hector Corro | addin 1st enhancement for business agent |
| `3ee6c10` | 2026-06-10 | Hector Corro | 2_f enhancement of financial agent |
| `ff45340` | 2026-06-10 | Hector Corro | 2_e enhancement of financial agent |
| `7f3c51e` | 2026-06-10 | Hector Corro | 2_d enhancement of financial agent |
| `124acfd` | 2026-06-10 | Hector Corro | 2_c enhancement of financial agent |
| `7f8afbf` | 2026-06-10 | Hector Corro | 2_b enhancement of financial agent |
| `6e71fe4` | 2026-06-10 | Hector Corro | 2_a nd enhancement of financial agent |
| `2c0f0c1` | 2026-06-10 | Hector Corro | 2nd enhancement of financial agent |
| `3d73c93` | 2026-06-10 | Hector Corro | 1st enhancement to financial agent |
| `12af382` | 2026-06-09 | Hector Corro | adding coverage script for all agents |
| `b3bbec9` | 2026-06-08 | Hector Corro | creating more workstream agents |
| `e3ebd9a` | 2026-06-05 | Matt Crysler | Adding a chatbot to the site |
| `087cc0b` | 2026-06-04 | Matt Crysler | Merge branch 'develop' |
| `8f56103` | 2026-06-04 | Matt Crysler | Finalizing changes to AI-first rule creation approach |
| `0ac8b4f` | 2026-06-03 | Hector Corro | fixing financial agents kpis |
| `e2dd2d9` | 2026-06-02 | Hector Corro | adding file download from agent response |
| `6306c68` | 2026-06-02 | Hector Corro | adding 1st draft of bussines and financial agents |
| `2ee1040` | 2026-06-02 | HecCorro | Merge pull request #1 from Nimble-Gravity/setup-databricks-uc13 |
| `b3cfa41` | 2026-06-02 | Hector Corro | Merge develop into setup-databricks-uc13 |
| `62a0a4f` | 2026-06-02 | Hector Corro | modifying logging for connector.py |
| `ca97c3c` | 2026-05-28 | Hector Corro | fixing chunking boundaries |
| `10cb778` | 2026-05-28 | Hector Corro | fixing chunking strategy and ingestion embedding |
| `13035cd` | 2026-05-28 | Hector Corro | ingestion parser fix |
| `957dcad` | 2026-05-28 | Hector Corro | fixing vector search fields |
| `0ca5a05` | 2026-05-28 | Hector Corro | fixing retrieval query |
| `09a0388` | 2026-05-28 | Hector Corro | fixing priority tiers order |
| `a510434` | 2026-05-28 | Hector Corro | modyfing files destination |
| `c7ae3b3` | 2026-05-28 | Hector Corro | adding packages into cluster for doc classifier |
| `b40930b` | 2026-05-28 | Hector Corro | fixing doc prompt and mlflow import |
| `7e2f20a` | 2026-05-28 | Hector Corro | creating schemas if missing |
| `9a413af` | 2026-05-28 | Hector Corro | fixing spark session within python scripts |
| `7916561` | 2026-05-28 | Hector Corro | adding UC volume creation |
| `7d667e2` | 2026-05-28 | Hector Corro | upload bug fixing |
| `710ef5b` | 2026-05-28 | Hector Corro | uploading and connection fixes |
| `0094e72` | 2026-05-27 | Hector Corro | addin dynamic company selection into sharepoint |
| `d3d59fc` | 2026-05-27 | Hector Corro | updating dependencies for cluster |
| `48541a0` | 2026-05-27 | Hector Corro | modyfing dbutils usage |
| `61fefe4` | 2026-05-27 | Hector Corro | modifying testing notebook |
| `4079922` | 2026-05-27 | Hector Corro | renaming scripts for pipeline |
| `8cb3e93` | 2026-05-27 | Hector Corro | modyfing tables for dynamic company selection |
| `6d1b3e2` | 2026-05-27 | Hector Corro | pushing productive scripts |
| `7b191f6` | 2026-05-26 | Matt Crysler | Proceeding with AI-first rule definition approach |
| `ee33d42` | 2026-05-26 | Matt Crysler | Adding a search bar for rules |
| `1dff51a` | 2026-05-26 | Matt Crysler | Updating the display of the AI rule rows |
| `9cca922` | 2026-05-26 | Matt Crysler | Implementing first pass NL rule creation with AI generation |
| `f35adc0` | 2026-05-22 | Matt Crysler | Beginning company view for assigned companies in the garden |
| `8f77543` | 2026-05-21 | HecCorro | feature: agents notebook creation and first retrieval techniques |
| `987d773` | 2026-05-20 | Matt Crysler | Implementing initial set of APIs for rules table |
| `8704b3b` | 2026-05-19 | HecCorro | feat: complete phase 1 - full corpus ingested 1241 files |
| `ebd25c2` | 2026-05-19 | HecCorro | fix: pdf to_json fix, excel batching, company-scoped volume path |
| `27076eb` | 2026-05-19 | HecCorro | fix: update notebook with to_json pdf fix |
| `18e682a` | 2026-05-18 | Hector Corro | feat: company scoping, deduplication and excel chunking fix |
| `9e70e9e` | 2026-05-18 | HecCorro | feat: listing files from sharepoint |
| `6ad2dfc` | 2026-05-18 | Matt Crysler | Adding app.yml file for databricks |
| `edf4137` | 2026-05-18 | HecCorro | feat: add parse and index notebook phase 1 |
| `58cd2f7` | 2026-05-18 | Hector Corro | feat: swap connector auth to client credentials flow |
| `fbf2328` | 2026-05-18 | Matt Crysler | Initial frontend concept |
| `142a1ee` | 2026-05-15 | Hector Corro | feat: add ingestion tools - connector and uploader |
| `9328ed2` | 2026-05-14 | Matt Crysler | Initial commit |
| `c45692c` | 2026-05-07 | Matt C | Initial commit |

---

## Commit Message Patterns

| Pattern | Count | Interpretation |
|---------|-------|----------------|
| `fix:` / `fixing` | ~35 | Iterative hardening dominates — especially ingestion, tokens, financial extraction |
| `feat:` / `feature:` | ~12 | New capabilities (ingestion phases, sub-agents, md_to_word) |
| `addin` / `adding` / `Adding` | ~15 | Incremental agent enhancements (often numbered 2_a–2_f) |
| `refactoring` | 2 | Structural cleanup (vision, retrieval) |
| Merge commits | 4 | Branch integration (PR #1, develop syncs) |

---

## Related Documentation

| Doc | Path |
|-----|------|
| Monorepo README | `README.md` |
| UC13 pipeline developer guide | `databricks/CLAUDE.md` |
| Workflow deployment guide | `databricks/workflows/README.md` |
| Architecture index (untracked) | `.dev/architecture/rallyday/INDEX.md` |
| Open product questions | `.dev/architecture/rallyday/open-questions.md` |

---

## Suggested Next Steps (ordered)

1. **Merge decision** — reconcile feature branch with develop (chatbot conflict).
2. **Validate FTA sub-agents** — run full `test_pipeline.ipynb` on a second company.
3. **Deepen non-financial agents** — apply BMA/FTA iteration pattern to CQA, Legal, QoE.
4. **Product seam** — define API/UI for surfacing `uc13.analysis.*` in Garden.
5. **Rule execution** — specify runtime for `python_source` rules against `opportunity_silver`.
