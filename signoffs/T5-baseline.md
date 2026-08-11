# T5 sign-off — Re-baseline: new comparison epoch (item 14)

**Plan:** eval-consolidation-m1-metric-guardrail-hardening v2.0 · **Date:** 2026-08-11 · **Status:** complete

## New baseline

| Field | Value |
|---|---|
| Baseline id | `baseline_acf58bcc4968` |
| Cluster run (baseline) | `772700312076387` |
| `ingestion_snapshot` | `uc13_ale:55812:2026-08-11` |
| `gold_snapshot` | `f692bb46fdb10f81dad4fb370e624d553cbd15f6c82e0a279b8e96dc2e051664` |
| Intent count | 57 |
| Report artifact | `eval/retrieval/reports/baseline_acf58bcc4968.json` |
| T4 snapshot coherence | PASS — matches T4 signoff `uc13_ale:55812:2026-08-11` |

## Gold resolution (item 16 warehouse half)

| Check | Result |
|---|---|
| Committed gold positive ids vs live `ingestion.chunks` | **3004/3004** (`T5_RESOLUTION_OK` on cluster run `772700312076387`) |
| Packet ref `test_eval_harness.py::test_eval_run_resolves_all_committed_gold_ids` | **Not present in repo** — equivalent cluster resolution check used (orchestrator naming drift; evidence below) |

## Zero-drift smoke (within-epoch)

| Field | Value |
|---|---|
| Cluster run | `837317463624897` |
| Method | Full-scope `enhancement` re-run vs `baseline_ref_run_id=baseline_acf58bcc4968` |
| Result | `T5_ZERO_DRIFT_OK max_abs_delta=0.0` |

## Negative compare (cross-epoch guard)

| Field | Value |
|---|---|
| Stale ref | `baseline_3831adf97292` (`uc13_ale:35104:2026-07-30`) |
| Cluster run | `697515193739501` |
| Expected | `IngestionSnapshotMismatchError` |
| Raised text | `ingestion_snapshot mismatch between baseline and current manifest` |
| Note | Probe held `gold_snapshot` + `registry_hash` at stale values so the epoch guard under test is `ingestion_snapshot` per `harness.py:623-626` (gold also changed at T4 — a naive compare fails earlier on `GoldSnapshotMismatchError`) |

## Runbook

- `eval/retrieval/README.md` — M1 comparison epoch pin + §15.3 refresh event record landed.

## Suite

- `python -m pytest eval/retrieval/tests/ tests/` → **938 passed, 5 skipped, 1 failed**
- Expected failure: `test_elder_care_slice_ready_intents_match_committed_gold` (T9 mandatory fixture regen — deferred at T4, not T5 scope)

## Kill-criterion evidence

| Criterion | Result |
|---|---|
| Baseline snapshot == T4 committed snapshot | PASS |
| Full-gold resolution post-refresh | PASS (3004/3004) |
| Zero-drift smoke | PASS |
| Negative cross-epoch compare | PASS |
| Runbook + baseline JSON committed | PASS (this signoff) |

**Operator signature / date:** executor attested 2026-08-11
