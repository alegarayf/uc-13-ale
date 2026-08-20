# UC-13 Eval Program Playbook

**What this is:** the operator playbook that sits beside [`eval_runbook.md`](eval_runbook.md). The runbook explains **what the system measures and which commands to run**. This file explains **where we stand today**, **how to run full pipelines and establish baselines**, **how to extend coverage to every SharePoint company**, **where signals and backlog live**, and **how much we can trust the product** — with enough structure to drive execution, analysis, and improvement loops.

**Companion docs:**

| Doc | Use when |
|-----|----------|
| [`eval_runbook.md`](eval_runbook.md) | You need command syntax, layer definitions, glossary |
| [`program/onboarding_runbook.md`](program/onboarding_runbook.md) | Step-by-step cluster onboarding (M4 authority) |
| [`program/trust_statement.md`](program/trust_statement.md) | Generated rollup — regenerate, never hand-edit |
| [`.dev/pending/eval-consolidation-open-items.md`](../.dev/pending/eval-consolidation-open-items.md) | Milestone auditor handoffs and cross-program open items |

**Catalog:** `uc13_ale` (dev/eval). **Default company:** `Elder Care`. **Company slug:** display name → lowercase underscore (`Elder Care` → `elder_care`).

---

## 1. How much can we trust the system?

Trust is **layered**, not a single score. A company can have strong retrieval and weak content correctness, or the reverse. Do not collapse layers into one number.

### 1.1 Five layers (independent)

| Layer | Trust question | Strong signal | Weak / misleading signal |
|-------|----------------|---------------|---------------------------|
| **Ingest completeness** | Did the data room land in the corpus? | Ratio near 100%, stable doc-type mix | Eval on incomplete VDR — model blamed for ingest gaps |
| **Retrieval** | Do the right chunks reach each intent? | Per-intent recall@10 vs gold; gate_pass on enhancement deltas | Aggregate recall on bloated `filename_closure` gold (mathematically capped ~1%) |
| **Agent fields (G1)** | Are expected JSON fields populated? | Golden checklist pass counts vs floors | **Presence only** — populated fields can still be wrong |
| **E2E / pipeline** | Did a full run complete and link to scored evidence? | Linked pipeline `run_id` + checklist in ops | DAG SUCCESS alone — no memo/claim quality guarantee |
| **Content correctness (S2)** | Are written claims supported by cited evidence? | High `supported` rate on whole-surface enumerations | Small calibration samples — not full-surface unless spot-check completed |

### 1.2 Verification rungs (content correctness only)

Historical rationale for these assignments: [`eval/content/RATIONALE.md`](content/RATIONALE.md).

| Rung | Meaning | Surfaces today |
|------|---------|----------------|
| **deterministic** | Code verifier, no LLM judgment | `legal_register` |
| **judge** | LLM cleared calibration vs human labels | **None** — no surface has earned this yet |
| **human** | Operator spot-check required | `fta_numeric`, `exec_summary` |

**Implication:** For claim-level trust today, rely on **deterministic legal verifier + human spot-checks on Elder Care**. G1 pass counts mean **structure**, not **correctness**.

### 1.3 What “fully scored” means (program target)

A company is **fully scored** when all applicable layers are attested in the trust statement with traceable evidence — not when a single harness run completes.

| Requirement | Elder Care | Clearsulting | GKF / SPG |
|-------------|------------|--------------|-----------|
| Ingest preflight | partial (98%) | attested | not in trust stmt domain* |
| Retrieval gold + baseline | yes | yes (12 bloated intents flagged) | no |
| Golden checklists (7 agents) | yes (Elder Care only on disk) | no | no |
| E2E linkage / promotion | ops data exists; trust stmt e2e layer not wired | skipped (eval debt) | Chip B smoke only |
| S2 content surfaces | fta attested; legal partial; exec partial | legal known_gap; rest not run | not run |

\*Trust statement company domain comes from `uc13_ale.ops.baseline_complete_companies` — extend by completing onboarding step 5 (harness baseline).

### 1.4 Honest program headline (Aug 2026)

- **One deep reference company:** Elder Care — retrieval + G1 rubrics + S2 on three surfaces.
- **One retrieval pilot:** Clearsulting — gold + harness + exemptions; not yet agent/S2 complete.
- **Two smoke-tier companies:** GKF, SPG — Chip B G1 informational + DAG e2e; no retrieval baselines.
- **Judge at production scale:** not built (CHK-27 descoped); calibration judge exists for samples only.

---

## 2. Company coverage matrix

### 2.1 Documented SharePoint eval set (Chip B + M4)

