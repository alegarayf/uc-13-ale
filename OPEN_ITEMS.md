# Open items — consolidated tracker

**For:** Alejandro · **Updated:** 2026-08-03  
**Purpose:** Single place for open, half-open, and stale-doc debt. Sources: repo-wide md scan + `pending.md`, `pending2.md`, `post_merge_regressions.md`, `my_runbook.md`, `uc13-company-data-analysis.md`, `GOLD_LABEL_BOOTSTRAP_HANDOFF.md`, `sqlite_removal.md`, `eval/retrieval/README.md`, `.dev/eval_framework_work.md`, `.dev/uc-13_pain_central_v1.2.0.md`, `MERGE_SCOUT_hector_ui_pipeline_integration.md`.

---

## Open / half-open

### Merge & gates

| Item | Program | Latest |
|------|---------|--------|
| **G5 VDR gate** — `run_vdr_pipeline.py` never exercised | `hector-ui-pipeline-merge` · `CLUSTER_GATES.md` G5 | **Open** — only merge gate without a run |
| **G2–G4 formal sign-off** | `CLUSTER_GATES.md` G2–G4 | **Half-open** — Elder Care e2e `827597669988464` + Chip B runs evidence DAG/memo/bridge; gate file not updated to PASS |
| **G6 gate file note stale** — G6 PASS says T7 baseline "not yet done" | `CLUSTER_GATES.md` G6 | **Update needed** — T7 promoted `baseline_544eb3f2a0e2` per `harness-baseline-2026-07-30.md` |
| **FTA memo generator** — `section 'financial_trends' generator failed`; `flags` not `json.loads()`'d (BMA R-3 class) | `post_merge_regressions.md` · Chip B logs | **Open** — FTA G1 still passes (16.5/18); silent memo degradation on Clearsulting/GKF/SPG |
| **Legal dedupe hardening** — add `source_doc` to `_register_dedupe_key` | `post_merge_regressions.md` R-2 backlog | **Open** — separate ticket; not merge blocker |
| **Legal R-2 (t4c variance)** | Chip B · `pending2.md` | **Deferred / accepted** — post-fix e2e **7/11** (≥7 floor); LLM entity-resolution variance |
| **phv4 NEW-1** — test `ec74042` insurance BACKGROUND filter | M-PHV4 · `pending2.md` | **Open** — sound fix, behavior untested |
| **O-14.13** — test or waiver for `build_exec_summary(..., llm_endpoint=None)` | Merge audit · `GOLD_LABEL_BOOTSTRAP_HANDOFF.md` | **Open** — `pass-with-conditions` waiver pending |
| **CQA cosmetic** — `industry_overlay_used` empty in assessment markdown | `CLUSTER_GATES.md` G1 watch · T6 | **Open / low** — cosmetic; fix if overlay label needed in memo |

### Data & ingest quality

| Item | Program | Latest |
|------|---------|--------|
| **Elder Care ingest gap** — ~52% of `should_parse` chunked; **182 missing** (112 FINANCIAL) | `uc13-company-data-analysis.md` §2, §11 | **Open** — Cell 8c/8d on missing set |
| **SPG ingest borderline** — 90.4% ingested, 41 missing (LEGAL-heavy) | Chip B T1 preflight | **Half-open** — GO for e2e; not remediated |
| **Join / hydration drift (R-08)** — Elder Care ~47.6% chunk↔`doc_relevance` join orphans | `pain_central` R-08 | **WATCH** — CI guard exists; can starve `workstream_filter` hydration |
| **Cell 8c never in smoke path** | `my_runbook.md` Phase 1 | **Half-open** — qualified M-PHV3 smoke skipped coverage report |
| **Incremental parser / status table** | `ingestion_parser_run_notes.md` | **Design backlog** — per-doc resume, embed-in-loop; not merge debt |
| **IndexSyncError job exit behavior** | `databricks/CLAUDE.md` | **Open question** — uncaught `IndexSyncError` may not fail Databricks job; never cluster-validated |

### Eval & harness

