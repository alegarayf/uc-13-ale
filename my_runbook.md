# My runbook — integration closeout → hardening finish

**For:** Alejandro only  
**Updated:** 2026-07-24  
**Companion:** `project_status_timeline.md` (PM-facing summary)

Use this as a **sequential checklist**. Each cluster block ≈ **2 hr** — batch them; don’t start a new block if the previous one failed.

---

## Milestone status (2026-07-24)

| Milestone | Status | Evidence |
|-----------|--------|----------|
| **M-PHV3** (integration) | **CLOSED** | Item 23 smoke PASS (qualified) `fe7d58f`; item 24 exit-gate PASS `f1da4ec` |
| **M-PHV4** (retrieval consolidation) | **CLOSED** | T1–T8 `08a5f86`→`fefcbc7`; cluster T8 2026-07-16; item 29 declined (PG5 fail); items 28/30 deferred |
| **M-PHV4 audit** (Phase 3) | **CLOSED** | `.dev/audits/2026-07-16-uc13-m-phv4-retrieval-consolidation.md` — `accepted-with-waivers` |
| **Eval harness all agents** (Phase 6) | **CLOSED** | M0–M4 on `dev2` → merged to `dev` 2026-07-24; M4 audit `.dev/audits/2026-07-21-uc13-eval-harness-all-agents-m4.md` — `accepted-with-waivers` |
| **Executive summary** (Phase 8) | **CLOSED** | 4/4 companies expanded synthesis `d06992a`; Rainmaker Rev2/Rev3 merged to `dev` 2026-07-24 |
| **Local git** | **`dev`** | `dev2` + `feat/exec-summary-rainmaker-restructure` merged 2026-07-24 |

**Open follow-ups (non-blocking):** none — BMA F2 closed 2026-07-24; Legal 9/11 PASS 2026-07-24 (post restrictive-merge fix).

---

## Rules of thumb

1. **Pin before every cluster session:** `git rev-parse HEAD`, notebook content SHA if you touched it, company=`Elder Care`, catalog=`uc13_ale`.
2. **Local first when cheap:** `pytest tests/test_catalog_convention.py -q` and full suite before any push.
3. **One attestation per run:** paste stdout verbatim; don’t paraphrase pass/fail.
4. **Don’t declare baselines authoritative** from sqlite or single-intent runs — promote to Delta or discard.
5. ~~**Retrieval code stays frozen** until integration smoke + closing audit are done.~~ **Lifted 2026-07-14** — M-PHV4 landed.
6. **Don’t cross-compare harness runs across registry versions** — `baseline_299063e87806` vs `baseline_1aeb0ace584a` raises `RegistryHashMismatchError` (intentional after `legal.insurance` fix).

---

## Phase 0 — Preflight (laptop, ~15 min)

- [x] `git status` clean or only intentional artifacts
- [x] On `dev` with `dev2` + Rainmaker branches merged — 2026-07-24
- [x] Re-run full suite after merge — **757 passed, 5 skipped** (2026-07-24)
- [x] Attestation template open: `.dev/plans/uc13-m-phv3-integration/item23-post-merge-smoke-attestation.md`
- [x] Cluster attached; Cell 0 pip done once per restart

---

## Phase 1 — Post-integration smoke 【BLOCKING · ~2 hr cluster】 ✅ DONE 2026-07-14 (qualified)

**Goal:** Prove ingestion + index sync + business model agent + `company_profile` read work on live infra.

**Notebook:** `databricks/jobs/notebooks/test_pipeline.ipynb`  
**Scope:** Parser path → BMA. Not a full seven-agent re-score.

### Run path (minimum)

