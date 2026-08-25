# UC-13 horizon map

Scouted 24 Aug 2026. Living index — not a second ledger. IDs live in `eval/program/product_backlog.yaml`, the Wave 4 charter/spec, and the M4 wave note.

**Now:** Wave 4, M4 of 8. Lab done (8/10 Elder Care fixes proven). Audit not run — that is the M5 gate. Two legal rows missed; claim 008 is new and unowned. M5–M8 defined, not planned. Beta→measurement parked (prod quiet since 3 Aug). No fine-tune track.

Companies: Elder Care · Clearsulting · GKF · SPG.

Need: **must** = Wave 4 cannot honestly finish, or a live unowned bug · **should** = high leverage / unblocks later, not on the charter critical path · **nice** = research, productization, later-wave.

---

## Overview — open / half-open / should-do

Closed M4 rows and standing rejects are **not** listed.

Status: **leftover** = unpaid from a finished slice · **pending** = chartered, not started · **deferred** = named later · **proposed** = not chartered, worth doing · **decide** = blocked on a call · **parked** = explicit non-goal with a hook · **blocked** = cannot start as-is

| Item | Status | Track | Need | Home | One line |
|---|---|---|---|---|---|
| M4 independent audit | leftover | Program | must | M5 entry | Lab closed; `audit_status: not_run`. Charter will not start M5 without this. |
| Spec Phase 2 cycle 3 (G0-soft) | pending | Program | must | every later M | `review_cycle: 3` still open. Soft gate, hard at M8 exit. |
| Phase 9 vs new wave | decide | Program | nice | after M8 | Charter ends at M8/G5. Beta wiring is not M8. |
| `eval-multi-company-coverage-expansion` plan | parked | Program | nice | **do not launch** | Still “ready for executor.” Active path is foldback M5–M7. |
| Ingestion-parser / eval-consolidation residuals | parked | Program | nice | verify first | Aug-14 checklists still say open. Do not silently absorb into M5. |
| `PB-legal_register-extraction-depth-contracts` | leftover | Legal | must | **unowned** | S2 1/35 (was 3/23). Bar missed. May be extraction, not retrieval — M8 does not rewrite prompts. |
| `PB-legal_register-retrieval-ip` | leftover | Legal | must | **unowned** | `ip_register` empty. 4 chunks, `retrieved_no_terms`, not corpus-absent. |
| Locator cascade must not revert | leftover | Legal | must | M8 constraint | T5 cascade landed; `derive_locator` HALT-31 + S2Writer guard untouched. |
| M8 Legal/KPI + D11 / GAP-108 | pending | Legal | must | M8 | Slug map; Legal S2 on three companies; replace GAP-109; G5 trust regen. |
| Elder Care Legal G1 4/11 regression | pending | Legal | must | M8 | Floor ≥9/11 (prior variance 7/11). Name a cause or re-ratify. |
| GAP-109 cross-company Legal/KPI weakness | pending | Legal | must | M8 replace | Distillation-era rationale still on the row. |
| Legal S2 failure taxonomy (retrieval vs extract vs schema) | proposed | Legal | should | before re-homing leftovers | Needed to decide prompt vs retrieval vs corpus. Not scheduled. |
| ESC-W4-1 KPI claim-level S2 | blocked | Legal | nice | Tier-3 spec | KPI not in `SURFACES`. M8 uses G1+corpus and states uncertainty. |
| `PB-exec_summary-008-locator-mismatch` | leftover | Exec | must | **unowned** | New M4 find. Wrong Pro Forma chunk vs page-46 Diligence Adjusted. |
| `PB-exec_summary-retrieval-scope-gap` | deferred | Exec | must | **M5 vs M7** | `spot_check` chunk-only; calibration already dual-source. 28/30 “unsupported” were evidence-path. |
| Dual-source evidence in **production** `spot_check` | proposed | Exec | should | same as scope-gap | Highest-leverage judge-prep. T12 wired calibration only. Same job as the row above if done once. |
| `PB-exec_summary-source-ref-mislabel` | deferred | Exec | nice | later | Presentation packet cites the wrong analysis table. |
| exec_summary S2 on GKF/SPG + Clearsulting dual-source re-run | parked | Exec | nice | after Wave 4 | Tied to scope-gap row. Explicit non-goal. |
| M5 Clearsulting 7/7 + promotion inputs | pending | Sign-off | must | M5 | Profiler re-run, 6 new checklists, scoring, e2e linkage. No plan yet. |
| M6 GKF 7/7 | pending | Sign-off | must | M6 | 7 new checklists (no FTA yet). Hub after M5. |
| M7 SPG 7/7 | pending | Sign-off | must | M7 | Completes G2 → M8 entry. |
| Profiler re-run Clearsulting / GKF / SPG | pending | Sign-off | must | M5–M7 | Stale evidence rule. Folded into each milestone. |
| Sampling-audit in wave manifest | pending | Sign-off | must | M5–M7 | Charter: ≥2 items/company. |
| `FU-M4-GATE` | leftover | Eval hygiene | must | M5 | Six committed-artifact pytest failures. |
| `FU-M4-MAP` | leftover | Eval hygiene | must | M5 pre-plan | Context-map SHA/content stale vs closure tree. |
| `FU-M4-TESTS` | leftover | Eval hygiene | must | M6 | D-M4-E leftovers → pytest. Must not slip past M6. |
| `FU-M4-CLONEGUARD` | leftover | Eval hygiene | should | **unscheduled** | In-tree 6 fail vs worktree 8 fail (`.dev/` gitignored). Named in the run, missing from wave-note table. |
| Architecture `INDEX.md` version lag | leftover | Eval hygiene | should | unowned | Files at 1.4/1.5; INDEX still 1.0 / 3 Aug. |
| Stale agent outputs / T2 artifacts post-M4 ingest | parked | Eval hygiene | should | M5+ | Re-run agents before scoring those companies. |
| `PB-fta_numeric-post-m4-chunk-citation-drift` | parked | Eval hygiene | nice | instrument | Leave open — detects chunk relocation after T6. |
| Slice recomposition (`eval/retrieval/slices/*.yaml`) | pending | Retrieval | must | M5 | M4 refreshed pins only. |
| Per-pass `vs_metadata_filters=True` canary | proposed | Retrieval | should | leftover design | Global A/B failed. IP pass with filters on retrieved 4 LEGAL chunks. |
| Debug `legal.litigation` 5.88pp A/B drop | proposed | Retrieval | should | before 2nd global canary | Necessary if filters are revisited. |
| SPG residual `filename_closure` gold (3 intents) | deferred | Retrieval | nice | adjacent | Not a Wave 4 checkpoint. |
| 1-week `route_chunks` vs `semantic_search` A/B | proposed | Retrieval | nice | research | Same extract prompt; kill if recall/citations/runtime lose. |
| Ingest-time structured digests | proposed | Retrieval | nice | research | Skip VS; citation-anchor risk. |
| ReAct / gap-driven retrieval | proposed | Retrieval | nice | research | Kill if cost >2× or >30% max-round without extract. |
| Cross-encoder rerank / BM25 hybrid | deferred | Retrieval | nice | after ablation plateau | Trigger: >5pt Recall@10 PHV cannot explain. |
| Contextual prefix at ingest | proposed | Retrieval | nice | research | Route B omitted this. |
| Worst-intent ablation post-M4 corpus | proposed | Retrieval | nice | research | Global `merge_rank_off` already rejected. |
| Cross-company FTA variance (SPG vs Clearsulting) | proposed | Retrieval | nice | research | Corpus/ingest profile before blaming the model. |
| Keyword-fallback vs semantic-only A/B | proposed | Retrieval | nice | research | Fallback rate attested; never formally killed. |
| M3 discriminative exec_summary probe | leftover | Calibration | should | **unscheduled** | Sample cannot honestly hit P2 (~5 non-supported vs ~12 needed). |
| Claim 026 label drift | parked | Calibration | should | before next P2 | Sample `supported` vs backfill `contradicted`. Do not relabel to manufacture balance. |
| CHK-27 + judge harness | parked | Calibration | nice | after Wave 4 | Descoped at M3. Only if probe+recal pass **and** operator authorizes. |
| Spec O4 fta_numeric degenerate floor | deferred | Calibration | nice | trigger-gated | 30/30 `supported`. |
| GAP-102 per-company G1 floors | blocked | Calibration | nice | after M8 | Blocked on M8 reporting. Not M8’s job. |
| Phase A — is beta alive? | proposed | Beta | should | **cheap parallel** | Last full diligence 3 Aug; CIM preview 20 Aug. Not being done. Does not block M5. |
| Which button beta hits (Rainmaker job vs `run_vdr_pipeline.py`) | proposed | Beta | should | Phase A | Job-path warning in `databricks/CLAUDE.md`. Necessary and not being done. |
| Phase B — wire runs into measurement | proposed | Beta | nice | after first real run | Stages 1–2 of the quality loop are disconnected. |
| Phase C — feedback → same backlog as M4 | proposed | Beta | nice | after B | Form + weekly triage + re-run before “fixed.” |
| Phase D — new beta companies, same bar | parked | Beta | nice | after M5–M7 | Explicit Wave 4 non-goal. |
| Is production the official beta home? | decide | Product | should | — | If yes, lab-only proof ≠ “fixed for stakeholders.” |
| CIM preview vs full diligence as separate products? | decide | Product | should | — | Never mix preview scores with full-diligence trust. |
| Feedback channel (form vs Slack) | decide | Product | nice | — | Must tie to a run. |
| Garden UI + auth for `analysis.*` | proposed | Product | nice | after Wave 4 | Blocks productization. Older architecture Q. |
| Cross-Analysis Agent (CIM vs data room) | proposed | Product | nice | after Wave 4 | Austin Phase 4. No module today. |
| Orchestrator Phase 5 pack (memo/deck/grids/tracker) | proposed | Product | nice | after Wave 4 | Only `md_to_word` exists. Deck/PDF out of scope. |
| Human-in-the-loop deal memory | proposed | Product | nice | later | Overrides, accepted flags, cross-deal benchmarks. |
| Highlight newly added VDR files | proposed | Product | nice | low priority | Client ask. Analysis quality first. |
| Data-room completeness scorecard | proposed | Product | nice | later | Thin rooms (Clearsulting Legal 0 classified docs). |
| Agent-quality A-03 / A-07 / A-09 | deferred | Product | nice | later wave | M2 sized ~52 registry rows; Wave 4 does not execute them. |
| Genie chatbot product fate | decide | Product | nice | — | `genie_rules.py` exists; product call never made. |
| Confidence-score distributions | proposed | Analysis | should | **unscheduled** | **Was missing from this map.** Histograms of `section_confidence`, citation confidence, retrieval/extract scores — by agent, company, surface. Calibrate whether “high” means anything. |
| System walkthrough (how a run actually flows) | proposed | Analysis | should | **unscheduled** | **Was missing.** Coupling surfaces, warehouse tables, contracts, agent DAG. Understanding, not a milestone. |
| CIM-only vs full-VDR substantiation study | proposed | Analysis | should | **in flight ~21–24 Aug** | Which claims need non-CIM docs. User-originated. Not in charter. |
| Corpus / gold / recall-artifact EDA | proposed | Analysis | nice | **unscheduled** | **Was missing.** Gold-size vs recall@10, chunk-length dist, company completeness. Explains the ~4% recall@10 artifact. |
| Judge vs human disagreement slices | proposed | Analysis | nice | **unscheduled** | **Was missing.** Where M3 failed: evidence path vs judge vs label. |
| `FU-M4-PINKEY` stable gold locator | deferred | Ingest/infra | should | later | Pins on `chunk_id` UUID → every re-parse rebuilds the M4 ladder. |
| `uc13_ale` embeddings_index gaps | leftover | Ingest/infra | should | unowned | Missing in probes. Necessary; not on Wave 4. |
| `pipeline_thread_id` / `ensure_coverage` in workflow | leftover | Ingest/infra | should | unowned | Thread attribution open; coverage still notebook-only. |
| `FU-M4-TRACK` un-ignore `.dev/` | deferred | Ingest/infra | nice | later | Declined; SHA pins ratified. Auditor needs working tree, not a clone. |
| Unified eval CLI | deferred | Ingest/infra | nice | GAP-105 | Harness/G1/e2e/spot-check still fragmented. CI bundle **accepted out of scope**. |
| Cell 7 full parser rebuild | parked | Ingest/infra | nice | needs approval | AGENTS.md safety rail. Vision parse unreliable on serverless. |
| Bootstrap `file_name` vs `doc_id` join | deferred | Ingest/infra | nice | next gold rebootstrap | Live probe 18 Aug: 0 divergence. |
| Hector T8/T9 leftover | deferred | Ingest/infra | nice | later | T1–T7 landed. Notebook + bridge packets ready. Not Wave 4. |
| Company inventory + ingest ranker | proposed | Ingest/infra | nice | before next new company | Rank SharePoint completeness first. |
| QoE Llama vs Sonnet A/B | proposed | Models | nice | research | QoE still defaults Llama in one path. Cheap. |
| Fine-tune / SFT / LoRA | proposed | Models | nice | **no track** | Nothing in repo trains weights. Treat as a **new program**, not a Wave 4 leftover. |
| Dataset / pre-training “all-company baseline” | parked | Models | nice | registry only | Never wired to gold or promotion. |

