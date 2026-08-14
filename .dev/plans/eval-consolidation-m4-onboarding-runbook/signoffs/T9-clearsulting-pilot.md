# T9 Clearsulting pilot walk — COMPLETE signoff

**Date:** 2026-08-14  
**Operator:** executor agent (T9 packet v1.2)  
**Catalog:** `uc13_ale`  
**Company display name:** Clearsulting  
**Canonical slug:** `clearsulting` (verified: `canonical_company_slug("Clearsulting") == "clearsulting"`)  
**Runbook:** `eval/program/onboarding_runbook.md` @ commit `8c68cf9`  
**Prerequisites:** T10-bis @ `231941b`, RB-DEFECT-T9-1 Option A @ `0a5b2f2`  
**Outcome:** **COMPLETE** — full eight-step walk; artifacts committed.

---

## Step 1 — Confirm company in program registry

**Action:** Reviewed `eval/program/registry.yaml` (no CLI).

**Open dispositions affecting Clearsulting surfaces:**

| Registry ID | Relevance |
|---|---|
| `A-09` | Clearsulting KPI overlay conflict — overlay_mismatch exemption filed Step 4 |
| `GAP-102-corpus-specific-gold-bootstrap-holes` | 0 LEGAL docs → five `corpus_absent` exemptions filed |
| `OI-eval-harness-evaluate-promotion-clearsulting-gkf-spg` | Promotion inputs absent — skip Step 6, eval-debt Step 7 |
| `OI-eval-harness-phase-c-multi-company-gold-yaml` | Updated in_progress with Clearsulting evidence |

**Exit code:** n/a (manual review)

---

## Step 2 — Ingest preflight

**Command:**

```bash
python -m eval.retrieval.ingest_preflight --company "Clearsulting" --catalog uc13_ale --backend sql_chunk_count
```

**Stdout:**

```
ingest_preflight: clearsulting @ uc13_ale backend=sql_chunk_count status=measured completeness=1.0000 denominator=22
```

**Exit code:** 0

---

## Step 3 — Parameterized gold bootstrap

**Command (runbook):**

```bash
python -m eval.retrieval.gold.bootstrap --company "Clearsulting" --catalog uc13_ale
```

**Execution:** Serverless Databricks `jobs.submit` via operator sync script (workspace upload + driver). T10-bis code synced before run.

| Attempt | Databricks run_id | Result |
|---|---|---|
| 1 | `502286866957035` | Bootstrap **SUCCESS** — 57 labels, 48 ready/partial; driver dbfs copy failed (non-fatal; gold on workspace) |
| 2 | `611237844786994` | FAILED — pydantic AliasChoices (pre-sync stale code; superseded) |

**Final stdout (bootstrap):**

```
Wrote 57 gold labels to .../clearsulting.yaml for company=clearsulting catalog=uc13_ale (ready/partial=48, snapshot=uc13_ale:2417:2026-08-14)
```

**Exit code:** 0 (bootstrap)

**Artifact:** `eval/retrieval/gold_labels/clearsulting.yaml` committed (702375 bytes).

**KPI overlay note (expected):** `kpi.retrieve_bench_and_capacity` landed `gold_status: ready` with `pdf_branch_unresolved` notes for `utilization_by_segment — leadership/sales-focused <50%` and `bench_note` (Section Other EBITDA considerations). Three other Clearsulting KPI claim_target intents resolved normally. No unexpected KPI `bootstrap_failed` beyond excluded healthcare intents.

---

## Step 4 — Exemption annotations from corpus profile

**Commands:** six `python -m eval.retrieval.exemptions add` invocations.

| Intent | Surface | Coverage | Reason | Evidence |
|---|---|---|---|---|
| `legal.contracts_vendors_platform` | `legal_register` | `eliminates` | `corpus_absent` | `legal_doc_count=0` |
| `legal.employment` | `legal_register` | `eliminates` | `corpus_absent` | `legal_doc_count=0` |
| `legal.insurance` | `legal_register` | `eliminates` | `corpus_absent` | `legal_doc_count=0` |
| `legal.ip_privacy` | `legal_register` | `eliminates` | `corpus_absent` | `legal_doc_count=0` |
| `legal.litigation` | `legal_register` | `eliminates` | `corpus_absent` | `legal_doc_count=0` |
| `kpi.retrieve_bench_and_capacity` | `null` | `null` | `overlay_mismatch` | `registry_id=A-09`, both EBITDA claim keys from gold notes |

**List verification:**

```bash
python -m eval.retrieval.exemptions list --company "Clearsulting"
```

**Exit code:** 0 (six rows)

**Artifact:** `eval/program/eval_exemptions.yaml`

---

## Step 5 — Harness baseline run

**Command:**

```bash
python -m eval.retrieval.harness_cli run --store-backend delta --run-type baseline --company-name "Clearsulting" --catalog uc13_ale
```

**Execution:** Databricks run `1086586115456516` (serverless; deps `pyyaml`, `pydantic>=2.0`, `mlflow`; PYTHONPATH includes `databricks/`).

**Stdout (tail):**

```
baseline_7174e0399e29
```

**Exit code:** 0 (harness succeeded; job wrapper reported INTERNAL_ERROR on `SystemExit(0)` — see RB-DEFECT-T9-3)

**Harness run_id:** `baseline_7174e0399e29`

---

## Step 6 — Per-company baseline promotion policy