| Item | Program | Latest |
|------|---------|--------|
| **`evaluate_promotion` — Clearsulting / GKF / SPG** | Chip B plan · T5 decision log | **Skipped by design** — no ops-store golden floors |
| **`evaluate_promotion` — Elder Care post-fix full refresh** | Chip B closeout | **Half-open** — BMA `promoted` on `827597669988464`; other 6 agents not re-promoted in INDEX |
| **Profiler re-run — Clearsulting / GKF / SPG** | Chip B plan (excluded) | **Open / optional** — INDEX profiler rows pre-DAG (stale) |
| **Phase C — multi-company gold YAML** | Chip A O-14.11 · M4 Decision 3 | **Deferred by design** — escalation only |
| **O-14.3 — 6 FTA `bootstrap_failed` rows** | Chip A · gold bootstrap | **Open / opportunistic** — 57-row yaml committed; rollup still has failed rows |
| **Chip B operator decisions** — Flag 5 (narrow B1 vs whole-DAG), Flag 6 (smoke-tier prior?) | `chip-b-4company-agent-validation/plan.md` | **Unanswered** — whole-DAG recorded; informational |
| **O-11 / GKF–SPG fallback re-verify** | `pain_central` O-11 | **Half-open** — index healthy (112k rows); re-score harness for `fallback_rate=0` |
| **M-PHV4 README T2 gate** still marked OPEN | `eval/retrieval/README.md` L218 | **Doc stale** — program **DECIDED OFF** (PG5 fail); R-02 attestation 2026-07-15 |
| **`legal.litigation` chunk_id diff debug** | `eval/retrieval/README.md` | **Deferred** — non-blocking |
| **FTA rubric → `eval/FTA/`** | `.dev/eval_framework_work.md` § open #7 | **Open** — provisional lock; no `eval/FTA/` folder yet |
| **`elder_care_slice.json` refresh trigger** | Chip A plan Flag 6 | **Open** — unclear when fixture must update post-gold change |
| **Multi-company harness gold matrix (Q-E03)** | `pain_central` | **Partial** — Chip B scorecards exist; per-company gold YAML deferred (Phase C) |

### Agent quality backlog

| Item | Program | Latest |
|------|---------|--------|
| **Clearsulting KPI overlay conflict (A-09)** | `pain_central` | **Open** — Profiler `healthcare_services` vs KPI `overlay_confirmed=tech_services` |
| **Agent depth uneven (A-03)** | M4 · Chip B scores | **Iteration backlog** — Elder Care CQA 3/6; Clearsulting/GKF KPI **1/3** (thin corpus + overlay) |
| **Excel cell-level citations (A-07)** | `pain_central` | **WATCH** — not systematic |
| **Clearsulting stakeholder narrative** — 0 LEGAL docs | `uc13-company-data-analysis.md` | **Open (comms)** — expected thin-data; document for stakeholders |

### Runbook & program milestones

| Item | Program | Latest |
|------|---------|--------|
| **Phase 7 — data room completeness scorecard** | `my_runbook.md` · D-01 | **Open (design)** — ingest % + workstream presence + agent gap counts; Clearsulting canonical example |
| **Phase 9 — Hector merge** | `my_runbook.md` · `pending.md` | **Half-open** — code on `feat/merge-hector-incoming`; inventory/merge to main track + Garden timing not closed |
| **M-PHV4 deferred** — OPEX/revenue/EBITDA multi-query pools (item 28), `workstream_tags.py` (item 30) | `to_dive_deeper.md` · M-PHV4 | **Deferred** — `_TYPE_ORDER` closed; 3–5 queries → one budget anti-pattern remains |
| **Cell 7 full parser rebuild** | `my_runbook.md` · pain O-12 | **Deferred** — serverless OOM; qualified pass on existing corpus |
| **T9 `.docx` on serverless** | Post-merge e2e | **Open (infra)** — missing `python-docx`; `.md` OK |
| **R-07 driver-bound two-hop retrieval** | `pain_central` | **Open** — architecture debt |
| **R-06 SQL bound parameters** | `pain_central` | **Partial** — `_escape_sql_literal` only |
| **Q-R03 shared index topology** | `pain_central` | **Candidate DECIDED** — one index per catalog; formal close pending doc update |

