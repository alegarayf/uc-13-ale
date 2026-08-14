# T11 sign-off — Clearsulting bloated `filename_closure` disposition (audit F-03)

**Plan:** eval-consolidation-m4-onboarding-runbook v1.6 · **Date:** 2026-08-14 · **Status:** operator disposition per ESC-M4-1 Decision 4 / charter Amendment A5

## Audit finding addressed

| Finding | Severity | Disposition |
|---|---|---|
| **F-03** | major (intent-drift) | Registry row `GAP-M4-1-clearsulting-bloated-filename-closure` + 12 per-intent eval-debt rows + this signoff; baseline **stands**, labeled not per-intent interpretable for the 12 intents below |

## Operator disposition — 12 bloated `filename_closure` intents

Pilot gold: `eval/retrieval/gold_labels/clearsulting.yaml` @ T9 snapshot `uc13_ale:2417:2026-08-14`. Counts re-derived at T11 execution (audit is evidence, not authority).

| Intent | Positives | Gold method | Max recall@10 |
|---|---:|---|---:|
| `cqa.retrieve_revenue_type_and_renewals` | 1273 | `filename_closure` | ≈ 0.79% (10/1273) |
| `fta.ebitda.q1_financial_statements` | 1262 | `filename_closure` | ≈ 0.79% (10/1262) |
| `fta.opex.q1_financial_statements` | 1262 | `filename_closure` | ≈ 0.79% (10/1262) |
| `fta.revenue.q1_financial_statements` | 1262 | `filename_closure` | ≈ 0.79% (10/1262) |
| `kpi.retrieve_delivery_model` | 1085 | `filename_closure` | ≈ 0.92% (10/1085) |
| `cqa.retrieve_customer_tenure` | 1082 | `filename_closure` | ≈ 0.92% (10/1082) |
| `profiler.banked_vs_nonbanked` | 1082 | `filename_closure` | ≈ 0.92% (10/1082) |
| `profiler.business_description` | 1082 | `filename_closure` | ≈ 0.92% (10/1082) |
| `profiler.deal_type` | 1082 | `filename_closure` | ≈ 0.92% (10/1082) |
| `profiler.industry_overlay` | 1082 | `filename_closure` | ≈ 0.92% (10/1082) |
| `profiler.revenue_model` | 1082 | `filename_closure` | ≈ 0.92% (10/1082) |
| `profiler.vertical_subsector` | 1082 | `filename_closure` | ≈ 0.92% (10/1082) |

**Selected option:** Accept residual — match `GAP-103-recall-at-10-bloated-gold` / `signoffs/T12-bench-disposition.md` precedent at Clearsulting pilot scale (12 intents vs Elder Care's one). No fresh Tier-3 spec escalation (defect class already described by `GAP-103` and `ESC-T12-1`).

**Accepted residual risk:** Mean recall and cohort-level comparisons on `baseline_7174e0399e29` are **not per-intent interpretable** for these 12 rows. A reader must not treat the pilot baseline's aggregate recall as meaningful per intent for this subset.

**Baseline caveat:** Harness baseline `baseline_7174e0399e29` **stands** — it is not withdrawn or recomputed. It is **labeled** on three surfaces: registry row `GAP-M4-1-clearsulting-bloated-filename-closure`, addendum in `signoffs/T9-clearsulting-pilot.md`, and caveat sentence in `eval/program/onboarding_runbook.md` Step 6 per-company baseline promotion policy.

**Alternatives not selected:** (a) re-bootstrap all 12 intents to narrower gold methods this remediation round; (b) withdraw or recompute the pilot baseline; (c) fresh Tier-3 spec escalation mirroring `ESC-T12-1`.

**Gold change in this execution:** **None** — structural fix and any gold method changes are T13's scope under A5; T11 is records only.

## Cross-references

| Artifact | Role |
|---|---|
| `eval/program/registry.yaml` → `GAP-M4-1-clearsulting-bloated-filename-closure` | Tracked hub label (survives `.dev/`) |
| `eval/program/eval_debt/eval_debt.yaml` | 12 per-intent open debt rows |
| `.dev/audits/eval-consolidation/M4/2026-08-14-eval-consolidation-m4-onboarding-runbook-audit.md` §7 F-03 | Audit evidence |
| `.dev/plans/eval-consolidation-m4-onboarding-runbook/escalations/ESC-M4-1-rb-defect-t9-1-gold-corpus.md` §5 Decision 4 | Ruling executed |

## Kill-criterion evidence

| Criterion | Result |
|---|---|
| Each intent named with count and ceiling (not one aggregate sentence) | PASS — table above |
| Baseline stands with explicit uninterpretability label on tracked + signoff + runbook surfaces | PASS — three surfaces cross-reference registry row and this signoff |
| No gold or eval-code edits in T11 | PASS — records only |

**Operator signature / date:** _Pending operator signature_ · disposition drafted 2026-08-14 per ESC-M4-1 §6 item 4 (orchestrator drafts; operator signs)