**Status:** Skipped per runbook §6 — no per-company golden checklists or pipeline `run_id` values for Clearsulting agents. Cited `registry:OI-eval-harness-evaluate-promotion-clearsulting-gkf-spg`.

**Exit code:** n/a (policy skip — not a HALT)

---

## Step 7 — Eval-debt rows for remaining shortfalls

**Command:**

```bash
python -m eval.retrieval.eval_debt open --company "Clearsulting" --surface null --kind promotion_inputs --closes-when "per-company golden checklists scored and pipeline run_ids recorded for all agents (registry:OI-eval-harness-evaluate-promotion-clearsulting-gkf-spg)"
```

**Ledger change:** `open_debt_high_water_mark` raised 0 → 1 before open.

**Opened row:** `clearsulting:global:promotion_inputs`

**Exit code:** 0

**Artifact:** `eval/program/eval_debt/eval_debt.yaml`

---

## Step 8 — Trust-statement regeneration

**Command:**

```bash
python -m eval.retrieval.trust_statement generate --catalog uc13_ale --registry eval/program/registry.yaml
```

**Stdout:**

```
trust_statement: wrote 14 rows for 2 companies -> eval/program/trust_statement.md
```

**Exit code:** 0

**Clearsulting verification:** seven trust rows present (`ingest_completeness`, `retrieval`, content surfaces with `known_gaps` from exemptions).

---

## Artifacts produced

| Path | Status |
|---|---|
| `eval/retrieval/gold_labels/clearsulting.yaml` | **Created** — 57 labels, 48 ready/partial |
| `eval/program/eval_exemptions.yaml` | **Updated** — 6 Clearsulting rows |
| `eval/program/eval_debt/eval_debt.yaml` | **Updated** — 1 open debt row |
| `eval/program/registry.yaml` | **Updated** — item 36 pilot row + RB-DEFECT-T9-3 |
| `eval/program/trust_statement.md` | **Regenerated** — Clearsulting rows included |
| `.dev/plans/eval-consolidation-m4-onboarding-runbook/signoffs/T9-clearsulting-pilot.md` | This signoff |

---

## Runbook-defect list

### RB-DEFECT-T9-1 — Unmapped KPI claim keys (RESOLVED @ `0a5b2f2`)

Option A claim-map extension; no longer fires on Clearsulting bootstrap.

### RB-DEFECT-T9-2 — KPI PDF citation branch (RESOLVED @ T10-bis `231941b`)

Bootstrap completes; overlay gaps annotated via exemption + gold notes.

### RB-DEFECT-T9-3 — Serverless cluster execution not documented in runbook (NEW)

- **Steps affected:** 3, 5
- **Decision needed:** Document serverless `jobs.submit` recipe — pip deps (`pydantic>=2.0`, `mlflow`), workspace code sync, `PYTHONPATH` with `databricks/`, gold retrieval without dbfs
- **Registry row:** `RB-DEFECT-T9-3` (committed)

---

## Judgements made

1. **`kpi.retrieve_bench_and_capacity` ready with overlay notes** — classified as `overlay_mismatch` exemption (surface/coverage null) per Flag-6; not a code defect.
2. **Five legal intents `bootstrap_failed`** — classified `corpus_absent` / `eliminates` (0 LEGAL-classified docs).
3. **CQA intents `cqa.retrieve_contract_terms`, `cqa.retrieve_customer_concentration` bootstrap_failed** — honest zero-positive citation backfill; no exemption filed (not in Step 4 scope; not Flag-6 ambiguous — left as bootstrap_failed gold).
4. **Promotion skip** — eval-debt opened; not a HALT.
5. **No code patches applied** — operator infrastructure only (workspace sync script, not committed).

---

## Kill-criterion evidence

| Criterion | Fired? | Evidence |
|---|---|---|
| Slug fold ≠ `clearsulting` | No | Python assert at walk start |
| Zero resolvable positives for every intent | No | 48/57 ready/partial; bootstrap completed |
| Step requires editing eval code to proceed | No | T10-bis prerequisite satisfied |
| Flag-6 unclassifiable corpus gap | No | Legal → corpus_absent; KPI overlay → overlay_mismatch |

---

## Post-walk addendum (2026-08-14)

**RB-DEFECT-T9-3** was filed during this walk (Steps 3 and 5 serverless execution) and closed @ `6f6e9ac` via runbook serverless subsections and `.dev/onboarding_cluster_submit.py`. Closure record: `signoffs/RB-DEFECT-T9-3.md`.

## Baseline interpretability label (2026-08-14, T11 / ESC-M4-1 Decision 4)

Harness baseline **`baseline_7174e0399e29` stands** — it is not withdrawn or recomputed. Per audit F-03 remediation (charter Amendment A5, ESC-M4-1 Decision 4), **12 of 48 scored intents** in the committed gold use bloated `filename_closure` positive sets (1,082–1,273 positives each; max recall@10 ≤ ~0.92%). **Mean recall on this baseline is not per-intent interpretable** for those 12 intents; readers must not treat aggregate metrics as meaningful per intent for that subset.

**Tracked label:** registry row `GAP-M4-1-clearsulting-bloated-filename-closure`. **Operator disposition:** `signoffs/T11-clearsulting-bloated-gold-disposition.md`. **Runbook:** Step 6 per-company baseline promotion policy caveat (bloated-gold baseline label).
