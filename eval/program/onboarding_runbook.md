# Company onboarding runbook (M4 / S3)

Executable procedure for onboarding a SharePoint company onto the eval program. **Catalog:** `uc13_ale` on every cluster step unless noted.

**Authority:** This document is the canonical onboarding path under `eval/program/`. The partial Clearsulting pattern in `eval/retrieval/README.md` (M-PHV1 / M-PHV2 sections) is historical context only — follow this runbook for M4 multi-company gold onboarding.

**Registry disambiguation:**

| Artifact | Path | Role |
|----------|------|------|
| **Program registry** (sole hub) | `eval/program/registry.yaml` | Dispositions, deferrals, runbook-defect rows |
| **Intent registry** (retrieval bootstrap) | `eval/retrieval/intent_registry.yaml` | Retrieval intent definitions consumed by gold bootstrap |

Do not cite retired registry mirrors or legacy eval contract paths — use only `eval/program/registry.yaml` as the program registry hub.

**Placeholder:** Replace `<Display Name>` with the SharePoint company folder name (e.g. `Clearsulting`, `Elder Care`).

---

## Walk order (spec §11 worked example)

### Step 1 — Confirm company in program registry

**Catalog:** n/a (repo edit).

1. Open `eval/program/registry.yaml` (program registry — not the intent registry).
2. Confirm the company is represented in the program domain (existing rows, staged onboarding items, or a new row added by operator edit).
3. Record any open program dispositions that affect this company's surfaces before continuing.

No CLI. This step is a manual registry edit / review.

---

### Step 2 — Ingest preflight

**Catalog:** `uc13_ale`.

Default walk uses the `sql_chunk_count` backend. Run `doc_status` as a secondary probe when operator needs document-level coverage context (backend richness deferred per registry row `PREFLIGHT-DOCSTATUS-1`).

**Default backend (`sql_chunk_count`):**

```bash
python -m eval.retrieval.ingest_preflight --company "<Display Name>" --catalog uc13_ale --backend sql_chunk_count
```

**Secondary backend (`doc_status`):**

```bash
python -m eval.retrieval.ingest_preflight --company "<Display Name>" --catalog uc13_ale --backend doc_status
```

Preflight returns a summary on stdout and exit code `0` on success. §8.4 boundary never raises — failures surface as exit code `1` with a message on stderr.

---

### Step 3 — Parameterized gold bootstrap

**Catalog:** `uc13_ale`.

Gold bootstrap requires an active Databricks `SparkSession` (after ingestion rebuild). Gold output defaults to `eval/retrieval/gold_labels/<canonical_slug>.yaml` via `harness.default_gold_path` — do not hand-derive filenames.

#### Cluster execution (serverless)

**Operator path when no local Spark** (typical laptop workflow): submit via `eval/program/onboarding_cluster_submit.py`. Full recipe: **Onboarding cluster steps** in `.dev/agent-databricks-recipes.md`.

The helper:

1. Loads repo-root `.env` (never prints tokens).
2. **Syncs code** — uploads `eval/retrieval/` and `databricks/agents/` to `/Workspace/Users/<you>/uc-13-ale/` (run `sync` subcommand alone to upload without submitting).
3. Submits a serverless `jobs.submit` task with pip deps: **`pyyaml`**, **`pydantic>=2.0`**, **`mlflow`**.
4. Sets **`PYTHONPATH`** to repo root (bootstrap driver).
5. Polls to completion; prints `DATABRICKS_RUN_ID=` on stdout.

```bash
python eval/program/onboarding_cluster_submit.py bootstrap --company "<Display Name>" --catalog uc13_ale
```

Use `--no-sync` only when the workspace copy is already fresh. Step 3 gold output lands on the workspace driver — export `eval/retrieval/gold_labels/<canonical_slug>.yaml` back locally before committing.

#### Reference shape (cluster CLI equivalent)

When running inside an interactive cluster notebook or all-in-one shell with Spark already active:

```bash
python -m eval.retrieval.gold.bootstrap --company "<Display Name>" --catalog uc13_ale
```

Optional explicit output path:

```bash
python -m eval.retrieval.gold.bootstrap --company "<Display Name>" --catalog uc13_ale --output eval/retrieval/gold_labels/<canonical_slug>.yaml
```

Replace `<canonical_slug>` with the folded slug printed by prior steps (e.g. `clearsulting`).

---

### Step 4 — Exemption annotations from corpus profile

**Catalog:** n/a (committed YAML store at `eval/program/eval_exemptions.yaml`).

Annotate intents the corpus cannot honestly gold-label. Thin-data companies (e.g. Clearsulting with zero LEGAL-classified docs) should produce `known_gap`-honest rows via `eliminates` exemptions rather than fabricated gold.

**Add one exemption:**

```bash
python -m eval.retrieval.exemptions add --company "<Display Name>" --intent-id <intent> --surface <fta_numeric|legal_register|exec_summary|null> --coverage <eliminates|narrows|null> --reason <corpus_absent|corpus_thin|overlay_mismatch> --evidence <k=v> --approved-by operator
```

**List exemptions for the company:**

```bash
python -m eval.retrieval.exemptions list --company "<Display Name>"
```

Example (Clearsulting legal corpus absent — adjust intent id to match bootstrap output):

```bash
python -m eval.retrieval.exemptions add --company "Clearsulting" --intent-id legal.evidence --surface legal_register --coverage eliminates --reason corpus_absent --evidence legal_doc_count=0 --approved-by operator
```

---

### Step 5 — Harness baseline run

**Catalog:** `uc13_ale`.

Establishes the retrieval harness baseline for the company. When `--gold-path` is omitted, gold resolves from `--company-name` via `canonical_company_slug` → `default_gold_path`. Requires Spark (Delta eval store).

#### Cluster execution (serverless)

**Operator path when no local Spark:** same helper as step 3 — `eval/program/onboarding_cluster_submit.py` with the `harness-baseline` subcommand. See **Onboarding cluster steps** in `.dev/agent-databricks-recipes.md`.

Prerequisites match step 3: **code sync** of `eval/retrieval/` + `databricks/agents/`, pip deps **`pyyaml`**, **`pydantic>=2.0`**, **`mlflow`**, and **`PYTHONPATH`** including `databricks/` (harness imports agent shared code).

```bash
python eval/program/onboarding_cluster_submit.py harness-baseline --company "<Display Name>" --catalog uc13_ale
```

Re-syncs by default before submit. On success, logs include a harness `baseline_<hash>` run id — record it for step 6 evidence. If Databricks reports `INTERNAL_ERROR` but logs contain a valid `baseline_*` id, treat as success (T9 quirk; the submit script checks logs).

#### Reference shape (cluster CLI equivalent)

When running inside an interactive cluster with Spark already active:

```bash
python -m eval.retrieval.harness_cli run --store-backend delta --run-type baseline --company-name "<Display Name>" --catalog uc13_ale
```

Optional explicit gold path:

```bash
python -m eval.retrieval.harness_cli run --store-backend delta --run-type baseline --company-name "<Display Name>" --catalog uc13_ale --gold-path eval/retrieval/gold_labels/<canonical_slug>.yaml
```

On success, stdout prints the harness `run_id`. Record it for step 6 evidence.

---

### Step 6 — Per-company baseline promotion policy

**Catalog:** `uc13_ale`.

Retrieval harness baseline (step 5) and E2E checklist-regression promotion (this section) are distinct mechanisms. Step 5 pins retrieval gold + harness metrics. Step 6 links **pipeline agent** golden-checklist scores to harness manifests via `evaluate_promotion` — a **Python library call with no CLI wrapper**.

#### Frozen signature

Location: `eval/retrieval/promotion_gate.py`

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

#### What promotion requires for a company that is not Elder Care