| Display name | Slug | Retrieval baseline | Gold YAML | G1 floors | S2 surfaces | Notes |
|--------------|------|-------------------|-----------|-----------|-------------|-------|
| Elder Care | `elder_care` | `baseline_acf58bcc4968`* | `elder_care.yaml` | yes | fta, legal, exec_summary | Reference corpus; 20/23 legal claims failed; 3/53 exec failed |
| Clearsulting | `clearsulting` | `baseline_7174e0399e29` | `clearsulting.yaml` | no (informational) | none | 0 legal docs; 12 bloated gold intents; promotion debt open |
| GKF | `gkf` | — | — | no | none | e2e `635893410954637`; profiler rows stale |
| SPG | `spg` | — | — | no | none | e2e `641030239604593`; ingest borderline |

\*Trust statement comparison epoch; older Chip A pin: `baseline_544eb3f2a0e2`.

### 2.2 Discovering companies beyond the four

There is **no committed manifest of all SharePoint folders**. Discover via:

- `test_pipeline.ipynb` Cell 2 (company dropdown), or
- `connector.list_companies()` on the workspace

Before batch onboarding, run a **read-only warehouse inventory** (distinct `company_name` in `ingestion.chunks` / upload log) and rank by chunk count + doc-type diversity.

---

## 3. Source-of-truth ledger (signals → backlog)

Use this index when triaging failures, writing improvements, or explaining results. **Do not open ad-hoc tracking** when a row already exists here.

### 3.1 Program records (repo)

| Role | Path | Update when |
|------|------|-------------|
| **Master disposition hub** | [`program/registry.yaml`](program/registry.yaml) | New gap, waiver, rung assignment, or closure |
| **Frozen source index** | [`program/source_manifest.yaml`](program/source_manifest.yaml) | Registry absorbs a new external source |
| **Open eval debt** | [`program/eval_debt/eval_debt.yaml`](program/eval_debt/eval_debt.yaml) | Known gap with explicit `closes_when` |
| **Product-signal backlog** | [`program/product_backlog.yaml`](program/product_backlog.yaml) | S2/eval measurement caveat or product defect surfaced, or closed with `closed_at` + `closed_evidence_refs` |
| **Corpus exemptions** | [`program/eval_exemptions.yaml`](program/eval_exemptions.yaml) | Intent/surface cannot be honestly measured |
| **Trust rollup** | [`program/trust_statement.md`](program/trust_statement.md) | After any layer changes — `trust_statement generate` |
| **Cross-milestone open items** | [`.dev/pending/eval-consolidation-open-items.md`](../.dev/pending/eval-consolidation-open-items.md) | Auditor handoffs; priority queue §Cross-milestone |
| **State snapshot** | [`.dev/eval_state_of_affairs_2026-08-03.md`](../.dev/eval_state_of_affairs_2026-08-03.md) | Historical; superseded on Clearsulting by M4 — still useful for gap taxonomy §10 |
| **Failure vocabulary** | [`architecture/rallyday/failure-taxonomy.md`](architecture/rallyday/failure-taxonomy.md) | Classifying retrieval/agent/infra failures |
| **Issues (incidents)** | [`.dev/issues/INDEX.md`](../.dev/issues/INDEX.md) | Harness gate failures, cluster attestation |

### 3.2 Warehouse (live)

| Schema / table | Role |
|----------------|------|
| `uc13_ale.ops.retrieval_harness_runs` | Harness run manifests |
| `uc13_ale.ops.retrieval_harness_results` | Per-intent metrics |
| `uc13_ale.ops.retrieval_harness_latest_baseline` | Per-company control baselines |
| `uc13_ale.ops.baseline_complete_companies` | Trust statement company domain |
| `uc13_ale.eval.s2_scores` | Claim-level content correctness |
| `uc13_ale.analysis.*` | Agent outputs scored by G1 and S2 |

### 3.3 Elder Care S2 evidence (spot-check artifacts)

| Surface | Verdicts | Failure analysis | Improvement backlog |
|---------|----------|------------------|---------------------|
| `exec_summary` | [`content/spot-check/exec_summary_elder_care_2026-08-12.verdicts.yaml`](content/spot-check/exec_summary_elder_care_2026-08-12.verdicts.yaml) | [`...failure_modes.md`](content/spot-check/exec_summary_elder_care_2026-08-12.failure_modes.md) | [`...m3_backlog.md`](content/spot-check/exec_summary_elder_care_2026-08-12.m3_backlog.md) |
| `fta_numeric` | [`content/spot-check/fta_numeric_elder_care_2026-08-13.verdicts.yaml`](content/spot-check/fta_numeric_elder_care_2026-08-13.verdicts.yaml) | [`...failure_modes.md`](content/spot-check/fta_numeric_elder_care_2026-08-13.failure_modes.md) | [`...m3_backlog.md`](content/spot-check/fta_numeric_elder_care_2026-08-13.m3_backlog.md) |
| `legal_register` | warehouse `s2_scores` + M3 dump | [`LCA/presentation_summary_elder_care.md`](LCA/presentation_summary_elder_care.md) | [`LCA/poc_delta_elder_care.md`](LCA/poc_delta_elder_care.md) |

