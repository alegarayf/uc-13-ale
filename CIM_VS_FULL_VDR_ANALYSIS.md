# CIM-only vs. Full-VDR — What the Rest of the Data Room Actually Adds

**Company:** Elder Care · **Date:** 2026-08-24 · **Status:** automatic-only (LLM judge, no human review yet — see §6)

**Scopes compared** (both are real, already-completed live pipeline runs — nothing in this report was re-run or simulated for this analysis):

| Scope | Catalog | Files ingested | Chunks | Agents run |
|---|---|---:|---:|---|
| **CIM-only** | `uc13_preview` | 1 (`2024 Elder Care - CIM_vF.pdf`) | 539 | All 7 workstreams + cross-analysis. **No Phase-5 memo/exec-summary** (`run_orchestrator=False`) |
| **Full-VDR** | `uc13_ale` | 450 | 55,819 | All 7 workstreams + cross-analysis + Phase-5 memo/exec-summary |

**Method:** two subagents pulled live warehouse data read-only and ran an automatic LLM judge (`databricks-claude-sonnet-4-6`) — no numbers here are estimated or backfilled. Raw artifacts: `.dev/analysis/cim-vs-vdr/{agent-level-diff.json, agent-level-diff.md, non-cim-doc-impact.json, claim-level-eval.json, claim-level-eval.md, doc-impact-ranking.json}`.

---

## 1. Bottom line

- The **CIM alone reproduces the P&L headline** (revenue, EBITDA, margins) almost exactly, because both runs cite the same CIM Pro Forma tables for those numbers.
- The CIM **cannot substantiate**: the legal register (contracts, litigation, CoC), real operational KPIs (census, caregiver headcount, compliance incidents), the real forecast model, or per-customer billing detail. Those come from **7 non-CIM documents that account for the overwhelming majority of quantifiable lift**.
- On the automatic claim-level check (53 exec-summary claims, each independently re-judged against each evidence scope): **full-VDR evidence supports 38/53 claims (72%) vs. 22/53 (42%) for CIM-only** — a **19-claim** swing directly attributable to non-CIM material or to workstreams the CIM-only path never runs (Phase 5).

---

## 2. Agent-level deltas — the real, quantified numbers

Source: `.dev/analysis/cim-vs-vdr/agent-level-diff.md` (latest row per table, both catalogs, warehouse-verbatim).

| Agent | Full-VDR | CIM-only | What changed |
|---|---|---|---|
| **Legal** | 14 contracts in register · 9/11 checklist items covered · 3 CoC-consent contracts · 2 litigation rows · `section_confidence=high` · 7 flags | **0** contracts · **0/11** checklist · **0** CoC · **0** litigation · `section_confidence=low` · **0** flags | Legal is **entirely invisible** to CIM-only — a CIM never contains the contract/lease/litigation corpus |
| **KPI** | Census: 351.8 avg / 361 latest weekly (5/9/2025) · Caregivers: 2,123 (4/21/2025) · 2 compliance incidents (NYSDOH) · source = `Company KPI Dashboard SAMPLE.xlsx` | Census: 1,186 TTM Aug-24 / 1,251 2024E · Caregivers: 165 scheduled TTM · 0 compliance incidents · source = CIM | CIM's own client/caregiver counts are on a **different basis and stale relative to the KPI dashboard** — a materially different operational picture |
| **Forecast** | source = `Elder Care Projection Model Refresh_vF.xlsx` · 15 assumptions, 4 stretch, 2 supported · 21 revenue-build rows | source = CIM · 8 assumptions, 1 stretch, 0 supported · 6 revenue-build rows | The real projection model nearly **doubles** assumption coverage and reveals more aggressive ("stretch") assumptions than the CIM discloses |
| **Customer quality** | #1 customer = a named client, $744,518.42 (billing detail) · source = `Revenue 36 months Billing Amount Summary by Client...xlsx` | #1 "customer" = New York **location** aggregate, $13,588K · source = CIM | CIM only exposes **location-level** rollups; true customer-level concentration risk is invisible without the billing file |
| **Cross-analysis** | 22 CIM claims extracted, 5 Critical issues | 43 CIM claims extracted, 6 Critical issues | Counter-intuitively higher counts CIM-only — see caveat in §5 (no Phase-5 cross-check against the fuller corpus to resolve/dedupe) |
| **Quality of earnings** | 17 Tier-4 addbacks, same dollar items (~$7,464K) · `addback_pct_of_ebitda` **not persisted** on this row | Same 17 items, ~$7,464K · `addback_pct_of_ebitda` = 246.9 | Underlying QoE math is CIM-sourced either way — no material lift here |
| **Financial trends** | PF Adj. Revenue $46,423K · PF Adj. EBITDA $9,239K · Reported EBITDA $2,773K (7.9%) — **identical** in CIM-only | Same figures | **No lift** — both runs cite the CIM's own P&L tables |
| **Business model** | `executive_summary` populated (~$46.4M ITM Aug-24 adj. revenue) | `executive_summary` **null** — CIM-only BMA JSON was **LLM-truncated** mid-extraction | Not a scope gap — a real extraction defect on the CIM-only run (see §5) |
| **Diligence report (Phase 5 memo)** | 6 rows; latest run rates FT/forecast/KPI/legal/QoE **Red**, BM/CQA **Yellow**; full top-10 issues, section ratings, reconciliation | **0 rows** — Phase 5 never runs in the CIM-only preview path | The entire memo/rating/reconciliation layer simply **does not exist** for CIM-only today |

