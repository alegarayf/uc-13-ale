# UC-13 horizon map

Scouted 24 Aug 2026. **Refreshed 26 Aug 2026** after M5–M8 landed. Living index — not a second ledger. IDs live in `eval/program/product_backlog.yaml`, the Wave 4 charter/spec, and the M8 findings (`.dev/plans/eval-signal-foldback-m8-root-cause/artifacts/T4-root-cause-findings.md`).

**Now:** Wave 4 charter spine is **done** (M1–M8). Investigation closed; product leftovers are unowned. Live Elder Care Legal is **8/11** (not 4/11). Iterate pack is **10 closable product items** (6 already on the backlog, 4 not filed). Beta→measurement still parked. No fine-tune track.

Companies: Elder Care · Clearsulting · GKF · SPG.

Need: **must** = live unowned product bug, or a standing constraint that must not regress. Wave 4 cannot “honestly finish” as a *product* story until the iterate pack has a home — the *charter* already exited. **should** = high leverage / unblocks later. **nice** = research, productization, later-wave.

---

## Overview — open / half-open / should-do

Closed M4 rows, closed M5–M8 charter work, and standing rejects are **not** listed as pending. Done spine is in **Wave 4 spine** and **Already run**.

Status: **leftover** = unpaid from a finished slice · **pending** = chartered, not started · **deferred** = named later · **proposed** = not chartered, worth doing · **decide** = blocked on a call · **parked** = explicit non-goal with a hook · **blocked** = cannot start as-is

