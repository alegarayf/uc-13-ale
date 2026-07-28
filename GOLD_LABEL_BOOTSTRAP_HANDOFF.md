# Gold label bootstrap & post-merge validation — agent handoff

**Primary chip (G6):** Close the 8-intent gold-label gap opened by `hector-ui-pipeline-merge` T5–T7 on **Elder Care**.  
**Follow-on chip (not G6):** Re-run merged agents on **Clearsulting, GKF, SPG** — post-merge validation, not retrieval gold labels.  
**Operator decision (2026-07-27):** Bootstrap the 8 labels on `uc13_ale` now (`pending2.md`).  
**Status (2026-07-28):** OPEN — registry has **57** intents; committed `elder_care.yaml` has **49** labels; xfail still on coverage test. Sqlite provenance fix **landed** (e2e `1074138209208842`, 9/0/0 Elder Care); BMA R-1/R-3 **fixed**; **4-company e2e not run** post-fix.

---

## 0. Terminology (read first)

Three different “bootstrap” concepts appear in this repo. Do not conflate them.

| Term | What it is | Where | Companies today |
|------|------------|-------|-----------------|
| **Retrieval gold-label bootstrap** | Citation-backed `positive_chunk_ids` / `negative_chunk_ids` per `intent_id` for the harness | `eval/retrieval/gold/bootstrap.py` → `eval/retrieval/gold_labels/{slug}.yaml` | **Elder Care only** (`elder_care.yaml` committed) |
| **Agent `baseline_bootstrap`** | First golden-checklist score accepted by `evaluate_promotion` | `eval/retrieval/promotion_gate.py` + `.dev/scorecards/` | Elder Care scored for all 7 agents; Clearsulting FTA/Legal only (M-PHV2) |
| **4-company pipeline e2e** | Full or partial DAG / agent runs on each SharePoint company | `run_diligence_pipeline.py`, Cells 11–17, `.dev/hector_merge_e2e_runner.py` | All 4 ingested on `uc13_ale`; **post-merge re-run only on Elder Care** |

**Validation conclusion (2026-07-28):**

- **New intents → yes, gold bootstrap required** — but **G6 closes on Elder Care only**. The harness contract (`eval/retrieval/README.md`, M-RE1) scores one gold file per company; only `elder_care.yaml` exists and only Elder Care has a committed registry-coverage test.
- **Other companies → yes, agent re-runs required** — but **not gold-label bootstrap** unless explicitly escalated. M4 charter **Decision 3** and `eval/retrieval/README.md` § second-company: FTA scorecard + pipeline evidence suffices; no full gold-label bootstrap on a second company unless FTA fails badly (spec §5.18).
- **Prerequisite link:** Citation backfill for the 8 new intents reads `uc13_ale.analysis.customer_quality` and `uc13_ale.analysis.kpi`. Those rows must be **post-merge** (fresh CQA/KPI runs) on the company being bootstrapped. Elder Care got a post-sqlite parallel DAG refresh (2026-07-27); Clearsulting/GKF/SPG analysis tables are **pre-merge** and must be re-run before any future multi-company gold bootstrap.

---

## 1. Intent — Chip A (G6, in scope)

Re-bootstrap Elder Care gold labels so **every row in `eval/retrieval/intent_registry.yaml` has exactly one row in `eval/retrieval/gold_labels/elder_care.yaml`**, with citation-backfilled positives from the live `uc13_ale` corpus on Databricks.

Minimum deliverables:

1. Ensure CQA + KPI agent rows are fresh on Elder Care (post-merge citations).
2. Run `GoldLabelBootstrap` on cluster against current Elder Care ingestion.
3. Commit updated `eval/retrieval/gold_labels/elder_care.yaml` (57 rows, single `ingestion_snapshot`).
4. Remove the `xfail` on `test_committed_elder_care_yaml_validates_and_covers_registry`.
5. Record stdout evidence (bootstrap summary + pytest pass).
6. *(Recommended)* Re-run harness baseline and promote a new control baseline — registry hash will change.

**Non-goals for Chip A (G6):**

- Committed gold-label YAML for Clearsulting/GKF/SPG — deferred per M4 Decision 3 (see §1b).
- Fixing pre-existing `bootstrap_failed` rows unless bootstrap pass naturally resolves them.
- Re-running Cell 7 full ingestion rebuild unless chunk count / snapshot materially drifted.