---

## Stats by track

**Pace:** 1 day ≈ Wave 4 charter **M1 through M4 as executed** (retrieval loop + ledger + calibration honesty + 8/10 product fixes with wet re-runs). You said that’s a conservative day; maybe more fits. **1 sprint = 10 working days.** Estimates are order-of-magnitude at that pace, about ±50%. They assume the same agent-heavy style, not solo-from-scratch.

**Essential** = `must` rows (Wave 4 honest finish + unowned live bugs). **Complete** = essential + should + nice, **excluding** SFT/LoRA/pre-training (those are a separate program, not a leftover). Dual-source `spot_check` is not double-counted with the scope-gap row.

| Track | Items | Must | Should | Nice | Essential | Complete |
|---|---:|---:|---:|---:|---|---|
| Program | 5 | 2 | 0 | 3 | 0.3d · 0.03 spr | 0.6d · 0.06 spr |
| Legal | 8 | 6 | 1 | 1 | 1.2d · 0.12 spr | 1.6d · 0.16 spr |
| Exec | 5 | 2 | 1 | 2 | 0.5d · 0.05 spr | 0.7d · 0.07 spr |
| Sign-off | 5 | 5 | 0 | 0 | 1.5d · 0.15 spr | 1.5d · 0.15 spr |
| Eval hygiene | 7 | 3 | 3 | 1 | 0.6d · 0.06 spr | 1.1d · 0.11 spr |
| Retrieval | 12 | 1 | 2 | 9 | 0.2d · 0.02 spr | 1.6d · 0.16 spr |
| Calibration | 5 | 0 | 2 | 3 | — | 0.8d · 0.08 spr |
| Beta | 5 | 0 | 2 | 3 | — | 1.0d · 0.10 spr |
| Product | 11 | 0 | 2 | 9 | — | 2.2d · 0.22 spr |
| Analysis | 5 | 0 | 3 | 2 | — | 1.5d · 0.15 spr |
| Ingest/infra | 9 | 0 | 3 | 6 | — | 1.2d · 0.12 spr |
| Models (serving A/B only) | 1 | 0 | 0 | 1 | — | 0.2d · 0.02 spr |
| **Wave 4 honest finish (must)** | **18** | **18** | — | — | **~4.3d · ~0.4 spr** | — |
| **Prudent (must + should)** | **~32** | 18 | ~14 | — | — | **~6.5d · ~0.7 spr** |
| **Everything on this map except SFT** | **78** | 18 | ~16 | ~44 | — | **~13d · ~1.3 spr** |