| Argument | Supply for new company? | Notes |
|----------|-------------------------|-------|
| `store` | Yes | `DeltaEvalStore(spark, catalog="uc13_ale")` on cluster |
| `run_id` | Yes **when available** | Pipeline agent `run_id` from agent `main()` — **not** the step-5 harness baseline `run_id` |
| `e2e_agent_id` | Yes | Frozen agent ids: `fta`, `legal`, `bma`, `cqa`, `kpi`, `qoe`, `profiler` |
| `company_name` | Yes | Display name matching SharePoint folder |
| `catalog` | Yes | `uc13_ale` |
| `candidate_score` | **Often no** | Requires a scored per-company golden checklist — most non–Elder Care companies lack these at first onboarding |
| `candidate_total` | **Often no** | Checklist denominator; agent-specific (e.g. FTA `18`, Legal `11`, BMA `7`) |
| `e2e_snapshot_table` | Yes | Agent analysis table (e.g. `uc13_ale.analysis.financial_trends` for FTA) — catalog-prefixed constants |
| `waiver_id` | Omit on first bootstrap | First run expects `status="baseline_bootstrap"` without `waiver_id` |

#### Policy

1. **Do not invent** `candidate_score`, `candidate_total`, or pipeline `run_id` values. If the company lacks a scored golden checklist and a fresh pipeline agent run for an agent, **skip** `evaluate_promotion` for that agent and proceed to step 7.
2. **First-bootstrap path:** When all required arguments *are* available and no prior E2E baseline exists for `(e2e_agent_id, company_name, catalog)`, expect `PromotionResult.status == "baseline_bootstrap"`.
3. **Non–Elder Care deferral:** Per-company golden checklists and full agent matrices are not assumed at onboarding time. Missing score provenance is an onboarding shortfall — not a reason to reuse Elder Care scores.
4. **Eval-debt instead of invented values:** When `candidate_score` / `candidate_total` or a pipeline `run_id` cannot be supplied, open an eval-debt row (step 7) with `closes_when` naming the missing artifact. Cite registry row `OI-eval-harness-evaluate-promotion-clearsulting-gkf-spg` for the general pattern on non–Elder Care companies.
5. **Bloated-gold baseline label:** A promoted baseline whose gold carries bloated `filename_closure` intents (positive sets so large that max recall@10 is not interpretable per intent) must be labeled at promotion time — registry row, operator disposition signoff, and runbook cross-reference — so aggregate recall is not read as per-intent meaningful; see `GAP-M4-1-clearsulting-bloated-filename-closure` and `signoffs/T11-clearsulting-bloated-gold-disposition.md`.

#### Example invocation (only when checklist + pipeline run exist)

```python
from eval.retrieval.promotion_gate import evaluate_promotion
from eval.retrieval.store import DeltaEvalStore

store = DeltaEvalStore(spark, catalog="uc13_ale")
result = evaluate_promotion(
    store,
    "<pipeline_agent_run_id>",
    e2e_agent_id="fta",
    company_name="<Display Name>",
    catalog="uc13_ale",
    candidate_score=<from scored golden checklist>,
    candidate_total=18,
    e2e_snapshot_table="uc13_ale.analysis.financial_trends",
)
# First run for this agent+company: result.status == "baseline_bootstrap"
```

---

### Step 7 — Eval-debt rows for remaining shortfalls

**Catalog:** n/a (committed ledger at `eval/program/eval_debt/eval_debt.yaml`).

Record per-company onboarding gaps (missing promotion inputs, unattested surfaces, corpus limits). Before opening rows, raise `open_debt_high_water_mark` in the ledger YAML if the projected open count would exceed the mark.

**Open one debt row:**

```bash
python -m eval.retrieval.eval_debt open --company "<Display Name>" --surface <fta_numeric|legal_register|exec_summary|null> --kind <kind> --closes-when "<condition>"
```

**List debt rows:**

```bash
python -m eval.retrieval.eval_debt list --company "<Display Name>"
```

Example (promotion inputs missing for legal surface):

```bash
python -m eval.retrieval.eval_debt open --company "Clearsulting" --surface legal_register --kind promotion_inputs --closes-when "per-company legal golden checklist scored and pipeline run_id recorded"
```