| Item | Status | Track | Need | Home | One line |
|---|---|---|---|---|---|
| Spec Phase 2 cycle 3 (G0-soft) | leftover | Program | should | after Wave 4 | Still `review_cycle: 3` / `phase2_review`. M8 exited on a recorded operator waiver. Not a product row. |
| Phase 9 vs new wave | decide | Program | nice | **now** | Charter ended at M8/G5. Next home for the iterate pack, beta wiring, or a new wave. |
| `eval-multi-company-coverage-expansion` plan | parked | Program | nice | **do not launch** | Still “ready for executor.” Foldback M5–M7 already did the live path. |
| Ingestion-parser / eval-consolidation residuals | parked | Program | nice | verify first | Aug-14 checklists still say open. Do not silently absorb into the iterate pack. |
| `PB-legal_register-extraction-depth-contracts` | leftover | Legal | must | **unowned** | S2 bar missed (1/35 vs 3/23). G1 t4c/coc recovered at 8/11; S2 did not. Extraction, not retrieval. |
| `PB-legal_register-retrieval-ip` | leftover | Legal | must | **unowned** | `ip_register` empty. Chunks retrieved, `retrieved_no_terms`. **Amend kind** — row still says `corpus_gap`. |
| Locator cascade must not revert | leftover | Legal | must | standing | M4 T5 cascade landed; M8 did not touch it. `derive_locator` HALT-31 + S2Writer guard stay. |
| `PB-legal_register-claim-failure-gkf` | leftover | Legal | must | **unowned** | Filed M8. S2 14/28. Locators resolved; quotes miss chunks. Employment / insurance / privacy. |
| `PB-legal_register-claim-failure-spg` | leftover | Legal | must | **unowned** | Filed M8. S2 1/5. Same quote-vs-chunk class. |
| KPI overlay-aware G1 scorer (A-09) | proposed | Legal | must | **add to backlog** | `score_kpi()` is healthcare-hardcoded. Ignores Clearsulting `tech_services` (8 keys) and GKF `consumer`. Not a VDR hole. |
| Elder Care Legal residual (founder + privacy) | proposed | Legal | must | **add to backlog** | Live 8/11 miss. `retrieved_no_terms` / privacy 4 of 5. Same class as GAP-103, not the Wave-2 empty-flag collapse. IP is the row above — do not add a third IP ticket. |
| SPG Legal extract on a fat corpus | proposed | Legal | must | **add to backlog** | G1 **1/11** with **181** LEGAL docs. `retrieved_no_terms` on t4c/coc/restrictive/vendor/platform. Distinct `closes_when` from the S2 1/5 row. |
| SPG KPI scored-block thinness (4/7) | proposed | Legal | must | **add to backlog** | Overlay *matches* healthcare. Three empty scored fields. Not A-09. Residual: corpus-absent vs extracted-absent until KPI S2 exists. |
| Legal S2 failure taxonomy (retrieval vs extract vs schema) | proposed | Legal | should | before re-homing leftovers | One-shot diagnostic, then throw away. Not a fifth product row. |
| ESC-W4-1 KPI claim-level S2 | blocked | Legal | nice | Tier-3 spec | KPI not in `SURFACES`. M8 used G1+corpus and stated uncertainty. Do not file as a product ticket. |
| GAP-109 still staged | leftover | Legal | nice | later | Rationale replaced (`M8-INVESTIGATION-COMPLETE`). Row stays `pending` / `staged` until the product rows close. Not a second investigation. |
| `PB-exec_summary-008-locator-mismatch` | leftover | Exec | must | **unowned** | Wrong Pro Forma chunk vs page-46 Diligence Adjusted. M5–M7 did not home it. |
| `PB-exec_summary-retrieval-scope-gap` | leftover | Exec | must | **unowned** | `spot_check` still chunk-only. Calibration already dual-source. M5 vs M7 owner was never resolved. |
| Dual-source evidence in **production** `spot_check` | proposed | Exec | should | same as scope-gap | Same job as the row above if done once. Do not double-count. |
| `PB-exec_summary-source-ref-mislabel` | deferred | Exec | nice | later | Presentation packet cites the wrong analysis table. |
| exec_summary S2 on GKF/SPG + Clearsulting dual-source re-run | parked | Exec | nice | after Wave 4 | Tied to scope-gap. Explicit non-goal. |
| `FU-M4-GATE` | leftover | Eval hygiene | should | unscheduled | Six committed-artifact pytest failures. Still cited at M6/M8. Wave 4 exited anyway. |
| `FU-M4-MAP` | leftover | Eval hygiene | should | unscheduled | Context-map SHA refresh deferred each milestone (`FOLLOWUP-M*-map-refresh`). |
| `FU-M4-TESTS` | leftover | Eval hygiene | should | verify | D-M4-E leftovers were M6’s home. Confirm landed or keep. |
| `FU-M4-CLONEGUARD` | leftover | Eval hygiene | should | **unscheduled** | In-tree vs worktree fail counts still diverge (M8 F4: 1566/19 vs 1510/24, same 6 fail node-ids). |
| Architecture `INDEX.md` version lag | leftover | Eval hygiene | should | unowned | Files at 1.6 / 1.8 (26 Aug). INDEX still 1.0 / 3 Aug. |
| T9 launcher credential-at-rest | leftover | Eval hygiene | should | M8 audit F2 | Baked warehouse env vars persist in uploaded launchers. Cleanup or named waiver. |
| Stale agent outputs / T2 artifacts post-M4 ingest | parked | Eval hygiene | should | triage | Mostly paid by M5–M7 checklists + Elder Care Legal re-extract (25 Aug). Do not keep blindly. |
| `PB-fta_numeric-post-m4-chunk-citation-drift` | parked | Eval hygiene | nice | instrument | Leave open — detects chunk relocation after T6. |
| Slice recomposition (`eval/retrieval/slices/*.yaml`) | leftover | Retrieval | should | verify | M5 was the home. Confirm live pins or drop. |
| Per-pass `vs_metadata_filters=True` canary | proposed | Retrieval | should | leftover design | Global A/B failed. IP pass with filters on retrieved 4 LEGAL chunks. |
| Debug `legal.litigation` 5.88pp A/B drop | proposed | Retrieval | should | before 2nd global canary | Necessary if filters are revisited. |
| SPG residual `filename_closure` gold (3 intents) | deferred | Retrieval | nice | adjacent | Registry `OI-eval-harness-spg-residual-filename-closure-gold-completeness`. Not a Wave 4 checkpoint. |
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
| GAP-102 per-company G1 floors | proposed | Calibration | should | **unblocked** | M8 produced the four-company G1 table. Eval/registry, not a product ticket. |
| CHK-27 + judge harness | parked | Calibration | nice | after Wave 4 | Descoped at M3. Only if probe+recal pass **and** operator authorizes. |
| Spec O4 fta_numeric degenerate floor | deferred | Calibration | nice | trigger-gated | 30/30 `supported`. |
| Phase A — is beta alive? | proposed | Beta | should | **cheap parallel** | Last full diligence 3 Aug; CIM preview 20 Aug. Does not block the iterate pack. |
| Which button beta hits (Rainmaker job vs `run_vdr_pipeline.py`) | proposed | Beta | should | Phase A | Job-path warning in `databricks/CLAUDE.md`. Necessary and not being done. |
| Phase B — wire runs into measurement | proposed | Beta | nice | after first real run | Stages 1–2 of the quality loop are disconnected. |
| Phase C — feedback → same backlog as M4 | proposed | Beta | nice | after B | Form + weekly triage + re-run before “fixed.” |
| Phase D — new beta companies, same bar | parked | Beta | nice | after iterate pack | Explicit Wave 4 non-goal. |
| Is production the official beta home? | decide | Product | should | — | If yes, lab-only proof ≠ “fixed for stakeholders.” |
| CIM preview vs full diligence as separate products? | decide | Product | should | — | Fair-experiment report landed 26 Aug. Never mix preview scores with full-diligence trust. |
| Feedback channel (form vs Slack) | decide | Product | nice | — | Must tie to a run. |
| Garden UI + auth for `analysis.*` | proposed | Product | nice | later wave | Blocks productization. Older architecture Q. |
| Cross-Analysis Agent (CIM vs data room) | proposed | Product | nice | later wave | Austin Phase 4. No module today. |
| Orchestrator Phase 5 pack (memo/deck/grids/tracker) | proposed | Product | nice | later wave | Only `md_to_word` exists. Deck/PDF out of scope. |
| Human-in-the-loop deal memory | proposed | Product | nice | later | Overrides, accepted flags, cross-deal benchmarks. |
| Highlight newly added VDR files | proposed | Product | nice | low priority | Client ask. Analysis quality first. |
| Data-room completeness scorecard | proposed | Product | nice | later | Thin rooms (Clearsulting Legal 0 classified docs). Not an agent fix. |
| Agent-quality A-03 / A-07 | deferred | Product | nice | later wave | M2 sized ~52 registry rows. **A-09 moved to Legal must** — M8 showed it is the CS/GKF KPI 1/3 cause. |
| Genie chatbot product fate | decide | Product | nice | — | `genie_rules.py` exists; product call never made. |
| Confidence-score distributions | proposed | Analysis | should | **unscheduled** | Histograms of `section_confidence`, citation confidence, retrieval/extract scores — by agent, company, surface. |
| System walkthrough (how a run actually flows) | proposed | Analysis | should | **unscheduled** | Coupling surfaces, warehouse tables, contracts, agent DAG. Understanding, not a milestone. |
| CIM-only vs full-VDR substantiation study | leftover | Analysis | should | **report landed** | Shareable report + audit 26 Aug. Directional only. Next is the product call above, not another arm. |
| Corpus / gold / recall-artifact EDA | proposed | Analysis | nice | **unscheduled** | Gold-size vs recall@10, chunk-length dist, company completeness. Explains the ~4% recall@10 artifact. |
| Judge vs human disagreement slices | proposed | Analysis | nice | **unscheduled** | Where M3 failed: evidence path vs judge vs label. |
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
| Fine-tune / SFT / LoRA | proposed | Models | nice | **no track** | Nothing in repo trains weights. Treat as a **new program**, not a leftover. |
| Dataset / pre-training “all-company baseline” | parked | Models | nice | registry only | Never wired to gold or promotion. |

