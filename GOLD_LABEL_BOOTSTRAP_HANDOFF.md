# Gold label bootstrap — agent handoff

**Task chip:** Close the 8-intent gold-label gap opened by `hector-ui-pipeline-merge` T5–T7.  
**Operator decision (2026-07-27):** Bootstrap the 8 labels on `uc13_ale` now (`pending2.md`).  
**Status:** OPEN — registry has **57** intents; committed `elder_care.yaml` has **49** labels.  
**Blocking:** `test_committed_elder_care_yaml_validates_and_covers_registry` is `xfail(strict=False)`.

---

## 1. Intent (what to do)

Re-bootstrap Elder Care gold labels so **every row in `eval/retrieval/intent_registry.yaml` has exactly one row in `eval/retrieval/gold_labels/elder_care.yaml`**, with citation-backfilled positives from the live `uc13_ale` corpus on Databricks.

Minimum deliverables:

1. Run `GoldLabelBootstrap` on cluster against current Elder Care ingestion.
2. Commit updated `eval/retrieval/gold_labels/elder_care.yaml` (57 rows, single `ingestion_snapshot`).
3. Remove the `xfail` on `test_committed_elder_care_yaml_validates_and_covers_registry`.
4. Record stdout evidence (bootstrap summary + pytest pass).
5. *(Recommended)* Re-run harness baseline and promote a new control baseline — registry hash will change.

**Non-goals for this chip:**

- Multi-company gold labels (Clearsulting/GKF/SPG) — explicitly deferred in M4 charter Decision 3.
- Fixing pre-existing `bootstrap_failed` rows unless bootstrap pass naturally resolves them.
- Re-running Cell 7 full ingestion rebuild unless chunk count / snapshot materially drifted.

---

## 2. Rationale (why this debt exists)

### 2.1 Direct cause — Hector merge agent depth (T5/T6/T7)

Hector's CQA and KPI 3-way merges ported **new retrieval tools** into production agents. Each tool maps 1:1 to a harness intent via `registry_extractor.py`.

| Agent merge | Retrieval tools before → after | New intents |
|-------------|-------------------------------|-------------|
| T6 CQA | 5 → 9 | +4 |
| T7 KPI | 5 → 9 | +4 |
| T5 QoE | unchanged | 0 |

Commit `8e1393c` regenerated `intent_registry.yaml` and updated `expected_intent_counts.yaml` (cqa: 9, kpi: 9, total 55–60). Gold labels were **not** updated — cluster citation-backfill was deferred.

### 2.2 Harness contract

The retrieval eval harness (M-RE1) requires:

- One `GoldLabel` per registry `intent_id` for the scored company (Elder Care only today).
- Labels pinned to an `ingestion_snapshot` triplet: `{catalog}:{chunk_count}:{date}`.
- Harness manifests store `registry_hash` + `gold_snapshot` — compare runs only within the same registry version.

Without the 8 labels, registry coverage tests fail and new CQA/KPI intents are `skipped_bootstrap_failed` in harness rollups.

### 2.3 Operator decision

`pending2.md` records the choice: **bootstrap now on `uc13_ale`**, not defer.

---

## 3. Lineage timeline

| When | Event | Artifact / SHA | Effect on gold labels |
|------|-------|----------------|----------------------|
| 2026-07-03 | M-RE3 control baseline | `baseline_299063e87806` | 49 intents, registry hash A |
| 2026-07-15 | `legal.insurance` filter fix (BACKGROUND) | `ec74042` → registry hash B | `RegistryHashMismatchError` vs Jul-3 baseline — compare waived |
| 2026-07-15/16 | New control baseline promoted | `baseline_1aeb0ace584a` | Stability-only evidence; 49-intent gold still valid for *that* registry |
| 2026-07-21 | M4 eval harness all agents closed | scorecards INDEX | Agent golden checklists; retrieval gold unchanged |
| 2026-07-24 | Hector merge T5/T6/T7 landed | `9d67077`…`53add78` | New CQA/KPI retrieval tools in agent code |
| 2026-07-24 | Registry catch-up | `8e1393c` | +8 intents in registry; xfail on coverage test |
| 2026-07-27 | Merge audit `pass-with-conditions` | `82538da` | G6 listed as operator follow-up |
| **Now** | **This task** | — | Re-bootstrap → 57 labels; new registry hash C |