### 3.4 Golden checklists (G1 — Elder Care only on disk)

`eval/{FTA,BMA,CQA,KPI,QOE,PROFILER,LCA}/golden_checklist_elder_care.md` — score after pipeline run; floors in [`.dev/g1_score_all_agents.py`](../.dev/g1_score_all_agents.py).

---

## 4. Execution procedures

### 4.1 Two run types (do not conflate)

| Run type | Purpose | Entry point | Writes to |
|----------|---------|-------------|-----------|
| **Pipeline E2E** | Produce fresh agent output on a company | `.dev/post_merge_closeout_submit.py e2e --company "X"` or `test_pipeline.ipynb` | `uc13_ale.analysis.*` |
| **Eval measurement** | Score that output (retrieval / G1 / S2) | Commands in §4.2–4.4 | ops tables, `s2_scores`, repo YAML |

Always record **`run_id`** from agent manifests and harness baselines in scorecard notes or registry evidence_refs.

### 4.2 Full eval walk for one company (all layers)

Replace `<Display Name>` with SharePoint folder name. Cluster steps use [`program/onboarding_cluster_submit.py`](program/onboarding_cluster_submit.py) when no local Spark — see [`.dev/agent-databricks-recipes.md`](../.dev/agent-databricks-recipes.md).

```
Phase A — Data readiness
  1. Registry review          → program/registry.yaml
  2. Ingest preflight         → eval.retrieval.ingest_preflight
  3. (If needed) Pipeline E2E → post_merge_closeout_submit / notebook

Phase B — Retrieval baseline
  4. Gold bootstrap (cluster) → onboarding_cluster_submit.py bootstrap
  5. Exemptions               → eval.retrieval.exemptions add|list
  6. Harness baseline         → onboarding_cluster_submit.py harness-baseline
  7. Review bloated gold      → eval_debt.yaml if filename_closure positives > ~500

Phase C — Agent field quality (G1)
  8. Score golden checklists  → eval/<AGENT>/golden_checklist_<slug>.md (create if new co.)
  9. G1 programmatic score    → python .dev/g1_score_all_agents.py --company "<Display Name>"
 10. Promotion / linkage      → evaluate_promotion() or record_e2e_linkage (FTA/Legal CLI)
     Skip + eval debt if checklist or run_id missing — never invent scores

Phase D — Content correctness (S2)
 11. Regenerate claim manifests → eval/content/extract_rubric_manifests.py (if new pipeline)
 12. legal_register            → legal_register_verifier (deterministic)
 13. fta_numeric / exec_summary → spot_check prepare → human review → write_spot_check_results
     (human rung until calibration passes — see §6)

Phase E — Rollup
 14. Eval debt                 → eval.retrieval.eval_debt open|list
 15. Trust statement          → eval.retrieval.trust_statement generate
```

Command details: [`eval_runbook.md`](eval_runbook.md) §4 and [`program/onboarding_runbook.md`](program/onboarding_runbook.md).

### 4.3 Pipeline E2E only (fresh agent output)

```bash
# Serverless DAG (typical)
python .dev/post_merge_closeout_submit.py e2e --company "<Display Name>"
```

Chip B reference run_ids: [`.dev/hector_merge_e2e_run_ids.json`](../.dev/hector_merge_e2e_run_ids.json).

After E2E: run G1 (`g1_score_all_agents.py`) and, for Elder Care–parity, S2 phases in §4.2 Phase D.

### 4.4 Retrieval-only refresh (no full pipeline)

When corpus or registry changed but agent output unchanged:

1. Re-bootstrap gold if citations/corpus shifted
2. `harness_cli run --run-type baseline --company-name "<Display Name>" --store-backend delta`
3. `validate-baseline` before comparing enhancements
4. Regenerate trust statement

### 4.5 Enhancement / experiment loop (retrieval)

1. Pin baseline `run_id`
2. Make retrieval change (chunking, ranking, prompts)
3. `harness_cli run --run-type enhancement --affected-intents ... --baseline-ref-run-id ...`
4. Read **per-intent** deltas, not aggregate alone
5. Promote baseline if net improvement

---

## 5. Extend to all SharePoint companies

### 5.1 Recommended rollout waves

| Wave | Companies | Goal | Definition of done |
|------|-----------|------|-------------------|
| **W0** | Elder Care | Reference + trust stmt complete | Wire e2e/agent_fields in trust stmt; refresh S2 after pipeline fixes |
| **W1** | Clearsulting | Second fully scored company | FTA checklist + S2 fta/exec; resolve 12 bloated gold rows; promotion or debt |
| **W2** | GKF, SPG | Retrieval + G1 baselines | gold YAML + harness baseline + informational→floors decision |
| **W3** | All others in SharePoint | Scalable onboarding | Repeat W1/W2 pattern; batch by ingest completeness |