---

## 1b. Intent — Chip B (follow-on, not G6)

Re-run **merged** agents (especially **CQA, KPI, QoE** from T5–T7) on **Clearsulting, GKF, SPG** after the sqlite fix and BMA R-1/R-3 fixes. Tracked as **4-company e2e** in `post_merge_regressions.md` and `CHANGELOG.MD` (2026-07-27/28 adversarial gaps).

Why this is separate from G6:

| Question | G6 (gold labels) | Chip B (4-company agents) |
|----------|------------------|---------------------------|
| Closes xfail? | Yes | No |
| Commits new YAML? | `elder_care.yaml` | No (unless Phase C escalated) |
| Validates Hector merge on thin corpora? | Elder Care only | Clearsulting (2.2k chunks, 0 LEGAL), GKF, SPG (71k) |
| Operator decision recorded? | `pending2.md` — bootstrap now | Open — `post_merge_regressions.md` pending table |

Minimum deliverables for Chip B:

1. Parallel or sequential DAG e2e per company on `uc13_ale` (`.dev/hector_merge_e2e_runner.py` or `run_diligence_pipeline.py`).
2. `g1_score_all_agents.py` golden-checklist scores per company; compare to pre-merge baselines where they exist.
3. Record scorecards / `evaluate_promotion` where applicable (`.dev/scorecards/INDEX.md`).
4. Document company-specific gaps (e.g. Clearsulting Legal 0/11 is expected thin-data behavior per `uc13-company-data-analysis.md`).

**Optional Phase C (escalation only):** If the program decides to score retrieval harness on non–Elder Care companies, bootstrap additional files:

```text
eval/retrieval/gold_labels/clearsulting.yaml
eval/retrieval/gold_labels/gkf.yaml
eval/retrieval/gold_labels/spg.yaml
```

Infrastructure already supports this — `default_gold_path(company_slug)` in `eval/retrieval/harness.py` — but `GoldLabelBootstrap.main()` hardcodes Elder Care output; multi-company bootstrap needs a parameterized entry point or notebook loop. No CI coverage test exists for non–Elder Care gold files today.

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

### 2.3 Why other companies still matter (even without gold YAML)

