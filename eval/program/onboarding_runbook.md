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

Requires an active Databricks Spark session (cluster after ingestion rebuild). Gold output defaults to `eval/retrieval/gold_labels/<canonical_slug>.yaml` via `harness.default_gold_path` — do not hand-derive filenames.

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

Establishes the retrieval harness baseline for the company. When `--gold-path` is omitted, gold resolves from `--company-name` via `canonical_company_slug` → `default_gold_path`.

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