- [x] Cell 1 — widgets: `sp_company_name=Elder Care`, `catalog=uc13_ale`, `llm_endpoint` Sonnet 4.6
- [x] Cell 8b — quick retrieval smoke (`RouteResult` — no `TypeError` on `.chunks`)
- [ ] Cell 7 — full parser rebuild → stdout must include **`✓ Index ready`** — **DEFERRED** (serverless OOM on 382-file vision parse; existing corpus used; qualified pass)
- [x] Cell 8 — chunk stats look sane
- [x] Cell 8c — coverage report; **8d only if gaps** — *8c not in executed path; 8d N/A*
- [x] Cells 9–10 — profiler + profile table (recommended)
- [x] Cell 11 — business model agent completes without traceback

**Pass:** Item 23 overall → PASS (qualified) — `fe7d58f`

---

## Phase 2 — Integration closeout (T7) 【laptop + git】 ✅ DONE 2026-07-14

- [x] Workflow YAML + exit gate item 24 — `f1da4ec`
- [x] Full suite green — 539 passed (T7)

---

## Phase 3 — Closing audit 【review session】 ✅ DONE 2026-07-16

- [x] Cold-read attestation + exit checklist + M-PHV3/M-PHV4 diffs
- [x] Auditor review on integration + PHV4 scope
- [x] Audit file: `.dev/audits/2026-07-16-uc13-m-phv4-retrieval-consolidation.md` — `accepted-with-waivers`
- [x] Waivers W1–W8 documented (see audit file)

---

## Phase 4 — Retrieval consolidation 【M-PHV4】 ✅ DONE 2026-07-16

- [x] Pin baseline: **`baseline_1aeb0ace584a`** (supersedes `baseline_299063e87806`)
- [x] FTA fallback + harness `dispatch_retrieval` → shared `fallback.py`
- [x] Cluster T8: FTA **16/18** · Legal **9/11** PASS (2026-07-24 re-score; was 7/11 CONDITIONAL on 7/16)
- [ ] Shared context assembly (charter item 28) — **DEFERRED**
- [ ] `workstream_tags.py` centralization (item 30) — **DEFERRED**

---

## Phase 4b — Metadata filter A/B 【optional】 ✅ DONE 2026-07-15

- [x] PG5 numeric bar **FAIL** — default stays `vs_metadata_filters=False`

---

## Phase 5 — Eval cleanup 【laptop】 ✅ DONE 2026-07-13

- [x] Delta authoritative baseline: **`baseline_1aeb0ace584a`**
- [x] Local report JSONs deleted; gitignored

---

## Phase 6 — Eval harness for all agents ✅ DONE 2026-07-21 (merged to `dev` 2026-07-24)

**Goal:** Same rigor as FTA/Legal for the other five agents.

- [x] Reproducible procedure — `eval/retrieval/README.md` unified 7-agent promotion-gate docs (M4-T1)
- [x] Golden checklists — BMA / CQA / KPI / QoE / Profiler (M1/M2)
- [x] `.dev/scorecards/INDEX.md` — five Elder Care `baseline_bootstrap` rows (M4-T8)
- [x] `evaluate_promotion` gate + `PromotionResult` (M3)
- [x] M4 audit — `.dev/audits/2026-07-21-uc13-eval-harness-all-agents-m4.md`

### Elder Care agent baselines (2026-07-21)

| Agent | Score | Gate |
|-------|-------|------|
| FTA | 16/18 | prior M-PHV2/M-RE3 |
| Legal | 9/11 PASS | prior M-PHV2/M-RE3; **9/11** post-fix 2026-07-24 (`.dev/scorecards/scorecard_lca_7_24_post_restrictive_fix_vs_7_16.md`) |
| BMA | 7/7 | `baseline_bootstrap` |
| CQA | 3/6 | `baseline_bootstrap` |
| KPI | 3/3 | `baseline_bootstrap` |
| QoE | 5/6 | `baseline_bootstrap` |
| Profiler | 7/7 | `baseline_bootstrap` |

**Follow-up:** ~~Reconcile BMA checklist file to 7/7 (M4 audit F2).~~ **DONE 2026-07-24** — `eval/BMA/golden_checklist_elder_care.md` reconciled to M4-T3 7/7; W-M4-1 closed.

---