### Related but separate debt (`pending2.md` phv4)

- **NEW-1:** `legal_contracts_agent.py` insurance filter fix (`ec74042`) — sound, untested for new behavior.
- **NEW-2:** Registry hash change made charter item-31 literal compare unrunnable; substitute stability check accepted at program level. **Not closed by this task** — document any new baseline promotion as a fresh registry generation.

---

## 4. The 8 missing intents

Registry (`57`) minus gold (`49`) = **8 intents**, all from T6/T7:

### CQA (+4) — source: `customer_quality_agent.py`

| intent_id | Agent tool | Bootstrap strategy hint |
|-----------|------------|-------------------------|
| `cqa.retrieve_cohort_data` | `_tool_retrieve_cohort_data` | Citation backfill from CQA analysis row; filename filters: Cohort, Customer, Retention, Revenue, QofE |
| `cqa.retrieve_contract_terms` | `_tool_retrieve_contract_terms` | CQA + LEGAL workstreams; Contract, MSA, Agreement, SOW |
| `cqa.retrieve_customer_health` | `_tool_retrieve_customer_health` | CUSTOMER workstream; health/tenure signals |
| `cqa.retrieve_revenue_type_and_renewals` | `_tool_retrieve_revenue_type_and_renewals` | Revenue type mix + renewal patterns (Hector guideline-2) |

### KPI (+4) — source: `kpi_agent.py`

| intent_id | Agent tool | Bootstrap strategy hint |
|-----------|------------|-------------------------|
| `kpi.retrieve_bench_and_capacity` | `_tool_retrieve_bench_and_capacity` | KPI_OPS + BUSINESS_MODEL; Bench, Capacity, Staffing, Pipeline |
| `kpi.retrieve_bill_rates_and_margins` | `_tool_retrieve_bill_rates_and_margins` | Rate card / project margin docs |
| `kpi.retrieve_healthcare_labor_market` | `_tool_retrieve_healthcare_labor_market` | Healthcare overlay labor market data |
| `kpi.retrieve_healthcare_revenue_per_unit` | `_tool_retrieve_healthcare_revenue_per_unit` | Revenue per bed/unit/caregiver metrics |

Full intent definitions (filters, `top_k`, queries): `eval/retrieval/intent_registry.yaml` lines ~268–378 (CQA) and ~727–873 (KPI).

---

## 5. Current state snapshot

```
registry intents:     57
committed gold labels:  49
missing from gold:      8  (listed above)
ingestion_snapshot pin: uc13_ale:35034:2026-07-02
gold status breakdown:  ready=18, partial=28, bootstrap_failed=3
```

Pre-existing `bootstrap_failed` (not part of the +8 gap, but may appear in re-bootstrap output):

- `cqa.retrieve_customer_concentration`
- `cqa.retrieve_retention_metrics`
- `qoe.retrieve_qofe_report`

**Catalog:** `uc13_ale` (dev/eval). Do not mix with prod `uc13` in comparisons.

**Vector index:** `uc13_ale.ingestion.embeddings_index` — confirmed ready (2026-07-27). Required for agent runs; bootstrap itself reads Delta `chunks` + analysis citations, not VS directly.

**Chunk count note:** Live corpus may differ from pinned `35034` (e.g. analysis doc cited ~35,104 chunks). Bootstrap recomputes snapshot from `COUNT(*)` at run time — expect `ingestion_snapshot` to update if chunk count changed.

---

## 6. Codebase map

### 6.1 Primary implementation

