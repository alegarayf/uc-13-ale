# My runbook — integration closeout → hardening finish

**For:** Alejandro only  
**Updated:** 2026-07-13  
**Companion:** `project_status_timeline.md` (PM-facing summary)

Use this as a **sequential checklist**. Each cluster block ≈ **2 hr** — batch them; don’t start a new block if the previous one failed.

---

## Rules of thumb

1. **Pin before every cluster session:** `git rev-parse HEAD`, notebook content SHA if you touched it, company=`Elder Care`, catalog=`uc13_ale`.
2. **Local first when cheap:** `pytest tests/test_catalog_convention.py -q` and full suite before any push.
3. **One attestation per run:** paste stdout verbatim; don’t paraphrase pass/fail.
4. **Don’t declare baselines authoritative** from sqlite or single-intent runs — promote to Delta or discard.
5. **Retrieval code stays frozen** until integration smoke + closing audit are done.

---

## Phase 0 — Preflight (laptop, ~15 min)

- [ ] `git status` clean or only intentional artifacts
- [ ] On `dev`, synced with `origin/dev`
- [ ] `pytest tests/test_catalog_convention.py -q` → green
- [ ] Optional full suite if you changed anything since last green run
- [ ] Attestation template open: `.dev/plans/uc13-m-phv3-integration/item23-post-merge-smoke-attestation.md`
- [ ] Cluster attached; Cell 0 pip done once per restart

**Record in attestation before run:**

```
Commit SHA at smoke run: ___________
Cluster date (UTC): ___________
```

---

## Phase 1 — Post-integration smoke 【BLOCKING · ~2 hr cluster】

**Goal:** Prove ingestion + index sync + business model agent + `company_profile` read work on live infra.

**Notebook:** `databricks/jobs/notebooks/test_pipeline.ipynb`  
**Scope:** Parser path → BMA. Not a full seven-agent re-score.

### Run path (minimum)

- [ ] Cell 1 — widgets: `sp_company_name=Elder Care`, `catalog=uc13_ale`, `llm_endpoint` Sonnet 4.6
- [ ] Cell 8b — quick retrieval smoke (`RouteResult` — no `TypeError` on `.chunks`)
- [ ] Cell 7 — full parser rebuild → stdout must include **`✓ Index ready`**
- [ ] Cell 8 — chunk stats look sane
- [ ] Cell 8c — coverage report; **8d only if gaps**
- [ ] Cells 9–10 — profiler + profile table (recommended)
- [ ] Cell 11 — business model agent completes without traceback

### Pass criteria

- [ ] No `IndexSyncError` on Cell 7
- [ ] BMA `main()` finished
- [ ] `company_profile` for Elder Care **row count > 0** in `uc13_ale.classification.company_profile`
- [ ] Explicit line in attestation: *company_profile reads for BMA return non-empty, correctly-catalogued data: PASS*

### Fill attestation

- [ ] Paste Cell 7 stdout excerpt (`✓ Index ready`)
- [ ] Paste Cell 11 stdout excerpt
- [ ] Set **Item 23 overall** → PASS (not “AWAITING OPERATOR RUN”)
- [ ] Notebook content SHA at run (should still be `ce094a4b8b3e046253fc876712531792a0b9ff89` unless you changed notebook)

### HALT — do not proceed to Phase 2 if

- Cell 8b throws on `RouteResult` unpacking
- Cell 7 missing `✓ Index ready`
- BMA fails on catalog / `company_profile` SQL
- You pushed new commits after this SHA without re-smoking

---

## Phase 2 — Integration closeout (T7) 【laptop + git · no cluster required unless you choose】

**Goal:** Formal exit so retrieval work is allowed.

### Code / docs

- [ ] Fix 5 stale `python_file` names in `databricks/workflows/uc13_ingestion_pipeline.yml` (drop `00_`, `01_`, etc. prefixes)
- [ ] Match names in `databricks/workflows/README.md`
- [ ] Verify: `grep` for old `0[0-9]_setup_vector_search` etc. → no hits
- [ ] Create `.dev/plans/uc13-m-phv3-integration/exit-gate-checklist.md` — cite smoke PASS, catalog test green, push outcome
- [ ] Append `CHANGELOG.MD` M-PHV3 entry
- [ ] Touch `.dev/architecture/rallyday/` housekeeping if anything changed (module-map, changelog, etc.)

### Git sync