### 5.2 Per-new-company checklist (copy for each)

- [ ] Display name confirmed in SharePoint / warehouse
- [ ] Ingest preflight ≥ acceptable threshold (operator-defined; flag if <95%)
- [ ] Full or partial pipeline E2E completed; `run_id`s recorded
- [ ] `gold_labels/<slug>.yaml` committed
- [ ] Exemptions filed for corpus holes (legal absent, overlay mismatch A-09 pattern)
- [ ] Harness baseline in ops; `run_id` in evidence
- [ ] Bloated gold reviewed (`filename_closure` positive count)
- [ ] Golden checklists created or waived with eval debt
- [ ] `evaluate_promotion` or debt row per agent
- [ ] S2 surfaces run or exempted (`known_gap`)
- [ ] Trust statement regenerated
- [ ] Registry / eval_debt updated

### 5.3 What requires new code vs operator work

| Work | Type |
|------|------|
| Onboarding steps 1–5 for company X | **Operator** — code exists (Clearsulting pilot) |
| Per-company golden checklists | **Operator/content** — adapt Elder Care rubrics |
| `BASELINES[slug]` in g1_score_all_agents.py | **Small config** — when floors ratified |
| Trust stmt `agent_fields` / `e2e` rows | **Small code** — trust_statement.py reads ops manifests (today stubbed) |
| Judge production harness (CHK-27) | **New build** — after calibration passes (§6) |
| Exec summary dual-source evidence (`analysis.*`) | **Product/eval** — highest leverage before re-calibration |

---

## 6. Judge and re-calibration path

### 6.1 What exists today

| Capability | Module | Scope |
|------------|--------|-------|
| Sample calibration judge | [`content/calibration.py`](content/calibration.py) | Fixed N-claim samples; outputs `rung_assignment: judge\|human` |
| Human whole-surface S2 | [`content/spot_check.py`](content/spot_check.py) | Full claim enumeration; `writer=human_spot_check` |
| Deterministic legal S2 | [`content/legal_register_verifier.py`](content/legal_register_verifier.py) | Register-row verification |
| Production judge harness | **Not built** (registry CHK-27 descoped) | Would write `writer=judge_harness` to `s2_scores` |

Registry rung assignments (CHK-26a): `exec_summary: human`, `fta_numeric: human`, `legal_register: deterministic`.

### 6.2 Path to judge rung (conditional)

```
1. Product fixes (esp. analysis.* lookup for exec_summary — m3_backlog #1)
2. Fix chunk truncation / broken chunk mapping (M2 WP-1, WP-2)
3. Re-run: python -m eval.content.calibration --surface ... --sample ...
4. If thresholds pass → update registry rung_assignments to judge
5. Build CHK-27 judge harness (reuse calibration judge_claim + s2_writer)
6. Block human spot_check for upgraded surfaces; run judge harness at scale
```

Re-calibration is **post-M3 / operator-authorized** — it does not auto-resurrect CHK-27 without an explicit build.

---

## 7. Open items and eval debt (action queue)

### 7.1 Cross-program priority (from pending ledger)

| P | Item | Action |
|---|------|--------|
| 1 | **ESC-T12-1** — bench `filename_closure` spec note | Tier-3 spec amendment or explicit waiver |
| 2 | **UGA-1** — upstream grounding audit | Execute per M4 entry gate |
| 3 | **F-14** — rung-3 `assessment_metrics` rows | Land metrics or extend waiver |
| 4 | **M0 registry** — GAP-104, housekeeping rows | Close or re-scope |
| 5 | **M1 F-9** coverage bundle | CI guards for gold/registry (deferred) |
| 6 | **Clearsulting promotion_inputs** | Golden checklists + pipeline run_ids — [`eval_debt/eval_debt.yaml`](program/eval_debt/eval_debt.yaml) |
| 7 | **12 Clearsulting bloated gold intents** | Re-bootstrap with `citation_backfill` or `aggregate_exclude` |

Full tables: [`.dev/pending/eval-consolidation-open-items.md`](../.dev/pending/eval-consolidation-open-items.md).

### 7.2 Known measurement caveats (do not misread scores)

- **Bloated gold:** `filename_closure` with 1k+ positives → recall@10 not interpretable per intent ([`eval_runbook.md`](eval_runbook.md) §4.2).
- **G1 pass ≠ correct:** field presence only (registry GAP-103).
- **Mean retrieval recall ~4% on Elder Care:** largely gold-size artifact, not a single ranker KPI.
- **Legal 7/11 G1 vs 20/23 S2 failures:** structural pass vs claim-level register verification — different layers.
- **Trust stmt e2e/agent_fields `not_attested`:** generator gap — ops may still have linkage data.

