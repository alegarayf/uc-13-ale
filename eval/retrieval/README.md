# UC13 RE² — Retrieval Evaluation Package

Offline harness, intent registry, gold labels, and eval store for the UC13 retrieval measurement program (M-RE1).

## Local development

```bash
pip install -r eval/retrieval/requirements.txt
pytest eval/retrieval/tests/
```

`pytest.ini` sets `pythonpath = databricks, .` so production `agents.shared.retrieval` and `eval.retrieval` import together.

## CI fixture

Frozen organic slice: `fixtures/elder_care_slice.json` (`EvalFixtureSlice`). Chunk rows are copied from `uc13_ale` at export time; pytest mocks VS/embed only — it does not invent corpus text.

## Cluster baseline runbook (Elder Care / `uc13_ale`)

Run once per Cell 7 ingestion rebuild or retrieval code change. Charter exit gate G2 (VS `company_name` pushdown) is verified during setup.

**Workspace catalog:** Elder Care baseline uses **`uc13_ale` for everything** — corpus, VS index, gold labels, **and** ops tables (`uc13_ale.ops.*`). The program charter examples use `uc13.ops` for a shared merge target; keep ops in `uc13_ale` until you promote upstream.

**Active baseline pin (2026-07-16):** `baseline_1aeb0ace584a` per `retrieval_harness_latest_baseline` (alternate stability twin: `baseline_813d0dd1b188`). Supersedes M-RE3 `baseline_299063e87806` after `legal.insurance` registry fix — do not cross-compare across registry versions (`RegistryHashMismatchError`).

### 1. Upstream preconditions (§5.15)

