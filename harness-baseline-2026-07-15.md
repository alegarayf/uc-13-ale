# Harness baseline re-attestation — 2026-07-15 (~1.5 hr)

**Company / catalog:** Elder Care / `uc13_ale`  
**Outcome:** Fixed. New control baseline promoted. Jul 3 compare waived (registry change).

---

## What we were trying to do

Re-run harness baseline after M-PHV4 and compare vs pinned control `baseline_299063e87806` (2026-07-03). Runbook step: no recall regression on gate-eligible intents.

**First attempts failed:** `gate_pass: False` on `baseline_f682f8e59b96`, `baseline_10b89226eb1d`.

---

## What was actually wrong (two bugs, not code regression)

### 1. Stale vector search index

Cell 7 not finishing with `✓ Index ready` → Delta had embeddings but VS didn’t serve them.  
`legal.insurance` returned lease PDFs instead of COI; sim scores ~0.25 vs ~0.45 on Jul 3.

**Fix:** Sync-only cell (`ingestion_parser._wait_for_index_sync`) — **not** full Cell 7.  
Result: `37,341 rows indexed | COMPLETED`.

### 2. Registry vs classifier mismatch (`legal.insurance`)

Classifier tags insurance/COI as **`BACKGROUND`** (by design in `document_classifier.py`).  
Intent used **`workstream_filter: [LEGAL]`** only → COI filtered out even when index was healthy.

**Fix (Option A):** Add `BACKGROUND` to `legal.insurance` workstream filter in:

- `eval/retrieval/intent_registry.yaml`
- `eval/retrieval/registry_extractor.py`
- `databricks/agents/workstreams/legal_contracts_agent.py`

Probe B after fix: COI returns. Provenance matches Jul 3 (6× `Elder Care NY COI.pdf`, sim ~0.41–0.45).

---

## Red herrings (not bugs)

| Observation | Reality |
|-------------|---------|
| `gate_pass: null` on manifest | Normal for `run_type=baseline` |
| Empty `retrieval_harness_deltas` | Manual `compare()` doesn’t persist; use `store.append_deltas()` if needed |
| Re-run Cell 5/6 classifier | Tags unchanged — insurance is supposed to be BACKGROUND |
| Compare vs Jul 3 after Option A | **`RegistryHashMismatchError`** — intentional; different intent config |

---

## Final state (promoted)

| Item | Value |
|------|--------|
| **New control baseline** | `baseline_1aeb0ace584a` |
| **Alternate (equivalent)** | `baseline_813d0dd1b188` |
| **Registry hash** | `9c73ed78a5d7e0cbc1cee4ddd0ec5d13da7139842cac057039db7572d2af0778` |
| **Stability** | `gate_pass: True` between the two new runs |
| **validate-baseline** | OK on `baseline_1aeb0ace584a` |
| **Supersedes** | `baseline_299063e87806` (document waiver, don’t compare across registry versions) |

**Informal Jul 3 diff:** Only material mover besides `legal.insurance` fix → `kpi.retrieve_kpi_dashboard` −2.3pp (partial gold; stable across new runs — note, don’t block).

---

## What’s left (runbook)

1. FTA Cell 12 → ≥ **16/18**
2. Legal Cell 16 → ≥ **7/11**
3. `record_e2e_linkage` for pipeline `run_id`s
4. Update `BASELINE_REF` pins in README / `my_runbook.md` → `baseline_1aeb0ace584a`

---

## Key snippets

**Sync-only (when Delta OK, index stale):**

```python
import ingestion_parser as ip
ip._wait_for_index_sync(spark=spark, catalog="uc13_ale", schema="ingestion",
    index_suffix="embeddings_index", table_embeddings="uc13_ale.ingestion.embeddings")
```

**New baseline (no compare to Jul 3):**

```python
BASELINE_REF = "baseline_1aeb0ace584a"
report = harness.run(run_type="baseline", company_name="Elder Care", catalog="uc13_ale", ...)
```

---

## Deeper write-up

`.dev/issues/2026-07-15-harness-baseline-gate-failure-elder-care.md`