### 7.3 Agent-quality backlog (registry A-*)

| ID | Title | Lane |
|----|-------|------|
| A-03 | Agent depth uneven | Product |
| A-07 | Excel cell-level citations | Product / retrieval |
| A-09 | Clearsulting KPI overlay conflict | Exemptions + overlay logic |

---

## 8. Product improvement backlog (from eval signals)

Fold these into product/engineering planning — eval has already isolated root cause.

### 8.1 High leverage (from S2 spot-checks)

| # | Fix | Evidence | Surfaces affected |
|---|-----|----------|-------------------|
| 1 | Add `analysis.*` / `diligence_report` as evidence source alongside chunk RAG | exec_summary failure_modes §0 | exec_summary S2, future judge |
| 2 | Fix `source_ref` mislabel (`legal.executive_summary` → `diligence_report.executive_summary`) | exec_summary m3_backlog #2 | exec_summary spot-check |
| 3 | De-dupe `revenue_by_segment_json` in FTA extraction | fta_numeric m3_backlog #1 | fta_numeric S2 |
| 4 | Add `source_location` to segment revenue schema | fta_numeric m3_backlog #2 | fta_numeric |
| 5 | Re-point broken vision chunk `027ec667…` → `cd9773ea…` | M2 audit WP-1; fta m3_backlog #3 | FTA citations, calibration |
| 6 | Fix ~1,200-char chunk truncation in evidence fetch | M2 audit WP-2 | fta_numeric, exec_summary |
| 7 | Legal extraction depth (T4C, CoC, platform, IP) | LCA poc_delta, presentation_summary | legal agent |

### 8.2 Retrieval / infra

| Item | Signal | Ref |
|------|--------|-----|
| OPEX basis / merge-rank | L3.context_basis_mismatch | failure-taxonomy |
| `legal.insurance` classifier vs intent filter | Harness gate failure 2026-07-15 | `.dev/issues/2026-07-15-harness-baseline-gate-failure-elder-care.md` |
| Index sync before harness | Stale VS index | Same issue doc |
| Fallback rate ~13% on Elder Care baseline | O-11 attestation | registry |

### 8.3 Eval program / automation

| Gap | Impact |
|-----|--------|
| No unified eval CLI | Operator error across harness/G1/e2e/S2 |
| Harness not in CI | Retrieval regressions ship silent |
| No INDEX ↔ ops cross-check | Scorecard trail drift |
| No g1 pytest | Scorer semantic drift |
| Per-company gold coverage pytest | Only Elder Care guarded |

---

## 9. Analysis and experiments backlog

Run these to prioritize companies and validate improvements — read-only unless noted.

| Analysis | Question | How |
|----------|----------|-----|
| **Company inventory** | Who exists in SharePoint/warehouse beyond the four? | SQL distinct `company_name`; chunk counts |
| **Ingest ranker** | Which companies are eval-ready first? | ingest_preflight batch; doc-type mix |
| **Clearsulting retrieval sanity** | Which intents are meaningful ex-bloat? | Per-intent report minus 12 debt intents |
| **Legal S2 failure taxonomy** | Retrieval vs extraction vs register schema? | M3 `s2_scores` dump + failing claim review |
| **Exec summary re-calibration prep** | Does analysis.* evidence lift agreement? | Prototype fetch → calibration sample only |
| **Cross-company FTA variance** | SPG 8.5/18 vs Clearsulting 17/18 — data or model? | Ingest + corpus profile before re-run |
| **Enhancement ablation** | merge_rank_on vs off on worst intents | harness_cli enhancement + validate-baseline |
| **Phase 7 completeness scorecard** | Separate ingest gaps from model gaps | registry OI Phase 7 (design) |

---

## 10. Explaining results to stakeholders

### 10.1 One-page narrative template

1. **Corpus:** ingest completeness % and known doc gaps (trust stmt ingest row).
2. **Findability:** retrieval attested or not; cite baseline `run_id`; mention bloated-intent caveats if any.
3. **Structure:** G1 pass counts per agent — "fields present," not "content verified."
4. **Correctness:** S2 surfaces — supported/failed counts; rung (human vs deterministic).
5. **Known gaps:** exemptions + eval_debt + registry staged items — deliberate, not hidden.
6. **Trust boundary:** "We trust X for Y; we do not yet trust Z."

### 10.2 Elder Care example (current)