### Orchestrator charter & product

| Item | Program | Latest |
|------|---------|--------|
| **Charter M3 — gate/condition + halt → 1-pager flow** | orchestrator charter · `to_also_think_about.md` · `pending.md` | **Open (design)** — triggers not exercised; subagent halt → exec summary path unspecified |
| **Exec-summary experiments** — aggressive LLM sections; mitigants digest | `pending.md` | **Idea** — optional for presentation |
| **Dataset / pre-training exploration** | `pending.md` | **Idea** |
| **`route_chunks` cleanup** | `pending.md` | **Half-open** — Route A removed; plumbing may delete |
| **MERGE_SCOUT decisions Q1–Q6** — deliverable default, Forecast/Cross-Analysis MVP, VDR prod, token caps, catalog split, Garden timing | `MERGE_SCOUT_hector_ui_pipeline_integration.md` §10 | **Unrecorded** — mostly decided in practice; never written to decision log |
| **S-05 / M-04 — Garden UI + prod auth** | `pain_central` | **Open** — product track |
| **M-02 Genie chatbot product fate** | `pain_central` | **Open (product)** — code merged; product decision pending |
| **P-07 Workflow YAML Llama 70B vs notebook Sonnet** | `pain_central` | **WATCH** — risk if workflow runs without `llm_endpoint` override |

### Test & automation debt (accepted gaps — track explicitly)

| Item | Program | Latest |
|------|---------|--------|
| No pytest for `g1_score_all_agents.py` | Chip B T5/T6 · CHANGELOG | **Accepted gap** — live stdout falsifiers |
| No pytest for markdown trackers | Chip B T7 · CHANGELOG | **Accepted gap** — manual review |
| No automated INDEX↔manifest cross-check | M4-T8 audit | **Accepted gap** |
| No test: 8 new gold intents have non-empty `positive_chunk_ids` | Chip A T4 | **Open gap** |
| No auto-check: CLUSTER_GATES PASS ⇒ 0 xfail | Chip A T5 CHANGELOG | **Open gap** |
| No cluster falsifier for Rainmaker PDF structure | Exec-summary T3/T6 | **Accepted gap** — image-only PDF |
| `record_e2e_linkage` scope — FTA/Legal only | `.dev/eval_framework_work.md` §9 | **Deferred v2** — golden five use INDEX only |

### Housekeeping (do today)

| Item | Program | Latest |
|------|---------|--------|
| **Chip A plan status + auditor handoff** (audit F1) | `chip-a-g6-gold-bootstrap/plan.md` | **Stale** — banner still "T7 pending" |
| **T2 working note fix** (audit F3) | `T2-cluster-bootstrap.md` | **Stale** — wrong pre-T2 `bootstrap_failed` for 2 intents |
| **Runbook G6 SHA** (audit F4) | `my_runbook.md` | **Wrong** — `dc2ce284` → **`2457cf9`** (T7) |
| **Commit gold guardrails** | Chip A audit | **Uncommitted** — `gold_positive_counts.yaml`, `test_gold_bootstrap.py` |
| **Doc sync (stale → reality)** | cross-doc | See **Stale docs** table below |

#### Stale docs — update, don't re-do work

| Doc | Stale claim | Reality |
|-----|-------------|---------|
| `GOLD_LABEL_BOOTSTRAP_HANDOFF.md` | G6 OPEN, 49 labels, Chip B not run | Closed 2026-07-30 |
| `pending2.md` | Chip B open | Closed 2026-07-30 |
| `sqlite_removal.md` | Phase 3 pending | Closed via e2e `1074138209208842` / `827597669988464` |
| `post_merge_regressions.md` §Open work | R-1/R-3/Profiler open | Superseded by Pending table (2026-07-30) |
| `my_runbook.md` | "open follow-ups: none"; missing G6/Chip B | Post–7/24 + Chip A/B closeout |
| `project_status_timeline.md` | Integration not closed; metadata A/B not run | Closed Jul 16–24 |
| `eval_framework_work.md` | Phase 6 active, 49-intent baseline | M4 closed; **`baseline_544eb3f2a0e2`** / 57 intents |
| `uc13-company-data-analysis.md` §10 | VS index MISSING | Index exists (112k rows); refresh § + harness re-score |
| `pain_central` v1.2.0 | Frozen 2026-07-24; A-08 OPEN, Q-E03 partial | Refresh: Legal **9/11**, Chip B scored, O-11 index fixed |
| `legal-restrictive-covenant-brief` | 7/11 restrictive triage | Superseded by 9/11 closeout |
| `MERGE_SCOUT` / `detailed_work_summary` | `reportlab` missing from requirements | **Closed** — in `databricks/requirements.txt` |
| `eval/retrieval/README.md` | T2 gate OPEN | DECIDED OFF (PG5) |
| `MERGE_SCOUT` §9 checklist | 3 pre-merge unchecked items | **Archive** — obsolete post-merge |

