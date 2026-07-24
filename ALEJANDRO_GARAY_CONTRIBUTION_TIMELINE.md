# UC-13 Pipeline — Work History & Handoff Guide

> **Audience:** Hector Corro and anyone rejoining the UC-13 codebase.  
> **Author / maintainer of this doc:** Alejandro Garay  
> **As of:** 2026-07-24  
> **Sources:** `git log --all`, `CHANGELOG.MD`, `my_runbook.md`, scorecards, milestone plans, cluster attestations.

---

## For Hector — start here (~5 min)

This repo is **your ingestion + agent foundation** (May–Jun) plus **a month of hardening, eval, orchestration, and reporting** on top (Jun 23 – Jul 24). Nothing was thrown away — the pipeline still runs through `test_pipeline.ipynb`, the same agent entrypoints, and the same UC tables you defined. The biggest deltas are: **legal agent architecture**, a new **orchestrator/reporting layer**, a full **retrieval eval harness**, and **production safety rails** (index sync, catalog convention, tests).

### Repo state today

| Item | Value |
|------|-------|
| **Branch to use** | `dev` (tracks `origin/dev`) |
| **HEAD** | `93f3462` — 2026-07-24 |
| **Catalog (eval / notebook)** | `uc13_ale` |
| **Catalog (production agent default)** | `uc13` — enforced by `tests/test_catalog_convention.py` |
| **Pytest** | **757 passed, 5 skipped** (post-merge, 2026-07-24) |
| **Harness control baseline** | `baseline_1aeb0ace584a` (do not cross-compare to `baseline_299063e87806` — registry hash changed) |
| **Notebook** | `databricks/jobs/notebooks/test_pipeline.ipynb` — still the production path |

### What you built (foundation · May 7 – Jun 19)

| Area | Your contribution |
|------|-------------------|
| **Ingestion** | SharePoint connector, UC Volume upload (1,241 files), classifier, parser 2.1, vision OCR, `ensure_coverage.py` |
| **Agents** | FTA + BMA deep iteration, financial sub-agents (revenue/EBITDA/OPEX), scaffolds for CQA/KPI/Legal/QoE |
| **Infra** | Vector search setup, workflow YAML, `agent_base.py`, `retrieval.py` (original), `company_profiler.py` |
| **Last commit on feature branch** | `1aed882` — 2026-06-19 — *fix: financial subagents and kpis retrievers* |

Full narrative: `.dev/PROJECT_HISTORY.md` (snapshot from 2026-06-20).

### What was added on top (Jun 23 – Jul 24 · Alejandro)

| Track | Outcome |
|-------|---------|
| **Retrieval & eval** | `eval/retrieval/` package — RouteResult API, 49-intent registry, gold labels, harness CLI, provenance, baselines, ablation |
| **Legal agent** | Multi-pass domain extraction (M0–M3), `analysis.legal` DDL, stakeholder `legal_report.yaml`, golden checklist — now **9/11** |
| **Orchestrator** | Bundle schema, `BundleBuilder`, Stage-6 LLM synthesis, TL;DR compression, full report + DOCX |
| **Pipeline hardening (PHV)** | Fail-closed index sync, `dev` merge, catalog convention, retrieval consolidation |
| **Executive summaries** | 4/4 companies; Rainmaker Rev2/Rev3 merged to `dev` (Jul 24) |
| **Eval harness (all agents)** | Golden checklists for all 7 agents, `evaluate_promotion` gate, first scored baselines |
| **Tests** | Grew from ad-hoc to **757** pytest cases + pyspark stubs / `pytest.ini` fix |

**Commit split (repo-wide):** Hector ~75 · Alejandro ~245 · Matt ~10.

---

## Changes to code you authored

These are the highest-signal diffs when re-reading your modules.