- **Ingest:** 98% — 8 docs missing; do not over-interpret agent misses on missing docs.
- **Retrieval:** Baseline attested; interpret per-intent; ignore bloated KPI/profiler intents for ranker decisions.
- **Agents:** FTA 16/18 structural; Legal 7/11 structural with documented extraction-depth gaps.
- **Correctness:** FTA 276/276 supported (human-reviewed); Legal 3/23 supported at claim level; Exec 50/53 supported — failures are real product signal.
- **Overall:** Strong on Elder Care financial structure and exec narrative grounding (after correct evidence path); legal register claims need product work; multi-company generalization unproven until W1–W3 complete.

### 10.3 What not to say

- "The eval suite passed" — layers are independent.
- "Retrieval is 4% so search is broken" — check gold method first.
- "BMA 7/7 so business model is correct" — G1 is presence-only.
- "Judge verified the report" — no surface on judge rung in production.

---

## 11. Suggested execution order (your stated goals)

Aligned to: full pipelines, new baselines, all companies, records/signals, improvement backlog, trust clarity.

| Step | Task | Outcome |
|------|------|---------|
| 1 | Warehouse company inventory + ingest batch preflight | Prioritized company queue |
| 2 | Complete Clearsulting W1 (E2E → FTA checklist → S2 fta → trust stmt) | Second scored company |
| 3 | GKF + SPG retrieval onboarding (gold + harness) | Four-company retrieval matrix |
| 4 | Refresh Elder Care pipeline + regenerate S2 after product fixes §8.1 | Current reference scores |
| 5 | Wire trust_statement agent_fields/e2e from ops (small PR) | Honest five-layer rollup |
| 6 | analysis.* evidence prototype + exec_summary re-calibration | Judge rung decision data |
| 7 | If calibration passes → spec CHK-27 judge harness build | Scalable S2 |
| 8 | Wave W3 batch onboarding (scripted cluster submits) | SharePoint-wide baselines |

---

## 12. Quick command index

See [`eval_runbook.md`](eval_runbook.md) §7 for the full table. Highest-frequency:

```bash
# Ingest
python -m eval.retrieval.ingest_preflight --company "<Name>" --catalog uc13_ale --backend sql_chunk_count

# Cluster onboarding
python eval/program/onboarding_cluster_submit.py bootstrap --company "<Name>" --catalog uc13_ale
python eval/program/onboarding_cluster_submit.py harness-baseline --company "<Name>" --catalog uc13_ale

# G1
python .dev/g1_score_all_agents.py --company "<Name>"

# Trust rollup
python -m eval.retrieval.trust_statement generate --catalog uc13_ale --registry eval/program/registry.yaml

# Eval debt
python -m eval.retrieval.eval_debt list --company "<Name>"
```

---

## 13. Document maintenance

| When | Update |
|------|--------|
| After each company onboarding | eval_debt, exemptions, gold YAML, registry evidence_refs, regenerate trust_statement |
| After S2 spot-check | spot-check verdicts YAML, failure_modes, m3_backlog if new patterns |
| After calibration attempt | registry rung_assignments + assessment_metrics (CHK-26a pattern) |
| After major program closeout | This playbook §2 matrix and §7 queue |

**Last consolidated:** 2026-08-18 (from eval program state through M4 Clearsulting pilot + M3 S2 Elder Care), updated 2026-08-20 for eval-signal-foldback M2/W0 ledger truth-up (registry `tshirt` sizing pass, `GAP-109` created, 4 `product_backlog.yaml` measurement-caveat closures, SPG `44038` correction).

---

## Reading retrieval metrics honestly

Retrieval numbers are easy to misread if you treat them like a single product KPI. This section is operator guidance before you interpret a harness report, compare baselines, or explain recall to stakeholders.

### Gold epoch is a first-class boundary

Gold labels are not patchable metadata — they are pinned to a **corpus epoch**. An epoch is the triple `catalog:chunk_count:run_date` (e.g. `uc13_ale:55812:2026-08-11`). The chunk count is a hard assertion against live warehouse state; the date is provenance from the refresh run, not something you guess ahead of time.

| Event | Why epoch matters |
|-------|-------------------|
| Ingestion rebuild (e.g. 2026-08-05 Elder Care) | ~98% of committed positive chunk ids can dangle overnight — incremental yaml edits do not repair this |
| Full gold refresh (M1 / Amendment A2) | All intents re-ground in **one** event; manifest, fixture, baseline, and trust artifacts must share one snapshot pin |
| Partial rebootstrap (e.g. "just the 8 bloated intents") | Leaves other intents on stale closure/citation mixes — epoch coherence becomes unprovable |

`compare()` against a baseline from a different ingestion snapshot correctly raises `IngestionSnapshotMismatchError`. That is not a harness bug — it is the guard doing its job.

**Rule:** When the corpus moves, assume a chartered full refresh and re-pin everything. Do not hand-edit positives to "fix" a drifted epoch.