- Cell 8c coverage PASS; Vector Search index sync current; join integrity (R-08) — run [join integrity (R-08)](#join-integrity-r-08) preflight before baseline.
- Registry intents for this baseline use `catalog: uc13_ale` (not legacy `uc13` default).

### 2. DDL preflight — required before delta baseline

Apply ops DDL **once** before the first `DeltaEvalStore` write. Use the **same catalog as the harness** (`uc13_ale`).

**Notebook cell** (after Cell 1 — `REPO_ROOT` on `sys.path`):

```python
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from eval.retrieval.scripts.apply_ops_ddl import apply_ops_ddl

OPS_CATALOG = "uc13_ale"
n = apply_ops_ddl(OPS_CATALOG)
print(f"Applied {n} statements → {OPS_CATALOG}.ops")
display(spark.sql(f"SHOW TABLES IN {OPS_CATALOG}.ops"))
```

Shell equivalent (repo root on cluster):

```bash
python eval/retrieval/scripts/apply_ops_ddl.py --catalog uc13_ale
```

HALT: do not attempt `--store-backend delta` baseline until this succeeds. Missing DDL causes `insert_run` failures (blocked, not `invalid`).

### 3. G2 — VS `company_name` pushdown probe (required, log result)

Before the harness baseline, run a single probe query with `company_name` filter on the cluster and **record whether filter pushdown was accepted**.

Example (Databricks notebook or job cell):

```python
from databricks.sdk import WorkspaceClient
from agents.shared.retrieval import semantic_search
from pyspark.sql import SparkSession

spark = SparkSession.getActiveSession()
company = "Elder Care"
catalog = "uc13_ale"

# Capture stdout: semantic_search / _query_vector_index logs pushdown acceptance or fallback.
result = semantic_search(
    query="revenue growth historical financial statements",
    spark=spark,
    company_name=company,
    catalog=catalog,
    top_k=5,
)
print(
    f"[G2 probe] company_name={company!r} catalog={catalog!r} "
    f"mode={result.mode} result_count={len(result.chunks)}"
)
```

**Interpretation (charter G2 / §5.15):**

| Log / outcome | Baseline status |
|---------------|-----------------|
| No `VS filter pushdown unavailable` message; filtered query succeeds | Proceed — valid multi-tenant interpretation |
| `VS filter pushdown unavailable (...)` printed; unfiltered fallback used | Mark baseline `harness_status: invalid` — acceptable per M-RE1 exit gate; document remediation (index schema / admin recreate) before using as `baseline_ref_run_id` |

Save probe output in the job log or PR notes. The harness does not auto-mark invalid on probe failure in v1 — operator responsibility per §5.15.

## join integrity (R-08)

Hydrate and gold-bootstrap SQL both inner-join `ingestion.chunks` to `classification.doc_relevance` on:

- `chunks.file_name = doc_relevance.filename`
- `chunks.company_name = doc_relevance.company_name`

Orphan chunks (no matching `doc_relevance` row for that file + company pair) are **dropped** by that join — they never surface in retrieval hydrate or filename-closure gold labels. Item 27 adds an executable guard so join drift is caught in CI, not only in this runbook bullet.

### CI regression guard (required before merge / baseline)

```bash
pytest tests/test_join_integrity.py -v
```

The test module uses a synthetic fixture with known orphan and non-orphan rows. It asserts:

1. `_hydrate_chunks_sql` and `eval/retrieval/gold/bootstrap.py` still use the join predicate above (shape drift → test failure).
2. Orphan chunks are **counted and listed**, not silently ignored when simulating the inner join.

This pytest check validates join **logic** and source-shape stability. It is **not** a substitute for a live-cluster orphan count after ingestion — schedule that separately if production data quality gates require it.

### Operator cluster spot-check (recommended before baseline)

After Cell 7 / Cell 8c, run on the target catalog (Elder Care baseline: `uc13_ale`):

```sql
SELECT COUNT(*) AS orphan_chunk_count
FROM uc13_ale.ingestion.chunks c
LEFT JOIN uc13_ale.classification.doc_relevance r
  ON c.file_name = r.filename
 AND c.company_name = r.company_name
WHERE c.company_name = 'Elder Care'
  AND r.filename IS NULL;
```

**Interpretation:**

| `orphan_chunk_count` | Action |
|----------------------|--------|
| `0` | Proceed — join integrity OK for this company |
| `> 0` | HALT baseline — investigate classifier coverage or filename normalization drift before harness run |

Record the count in the job log or PR notes alongside the G2 probe output.

## M-RE3 VS filter pushdown spike (items 24–25)

Entry gate **before** implementing `workstream` / `priority_tier` metadata filter pushdown in `retrieval.py` (T2). The probe calls `WorkspaceClient().vector_search_indexes.query_index()` **directly** — it does **not** use `semantic_search` / `_query_vector_index`, which silently retries without `filters_json` on SDK errors.

**Index columns (already synced):** `workstream` (`ARRAY<STRING>`), `priority_tier` (`INT`), `company_name` — see `databricks/jobs/scripts/setup_vector_search.py`.

### Operator run

**Notebook cell** (after Cell 1 — `REPO_ROOT` on `sys.path`, `catalog` / `sp_company_name` widgets):

```python
from pathlib import Path

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

scripts_dir = str(Path(REPO_ROOT) / "jobs" / "scripts")
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

import importlib
import vs_filter_pushdown_probe as probe
importlib.reload(probe)

summary = probe.main(spark, catalog="uc13_ale", company_name="Elder Care")
print(summary)
```

**G2 re-verify snippet** (same session — confirms `company_name` pushdown still accepted):

```python
from agents.shared.retrieval import semantic_search

result = semantic_search(
    query="revenue growth historical financial statements",
    spark=spark,
    company_name="Elder Care",
    catalog="uc13_ale",
    top_k=5,
)
print(
    f"[G2 re-verify] company_name='Elder Care' catalog='uc13_ale' "
    f"mode={result.mode} result_count={len(result.chunks)}"
)
# PASS when stdout has no "VS filter pushdown unavailable" line.
```

After the run, copy stdout into the job log or PR notes and update the matrix cells below from probe log lines (`status=pass` / `status=fail`). **Do not mark `PASS` without cluster stdout evidence.**

### Operator attestation (cluster run)

**Date:** 2026-07-03 · **Workspace:** `uc13_ale` · **Company:** Elder Care · **Operator:** Ale

**Probe summary:** `{'company_name': 'pass', 'workstream': 'pass', 'priority_tier': 'pass'}` — all 11 candidates `sdk_accepted` (direct `query_index`, no `retrieval.py` fallback).

**G2 re-verify:** `semantic_search(..., company_name="Elder Care", catalog="uc13_ale")` → `mode=semantic`, `result_count=5`, no `VS filter pushdown unavailable` line.

<details>
<summary>Probe stdout (archived)</summary>

```
[vs_filter_pushdown_probe] index='uc13_ale.ingestion.embeddings_index' company_name='Elder Care' catalog='uc13_ale'
[vs_filter_pushdown_probe] dimension=company_name status=pass label=equality {"company_name": 'Elder Care'} :: sdk_accepted result_count=5 filters_json={"company_name": "Elder Care"}
[vs_filter_pushdown_probe] dimension=workstream status=pass label=equality scalar {"workstream": "FINANCIAL"} :: sdk_accepted result_count=5 filters_json={"workstream": "FINANCIAL"}
[vs_filter_pushdown_probe] dimension=workstream status=pass label=list any-of {"workstream": ["FINANCIAL"]} :: sdk_accepted result_count=5 filters_json={"workstream": ["FINANCIAL"]}
[vs_filter_pushdown_probe] dimension=workstream status=pass label=list any-of {"workstream": ["FINANCIAL", "BUSINESS_MODEL"]} :: sdk_accepted result_count=5 filters_json={"workstream": ["FINANCIAL", "BUSINESS_MODEL"]}
[vs_filter_pushdown_probe] dimension=workstream status=pass label=LIKE {"workstream LIKE": "FINANCIAL"} :: sdk_accepted result_count=5 filters_json={"workstream LIKE": "FINANCIAL"}
[vs_filter_pushdown_probe] dimension=priority_tier status=pass label=equality {"priority_tier": 2} :: sdk_accepted result_count=5 filters_json={"priority_tier": 2}
[vs_filter_pushdown_probe] dimension=priority_tier status=pass label=lte {"priority_tier <=": 2} :: sdk_accepted result_count=5 filters_json={"priority_tier <=": 2}
[vs_filter_pushdown_probe] dimension=priority_tier status=pass label=gte {"priority_tier >=": 1} :: sdk_accepted result_count=5 filters_json={"priority_tier >=": 1}
[vs_filter_pushdown_probe] dimension=priority_tier status=pass label=lt {"priority_tier <": 3} :: sdk_accepted result_count=5 filters_json={"priority_tier <": 3}
[vs_filter_pushdown_probe] dimension=workstream status=pass label=company + workstream {"company_name": 'Elder Care', "workstream": "FINANCIAL"} :: sdk_accepted result_count=5 filters_json={"company_name": "Elder Care", "workstream": "FINANCIAL"}
[vs_filter_pushdown_probe] dimension=priority_tier status=pass label=company + tier lte {"company_name": 'Elder Care', "priority_tier <=": 2} :: sdk_accepted result_count=5 filters_json={"company_name": "Elder Care", "priority_tier <=": 2}
[vs_filter_pushdown_probe] summary={'company_name': 'pass', 'workstream': 'pass', 'priority_tier': 'pass'}
```

</details>

**T2 gate:** **DECIDED OFF** (M-PHV4 PG5 fail, 2026-07-15) — `vs_metadata_filters` default stays `False`. Attestation: `.dev/attestations/m-phv4-r02-vs-metadata-filters-ab-elder-care-2026-07-15.md`. Probe results below are **historical evidence** only; T2 VS metadata filter pushdown is not in scope.

### Pass/fail matrix

| Candidate `filters_json` (standard-endpoint dict) | Dimension | Result | Notes |
|---------------------------------------------------|-----------|--------|-------|
| `{"company_name": "Elder Care"}` | `company_name` | PASS | G2 re-verify; same predicate as `retrieval._query_vector_index` |
| `{"workstream": "FINANCIAL"}` | `workstream` | PASS | Scalar equality on `ARRAY<STRING>` — sdk_accepted 2026-07-03 |
| `{"workstream": ["FINANCIAL"]}` | `workstream` | PASS | Multi-value any-of per VS filter guide |
| `{"workstream": ["FINANCIAL", "BUSINESS_MODEL"]}` | `workstream` | PASS | Overlap proxy (any-of); not documented as `ARRAY_CONTAINS` |
| `{"workstream LIKE": "FINANCIAL"}` | `workstream` | PASS | Docs workaround when native array overlap unsupported |
| `{"priority_tier": 2}` | `priority_tier` | PASS | Equality |
| `{"priority_tier <=": 2}` | `priority_tier` | PASS | Operator-suffixed `<=` key |
| `{"priority_tier >=": 1}` | `priority_tier` | PASS | Operator-suffixed `>=` key |
| `{"priority_tier <": 3}` | `priority_tier` | PASS | Operator-suffixed `<` key |
| `{"company_name": "Elder Care", "workstream": "FINANCIAL"}` | `workstream` | PASS | Multi-key AND + tenant filter |
| `{"company_name": "Elder Care", "priority_tier <=": 2}` | `priority_tier` | PASS | Multi-key AND + tier cap |

**Dimension rollup (for T2 gate):** `workstream` / `priority_tier` summary is `pass` when **any** row for that dimension is `PASS` on a live cluster run; dimensions are independent (partial pass is valid — T2 implements only passing dimensions). `company_name` summary is `pass` / `fail` only (G2 re-verify).

**T2 partial-pass note:** If e.g. `workstream` rows pass but all `priority_tier` rows fail, T2 wires pushdown for `workstream` only — not all-or-nothing.

### 4. Cluster baseline harness

**Notebook cell** (recommended):

```python
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from eval.retrieval.harness import EvalHarness
from eval.retrieval.store import DeltaEvalStore

CATALOG = "uc13_ale"
harness = EvalHarness()
store = DeltaEvalStore(spark, catalog=CATALOG)

report = harness.run(
    run_type="baseline",
    company_name="Elder Care",
    catalog=CATALOG,
    store=store,
    store_backend="delta",
    spark=spark,
)
print("run_id:", report.manifest.run_id)
print("harness_status:", report.manifest.harness_status)
```

Shell equivalent:

```bash
python -m eval.retrieval.harness_cli run \
  --store-backend delta \
  --run-type baseline \
  --company-name "Elder Care" \
  --catalog uc13_ale
```

- **Must** pass `--store-backend delta` on cluster (not sqlite).
- Report written to `eval/retrieval/reports/{run_id}.json`.
- Query manifest:

```sql
SELECT * FROM uc13_ale.ops.retrieval_harness_runs WHERE run_id = '<id>';
```

**G4 verify** (Elder Care workspace):

```sql
SELECT run_id, harness_status, completed_at
FROM uc13_ale.ops.retrieval_harness_latest_baseline
WHERE company_name = 'Elder Care' AND catalog = 'uc13_ale';
```

If G2 probe failed, set `harness_status: invalid` on the manifest (operator step) and do not use the run as `baseline_ref_run_id`.

### 5. Optional — local sqlite baseline

For laptop iteration without cluster:

```bash
python -m eval.retrieval.harness_cli run \
  --store-backend sqlite \
  --run-type baseline \
  --company-name "Elder Care" \
  --catalog uc13_ale
```

Store path: `eval/retrieval/.local/re2_store.sqlite` (gitignored). Requires active `SparkSession` for live retrieval dispatch unless tests inject `retrieval_dispatch`.

### 6. Promote local run to Delta (after validation)

When a completed sqlite run should be shared on the cluster:

```bash
python -m eval.retrieval.scripts.sync_eval_store \
  --run-id <id> \
  --direction sqlite_to_delta \
  --catalog uc13_ale
```

Optional: `--sqlite-path <path>`. Idempotent on `run_id` when Delta already has a complete run. Does **not** sync Delta → SQLite.

## M-RE3 ablation matrix runbook (merge-rank arms)

Operator steps for M-RE3 exit gate **item 28** (merge-rank ablation matrix with `HarnessDelta` vs baseline). Requires T4 ablation dispatch wiring (`--ablation-config`) and a **complete** baseline in Delta for the tenant.

**Coverage disclosure (M-RE2 Finding F1 precedent):** Live-cluster execution of this matrix against real Elder Care retrieval has **not** occurred as part of the M-RE3 coding session. CI proves the mechanism via `eval/retrieval/tests/test_ablation.py::test_ablation_matrix_four_arms_produce_distinct_runs_and_deltas` (SQLite + injected `retrieval_dispatch`). Operator cluster runs below are required before treating item 28 as attested on real corpus data.

**Baseline reference:** Pin `baseline_ref_run_id=baseline_1aeb0ace584a` (M-PHV4 post-consolidation Elder Care baseline, promoted 2026-07-15). Historical: M-RE3 `baseline_299063e87806` (2026-07-03); M-RE1 `baseline_f0f4f68ac7af`.

**Intent scope:** Omit `--affected-intents` entirely for ablation runs. Per spec §5.12.1, `run_type: ablation` defaults to **all registered intents** when the flag is omitted (`EvalHarness._resolve_scope`). Do not pass a narrowed intent list — that would silently under-scope gate computation relative to retrieval code changes in T2/T3/T4.

**Store backend:** Cluster runs **must** use `--store-backend delta` (never `sqlite` on cluster ablation runs).

**Arms in scope (4):** `merge_rank_on`, `merge_rank_off`, `sim_only`, `tier_only`. Each maps to `semantic_search(..., merge_rank_mode=...)` per plan D7.

**Not in scope for cluster matrix:** `vs_filter_pushdown` — T2 landed `semantic_search(..., vs_metadata_filters=False)` but the harness arm is not dispatchable in M-RE3 (`ablation_arm_to_merge_rank_mode` raises `PreconditionError`). Do not include a 5th cluster invocation until a follow-on wires dispatch.

### Preflight

1. DDL applied for `uc13_ale.ops` (same as baseline runbook §2).
2. Complete baseline exists and is valid for `baseline_ref_run_id` (G2 probe passed for that baseline).
3. `validate-baseline` passes for the pinned baseline:

```bash
python -m eval.retrieval.harness_cli validate-baseline \
  --store-backend delta \
  --catalog uc13_ale \
  --baseline-ref-run-id baseline_1aeb0ace584a \
  --company-name "Elder Care"
```

### Cluster ablation invocations (one per arm)

Run each command separately. Each produces its own `run_id` and `HarnessDelta` rows vs the pinned baseline. `baseline_ref_run_id` resolves automatically via `retrieval_harness_latest_baseline` when omitted; pin explicitly when comparing against M-RE1:

**Notebook cell** (after Cell 1 — `REPO_ROOT` on `sys.path`):

```python
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from eval.retrieval.harness import EvalHarness
from eval.retrieval.store import DeltaEvalStore

CATALOG = "uc13_ale"
BASELINE_REF = "baseline_1aeb0ace584a"  # M-PHV4 post-consolidation (promoted 2026-07-15)
harness = EvalHarness()
store = DeltaEvalStore(spark, catalog=CATALOG)

for arm in ("merge_rank_on", "merge_rank_off", "sim_only", "tier_only"):
    report = harness.run(
        run_type="ablation",
        company_name="Elder Care",
        catalog=CATALOG,
        store=store,
        store_backend="delta",
        baseline_ref_run_id=BASELINE_REF,
        ablation_config={"arm": arm},
        spark=spark,
    )
    print(f"arm={arm} run_id={report.manifest.run_id} gate_pass={report.manifest.gate_pass}")
```

**Shell equivalents** (repo root on cluster; run each arm separately):

```bash
python -m eval.retrieval.harness_cli run --store-backend delta --run-type ablation \
  --company-name "Elder Care" --catalog uc13_ale \
  --baseline-ref-run-id baseline_1aeb0ace584a \
  --ablation-config '{"arm": "merge_rank_on"}'
```

```bash
python -m eval.retrieval.harness_cli run --store-backend delta --run-type ablation \
  --company-name "Elder Care" --catalog uc13_ale \
  --baseline-ref-run-id baseline_1aeb0ace584a \
  --ablation-config '{"arm": "merge_rank_off"}'
```

```bash
python -m eval.retrieval.harness_cli run --store-backend delta --run-type ablation \
  --company-name "Elder Care" --catalog uc13_ale \
  --baseline-ref-run-id baseline_1aeb0ace584a \
  --ablation-config '{"arm": "sim_only"}'
```

```bash
python -m eval.retrieval.harness_cli run --store-backend delta --run-type ablation \
  --company-name "Elder Care" --catalog uc13_ale \
  --baseline-ref-run-id baseline_1aeb0ace584a \
  --ablation-config '{"arm": "tier_only"}'
```

### Post-run verification

**Manifest check** — expect `run_type=ablation`, non-null `ablation_arm` matching the config, and `baseline_ref_run_id` pinned:

```sql
SELECT run_id, run_type, ablation_arm, baseline_ref_run_id, gate_pass, harness_status
FROM uc13_ale.ops.retrieval_harness_runs
WHERE run_type = 'ablation'
  AND company_name = 'Elder Care'
  AND catalog = 'uc13_ale'
ORDER BY completed_at DESC
LIMIT 10;
```

**HarnessDelta shape** — per intent, per gate metric (`recall_at_10`, `precision_at_10`, `basis_conflict_at_10`, `mrr`):

```sql
SELECT run_id, intent_id, metric, before_value, after_value, delta_value, gate_pass, in_gated_scope
FROM uc13_ale.ops.retrieval_harness_deltas
WHERE run_id IN ('<merge_rank_on_run_id>', '<merge_rank_off_run_id>', '<sim_only_run_id>', '<tier_only_run_id>')
ORDER BY run_id, intent_id, metric;
```

Expect four distinct `run_id`s, each with `ablation_arm` populated on manifest and result rows. At least one arm should show non-zero `delta_value` on a gated metric vs `baseline_299063e87806` (merge-rank mode changes chunk ordering on cluster retrieval). Cluster attestation (2026-07-03): `merge_rank_on` gate_pass=true; alt arms false — production default confirmed.

**Provenance:** Query ablation provenance by harness `run_id`, not pipeline `run_id` — harness and pipeline runs share `append_provenance` but use different manifest `run_id`s.

## M-RE3 post-hardening re-baseline + E2E runbook

Operator steps for M-RE3 exit gates **item 29** (post-hardening harness baseline), **FTA 18-field** re-score, and **Legal 11-item** re-score after T2–T5 hardening lands. Requires `test_pipeline.ipynb` Cell 1 (`set_pipeline_thread`, `REPO_ROOT` on `sys.path`) before any agent `main()` — run Cell 12 / Cell 16 **after** Cell 1.

**Coverage disclosure (M-RE2 F1 precedent):** Live-cluster execution of the post-hardening baseline, ablation matrix (see § M-RE3 ablation matrix runbook above), and E2E re-scores has **not** occurred as part of the M-RE3 coding session. CI proves harness mechanism; operator cluster runs below are required before treating item 29 as attested.

**Control baseline reference:** Active pin **`baseline_1aeb0ace584a`** (promoted 2026-07-15; supersedes M-RE3 `baseline_299063e87806`). FTA checklist **16/18** · Legal **7/11 pass** (M-PHV4 T8, 2026-07-16).

**Baseline authority (Flag 7):** **Authoritative baseline:** `baseline_1aeb0ace584a` per `retrieval_harness_latest_baseline` (operator-promoted 2026-07-15). Historical M-RE3: `baseline_299063e87806` (2026-07-03). Do not promote incomplete local report JSON (e.g. `baseline_fb7118e87dad`) without operator designation.

**Intent scope:** Omit `--affected-intents` for the post-hardening baseline. Per spec §5.12.1, `run_type: baseline` defaults to **all registered intents** when the flag is omitted — required because M-RE3 changed `retrieval.py`, `databricks/agents/shared/fallback.py`, and harness ablation dispatch (full-suite scope).

**Triplet pin awareness:** `validate_baseline_ref` still checks `registry_hash`, `gold_snapshot`, and `ingestion_snapshot` on the pinned baseline. A Cell 7 ingestion rebuild without gold rebootstrap will fail preflight — same as M-RE1 baseline runbook.

### Post-hardening baseline re-run

**Preflight** (same as cluster baseline runbook §§2–3):

1. `apply_ops_ddl("uc13_ale")` additive migration if DDL changed since last pull.
2. G2 `company_name` pushdown probe — log stdout; HALT if `VS filter pushdown unavailable`.
3. M-RE3 VS spike matrix attested PASS (see § M-RE3 VS filter pushdown spike) — T2 capability landed gated off (`vs_metadata_filters=False` default).

**Cluster invocation** — omit `--affected-intents`:

```bash
python -m eval.retrieval.harness_cli run \
  --store-backend delta \
  --run-type baseline \
  --company-name "Elder Care" \
  --catalog uc13_ale
```

**Notebook cell** (after Cell 1):

```python
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from eval.retrieval.harness import EvalHarness
from eval.retrieval.store import DeltaEvalStore

CATALOG = "uc13_ale"
harness = EvalHarness()
store = DeltaEvalStore(spark, catalog=CATALOG)

report = harness.run(
    run_type="baseline",
    company_name="Elder Care",
    catalog=CATALOG,
    store=store,
    store_backend="delta",
    spark=spark,
)
print("post_hardening_baseline_run_id:", report.manifest.run_id)
print("harness_status:", report.manifest.harness_status)
print("gate_pass:", report.manifest.gate_pass)
```

### Promotion check — `retrieval_harness_latest_baseline`

After `harness_status: complete`, confirm the view points at your new run (not an older incomplete row):

```sql
SELECT run_id, harness_status, gate_pass, registry_hash, gold_snapshot, ingestion_snapshot, completed_at
FROM uc13_ale.ops.retrieval_harness_latest_baseline
WHERE company_name = 'Elder Care' AND catalog = 'uc13_ale';
```

**Operator action:** Record the promoted `run_id` in PR notes and update ablation runbook `BASELINE_REF` / `--baseline-ref-run-id` pins. Re-run `validate-baseline` against the new id before ablation arms:

```bash
python -m eval.retrieval.harness_cli validate-baseline \
  --store-backend delta \
  --catalog uc13_ale \
  --baseline-ref-run-id <post_hardening_baseline_run_id> \
  --company-name "Elder Care"
```

If G2 probe failed on this run, mark `harness_status: invalid` and do **not** promote.

### Item 23 (FTA) — Elder Care 18-field checklist re-score

Reuse M-RE2 item 23 steps (below in § M-RE2 cluster validation runbook). **Target:** ≥ **16/18** (maintain M-RE2 Control baseline).

1. Run Cell 12 (Financial Trends Agent) on Elder Care with `catalog=uc13_ale`.
2. Score the 18-field FTA golden checklist; target ≥ **16/18**.
3. Run Cell 12a to snapshot the eval arm before changing `retrieval_mode`.
4. Link checklist score to the **pipeline** manifest (`run_id` from `close_agent_run` inside `fta.main()` — **not** the harness baseline `run_id`):

```bash
python -m eval.retrieval.scripts.record_e2e_linkage \
  --run-id <fta_pipeline_agent_run_id> \
  --e2e-agent-id fta \
  --e2e-checklist-score <n> \
  --e2e-checklist-total 18 \
  --e2e-snapshot-table uc13_ale.analysis.financial_trends_eval_snapshot \
  --store-backend delta \
  --catalog uc13_ale
```

Verify linkage:

```sql
SELECT run_id, run_type, e2e_agent_id, e2e_checklist_score, e2e_checklist_total, e2e_snapshot_table
FROM uc13_ale.ops.retrieval_harness_runs
WHERE run_id = '<fta_pipeline_agent_run_id>';
```

### Legal 11-item checklist re-score

Canonical checklist: `eval/LCA/golden_checklist_elder_care.md` (single copy on disk; structural contract in `tests/test_golden_checklist_elder_care.py`). **Baseline:** 7 `pass` / 4 `gap-correct` / 0 `partial` (M3 normative YAML). **Target:** maintain or improve assessed pass count; no regression on `pass` rows.

1. Run Cell 16 (`legal_contracts_agent.main()`) on Elder Care with `catalog=uc13_ale` after Cell 1.
2. Load normative report: `/Volumes/uc13_ale/analysis/reports/Elder_Care/legal_report.yaml`.
3. Score each of the 11 `item_id` rows in `golden_checklist_elder_care.md` (`pass` | `partial` | `gap-correct` | `n/a`) using the same verdict rules documented in that file.
4. Record score summary (`<n>/11 pass`) and git SHA in PR notes. No `record_e2e_linkage` CLI for Legal in v1 — manual attestation only.

Optional structural sanity check (laptop):

```bash
pytest tests/test_golden_checklist_elder_care.py -q
```

### M-RE3 operator checklist (item 29)

| Step | Command / action | Pass criterion |
|------|------------------|----------------|
| 1 | Post-hardening `harness_cli run --run-type baseline` (no `--affected-intents`) | `harness_status: complete`; new `run_id` in Delta |
| 2 | `retrieval_harness_latest_baseline` query | View `run_id` matches step 1 |
| 3 | `validate-baseline` on promoted `run_id` | Exit 0 |
| 4 | M-RE3 ablation matrix (4 arms) vs promoted baseline | Four `run_id`s + `HarnessDelta` rows (§ ablation runbook) |
| 5 | FTA Cell 12 + 18-field re-score + `record_e2e_linkage` | ≥ 16/18; `e2e_*` fields set on pipeline manifest |
| 6 | Legal Cell 16 + 11-item re-score | No regression on golden `pass` rows |
| 7 | Update `BASELINE_REF` pins in this README after promotion | **Done 2026-07-16** — active pin `baseline_1aeb0ace584a` |

## M-RE2 cluster validation runbook (FTA pipeline)

Operator steps for M-RE2 exit gates **item 18** (fallback rate) and **item 23** (Elder Care FTA 18-field checklist re-score). Requires `test_pipeline.ipynb` Cell 1 (`set_pipeline_thread`, `REPO_ROOT` on `sys.path`) before any agent `main()` — run Cell 12 **after** Cell 1 and snapshot with Cell 12a before switching `retrieval_mode`.

**Control baseline reference:** 16/18 on the RT7 golden checklist (pre-T4 Control arm); M-RE1 harness baseline `baseline_f0f4f68ac7af`. **Item-23 target:** ≥ **16/18** on Elder Care after M-RE2 OPEX context + provenance fixes.

### Item 18 — keyword fallback rate

**Store backend (read this first):** On a Databricks cluster with an active Spark session, `open_agent_run()` writes pipeline manifests and provenance to **`{catalog}.ops.*` Delta tables** (default catalog from Cell 1 → `uc13_ale`). SQLite at `eval/retrieval/.local/re2_store.sqlite` is the **laptop / no-Spark** fallback only.

**Cluster preflight — run every time the DDL file changes, not just once:** `apply_ops_ddl` is safe to re-run. It applies `CREATE TABLE IF NOT EXISTS` (no-op if the table already exists) **and then** additively reconciles any columns your live table is missing vs. the current schema (e.g. `pipeline_thread_id` added in M-RE2 T1) via `ALTER TABLE ADD COLUMNS` — it never drops or rewrites existing rows.

```python
from eval.retrieval.scripts.apply_ops_ddl import apply_ops_ddl
n = apply_ops_ddl("uc13_ale")
print(f"Applied {n} DDL statements")
# Watch stdout for: "[apply_ops_ddl] additive migration on retrieval_harness_runs: added [...]"
```

If `open_agent_run()` / `fta.main()` fails with `DELTA_METADATA_MISMATCH`, it means your `uc13_ale.ops.retrieval_harness_runs` (or `retrieval_provenance`) table predates a schema change and is missing a column that current code writes. Re-running `apply_ops_ddl` after pulling latest closes this — `CREATE TABLE IF NOT EXISTS` alone does **not**, since it is a no-op on an existing table.

No migration is needed for SQLite — `SqliteEvalStore` creates tables on first write and additively `ALTER TABLE`s new columns on open.

After FTA `main()` completes (`open_agent_run` / `close_agent_run` inside `fta.main()`), read `fallback_rate` from Delta:

```sql
SELECT run_id, harness_status, run_type, fallback_rate, empty_rate, completed_at
FROM uc13_ale.ops.retrieval_harness_runs
WHERE run_type = 'pipeline'
ORDER BY completed_at DESC
LIMIT 5;
```

**Do not** build the sqlite path from `REPO_ROOT` in Cell 1 — that variable points at `databricks/`, not the git repo root. If you must inspect sqlite (local only), use:

```python
from eval.retrieval.provenance import default_sqlite_path
print(default_sqlite_path())
```

### Provenance verify

Confirm provenance rows landed for the FTA `agent_run_id`:

```sql
SELECT COUNT(*) AS provenance_rows
FROM uc13_ale.ops.retrieval_provenance
WHERE run_id = '<fta_agent_run_id>';
```

Expect `provenance_rows > 0` after a full FTA pipeline run with M-RE2 wiring.

**If `harness_status: complete` but `provenance_rows = 0` and `fallback_rate`/`empty_rate` are both `NULL`:** you are hitting a fixed bug, not a config gap — confirm you have pulled the commit containing the `contextvars.copy_context()` fix in `FinancialTrendsAgent.run()`. `ThreadPoolExecutor.submit()` does not inherit the main thread's `agent_run_id` ContextVar by default, so the three FTA sub-agents (Revenue/EBITDA/OPEX) silently skipped provenance emission before this fix. See `.dev/decision-logs/T4-m-re2-threadpool-context-propagation.md`.

**If Cell 12 fails with `ConcurrentAppendException [DELTA_CONCURRENT_APPEND.ROW_LEVEL_CHANGES]` on `retrieval_provenance`:** confirm you've pulled the commit that adds `DeltaEvalStore._provenance_write_lock` (serializes `append_provenance`'s `MERGE` and `patch_context_allocations`'s now-batched `MERGE` across FTA's three sub-agent threads) on top of `retry_on_delta_conflict()`. Together these should eliminate self-inflicted conflicts from FTA's own threads entirely — retries remain only as a safety net against a *different* concurrent writer (e.g. another pipeline/harness run against the same table at the same time). If you still see this error after pulling both fixes, it means two separate runs are writing concurrently — check whether another Cell 12/harness run is active on this workspace at the same time. See "Second follow-on fix" in `.dev/decision-logs/T4-m-re2-threadpool-context-propagation.md`.