1. **Merge validation:** T5–T7 changed CQA/KPI/QoE agent code. Only Elder Care has post-merge e2e evidence (`run_id=1074138209208842`). Other companies may hit different token caps, corpus shapes, or thin-data paths (BMA R-1 was Elder Care–discovered but SPG's 71k chunks are a different stress profile).
2. **Citation freshness:** If Phase C multi-company gold labels are ever bootstrapped, citation backfill requires post-merge `analysis.customer_quality` / `analysis.kpi` rows per company.
3. **Operator note (`pending2.md`):** New or updated data-room docs → re-run the affected agent; low-confidence TLDR sections may indicate stale upstream analysis.

### 2.4 Operator decisions

| Decision | Source | Effect |
|----------|--------|--------|
| Bootstrap 8 intents on `uc13_ale` now | `pending2.md` | Chip A (G6) |
| Multi-company gold labels deferred | M4 charter Decision 3, `eval/retrieval/README.md` L759 | Chip B = agent runs only unless escalated |
| 4-company e2e open post-sqlite-fix | `post_merge_regressions.md`, `CHANGELOG.MD` 2026-07-27/28 | Chip B |

---

## 3. Lineage timeline

| When | Event | Artifact / SHA | Effect |
|------|-------|----------------|--------|
| 2026-07-03 | M-RE3 control baseline | `baseline_299063e87806` | 49 intents, registry hash A |
| 2026-07-15 | `legal.insurance` filter fix (BACKGROUND) | `ec74042` → registry hash B | `RegistryHashMismatchError` vs Jul-3 baseline — compare waived |
| 2026-07-15/16 | New control baseline promoted | `baseline_1aeb0ace584a` | Stability-only evidence; 49-intent gold still valid for *that* registry |
| 2026-07-21 | M4 eval harness all agents closed | scorecards INDEX | Agent golden checklists; retrieval gold unchanged |
| 2026-07-24 | Hector merge T5/T6/T7 landed | `9d67077`…`53add78` | New CQA/KPI retrieval tools in agent code |
| 2026-07-24 | Registry catch-up | `8e1393c` | +8 intents in registry; xfail on coverage test |
| 2026-07-27 | Sqlite provenance fix + Elder Care parallel e2e | `1074138209208842` | 9/0/0 DAG; CQA/KPI citations refreshed on Elder Care |
| 2026-07-27 | Gold bootstrap started then **stopped**; yaml reverted | — | G6 still open |
| 2026-07-27 | Merge audit `pass-with-conditions` | `82538da` | G6 listed as operator follow-up |
| 2026-07-28 | BMA R-1/R-3 fixed + live-verified | `post_merge_regressions.md` | Isolated BMA verify; full DAG re-score still open |
| **Now** | **Chip A** | — | Re-bootstrap → 57 Elder Care labels; registry hash C |
| **Next** | **Chip B** | — | 4-company agent e2e post-fix (no gold YAML unless Phase C) |

### Related but separate debt (`pending2.md` phv4)

- **NEW-1:** `legal_contracts_agent.py` insurance filter fix (`ec74042`) — sound, untested for new behavior.
- **NEW-2:** Registry hash change made charter item-31 literal compare unrunnable; substitute stability check accepted at program level. **Not closed by Chip A** — document any new baseline promotion as a fresh registry generation.

---

## 4. The 8 missing intents (Chip A only)

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

### 5.1 Elder Care gold labels (Chip A)

```
registry intents:      57
committed gold labels: 49
missing from gold:     8  (listed above)
ingestion_snapshot pin: uc13_ale:35034:2026-07-02  (will update at bootstrap)
gold status breakdown: ready=18, partial=28, bootstrap_failed=3
pytest gate:           764 passed, 5 skipped, 1 xfailed (coverage test)
```

Pre-existing `bootstrap_failed` (not part of the +8 gap, but may appear in re-bootstrap output):

- `cqa.retrieve_customer_concentration`
- `cqa.retrieve_retention_metrics`
- `qoe.retrieve_qofe_report`

### 5.2 Four-company corpus (`uc13-company-data-analysis.md`)

All four SharePoint companies are pipeline-complete on `uc13_ale`. Post-merge agent validation status:

| Company | Chunks | Analysis tables | Post-merge e2e | Notes |
|---------|--------|-----------------|------------------|-------|
| Elder Care | 35.1k | All 7 agents | **Yes** (2026-07-27) | Gold company; G6 target |
| Clearsulting | 2.2k | All populated (pre-merge) | **No** | 0 LEGAL docs — Legal 0/11 expected |
| GKF | 3.0k | All populated (pre-merge) | **No** | 100% ingest join integrity |
| SPG | 71.0k | All populated (pre-merge) | **No** | LEGAL-heavy; BMA token-cap stress candidate |

**Catalog:** `uc13_ale` (dev/eval). Do not mix with prod `uc13` in comparisons.

**Vector index:** `uc13_ale.ingestion.embeddings_index` — confirmed ready. Required for agent runs and harness; bootstrap itself reads Delta `chunks` + analysis citations, not VS directly.

**Chunk count note:** Live corpus may differ from pinned `35034`. Bootstrap recomputes snapshot from `COUNT(*)` at run time.

---

## 6. Codebase map

### 6.1 Primary implementation

| Path | Role |
|------|------|
| `eval/retrieval/gold/bootstrap.py` | `GoldLabelBootstrap(company_name=..., catalog=...)` — two-pass bootstrap; `main()` hardcodes Elder Care output |
| `eval/retrieval/gold/__init__.py` | Package export |
| `eval/retrieval/intent_registry.yaml` | **Authoritative intent list** (57 rows) |
| `eval/retrieval/gold_labels/elder_care.yaml` | **Chip A target output** |
| `eval/retrieval/harness.py` | `default_gold_path(company_slug)` — multi-company path convention; only `elder_care` committed |
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
| `eval/retrieval/tests/test_gold_bootstrap.py` | Bootstrap logic (mocked Spark); **xfail coverage test** to remove (Chip A) |
| `eval/retrieval/tests/test_scope_resolver.py` | `bootstrap_failed` intents excluded from gate-eligible set |
| `eval/retrieval/tests/fixtures/scope_resolver_cases.yaml` | Fixture: `cqa.retrieve_customer_concentration` in affected-not-gated |
| `eval/retrieval/tests/test_harness_fixture.py` | Registry hash + gold snapshot roundtrip |

### 6.5 Harness ops & baselines

| Path | Role |
|------|------|
| `eval/retrieval/README.md` | **Operator runbook** — cluster baseline, DDL, join integrity (R-08), triplet pin rules, Decision 3 second-company procedure |
| `eval/retrieval/harness_cli.py` | CLI: `run`, `validate-baseline` (`--company-name` required) |
| `eval/retrieval/scripts/apply_ops_ddl.py` | Ops tables DDL for delta store |
| `harness-baseline-2026-07-15.md` | Prior baseline debug + `baseline_1aeb0ace584a` promotion narrative |
| `my_runbook.md` | Retrieval baseline pin: `baseline_1aeb0ace584a` |
| `uc13-company-data-analysis.md` | Multi-company corpus stats, `skipped_bootstrap_failed` rollup |

### 6.6 Merge & regression context

| Path | Role |
|------|------|
| `pending2.md` | Operator decision: bootstrap now (Chip A) |
| `post_merge_regressions.md` | Living regression map — 4-company e2e open, G6 open, BMA/Legal triage |
| `sqlite_removal.md` | Sqlite fix handoff — Phase 3 closed on Elder Care e2e |
| `.dev/plans/hector-ui-pipeline-merge/plan.md` | T5–T7 merge |
| `.dev/plans/hector-ui-pipeline-merge/CLUSTER_GATES.md` | **G6** — Chip A only |
| `.dev/audits/2026-07-27-hector-ui-pipeline-merge.md` | Audit notes xfail as pre-existing |
| `CHANGELOG.MD` | `8e1393c` deferral; 2026-07-27/28 e2e + BMA fix entries |

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

For the 8 new intents, pass-1 citation backfill requires a **fresh CQA/KPI agent run** with populated `citations` JSON. Elder Care was refreshed 2026-07-27; other companies need Chip B runs first.

**Multi-company API (Phase C):** `GoldLabelBootstrap` accepts `company_name` and `catalog` but `main()` only writes `elder_care.yaml`. For other companies:

```python
from pathlib import Path
from eval.retrieval.gold.bootstrap import GoldLabelBootstrap, load_registry, write_gold_labels

company = "Clearsulting"  # or "GKF", "SPG"
slug = company.lower().replace(" ", "_")
bootstrap = GoldLabelBootstrap(spark, company_name=company)
labels = bootstrap.bootstrap(load_registry(registry_path))
write_gold_labels(repo_root / f"eval/retrieval/gold_labels/{slug}.yaml", labels)
```

---

## 8. Execution procedure

### Chip A — G6 Elder Care gold bootstrap (cluster)

#### Prerequisites

- [ ] Databricks Repos synced to merge branch (≥ `82538da` + BMA R-1/R-3 fixes).
- [ ] `uc13_ale` Elder Care corpus present (`ingestion.chunks` > 0).
- [ ] VS index `uc13_ale.ingestion.embeddings_index` ready.
- [ ] CQA + KPI agent rows fresh (2026-07-27 e2e or re-run Cells 14/15 if citations stale).

#### Step A1 — Bootstrap gold labels

```python
from eval.retrieval.gold.bootstrap import main as bootstrap_main
bootstrap_main()
# Expected: "Wrote 57 gold labels to .../elder_care.yaml (ready/partial=N, snapshot=uc13_ale:XXXX:YYYY-MM-DD)"
```

#### Step A2 — Review output

- [ ] `len(labels) == 57`
- [ ] All 8 new intent_ids present with `gold_status != bootstrap_failed` (or document corpus gap)
- [ ] Single `ingestion_snapshot` across all rows

#### Step A3 — Local validation

```bash
uv run --project databricks pytest eval/retrieval/tests/test_gold_bootstrap.py -q
```

Remove `@pytest.mark.xfail` on `test_committed_elder_care_yaml_validates_and_covers_registry` before expecting 0 xfailed.

Full suite gate:

```bash
uv run --project databricks pytest tests/ eval/retrieval/tests/ -q
# Target: 764 passed, 5 skipped, 0 xfailed, 0 failed
```

#### Step A4 — Commit

```text
gold: rebootstrap elder_care.yaml for 8 post-merge CQA/KPI intents (T5-T7)

Closes hector-ui-pipeline-merge G6 / pending2.md. Citation-backfill from
uc13_ale Elder Care corpus; removes xfail on registry coverage test.
```

#### Step A5 — (Recommended) Harness baseline re-attestation

Per `eval/retrieval/README.md`:

1. Join integrity (R-08) preflight.
2. `python -m eval.retrieval.harness_cli run --store-backend delta --catalog uc13_ale --company-name "Elder Care" --run-type baseline`
3. Promote new control baseline; update pins in `my_runbook.md`, `harness-baseline-*.md`.
4. **Do not** compare recall@10 to `baseline_1aeb0ace584a` — `RegistryHashMismatchError` expected after registry expansion.

---

### Chip B — 4-company agent validation (follow-on)

#### Prerequisites

- [ ] Chip A not required to start Chip B, but both should use the same merge branch with sqlite + BMA fixes.
- [ ] Index sync passes for each company before agent runs.

#### Step B1 — Per-company e2e

Run parallel DAG or sequential agent cells per company on `uc13_ale`:

| Company | Suggested entry | Priority agents (T5–T7) |
|---------|-----------------|---------------------------|
| Clearsulting | `.dev/hector_merge_e2e_runner.py` or Cells 11–17 | CQA, KPI, QoE, BMA |
| GKF | same | CQA, KPI, QoE, BMA |
| SPG | same | CQA, KPI, QoE, BMA (token-cap watch) |

#### Step B2 — Score and record

```bash
python .dev/g1_score_all_agents.py
```

Record outcomes in `post_merge_regressions.md` and `.dev/scorecards/` as appropriate.

#### Step B3 — (Phase C only, if escalated) Multi-company gold bootstrap

Only if operator explicitly expands retrieval harness beyond Elder Care. Requires Chip B fresh analysis rows per company, then parameterized `GoldLabelBootstrap` loop (§7). Add coverage tests mirroring `test_committed_elder_care_yaml_validates_and_covers_registry` per committed YAML.

---

## 9. Acceptance criteria

### Chip A (G6) — done definition

| # | Criterion | Verifier |
|---|-----------|----------|
| A1 | `elder_care.yaml` has 57 rows, 1:1 with registry | `test_committed_elder_care_yaml_validates_and_covers_registry` |
| A2 | No `xfail` on coverage test | pytest collection |
| A3 | Full suite ≥ 764 pass, 0 xfailed | `pytest tests/ eval/retrieval/tests/ -q` |
| A4 | Bootstrap stdout archived | `.dev/` attestation or commit message |
| A5 | 8 new intents not `bootstrap_failed` OR gap documented | manual yaml review |
| A6 | G6 in `CLUSTER_GATES.md` marked PASS | operator sign-off |

### Chip B — done definition

| # | Criterion | Verifier |
|---|-----------|----------|
| B1 | CQA/KPI/QoE run SUCCESS on all 3 non–Elder Care companies | e2e logs / `analysis.*` `created_at` |
| B2 | Golden-checklist scores recorded | `g1_score_all_agents.py` output |
| B3 | No unexpected regressions vs pre-merge baselines | `post_merge_regressions.md` update |
| B4 | Thin-data gaps documented (Clearsulting Legal, etc.) | scorecard notes |

### Phase C — only if escalated

| # | Criterion | Verifier |
|---|-----------|----------|
| C1 | `{company_slug}.yaml` committed per company | file exists under `gold_labels/` |
| C2 | Harness `run` succeeds per company | `harness_cli run --company-name ...` |
| C3 | Coverage test per committed YAML | new pytest (not yet authored) |

---

## 10. Risks and watch-items

| Risk | Mitigation |
|------|------------|
| Stale CQA/KPI `citations` JSON (Elder Care) | Re-run agents before Chip A bootstrap |
| Stale analysis on Clearsulting/GKF/SPG | Chip B before any Phase C gold bootstrap |
| `ingestion_snapshot` drift vs old baseline | Expected — promote new baseline, don't cross-compare |
| Pre-existing 3 `bootstrap_failed` rows | Out of scope for Chip A unless bootstrap fixes them |
| Clearsulting thin LEGAL (0 docs) | Expected gap-correct; do not treat as agent failure |
| SPG BMA token-cap (71k chunks) | BMA R-1 fix should help; watch e2e logs for truncation |
| Join integrity (orphan chunks) | R-08 preflight per README |
| Parallel DAG SQLite threading | **Closed** by sqlite fix — parallel DAG OK with `spark=` injection |

---

## 11. Downstream effects

### After Chip A (G6)

1. Harness gate-eligible set expands by 8 intents.
2. New registry hash — future baselines use hash C.
3. Hector merge G6 closed.
4. CQA/KPI retrieval regression detectable on Elder Care.

### After Chip B

1. Post-merge validation confidence across all SharePoint companies.
2. Fresh analysis rows enable optional Phase C multi-company gold labels.
3. Scorecards / INDEX updated for non–Elder Care partitions where applicable.

### Does not close

- phv4 NEW-2 waiver (registry hash compare substitute).
- Legal R-2 (t4c variance) — deferred per operator.
- Formal `evaluate_promotion` for 2026-07-27 e2e batch — still open in `post_merge_regressions.md`.

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
from collections import Counter
from pathlib import Path
from eval.retrieval.gold.bootstrap import load_registry
ids=[i.agent_id for i in load_registry(Path('eval/retrieval/intent_registry.yaml'))]
print(Counter(ids), 'total', len(ids))
"

# Re-score all agents (Chip B)
python .dev/g1_score_all_agents.py
```

---

## 13. Agent pickup checklist

### Chip A (G6) — do first

- [ ] Read `pending2.md` (operator decision)
- [ ] Confirm CQA/KPI Elder Care `created_at` ≥ 2026-07-27 (or re-run)
- [ ] Run bootstrap on `uc13_ale` / Elder Care
- [ ] Remove xfail in `test_gold_bootstrap.py`
- [ ] Commit `elder_care.yaml` + test fix
- [ ] Run full pytest suite (target 0 xfailed)
- [ ] (Recommended) Promote new harness baseline
- [ ] Mark G6 PASS in `CLUSTER_GATES.md`

### Chip B — do after or in parallel (not G6)

- [ ] Read `post_merge_regressions.md` pending table
- [ ] Run 4-company e2e post-sqlite-fix + BMA R-1/R-3
- [ ] Score with `g1_score_all_agents.py`
- [ ] Update `post_merge_regressions.md` and scorecards
- [ ] Escalate to Phase C only if operator wants multi-company harness gold labels

---

## 14. Potential additions & follow-ups (agent discretion)

Items below were surfaced from a cross-doc review (`post_merge_regressions.md`, `pending2.md`, `sqlite_removal.md`, `CLUSTER_GATES.md`, `my_runbook.md`, `uc13-company-data-analysis.md`, merge audit, changelog 2026-07-27/28). **Not in scope unless an agent or operator explicitly pulls them in.** Chips A/B/C above remain the default program.

### How to use this section

| Bucket | Meaning |
|--------|---------|
| **Include (recommended)** | Strong fit for the same cluster session or immediately after Chip A; low scope creep |
| **Optional (same program)** | Reasonable to batch with merge closeout; agent judges cost vs value |
| **Operator decision** | Blocked on an explicit call — do not assume |
| **Exclude** | Deferred, out of scope, or separate ticket per operator / program decision |
| **Meta / doc hygiene** | Update trackers after work lands; not cluster work |

Suggested program sizes (for reference only):

- **Package A (minimum):** Chip A only → closes G6 + xfail
- **Package B (recommended):** Chip A + Tier-2 harness attestation + BMA re-score + scorecard INDEX update
- **Package C (full):** Package B + Chip B + G5 VDR + Profiler re-run

---

### Include (recommended) — not yet spelled out above

| ID | Item | Source | Verifier / notes |
|----|------|--------|------------------|
| R-14.1 | **Update `INGESTION_SNAPSHOT` test pin** after bootstrap if chunk count changed | `test_gold_bootstrap.py` pins `uc13_ale:35034:2026-07-02`; T11 changelog precedent | pytest `test_committed_elder_care_yaml_validates_and_covers_registry` + `test_compute_ingestion_snapshot_single_value` |
| R-14.2 | **R-08 join integrity preflight** before harness baseline | `eval/retrieval/README.md` § join integrity | Cluster orphan-count SQL = 0; CI `tests/test_join_integrity.py` already green |
| R-14.3 | **VS index sync check** (`✓ Index ready`) before harness or retrieval-sensitive runs | `harness-baseline-2026-07-15.md` | Sync-only cell if Delta embeddings OK but index stale |
| R-14.4 | **Land working-tree commits** before cluster session (sqlite fix, BMA R-1/R-3, doc updates) | `post_merge_regressions.md` (some items still say "uncommitted"; git may be ahead) | `git status` clean; HEAD matches Databricks Repos sync SHA |
| R-14.5 | **BMA post-fix golden re-score → 7/7** | `post_merge_regressions.md`, `pending2.md` | `g1_score_all_agents.py` on fresh BMA row; R-1/R-3 only isolated-verified so far |
| R-14.6 | **Verify orchestrator memo** — no `section 'business_model' generator failed` | `post_merge_regressions.md` R-3 | Full DAG log or `run_full_pipeline.py` after BMA re-run |

---

### Optional (same program) — agent decides

| ID | Item | Source | When to include |
|----|------|--------|-----------------|
| O-14.1 | **Promote new harness control baseline** (registry hash C) + update pins | §8 Step A5, `harness-baseline-2026-07-15.md`, `my_runbook.md` | After Chip A; pairs with R-14.2/R-14.3 |
| O-14.2 | **Refresh `elder_care_slice.json`** if ready exemplar chunk IDs change | `CHANGELOG.MD` T11, `test_elder_care_slice_fixture.py` | Only if bootstrap mutates pinned ready rows |
| O-14.3 | **Fix pre-existing `bootstrap_failed` rows opportunistically** | §5.1 lists 3 in yaml; harness rollup has **6** `skipped_bootstrap_failed` (adds 3 FTA `q1_financial_statements` intents) | Include if rebootstrap pass naturally resolves them; else document corpus gaps |
| O-14.4 | **Formal scorecards** — `evaluate_promotion` + `.dev/scorecards/INDEX.md` for e2e `1074138209208842` and any new runs | Changelog 2026-07-27/28 adversarial gaps, §11 | Closes observability gap; not required for G6 |
| O-14.5 | **Full parallel e2e** (9 agents) post-BMA fix | `post_merge_regressions.md` | Alternative to isolated BMA path; also re-validates exec-summary bridge, forecast, cross_analysis |
| O-14.6 | **Profiler re-run** (Cells 9–10) | `post_merge_regressions.md` — stale profile `created_at` 2026-07-22 | G1 incomplete for profiler; not in DAG |
| O-14.7 | **G5 VDR gate** — `run_vdr_pipeline.py` one company E2E | `CLUSTER_GATES.md` G5 | Merge gate; unrelated to retrieval gold |
| O-14.8 | **GKF/SPG VS index sync** before Chip B agent runs | `uc13-company-data-analysis.md` P0 | Prerequisite if semantic retrieval untrusted on those companies |
| O-14.9 | **SPG BMA token-cap watch** during Chip B | `post_merge_regressions.md`, 71k chunks | R-1 fix should help; watch e2e log for truncation |
| O-14.10 | **QoE extraction token-cap preemptive check** | `CLUSTER_GATES.md` G1 watch-item | Same class as BMA R-1; currently holds 5/6 |
| O-14.11 | **Phase C multi-company gold YAML** (`clearsulting.yaml`, `gkf.yaml`, `spg.yaml`) | M4 Decision 3 (default: defer), §1b | Only if operator escalates harness beyond Elder Care |
| O-14.12 | **phv4 NEW-2 program sign-off** — accept substitute stability evidence for item-31 | `pending2.md` | Program decision after O-14.1 baseline promotion; cannot retro-compare to `baseline_299063e87806` |
| O-14.13 | **Audit F-3** — test or written waiver for `build_exec_summary(..., llm_endpoint=None)` | `.dev/audits/2026-07-27-hector-ui-pipeline-merge.md` | Merge audit `pass-with-conditions`; not G6-blocking |
| O-14.14 | **G2–G4 formal sign-off** in `CLUSTER_GATES.md` | `post_merge_regressions.md` — partially evidenced by e2e `1074138209208842` | Mark PASS with stdout if not already done |
| O-14.15 | **Clearsulting Legal 0/11 attestation** — thin-data narrative, not agent failure | `uc13-company-data-analysis.md`, M-PHV2 scorecards | Required context when scoring Chip B |

---

### Operator decision — do not assume

| ID | Question | Options | Source |
|----|----------|---------|--------|
| D-14.1 | **BMA validation path** | (a) Isolated BMA re-run + `g1_score_all_agents.py` first, or (b) straight to full parallel e2e | `pending2.md` L7–10 |
| D-14.2 | **Pre-existing `bootstrap_failed` intents** | Fix during rebootstrap vs document-only vs stay out of scope | §5.1 vs 6-intent harness rollup |
| D-14.3 | **Package size** | A (G6 only) / B (G6 + harness + BMA + scorecards) / C (+ 4-company + VDR + Profiler) | §14 program sizes |
| D-14.4 | **Phase C multi-company gold labels** | Escalate vs keep deferred per M4 Decision 3 | `eval/retrieval/README.md` L759 |
| D-14.5 | **phv4 NEW-2** | Accept substitute stability evidence vs hold for more baselines | `pending2.md` |

---

### Exclude — do not pull into this chip without new operator approval

| ID | Item | Why excluded | Source |
|----|------|--------------|--------|
| X-14.1 | **Legal R-2 (t4c 8/11 vs 9/11)** | Operator deferred — LLM entity-resolution variance, not merge blocker | `pending2.md`, `post_merge_regressions.md` |
| X-14.2 | **Legal dedupe hardening** (`source_doc` in `_register_dedupe_key`) | Separate follow-up ticket | `pending2.md`, `post_merge_regressions.md` backlog |
| X-14.3 | **phv4 NEW-1** — test `ec74042` insurance BACKGROUND filter behavior | Sound fix but untested; unrelated to G6/CQA/KPI gap | `pending2.md` |
| X-14.4 | **CQA cosmetic** — `industry_overlay_used` empty in assessment markdown | No checklist score impact | `CLUSTER_GATES.md` G1 watch-item |
| X-14.5 | **Elder Care ingest gap** — 182 `should_parse` files missing from chunks (52% join) | Large scope (Cell 7/8c/8d); improves gold quality not registry coverage | `uc13-company-data-analysis.md` |
| X-14.6 | **Phase 7 data room completeness scorecard** | Design milestone, not merge closure | `my_runbook.md`, `pending.md` |
| X-14.7 | **M-PHV4 deferred items 28/30** (shared context assembly, `workstream_tags.py`) | Pre-merge program debt | `my_runbook.md` Phase 4 |
| X-14.8 | **`set_pipeline_thread` wiring in `pipeline.py`** | Separate debt; sqlite fix worked without it | `sqlite_removal.md` |
| X-14.9 | **Presentation / TLDR experiments** (aggressive LLM generation, mitigants digest) | Product experiment | `pending.md` |
| X-14.10 | **Garden UI (`develop`) merge** | Explicitly later per merge scout | `MERGE_SCOUT_hector_ui_pipeline_integration.md` §10 |

---

### Meta / doc hygiene — after cluster work

| ID | Item | When |
|----|------|------|
| M-14.1 | Update `post_merge_regressions.md` pending table (close rows as done) | After each tier |
| M-14.2 | Update `sqlite_removal.md` — Phase 3 checklist still shows open boxes; e2e `1074138209208842` closed it | After confirming cluster evidence |
| M-14.3 | Update `my_runbook.md` — still says Phase 9 Hector merge pending / "open follow-ups: none" | After merge program closeout |
| M-14.4 | Update `CHANGELOG.MD` tier-2 entry for completed chips | On commit |
| M-14.5 | **Ongoing ops pattern:** new/updated data-room docs → re-run affected agent; low-confidence TLDR → check upstream staleness | `pending2.md` L14–15 — not a one-shot task |

---

### Dependency sketch (if pulling optional items in)

```
R-14.4 (commit/sync)
  → Chip A (§13)
    → R-14.1 (test pin) + O-14.2 (slice fixture, if needed)
    → R-14.2 + R-14.3 → O-14.1 (baseline promote) → O-14.12 (NEW-2 sign-off)
  → R-14.5/R-14.6 (+ O-14.5 if chosen) — can parallel Chip A only after BMA fix is on cluster
  → Chip B (§13) — needs sqlite + BMA fixes on branch; O-14.8 before agent runs
  → O-14.11 Phase C — only after Chip B fresh analysis per company
```

---

*Updated 2026-07-28. Chip A operator intent: `pending2.md`. Chip B tracker: `post_merge_regressions.md`. Implementation: `eval/retrieval/gold/bootstrap.py`.*