SFT / LoRA / pre-training: **not in those totals.** That is a new program (data, labels, training loop, eval). Weeks-to-a-wave, not a leftover.

**Read of the numbers:** at the M1–M4-per-day pace, **what you actually need** (M4 close + M5–M8 + unowned bugs) is **under half a two-week sprint**. Adding the “should” pile (beta pulse, conf-score dist, system walkthrough, CIM vs VDR, probe, CLONEGUARD, PINKEY) still **fits in one sprint**. The long tail is optional research and productization — another sprint if you want all of it, not if you want Wave 4 done.

Analysis was **not** in the first map. It is now a track: confidence-score distributions, system-flow understanding, CIM vs VDR, corpus/gold EDA, judge-vs-human slices. None of that is `must` for the charter; the first three are `should` if the goal is to understand the system rather than only close milestones.

---

## Suggested sequence

Cheap checks beside the spine. Research beside both. Do not serialize everything.

1. Invoke M4 auditor.
2. Phase A + which-button in parallel. Conf-score dist + system walkthrough can start the same day — they do not block M5.
3. Home the two legal rows + claim 008 (M4-tail vs M8 vs named FU).
4. Resolve scope-gap owner (M5 vs M7) and whether CLONEGUARD is official.
5. M5 hygiene: GATE, MAP, slices. Then Clearsulting.
6. M6 GKF + TESTS.
7. M7 SPG (+ dual-source `spot_check` if that is M7).
8. M8 legal/KPI + D11. Do not revert T5 locator cascade. KPI stays G1+corpus unless ESC-W4-1 is amended.
9. Then Phase 9 vs new wave (beta wiring, CIM vs VDR product, Garden).
10. Parallel: PINKEY, discriminative probe, per-pass VS filters, CIM-vs-VDR study, legal S2 taxonomy. Do not reopen `merge_rank_off`, global metadata filters, or BMA two-pass.

