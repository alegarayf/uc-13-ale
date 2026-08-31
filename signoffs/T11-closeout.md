# T11 sign-off — S1 close-out + G4 gate review (item 22)

**Plan:** eval-consolidation-m1-metric-guardrail-hardening v2.0 · **Date:** 2026-08-11 · **Status:** complete

## G4 exit gate (charter §5 — S1 → M2 entry)

| Criterion | Evidence | Result |
|---|---|---|
| Mean recall re-baselined and interpretable | `baseline_acf58bcc4968` at `uc13_ale:55812:2026-08-11`; GAP-103 closed; bloated filename_closure epoch retired | PASS |
| Guards 15/16/17 in place and green | T6 slug guard; T7 gold guards + xfail guard (`test_gold_bootstrap.py`, `test_gate_xfail_guard.py`) | PASS |
| Golden-five queryable via `ops.e2e_linkage` | T10 backfill 15 rows; 5/5 agents (`signoffs/T10-e2e-linkage.md`) | PASS |
| Operator gold-diff eyeball recorded | T4 signoff APPROVED 2026-08-11; `signoffs/T4-eyeball-pack.json` | PASS |

**Epoch discipline:** Live comparison epoch is `baseline_acf58bcc4968` only. Do **not** use `35104`-epoch baselines (`baseline_3831adf97292`, `baseline_544eb3f2a0e2`) as live comparison refs. `retrieval_harness_latest_baseline` still points at the stale pin until operator promotion (documented in runbook).

## GAP-103 final disposition (operator-adjudicated at G4)

| Field | Value |
|---|---|
| Registry id | `GAP-103-recall-at-10-bloated-gold` |
| Prior on-disk state | `status: pending`, `evidence_refs: []` |
| Superseded history | T2-v1.1 `status: blocked` payload in `signoffs/T2-rebootstrap.md` — **not applied** |
| Final disposition | `staged` → **`closed`** |
| Rationale | Charter Amendment A2 refresh: 8 bloated KPI/profiler intents resolved (2 `citation_backfill`, 1 retained `filename_closure`, 5 `aggregate_exclude` / `no_citation_source`); 52 ready/partial + 5 annotated exclusions |
| Evidence refs | `signoffs/T4-refresh.md`, `signoffs/T4-eyeball-pack.json`, `eval/retrieval/gold_labels/elder_care.yaml`, `signoffs/T5-baseline.md`, `baseline_acf58bcc4968` |

## Registry dispositions (S1 gate review summary)

| Action | Count | Item ids |
|---|---|---|
| **Closed** (M1 evidence landed) | 5 | `GAP-103-recall-at-10-bloated-gold`, `GAP-105-no-ci-guard-gold-positives`, `GAP-105-no-cluster-gates-xfail-guard`, `OI-eval-harness-elder-care-slice-json-refresh-trigger`, `OI-eval-harness-fta-rubric-eval-fta` |
| **Accepted** (ratified known gaps) | 10 | GAP-103/105 family rows listed in `eval/program/registry.yaml` with `disposition: accepted` |
| **Staged/pending** (S2+ backlog) | 28 | Remaining S1-staged rows unchanged — product/agent/Phase-C backlog carries forward |

## Trust statement v1

| Field | Value |
|---|---|
| Generator | `eval/retrieval/trust_statement.py` v1 |
| Artifact | `.dev/eval-program/trust_statement.md` |
| Comparison epoch | `baseline_acf58bcc4968` |
| Ingestion snapshot | `uc13_ale:55812:2026-08-11` |
| Gold phrasing | 52 ready/partial + 5 annotated exclusions (no_citation_source) |
| Retrieval row | `attested` with new-epoch evidence refs only |
| Stale epoch refs | None (`35104` absent from artifact) |

## §15.3 refresh event (cross-check)

| Field | Value |
|---|---|
| Event | Full-57 gold refresh (T4) + new harness baseline (T5) |
| Date | 2026-08-11 |
| `ingestion_snapshot` | `uc13_ale:55812:2026-08-11` |
| Runbook record | `eval/retrieval/README.md` § M1 gold refresh + re-baseline |

## Kill-criterion evidence

| Criterion | Result |
|---|---|
| GAP-103 closed with operator eyeball chain | PASS (T4 APPROVED + registry row) |
| Trust statement cites new epoch only | PASS (no `35104` / stale baseline as current) |
| All G4 exit items have evidence chains | PASS |
| Suite green | PASS (see below) |

## Suite

```text
python -m pytest eval/retrieval/tests/test_trust_statement.py eval/retrieval/tests/ tests/ -q
```

Full-suite count recorded at T11 completion in CHANGELOG.

**Operator signature / date:** executor attested 2026-08-11 (G4 eyeball satisfied by T4 operator APPROVED)
