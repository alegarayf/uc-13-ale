# My runbook — integration closeout → hardening finish

**For:** Alejandro only  
**Updated:** 2026-07-16  
**Companion:** `project_status_timeline.md` (PM-facing summary)

Use this as a **sequential checklist**. Each cluster block ≈ **2 hr** — batch them; don’t start a new block if the previous one failed.

---

## Milestone status (2026-07-16)

| Milestone | Status | Evidence |
|-----------|--------|----------|
| **M-PHV3** (integration) | **CLOSED** | Item 23 smoke PASS (qualified) `fe7d58f`; item 24 exit-gate PASS `f1da4ec`; on `origin/dev` |
| **M-PHV4** (retrieval consolidation) | **CLOSED** | T1–T8 `08a5f86`→`fefcbc7`; cluster T8 2026-07-16; item 29 declined (PG5 fail); items 28/30 deferred |
| **Closing audit** (Phase 3) | **OPEN** | T7 audit T-1 remediation `4f51d2d`; no `.dev/audits/*-integration-closeout.md` yet |
| **Local git** | **`origin/dev` @ `fefcbc7`** | Uncommitted: README baseline-pin sweep, `harness-baseline-2026-07-15.md`, `pending2.md`, linkage test |

**Audit waivers to document (from `pending2.md`):** NEW-1 `ec74042` edited `legal_contracts_agent.py` mid-milestone (insurance `BACKGROUND` filter fix — sound, behavior not re-tested); NEW-2 Jul 3 harness compare waived → stability pair only (`baseline_1aeb0ace584a` / `813d0dd1b188`).

---

## Rules of thumb

1. **Pin before every cluster session:** `git rev-parse HEAD`, notebook content SHA if you touched it, company=`Elder Care`, catalog=`uc13_ale`.
2. **Local first when cheap:** `pytest tests/test_catalog_convention.py -q` and full suite before any push.
3. **One attestation per run:** paste stdout verbatim; don’t paraphrase pass/fail.
4. **Don’t declare baselines authoritative** from sqlite or single-intent runs — promote to Delta or discard.
5. ~~**Retrieval code stays frozen** until integration smoke + closing audit are done.~~ **Lifted 2026-07-14** — M-PHV4 landed; Phase 3 audit still recommended before more retrieval work.
6. **Don’t cross-compare harness runs across registry versions** — `baseline_299063e87806` vs `baseline_1aeb0ace584a` raises `RegistryHashMismatchError` (intentional after `legal.insurance` fix).

---

## Phase 0 — Preflight (laptop, ~15 min)

- [x] `git status` clean or only intentional artifacts — *4 uncommitted files (baseline README pins + docs; 2026-07-16)*
- [x] On `dev`, synced with `origin/dev` — **`fefcbc7`** (2026-07-16)
- [x] `pytest tests/test_catalog_convention.py -q` → green (44 passed, 2026-07-16)
- [ ] Optional full suite if you changed anything since last green run — *last recorded: 558 passed at M-PHV4 T8*
- [x] Attestation template open: `.dev/plans/uc13-m-phv3-integration/item23-post-merge-smoke-attestation.md`
- [x] Cluster attached; Cell 0 pip done once per restart — *2026-07-14/16 sessions*

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

---

## Phase 2 — Integration closeout (T7) 【laptop + git】 ✅ DONE 2026-07-14

**Goal:** Formal exit so retrieval work is allowed.

### Code / docs

- [x] Fix 5 stale `python_file` names in `databricks/workflows/uc13_ingestion_pipeline.yml` — `f1da4ec`
- [x] Match names in `databricks/workflows/README.md`
- [x] Verify: `grep` for old `0[0-9]_setup_vector_search` etc. → no hits
- [x] Create `.dev/plans/uc13-m-phv3-integration/exit-gate-checklist.md` — item 24 **PASS**
- [x] Append `CHANGELOG.MD` M-PHV3 entry
- [x] Touch `.dev/architecture/rallyday/` housekeeping

### Git sync

- [x] Re-run Genie parity at T7 → empty
- [x] Push `dev` to `origin/dev` — T7 era `f1da4ec`
- [x] Confirm smoke SHA in push chain — smoke `d3230fa`

### Tests

- [x] `pytest tests/test_catalog_convention.py -q`
- [x] Full suite green before push — 539 passed (T7)

---

## Phase 3 — Closing audit 【review session】 ← **YOU ARE HERE**

**Goal:** Close the loop validation started in early July; integration + M-PHV4 get formal sign-off.

- [x ] Cold-read attestation + exit checklist + M-PHV3/M-PHV4 diffs (`fefcbc7` range)
- [x ] Run auditor skill / big-model review on integration + PHV4 scope
- [x ] Write `.dev/audits/2026-07-__-uc13-integration-closeout.md` with `audit_status: clean` or `accepted-with-waivers`
- [ x] Note waivers by name — see table below .dev\audits\2026-07-16-uc13-m-phv4-retrieval-consolidation.md