---

## Iterate pack (the now-slice)

File four missing rows, amend one, then home all ten. Do not add Clearsulting Legal 0/11 (corpus-absent), KPI S2 (spec), or a second IP row.

| # | Item | Ledger | Close when |
|---|---|---|---|
| 1 | KPI overlay-aware G1 scorer | **add** | CS/GKF KPI G1 reads the matching overlay block, not only `healthcare_kpis_json` |
| 2 | Elder Care founder + privacy extract | **add** | Fresh G1 ≥9/11 or those two items leave `retrieved_no_terms` / 4-of-5 |
| 3 | SPG Legal extract (G1) | **add** | SPG Legal G1 moves off 1/11 against the 181-doc LEGAL set |
| 4 | SPG KPI 4/7 | **add** | Scored healthcare fields fill, or named corpus-absent |
| 5 | `PB-legal_register-retrieval-ip` | **amend** then fix | Kind is `retrieved_no_terms`, not `corpus_gap`; `ip_register` populated or unable_to_assess |
| 6 | `PB-legal_register-claim-failure-gkf` | filed | Supported fraction > 14/28 |
| 7 | `PB-legal_register-claim-failure-spg` | filed | Supported fraction > 1/5 |
| 8 | `PB-legal_register-extraction-depth-contracts` | open | S2 beats 3/23 (G1 t4c/coc recovery is not enough) |
| 9 | `PB-exec_summary-008-locator-mismatch` | open | Claim 008 cites Diligence Adjusted; 46,423 supported |
| 10 | `PB-exec_summary-retrieval-scope-gap` | open | Production `spot_check` is dual-source |

