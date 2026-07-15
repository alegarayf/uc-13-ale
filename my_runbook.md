# My runbook — integration closeout → hardening finish



**For:** Alejandro only  

**Updated:** 2026-07-15  

**Companion:** `project_status_timeline.md` (PM-facing summary)



Use this as a **sequential checklist**. Each cluster block ≈ **2 hr** — batch them; don’t start a new block if the previous one failed.



---



## Milestone status (2026-07-15)



| Milestone | Status | Evidence |

|-----------|--------|----------|

| **M-PHV3** (integration) | **CLOSED** | Item 23 smoke PASS (qualified) `fe7d58f`; item 24 exit-gate PASS `f1da4ec`; pushed to `origin/dev` |

| **M-PHV4** (retrieval consolidation) | **CLOSED (code)** · cluster regression open | T1–T6 landed `08a5f86`→`50aad12`; item 29 declined (PG5 bar fail); items 28/30 deferred |

| **Closing audit** (Phase 3) | **OPEN** | §8 adversarial audit scheduled post-orchestrator — no `.dev/audits/*-integration-closeout.md` yet |

| **Local git** | **3 commits ahead of `origin/dev`** | `50aad12`, `a3ff631`, `76c38e5` not pushed (PHV4 closeout + pre-audit) |



---



## Rules of thumb



1. **Pin before every cluster session:** `git rev-parse HEAD`, notebook content SHA if you touched it, company=`Elder Care`, catalog=`uc13_ale`.

2. **Local first when cheap:** `pytest tests/test_catalog_convention.py -q` and full suite before any push.

3. **One attestation per run:** paste stdout verbatim; don’t paraphrase pass/fail.

4. **Don’t declare baselines authoritative** from sqlite or single-intent runs — promote to Delta or discard.

5. ~~**Retrieval code stays frozen** until integration smoke + closing audit are done.~~ **Lifted 2026-07-14** — M-PHV4 T1–T5 landed; Phase 3 audit still recommended before more retrieval work.



---



## Phase 0 — Preflight (laptop, ~15 min)



- [x] `git status` clean or only intentional artifacts — *only `left_off.md` modified locally (2026-07-15)*

- [ ] On `dev`, synced with `origin/dev` — **3 commits ahead** (`76c38e5` vs `origin/dev` `0de1fc3`)

- [x] `pytest tests/test_catalog_convention.py -q` → green (44 passed, 2026-07-15)

- [ ] Optional full suite if you changed anything since last green run — *last recorded: 539 passed at T7*

- [x] Attestation template open: `.dev/plans/uc13-m-phv3-integration/item23-post-merge-smoke-attestation.md`

- [x] Cluster attached; Cell 0 pip done once per restart — *2026-07-14 smoke session*



**Record in attestation before run:**



```

Commit SHA at smoke run: d3230fa9aa22aeb2051144d43f5742fb8d90a066

Cluster date (UTC): 2026-07-14

```



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

- [x] Cells 9–10 — profiler + profile table (recommended) — *Cell 10 executed*

- [x] Cell 11 — business model agent completes without traceback



### Pass criteria



- [ ] No `IndexSyncError` on Cell 7 — **N/A** (Cell 7 deferred per qualification)

- [x] BMA `main()` finished

- [x] `company_profile` for Elder Care **row count > 0** in `uc13_ale.classification.company_profile`

- [x] Explicit line in attestation: *company_profile reads for BMA return non-empty, correctly-catalogued data: PASS*



### Fill attestation



- [ ] Paste Cell 7 stdout excerpt (`✓ Index ready`) — **N/A** (deferred)

- [x] Paste Cell 11 stdout excerpt

- [x] Set **Item 23 overall** → PASS (qualified) — `fe7d58f` / attestation complete

- [x] Notebook content SHA at run — `ce094a4b8b3e046253fc876712531792a0b9ff89` (unchanged)



### HALT — do not proceed to Phase 2 if



- ~~Cell 8b throws on `RouteResult` unpacking~~ — PASS

- ~~Cell 7 missing `✓ Index ready`~~ — waived (qualified deferral; M-PHV3 did not touch parser)

- ~~BMA fails on catalog / `company_profile` SQL~~ — PASS

- ~~You pushed new commits after this SHA without re-smoking~~ — T7 push included smoke SHA + hygiene only



---



## Phase 2 — Integration closeout (T7) 【laptop + git】 ✅ DONE 2026-07-14



**Goal:** Formal exit so retrieval work is allowed.



### Code / docs



- [x] Fix 5 stale `python_file` names in `databricks/workflows/uc13_ingestion_pipeline.yml` (drop `00_`, `01_`, etc. prefixes) — `f1da4ec`

- [x] Match names in `databricks/workflows/README.md`

- [x] Verify: `grep` for old `0[0-9]_setup_vector_search` etc. → no hits (verified 2026-07-15)