**Pre-audit landings (not a substitute for §8 audit file):**

- [x] M-PHV4 T7 audit T-1 remediation — `4f51d2d` (inventory matcher hardening + architecture doc wording)
- [x] Pre-audit CHANGELOG/README touch — `76c38e5`, `a3ff631`

**Waivers to document in audit file:**

| ID | Waiver | Notes |
|----|--------|-------|
| W1 | Cell 7 parser rebuild deferred (qualified smoke) | Serverless OOM; M-PHV3 did not touch parser |
| W2 | BMA LLM truncation | Out of smoke scope |
| W3 | No workflow YAML `python_file` pytest | T7 adversarial gap |
| W4 | NEW-1 `ec74042` `legal_contracts_agent.py` edit | Insurance `BACKGROUND` workstream filter; registry hash change |
| W5 | NEW-2 Jul 3 harness compare waived | Stability pair only; see `harness-baseline-2026-07-15.md` |
| W6 | Legal 7/16 CONDITIONAL | 7/11 ties count; `restrictive` pass→gap-correct; target 8/11 post-fix |
| W7 | R-02 PG5 bar fail | `vs_metadata_filters` stays `False`; item 29 not activated |
| W8 | M-PHV4 items 28/30 deferred | Shared context assembly; `workstream_tags.py` centralization |

**Gate:** Further retrieval work should wait on audit file (recommended, not blocking per M-PHV4 closeout).

---

## Phase 4 — Retrieval consolidation 【M-PHV4】 ✅ DONE 2026-07-16

**Goal:** Changes to `retrieval.py`, `fallback.py`, `context_utils.py` + regression proof.

### Before coding

- [x] Charter: `.dev/specs/pipeline/uc13_pipeline_hardening_milestone_charter.md`
- [x] Pre-plan: `.dev/plans/uc13-m-phv4-retrieval-consolidation/`
- [x] Pin baseline: **`baseline_1aeb0ace584a`** (promoted 2026-07-15; supersedes `baseline_299063e87806`)

### Work packages

- [ ] Shared context assembly (OPEX pool / revenue / EBITDA budgets) — **DEFERRED** (charter item 28)
- [x] FTA fallback → shared `fallback.py` (13 call sites) — T2 `22d91f4`
- [x] Harness `dispatch_retrieval` → shared `fallback.py` (Surface 11) — T3 `dc86baf`
- [x] `_TYPE_ORDER` dedup — T1 `08a5f86`
- [x] Join-integrity preflight — T4 `9e39ff7` + README § R-08
- [x] `legal.insurance` registry fix (`BACKGROUND` workstream) — `ec74042` + `intent_registry.yaml`
- [x] Metadata filter A/B (Phase 4b) — done; activation declined

### Cluster regression (T8) ✅ DONE 2026-07-16

- [x] `apply_ops_ddl("uc13_ale")` — no DDL changes in M-PHV4
- [x] G2 probe — `company_name` pushdown accepted
- [x] Harness baseline promoted **`baseline_1aeb0ace584a`** (stability twin `baseline_813d0dd1b188`; VS sync + registry fix per `harness-baseline-2026-07-15.md`)
- [x] Compare vs `baseline_299063e87806` — **waived** (`RegistryHashMismatchError`; documented)
- [x] FTA Cell 12 → **16/18** — `.dev/scorecards/scorecard_7_16_post_phv4_vs_7_03.md`
- [x] Legal Cell 16 → **7/11** CONDITIONAL — `.dev/scorecards/scorecard_lca_7_16_post_phv4_vs_7_03.md`; brief `legal-restrictive-covenant-brief-2026-07-16.md`
- [x] `record_e2e_linkage` — FTA `5fef915601574dc3be629546910ba71e` · Legal `06ef2d29538e453d8af33b4944042775`
- [x] T8 CHANGELOG + cluster write-up — `fefcbc7`
- [x] M-PHV4 T7 audit remediation — `4f51d2d`
- [x] Unit suite — **558 passed** (T8 item 32)
- [ ] Commit uncommitted README `BASELINE_REF` pin sweep (working tree)

**M-PHV4 program exit:** Items 25–27 + Surface 11 landed; item 29 not activated; items 28/30 deferred.

---

## Phase 4b — Metadata filter A/B 【optional】 ✅ DONE 2026-07-15