---

## Stats by track

**Pace:** 1 day ≈ Wave 4 charter **M1 through M8 as executed**. **1 sprint = 10 working days.** Estimates ±50%, same agent-heavy style.

**Essential** = `must` rows that are closable product work (iterate pack). Locator cascade is a constraint, not a day of work. Dual-source `spot_check` is not double-counted with the scope-gap row. **Complete** = essential + should + nice, **excluding** SFT/LoRA/pre-training.

| Track | Items | Must | Should | Nice | Essential | Complete |
|---|---:|---:|---:|---:|---|---|
| Program | 4 | 0 | 1 | 3 | — | 0.4d · 0.04 spr |
| Legal | 12 | 9 | 1 | 2 | 1.8d · 0.18 spr | 2.2d · 0.22 spr |
| Exec | 5 | 2 | 1 | 2 | 0.5d · 0.05 spr | 0.7d · 0.07 spr |
| Eval hygiene | 8 | 0 | 7 | 1 | — | 0.8d · 0.08 spr |
| Retrieval | 12 | 0 | 3 | 9 | — | 1.4d · 0.14 spr |
| Calibration | 5 | 0 | 3 | 2 | — | 0.6d · 0.06 spr |
| Beta | 5 | 0 | 2 | 3 | — | 1.0d · 0.10 spr |
| Product | 10 | 0 | 2 | 8 | — | 2.0d · 0.20 spr |
| Analysis | 5 | 0 | 3 | 2 | — | 0.8d · 0.08 spr |
| Ingest/infra | 9 | 0 | 3 | 6 | — | 1.2d · 0.12 spr |
| Models (serving A/B only) | 1 | 0 | 0 | 1 | — | 0.2d · 0.02 spr |
| **Iterate pack (must product)** | **10** | **10** | — | — | **~2.3d · ~0.2 spr** | — |
| **Prudent (must + should)** | **~35** | 11 | ~24 | — | — | **~5.5d · ~0.6 spr** |
| **Everything on this map except SFT** | **~76** | 11 | ~24 | ~41 | — | **~11d · ~1.1 spr** |