- [x] Create `.dev/plans/uc13-m-phv3-integration/exit-gate-checklist.md` — item 24 **PASS**

- [x] Append `CHANGELOG.MD` M-PHV3 entry

- [x] Touch `.dev/architecture/rallyday/` housekeeping if anything changed (module-map, changelog, etc.)



### Git sync



- [x] Re-run Genie parity: `git diff origin/dev..HEAD -- backend-ai/app/services/genie_rules.py` → empty (at T7)

- [x] **User go-ahead** then push: sync `dev` to `origin/dev` — T7 second PG2 push landed `f1da4ec` era

- [x] Confirm smoke SHA is what got pushed (no commits between smoke and push except T7 hygiene) — smoke `d3230fa`



### Tests



- [x] `pytest tests/test_catalog_convention.py -q`

- [x] Full suite green before push — 539 passed, 10 skipped (T7)



**Follow-up:** push remaining 3 local commits (`50aad12` PHV4 closeout + pre-audit) when ready.



---



## Phase 3 — Closing audit 【review session · can same day as Phase 2】 ← **YOU ARE HERE**



**Goal:** Close the loop validation started in early July; integration gets its own sign-off.



- [ ] Cold-read attestation + exit checklist + T3–T5 diffs

- [ ] Run auditor skill / big-model review on integration scope (not full re-validation of all agents)

- [ ] Write `.dev/audits/2026-07-__-uc13-integration-closeout.md` (or similar) with `audit_status: clean` or `accepted-with-waivers`

- [ ] Note any waivers by name — don’t silently carry gaps into retrieval work



**Waivers to document:** Cell 7 parser rebuild deferred (qualified); BMA LLM truncation (out of scope); no workflow YAML `python_file` pytest (T7 adversarial gap).



**Gate:** Retrieval consolidation **code already landed** (M-PHV4); formal audit still recommended before further retrieval work.



---



## Phase 4 — Retrieval consolidation 【M-PHV4 · code DONE · cluster regression OPEN】



**Goal:** First changes to `retrieval.py`, `fallback.py`, `context_utils.py` + regression proof.



### Before coding



- [x] Read charter stub for “Retrieval consolidation” in `.dev/specs/pipeline/uc13_pipeline_hardening_milestone_charter.md`

- [x] Pre-plan / context map if you use the orchestrator workflow — `.dev/plans/uc13-m-phv4-retrieval-consolidation/`

- [x] Pin baseline: **`baseline_299063e87806`** (Elder Care / `uc13_ale`)



### Work packages (in rough dependency order)



- [ ] Shared context assembly (OPEX pool / revenue / EBITDA budgets — see `to_dive_deeper.md`) — **DEFERRED** (charter item 28)

- [x] FTA fallback → shared `fallback.py` (13 call sites) — T2 `22d91f4`

- [x] Harness `dispatch_retrieval` → shared `fallback.py` (Surface 11) — T3 `dc86baf`

- [x] `_TYPE_ORDER` dedup across `retrieval.py` / `context_utils.py` — T1 `08a5f86`

- [x] Join-integrity preflight doc + guard — T4 `9e39ff7` (`tests/test_join_integrity.py` + README § R-08)

- [x] Optional: metadata filter A/B (Phase 4b below) — operator runs 2026-07-15; activation declined



### Cluster regression 【~2 hr each; plan multiple sessions】 ← **still open**



- [x ] `apply_ops_ddl("uc13_ale")` if DDL changed — *no DDL changes in M-PHV4*

- [x ] G2 probe — `company_name` pushdown still accepted (no “VS filter pushdown unavailable”)

- [ ] Full harness baseline: `python -m eval.retrieval.harness_cli run --store-backend delta --run-type baseline --company-name "Elder Care" --catalog uc13_ale`

- [ ] Compare vs `baseline_299063e87806` — no recall regression on gate-eligible intents

- [ ] FTA Cell 12 re-score → target **≥ 16/18**

- [ ] Legal Cell 16 re-score → target **≥ 7/11** pass on `eval/LCA/golden_checklist_elder_care.md`

- [ ] `record_e2e_linkage` for FTA + Legal pipeline `run_id`s if you re-ran them



**Done when:** harness compare clean, FTA/Legal floors hold, assembly unit tests green, audit for this phase.



**M-PHV4 program exit:** T6 housekeeping `50aad12` records items 25–27 + Surface 11 landed; item 29 not activated; items 28/30 deferred. Unit tests green; cluster re-attestation deferred per T3 adversarial gap.



---



## Phase 4b — Metadata filter A/B 【optional · ~4 hr cluster · 2 runs】 ✅ DONE 2026-07-15



Only needed if you want filters **on** in production. Hardening can finish with them **off**.



- [x] Runbook: `eval/retrieval/README.md` § “R-02 manual A/B”

- [x] Run A: `vs_metadata_filters=False` (control) — `enhancement_b079befc8b38`

- [x] Run B: `vs_metadata_filters=True` — `enhancement_3c397f54d016`

