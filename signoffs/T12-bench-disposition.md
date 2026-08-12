# T12 sign-off — Bench disposition + audit F-1/F-2/F-3 close-out

**Plan:** eval-consolidation-m1-metric-guardrail-hardening v2.1 §7.2 · **Date:** 2026-08-11 · **Status:** complete (option a)

## Audit findings addressed

| Finding | Severity | Disposition |
|---|---|---|
| **F-1** | major (process-violation) | Retroactive kill-criterion note appended to `decision-logs/T3.md`; G4 eyeball (`signoffs/T4-refresh.md` APPROVED 2026-08-11) recorded as adjudication for bench carve-out |
| **F-2** | major (intent-drift) | Operator disposition **(a)** — Tier-3 spec note via `escalations/ESC-T12-1-bench-spec-note.md`; GAP-103 rationale corrected |
| **F-3** | minor (decision-log-stale) | T2 assumption banner-superseded; T3 retroactive note clarifies §5.2 item 3 misread |

## Operator disposition (F-2)

| Field | Value |
|---|---|
| Intent | `kpi.retrieve_bench_and_capacity` |
| Shipped state | `filename_closure` / 2,925 positives / `aggregate_exclude: false` |
| Recall@10 ceiling | ≈ 10/2925 ≈ **0.34%** |
| **Selected option** | **(a) Tier-3/spec note** — amend §19/D4 to name bench exception with residual stated |
| Tier-3 routing artifact | `.dev/plans/eval-consolidation-m1-metric-guardrail-hardening/escalations/ESC-T12-1-bench-spec-note.md` |
| Alternatives not selected | (b) exclusion amendment + §15.3 row re-write; (c) accepted-divergence entry only |
| Gold change in this execution | **None** — bench row unchanged at `uc13_ale:55812:2026-08-11` |
| Baseline caveat | Bench per-intent row in `baseline_acf58bcc4968` was computed against closure gold; expected if spec later excludes bench — re-baseline only on explicit operator instruction |

## GAP-103 rationale correction

| Field | Value |
|---|---|
| Registry id | `GAP-103-recall-at-10-bloated-gold` |
| Prior rationale defect | Claimed full interpretability over all 8 item-12 intents including bench closure set |
| Corrected scope | 7 of 8 resolved (2 citation_backfill, 5 aggregate_exclude); bench retained by operator decision at G4 with recall@10 ≤ 0.34% accepted residual pending Tier-3 spec absorption |

## Kill-criterion evidence

| Criterion | Result |
|---|---|
| Operator disposition recorded before execution | PASS (option a selected at execution gate) |
| Option (a) spec-text portion routed Tier 3 | PASS (`ESC-T12-1-bench-spec-note.md` emitted) |
| DoD (i)–(v) landed | PASS (see decision log `decision-logs/T12.md`) |
| Artifacts resolve | PASS (paths cited above) |

## Re-audit request

**Requested:** revision **2** of `.dev/audits/eval-consolidation/M1/2026-08-11-eval-consolidation-m1-audit.md` after T12 program-side records land (and T13/T14 per operator schedule).

**Expected re-grade inputs:** this signoff; `decision-logs/T12.md`; `ESC-T12-1-bench-spec-note.md`; corrected `registry.yaml` GAP-103 row; T2/T3 log updates; plan §2 *Landed:* lines.

**Operator signature / date:** Alejandro · 2026-08-11 (disposition option a recorded at T12 execution)