### Item 23 — Elder Care E2E checklist re-score

1. Run Cell 12 (Financial Trends Agent) on Elder Care with `catalog=uc13_ale`.
2. Score the 18-field FTA golden checklist (RT7 scorecard); target ≥ **16/18** (Control baseline **16/18**).
3. Run Cell 12a to snapshot the eval arm before changing `retrieval_mode`.
4. Link the checklist score to the pipeline manifest:

```bash
python -m eval.retrieval.scripts.record_e2e_linkage \
  --run-id <fta_agent_run_id> \
  --e2e-agent-id fta \
  --e2e-checklist-score <n> \
  --e2e-checklist-total 18 \
  --e2e-snapshot-table uc13_ale.analysis.financial_trends_eval_snapshot \
  --store-backend delta \
  --catalog uc13_ale
```

Verify linkage:

```sql
SELECT run_id, e2e_agent_id, e2e_checklist_score, e2e_checklist_total, e2e_snapshot_table
FROM uc13_ale.ops.retrieval_harness_runs
WHERE run_id = '<fta_agent_run_id>';
```

Item 23 is **runtime-armed only** — not CI-gated.

## PHV validation

Operator runbook for **M-PHV2** (Validation expansion): per-agent Elder Care re-score matrix (spec §5.12.2 / charter item 10), regression floors (item 12), and second-company validation prerequisites. Requires `test_pipeline.ipynb` Cell 1 (`set_pipeline_thread`, `REPO_ROOT` on `sys.path`) before any agent `main()` — same precondition as § M-RE3 post-hardening re-baseline + E2E runbook.