## Phase 7 — Data room completeness 【design · pending】 ← **YOU ARE HERE**

- [ ] Define minimal checklist per overlay (healthcare first)
- [ ] Map to `doc_relevance`, `chunks`, `ensure_coverage.get_coverage_report`
- [ ] Prototype in notebook (8c-style)

---

## Phase 8 — Executive summary / one-pager ✅ DONE 2026-07-20 (+ Rainmaker Rev2/Rev3 merged 2026-07-24)

- [x] Rename TL;DR → Executive Summary in orchestrator templates
- [x] 4/4 portfolio companies expanded synthesis — `d06992a`
- [x] Rainmaker Rev2: `thesis_bullets`, `key_watchouts`, `workforce_notes`, Bucket A restructure
- [x] Rainmaker Rev3: Stage-6 prompt + compressed template alignment; Elder Care R3 ACCEPT (1344w)

---

## Phase 9 — Hector merge 【inventory first · pending】

- [ ] Inventory his repo vs yours; merge after audit + baselines stable

---

## Quick reference

| What | Where |
|------|--------|
| Smoke attestation | `.dev/plans/uc13-m-phv3-integration/item23-post-merge-smoke-attestation.md` |
| M-PHV3 exit gate | `.dev/plans/uc13-m-phv3-integration/exit-gate-checklist.md` |
| Harness baseline write-up | `harness-baseline-2026-07-15.md` |
| M-PHV4 audit | `.dev/audits/2026-07-16-uc13-m-phv4-retrieval-consolidation.md` |
| M4 eval-harness audit | `.dev/audits/2026-07-21-uc13-eval-harness-all-agents-m4.md` |
| FTA 7/16 scorecard | `.dev/scorecards/scorecard_7_16_post_phv4_vs_7_03.md` |
| Legal 7/16 scorecard | `.dev/scorecards/scorecard_lca_7_16_post_phv4_vs_7_03.md` |
| Scorecards index | `.dev/scorecards/INDEX.md` |
| Retrieval baseline pin | **`baseline_1aeb0ace584a`** |
| Promotion gate | `eval/retrieval/promotion_gate.py` |

---

## This week — minimal path

```
[x] Phase 1–5           — done
[x] Phase 3 audit       — done 2026-07-16
[x] Phase 6 eval harness — done 2026-07-21; merged to dev 2026-07-24
[x] Phase 8 exec summary — done; Rainmaker merged 2026-07-24
[ ] Phase 7 data room   ← you are here
```

**Remaining:** Phase 7 design

---

## Session log

| Date | Phase | Commit SHA | run_id / notes | Pass? |
|------|-------|------------|----------------|-------|
| 2026-07-13 | 5 eval cleanup | d3230fa | Deleted 123 incomplete report JSONs | PASS |
| 2026-07-14 | 1 smoke | d3230fa | Cells 0/1/8b/8/10/11; Cell 7 deferred (OOM) | PASS (qualified) |
| 2026-07-14 | 2 closeout | f1da4ec | T7 workflow YAML + exit gate; 539 pytest | PASS |
| 2026-07-15/16 | 4 cluster | ec74042→fefcbc7 | `baseline_1aeb0ace584a`; FTA 16/18 · Legal 7/11 CONDITIONAL | PASS (Legal CONDITIONAL) |
| 2026-07-16 | 3 audit | — | M-PHV4 audit `accepted-with-waivers` | PASS |
| 2026-07-20 | 8 exec summary | d06992a | 4/4 expanded executive summaries | PASS |
| 2026-07-21 | 6 eval harness | b2087b9 | M4 all five agents `baseline_bootstrap`; M4 audit `accepted-with-waivers` | PASS |
| 2026-07-24 | git merge | — | `dev2` + `feat/exec-summary-rainmaker-restructure` → `dev`; runbook updated | PASS |
| 2026-07-24 | closeout | acf4843→91b6b5f | BMA F2 7/7; Legal 9/11; W-M4-4 manifest spot-check; pushed `dev` | PASS |