SFT / LoRA / pre-training: **not in those totals.**

**Read of the numbers:** the 24 Aug “~4 days to finish Wave 4” is **spent**. What is left that is actually a fix is the **iterate pack (~2 days)**. The should pile (beta pulse, floors, taxonomy, hygiene, CIM product call) still fits in a sprint. The long tail is optional.

Do not treat a G1 score as a company-quality ranking. Clearsulting Legal 0/11 is missing docs. Clearsulting/GKF KPI 1/3 is a healthcare-hardcoded scorer. SPG Legal 1/11 is extraction on a fat corpus. Those are not one defect.

---

## Suggested sequence

Cheap ledger work first. Research beside both. Do not serialize everything.

1. File the four missing backlog rows and amend `PB-legal_register-retrieval-ip` kind.
2. One-shot Legal S2 taxonomy, then home the iterate pack (new wave vs named FU vs Phase 9 — record the call).
3. Cheap eval first: KPI overlay scorer (A-09) + GAP-102 floors.
4. Legal extracts: Elder Care residual, contracts S2, IP, SPG G1, GKF/SPG S2 quote-match.
5. Exec: claim 008 + dual-source `spot_check` (same change if you do it once).
6. Phase A + which-button in parallel. Conf-score dist + system walkthrough still do not block product work.
7. Phase 9 vs new wave (beta wiring, CIM-vs-VDR product, Garden).
8. Parallel: PINKEY, discriminative probe, per-pass VS filters, legal taxonomy if not done in (2), T9 launcher cleanup. Do not reopen `merge_rank_off`, global metadata filters, BMA two-pass, or the 4/11 closeout story.

---

## Wave 4 spine

| ID | Intent | Status |
|---|---|---|
| M1 Retrieval loop | Measured; `merge_rank_off` rejected. Elder Care evidence superseded by M4 CIM re-parse. | done |
| M2 Ledger truth-up | Registry sized. Sized ≠ scheduled. | done |
| M3 Calibration honesty | Honest fail. Promotion inadmissible. Probe still owed. | done |
| M4 Product fixes | 8/10 closed on Elder Care. Audit rev3 `pass-with-conditions`. | done |
| M5 Clearsulting 7/7 | Checklists + promotion + e2e linkage. Audit `accepted-with-waivers`. | done |
| M6 GKF 7/7 | Checklists + promotion. Audit landed. | done |
| M7 SPG 7/7 | Completes G2. Audit landed (amendment T9 closed F1–F3). | done |
| M8 Legal/KPI root cause | D11, Legal S2 ×3, GAP-109 replace, 8/11 re-ratify, G5. Audit `accepted-with-waivers` (F1 changelog, F2 credentials). | done · leftovers unowned |

---

## Already run — do not reopen

| Experiment | Result |
|---|---|
| Route B vs A | A rejected (1/18 FTA). Semantic + merge-rank stays. |
| Merge-rank 4 arms + M1 `off` × 4 companies | `sim × tier` won; all `off` gates failed. |
| Global `vs_metadata_filters` A/B | Failed PG5. Default False. Per-pass canary survived. |
| BMA two-pass / Haiku extract | Quality loss; 8k cap cannot fill schema. Sonnet, one call. Standing merge reject. |
| M3 exec_summary calibration | P2/P4 fail. Human rung. Registry 0.857 is stale — not upgrade evidence. |
| M4 wet re-runs | 8/10 closed. Contracts extract + IP + claim 008 left open. |
| M5–M7 7/7 + promotion | Clearsulting / GKF / SPG checklists and `ops.e2e_linkage` landed. Did **not** home 008 or scope-gap. |
| D11 slug→display map | Landed. Warehouse display (`GKF`/`SPG`) ≠ folded `s2_scores.company`. Title-case inverse is retired. |
| First `legal_register` S2 outside Elder Care | Clearsulting 0 claims (expected, 0 LEGAL docs). GKF 14/28. SPG 1/5. |
| Elder Care Legal 4/11 as the live score | Extraction bug on Wave-2 pass `766487529692196`. Fresh G1 **8/11**. Rubric and corpus (+7 chunks) ruled out. Floor ≥9/11 still missed. |
| GAP-109 distillation-era rationale | Replaced. Do not re-investigate; execute the iterate pack. |
| Fair CIM-only vs full-VDR (Elder Care) | Report landed 26 Aug. Legal **lost**; KPI/customer/forecast **different**; QoE/FT/BMA **same**. Directional frozen-53 only. |

