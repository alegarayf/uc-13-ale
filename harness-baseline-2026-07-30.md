# Harness baseline re-attestation — 2026-07-30 (Chip A / G6 T7)

**Company / catalog:** Elder Care / `uc13_ale`  
**Outcome:** New control baseline promoted after 57-intent registry expansion (Hector merge CQA+4, KPI+4). Prior baseline superseded — **not** cross-comparable.

---

## What we were trying to do

Per `GOLD_LABEL_BOOTSTRAP_HANDOFF.md` §8 Step A5 (O-14.1): run the retrieval harness against the newly-expanded **57-intent** registry and **57-row** gold file (`eval/retrieval/gold_labels/elder_care.yaml`), promote the run as the new Elder Care control baseline, and update runbook pins.

**Prerequisites (re-checked at execution):**

| Gate | Evidence |
|------|----------|
| T5 pytest | `765 passed, 5 skipped, 0 xfailed` — `.dev/plans/chip-a-g6-gold-bootstrap/T5-pytest-stdout.txt`; G6 PASS in `CLUSTER_GATES.md` (gold bootstrap scope) |
| T6 preflight | `pytest tests/test_join_integrity.py` — 5 passed; live `orphan_chunk_count=0`; VS index `ready=True`, `indexed_row_count=112,145` ≥ `elder_care_embeddings=35,104` |

**Explicit non-goal:** No compare against `baseline_1aeb0ace584a` — registry hash changed (49 → 57 intents). `RegistryHashMismatchError` / `GoldSnapshotMismatchError` would be expected and correct if attempted.

---

## Invocation (frozen CLI)

```bash
python -m eval.retrieval.harness_cli run \
  --store-backend delta \
  --run-type baseline \
  --company-name "Elder Care" \
  --catalog uc13_ale
```

`--baseline-ref-run-id` **omitted** (no retro-compare to pre-expansion baseline).

**Databricks serverless job:** `906802094204729` (runner uploaded to workspace; stdout captured locally).

---

## Final state (promoted)

| Item | Value |
|------|--------|
| **New control baseline** | `baseline_544eb3f2a0e2` |
| **Registry hash (hash C)** | `6cff2533a3509e131bab100bf8b149f2006006e557e3410c5fff421a292054b7` |
| **Gold snapshot** | `9f2619ba07fa429a14e0a82b092aaacd805db6ce59b321e59938ccde2659be80` |
| **Ingestion snapshot** | `uc13_ale:35104:2026-07-30` |
| **Intent count** | 57 |
| **harness_status** | `complete` |
| **gate_pass** | `null` (normal for `run_type=baseline`) |
| **Supersedes** | `baseline_1aeb0ace584a` (registry hash `9c73ed78…` — 49-intent era; **do not cross-compare recall@10**) |

**`retrieval_harness_latest_baseline` view:** confirms `baseline_544eb3f2a0e2` for Elder Care / `uc13_ale`.

---

## Registry incomparability (kill-criterion narrative)

This baseline attests harness health on the **post-Hector-merge 57-intent registry** and T2-rebootstrapped gold — **not** a stability regression vs `baseline_1aeb0ace584a`. Any future enhancement/ablation runs on this registry must pin `baseline_ref_run_id=baseline_544eb3f2a0e2` (or a successor promoted under the same registry hash).

**phv4 NEW-2 / D-14.5:** This artifact exists for operator sign-off on whether the new baseline substitutes prior stability evidence — **not resolved in this subtask**.

---

## Cross-reference

- G6 gold bootstrap PASS (T5, pre-baseline): `.dev/plans/hector-ui-pipeline-merge/CLUSTER_GATES.md` § G6
- Prior baseline narrative: `harness-baseline-2026-07-15.md` (`baseline_1aeb0ace584a`)
- Harness stdout: `.dev/plans/chip-a-g6-gold-bootstrap/T7-harness-stdout.txt`

---

## Key snippet

```python
BASELINE_REF = "baseline_544eb3f2a0e2"  # 57-intent registry (hash C); supersedes baseline_1aeb0ace584a
```