---

## Suggested order for today

1. Housekeeping commit + doc sync (guardrails, runbook SHA, handoff, sqlite_removal, CLUSTER_GATES G6 T7 note).
2. G2–G4 + G6 gate file PASS updates from existing e2e evidence.
3. FTA memo `flags` parse fix (same patch class as BMA R-3).
4. G5 VDR gate run (if cluster time).
5. Harness re-score for O-11 close + `uc13-company-data-analysis.md` §10 refresh.
6. Phase 7 design sketch (if capacity).

---

## Closed / recently closed (reference)

| Item | Program | Closed |
|------|---------|--------|
| **G6 gold bootstrap (Chip A)** | `chip-a-g6-gold-bootstrap` · CLUSTER_GATES G6 | **2026-07-30** — 57-row `elder_care.yaml`, 765 tests, audit pass-with-conditions; harness `baseline_544eb3f2a0e2` |
| **Chip B 4-company e2e** | `chip-b-4company-agent-validation` | **2026-07-30** — Clearsulting/GKF/SPG 9/0/0 each; 21 INFO scorecards |
| **Elder Care post-fix e2e** | `post_merge_regressions.md` | **2026-07-28** — `827597669988464` 9/0/0; BMA 7/7, Profiler 7/7 |
| **SQLite → Delta provenance (Phase 3)** | `sqlite_removal.md` | **2026-07-27/28** — `open_agent_run(spark=)`; 326 provenance rows on Delta |
| **BMA R-1 + R-3** | `post_merge_regressions.md` | **2026-07-28** — Sonnet override + `flags` json.loads; SPG 71k-chunk hold confirmed Chip B |
| **Phase 6 — eval harness all agents** | `my_runbook.md` · M4 | **2026-07-21** — merged `dev` 2026-07-24 |
| **Phase 8 — executive summary** | `my_runbook.md` · Rainmaker | **2026-07-20/24** — TL;DR → Executive Summary; 4/4 companies |
| **M-PHV3 integration + audit** | `my_runbook.md` | **2026-07-14/16** — qualified smoke; M-PHV4 audit accepted-with-waivers |
| **Legal 9/11 post restrictive-merge fix (A-08)** | M4 · runbook | **2026-07-24** — closes pain_central A-08 (was 7/11 on 7/16) |
| **O-14.5 / O-14.8 / O-14.9 / O-14.10 / O-14.15** | Chip B | **2026-07-30** |
| **G6 magnitude-shift disclosure (audit F2)** | Chip A | **2026-07-30** |
| **phv4 NEW-2 registry hash compare** | M-PHV4 | **Waived** at `baseline_544eb3f2a0e2` |
| **`reportlab` in requirements.txt** | MERGE_SCOUT / VDR | **Landed** — `databricks/requirements.txt` |
| **Re-score all agents post M-RE3** | `pending.md` (old) | **Superseded** — M4 + Chip B scoring; no fresh 2026-08 pass unless requested |
| **Score FTA on more companies** | `pending.md` (old) | **Partially done** — Chip B Clearsulting 17/18, GKF 13.5/18, SPG 8.5/18 (informational) |
| **TL;DR → Executive Summary rename** | `pending.md` charter | **Done** — Phase 8 / Rainmaker |