**No SFT/LoRA program exists.** Calibration here means sample power + relative thresholds, not training a judge.

---

## Standing rejects

BMA two-pass · `merge_rank_off` as default · global metadata filters on · Route A for batch diligence · relabel unverifiable exec_summary claims to manufacture P2 · cross-epoch recall compares · “judge verified the report” from M2/M3 figures · **force a 4/11 Elder Care Legal closeout** · **treat healthcare-only KPI G1 as a company-quality ranking** · **file Clearsulting Legal 0/11 as an agent bug**.

---

## Contradictions to resolve first

1. Charter exit = 10 M4 closures; T12 closed 8; charter not amended. Still true.
2. Scope-gap owner: M4 non-goals said M7; spec §2.2 said M5. M5–M7 ran and left it unowned.
3. CLONEGUARD named in the M4 run, absent from the wave-note follow-up table. M8 F4 still sees the split.
4. Legal IP kind is `corpus_gap` in the ledger and `retrieved_no_terms` in M4 T9-bis + M8 T4. Amend before fixing.
5. Extraction-depth called retrieval at M4 T3; S2 got worse after retrieval widening. M8 agrees: extract.
6. Claim 008 still has no home (“not M7” and “file as M7 variant” both appeared; neither shipped).
7. GAP-109 is investigation-complete and still `status: pending`. That is correct only if the iterate pack is the closer.
8. A-09 is still a later-wave registry row and is also the M8 KPI cause. Split: execute A-09; leave A-03 / A-07 deferred.
9. M8 T8 handoff said `audit_status: not_run`; the 26 Aug auditor then recorded `accepted-with-waivers`. The audit file wins.
10. Older multi-company coverage plan still “ready for executor.” Active path was M5–M7. Still do not launch.

Resolved since 24 Aug (do not re-open): M4 audit ran (rev3 `pass-with-conditions`); verifier is not M8-only (wrapper landed); D11 / 4/11 / GAP-109-replace / M5–M8 “not started.”

**Highest-leverage gap:** the iterate pack has no owning wave. Two M4 legal leftovers + 008 were already unowned; M8 added four unfiled findings and two S2 rows. Until those get a home, a Phase 9 / new-wave plan will swallow or drop them.

---

## First decisions to record here

1. Home for the iterate pack: new wave vs named FU vs absorb into Phase 9.
2. File the four missing backlog rows + amend IP kind? (recommended: yes, cheap.)
3. Scope-gap owner — still open; M5–M7 skipped it.
4. Phase 9 vs new wave — M8 is done; this call is due.
5. CLONEGUARD: official FU or run footnote?
6. M8 F2 launchers: delete-after-job vs accept the residual.
7. Cycle-3: actually run Phase 2, or leave the M8 waiver as the last word.

Sources: `.dev/` plans/specs/wave notes/audits/handoffs; tracked ledgers (`product_backlog.yaml`, `registry.yaml`, `eval_debt.yaml`, `trust_statement.md`); M8 T4 findings + T3 verifier evidence; `CHANGELOG.MD`; fair-experiment shareable report. 24 Aug scout kept for long-tail tracks; spine and Legal/KPI rows rewritten against 26 Aug evidence.