**Coverage disclosure:** Cluster execution of agent re-scores and second-company runs is **operator-owned** — this section defines the rubric and pass criteria only. Scorecards and attestations live under `.dev/scorecards/` and `.dev/attestations/` (Option C content-SHA pin protocol).

### Per-agent validation matrix (spec §5.12.2)

| Agent | Elder Care gate | Scoring source | Notebook cell (agent-qualified) | Second company |
|-------|-----------------|----------------|-------------------------------|----------------|
| FTA | ≥ **16/18** (maintain M-RE3) | 18-field golden checklist (`.dev/scorecards/prereqs.md` rubric); M-RE3 baseline: `.dev/scorecards/scorecard_7_03_post_m3_vs_7_02.md` | Cell 12 (Financial Trends Agent) | Run + scorecard; no numeric floor in v0.1.0 — document baseline |
| Legal | ≥ **7/11** pass (maintain G3) | Golden checklist — see [Canonical Legal checklist](#canonical-legal-golden-checklist) below; M-RE3 baseline: `.dev/scorecards/scorecard_lca_7_03_post_m3_vs_g3_elder_care.md` | Cell 16 (Legal Contracts Agent) | Same |
| BMA | Golden checklist + promotion gate | `eval/BMA/golden_checklist_elder_care.md`; `evaluate_promotion` — see [Promotion gate invocation (BMA, CQA, KPI, QoE, Profiler)](#promotion-gate-invocation-bma-cqa-kpi-qoe-profiler) | Cell 11 (Business Model Agent) | Parser + agent run |
| CQA | Golden checklist + promotion gate | `eval/CQA/golden_checklist_elder_care.md`; `evaluate_promotion` (same subsection) | Cell 14 (Customer Quality Agent) | Parser + agent run minimum |
| KPI | Golden checklist + promotion gate | `eval/KPI/golden_checklist_elder_care.md`; `evaluate_promotion` (same subsection) | Cell 15 (KPI Agent) | Parser + agent run minimum |
| QoE | Golden checklist + promotion gate | `eval/QOE/golden_checklist_elder_care.md`; `evaluate_promotion` (same subsection; precondition-adjusted `candidate_total` — see QoE subsection) | Cell 17 (Quality of Earnings Agent) | Parser + agent run minimum |
| Profiler | Golden checklist + promotion gate | `eval/PROFILER/golden_checklist_elder_care.md`; `evaluate_promotion` (same subsection) | Cells 9–10 (Company Profiler) | Parser + agent run minimum |

### Canonical Legal golden checklist

**Authoritative path (Flag 1 resolution):** `eval/LCA/golden_checklist_elder_care.md`

This is the **only git-tracked** copy (`git ls-files '*golden_checklist_elder_care.md'` → one row). Use it for all M-PHV2 Legal scoring.

| Path | Status | Role |
|------|--------|------|
| `eval/LCA/golden_checklist_elder_care.md` | **Tracked — canonical** | Operator scoring source; cited by § M-RE3 post-hardening re-baseline + E2E runbook |
| `.dev/legal_agent/eval/golden_checklist_elder_care.md` | Gitignored evidence fixture | `tests/test_golden_checklist_elder_care.py` skipif target when present on operator machine — **not** a second scoring source |
| `databricks/agents/workstreams/LCA/eval/golden_checklist_elder_care.md` | Present on disk, not tracked | Development convenience copy — **not** authoritative; do not score against it |

Structural contract when the gitignored fixture exists: `pytest tests/test_golden_checklist_elder_care.py -q`. Verdict rules (`pass` | `partial` | `gap-correct` | `n/a`) are defined in the canonical file header.

### Smoke E2E definition (BMA, CQA, KPI, QoE, Profiler) — historical bar

Spec §5.12.2's original "Harness partition + smoke E2E" cell was **falsifiable** at M-PHV2 v0.1.0 as follows (Flag 5 resolution). This bar applied **before** each agent's golden checklist and promotion gate landed (M1/M2/M3). INDEX.md rows that still read `smoke E2E 3/3` attest to that historical phase only.

All three conditions had to hold for **pass** under the smoke bar:

1. **Agent `main()` completes without raising** — run the agent-qualified notebook cell on Elder Care with `catalog=uc13_ale` after Cell 1 and index-sync preflight (Cells 7, 8c–8d as needed).
2. **Harness partition report is generated** — a harness run covering that agent's intent partition exists with `harness_status: complete`. Agent partition ids per `eval/retrieval/registry_extractor.py::AGENT_ID_BY_STEM` (`bma`, `cqa`, `kpi`, `qoe`, `profiler`). Record the harness `run_id` on the scorecard.
3. **Output table row count > 0** — the agent's analysis output table for the run company has at least one row (e.g. `SELECT COUNT(*) FROM <catalog>.analysis.<agent_output_table> WHERE company_name = 'Elder Care'` > 0). Proves the pipeline wrote structured output, not merely that retrieval returned chunks.

**Current Elder Care procedure (post–golden-checklist):** score against `eval/<AGENT>/golden_checklist_elder_care.md`, then invoke `evaluate_promotion` per [Promotion gate invocation (BMA, CQA, KPI, QoE, Profiler)](#promotion-gate-invocation-bma-cqa-kpi-qoe-profiler). The smoke bar remains documented here as provenance for older scorecard rows; it is **not** the active gate once a golden checklist exists for that agent.

### Item 12 — FTA/Legal regression confirmation (Flag 6)

Before charter item 12 is closed, the operator must decide whether M-RE3 7/03 scores remain valid after M-PHV1 index-sync hardening or whether fresh cluster re-runs are required.

| Field | Value |
|-------|-------|
| **Fresh cluster re-run required** | **`yes`** — post-M-PHV1 full notebook E2E performed 2026-07-08 (Elder Care, thread `773c2c96-558e-480b-a142-b63b2a1effbe`) |
| **Rationale** | M-PHV1 `IndexSyncError` fail-closed changed Cell 7/8d behavior; operator executed post-hardening E2E. Checklist scores **16/18** FTA and **7/11** Legal unchanged vs M-RE3 (not re-checklisted on July 8 output). `record_e2e_linkage` on M-RE3 `run_id`s retained for regression trail; July 8 pipeline `run_id`s: FTA `6c4db191…`, Legal `9dc9070c…`. |
| **FTA score used for item 12** | **16/18** |
| **Legal score used for item 12** | **7/11 pass** |

**Executor stance:** This field is genuinely open at plan time — M-PHV1 changed index-sync fail-closed behavior (Design Principle 1) while M-RE3 7/03 scores predate that landing. This runbook does **not** pre-decide; the operator owns the yes/no call.

**Regression floors (unchanged):** FTA ≥ **16/18**; Legal ≥ **7/11** pass rows on `eval/LCA/golden_checklist_elder_care.md`. Reference baselines: `.dev/scorecards/scorecard_7_03_post_m3_vs_7_02.md` (FTA), `.dev/scorecards/scorecard_lca_7_03_post_m3_vs_g3_elder_care.md` (Legal).

### Second company selection & run

Charter items **13–14** / spec §5.12.2 second-company column. Resolves context-map **Flag 4** — this runbook documents **selection criteria and procedure only**; the operator owns the company choice (placeholder fields below, not a pre-selected name).

#### Selection criteria (frozen — do not paraphrase)

- **Spec §5.12.2:** Operator chooses from available SharePoint companies with non-trivial data room; document in scorecard header.
- **Charter reference corpus v2:** must differ from Elder Care.

| Field | Value |
|-------|-------|
| **Selected company** | **_(operator: SharePoint folder name — must differ from `Elder Care`)_** |
| **Selection rationale** | **_(operator: why this company meets "non-trivial data room")_** |

Discover candidates via `test_pipeline.ipynb` Cell 2 (SharePoint company dropdown) or `connector.list_companies()` — do **not** treat this runbook as naming a specific second company.

#### M-PHV1 Clearsulting attestation — pattern, not exit gate

The M-PHV1 operator attestation (`.dev/attestations/m-phv1-clearsulting-2026-07-07.md`) demonstrates a **viable pattern** for second-corpus validation:

- Parser + agent outputs on a non–Elder Care SharePoint company
- `company_name` isolation on the shared `uc13_ale` eval catalog (tenant isolation via row filters, not a separate UC catalog)
- Index sync success path (`✓ Index ready`) before Phase 3 agents

It is **not** a substitute for M-PHV2's exit gate — different milestone, **incomplete agent matrix** (M-PHV1 attested parser + FTA/Legal smoke only; M-PHV2 requires all seven Phase 3 agents on Elder Care plus second-company FTA minimum per Decision 3). Re-running Clearsulting or choosing a different company under M-PHV2's fuller matrix is an **open operator decision** — not resolved here.

#### Run procedure (items 13–14)

**Minimum (Decision 3):** parser + FTA — Cells 1 → 7 (index sync) → ingestion/parser path for the selected company → Cell 12 (Financial Trends Agent) on the selected `company_name` with `catalog=uc13_ale`.

**Optional full pipeline:** extend through remaining Phase 3 agents per the [Per-agent validation matrix](#per-agent-validation-matrix-spec-5122) second-company column (parser + agent run minimum for BMA/CQA/KPI/QoE/Profiler).

**Scorecard header (required):** Before closing item 14, copy `.dev/scorecards/templates/second_company_header_template.md` to the top of the filled scorecard(s). Record **company name** and **catalog** used — these fields are mandatory on every second-company scorecard and must match the `Company` / `Catalog` columns when adding a row to `.dev/scorecards/INDEX.md`.

| Field | Value |
|-------|-------|
| **Run scope** | `parser + FTA minimum` / `full pipeline` — **_(operator: circle one)_** |
| **FTA scorecard file** | **_(operator: path under `.dev/scorecards/` — no numeric floor in v0.1.0; document baseline)_** |
| **Harness / pipeline run ids** | **_(operator: cite `run_id` from `uc13_ale.ops.retrieval_harness_runs` or agent manifests)_** |

No full gold-label bootstrap on the second company (Decision 3) — FTA scorecard + harness/pipeline evidence is sufficient unless FTA fails badly (then escalate per spec §5.18).

### record_e2e_linkage invocations

Charter item **17**. Links golden-checklist scores to pipeline `HarnessRun` manifests for all seven agents. **Scope:** FTA and Legal call `record_e2e_linkage` directly (bash examples below). BMA, CQA, KPI, QoE, and Profiler call it **indirectly** via `evaluate_promotion` (Python library — see [Promotion gate invocation (BMA, CQA, KPI, QoE, Profiler)](#promotion-gate-invocation-bma-cqa-kpi-qoe-profiler) and [Scoping note](#scoping-bma-cqa-kpi-qoe-profiler) below).

Frozen CLI surface for **direct** `record_e2e_linkage` invocation (FTA/Legal; verified against `record_e2e_linkage.py::build_parser`):

```text
python -m eval.retrieval.scripts.record_e2e_linkage --run-id <...> --e2e-agent-id <...> --e2e-checklist-score <int> --e2e-checklist-total <int, required> --e2e-snapshot-table <FQN> --store-backend <sqlite|delta> --catalog <...> [--sqlite-path <path>]
```

Use the **pipeline** `run_id` from `close_agent_run` inside the agent's `main()` — **not** a harness baseline `run_id`.

#### FTA (18-field checklist)

After Cell 12 (Financial Trends Agent) Elder Care re-score (target ≥ **16/18**):

```bash
python -m eval.retrieval.scripts.record_e2e_linkage \
  --run-id <fta_pipeline_agent_run_id> \
  --e2e-agent-id fta \
  --e2e-checklist-score <from Cell 12 re-score> \
  --e2e-checklist-total 18 \
  --e2e-snapshot-table uc13_ale.analysis.financial_trends_eval_snapshot \
  --store-backend delta \
  --catalog uc13_ale
```

#### Legal (11-item checklist)

After Cell 16 (Legal Contracts Agent) Elder Care re-score against `eval/LCA/golden_checklist_elder_care.md` (target ≥ **7/11** pass rows):

```bash
python -m eval.retrieval.scripts.record_e2e_linkage \
  --run-id <legal_pipeline_agent_run_id> \
  --e2e-agent-id legal \
  --e2e-checklist-score <from Cell 16 re-score> \
  --e2e-checklist-total 11 \
  --e2e-snapshot-table uc13_ale.analysis.legal \
  --store-backend delta \
  --catalog uc13_ale
```

Verify linkage (either agent):

```sql
SELECT run_id, e2e_agent_id, e2e_checklist_score, e2e_checklist_total, e2e_snapshot_table
FROM uc13_ale.ops.retrieval_harness_runs
WHERE run_id = '<pipeline_agent_run_id>';
```

#### Promotion gate invocation (BMA, CQA, KPI, QoE, Profiler)

For BMA, CQA, KPI, QoE, and Profiler, link golden-checklist scores via **`evaluate_promotion`** — a **Python library call** with **no CLI wrapper** (M3 Decision M3-B; this milestone does not add one). On promoting outcomes (`baseline_bootstrap`, `promoted`, `promotion_waived`), the gate calls `record_e2e_linkage` internally; FTA/Legal continue to call `record_e2e_linkage` directly (bash examples above).

**Frozen signature** (`eval/retrieval/promotion_gate.py`):

```python
def evaluate_promotion(
    store: EvalStore,
    run_id: str,
    *,
    e2e_agent_id: str,
    company_name: str,
    catalog: str,
    candidate_score: int,
    candidate_total: int,
    e2e_snapshot_table: str,
    waiver_id: str | None = None,
) -> PromotionResult:
```

**Error envelope (M3, unchanged):** `InvalidWaiverIdError` (malformed `waiver_id`), `RunNotFoundError`, and `StoreError` propagate unchanged. First-bootstrap runs for these five agents do **not** supply `waiver_id`; expected first-run outcome is `status="baseline_bootstrap"` (unconditional accept per spec §5).

**Score provenance (Decision M4-C, operator-owned):** **Default path** — reuse the existing golden-checklist Summary pass-count in `eval/<AGENT>/golden_checklist_elder_care.md` together with the existing pipeline `run_id` already cited on that agent's INDEX.md row, when both are dated within the program's active execution window and the operator judges them current. **Escape hatch** — if the operator judges existing checklist or pipeline-run evidence stale, re-run the relevant notebook cell and re-score before invoking the gate; **do not silently reuse stale evidence**. Record the choice on the scorecard (naming convention: `.dev/scorecards/uc13-eval-harness-all-agents_<agent>_elder-care_<run-date>.md`).

**Notebook setup** (after Cell 1; cluster with Delta store):

```python
from eval.retrieval.promotion_gate import evaluate_promotion
from eval.retrieval.store import DeltaEvalStore

store = DeltaEvalStore(spark, catalog="uc13_ale")
# Pipeline run_id from close_agent_run inside the agent's main() — not a harness baseline run_id.
```

Frozen manifest agent ids (same vocabulary as `--e2e-agent-id` on the direct CLI): `--e2e-agent-id bma`, `--e2e-agent-id cqa`, `--e2e-agent-id kpi`, `--e2e-agent-id qoe`, `--e2e-agent-id profiler`.

##### BMA (`--e2e-agent-id bma`, `candidate_total=7`)

After Cell 11 (Business Model Agent) Elder Care re-score against `eval/BMA/golden_checklist_elder_care.md`:

```python
result = evaluate_promotion(
    store,
    "<bma_pipeline_agent_run_id>",
    e2e_agent_id="bma",
    company_name="Elder Care",
    catalog="uc13_ale",
    candidate_score=<from golden checklist Summary>,  # default reuse: 4
    candidate_total=7,
    e2e_snapshot_table="uc13_ale.analysis.business_model",
)
print(result.status)  # first run: baseline_bootstrap
```

##### CQA (`--e2e-agent-id cqa`, `candidate_total=6`)

After Cell 14 (Customer Quality Agent) Elder Care re-score against `eval/CQA/golden_checklist_elder_care.md`:

```python
result = evaluate_promotion(
    store,
    "<cqa_pipeline_agent_run_id>",
    e2e_agent_id="cqa",
    company_name="Elder Care",
    catalog="uc13_ale",
    candidate_score=<from golden checklist Summary>,  # default reuse: 3
    candidate_total=6,
    e2e_snapshot_table="uc13_ale.analysis.customer_quality",
)
print(result.status)  # first run: baseline_bootstrap
```

##### KPI (`--e2e-agent-id kpi`, `candidate_total=3`)

After Cell 15 (KPI Agent) Elder Care re-score against `eval/KPI/golden_checklist_elder_care.md`:

```python
result = evaluate_promotion(
    store,
    "<kpi_pipeline_agent_run_id>",
    e2e_agent_id="kpi",
    company_name="Elder Care",
    catalog="uc13_ale",
    candidate_score=<from golden checklist Summary>,  # default reuse: 3
    candidate_total=3,
    e2e_snapshot_table="uc13_ale.analysis.kpi",
)
print(result.status)  # first run: baseline_bootstrap
```

##### QoE (`--e2e-agent-id qoe`, `candidate_total=6` or `5`)

QoE golden-checklist scoring depends on FTA `addback_schedule_json` being present for the in-run company. This is **distinct** from the harness retrieval preconditions in [§1. Upstream preconditions (§5.15)](#1-upstream-preconditions-515) — it gates only the `tier_classification_fidelity` checklist row, not retrieval readiness.

**Presence bar (H2).** At QoE agent run time, `QualityOfEarningsAgent._load_addback_passthrough` queries `{catalog}.analysis.financial_trends` for the company (latest `created_at`) and parses `addback_schedule_json`. The bar **passes** only when the parsed value is a **non-empty** `list[dict]`. It **fails** when any of the following yield an empty passthrough: no row, SQL `NULL`, JSON empty array (`"[]"`), query/parse failure, or malformed JSON. On most failure modes the agent records a `data_room_gaps` note that FTA has not run or found no addbacks; empty-array JSON returns `[]` without that gap note (see `tests/test_qoe_precondition_gate.py`).

**Manual scoring equivalence (operator re-score, no separate code path).** When an operator re-scores QoE outside the agent run, re-derive the same presence check from FTA's current `financial_trends.addback_schedule_json` for the same `company_name` (latest `created_at`) — this is documented equivalence to the in-run passthrough, not a second code path.

**Checklist N vs precondition-adjusted M (Decision M2-C).** `eval/QOE/golden_checklist_elder_care.md` header and `GOLDEN_CHECKLIST_COVERAGE` in `quality_of_earnings_agent.py` are always the **full fixed count** **N = 6** (structural test passing: `pytest tests/test_golden_checklist_elder_care.py -v`, `qoe` case). The operator supplies a separate scoring-time denominator **M** as `candidate_total`:

| Precondition bar | Adjusted total M | Arithmetic |
|---|---|---|
| Pass (non-empty addback schedule) | 6 | `M = N` |
| Fail | 5 | `M = N - 1` (exclude the one precondition-gated tier-classification item: `tier_classification_fidelity`) |

This adjustment is **operator-computed and procedural** — no automated enforcement at MVP.

After Cell 17 (Quality of Earnings Agent) Elder Care re-score against `eval/QOE/golden_checklist_elder_care.md`, supply **M** from the table above:

```python
result = evaluate_promotion(
    store,
    "<qoe_pipeline_agent_run_id>",
    e2e_agent_id="qoe",
    company_name="Elder Care",
    catalog="uc13_ale",
    candidate_score=<from golden checklist Summary>,  # default reuse: 5
    candidate_total=<M from table above: 6 or 5>,
    e2e_snapshot_table="uc13_ale.analysis.quality_of_earnings",
)
print(result.status)  # first run: baseline_bootstrap
```

**Executable proof of both branches:** `tests/test_qoe_precondition_gate.py` — stub-spark coverage of `_load_addback_passthrough` pass/fail paths and test-local `_adjust_checklist_total` denominator arithmetic (`6` vs `5`).

##### Profiler (`--e2e-agent-id profiler`, `candidate_total=7`)

After Cells 9–10 (Company Profiler) Elder Care re-score against `eval/PROFILER/golden_checklist_elder_care.md`:

```python
result = evaluate_promotion(
    store,
    "<profiler_pipeline_agent_run_id>",
    e2e_agent_id="profiler",
    company_name="Elder Care",
    catalog="uc13_ale",
    candidate_score=<from golden checklist Summary>,  # default reuse: 7
    candidate_total=7,
    e2e_snapshot_table="uc13_ale.classification.company_profile",
)
print(result.status)  # first run: baseline_bootstrap
```

Verify linkage (any agent):

```sql
SELECT run_id, e2e_agent_id, e2e_checklist_score, e2e_checklist_total, e2e_snapshot_table
FROM uc13_ale.ops.retrieval_harness_runs
WHERE run_id = '<pipeline_agent_run_id>';
```

#### Scoping: BMA, CQA, KPI, QoE, Profiler

`record_e2e_linkage` **is** applicable to all seven agents. FTA and Legal invoke it **directly** (bash CLI above). BMA, CQA, KPI, QoE, and Profiler invoke it **indirectly** via `evaluate_promotion` (Python library — [Promotion gate invocation](#promotion-gate-invocation-bma-cqa-kpi-qoe-profiler) above). Do not call `record_e2e_linkage` standalone for those five unless you are debugging the M0 CLI in isolation; production linkage goes through the promotion gate.

Ordinary harness-run recording remains available for retrieval-only partition reports:

```bash
python -m eval.retrieval.harness_cli run --store-backend <sqlite|delta> --run-type <...> --company-name <...> --catalog <...> --baseline-ref-run-id baseline_1aeb0ace584a [--ablation-config <...>]
```

Record each harness `run_id` on the agent's scorecard when documenting historical smoke-E2E evidence; golden-checklist scores use `evaluate_promotion` per the promotion-gate subsection.

## R-02 manual A/B

M-PHV2 hub (charter §4, item 16). Records the manual `vs_metadata_filters` kwarg-flip experiment on Elder Care — decision input for M-PHV4 item 29 via this same hub (`eval/retrieval/README.md § R-02 manual A/B`, M-PHV2 → M-PHV4 order). M-PHV4 extends this section with the activation decision **only if** the numeric bar and second-reviewer sign-off below both pass.

**Coverage disclosure:** Cluster execution of the two runs is **operator-owned** — this section defines procedure, the Decision 14 numeric bar, and the sign-off schema only.

### Why not `--ablation-config` (Decision 9)

`--ablation-config` / `ablation_arm` **cannot** represent `vs_metadata_filters`. `harness.py::ablation_arm_to_merge_rank_mode` raises `PreconditionError` for `vs_filter_pushdown` — the harness dispatcher is 1-D over `merge_rank_mode`; `vs_metadata_filters` is an orthogonal boolean with **no** `harness_cli.py` flag. **Do not invent a CLI flag** — there is no harness CLI switch for this kwarg; set it only in code/notebook via `retrieval_dispatch`.

The frozen CLI surface for harness runs (unchanged this milestone):

```bash
python -m eval.retrieval.harness_cli run --store-backend <sqlite|delta> --run-type <...> --company-name <...> --catalog <...> --baseline-ref-run-id baseline_1aeb0ace584a [--ablation-config <...>]
```

For this A/B, invoke **without** `--ablation-config`. Set `vs_metadata_filters=False` (run A) and `vs_metadata_filters=True` (run B) directly in a harness-invoking script or notebook cell by passing a custom `retrieval_dispatch` to `EvalHarness` that threads the kwarg into `semantic_search(...)`.

### Two-run procedure

**Baseline reference:** `baseline_299063e87806` — pin used for the completed 2026-07-15 item-16 A/B (historical; active control is now `baseline_1aeb0ace584a`, see § Cluster baseline runbook).

**Preflight:** Same as § M-RE3 post-hardening re-baseline + E2E runbook (DDL, G2 `company_name` pushdown probe, registry/gold/ingestion_snapshot pins). Omit `--affected-intents` so gate-eligible scope matches the full registered intent suite.

| Run | `vs_metadata_filters` | Role |
|-----|----------------------|------|
| **A (flag off)** | `False` | Control — matches production default |
| **B (flag on)** | `True` | Candidate activation path for M-PHV4 item 29 |

**Notebook pattern** (after Cell 1; repeat with `VS_METADATA_FILTERS = False` then `True`):

```python
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from agents.shared.retrieval import semantic_search
from eval.retrieval.harness import (
    EvalHarness,
    ablation_arm_to_merge_rank_mode,
    build_search_kwargs,
    uses_fallback_wrapper,
)
from eval.retrieval.store import DeltaEvalStore

CATALOG = "uc13_ale"
BASELINE_REF = "baseline_299063e87806"
VS_METADATA_FILTERS = False  # Run A: False; Run B: True


def dispatch_with_vs_metadata_filters(intent, *, company_name, spark, ablation_arm=None):
    kwargs = build_search_kwargs(intent, company_name=company_name, spark=spark)
    merge_rank_mode = ablation_arm_to_merge_rank_mode(ablation_arm)
    if merge_rank_mode is not None:
        kwargs["merge_rank_mode"] = merge_rank_mode
    kwargs["vs_metadata_filters"] = VS_METADATA_FILTERS
    result = semantic_search(**kwargs)
    if uses_fallback_wrapper(intent):
        min_results = intent.min_results if intent.min_results is not None else 3
        if len(result.chunks) < min_results and intent.file_name_filter:
            result = semantic_search(**{**kwargs, "file_name_filter": None})
    return result


harness = EvalHarness(retrieval_dispatch=dispatch_with_vs_metadata_filters)
store = DeltaEvalStore(spark, catalog=CATALOG)

report = harness.run(
    run_type="enhancement",
    company_name="Elder Care",
    catalog=CATALOG,
    store=store,
    store_backend="delta",
    baseline_ref_run_id=BASELINE_REF,
    spark=spark,
)
print("r02_ab_run_id:", report.manifest.run_id)
print("vs_metadata_filters:", VS_METADATA_FILTERS)
print("harness_status:", report.manifest.harness_status)
```

Record both `run_id` values and per-intent `recall_at_10` from each report for the bar check below. `harness_cli run` alone cannot flip `vs_metadata_filters` — use the notebook/script pattern above or an equivalent custom `retrieval_dispatch`.

### Numeric bar (Decision 14 / Program Gate PG5)

Activation (M-PHV4 item 29) requires **all three** PG5 parts — numeric bar **and** second-reviewer sign-off (§5.19 rejects bar-alone or sign-off-alone). The numeric bar has **two** conjunctive conditions, measured vs run A (flag off):

1. **Per-intent:** No gate-eligible intent's recall@10 drops **more than 5 percentage points** vs run A.
2. **Aggregate:** Aggregate recall@10 across gate-eligible intents does **not decrease** vs run A.

| Field | Run A (`run_id`) | Run B (`run_id`) | Aggregate recall@10 (gate-eligible) | Per-intent max drop (pp) | Numeric bar pass? |
|-------|------------------|------------------|---------------------------------------|--------------------------|-------------------|
| **Elder Care / `uc13_ale` (2026-07-15)** | `enhancement_b079befc8b38` | `enhancement_3c397f54d016` | A **4.23%** / B **4.16%** (43 gated intents) | **5.88** (`legal.litigation`) | **no** |

Operator record: `.dev/attestations/m-phv4-r02-vs-metadata-filters-ab-elder-care-2026-07-15.md`. Delta-validated against `uc13_ale.ops.retrieval_harness_results` (2026-07-15).

Gate-eligible intents: those in the harness run's `gated_intents` manifest field (same vocabulary as `eval/retrieval/scope_resolver.py::gate_eligible_intent_ids`).

### Second-reviewer sign-off (Decision 14)

Required **in addition to** the numeric bar. The reviewer must not be the operator who ran the A/B.

| Field | Value |
|-------|-------|
| **Reviewer name** | **Waived for M-PHV4 exit** — packet sent 2026-07-15 (`.dev/attestations/m-phv4-r02-second-reviewer-packet-2026-07-15.md`); formal return not required while numeric bar is `no` and item 29 stays declined |
| **Date** | 2026-07-15 (operator waiver) |
| **Diff reviewed** | Run A `enhancement_b079befc8b38` / Run B `enhancement_3c397f54d016`; per-intent table in attestation above |
| **Verdict** | **waived** — activation already blocked by numeric bar; independent review may complete later without unblocking item 29 |

### M-PHV4 item 29 activation decision (2026-07-15)

| Field | Value |
|-------|-------|
| **Item 16 operator A/B** | Complete — numeric bar table filled |
| **Item 29 default flip** (`vs_metadata_filters=True`) | **Not activated** — PG5 numeric bar `no` |
| **Production default** | `False` (unchanged at `retrieval.py`) |
| **Second-reviewer sign-off** | **Waived for M-PHV4 exit** — packet sent 2026-07-15; formal return not required while bar `no` |
| **§8 auditor** | Scheduled **after** orchestrator review → adversarial audit (pre-audit README commit `a3ff631`) |
| **`legal.litigation` debug** | Deferred — chunk_id diff A vs B when bandwidth allows; not program-blocking |

### If the bar fails (PG5 failure-non-blocking)

If the numeric bar fails **or** sign-off is `fail`, record the diff and verdict in the tables above anyway. **`vs_metadata_filters=True` activation does not proceed to M-PHV4** — production default stays `False` per §5.13. Failure does **not** block M-PHV4 exit; it only blocks item 29 default flip.

## Related CLIs

| Command | Purpose |
|---------|---------|
| `python eval/retrieval/scripts/apply_ops_ddl.py --catalog uc13_ale` | One-time `uc13_ale.ops` DDL (Elder Care workspace) |
| `python -m eval.retrieval.harness_cli run ...` | Harness execution |
| `python -m eval.retrieval.harness_cli validate-baseline ...` | Preflight baseline_ref checks |
| `python -m eval.retrieval.scripts.sync_eval_store --run-id <id> --direction sqlite_to_delta` | SQLite → Delta promotion |
| `python -m eval.retrieval.scripts.record_e2e_linkage --run-id <id> --e2e-agent-id fta --e2e-checklist-score <n> ...` | Link FTA E2E checklist to pipeline manifest |