---

## Wave 4 spine

| ID | Intent | Status |
|---|---|---|
| M1 Retrieval loop | Measured; `merge_rank_off` rejected. Elder Care evidence superseded by M4 CIM re-parse. | done |
| M2 Ledger truth-up | Registry sized. Sized ≠ scheduled. | done |
| M3 Calibration honesty | Honest fail. Promotion inadmissible. Probe still owed. | done |
| M4 Product fixes | 8/10 closed on Elder Care. Audit not run. | lab closed · audit open |
| M5 Clearsulting 7/7 | Absorbs GATE / MAP / slices. | not started |
| M6 GKF 7/7 | Absorbs TESTS. | not started |
| M7 SPG 7/7 | Completes G2. | not started |
| M8 Legal/KPI root cause | D11, Legal S2 ×3, GAP-109 replace, G5. “W5” in charter = this, not a later program. | not started |

---

## Already run — do not reopen

| Experiment | Result |
|---|---|
| Route B vs A | A rejected (1/18 FTA). Semantic + merge-rank stays. |
| Merge-rank 4 arms + M1 `off` × 4 companies | `sim × tier` won; all `off` gates failed. |
| Global `vs_metadata_filters` A/B | Failed PG5. Default False. Per-pass canary survived. |
| BMA two-pass / Haiku extract | Quality loss; 8k cap cannot fill schema. Sonnet, one call. Standing merge reject. |
| M3 exec_summary calibration | P2/P4 fail. Human rung. Registry 0.857 is stale — not upgrade evidence. |
| M4 wet re-runs | 8/10 closed. |

