# Cross-company FTA variance — ingest vs model

**Plan:** eval-multi-company-coverage-expansion · **T7 report (4)**  
**Generated:** 2026-08-18 (read-only SQL + Chip B citations; no cluster runs)

## Question

**SPG 8.5/18 vs Clearsulting 17/18 vs Elder Care 16/18** — corpus/thinness confound or model gap?

## Evidence refs

| Ref | Role |
|-----|------|
| `OPEN_ITEMS.md` §Score FTA on more companies | Chip B informational scores: Clearsulting **17/18**, GKF **13.5/18**, SPG **8.5/18** |
| `eval/eval_program_playbook.md` §2.1 | Company matrix; confidence tier labels |
| `eval/program/onboarding_queue.yaml` | Ingest rank framing (T5 — not duplicated here) |
| `uc13_ale.ops.retrieval_harness_runs` | E2E linkage scores |
| `uc13_ale.ingestion.chunks` | Corpus size / file-type diversity |
| `.dev/hector_merge_e2e_run_ids.json` | Chip B parallel DAG run_ids |

## Confidence tier legend

| Tier | Meaning in this table |
|------|----------------------|
| **Ratified floor** | Elder Care FTA 16/18 in `g1_score_all_agents.py` BASELINES — structural gate, multiple linked run_ids |
| **Chip B informational** | Single DAG e2e golden-checklist score; **not** ratified G1 floor (`BASELINES` is `None` for Clearsulting/GKF/SPG per plan D3) |
| **pending (T6)** | Retrieval harness baseline not yet landed for GKF/SPG ex-bloat compare |

Do **not** treat informational scores as equivalent-confidence to Elder Care ratified floors.

## Variance table

| Company | FTA G1 score | Confidence | Chunks | File types | Retrieval baseline | Primary confound | Model-gap signal |
|---------|-------------|------------|--------|------------|-------------------|------------------|------------------|
| **Elder Care** | **16/18** | Ratified floor | 55,812 | 4 | `baseline_acf58bcc4968` (trust epoch) | Reference healthcare corpus | Baseline — field 9 OPEX basis known issue |
| **Clearsulting** | **17/18** (Chip B) / **16/18** (e2e linkage) | Informational | 2,417 | 2 | `baseline_7174e0399e29` (12 bloated intents) | **Corpus thinness** (2 file types; 0 LEGAL docs); consulting doc mix | Score **above** Elder Care on checklist despite thin corpus — likely **doc-type alignment** with FTA rubric, not retrieval quality |
| **SPG** | **8.5/18** | Informational | 43,602 | 2 | **pending (T6)** | Large chunk count but **ingest borderline** (98.6% completeness per onboarding_queue); sparse file-type diversity | Low checklist ⇒ investigate **corpus content** (missing financial statements?) before blaming retrieval |
| **GKF** | **13.5/18** | Informational | 3,107 | 2 | **pending (T6)** | Small corpus, stale profiler rows (playbook §2.1) | Mid-pack informational — corpus thinness + **stale analysis** confound |

### E2E linkage detail (warehouse)

| company_name | run_id | e2e_agent_id | score |
|--------------|--------|--------------|-------|
| Elder Care | `e3956dfb482f48dd97004bd130cc8f7f` | fta | 16/18 |
| Clearsulting | `d5e782836d5b4acb841ee960e49ad86a` | fta | **16/18** |
| SPG | — | — | **pending (T6)** — no harness baseline row |
| GKF | — | — | **pending (T6)** — no harness baseline row |

Chip B OPEN_ITEMS cites Clearsulting **17/18** from a separate scoring pass (`.dev/hector_merge_e2e_run_ids.json` batch). Treat **16/18 linkage vs 17/18 Chip B** as scoring-pass variance, not a contradiction — both informational.

### Clearsulting retrieval vs FTA checklist disconnect

Ex-bloat harness (`baseline_7174e0399e29`, see report 1): mean `recall@10` **0.050** on 36 evaluated intents; only `kpi.retrieve_bill_rates_and_margins` (0.875) strong. Yet FTA checklist scores 16–17/18.

**Interpretation:** FTA golden checklist measures **agent output structure** on latest `analysis.financial_trends` row, largely **downstream of retrieval**. Clearsulting FTA success is **not** evidence of retrieval health — confound is **corpus suitability for FTA fields**, not merge-rank quality.

### SPG 8.5/18 — ingest before re-run

| Signal | Value | Implication |
|--------|-------|-------------|
| Chunks | 43,602 (2nd largest) | Not a zero-corpus failure |
| Ingest completeness | 98.6% (`onboarding_queue.yaml`) | Borderline — missing doc types likely |
| File types | 2 | Low diversity — financial vs legal mix unknown |
| FTA analysis row | 1 row present | Agent ran; checklist partial |

**Recommended sequencing:** Complete ingest preflight + gold bootstrap (T6 baselines) **before** attributing 8.5/18 to model regression. SPG/GKF harness cells remain **`pending (T6)`** until sibling subtask lands baselines.

## Decision matrix (operator)

| If… | Then likely… | Next action |
|-----|--------------|-------------|
| SPG missing FINANCIAL statement filenames in ingest | **Ingest / corpus gap** | Expand SharePoint ingest; re-run FTA |
| SPG corpus rich but harness recall low (post-T6) | **Model / retrieval gap** | Ablation on worst FTA intents |
| Clearsulting FTA high but harness recall low | **Checklist ≠ retrieval** (expected) | Do not use Clearsulting FTA to gate retrieval promotion |
| Elder Care 16/18 stable across run_ids | **Ratified reference** | Compare new companies against checklist **and** harness |

## Onboarding context (framing only)

Per `eval/program/onboarding_queue.yaml`: Clearsulting is **W1** (second scored company target); GKF/SPG are **W2** retrieval+baseline wave. Inventory ranks GKF/Clearsulting ingest completeness at 1.0 vs SPG/Elder Care ~0.98 — FTA variance does **not** correlate with ingest rank alone.