| Your file / area | What changed | Why |
|------------------|--------------|-----|
| `retrieval.py` | Returns `RouteResult` (not `list`); merge-rank; VS `company_name` pushdown; optional `vs_metadata_filters` (off); `intent_id` + provenance hook | Measurable retrieval + observability; default path behavior preserved when flags off |
| `context_utils.py` | `semantic_search_with_fallback` delegates to shared `fallback.py`; OPEX per-query budgets `(8k/3k/4k)`; labeled sections | FTA context assembly + PHV4 consolidation |
| `financial_trends_agent.py` + sub-agents | `open_agent_run` wiring; explicit `intent_id` on retrieval; `basis_cross_check`; ThreadPoolExecutor `contextvars` fix | Provenance + parallel sub-agent safety |
| `legal_contracts_agent.py` | **Major rewrite** — 5 domain passes, tri-state merge, Option-C flags, dual-write YAML; Jul 24 restrictive-covenant merge fix | Spec-aligned stakeholder report; checklist 7/11 → **9/11** |
| `business_model_agent.py` (+ 4 others) | Removed `_CATALOG` shadows; `catalog` threaded through `run()` | PHV3 catalog convention |
| `ingestion_parser.py` | `IndexSyncError` — parser **halts** if vector index sync fails | PHV1 — no silent stale-index retrieval |
| `uc13_ingestion_pipeline.yml` | Dropped `00_`–`04_` prefixes; legal depends on profiler; catalog default `uc13_ale` | PHV3 workflow hygiene |
| `test_pipeline.ipynb` | Cells for orchestrator (18–19), eval arms (1a), halt-on-failure docs, profiler linkage | E2E + attestation surface |
| `md_to_word.py` | Used by orchestrator DOCX export (unchanged API) | Stakeholder deliverables |
| **New (didn't exist)** | `eval/retrieval/*`, `databricks/agents/orchestrator/*`, `databricks/agents/shared/fallback.py` | Eval harness + reporting layer |

**Route A (`route_chunks.py`):** Built for A/B eval Jun 23–25, then **removed from production** — semantic + merge-rank won the scorecard.

---

## Elder Care agent scores (current)

| Agent | Checklist | Score | Last verified |
|-------|-----------|-------|---------------|
| FTA | 18-field golden | **16/18** | 2026-07-16 post-PHV4 |
| Legal | 11-item golden | **9/11** | 2026-07-24 (restrictive merge fix) |
| BMA | Golden checklist | **7/7** | 2026-07-21; checklist reconciled 2026-07-24 |
| CQA | Golden checklist | **3/6** | 2026-07-21 `baseline_bootstrap` |
| KPI | 3-row checklist | **3/3** | 2026-07-21 |
| QoE | Golden checklist | **5/6** | 2026-07-21 |
| Profiler | Golden checklist | **7/7** | 2026-07-21 |

**Clearsulting (2nd company):** FTA 16/18; Legal 0/11 (thin data room — expected gap behavior).

Scorecards: `.dev/scorecards/INDEX.md` · Legal 9/11: `.dev/scorecards/scorecard_lca_7_24_post_restrictive_fix_vs_7_16.md`

---

## Open work & collaboration points

| Item | Status | Notes |
|------|--------|-------|
| **Data room completeness score** | **Next up** (Phase 7) | Design preflight — map `doc_relevance` / `ensure_coverage` to a single completeness metric |
| **Metadata filter activation** | Deferred | `vs_metadata_filters` built but off — PG5 A/B failed Jul 15 |
| **Shared context assembly (PHV4 item 28)** | Deferred | OPEX pooling still agent-local |
| **`workstream_tags.py` centralization (item 30)** | Deferred | |
| **Garden UI / Genie chatbot** | Product decision | Chatbot on `develop` only; analysis not wired to UI |
| **Your parallel repo / branch inventory** | Phase 9 pending | `my_runbook.md` — merge after baseline stability (now stable on `dev`) |
| **Cell 7 full ingestion rebuild** | Qualified pass | Smoke attestation deferred full rebuild (serverless OOM on 382-file vision parse) |

Alejandro's operational checklist: `my_runbook.md` (session log through 2026-07-24).

---

## Quick reference — where to read

| Question | Go to |
|----------|-------|
| How do I run the pipeline? | `databricks/CLAUDE.md` + `test_pipeline.ipynb` Cell 1 widgets |
| What changed milestone-by-milestone? | `CHANGELOG.MD` (19 program sections) |
| Harness / baselines / promotion gate? | `eval/retrieval/README.md` |
| Architecture / coupling surfaces? | `.dev/architecture/rallyday/` |
| Legal restrictive covenant debug? | `legal-restrictive-covenant-brief-2026-07-16.md` |
| Baseline re-attestation story? | `harness-baseline-2026-07-15.md` |
| PHV / eval audits? | `.dev/audits/2026-07-16-*.md`, `.dev/audits/2026-07-21-*.md` |

---

## Quantitative snapshot

| Metric | Value |
|--------|-------|
| Alejandro commits (Jun 23 – Jul 24) | **~245** |
| Hector commits (repo total) | **~75** |
| Files changed vs `1aed882` | **277 files**, +97,974 / −25,470 lines (repo-wide) |
| Core dirs (`databricks/`, `eval/`, `tests/`) | **128 files**, +88,252 / −1,775 lines |
| Pytest cases | **757** passed (2026-07-24) |
| Workstream agents | **7** |
| Intent registry | **49** retrieval intents |
| Companies with executive summaries | **4** |
| Active branch | **`dev`** |

### Daily commit density

```
Jun 23 ████████  8     Jul 06 ██████    6 (+1 Ale)
Jun 24 ████████  8     Jul 07 ████████████ 12
Jun 25 ████      4     Jul 08 █████     5
Jun 26 ██████████████████ 18   Jul 09 ██████    6
Jun 29 █████████████████████ 21   Jul 10 ██        2
Jun 30 ████████████████████████████ 28   Jul 12 █         1
Jul 01 ██████████████ 14   Jul 14 ███████   7
Jul 02 ███████████████████ 19   Jul 15 ███████   7
Jul 03 ██████████ 10   Jul 16 ██        2
                      Jul 17 ███████   7
                      Jul 18 █████     5
                      Jul 20 ███████████ 11
                      Jul 21 ████████████████████████████ 28
                      Jul 22 █████     5
```

---

## Milestone Map

Chronological program milestones (each has detailed entries in `CHANGELOG.MD`):

| # | Milestone | Dates | Theme |
|---|-----------|-------|-------|
| 1 | **uc13-remediation-plan** | Jun 23–25 | Route A/B retrieval eval, VS schema alignment, FTA golden checklist |
| 2 | **uc13-m0** — Legal platform setup | Jun 25–26 | `analysis.legal` Delta DDL, catalog threading, workflow rewire |
| 3 | **uc13-m1** — Legal multi-pass extraction | Jun 26 | 5 domain passes, Sonnet enforcement, E2E exit gate |
| 4 | **uc13-m2** — Legal flags/gaps/stakeholder | Jun 26 | Option-C flags, gap assessment, dual-write YAML reports |
| 5 | **uc13-m3** — Legal closure | Jun 29 | Golden checklist G3, presentation summary, POC delta |
| 6 | **uc13-orchestrator-m1** — Demo E2E | Jun 29 | Bundle schema, populate/validate, Jinja templates, DOCX |
| 7 | **uc13-tldr-compression** | Jun 30 | `compress_for_tldr`, compressed template, quality-check CLI |
| 8 | **uc13-orchestrator-m2** — BundleBuilder MVP | Jun 30 | Deterministic builder, ConfidenceEngine, Stage-6 synthesis |
| 9 | **uc13-m-re1** — Eval foundation | Jul 1 | RouteResult API, EvalStore, gold bootstrap, harness |
| 10 | **m-re2** — Observability & FTA context | Jul 2–3 | Provenance, run context, OPEX budgets, Delta concurrency fixes |
| 11 | **m-re3** — Core hardening | Jul 3–6 | VS filter pushdown, ablation matrix, shared fallback, re-baseline |
| 12 | **uc13-m-phv1** — Pipeline gates | Jul 6–7 | `IndexSyncError` fail-closed, halt-on-failure sync |
| 13 | **repo-test-baseline-hygiene** | Jul 7 | pytest.ini, pyspark stubs, sqlite baseline flakiness fix |
| 14 | **uc13-m-phv2** — Validation expansion | Jul 7–8 | All 7 agents smoke, Clearsulting 2nd company, E2E attestations |
| 15 | **uc13-m-phv3** — Integration | Jul 8–14 | Fast-forward `origin/dev`, catalog convention, post-merge smoke |
| 16 | **uc13-m-phv4** — Retrieval consolidation | Jul 14–16 | `_TYPE_ORDER` dedup, FTA/harness fallback unification, R-08 join integrity |
| 17 | **uc13-exec-summary-wed-sprint** | Jul 17–20 | Expanded synthesis v1.0→v1.3, 4/4 company TL;DRs |
| 18 | **uc13-eval-harness-all-agents** | Jul 21 | Golden checklists M1–M2, promotion gate M3, first scored runs M4 |
| 19 | **uc13-exec-summary-wed-sprint-rev2/rev3** | Jul 22–24 | Rainmaker restructure; Rev3 merged to `dev` |
| 20 | **Legal restrictive fix + BMA F2** | Jul 24 | Legal **9/11**; BMA checklist reconciled to 7/7 |

---

## Chronological Timeline

### Phase 0 — Hector's foundation (May 7 – Jun 19)

Matt bootstrapped the Garden app; **Hector built the UC13 ingestion stack and agents** on a parallel branch merged via PR #1 (2026-06-02). Six weeks of agent hardening followed — especially FTA (vision OCR, sub-agents, EBITDA/P&L schema, token truncation fixes). Feature branch ended at `1aed882` (2026-06-19). Alejandro's continuation begins **four days later** (Jun 23).

---

### Phase 1 — Retrieval remediation & eval arms (Jun 23–25)

**Goal:** Fix retrieval quality for FTA; establish A/B evaluation methodology before agent rewrites.

| Date | Key work |
|------|----------|
| **Jun 23** | Program kickoff — remediation plan docs; **Route A** (`route_chunks.py` SQL metadata router); **Route B** enhancements to `retrieval.py` (VS filter pushdown, merge-rank, SQL escaping); wire `retrieval_mode` through FTA `context_utils` adapter |
| **Jun 24** | FTA corpus-stats Cell 8f + Elder Care prerequisites; filename-filter parity fix (RA); frozen two-arm eval protocol + scorecard template (RB); Cell 1a arm-switch helper (RUX); three-arm run prep (control / semantic / routed) |
| **Jun 25** | Snapshot table for report versioning/traceability; **pivot to Legal agent**; Elder Care A0 corpus baseline (T1); legacy legal baseline capture before DDL migration (T2) |

**Outcome (RT7 scorecard, Jun 25):** Route A disqualified (1/18 — wrong subsidiary docs). Route B (`semantic`, 15/18) vs Control (16/18): merge-rank caused OPEX basis mismatch but richer exec summary. **Decision:** lock FTA to enhanced `semantic_search`; OPEX is a context-ranking fix, not a retrieval defect.

**Key files created:** `databricks/agents/shared/route_chunks.py`, `databricks/agents/shared/_types.py` (`RouteResult`), `tests/test_route_chunks.py`, `.dev/plans/uc13-remediation-plan/scorecard.md`

---

### Phase 2 — Legal agent rebuild M0–M3 (Jun 25–29)

**Goal:** Replace monolithic legal extraction with spec-aligned multi-pass pipeline and stakeholder-ready output.

#### M0 — Platform setup (Jun 25–26)

- Migrated storage to `analysis.legal` Delta table + `legal_contracts` compat VIEW
- Threaded runtime `catalog` through `LegalContractsAgent` (removed module-level `_CATALOG`)
- Workflow catalog default → `uc13_ale`; Cell 18 summary loop branches for legal tables
- Architecture docs + `databricks/CLAUDE.md` catalog row

#### M1 — Multi-pass retrieval & extraction (Jun 26)

- `_DOMAIN_PASSES` loop (5 spec §5.11 passes) replacing monolithic 6-retrieval path
- Per-pass retrieval with A0-tuned filename filters + `catalog`-threaded fallback
- Per-pass extraction prompts/schemas; `extraction_endpoint` with Sonnet override for Haiku/Llama
- **Exit gate:** 10 domain trace steps, Delta row in `uc13_ale.analysis.legal`, Volume report written

#### M2 — Flags, gaps, stakeholder report (Jun 26)

- Tri-state helpers (`_is_true`, `_is_not_found`), `_merge_registers`, roll-up migration
- Option-C MVP flags (`coc_consent_required`, `restrictive_covenant`, etc.)
- `_assess_coverage_gaps`, `_compute_section_confidence`, executive summary builder
- Dual-write: normative `legal_report.yaml` + legacy `legal_contracts_report.yaml`
- **Exit gate:** `section_confidence=high`, 8 flags, 4 unable-to-assess items, Volume dual-write verified

#### M3 — Schema guard, tests, E2E closure (Jun 29)

- Inline schema guard in `main()` (FTA pattern); runtime behavioral tests for helpers/merge/flags
- Elder Care E2E dual compare + POC delta (4 `unable_to_assess` items traced to corpus/retrieval gaps)
- Golden checklist **7 pass · 4 gap-correct** (11 rows); presentation summary for stakeholders
- Volume YAML post-E2E verification (normative 22,300 bytes, 12/12 outline keys)

**Scores held:** Legal **7/11** on Elder Care through Jul 16; improved to **9/11** on Jul 24 after restrictive-covenant merge fix (see `legal-restrictive-covenant-brief-2026-07-16.md`).

---

### Phase 3 — Orchestrator & stakeholder reporting (Jun 29–30)

**Goal:** Unified bundle from all agent outputs → full report + compressed TL;DR one-pager.

#### M1 — Demo E2E (Jun 29)

| Component | Deliverable |
|-----------|-------------|
| Schema | `orchestrator_bundle.schema.yaml` (draft-07, closed `meta.agents_present`) |
| Ingest | `ingest_snapshots()` — latest Delta row per agent + Volume YAML fallbacks |
| Populate | `populate_bundle()`, `validate_bundle()` (jsonschema HALT), confidence engine |
| Templates | `full_report.md.j2`, `tldr_one_pager.md.j2` (Appendix C section order) |
| Render | `renderers.py` — Jinja2 → Volume MD; DOCX via `md_to_word` |
| Demo | `demo_walkthrough.py` — 7 stdout gates for cluster verification |

Cluster fixes during M1: LLM merge structural restore (list-of-dict preservation), freshness datetime normalize (UTC-aware).

#### TL;DR compression (Jun 30)

- `tldr_compress.py` — `compress_for_tldr()` (headline, financial strip, gap filter, QoE collapse, risk dedupe)
- `tldr_one_pager_compressed.md.j2` — spec §6 section order
- `TLDR_RENDER_MODE` env switch (compressed vs legacy)
- `tldr_quality_check.py` — soft gates (word count, dict-leak, operator-gap vocabulary)
- **Cluster result:** Elder Care **2,354 → 730 words**; all quality gates PASS
- Polish passes T8–T12b: headline dollar regex, In One Line dedup, risk display titles, margin disambiguation

#### M2 — BundleBuilder MVP (Jun 30)

- `field_mapping.py` — 17-row Appendix B mappings
- `ConfidenceEngine` — per-area rules, `medium_low` composite, min-area-wins
- `BundleBuilder.build()` — deterministic stages 0–8 (ingest → map → flags → gaps → confidence → fill_state → validate → persist)
- `GapAggregator` — §5.6.2 dedupe, diligence top-8
- Stage-6 executive synthesis default-on when `llm_endpoint` set
- Cell 19 production path + render cell gate (`ORCHESTRATOR_USE_BUILDER=1`)
- Elder Care pytest fixtures + G4 builder verification (84 scoped tests passed)

---

### Phase 4 — Retrieval eval harness RE¹–RE³ (Jul 1–6)

**Goal:** Measurable, repeatable retrieval quality with baselines, provenance, and ablation tooling.

#### M-RE1 — Foundation (Jul 1)

| Module | Purpose |
|--------|---------|
| `eval/retrieval/_types.py` | Pydantic v2 models, frozen `RouteResult` contract |
| `eval/retrieval/store.py` | `SqliteEvalStore` + `DeltaEvalStore`, ops DDL |
| `eval/retrieval/harness.py` | `EvalHarness.run/compare/validate_baseline_ref` |
| `eval/retrieval/gold/bootstrap.py` | Two-pass gold label bootstrap |
| `eval/retrieval/intent_registry.yaml` | 49 intents across 9 agent partitions |
| `eval/retrieval/harness_cli.py` | Frozen CLI for baseline/ablation runs |
| `semantic_search()` | Migrated to `RouteResult` with mode (`semantic`/`keyword`/`empty`) + scores |
| Route A | **Removed** from production; wrappers migrated to `RouteResult.chunks` |

Gold labels: `eval/retrieval/gold_labels/elder_care.yaml` (49 intents, 3 ready exemplars). CI fixture: `fixtures/elder_care_slice.json`.

#### M-RE2 — Observability & FTA context (Jul 2–3)

- `run_context.py` — `open_agent_run`/`close_agent_run`, pipeline manifest schema
- `provenance.py` — `ProvenanceEmitter`, per-retrieval provenance rows in Delta
- OPEX per-query budgets `(8000, 3000, 4000)` + labeled context sections
- `basis_cross_check` — projection vs historical mismatch detection
- Context allocation provenance patch (`chars_allocated`/`context_section`)
- Pipeline agent run wiring on all 6 workstream `main()` entrypoints
- `record_e2e_linkage` CLI — links harness runs to agent checklist scores

**Production fixes (cluster-discovered):**
- `apply_ops_ddl.py` additive Delta column migration (`DELTA_METADATA_MISMATCH`)
- FTA `ThreadPoolExecutor` losing `contextvars` → provenance silent no-op (fixed with `copy_context`)
- Concurrent Delta MERGE contention → retry-with-backoff + batched OPEX patch + write lock

**E2E result:** FTA **16/18** on Elder Care (ties Control); M-RE2 Item 23 gate PASS.

#### M-RE3 — Core hardening (Jul 3–6)

- VS filter pushdown probe — all 11 `filters_json` candidates PASS on cluster
- `vs_metadata_filters` capability (gated off by default)
- Shared `fallback.py` for BMA/Legal filename-filter retry
- Ablation dispatch — 4 merge-rank arms (`sim_tier`, `off`, `sim_only`, `tier_only`)
- Promoted control baseline **`baseline_299063e87806`** → later **`baseline_1aeb0ace584a`**
- Ablation: `merge_rank_on` gate_pass=true; alt arms deliberately fail (proves merge-rank earns its keep)

---

### Phase 5 — Pipeline hardening PHV1–PHV4 (Jul 6–16)

**Goal:** Make the merged pipeline safe to run in production; integrate with `dev`; consolidate retrieval.

#### M-PHV1 — Pipeline gates (Jul 6–7)

- `IndexSyncError` — parser **halts** on vector index sync failure (no stale-index continuation)
- `_wait_for_index_sync` — `max_wait_seconds=1800`, terminal FAILED/CANCELED → raise
- Unit tests for fail-closed paths in `main()` and `ensure_coverage.ingest_missing()`
- `databricks/CLAUDE.md` exit-gate runbook; Cell 7/8d halt-on-failure docs
- Locked Cell 1 `llm_endpoint` default to `databricks-claude-sonnet-4-6`

#### Repo test baseline hygiene (Jul 7)

- Fixed `pytest.ini` comma bug (`pythonpath` parsed as broken tokens on Windows)
- Root `conftest.py` — comprehensive `pyspark` stubs (distinct scalar types)
- `SqliteEvalStore.get_latest_baseline` — `rowid DESC` tie-break fix
- Skip guards on gitignored legal eval fixtures
- **Result:** 12 failed → **0 failed, 454 passed, 10 skipped**

#### M-PHV2 — Validation expansion (Jul 7–8)

- PHV validation runbook + 7-agent matrix in `eval/retrieval/README.md`
- Scorecard index schema (`.dev/scorecards/INDEX.md`) — 9-column header, FTA/Legal backfill
- 14 agent scorecards (7 agents × 2 companies: Elder Care + Clearsulting)
- E2E linkage attestation — 4 `record_e2e_linkage` rows (FTA/Legal × 2 companies)
- Second company: **Clearsulting** (Legal 0/11 — thin data room, gap-correct)
- **FTA 16/18 · Legal 7/11** held through validation

#### M-PHV3 — Integration (Jul 8–14)

- Pre-merge verification (Item 19 PASS) — Genie parity, no divergent commits
- **Fast-forward `origin/dev` to `dev2` HEAD** (2026-07-09)
- Legal agent catalog default corrected to `uc13` (production convention)
- Removed `_CATALOG` shadow constants from 5 workstream agents
- `tests/test_catalog_convention.py` — §5.12.3 static enforcement (44 tests)
- Post-merge Elder Care smoke **PASS (qualified)** — Cells 0/1/8b/8/10/11; Cell 7 full rebuild deferred (serverless OOM)
- Workflow YAML path hygiene (dropped `00_`–`04_` numbered prefixes)
- Second PG2 push to `origin/dev`

#### M-PHV4 — Retrieval consolidation (Jul 14–16)

| Item | Change |
|------|--------|
| R-09 | `_TYPE_ORDER` canonical constant in `retrieval.py` (deduped from `context_utils`) |
| R-03 | FTA `semantic_search_with_fallback` → thin delegator to `fallback.py` |
| R-03 | Harness `dispatch_retrieval` unified on shared fallback (Surface 11) |
| R-08 | Join-integrity preflight test + README orphan-count SQL |
| R-02 | VS metadata filters A/B — **not activated** (PG5 numeric bar fail: max drop 5.88pp `legal.litigation`) |
| Audit | Hardened `semantic_search` inventory matcher; legal intent registry fix |

**PG4 closure (Jul 16):** Promoted `baseline_1aeb0ace584a`; FTA re-score **16/18**; Legal **7/11** CONDITIONAL PASS; 558 unit tests passed.

**Operator debug (Jul 15):** Stale VS index + `legal.insurance` registry/classifier mismatch (`BACKGROUND` vs `LEGAL` filter) — documented in `harness-baseline-2026-07-15.md`.

---

### Phase 6 — Executive summary sprint (Jul 17–20)

**Goal:** Production-quality one-pagers for all 4 portfolio companies with expanded LLM synthesis.

**Branch:** `feat/exec-summary-expanded-synthesis` (cut from `dev-exec-summ`)

| Version | Changes | Elder Care validation |
|---------|---------|----------------------|
| **v1.0** | H1 rename TL;DR → **Executive Summary**; Stage-6 fields: `business_snapshot_narrative`, `mitigants_digest`, `confidence_rationale` | ACCEPT (1,703 words, +378 vs baseline) |
| **v1.1** | PE mitigation-strategy prompt; 3-col Top Risks; KPI dict-repr fix; section header rename | ACCEPT (2,061 words) |
| **v1.2** | 5 digest lead-ins (`legal_digest`, `qoe_digest`, etc.); presentation pass (de-truncate, coverage %, 2-col KPI) | ACCEPT partial (legal_digest abandoned — contradicts detail) |
| **v1.3** | Whole-bundle overview + `[Section Tag]` citations; dropped 4 per-section digests; deterministic citation resolver | ACCEPT (2,264 words) |

**T7 sequence:** Clearsulting (1,734w) → GKF (1,965w) → SPG (1,894w) — all ACCEPT.  
**T9 assembly:** **4/4 expanded** executive summaries; zero baseline fallbacks; Volume `tldr_one_pager.md`/`.docx` verified.

Merged to `dev` at `d06992a` (2026-07-20).

---

### Phase 7 — Eval harness for all agents (Jul 21)

**Goal:** Extend FTA/Legal golden-checklist pattern to all 7 agents; promotion gate for baseline management.

#### M0 — Instrumentation

- Generalized `record_e2e_linkage` CLI for all 7 agents
- Profiler pipeline-run tracking
- Deterministic fixture tests: BMA revenue-durability, CQA thresholds, KPI overlay-selection, QoE downstream-math

#### M1 — Golden checklists (BMA, CQA, KPI, Profiler)

- `GOLDEN_CHECKLIST_COVERAGE` constants per agent
- Elder Care checklists: BMA, CQA (eval dirs), KPI (3 rows), Profiler
- Parameterized structural harness hub (`CHECKLIST_CASES`)

#### M2 — QoE golden checklist

- QoE Elder Care checklist + precondition-gate test fixture (`_load_addback_passthrough`)
- FTA addback precondition-gate procedure documented

#### M3 — Promotion gate

- `PromotionResult` dataclass + waiver-ID validator
- `select_prior_e2e_baseline()` — checklist-regression baseline helper
- `evaluate_promotion()` — gate decision logic with H1-R write-on-promote invariant
- Program Gate G3 test suite

#### M4 — First scored runs

| Agent | Score | Gate |
|-------|-------|------|
| BMA | **7/7** | `baseline_bootstrap` |
| KPI | **3/3** | `baseline_bootstrap` |
| QoE | **5/6** | `baseline_bootstrap` |
| Profiler | First scored baseline | `evaluate_promotion` |
| README | Unified 7-agent rewrite | Program Gate G4 |

---

### Phase 8 — Rainmaker executive summary Rev 2 & Rev 3 (Jul 22–24) · **DONE**

**Branches:** `feat/exec-summary-rainmaker-restructure` → merged to `dev` 2026-07-24

| Rev | Changes | Elder Care validation |
|-----|---------|----------------------|
| **Rev 2** | `thesis_bullets`, `key_watchouts`, `workforce_notes`; Bucket A restructure (KPI fold, removed standalone Legal/QoE/KPI sections) | ACCEPT — 2,346 words |
| **Rev 3** | Stage-6 prompt + compressed template aligned to Rainmaker section order (8 H2s); Analysis Notes as prose paragraph | ACCEPT — **1,344 words** |

### Phase 9 — Post-merge closeout (Jul 24)

- Merged `dev2` + Rainmaker branch into `dev`; pushed to `origin/dev`
- Legal Cell 16 re-score: **9/11 PASS** (restrictive covenant merge fix)
- BMA golden checklist reconciled to M4 **7/7** (audit F2 closed)
- Full suite: **757 passed, 5 skipped**

---

## Deliverables Matrix

### Production code (primary)

| Area | Key modules / paths |
|------|---------------------|
| Retrieval core | `databricks/agents/shared/retrieval.py`, `fallback.py`, `context_utils.py` |
| Legal agent | `databricks/agents/workstreams/legal_contracts_agent.py` |
| Orchestrator | `databricks/agents/orchestrator/` — `bundle_builder.py`, `populate.py`, `tldr_compress.py`, `renderers.py`, `field_mapping.py`, `confidence.py` |
| Templates | `orchestrator/templates/full_report.md.j2`, `tldr_one_pager_compressed.md.j2` |
| Ingestion safety | `databricks/jobs/scripts/ingestion_parser.py` (`IndexSyncError`) |
| Eval harness | `eval/retrieval/` — full package (harness, store, provenance, gold, CLI) |
| Formatters | `databricks/agents/orchestrator/formatters.py`, `tldr_quality_check.py` |
| Tests | `tests/` (32 files), `eval/retrieval/tests/` (18 files) |

### Evaluation artifacts

| Artifact | Location |
|----------|----------|
| FTA golden checklist (18 fields) | `.dev/plans/uc13-remediation-plan/` + scorecards |
| Legal golden checklist (11 items) | `eval/LCA/golden_checklist_elder_care.md` |
| BMA/CQA/KPI/QoE/Profiler checklists | `eval/{BMA,CQA,KPI,QOE,PROFILER}/golden_checklist_elder_care.md` |
| Scorecard index | `.dev/scorecards/INDEX.md` |
| Intent registry | `eval/retrieval/intent_registry.yaml` (49 intents) |
| Gold labels | `eval/retrieval/gold_labels/elder_care.yaml` |
| Harness baselines | `uc13_ale.ops.retrieval_harness_*` (Delta); promoted `baseline_1aeb0ace584a` |
| Ablation evidence | `ablation_test_roll_up_by_arm.csv`, etc. |

### Stakeholder outputs (4 companies)

| Company | Executive summary | Status |
|---------|-------------------|--------|
| Elder Care | `tldr_one_pager.md` / `.docx` on UC Volume | Rainmaker **Rev 3** ACCEPT (1,344w); merged to `dev` |
| Clearsulting | Volume artifacts verified | Expanded synthesis ACCEPT |
| GKF | Volume artifacts verified | Expanded synthesis ACCEPT |
| SPG | Volume artifacts verified (71,010 chunks) | Expanded synthesis ACCEPT |

### Documentation & runbooks

| Doc | Purpose |
|-----|---------|
| `CHANGELOG.MD` | Milestone-tier changelog (primary audit trail) |
| `databricks/CLAUDE.md` | Pipeline developer guide, catalog convention, exit gates |
| `eval/retrieval/README.md` | Harness ops, PHV validation matrix, R-02 A/B, join integrity |
| `my_runbook.md` | Operator checklist + session log (Alejandro; useful for cluster reruns) |
| `project_status_timeline.md` | PM-facing summary (stale as of 2026-07-13 — see this doc + `my_runbook.md` for current state) |
| `harness-baseline-2026-07-15.md` | Baseline re-attestation debug log |
| `legal-restrictive-covenant-brief-2026-07-16.md` | Legal agent fix brief |
| `AGENTS.md` | Agent instructions for Cursor/Claude |
| `.dev/PROJECT_HISTORY.md` | Pre-handoff repo narrative (Jun 20 snapshot) |
| `.dev/architecture/rallyday/` | Architecture reference folder (module map, contracts, coupling surfaces) |
| `.dev/plans/` | Per-milestone orchestrator plans (PHV, exec-summary, eval-harness) |
| `.dev/decision-logs/` | Architectural decision records per subtask |

---

## Agent Scorecard Summary (Elder Care) — see also top section

| Agent | Checklist | Score | Notes |
|-------|-----------|-------|-------|
| FTA (Financial Trends) | 18-field golden | **16/18** | Held from M-RE3 through PHV4 re-score (Jul 16) |
| Legal (LCA) | 11-item golden | **9/11** | Jul 24 post restrictive-merge fix (was 7/11 CONDITIONAL Jul 16) |
| BMA | Golden checklist | **7/7** | Baseline Jul 21; checklist file reconciled Jul 24 |
| KPI | Golden checklist (3 rows) | **3/3** | First scored baseline Jul 21 |
| QoE | Golden checklist | **5/6** | First scored baseline Jul 21 |
| CQA | Golden checklist | **3/6** | `baseline_bootstrap` Jul 21 |
| Profiler | Golden checklist | **7/7** | Pipeline-run tracking added Jul 21 |

**Clearsulting (2nd company):** FTA 16/18; Legal **0/11** (thin data room — all gaps, not agent failure).

---

## Branch & Integration History (Jul 24)

```
main ───────────────────────────── (stale)
  │
develop / dev ─── PR#1 (Jun 2, Hector) ─── Matt chatbot (Jun 5)
  │
feature/databricks-financial-bussines-agents ─── Hector last 1aed882 (Jun 19)
  │
  ├── [Jun 23 – Jul 24: hardening, eval, orchestrator, PHV, exec summary]
  │
dev2 ─── PHV + eval-harness (merged into dev Jul 24)
  │
feat/exec-summary-* ─── merged into dev Jul 24
  │
dev  ←── CURRENT (HEAD 93f3462, tracks origin/dev)
```

---

## Current State (2026-07-24)

| Dimension | State |
|-----------|-------|
| **Active branch** | `dev` (synced with `origin/dev`) |
| **Latest commit** | `93f3462` — *Restore git merge session log row in runbook* |
| **Milestones closed** | M-PHV3, M-PHV4, eval-harness M0–M4, executive summary (incl. Rainmaker Rev3) |
| **Test suite** | 757 passed, 5 skipped |
| **Next planned work** | Data room completeness score (Phase 7); Hector repo inventory (Phase 9) |
| **Catalog (eval)** | `uc13_ale` |
| **Catalog (production default)** | `uc13` |
| **Control baseline** | `baseline_1aeb0ace584a` |

### Deferred (documented, non-blocking)

- `vs_metadata_filters` activation (PG5 bar failed)
- PHV4 items 28/30 (context assembly, `workstream_tags.py`)
- Cell 7 full ingestion rebuild on serverless (qualified smoke pass without it)
- Garden UI / Genie chatbot integration
- Scheduled workflow job — YAML exists; notebook remains production path

---

## Complete Commit Log

Grouped by date. Format: `HH:MM | subject`

### 2026-06-23 (8 commits) — Remediation kickoff

```
12:22 | preo + org + docs -- moving to exec route a and b
12:55 | T2: add Route A route_chunks SQL metadata router
13:11 | T5: wire context_utils retrieval_mode dispatch and RouteResult adapter
13:15 | T6: Wire retrieval_mode through FTA call chain
13:21 | T4: enhance retrieval.py with VS filter pushdown, merge rank, and SQL escaping
17:05 | working on a + b
17:17 | pushing
18:52 | T3: complete VS schema alignment with contract tests and index ready confirmation
```

### 2026-06-24 (8 commits) — Three-arm eval

```
09:55 | prep + r:b
16:05 | T1: add FTA corpus-stats cell and record Elder Care prerequisites
16:20 | prep - conducting three arm run (control + semantic + routing)
17:35 | RA: push filename filter into route_chunks SQL and add routed retry
17:37 | RB: freeze two-arm eval protocol (D7a) with scorecard template and pytest guard
17:37 | RUX: add Cell 1a retrieval_mode switch helper for A/B eval
17:41 | prep - fixing routed sql
18:25 | prep - fixing routed sql
```

### 2026-06-25 (4 commits) — Legal pivot

```
09:10 | snapshot table for 3-arm tracing/versioning
18:32 | prep -> switch focus to legal agent
20:07 | T1: Record Elder Care A0 corpus baseline measurement on uc13_ale
20:40 | T2: Capture Elder Care legacy legal agent baseline before T3 DDL migration
```

### 2026-06-26 (18 commits) — Legal M0–M2

```
08:23 | T3: Migrate legal agent storage to analysis.legal Delta table with compat view
10:23 | sonnet timeout on serverless - pushing nb to dbs workspace
10:39 | T4: Rewire legal agent workflow and notebook for standalone analysis.legal writes
10:42 | T5: Document M0 legal architecture surfaces and CLAUDE.md catalog row
11:01 | T-A1: Thread runtime catalog through LegalContractsAgent run path
11:03 | T-A2: Set workflow catalog default to uc13_ale
11:04 | T-A3: branch Cell 18 summary loop for legal tables without report_path
11:53 | T1: Scaffold _DOMAIN_PASSES loop replacing monolithic legal extraction path
11:56 | T2: Wire domain retrieval with catalog-threaded fallback and A0-tuned filters
12:00 | T4: Rename run() to extraction_endpoint and enforce Sonnet override
12:01 | T3: Wire per-pass extraction prompts and domain_extract_pass loop
12:04 | T5: Wire M1 interim return bridge and remove monolithic retrieval dead code
17:57 | T1: Add tri-state helpers, merge_registers, and roll-up field migration
18:09 | T2: Add stakeholder coverage gap assessment and section confidence
18:11 | T4: Wire run() post-pass pipeline with executive summary and gap JSON
18:13 | T5: thread gap/confidence fields through Delta mapper
18:15 | T6: dual-write normative legal_report.yaml and legacy legal_contracts_report.yaml
18:45 | T7: Amend M2 AST falsifiers and close Elder Care exit gate
```

### 2026-06-29 (21 commits) — Legal M3 + Orchestrator M1

```
09:16 | T2: Add runtime behavioral tests for legal agent helpers, merge, and flags
09:18 | T1: Move legal agent schema guard inline into main() per D1-A
09:26 | T3: close W-M2-COV with gap, confidence, and dual-write tests
09:43 | T4: Elder Care E2E dual compare and POC delta (G4)
11:44 | T7: Volume YAML post-E2E verification (D1/D4-A)
11:44 | T5: Golden checklist eval artifact with structural contract tests (G3)
11:44 | T6: Add presentation summary contract tests (D2 stakeholder closure)
12:24 | lca 4/4 + eval - moving to orch
18:34 | context upload
18:52 | org
18:56 | org
18:58 | T1: freeze orchestrator TLDR_REQUIRED_FIELDS and FILL_STATE_RULES constants
19:05 | T2: add orchestrator bundle schema, paths, and AGENTS_PRESENT_KEYS
19:19 | T3: add ingest_snapshots for Delta and Volume YAML reads
19:34 | T4: add populate_bundle, validate_bundle, and orchestrator deps
19:37 | syncing upstream to run workspace-based tests (×4)
20:06 | T8: Add orchestrator demo walkthrough, DOCX export cells, and M1 verification tests
20:15 | e2e tldr_run results + demo_walkthrough fix
```

### 2026-06-30 (28 commits) — TL;DR compression + BundleBuilder M2

```
11:10 | T1: add shared formatters for TL;DR compression layer
11:15 | T2: add compress_for_tldr projection engine
11:17 | T3: Add compressed TL;DR one-pager Jinja template
11:21 | T4: Wire TLDR_RENDER_MODE and compressed render path in renderers
11:23 | T5: Add tldr_quality_check soft-gate CLI
11:25 | T6: Add Elder Care compression fixture and section 7.1 integration tests
11:31 | T7: Record Elder Care cluster TL;DR compression verification metrics
11:32 | manual test on wrkspace
11:48 | audit
12:03 | T8: Fix headline dollar regex and gross vs EBITDA margin labels
12:06 | T9: Sentence-boundary In One Line, dedup flag, rank-before-cap
12:09 | T10: Stakeholder risk display titles and trimmed evidence/mitigant cells
12:14 | T11: Jinja whitespace trim on compressed TLDR template
12:34 | T12: Disambiguate duplicate Gross Margin headline ribbon labels
12:38 | T12b: Extend tldr_quality_check with headline and risk regression gates
12:38 | pushing to test tl;dr v4
17:38 | T2: extract ConfidenceEngine with medium_low composite
17:39 | T1: add Appendix B field_mapping and dedupe AGENT_DELTA_TABLE_SUFFIXES
17:47 | T3: Add deterministic BundleBuilder pipeline and GapAggregator
17:54 | T4: Delegate populate confidence to shared ConfidenceEngine
17:59 | T5: Elder Care pytest fixtures and G4 builder verification
18:03 | T6: Cell 19 production BundleBuilder path and render cell gate
18:23 | T7: Stage 6 executive synthesis default-on when llm_endpoint set
18:23 | pushing to test in dbs
19:14 | T9: Close audit documentation drift
19:14 | T8: KPI diligence dict formatting
19:16 | T10: Synthesis fail-open logging via print() and notebook DOCX path hygiene
19:20 | runs successful - fixed dict leakage and other fixes
```

### 2026-07-01 (14 commits) — M-RE1 eval foundation

```
19:29 | org + prep 4 eval harness and VS v3
19:49 | T1: RE² eval package scaffold and RouteResult contract freeze
19:51 | T2: migrate semantic_search to RouteResult with mode and scores
19:55 | T3: propagate RouteResult in wrappers and remove Route A
19:56 | T5: Intent registry extractor and golden count CI gate
19:57 | T7: EvalStore protocol, sqlite/delta backends, and ops DDL apply CLI
19:59 | T4: migrate agent callers to RouteResult.chunks and add CI guard
20:02 | T6: Gold label bootstrap — elder_care.yaml, mocked Spark tests
20:05 | T8: EvalHarness, scope resolver, and golden gate fixtures
20:08 | T10: Refresh M-RE1 architecture docs and static contract tests
20:09 | T9: CI fixture, sync_eval_store CLI, and cluster baseline runbook
20:28 | retrieval harness + upgrade m 1/4 - pushing to test in workspace
20:47 | .
20:52 | ddl
```

### 2026-07-02 (19 commits) — M-RE2 observability

```
07:51 | store.py fix
08:35 | eval harness built + baselines in repo
08:54 | T11: Re-pin CI eval tests and fixtures to cluster gold (G3 PASS)
17:51 | T1: Land run context API and pipeline manifest schema
17:56 | T2: Add shared provenance module and ProvenanceEmitter
18:05 | T3: Wire retrieval provenance emit hook and intent_id propagation
18:11 | T5: OPEX per-query budgets and labeled context sections
18:16 | T4: Wire pipeline run context on workstream agents and FTA intent attribution
18:19 | T7: BasisCrossCheck Option D on FTA merge path
18:19 | T6: Context allocation provenance patch for OPEX intents
18:23 | T8: Consolidate M-RE2 regression unit tests
18:28 | T9: E2E linkage CLI, M-RE2 operator runbook, architecture append
18:33 | pushing to run e2e test in workspace
18:39 | fixed path databricks
18:57 | re
19:16 | Fix DELTA_METADATA_MISMATCH: additive Delta column migration
19:36 | Fix FTA ThreadPoolExecutor losing provenance ContextVars
19:55 | Add retry-with-backoff for concurrent Delta MERGE/UPDATE
20:17 | Batch OPEX provenance patch into one MERGE + lock Delta writes
```

### 2026-07-03 (10 commits) — M-RE3 hardening

```
10:06 | A3: Close M-RE2 documentation drift after A1/A2 cluster fixes
11:11 | T1: Add VS filter pushdown probe script and M-RE3 entry-gate matrix
11:14 | T3: consolidate BMA/Legal fallback into shared fallback.py
11:18 | testing in wrkspace
12:13 | T1 attestation: record cluster VS filter pushdown probe PASS
12:17 | T2: add vs_metadata_filters capability (gated off by default)
12:37 | T4: wire ablation_config to merge_rank_mode dispatch in harness
12:43 | T5: Ablation matrix fixture proof and cluster runbook
19:07 | T6: Post-hardening re-baseline runbook and M-RE3 housekeeping docs
19:51 | pushing ablation to test in workspace
```

### 2026-07-06 (7 commits) — M-PHV1 + account switch

```
10:31 | [Ale] pushing to pull; ablation test results + org and prep
20:40 | T1: fail-closed IndexSyncError on vector index sync paths
20:42 | T3: Lock Cell 1 llm_endpoint default and fix CLAUDE.md extraction row
20:43 | T4: Document halt-on-failure index sync in test_pipeline Cells 7/8
20:44 | T2: Add fail-closed index-sync unit tests
20:46 | T5: Add M-PHV1 exit-gate verification runbook to CLAUDE.md
20:50 | T6: Post-milestone housekeeping for M-PHV1 pipeline gates
```

### 2026-07-07 (12 commits) — PHV2 kickoff + test hygiene

```
09:33 | T7: Close audit F2/F3 — path-3 test coverage and import placement
10:39 | pushing to test wrkspc
15:49 | pushing to test wrkspc
19:39 | T1: Item 9 PG1 entry-gate PASS — M-RE3 evidence verified at HEAD
19:43 | T2: Add PHV validation runbook section and agent matrix to README
19:45 | T7: Add notebook E2E cell ledger attestation template and structural tests
19:48 | T4: Add scorecard index schema and smoke-E2E templates
19:48 | T3: add R-02 manual A/B hub section to eval retrieval README
19:55 | T5: Document second-company selection criteria and run procedure
19:57 | T6: Document record_e2e_linkage invocations for FTA and Legal only
20:01 | T8: M-PHV2 exit-gate checklist template and structural tests
20:07 | pushing to test wrkspc
```

### 2026-07-08 (5 commits) — PHV2 closure

```
11:17 | pushing to test wrkspc: dedup and merge broke on new fields
16:37 | T9: PHV2 FTA/Legal scorecards from operator evidence
16:50 | T9: complete smoke-agent scorecards from uc13_ale.ops SQL evidence
17:11 | Log M-PHV2 item 17 E2E linkage operator attestation
17:40 | T10: close M-PHV2 exit gates with operator E2E attestations and Flag 6
```

### 2026-07-09 (6 commits) — PHV3 integration start

```
10:35 | T1: Item 19 + PG2 pre-merge verification (PASS)
10:41 | pre merge dets
10:42 | T2: fast-forward origin/dev to dev2 HEAD (push #1 of 2)
10:58 | T3: correct legal agent catalog default to uc13 and document convention
11:15 | T4: remove _CATALOG shadow constants from five workstream agents
11:21 | pushing from cafe -> apt
```

### 2026-07-10 – 2026-07-12 (3 commits)

```
Jul 10 | T5: Add §5.12.3 catalog convention static test (PG3 gate)
Jul 10 | T6: prepare item 23 post-merge smoke attestation template
Jul 12 | t6 operator tests m3 phv
```

### 2026-07-14 (7 commits) — PHV3 closure + PHV4 start

```
10:47 | T6: close item 23 smoke attestation PASS (qualified)
10:50 | T7: M-PHV3 exit closure — workflow YAML hygiene and PG2 push prep
10:54 | Eval cleanup: gitignore harness report snapshots and remove incomplete locals
12:48 | T1: deduplicate _TYPE_ORDER across retrieval and context_utils
12:49 | T4: Add R-08 join-integrity preflight test and README section
12:52 | T2: consolidate FTA retrieval onto shared fallback.py (R-03 item 26)
12:55 | T3: unify harness dispatch_retrieval onto shared fallback.py (Surface 11)
```

### 2026-07-15 (7 commits) — PHV4 closure prep

```
08:51 | pushing to test A/B vs metadata + operator tasks
09:56 | T6: M-PHV4 charter housekeeping — milestone closeout documentation
10:04 | pre audit commit (×2)
13:30 | T7: Harden semantic_search inventory matcher (audit T-1 remediation)
19:14 | operator runs in wrksps - resetting the branch
20:40 | fixing legal agent intent registry + testing again
```

### 2026-07-16 (2 commits)

```
12:54 | agents + scorecards + linkage + completed amendments to m4 phv — re auditing
20:11 | phv work done now moving to feature branch to work on exec summary
```

### 2026-07-17 (7 commits) — Exec summary sprint start

```
11:12 | T1: rename one-pager H1 display text to Executive Summary
17:33 | T2: Baseline smoke all 4 companies on uc13_ale compressed pipeline
17:57 | T3: expand Stage 6 executive narrative fields on feature branch
17:58 | T8: phv4 legal-snapshot spot-check and async PG4 escalation record
18:04 | T4: wire executive narrative fields through compress and template
18:14 | T5: extend exec-summary contract tests for expanded synthesis fields
18:23 | T6: ACCEPT Elder Care expanded synthesis — cluster validation
```

### 2026-07-18 (5 commits) — Exec summary v1.1

```
10:31 | T10: Reframe Stage-6 prompt for mitigation strategy and confidence-with-gaps
10:31 | T12: format KPI stated values as readable prose instead of dict reprs
10:32 | T11: drop Mitigant column, rename section headers, clean risk Evidence
11:11 | T13: Update tests for v1.1.0 Top Risks and section header changes
11:21 | T14: Elder Care v1.1.0 re-run validated — ACCEPT, resume T7
```

### 2026-07-20 (11 commits) — Exec summary v1.2–v1.3 + 4/4 assembly

```
12:01 | T15: deterministic presentation pass — de-truncate, coverage %, KPI reshape
12:02 | T16: Stage-6 synthesis expansion — 5 digest lead-ins + refined mitigants/confidence
12:04 | T17: Project and render digest lead-ins above section detail
12:06 | T18: Test updates for v1.2.0 digest lead-ins and presentation pass
12:25 | T19: Elder Care v1.2.0 re-validate — partial digest ship, resume T7
19:31 | T21: deterministic citation resolver and compress projection drops
19:37 | T23: update tests for v1.3.0 consolidated overview and dropped digests
19:49 | T24: Accept Elder Care v1.3.0 validation — resume T7
20:38 | T7: complete expanded-synthesis sequence for Clearsulting, GKF, and SPG
20:45 | T9: Final assembly — 4/4 expanded executive summaries selected
21:02 | exec summaries work done - 4 companies tldr created w latest version
```

### 2026-07-21 (28 commits) — Eval harness all agents M0–M4

```
13:09 | T1: Generalize record_e2e_linkage CLI for all 7 agents
13:10 | T5: Add KPI overlay-selection deterministic-rule fixture
13:11 | T6: Add QoE downstream-math deterministic fixture tests
13:11 | T2: Instrument Profiler with pipeline-run tracking
13:12 | T3: Add BMA revenue-durability deterministic fixture tests
13:12 | T4: Add CQA deterministic-rule threshold fixtures
13:16 | T7: Seed eval-harness M0 architecture docs and changelog section
14:00 | M1-T1: Add GOLDEN_CHECKLIST_COVERAGE constants for BMA, CQA, KPI, Profiler
14:05 | T5: Author Profiler golden checklist for Elder Care
14:05 | T3: Author CQA golden checklist for Elder Care
14:06 | T2: Author BMA golden checklist for Elder Care
14:06 | T4: Author KPI golden checklist for Elder Care (3 rows)
14:12 | T6: Parameterize golden checklist structural harness (M1 HUB)
17:10 | M2-T1: Add QoE golden checklist coverage constant and Elder Care checklist
17:11 | M2-T2: Extend golden checklist hub with QoE CHECKLIST_CASES row
17:12 | M2-T3: Add QoE precondition-gate test fixture
17:14 | M2-T4: Document QoE FTA addback precondition-gate procedure in README
17:54 | M3-T2: Add PromotionResult dataclass and waiver-ID validator scaffolding
17:55 | M3-T1: Add select_prior_e2e_baseline checklist-regression baseline helper
17:57 | M3-T3: implement evaluate_promotion gate decision logic
18:00 | M3-T4: Add promotion gate test suite (Program Gate G3)
18:37 | M4-T1: README unified 7-agent rewrite
18:39 | M4-T2: invert guard test for unified 7-agent README (Program Gate G4)
18:43 | M4-T6: QoE first scored run — baseline_bootstrap 5/6
18:45 | M4-T5: KPI first scored run — baseline_bootstrap 3/3
18:49 | M4-T3: BMA first scored run — baseline_bootstrap 7/7
18:53 | M4 T7: Profiler Elder Care first scored baseline via evaluate_promotion
18:57 | M4-T8: Close scorecard INDEX and program housekeeping
```

### 2026-07-22 (5 commits) — Rainmaker Rev 2

```
11:28 | T1: Cut feat/exec-summary-rainmaker-restructure from dev at d06992a
11:29 | T3: Add Revision 2 optional schema properties (thesis_bullets, key_watchouts, workforce_notes)
11:30 | T4: Stage 6 prompt/allowlist/merge for thesis_bullets, key_watchouts, Bucket B attribution
11:30 | T2: map BMA workforce_capacity to company_framing.workforce_notes
11:36 | T5: Bucket A TLDR restructure — Rainmaker section order and KPI fold
```

### 2026-07-22 – 2026-07-24 (8 commits) — Rainmaker Rev 3 + merge + fixes

```
Jul 22 16:31 | T1: Rev3 Stage-6 prompt restructure for Rainmaker fidelity
Jul 22 16:35 | T2: Restructure compressed one-pager template and compress layer for Rev3
Jul 22 16:42 | T3: Elder Care R3 validation ACCEPT — 1344w, Rainmaker section parity
Jul 24 10:16 | Merge branch feat/exec-summary-rainmaker-restructure — Rainmaker Rev2/Rev3
Jul 24 10:16 | Update my_runbook.md — Phase 6/8 done, dev2 + Rainmaker merged
Jul 24 12:16 | Close M4 F2 BMA checklist drift and legal restrictive merge fix
Jul 24 12:30 | Update runbook after Legal 9/11 re-score and dev push
Jul 24 12:30 | Restore git merge session log row in runbook
```

---

## Appendix — Alejandro git identities

For commit archaeology only. Three identities, same person:

| Identity | Email | Commits |
|----------|-------|---------|
| Ale | `alejandroa.garay.ag@gmail.com` | 131 |
| Alejandro Garay | `alejandro.garay@nimblegravity.com` | 112 |
| alegarayf | `alejandro.garay@nimblegravity.com` | 2 |

**Alejandro first commit:** `95166bf` — 2026-06-23  
**Alejandro latest commit:** `93f3462` — 2026-07-24

---

## Document maintenance

| Check | Status |
|-------|--------|
| Milestones through Jul 24 | ✓ |
| Hector foundation credited | ✓ |
| Changes-to-your-code table | ✓ |
| Agent scores (Legal 9/11) | ✓ |
| Branch state (`dev`) | ✓ |
| `.dev/` gitignored artifacts | Referenced by path/SHA in `CHANGELOG.MD` — not in git tree |

*Last updated 2026-07-24. Primary living docs: `CHANGELOG.MD`, `my_runbook.md`, `eval/retrieval/README.md`.*