---

## 3. Top non-CIM documents by quantified impact

Two independent measurements agree on the same top tier:

**(a) Structural citation impact** — distinct fields across all 7 agents + cross-analysis that cite the doc as source (`non-cim-doc-impact.json`, 41 docs total, CIM itself excluded since it's cited 250×):

| Rank | Document | Distinct citing fields | Agent(s) |
|---:|---|---:|---|
| 1 | Elder Care Projection Model Refresh_vF.xlsx | 35 | forecast, cross_analysis, diligence_report |
| 2 | Company KPI Dashboard SAMPLE.xlsx | 15 | kpi, cross_analysis, diligence_report |
| 3 | Revenue 36 months Billing Amount Summary by Client...xlsx | 12 | customer_quality |
| 4 | Batistil Contract Agreement 2025.pdf | 8 | legal, customer_quality, cross_analysis, diligence_report |
| 5 | Elder Care - Diligence Workbook - vSHARE_6.25.25.xlsx | 8 | kpi, cross_analysis, diligence_report |
| 6 | Elder Care Performance Detail_12.31.24_vF.xlsx | 7 | customer_quality |
| 7 | dropbox_hipaa_agreement.pdf | 6 | legal |
| 8 | GL LLC_2022_1120S_Tax Returns_Redacted.pdf | 6 | quality_of_earnings, cross_analysis, diligence_report |

**(b) Claim-flip impact** — of the docs above, which ones empirically flip an exec-summary claim from unsupported/contradicted (CIM-only) to `supported` (full-VDR), per the automatic judge (`doc-impact-ranking.json`):

| Rank | Document | Claims citing | Claims flipped to `supported` |
|---:|---|---:|---:|
| 1 | Company KPI Dashboard SAMPLE.xlsx | 3 | **3** (exec.claim.003, .004, .052) |
| 2 | Elder Care - Diligence Workbook - vSHARE_6.25.25.xlsx | 3 | **3** (exec.claim.021, .039, .049) |
| 3 | Batistil Contract Agreement 2025.pdf | 2 | **2** (exec.claim.043, .051) |
| 4 | April 30 2025 Retainer Agreement (Ackerman)...pdf | 2 | 1 (exec.claim.023) |
| 5 | Elder Care - Diligence Workbook - vSHARE_6.19.25.xlsx | 1 | 1 (exec.claim.020) |
| 6 | Manhattan_Lease_0424.pdf | 1 | 1 (exec.claim.024) |

The KPI dashboard and the diligence workbook are the two documents with **both** the widest structural reach and a 100% claim-flip rate — they are the single highest-value non-CIM additions.

---

## 4. Exec-summary claim eval — automatic judge, both scopes

Source: `.dev/analysis/cim-vs-vdr/claim-level-eval.md` — all 53 claims from the existing rubric (`eval/content/exec_summary_rubric_claims.json`), each independently re-judged (`databricks-claude-sonnet-4-6`) against CIM-only evidence and full-VDR evidence.

| Scope | supported | contradicted | unsupported |
|---|---:|---:|---:|
| **Full-VDR** | **38** | 4 | 11 |
| **CIM-only** | **22** | 5 | 26 |

**Agreement: 28/53 (52.8%)** — meaning nearly half the claims get a *different* verdict depending on evidence scope.

- **19 claims** go from `supported` (full-VDR) to worse (CIM-only): `exec.claim.003, 004, 017, 020, 021, 022, 023, 024, 025, 036, 038, 039, 041, 042, 043, 048, 049, 051, 052`
- **3 claims** go the other way (`supported` CIM-only, not full-VDR): `exec.claim.027, 032, 034` — worth a spot-check, since a claim being "supported" with *less* evidence is a flag for judge over-permissiveness, not necessarily a real finding.

Full per-claim rationale for all 25 disagreements is in `claim-level-eval.md`.

---

## 5. Caveats — read before quoting these numbers externally

1. **Full-VDR agent timestamps are not one run.** `financial_trends` and `legal` are from 2026-08-21; the other 5 workstreams + diligence_report are from 2026-08-19. QoE/forecast/cross-analysis may reflect an older FTA/legal snapshot than the latest FTA/legal rows shown here.
2. **CIM-only `business_model.executive_summary` is null due to an LLM truncation defect** on that run (`Unterminated string` mid-JSON), not because the CIM lacks the content. Don't read that null as "CIM has no business overview" — it's a bug on that specific run.
3. **`uc13_preview.analysis.diligence_report` has zero rows by design** (`run_orchestrator=False`). Any claim requiring top-10 issues / section ratings / reconciliation has **no analysis-table evidence at all** in the CIM-only judge run — several of the 19 "worse" flips are attributable to this structural gap, not to a specific missing document (flagged per-claim in `claim-level-eval.md`).
4. **Cross-analysis CIM-claim counts are higher CIM-only (43 vs 22)** — counter-intuitive, and not yet root-caused; likely the CIM-only cross-analysis agent had less competing full-corpus evidence to reconcile against. Flagged as an open question, not asserted as a finding.
5. **This is an automatic-only re-adjudication** — the judge has not been calibrated to `judge` rung for `exec_summary` (rung is `human` per `eval/eval_runbook.md` §4.9); treat verdicts as directional signal, not certified ground truth. The 3 "CIM-only better" claims (027, 032, 034) are the most worth a manual spot-check.
6. Legal, KPI, and Forecast deltas are the most defensible/attestable findings in this report — they're binary presence/absence or clearly-sourced numeric deltas, not judge-model interpretation.

---

## 6. Next step — the actual experiment (same pipeline, two corpora)

**This document is already worth pursuing.** §§1–5 are a real warehouse read of two live runs, and Legal / KPI / Forecast / customer-quality are binary or numeric enough to quote internally as directional. They are **not** yet a fair product comparison, and they should not be the shareable team doc.

The gap is experimental, not analytical. We compared two *different products* (CIM Rainmaker preview with `run_orchestrator=False` in `uc13_preview` vs. a split-timestamp full-diligence run in `uc13_ale`) and then re-judged the **full-VDR** exec-summary rubric against two evidence scopes. That answers “can CIM tables substantiate the full-room memo?” It does **not** answer “what does the same pipeline produce when the only difference is the data room?”

The shareable report needs the second question, plus cost and latency.

### 6.1 What “fair” means

| Knob | Both arms |
|---|---|
| Company | Elder Care |
| Git SHA | same commit |
| Pipeline | same: Phase 3–5 DAG (`run_pipeline(..., run_orchestrator=True)`) + `build_exec_summary()` — **not** the Rainmaker preview path |
| Endpoints | same `llm_endpoint` / `extraction_endpoint` / `vision_endpoint` |
| Catalog convention | eval catalog is `uc13_ale` (never production `uc13`) |
| Deliverables | both produce a Phase-5 memo (`.md`/`.docx`) **and** an exec-summary one-pager |
| Independent variable | corpus only: CIM PDF vs. full data room |

**Catalog isolation is required.** CIM-only retrieval cannot run against `uc13_ale.ingestion.embeddings_index` while 450 files are already indexed — agents would still retrieve non-CIM chunks. So:

| Arm | Catalog | Corpus | Why |
|---|---|---|---|
| **Full-VDR** | `uc13_ale` | 450 files / ~55,819 chunks (already ingested) | Canonical eval catalog |
| **CIM-only** | `uc13_preview` (or a sibling eval catalog) | 1 file / 539 chunks (already ingested) | Same pipeline code, isolated index so retrieval is actually CIM-scoped |

Same *pipeline*, two *catalogs*, one variable. Reusing `uc13_preview` is fine **if and only if** we stop using `run_vdr_rainmaker.py` (`run_orchestrator=False`) and instead call the full DAG + exec summary. That single switch kills caveat §5.3 (zero `diligence_report` rows) and makes the two memos comparable.

Skip re-ingest on both arms unless chunk `created_at` / `doc_status` show the corpus is stale. Re-running Phase 3–5 is enough to fix caveat §5.1 (split timestamps) and to retry the CIM BMA truncation (§5.2).

**Operator approval needed** before either job: this writes new `analysis.*` rows (and Phase-5 volume reports). Read-only warehouse probes do not.

### 6.2 How to run it

Capture a **run card** at the end of each job (stdout + a JSON drop under `.dev/analysis/cim-vs-vdr/runs/<arm>/`). Instrumentation already exists — it was just never persisted for this comparison:

- Tokens: `reset_token_counter()` before the DAG; `get_token_totals()` + `get_token_breakdown()` after (prompt / completion / total, per endpoint, estimated $).
- Latency: wall-clock around `run_pipeline` + `build_exec_summary`; per-agent `duration_s` from `AgentRun` (already written into `diligence_report.agent_run_manifest_json`).
- Identity: git SHA, catalog, company, endpoints, `created_at` of every analysis row, report volume paths.

**Arm A — full-VDR (`uc13_ale`).** Phase 3–5 only (ingest already done):

```text
catalog=uc13_ale
sp_company_name=Elder Care
run_pipeline(..., run_orchestrator=True)
build_exec_summary(catalog="uc13_ale", ...)
```

**Arm B — CIM-only (`uc13_preview`).** Same calls, different catalog. If preview chunks are current, skip ingest; if not, scoped ingest via `file_whitelist` / `detect_cim()` then the same DAG. Confirm after the run: `uc13_preview.analysis.diligence_report` has a new row, BMA `executive_summary` is non-null, all 7 workstreams + cross-analysis share one timestamp window.

Do not start analysis until both run cards show `SUCCESS` for Phase 3–5 and both memo + one-pager paths exist. If CIM BMA truncates again, that is a run failure, not a finding — retry that arm before comparing.

### 6.3 Analysis — what is agentable (waves)

After both jobs land, this is a subagent DAG. Nothing below needs a new pipeline.

**Wave 0 — preflight (one agent, read-only).** Confirm: same git SHA; one `created_at` cluster per arm; CIM-only file count = 1; full-VDR file count ~450; both `diligence_report` rows present; both report files on volume; run cards have tokens + latency. HALT if any of those fail.

**Wave 1 — three parallel extracts (no LLM required).**

| Workstream | Output | Source |
|---|---|---|
| **Cost / latency** | Per-arm and per-agent tokens, $, wall-clock, `duration_s` | run cards + `agent_run_manifest_json` |
| **Agent-level warehouse diff** | Replay of §§2–3 on the *new* rows (legal register, KPI census, forecast assumptions, customer #1, QoE addbacks, FT P&L, BMA, cross-analysis, Phase-5 ratings) | warehouse, same method as `agent-level-diff.md` |
| **Report-artifact diff** | Section-by-section delta of the two Phase-5 memos and the two exec-summary one-pagers | volume `.md`/`.docx` (and YAML snapshots) |

**Wave 2 — two parallel evals (LLM + warehouse).**

| Workstream | Question it answers |
|---|---|
| **Generated-report delta (the shareable core)** | What does the CIM-only *memo* actually omit, contradict, or phrase differently vs. the full-VDR memo? This is the product question. |
| **Claim re-eval (keep what we did here)** | Re-judge the 53 `exec_summary` rubric claims against each arm’s **own** evidence, now that both arms have Phase 5. Separately keep the current method (“can CIM evidence support the full-VDR memo’s claims?”) as a substantiation appendix — it is a different question. |

Human spot-check is **narrow**, not a full re-read: the 3 CIM-better flips (027, 032, 034), the cross-analysis claim-count inversion, and any new “CIM-only better” or Phase-5-only flips. `exec_summary` stays on the `human` rung (`eval/eval_runbook.md` §4.9); do **not** block the shareable doc on a calibration run. Quote Legal / KPI / Forecast / customer-quality as attested; quote judge % as directional.

**Wave 3 — assemble the shareable doc** (one agent, after Waves 1–2). Structure below.

### 6.4 Shareable team report — required sections

Working title: **CIM-only vs. full data room — what the rest of the VDR costs, and what it buys (Elder Care).** Status: one coherent run per arm, same pipeline. This file (`CIM_VS_FULL_VDR_ANALYSIS.md`) is the directional prior, not the handout.

1. **Setup (half a page).** Same pipeline, same SHA, same endpoints; only corpus differs; catalogs `uc13_ale` vs isolated CIM; both produced memo + one-pager.
2. **Cost and latency.** Tokens (prompt / completion / total), estimated $, wall-clock, per-agent duration. Full-VDR vs CIM-only vs delta. This is the tradeoff numerator.
3. **Delta table — what is lost or different** (the section to screenshot). One row per diligence object the IC/partner actually uses. Columns: *object · full-VDR · CIM-only · lost / different / same · why (doc or pipeline)*. Seed from §§2–3, then replace with Wave 1 numbers. Expected shape (to be overwritten by the new runs, not quoted as final):

   | Object | Full-VDR has | CIM-only has | Verdict |
   |---|---|---|---|
   | P&L headlines (rev, EBITDA, margins) | CIM Pro Forma | same CIM tables | **same** |
   | QoE addback dollar items | CIM-sourced | CIM-sourced | **same** (math) |
   | Legal register / CoC / litigation | contracts, leases, litigation files | nothing | **lost** |
   | Operating KPIs (census, caregivers, incidents) | KPI dashboard | stale CIM counts, different basis | **different** (and misleading if quoted) |
   | Forecast model | Projection Model Refresh | CIM assumptions only | **lost** (coverage + stretch) |
   | True customer concentration | billing-by-client file | location rollups labeled as customers | **lost** (and mislabeled) |
   | Phase-5 ratings / top-10 / reconciliation | memo | *(will exist on the new CIM-only run)* | compare ratings, not presence |
   | Exec-summary claims supportable | TBD on new run | TBD on new run | Wave 2 |

   Add a short “top non-CIM documents” appendix (KPI dashboard, diligence workbook, projection model, billing file, named contracts) so the team sees *which files* buy the lift, not just “more files.”
4. **Comparison of the two approaches.** Two products, not two scores:
   - **CIM-only** = cheap, fast, good for P&L headlines and a first commercial read; blind on legal, real ops KPIs, the forecast model, and customer-level risk; cheaper in tokens and wall-clock by the Wave 1 ratio.
   - **Full-VDR** = the memo you can underwrite legal / ops / forecast / concentration on; costs the remaining files + the extra retrieval/generation.
   - **What this study already showed (keep):** even before a fair re-run, the CIM cannot see legal, true KPIs, the projection model, or named-customer concentration. That finding should survive the cleaner experiment. What should **not** be carried over uncritically: the 72% vs 42% claim split, the 19-claim swing, and anything that depended on Phase 5 being absent or on a truncated BMA.
5. **Caveats (short).** Automatic judge is directional; human rung unchanged; one company (Elder Care); CIM-only catalog is isolated by necessity; do not mix preview scores with full-diligence trust (horizon-map product question).

### 6.5 What we are *not* doing in this experiment

- Recalibrating `exec_summary` to `judge` rung (optional later; not a gate).
- Touching production `uc13`.
- Re-ingesting 450 files or a full parser rebuild.
- Treating Rainmaker (`run_orchestrator=False`) as the CIM-only arm.
- Mixing timestamps across agents inside an arm.

### 6.6 Why this is still worth it

§§1–5 already named the documents that matter and the workstreams where CIM is structurally blind. The experiment above is what turns that into a team-shareable tradeoff: **same machine, two fuel loads, both full reports, with a price tag.** Most of the analysis after the two jobs is warehouse diffs + report diffs + a narrow human spot-check — highly agentable, not a new research program.