| Path | Role |
|------|------|
| `eval/retrieval/gold/bootstrap.py` | `GoldLabelBootstrap` — two-pass bootstrap (pass-1 positives, pass-2 negatives); `main()` entry point |
| `eval/retrieval/gold/__init__.py` | Package export |
| `eval/retrieval/intent_registry.yaml` | **Authoritative intent list** (57 rows) |
| `eval/retrieval/gold_labels/elder_care.yaml` | **Target output** — committed gold labels |
| `eval/retrieval/models.py` | `GoldLabel`, `RetrievalIntent` Pydantic models |
| `eval/retrieval/harness.py` | `compute_registry_hash()`, `compute_gold_snapshot()` — manifest triplet pins |

### 6.2 Agent source (why intents exist)

| Path | New tools (T6/T7) |
|------|-------------------|
| `databricks/agents/workstreams/customer_quality_agent.py` | `_tool_retrieve_cohort_data`, `_tool_retrieve_customer_health`, `_tool_retrieve_contract_terms`, `_tool_retrieve_revenue_type_and_renewals` (~L496–593, wired ~L916–919) |
| `databricks/agents/workstreams/kpi_agent.py` | `_tool_retrieve_bill_rates_and_margins`, `_tool_retrieve_bench_and_capacity`, `_tool_retrieve_healthcare_revenue_per_unit`, `_tool_retrieve_healthcare_labor_market` (~L486–588, wired ~L953–956) |

### 6.3 Registry extraction & guards

| Path | Role |
|------|------|
| `eval/retrieval/registry_extractor.py` | Static scan of agent tools → registry rows |
| `eval/retrieval/tests/fixtures/expected_intent_counts.yaml` | CI partition counts (cqa: 9, kpi: 9, total 55–60) |
| `eval/retrieval/tests/test_registry_extractor.py` | Registry drift guards |
| `databricks/agents/shared/run_context.py` | Loads `intent_registry.yaml` at agent runtime |

### 6.4 Tests (acceptance surface)

| Path | What it proves |
|------|----------------|
| `eval/retrieval/tests/test_gold_bootstrap.py` | Bootstrap logic (mocked Spark); **xfail coverage test** to remove |
| `eval/retrieval/tests/test_scope_resolver.py` | `bootstrap_failed` intents excluded from gate-eligible set |
| `eval/retrieval/tests/fixtures/scope_resolver_cases.yaml` | Fixture: `cqa.retrieve_customer_concentration` in affected-not-gated |
| `eval/retrieval/tests/test_harness_fixture.py` | Registry hash + gold snapshot roundtrip |

### 6.5 Harness ops & baselines

| Path | Role |
|------|------|
| `eval/retrieval/README.md` | **Operator runbook** — cluster baseline, DDL, join integrity (R-08), triplet pin rules |
| `eval/retrieval/harness_cli.py` | CLI: `run`, `validate-baseline` |
| `eval/retrieval/scripts/apply_ops_ddl.py` | Ops tables DDL for delta store |
| `harness-baseline-2026-07-15.md` | Prior baseline debug + `baseline_1aeb0ace584a` promotion narrative |
| `my_runbook.md` | Retrieval baseline pin: `baseline_1aeb0ace584a` |
| `uc13-company-data-analysis.md` | Elder Care corpus stats, prior `skipped_bootstrap_failed` rollup |

### 6.6 Merge program context

| Path | Role |
|------|------|
| `pending2.md` | Operator decision: bootstrap now |
| `.dev/plans/hector-ui-pipeline-merge/plan.md` | T5–T7 merge; §8 follow-up gold-label bootstrap |
| `.dev/plans/hector-ui-pipeline-merge/CLUSTER_GATES.md` | **G6** — this task |
| `.dev/audits/2026-07-27-hector-ui-pipeline-merge.md` | Audit notes xfail as pre-existing, unchanged |
| `CHANGELOG.MD` | `8e1393c` entry documents deferral |

---

## 7. Bootstrap mechanics (how it works)

From `eval/retrieval/gold/bootstrap.py` (spec §5.12.2 / Appendix A):