---

### Step 8 — Trust-statement regeneration

**Catalog:** `uc13_ale`.

Regenerates `eval/program/trust_statement.md` from live ops, the program registry, and committed exemption / ingest state. T6 wired exemption-store companies and ingest preflight delegation into trust rows.

```bash
python -m eval.retrieval.trust_statement generate --catalog uc13_ale --registry eval/program/registry.yaml
```

Verify regenerated rows for the onboarded company include expected `known_gap` entries from step 4 exemptions and ingest probe status from step 2.

---

## Runbook defect clause (spec §11.2)

If any step during a walk requires **design judgement** — choosing a new metric, inventing a gold label, defining a new exemption reason, or improvising a CLI flag not listed above — **stop**. That gap is a **runbook defect**, not an operator workaround.

**Procedure:**

1. Do not improvise.
2. Add a row to `eval/program/registry.yaml` describing the defect (what decision was needed, which step blocked, proposed contract change).
3. Resume the walk only after the registry disposition is resolved and this runbook is updated in a follow-on subtask.

Program-wide deferrals belong in the program registry. Company-scoped onboarding shortfalls with a trust-row citation belong in the eval-debt ledger (step 7).

---

## Multi-company onboarding lessons

Operator-facing lessons from the Clearsulting pilot (M4), Chip B 4-company agent validation, and gold-bootstrap handoff work. These complement the step-by-step walk above; they do not replace any step.

### INFO vs gated G1 scoring vocabulary

Three different "bootstrap" labels appear in this repo. Do not conflate them:

| Term | What it is | Where |
|------|------------|-------|
| **Retrieval gold bootstrap** | Citation-backed `positive_chunk_ids` per `intent_id` for the harness | Step 3 — `eval.retrieval.gold.bootstrap` → `gold_labels/{slug}.yaml` |
| **G1 `INFO (baseline_bootstrap)`** | Golden-checklist score with **no PASS/REGRESSION gate** — first post-merge evidence only | `.dev/g1_score_all_agents.py` when `BASELINES[company_slug][agent]` is `None` |
| **Agent `baseline_bootstrap`** | First scored checklist accepted by `evaluate_promotion` when no prior ops-store baseline exists | Step 6 — `PromotionResult.status == "baseline_bootstrap"` |

**G1 gate semantics:** When a company has a declared golden floor (Elder Care today), the scorer emits **PASS** or **REGRESSION** against that floor. When no floor is configured (`None`), the scorer emits **`INFO (baseline_bootstrap)`** — the score is recorded for evidence, but there is no pass/fail verdict. That is expected for a company with no prior golden checklist, not a failure mode.

**Why it matters:** A Chip B scorecard showing `INFO (baseline_bootstrap)` for GKF or SPG is correct first-run labeling. It is **not** evidence that retrieval gold bootstrap (step 3) failed or leaked into agent validation.

### No floor without a prior baseline

**Rule:** Do not invent a comparison bar. Absence of a prior baseline is an explicit design decision — informational scores, not fabricated PASS/FAIL.

1. **Do not compare against Elder Care.** The scorer previously hardcoded Elder Care golden floors; running another company's rows through those floors produces false PASS/REGRESSION verdicts against the wrong company's bar.
2. **Smoke-tier scorecards are not golden floors.** Clearsulting's 2026-07-07 smoke-tier `3/3` INDEX rows pre-date post-merge fixes and a different evidence tier. Treat them as historical smoke evidence, not as `evaluate_promotion` priors.
3. **Skip `evaluate_promotion` when inputs are missing.** Step 6 already defers promotion when `candidate_score`, `candidate_total`, or a pipeline `run_id` cannot be supplied honestly. The same principle applies to G1 scoring: no valid prior → document-only scorecards with `INFO` gate, not gated PASS/REGRESSION.
4. **Open eval-debt instead of reusing another company's scores.** Missing per-company golden checklists are onboarding shortfalls (step 7), not reasons to borrow Elder Care numbers.