- [ ] Re-run Genie parity: `git diff origin/dev..HEAD -- backend-ai/app/services/genie_rules.py` → empty
- [ ] **User go-ahead** then push: sync `dev` to `origin/dev` (plan expected `dev2:dev` — if `dev2` is behind, fast-forward `dev2` to `dev` first or push `dev` explicitly; don’t force)
- [ ] Confirm smoke SHA is what got pushed (no commits between smoke and push except T7 hygiene)

### Tests

- [ ] `pytest tests/test_catalog_convention.py -q`
- [ ] Full suite green before push

---

## Phase 3 — Closing audit 【review session · can same day as Phase 2】

**Goal:** Close the loop validation started in early July; integration gets its own sign-off.

- [ ] Cold-read attestation + exit checklist + T3–T5 diffs
- [ ] Run auditor skill / big-model review on integration scope (not full re-validation of all agents)
- [ ] Write `.dev/audits/2026-07-__-uc13-integration-closeout.md` (or similar) with `audit_status: clean` or `accepted-with-waivers`
- [ ] Note any waivers by name — don’t silently carry gaps into retrieval work

**Gate:** No retrieval consolidation coding until this file exists and smoke is PASS.

---

## Phase 4 — Retrieval consolidation 【next hardening phase】

**Goal:** First changes to `retrieval.py`, `fallback.py`, `context_utils.py` + regression proof.

### Before coding

- [ ] Read charter stub for “Retrieval consolidation” in `.dev/specs/pipeline/uc13_pipeline_hardening_milestone_charter.md`
- [ ] Pre-plan / context map if you use the orchestrator workflow
- [ ] Pin baseline: **`baseline_299063e87806`** (Elder Care / `uc13_ale`)

### Work packages (in rough dependency order)

- [ ] Shared context assembly (OPEX pool / revenue / EBITDA budgets — see `to_dive_deeper.md`)
- [ ] FTA fallback → shared `fallback.py` (3 call sites in revenue/ebitda/opex sub-agents)
- [ ] Join-integrity preflight doc + guard
- [ ] Optional: metadata filter A/B (Phase 4b below)

### Cluster regression 【~2 hr each; plan multiple sessions】

- [ ] `apply_ops_ddl("uc13_ale")` if DDL changed
- [ ] G2 probe — `company_name` pushdown still accepted (no “VS filter pushdown unavailable”)
- [ ] Full harness baseline: `python -m eval.retrieval.harness_cli run --store-backend delta --run-type baseline --company-name "Elder Care" --catalog uc13_ale`
- [ ] Compare vs `baseline_299063e87806` — no recall regression on gate-eligible intents
- [ ] FTA Cell 12 re-score → target **≥ 16/18**
- [ ] Legal Cell 16 re-score → target **≥ 7/11** pass on `eval/LCA/golden_checklist_elder_care.md`
- [ ] `record_e2e_linkage` for FTA + Legal pipeline `run_id`s if you re-ran them

**Done when:** harness compare clean, FTA/Legal floors hold, assembly unit tests green, audit for this phase.

---

## Phase 4b — Metadata filter A/B 【optional · ~4 hr cluster · 2 runs】

Only needed if you want filters **on** in production. Hardening can finish with them **off**.

- [ ] Runbook: `eval/retrieval/README.md` § “R-02 manual A/B”
- [ ] Run A: `vs_metadata_filters=False` (control)
- [ ] Run B: `vs_metadata_filters=True`
- [ ] Record both `run_id`s + per-intent recall@10
- [ ] Bar: no gate-eligible intent drops >5pp; aggregate recall non-decreasing
- [ ] **Second reviewer** (not you) signs off
- [ ] If bar fails: document and leave default `False` — still valid exit

---

## Phase 5 — Eval cleanup (leftover partial runs) 【laptop + maybe 1 cluster】 ✅ DONE 2026-07-13

From `left_off.md` — clear the deck before new baselines.

- [x] Inventory `eval/retrieval/reports/` — **123 incomplete** (120 sqlite, 3 delta); **0 complete**
- [x] Discard locals like `baseline_b83bfa165853` (sqlite, single-intent, incomplete) — **deleted all 123 report JSONs**
- [x] d3230fa ablation JSONs — **deleted** (incomplete; not promotable); added `eval/retrieval/reports/*.json` to `.gitignore`
- [x] Confirm authoritative retrieval baseline still `baseline_299063e87806` in Delta — **PASS** (warehouse SQL 2026-07-13): `complete`, 49 intents, `uc13_ale:35034:2026-07-02`; local partial ids **not** in Delta; M-RE3 ablation matrix + FTA 16/18 + Legal 7/11 intact
- [ ] If you re-baseline after retrieval work, update README pins + `BASELINE_REF` everywhere — **defer to Phase 4**

