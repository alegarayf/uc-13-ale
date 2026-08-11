# T4 sign-off — Full-57 gold refresh (charter Amendment A2)

**Plan:** eval-consolidation-m1-metric-guardrail-hardening v2.0 · **Date:** 2026-08-11 · **Status:** operator approved

## Cluster run

| Field | Value |
|---|---|
| Run ID | `958769428875629` |
| Driver workspace path | `/Users/alejandro.garay@nimblegravity.com/t4_full57_refresh_driver.py` |
| Staged volume path | `/Volumes/uc13_ale/analysis/reports/eval_staging/elder_care_full57_t4.yaml` |
| Staged local evidence | `signoffs/T4-staged-elder_care-full57.yaml` |
| SHA256 sentinel | `T4_SHA256_ALL_OK` |

## Payload hashes (embedded at submit time)

| Artifact | SHA256 |
|---|---|
| `eval/retrieval/gold/bootstrap.py` | `ed52c65afb2bffd093ce7b11c23c2a151d48472e48a3dfdcbf2cf7d547b09c94` |
| `eval/retrieval/models.py` | `2a51664dad1d04aafa75d7771e78e97839b32ce96985db798efedc0cda1f76a2` |
| `eval/retrieval/errors.py` | `946e332c7131dcf59a58e386d0fb203699d3747d8e5992cba9922f4f408e5f5c` |
| `eval/retrieval/intent_registry.yaml` | `6cff2533a3509e131bab100bf8b149f2006006e557e3410c5fff421a292054b7` |
| `eval/retrieval/gold/kpi_claim_intent_map.yaml` | `5adb9f7639f7439e2eb943bdc59b6c277aa26de0e444f1eff406b914f566c35d` |
| `eval/retrieval/gold/gold_exclusions.yaml` | `4a9ea546794bb40c1482dca645f97a56ee362084030e5ed7f1a1238b9fd98887` |

## Snapshot & scope

- **Ingestion snapshot:** `uc13_ale:55812:2026-08-11` (count component asserted == 55,812 on cluster)
- **Intent count:** 57 / 57 (registry-derived)
- **Ready/partial:** 52 · **Annotated exclusions:** 5 · **Other bootstrap_failed:** 0
- **Total positive chunk ids (union):** 3,004 · **Resolution rate:** 100% (3,004/3,004)

## Kill-criterion evidence

| Criterion | Result |
|---|---|
| Snapshot count == 55,812 | PASS (`T4_SNAPSHOT_OK uc13_ale:55812:2026-08-11`) |
| Non-item-12 method changes | PASS (0 / 49 — see `signoffs/T4-eyeball-pack.json`) |
| Exclusion population == 5 | PASS |
| Staged ids live resolution | PASS (100%) |
| Payload hash verification | PASS (`T4_SHA256_ALL_OK`) |

## Item-12 eyeball diffs (8 intents)

See `signoffs/T4-eyeball-pack.json` → `item12_diffs`. Summary:

| Intent | Before → After | Method transition |
|---|---|---|
| `kpi.retrieve_healthcare_ops` | 2829 partial → 20 ready | `filename_closure` → `citation_backfill` (pool ≈20) |
| `kpi.retrieve_healthcare_revenue_per_unit` | 2829 partial → 53 ready | `filename_closure` → `citation_backfill` (pool ≈53) |
| `kpi.retrieve_bench_and_capacity` | 2842 partial → 2925 partial | **unchanged** `filename_closure` (no mapped claims; not in exclusion artifact) |
| 4 KPI + `profiler.company_size_indicators` | bloated partial → 0 excluded | → `bootstrap_failed` + `aggregate_exclude` / `no_citation_source` |

**Eyeball note:** Plan §0.2 predicted 3 × `citation_backfill` transitions; live outcome is **2** citation_backfill + **1** retained `filename_closure` (`bench_and_capacity`, unmappable per T2-a). Excluded population matches plan (5).

## Non-item-12 statistical summary (49 intents)

- Method changes: **0**
- Status changes: **0**
- Count delta: min −9, max +19, mean +0.35, median −1

## GAP-103 evidence refs

- This refresh replaces bloated `filename_closure` gold for item-12 KPI/profiler intents against the post-2026-08-05 corpus (55,812 chunks).
- Staged evidence + eyeball pack: `signoffs/T4-staged-elder_care-full57.yaml`, `signoffs/T4-eyeball-pack.json`.
- Final disposition deferred to T11 close-out per plan.

## Operator eyeball gate

- [x] **APPROVED** — proceed with single commit (gold + manifest + `INGESTION_SNAPSHOT`)
- [ ] **REJECTED** — gold uncommitted; escalate with evidence

**Operator signature / date:** APPROVED 2026-08-11 (Alejandro)
