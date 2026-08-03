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

**Explicit non-goal:** No compare against `baseline_1aeb0ace584a` — registry hash changed (49 → 57 intents) **and** T2 full-registry rebootstrap reworked gold ground truth (see §Gold magnitude shift below). `RegistryHashMismatchError` / `GoldSnapshotMismatchError` would be expected and correct if attempted.

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

**Do not attribute recall@10 drift to registry expansion alone.** The T2 rebootstrap also redefined ground truth for most pre-existing intents (see below).

## Gold magnitude shift (T2 full-registry rebootstrap)

Compared to pre-T2 committed gold (`a3634eb`, 49 rows, snapshot `uc13_ale:35034:2026-07-02`) vs post-T2 (`515d322`, 57 rows, `uc13_ale:35104:2026-07-30`):

| Metric | Pre-T2 | Post-T2 |
|--------|--------|---------|
| Total `positive_chunk_ids` | 51,987 | 23,721 (−54%) |
| Pre-existing intents with changed positives | — | 41 / 49 |
| Pre-existing intents with drop > 5 chunks | — | 28 |
| `partial` → `ready` transitions | — | 16 |
| `filename_closure` → `citation_backfill` | — | 16 |

**Mechanism:** `GoldLabelBootstrap.bootstrap()` regenerates every registry row. Fresh post-merge analysis citations (CQA/KPI/QoE/BMA, `created_at` ≥ 2026-07-28) unlocked `citation_backfill` for intents that previously fell back to broad `filename_closure` sets (thousands of chunks). This is a precision upgrade by design, not a yaml hand-edit.

**Largest pre-existing drops (examples):**

| Intent | Pre | Post | Transition |
|--------|-----|------|------------|
| `bma.retrieve_workforce_and_capacity` | 3,796 | 36 | partial/filename_closure → ready/citation_backfill |
| `cqa.retrieve_payor_mix` | 3,251 | 10 | partial/filename_closure → ready/citation_backfill |
| `qoe.retrieve_revenue_quality` | 3,251 | 73 | partial/filename_closure → ready/citation_backfill |

**Spot-check (2026-07-30):** Five mixed-method intents verified on live `uc13_ale` — all positive chunk IDs resolve in `ingestion.chunks`; citation_backfill rows have analysis citations. Verdict: **accepted precision upgrade** (`.dev/scripts/spot_check_gold_citations.py`).

**Review tooling:** `python .dev/scripts/diff_gold_labels.py --before <ref> --after <ref> --fail-on-threshold` — mandatory before any future full rebootstrap commit.

**phv4 NEW-2 / D-14.5:** **CLOSED 2026-07-30** — substitute stability evidence accepted. Attestation: `.dev/attestations/chip-a-g6-d14-5-baseline-sign-off.md`.

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