---

## Phase 6 — Eval harness for all agents 【parallel track after Phase 3】

**Goal:** Same rigor as FTA/Legal for the other five agents.

### Framework (reproducible procedure)

- [ ] Draft a single script or skill: preflight → harness baseline → agent run → score → promote
- [ ] Source material: `eval/retrieval/README.md` (PHV validation, cluster baseline, ablation, record_e2e_linkage sections)
- [ ] Inputs frozen per run: `registry_hash`, `gold_snapshot`, `ingestion_snapshot`

### Golden checklists to create

| Agent | Starting point |
|-------|----------------|
| BMA | Scorecard smoke + output table schema; no checklist on disk yet |
| CQA | Same |
| KPI | Same |
| QoE | Same |
| Profiler | Same |

- [ ] Pick one agent; draft checklist markdown (mirror `eval/LCA/golden_checklist_elder_care.md` structure)
- [ ] Add structural pytest if useful (`tests/test_golden_checklist_*.py` pattern)
- [ ] Score on Elder Care cluster run; row in `.dev/scorecards/INDEX.md`
- [ ] Repeat for remaining four (can batch agent runs in one ~2 hr session if ingestion already warm)

### Baselines index

- [ ] Extend INDEX or new file: agent × company × score × `run_id` × date
- [ ] Clearsulting documented as thin corpus where scores are informational only

---

## Phase 7 — Data room completeness 【design then build】

**Goal:** “How complete is this data room?” before agents run.

- [ ] Define minimal checklist per overlay (healthcare first): doc types × workstreams
- [ ] Map to existing tables: `doc_relevance`, `chunks`, `ensure_coverage.get_coverage_report`
- [ ] Sketch output: `% complete`, missing list, confidence cap for bundle
- [ ] Prototype in notebook (8c-style) before productionizing
- [ ] Run on Elder Care vs Clearsulting — validate Clearsulting shows expected gaps

---

## Phase 8 — Executive summary / one-pager 【lower urgency】

- [ ] Rename TL;DR → Executive Summary in `databricks/agents/orchestrator/templates/tldr_one_pager*.j2`
- [ ] Review `pending.md` presentation experiment (more LLM-generated sections from same bundle)
- [ ] `to_also_think_about.md`: halt conditions, flow agent → one-pager → full report
- [ ] Re-render Elder Care sample; compare to `tldr_one_pager_v6.md` / `full_report.md`

---

## Phase 9 — Hector merge 【inventory first】

- [ ] List his repo URL / branch
- [ ] Diff: agents, notebook cells, eval artifacts, companies in SharePoint
- [ ] What he has that I lack vs what I have that he lacks
- [ ] Merge only after integration + retrieval baselines are stable
- [ ] Backfill scorecards and harness runs post-merge

---

## Quick reference

| What | Where |
|------|--------|
| Smoke attestation | `.dev/plans/uc13-m-phv3-integration/item23-post-merge-smoke-attestation.md` |
| T7 packet | `.dev/plans/uc13-m-phv3-integration/packets/T7.md` |
| Scorecards | `.dev/scorecards/INDEX.md` |
| Harness CLI | `python -m eval.retrieval.harness_cli run --help` |
| FTA checklist | RT7 / scorecards; 18 fields, floor 16/18 |
| Legal checklist | `eval/LCA/golden_checklist_elder_care.md`, floor 7/11 |
| Retrieval baseline pin | `baseline_299063e87806` |
| Open brain dumps | `pending.md`, `left_off.md`, `to_dive_deeper.md`, `to_also_think_about.md` |

---

## This week — minimal path

```
[ ] Phase 1 smoke          (~2 hr)  ← you are here (BLOCKING)
[ ] Phase 2 closeout       (laptop)
[ ] Phase 3 closing audit  (review)
[x] Phase 5 eval cleanup   (laptop, quick) — done 2026-07-13
[ ] Start Phase 4 planning if cluster time left (after Phases 1–3)
```

**Week success:** Phases 1–3 done. Everything else is carryover.

---

## Session log (fill as you go)

| Date | Phase | Commit SHA | run_id / notes | Pass? |
|------|-------|------------|----------------|-------|
| 2026-07-13 | 5 eval cleanup | d3230fa | Delta `baseline_299063e87806` confirmed; deleted 123 local incomplete report JSONs; gitignore reports | PASS |
| | 1 smoke | | | |
| | 2 push | | | |
| | 4 harness | | | |
| | 4 FTA/Legal | | | |