### Cross-epoch baseline comparison is invalid

Control baselines are valid **only within the same registry hash + gold snapshot + ingestion snapshot**. Promoting a new baseline supersedes the prior pin — it does not retro-compare recall@10 across eras.

| Baseline transition | Why cross-compare fails |
|---------------------|-------------------------|
| `baseline_299063e87806` → `baseline_1aeb0ace584a` (2026-07-15) | Registry change (`legal.insurance` workstream filter) → `RegistryHashMismatchError` if you try Jul 3 vs post-fix |
| `baseline_1aeb0ace584a` → `baseline_544eb3f2a0e2` (2026-07-30) | 49 → 57 intents **and** T2 full-registry rebootstrap reworked ground truth for 41/49 pre-existing intents |
| Chip A → M1 comparison epoch (`baseline_acf58bcc4968`) | Post-2026-08-05 corpus + citation_backfill epoch — not comparable to closure-heavy pre-M1 gold |

Attempting retro-compare across these boundaries produces misleading drift narratives. Enhancement and ablation runs must pin `baseline_ref_run_id` to a baseline promoted **under the current registry hash** — omit `--baseline-ref-run-id` only when establishing a fresh control baseline, not when diagnosing regression.

**Do not attribute aggregate recall shifts to ranker quality alone.** T2 rebootstrap alone cut total positive chunk ids ~54% (51,987 → 23,721) by replacing broad `filename_closure` with `citation_backfill` — a precision upgrade, not a yaml typo.

### Bloated gold and the bench recall ceiling

Some intents are **mathematically capped** regardless of retriever quality. When gold positives come from `filename_closure` at O(1000+) chunks, recall@10 ≈ 10/N — a perfect retriever that returns only cited chunks can score ~0% against that gold. That is eval theater, not product signal.

| Pattern | Symptom | Correct response |
|---------|---------|------------------|
| `filename_closure` with 1k+ positives | Per-intent recall@10 not interpretable | Re-bootstrap with `citation_backfill`, or file `aggregate_exclude` in [`retrieval/gold/gold_exclusions.yaml`](retrieval/gold/gold_exclusions.yaml) |
| KPI item-12 intents unmappable to claims | Positive chain falls through to closure fallback | Intent must be claim-mapped **or** excluded before gold write — no third state |
| `kpi.retrieve_bench_and_capacity` (bench) | 2,925 closure positives → recall@10 ceiling ≈ **0.34%** | Operator disposition **(a)** at T12: Tier-3 spec note + accepted residual; gold row unchanged; **not** in aggregate KPI recall |

Seven of eight KPI item-12 intents were resolved (two `citation_backfill`, five `aggregate_exclude`). Bench is the documented exception pending Tier-3 spec absorption (`ESC-T12-1`). Per-intent rows for bench in `baseline_acf58bcc4968` were computed against closure gold — expected until an explicit operator re-baseline after spec change.

**When reading aggregate recall:** exclude `aggregate_exclude` intents and bloated closure rows. Read **per-intent** deltas on gate-eligible intents only (see §4.5, §7.2).

### Baseline promotion and recovery when numbers look wrong

| Step | Action |
|------|--------|
| **Establish control** | `harness_cli run --run-type baseline` with **no** `--baseline-ref-run-id`; record new `run_id` |
| **Validate before compare** | `validate-baseline` on the pinned control |
| **Enhancement loop** | Pin same-epoch `baseline_ref_run_id`; read per-intent deltas, not aggregate alone |
| **Promote successor** | New baseline supersedes old — document waiver; do not cross-compare recall@10 across registry/gold epochs |

When a baseline run fails gates or per-intent recall looks impossibly low, check infrastructure before blaming the ranker:

1. **Stale vector search index** — Delta has embeddings but VS does not serve them (symptom: wrong doc types returned, sim scores ~0.25 vs ~0.45). Fix: **sync-only** index wait (`ingestion_parser._wait_for_index_sync`) — not a full parser rebuild.
2. **Registry vs classifier mismatch** — e.g. COI tagged `BACKGROUND` but intent filter is `LEGAL` only → positives filtered out even when index is healthy. Fix intent registry / extractor / agent filter alignment, then promote a **new** baseline (registry hash changed — prior baseline not cross-comparable).

Red herrings: `gate_pass: null` on baseline manifests is normal; empty `retrieval_harness_deltas` after manual `compare()` means deltas were not persisted — use `store.append_deltas()` if you need them in ops.

Sources: `.dev/retrospectives/learning/2026-08-13-eval-consolidation-m1-metric-guardrail-hardening.md`, `signoffs/T12-bench-disposition.md`, `.dev/archive/harness-baseline-2026-07-15.md`, `.dev/archive/harness-baseline-2026-07-30.md`

---