**No SFT/LoRA program exists.** Calibration here means sample power + relative thresholds, not training a judge.

---

## Standing rejects

BMA two-pass · `merge_rank_off` as default · global metadata filters on · Route A for batch diligence · relabel unverifiable exec_summary claims to manufacture P2 · cross-epoch recall compares · “judge verified the report” from M2/M3 figures.

---

## Contradictions to resolve first

1. `eval_next_steps.md` says M4 in progress; wave note says lab complete, audit not run.
2. Charter exit = 10 closures; T12 closed 8; charter not amended.
3. Scope-gap owner: M4 non-goals say M7; spec §2.2 says M5.
4. CLONEGUARD named in the run, absent from the wave-note follow-up table.
5. T13 brief is a HALT (6 vs 8 fails); T13-ter is complete. Clone issue is not gone.
6. Legal IP: T9 `no_chunks` vs T9-bis 4 chunks `retrieved_no_terms`; exemption file does not exist.
7. Extraction-depth called retrieval at T3; S2 got worse after retrieval widening.
8. Claim 008 “is not M7” and “file as M7 variant” both appear.
9. Charter still says verifier is M8-only; D-M4-B already edited it. Wave note is binding.
10. Older multi-company coverage plan still “ready for executor.” Active path is M5–M7.

**Highest-leverage gap:** two missed legal rows + claim 008 have no owning milestone. Dual-source `spot_check` is labeled M5 and M7. Until those get a home, M5 planning will swallow or drop them.

---

## First decisions to record here

1. M4 audit: invoke / waive / accept-with-waivers.
2. Home for the two legal rows + 008.
3. Scope-gap owner (M5 vs M7).
4. Phase A in parallel with M5? (recommended: yes, cheap.)
5. CLONEGUARD: official FU or run footnote?
6. Phase 9 vs new wave — can wait until M8 is in sight.

Sources: `.dev/` plans/specs/wave notes/handoffs/pending; tracked ledgers; `eval_next_steps.md`; git (~200 commits); recent transcripts (beta loop, CIM vs VDR). Older pending checklists are listed as parked, not silently promoted into M5.
