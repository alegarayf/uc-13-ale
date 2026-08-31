# T9 sign-off — CI slice refresh script + mandatory fixture regen (item 19)

**Plan:** eval-consolidation-m1-metric-guardrail-hardening v2.0 · **Date:** 2026-08-11 · **Status:** complete

## Deliverables

| Artifact | Path |
|---|---|
| Refresh script | `eval/retrieval/scripts/refresh_elder_care_slice.py` |
| Drift policy | `eval/retrieval/README.md` § CI fixture refresh policy |
| Regenerated fixture | `eval/retrieval/fixtures/elder_care_slice.json` |
| Hermetic script tests | `eval/retrieval/tests/test_refresh_elder_care_slice.py` |

## Slice population (frozen)

| Intent | `gold_method` | `gold_status` | Positives |
|---|---|---|---|
| `fta.opex.q3_projected_financials` | `citation_backfill` | `ready` | 6 |
| `legal.contracts_vendors_platform` | `citation_backfill` | `ready` | 15 |
| `cqa.retrieve_customer_concentration` | `citation_backfill` | `ready` | 10 |

No slice intent method changes (kill criterion: method change → halt).

## Regeneration run

| Field | Value |
|---|---|
| Command | `python -m eval.retrieval.scripts.refresh_elder_care_slice` |
| Gold source | `eval/retrieval/gold_labels/elder_care.yaml` (post-T4/T5 epoch) |
| Prior fixture snapshot | `uc13_ale:35104:2026-07-30` (stale — 2026-08-05 corpus rebuild) |
| New fixture snapshot | `uc13_ale:55812:2026-08-11` |
| Union chunk ids | 31 (unique across 3 intents; prior fixture had 35 rows from old-epoch gold) |
| Live resolution | **31/31** (`resolved=31` in script stdout) |
| Warehouse path | `uc13_ale.ingestion.chunks` ⋈ `classification.doc_relevance` via `databricks-sdk` statement execution |

## Epoch hygiene

- Grep `eval/retrieval/fixtures/` for `35104` → **0 matches** post-regen.
- Fixture intents match committed gold positives (`test_elder_care_slice_ready_intents_match_committed_gold`).

## Downstream note (T5)

- Do **not** use `35104`-epoch baselines (`baseline_3831adf97292`, `baseline_544eb3f2a0e2`) as live comparison refs.
- `retrieval_harness_latest_baseline` still points at the stale pin until operator promotion (documented in runbook).

## Kill-criterion evidence

| Criterion | Result |
|---|---|
| Regenerated ids resolve live | PASS (31/31) |
| Slice intent methods unchanged | PASS (all `citation_backfill`) |
| Script regenerates without hand edits | PASS (script-only write path) |
| Fixture tests green | PASS (see suite below) |
| No old-epoch strings in fixture artifacts | PASS |

## Suite

```text
python -m pytest eval/retrieval/tests/test_elder_care_slice_fixture.py eval/retrieval/tests/test_refresh_elder_care_slice.py -q
→ 9 passed
```

Full suite run at T9 completion:

```text
python -m pytest eval/retrieval/tests/ tests/ -q
→ 976 passed, 6 skipped
```

**Operator signature / date:** executor attested 2026-08-11