- [x] Run A `vs_metadata_filters=False` — `enhancement_b079befc8b38`
- [x] Run B `vs_metadata_filters=True` — `enhancement_3c397f54d016`
- [x] PG5 numeric bar — **FAIL** (5.88pp `legal.litigation`; aggregate −0.07pp)
- [x] Second reviewer — **waived for exit** (packet sent)
- [x] Default stays `False` — attestation `.dev/attestations/m-phv4-r02-vs-metadata-filters-ab-elder-care-2026-07-15.md`

---

## Phase 5 — Eval cleanup 【laptop】 ✅ DONE 2026-07-13

- [x] Inventory `eval/retrieval/reports/` — 123 incomplete; 0 complete
- [x] Deleted all local report JSONs; `eval/retrieval/reports/*.json` gitignored — `f57386b`
- [x] Delta authoritative baseline confirmed (was `baseline_299063e87806`; now `baseline_1aeb0ace584a`)
- [x] README + runbook `BASELINE_REF` pins updated to `baseline_1aeb0ace584a` — **committed in working-tree README sweep pending commit**

---

## Phase 6 — Eval harness for all agents 【parallel track · pending】

**Goal:** Same rigor as FTA/Legal for the other five agents.

- [ ] Draft reproducible procedure (preflight → harness → agent → score → promote)
- [ ] Golden checklists for BMA / CQA / KPI / QoE / Profiler
- [ ] Extend `.dev/scorecards/INDEX.md` for agent baselines index

---

## Phase 7 — Data room completeness 【design · pending】

- [ ] Define minimal checklist per overlay (healthcare first)
- [ ] Map to `doc_relevance`, `chunks`, `ensure_coverage.get_coverage_report`
- [ ] Prototype in notebook (8c-style)

---

## Phase 8 — Executive summary / one-pager 【lower urgency · pending】

- [ ] Rename TL;DR → Executive Summary in orchestrator templates
- [ ] Review `pending.md` / `pending2.md` presentation experiments
- [ ] Re-render Elder Care sample

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
| R-02 A/B attestation | `.dev/attestations/m-phv4-r02-vs-metadata-filters-ab-elder-care-2026-07-15.md` |
| Legal restrictive brief | `legal-restrictive-covenant-brief-2026-07-16.md` |
| FTA 7/16 scorecard | `.dev/scorecards/scorecard_7_16_post_phv4_vs_7_03.md` |
| Legal 7/16 scorecard | `.dev/scorecards/scorecard_lca_7_16_post_phv4_vs_7_03.md` |
| Scorecards index | `.dev/scorecards/INDEX.md` |
| Retrieval baseline pin | **`baseline_1aeb0ace584a`** (was `baseline_299063e87806`) |
| Audit open items | `pending2.md` (NEW-1/NEW-2) |
| Open brain dumps | `pending.md`, `left_off.md`, `to_dive_deeper.md` |

---

## This week — minimal path

```
[x] Phase 1 smoke          — PASS (qualified) 2026-07-14
[x] Phase 2 closeout       — T7 done 2026-07-14
[ ] Phase 3 closing audit  ← you are here
[x] Phase 4 (M-PHV4)       — code + cluster T8 done 2026-07-16
[x] Phase 4b A/B           — done 2026-07-15; activation declined
[x] Phase 5 eval cleanup   — done 2026-07-13
```

**Remaining:** Phase 3 audit file · commit README baseline-pin sweep · Legal restrictive fix re-test (target 8/11) · optional push if new commits after audit

---

## Session log

| Date | Phase | Commit SHA | run_id / notes | Pass? |
|------|-------|------------|----------------|-------|
| 2026-07-13 | 5 eval cleanup | d3230fa | Deleted 123 incomplete report JSONs; gitignore reports | PASS |
| 2026-07-14 | 1 smoke | d3230fa | Cells 0/1/8b/8/10/11; Cell 7 deferred (OOM); item 23 qualified | PASS |
| 2026-07-14 | 2 closeout | f1da4ec | T7 workflow YAML + exit gate item 24; 539 pytest | PASS |
| 2026-07-14 | 4 code | 08a5f86→dc86baf | M-PHV4 T1–T4 | PASS |
| 2026-07-15 | 4b A/B | 0de1fc3 | A/B runs; PG5 fail; default stays False | PASS (decline) |
| 2026-07-15 | 4 closeout | 50aad12 | M-PHV4 T6 housekeeping; items 28/30 deferred | PASS |
| 2026-07-15/16 | 4 cluster | ec74042→fefcbc7 | VS sync + `legal.insurance` fix; `baseline_1aeb0ace584a`; FTA 16/18 · Legal 7/11 CONDITIONAL; `e2e_*` linked | PASS (Legal CONDITIONAL) |
| 2026-07-16 | 4 audit-prep | 4f51d2d | M-PHV4 T7 audit T-1 remediation (inventory matcher) | PASS |
| | 3 audit | | `.dev/audits/*-closeout.md` not written | |