**Pass 1 — positives**

1. `citation_backfill` — read agent `analysis.*` row citations JSON → resolve to `chunk_id` via `ingestion.chunks`.
2. `section_range` — CIM page/section anchors (FTA-specific suffixes).
3. `filename_closure` — match `file_name_filter` tokens from intent registry against classified files.

**Pass 2 — negatives**

1. `basis_rule` — section_header ILIKE patterns (`%Projection%`, `%Pro Forma Income%`, `%Forecast%`).
2. `section_rule` — historical basis exclusions.
3. `cross_intent_positive` — paired intent negatives (FTA q1 ↔ q3 patterns).

**Join predicate (critical):** Bootstrap SQL inner-joins `ingestion.chunks` ↔ `classification.doc_relevance` on `(company_name, source_document)`. Orphan chunks are invisible to bootstrap.

**Analysis table map** (`AGENT_ANALYSIS_TABLE` in bootstrap.py):

```
cqa → customer_quality
kpi → kpi
qoe → quality_of_earnings
bma → business_model
legal → legal
fta.* → financial_trends
```

For the 8 new intents, pass-1 citation backfill requires a **fresh CQA/KPI agent run** on Elder Care with populated `citations` JSON in the analysis table. If the merge e2e DAG did not re-run CQA/KPI (see parallel SQLite threading issue in hector merge e2e), bootstrap may fall back to `filename_closure` only → review `gold_status` and `confidence` per row.

---

## 8. Execution procedure (cluster)

### Prerequisites

- [ ] Databricks Repos synced to `feat/merge-hector-incoming` (≥ `82538da`).
- [ ] `uc13_ale` Elder Care corpus present (`ingestion.chunks` > 0).
- [ ] VS index `uc13_ale.ingestion.embeddings_index` ready (for downstream harness, not bootstrap itself).
- [ ] CQA + KPI agent rows reasonably fresh (re-run Cells 14/15 or sequential DAG if citations stale).

### Step 1 — Bootstrap gold labels

On Databricks cluster (notebook or serverless with Spark):

```python
# After REPO_ROOT on sys.path and active SparkSession
from eval.retrieval.gold.bootstrap import main as bootstrap_main
bootstrap_main()
# Expected stdout: "Wrote 57 gold labels to .../elder_care.yaml (ready/partial=N, snapshot=uc13_ale:XXXX:YYYY-MM-DD)"
```

Or module invocation from repo root on cluster:

```bash
python -m eval.retrieval.gold.bootstrap
```

### Step 2 — Review output

- [ ] `len(labels) == 57`
- [ ] All 8 new intent_ids present with `gold_status != bootstrap_failed` (or document corpus gap if failed)
- [ ] Single `ingestion_snapshot` across all rows
- [ ] Diff `elder_care.yaml` — no accidental edits to unrelated intents

### Step 3 — Local validation

```bash
uv run --project databricks pytest eval/retrieval/tests/test_gold_bootstrap.py -q
```

Remove the `@pytest.mark.xfail` block on `test_committed_elder_care_yaml_validates_and_covers_registry` (lines ~278–285) **before** expecting 0 xfailed.

Full suite gate:

```bash
uv run --project databricks pytest tests/ eval/retrieval/tests/ -q
# Target: 762 passed, 5 skipped, 0 xfailed, 0 failed
```

### Step 4 — Commit

```text
gold: rebootstrap elder_care.yaml for 8 post-merge CQA/KPI intents (T5-T7)

Closes hector-ui-pipeline-merge G6 / pending2.md. Citation-backfill from
uc13_ale Elder Care corpus; removes xfail on registry coverage test.
```

### Step 5 — (Recommended) Harness baseline re-attestation

Per `eval/retrieval/README.md` cluster baseline runbook:

1. Join integrity (R-08) preflight.
2. `python -m eval.retrieval.harness_cli run --store-backend delta --catalog uc13_ale --company "Elder Care" --run-type baseline`
3. Stability check vs prior baseline **within same registry hash only**.
4. Promote new control baseline; update pins in `my_runbook.md`, `harness-baseline-*.md`, README `BASELINE_REF`.
5. **Do not** compare recall@10 to `baseline_1aeb0ace584a` — `RegistryHashMismatchError` is expected after registry expansion.

---

## 9. Acceptance criteria (done definition)

| # | Criterion | Verifier |
|---|-----------|----------|
| A1 | `elder_care.yaml` has 57 rows, 1:1 with registry | `test_committed_elder_care_yaml_validates_and_covers_registry` |
| A2 | No `xfail` on coverage test | pytest collection |
| A3 | Full suite ≥ 761 pass, 0 xfailed | `pytest tests/ eval/retrieval/tests/ -q` |
| A4 | Bootstrap stdout archived | `.dev/` attestation or commit message |
| A5 | 8 new intents not `bootstrap_failed` OR gap documented with corpus citation | manual review of yaml rows |
| A6 | G6 in `CLUSTER_GATES.md` marked PASS | operator sign-off |

---

## 10. Risks and watch-items

| Risk | Mitigation |
|------|------------|
| Stale CQA/KPI `citations` JSON | Re-run agents on Elder Care before bootstrap |
| `ingestion_snapshot` drift vs old baseline | Expected — promote new baseline, don't cross-compare |
| Pre-existing 3 `bootstrap_failed` rows | Out of scope unless bootstrap pass fixes them; document if still failed |
| Corpus gap (Clearsulting-style thin LEGAL) | Elder Care is the gold company — should have coverage; flag if not |
| Join integrity (orphan chunks) | Run R-08 preflight per README |
| Parallel DAG SQLite threading | Run CQA/KPI sequentially if provenance errors (`financial_trends` pattern) |

---

## 11. Downstream effects (after this chip)

1. **Harness gate-eligible set expands** — 8 more intents scored in baseline rollups.
2. **New registry hash** — all future baselines use hash C; pin in `retrieval_harness_latest_baseline`.
3. **Hector merge G6 closed** — one fewer open condition on merge greenlight.
4. **CQA/KPI retrieval regression detectable** — harness can now measure the new tools Hector added.
5. **Does not close** phv4 NEW-2 waiver — that's a separate program decision about historical compare evidence.

---

## 12. Quick reference commands

```bash
# Gap check (local)
python -c "
from pathlib import Path
from eval.retrieval.gold.bootstrap import load_registry, load_gold_labels
reg={i.intent_id for i in load_registry(Path('eval/retrieval/intent_registry.yaml'))}
gold={l.intent_id for l in load_gold_labels(Path('eval/retrieval/gold_labels/elder_care.yaml'))}
print('missing:', sorted(reg-gold))
"

# Registry partition counts
python -c "
import yaml
from collections import Counter
from eval.retrieval.gold.bootstrap import load_registry
ids=[i.agent_id for i in load_registry(__import__('pathlib').Path('eval/retrieval/intent_registry.yaml'))]
print(Counter(ids), 'total', len(ids))
"
```

---

## 13. Agent pickup checklist

- [ ] Read `pending2.md` (operator decision)
- [ ] Read `eval/retrieval/gold/bootstrap.py` (implementation)
- [ ] Read `eval/retrieval/README.md` § cluster baseline + R-08 join integrity
- [ ] Confirm 8 missing intent_ids (§4 above)
- [ ] Run bootstrap on `uc13_ale` / Elder Care
- [ ] Remove xfail in `test_gold_bootstrap.py`
- [ ] Commit `elder_care.yaml` + test fix
- [ ] Run full pytest suite
- [ ] Archive bootstrap stdout
- [ ] (Recommended) Promote new harness baseline
- [ ] Mark G6 PASS in `CLUSTER_GATES.md`

---

*Generated 2026-07-27 for agent handoff. Source of truth for operator intent: `pending2.md`. Source of truth for implementation: `eval/retrieval/gold/bootstrap.py`.*
