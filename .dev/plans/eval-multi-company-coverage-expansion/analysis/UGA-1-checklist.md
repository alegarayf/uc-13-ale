# UGA-1 execution checklist (outline only)

**Registry ID:** `UGA-1` — Upstream per-workstream grounding audit (Concern 1)  
**Spec pin:** `.dev/specs/eval-consolidation-program/spec.md` §18  
**Canonical prompt:** `.dev/audits/eval-consolidation/M3/upstream-grounding-audit-prompt.md`  
**Status:** `deferred` — M4 entry-gate item; **not started**  
**This document:** execution outline for a future operator session — **not the audit itself**

---

## Purpose

Verify that per-workstream **analysis tables** (`uc13_ale.analysis.*`) are grounded in VDR source chunks — one layer **upstream** of the T5 exec_summary reconciliation (which checked bundle-fidelity only).

Pipeline under test: `ingestion → vector DB → per-workstream agent → bundle → diligence_report / exec_summary`.

---

## Pre-flight (before sampling)

- [ ] Read `AGENTS.md` and `.cursor/skills/databricks-access/SKILL.md`
- [ ] Confirm read-only mode — no table writes, no calibration re-run, no registry / CHK-26a edits
- [ ] Load prior T5 artifacts:
  - [ ] `eval/content/spot-check/exec_summary_elder_care_2026-08-12.verdicts.yaml`
  - [ ] `eval/content/spot-check/exec_summary_elder_care_2026-08-12.failure_modes.md`
  - [ ] Related m3_backlog notes if present
- [ ] Confirm catalog `uc13_ale`, company **Elder Care**
- [ ] Do **not** re-decide M2 rungs (calibration-disagreement-audit D1, Option A, locked)

---

## Scope — workstreams and tables

Per spec §18 / filed prompt, sample fields from:

| Workstream / table | Example fields to prioritize |
|--------------------|----------------------------|
| `analysis.quality_of_earnings` | `addback_ledger_json` (exhaustive — 17 line items) |
| `analysis.financial_trends` | `revenue_trend_json`, `ebitda_json`, `addback_pct_of_ebitda` |
| `analysis.diligence_report` | `top_10_issues_json`, `reconciliation_summary_json`, `section_ratings_json`, `section_confidence_json` |
| `analysis.business_model` | `customer_operational_metrics_json` (client/location counts) |
| `analysis.kpi` | `healthcare_kpis_json` (caregiver headcount, census) |
| `analysis.forecast` | `forecast_assumptions_json` (credibility_rating claims) |
| Other §18-listed tables | `legal_contracts`, `customer_quality` — as time permits |

**Sample size:** ~20 fields, weighted toward exec_summary claims that **flipped verdict** in T5 reconciliation.

---

## Per-field method (repeat for each sample)

1. [ ] Read field's `source_doc` / `source_location` (or `raw_text` where present)
2. [ ] **Direct lookup** — locate cited chunk(s) in `uc13_ale.ingestion.chunks` by document/location (not fresh semantic search)
3. [ ] **Transcription check** — chunk exists; text contains the stated number/fact
4. [ ] **Aggregate check** — for computed fields, trace line items to verifiable chunks
5. [ ] **Retrieval probe** — separate semantic search (`embeddings_index`, top-5) for same fact; record whether correct chunk is retrievable
6. [ ] **Classify:** `verbatim_confirmed` | `computed_correctly_from_verified_inputs` | `citation_not_found` | `citation_found_but_mismatched` | `cannot_verify`

---

## Deliverables

- [ ] Report: `.dev/eval-program/spot-check/upstream_grounding_audit_elder_care_<date>.md`
  - [ ] Table of sampled fields with classifications
  - [ ] Root-cause summary (systemic vs isolated vs clean)
  - [ ] Explicit recommendation: impact on T5 `verdicts.yaml` confidence and m3_backlog item #1 (`analysis.*` lookup fix) priority
- [ ] **No** registry writes, **no** CHK-26a rung changes in the audit session
- [ ] Operator sign-off before any follow-on action beyond the report

---

## Escalation paths (if material failures found)

- [ ] File new finding for operator review — do **not** unilaterally flip rungs or re-trigger calibration
- [ ] Cross-reference ESC-T12-1 M5 handoff Flag 9: "M2 §6.3 loop-back" citation **unverified**; use playbook §6.2 for re-calibration sequencing until operator clarifies
- [ ] Update `.dev/pending/eval-consolidation-open-items.md` UGA-1 row after execution (separate hygiene subtask)

---

## Out of scope (checklist boundary)

- Executing the audit in this M5 subtask (T8 drafts outline only)
- Clearsulting / GKF / SPG multi-company expansion (Elder Care reference company only)
- Production judge harness (CHK-27 descoped)
- Trust-statement or S2 score-table regeneration

---

*Outline derived from registry row `UGA-1`, spec §18, and `.dev/audits/eval-consolidation/M3/upstream-grounding-audit-prompt.md`.*