## Why these rubrics

Golden checklists (G1) score **field presence and structure** against client product intent — not deal verdicts. When you design a checklist for the next agent, ground it in Rallyday's associate model and the workstream contracts below rather than inventing pass/fail semantics.

### What the client is buying

Austin's bar (Rallyday / PE diligence): an **associate doing first-pass diligence** — orient to the business, test whether data supports the story, surface red flags, generate diligence questions, help form an initial underwriting view. Analysis beats download automation; every fact needs source-linked provenance with confidence.

Golden checklists mirror **Phase 3 workstream output contracts**, not Phase 4/5 synthesis (Cross-Analysis and Orchestrator are not built). Each checklist row asks: did the agent populate the structured facts, flags, citations, and gaps the spec expects for that diligence category?

### Flags, not verdicts

| Design rule | Implication for rubrics |
|-------------|-------------------------|
| Threshold breach = **flag with context**, presented neutrally | Checklist items verify flag **presence** and field shape — not whether the deal should proceed |
| **Never block a deal** | No rubric row should encode go/no-go; Red/Yellow/Green are directional signals |
| No composite deal scores | G1 pass counts are per-agent structural floors, not a rolled-up trust score |
| Phase 1: **stated metrics as truth** | Rubrics check extraction of what documents say — not recomputed NRR, DSO, cohort math |
| Prefer diligence questions over heavy compute | Missing data → `_data_room_gaps` / information requests, not inferred fills |

Negative vocabulary in product: Red/Yellow flags, data room gaps, reconciliation mismatches, reduced confidence (e.g. non-banked without CIM). Positive vocabulary: Green flags, Supported assumptions, corroborated citations — evidence for the deal team, not automated approval.

### Austin categories → agents → checklist files

Austin's nine diligence categories map to PE spec workstream agents. G1 golden checklists exist per built agent (Elder Care reference today):

| Austin § | Category | Agent | Eval checklist path |
|----------|----------|-------|---------------------|
| 1 | Business model overview | Business Model (BMA) | `eval/BMA/golden_checklist_<slug>.md` |
| 2 | Customer quality & concentration | Customer Quality (CQA) | `eval/CQA/...` |
| 3 | Financial trend analysis | Financial Trends (FTA + sub-agents) | `eval/FTA/...` |
| 4 | KPI & operating metrics | KPI | `eval/KPI/...` |
| 5 | Contract & legal risk | Legal & Contracts (LCA) | `eval/LCA/...` |
| 6 | Quality of revenue & earnings | Quality of Earnings (QoE) | `eval/QOE/...` |
| 7 | Forecast & underwriting | *(partial — FTA `opex_sub_agent`)* | Forecast rows live under FTA rubric scope |
| 2 (parallel) | Company / industry context | Company Profiler | `eval/PROFILER/...` |
| — | Retrieval-facing probes | *(harness intents, not a Phase 3 agent)* | Separate retrieval layer — do not conflate with G1 |

Categories 8–9 (consolidated red flags, IC deliverables) defer to future Cross-Analysis / Orchestrator — **not** current golden checklist scope. Per-agent flags and gaps are in scope; consolidated top-10 issues and memo assembly are not.

### Shaping checklist rows for a new agent

When extending G1 to a new company or agent, align rows to the spec contract:

| Output element | What to check in G1 | What G1 does **not** prove |
|----------------|---------------------|----------------------------|
| Structured facts (JSON tables, registers) | Expected fields populated vs floor | Values are correct vs source documents |
| `flags` (`Flag`: metric, value, threshold, severity, note, source_doc, confidence) | Flag objects present where thresholds apply | Materiality judgment |
| `citations` (document, location, quote, confidence) | Citation coverage on key claims | Claim-level S2 correctness (human/judge rung) |
| `data_room_gaps` | Missing expected docs surfaced | Seller will provide them |
| Extraction discipline | Null when absent; no invented reconciliation | Cross-document reconciliation (deferred) |

Industry overlays (`tech_services`, `healthcare`, etc.) change **which thresholds and KPI sets apply** — checklist variants should follow `company_profiler` overlay, not a single generic template. Agent hand-offs (e.g. CQA `contract_trigger_list` → Legal, FTA addbacks → QoE) inform **cross-agent consistency expectations** in registry notes, not single-checklist pass/fail.

**Full authority** — thresholds, clause rules, addback tiers, forecast credibility rubric, build sequence, and runtime `Flag`/`Citation` schema: see [`.dev/uc13-client-guidelines-distillation.md`](../.dev/uc13-client-guidelines-distillation.md) (primary sources: `databricks/Guidelines/Austin_email_guidelines.txt`, `PE_Diligence_Agent_Spec_v2.pdf`).

Sources: `.dev/uc13-client-guidelines-distillation.md`