When baseline evidence tiers differ across companies (golden vs smoke vs none), default to **no gate** until an operator explicitly promotes a floor.

### Company-scoped gold exclusions

**Rationale:** Gold exclusion and exemption machinery operates in **`(intent_id × company)`** space — bootstrap, disjointness tests, harness rollups, and claim-map resolution all consume per-company gold. A config artifact keyed by `intent_id` alone is a coupling surface: changing exclusion for one company can silently rewrite another company's committed gold annotations.

**Structural fix:** `eval/retrieval/gold/gold_exclusions.yaml` is company-scoped (`companies.{slug}.excluded[]`). Step 4 exemptions in `eval/program/eval_exemptions.yaml` are also keyed per company. Do not add global intent-only exclusion rows.

**Clearsulting illustrations:**

| Defect class | What happened | Honest handling |
|--------------|---------------|-----------------|
| **Bloated `filename_closure`** | Twelve intents with 1,000+ positives each — aggregate recall@10 looks green while per-intent max recall@10 is ~1% and not interpretable | Registry disposition (`GAP-M4-1-clearsulting-bloated-filename-closure`), eval-debt rows, baseline labelling at promotion — not re-bootstrap or pretend the metric is meaningful per intent |
| **KPI PDF corpus gap** | Warehouse citations use `Section: {title}[, Page N]` while chunk `section_header` stores title only; some cited sections (e.g. `Other EBITDA considerations`) have no matching parsed header — content lives under `Overview` / `Description of adjustment` | `overlay_mismatch` exemption (step 4), not a bootstrap bug; resolve what format allows, degrade honestly what overlay forbids |

When a shared hub artifact looks "transitive" but is consumed in a two-dimensional context, treat it as a coupling surface regardless of import depth.

### Chip A (gold bootstrap) vs Chip B (4-company e2e smoke)

Historical program chips map onto this runbook as follows:

| | **Chip A — retrieval gold bootstrap** | **Chip B — 4-company agent e2e smoke** |
|---|--------------------------------------|----------------------------------------|
| **Purpose** | Citation-backed gold labels + harness baseline for retrieval eval | Post-merge pipeline agent validation on thin/large corpora |
| **Runbook equivalent** | Steps 2–5 (preflight → gold bootstrap → exemptions → harness baseline) | **Not in this runbook** — separate DAG e2e + `g1_score_all_agents.py --company` |
| **Commits** | `eval/retrieval/gold_labels/{slug}.yaml`, harness baseline evidence | Scorecards under `.dev/scorecards/`; no gold YAML unless escalated |
| **Required for new company eval onboarding?** | **Yes** — steps 3 and 5 are the parameterized Chip A path | **No** — optional unless validating merged agent code (CQA/KPI/QoE depth), refreshing `analysis.*` citation rows before citation backfill, or operator explicitly wants post-merge smoke evidence |
| **Prerequisite link** | CQA/KPI analysis rows should be post-merge if citation backfill depends on them | Fresh analysis rows per company enable future gold bootstrap but do not require it |

**When to run Chip B work for a new company:** After ingestion is stable, when merge-validation confidence is needed across corpus shapes (thin Clearsulting, LEGAL-heavy SPG scale), or when step 3 citation backfill requires fresh agent runs. Chip B does **not** substitute for steps 3–5; conversely, completing steps 3–5 does **not** close Chip B agent-validation debt.

**Phase C escalation (optional):** Multi-company committed gold YAML beyond the company being onboarded requires explicit operator escalation — infrastructure supports `default_gold_path(company_slug)`, but CI coverage tests and promotion policy apply per committed file.

Sources: `.dev/retrospectives/learning/2026-08-15-eval-consolidation-m4-onboarding-runbook.md`, `.dev/retrospectives/learning/2026-08-13-chip-b-4company-agent-validation.md`, `.dev/archive/GOLD_LABEL_BOOTSTRAP_HANDOFF.md`