- [x] Record both `run_id`s + per-intent recall@10 — README hub filled `a3ff631`

- [x] Bar: no gate-eligible intent drops >5pp; aggregate recall non-decreasing — **FAIL** (5.88pp `legal.litigation`; aggregate −0.07pp)

- [x] **Second reviewer** (not you) signs off — **waived for M-PHV4 exit**; packet sent (`.dev/attestations/m-phv4-r02-second-reviewer-packet-2026-07-15.md`)

- [x] If bar fails: document and leave default `False` — still valid exit — attestation + README hub complete



---



## Phase 5 — Eval cleanup (leftover partial runs) 【laptop + maybe 1 cluster】 ✅ DONE 2026-07-13



From `left_off.md` — clear the deck before new baselines.



- [x] Inventory `eval/retrieval/reports/` — **123 incomplete** (120 sqlite, 3 delta); **0 complete**

- [x] Discard locals like `baseline_b83bfa165853` (sqlite, single-intent, incomplete) — **deleted all 123 report JSONs**

- [x] d3230fa ablation JSONs — **deleted** (incomplete; not promotable); added `eval/retrieval/reports/*.json` to `.gitignore`

- [x] Confirm authoritative retrieval baseline still `baseline_299063e87806` in Delta — **PASS** (warehouse SQL 2026-07-13): `complete`, 49 intents, `uc13_ale:35034:2026-07-02`; local partial ids **not** in Delta; M-RE3 ablation matrix + FTA 16/18 + Legal 7/11 intact

- [ ] If you re-baseline after retrieval work, update README pins + `BASELINE_REF` everywhere — **defer until Phase 4 cluster regression**



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

| M-PHV3 exit gate | `.dev/plans/uc13-m-phv3-integration/exit-gate-checklist.md` (item 24 PASS) |

| T7 packet | `.dev/plans/uc13-m-phv3-integration/packets/T7.md` |

| R-02 A/B attestation | `.dev/attestations/m-phv4-r02-vs-metadata-filters-ab-elder-care-2026-07-15.md` |

| R-02 reviewer packet | `.dev/attestations/m-phv4-r02-second-reviewer-packet-2026-07-15.md` |

| Scorecards | `.dev/scorecards/INDEX.md` |

| Harness CLI | `python -m eval.retrieval.harness_cli run --help` |

| FTA checklist | RT7 / scorecards; 18 fields, floor 16/18 |

| Legal checklist | `eval/LCA/golden_checklist_elder_care.md`, floor 7/11 |

| Retrieval baseline pin | `baseline_299063e87806` |

| Open brain dumps | `pending.md`, `left_off.md`, `to_dive_deeper.md`, `to_also_think_about.md` |



---



## This week — minimal path



```

[x] Phase 1 smoke          (~2 hr)  — PASS (qualified) 2026-07-14

[x] Phase 2 closeout       (laptop) — T7 done 2026-07-14

[ ] Phase 3 closing audit  (review) ← you are here

[x] Phase 4 code (M-PHV4)  (laptop) — T1–T6 done 2026-07-14/15

[x] Phase 4b A/B           (cluster) — done 2026-07-15; activation declined

[ ] Phase 4 cluster regression (~2 hr) — harness compare + FTA/Legal re-score

[x] Phase 5 eval cleanup   (laptop) — done 2026-07-13

```



**Week success (revised):** Phases 1–2 done; M-PHV4 code + A/B done. **Remaining:** Phase 3 audit, Phase 4 cluster regression, push 3 local commits.



---



## Session log (fill as you go)



| Date | Phase | Commit SHA | run_id / notes | Pass? |

|------|-------|------------|----------------|-------|

| 2026-07-13 | 5 eval cleanup | d3230fa | Delta `baseline_299063e87806` confirmed; deleted 123 local incomplete report JSONs; gitignore reports | PASS |

| 2026-07-14 | 1 smoke | d3230fa | Cells 0/1/8b/8/10/11; Cell 7 deferred (OOM); item 23 PASS (qualified) | PASS |

| 2026-07-14 | 2 closeout | f1da4ec | T7 workflow YAML + exit gate item 24; 539 pytest; Genie parity empty | PASS |

| 2026-07-14 | 4 code | 08a5f86→dc86baf | M-PHV4 T1–T4: type order, FTA fallback, harness fallback, join-integrity | PASS |

| 2026-07-15 | 4b A/B | 0de1fc3 | A `enhancement_b079befc8b38` / B `enhancement_3c397f54d016`; PG5 bar fail; default stays False | PASS (decline) |

| 2026-07-15 | 4 closeout | 50aad12 | M-PHV4 T6 housekeeping; items 28/30 deferred; README hub `a3ff631` | PASS |

| | 3 audit | | | |

| | 4 harness | | post-M-PHV4 cluster regression | |

| | 4 FTA/Legal | | re-score after consolidation | |


