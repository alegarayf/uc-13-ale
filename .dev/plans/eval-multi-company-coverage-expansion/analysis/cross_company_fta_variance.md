# Cross-company FTA variance — ingest vs model

**Plan:** eval-multi-company-coverage-expansion · **T7 report (4)** · **T6 refresh (housekeeping)**  
**Generated:** 2026-08-18 (read-only SQL + Chip B citations; no cluster runs) · **Updated:** 2026-08-19 post-T6

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
| `.dev/plans/eval-multi-company-coverage-expansion/signoffs/T6-gkf-spg-retrieval.md` | GKF/SPG retrieval baselines + ingest (T6 retry 3) |

## Confidence tier legend

| Tier | Meaning in this table |
|------|----------------------|
| **Ratified floor** | Elder Care FTA 16/18 in `g1_score_all_agents.py` BASELINES — structural gate, multiple linked run_ids |
| **Chip B informational** | Single DAG e2e golden-checklist score; **not** ratified G1 floor (`BASELINES` is `None` for Clearsulting/GKF/SPG per plan D3) |
| **T6 retrieval baseline** | Harness baseline landed at T6 retry 3 — informational only; G1 floors not ratified; FTA checklist scores unchanged from Chip B |

Do **not** treat informational scores as equivalent-confidence to Elder Care ratified floors.

## Variance table

| Company | FTA G1 score | Confidence | Chunks | File types | Retrieval baseline | Primary confound | Model-gap signal |
|---------|-------------|------------|--------|------------|-------------------|------------------|------------------|
| **Elder Care** | **16/18** | Ratified floor | 55,812 | 4 | `baseline_acf58bcc4968` (trust epoch) | Reference healthcare corpus | Baseline — field 9 OPEX basis known issue |
| **Clearsulting** | **17/18** (Chip B) / **16/18** (e2e linkage) | Informational | 2,417 | 2 | `baseline_7174e0399e29` (12 bloated intents) | **Corpus thinness** (2 file types; 0 LEGAL docs); consulting doc mix | Score **above** Elder Care on checklist despite thin corpus — likely **doc-type alignment** with FTA rubric, not retrieval quality |
| **SPG** | **8.5/18** (Chip B only; **post-ingest gate checklist 2026-08-19**) | Chip B informational | 43,602+ | 2 | `baseline_0ec50347353a` (T6; 20 bloated intents) | Ingest **closed 1.0** (363/363); SpreadsheetML `.xls` fix landed 2026-08-19 — **8.5/18 reflects pre-rerun Chip B row**; FTA re-run pending | Low checklist on thin FTA fields — re-score after post-ingest FTA pipeline run |
| **GKF** | **13.5/18** (Chip B only) | Chip B informational | 3,107 | 2 | `baseline_4e098a2a2252` (T6; 26 bloated intents) | Small corpus, stale profiler rows (playbook §2.1); 5× legal `corpus_thin` exemptions | Mid-pack informational — corpus thinness + **stale analysis** confound |

### E2E linkage detail (warehouse)

| company_name | run_id | e2e_agent_id | score |
|--------------|--------|--------------|-------|
| Elder Care | `e3956dfb482f48dd97004bd130cc8f7f` | fta | 16/18 |
| Clearsulting | `d5e782836d5b4acb841ee960e49ad86a` | fta | **16/18** |
| SPG | — | — | **not in T6 scope** — retrieval baseline only (`baseline_0ec50347353a`); no `ops.e2e_linkage` row scored at T6 |
| GKF | — | — | **not in T6 scope** — retrieval baseline only (`baseline_4e098a2a2252`); no `ops.e2e_linkage` row scored at T6 |

Chip B OPEN_ITEMS cites Clearsulting **17/18** from a separate scoring pass (`.dev/hector_merge_e2e_run_ids.json` batch). Treat **16/18 linkage vs 17/18 Chip B** as scoring-pass variance, not a contradiction — both informational.

### Clearsulting retrieval vs FTA checklist disconnect

Ex-bloat harness (`baseline_7174e0399e29`, see report 1): mean `recall@10` **0.050** on 36 evaluated intents; only `kpi.retrieve_bill_rates_and_margins` (0.875) strong. Yet FTA checklist scores 16–17/18.

**Interpretation:** FTA golden checklist measures **agent output structure** on latest `analysis.financial_trends` row, largely **downstream of retrieval**. Clearsulting FTA success is **not** evidence of retrieval health — confound is **corpus suitability for FTA fields**, not merge-rank quality.

### SPG 8.5/18 — ingest before re-run

| Signal | Value | Implication |
|--------|-------|-------------|
| Chunks | 43,602+ (2nd largest) | Not a zero-corpus failure |
| Ingest completeness | **1.0000** (363/363 post-T8) | **Closed** — was 0.9863 (359/364); SpreadsheetML `.xls` + projection model re-ingested |
| File types | 2 | Low diversity — financial vs legal mix unknown |
| FTA analysis row | Chip B `2026-07-30` (pre-ingest-fix corpus) | Golden checklist **8.5/18** scored post-ingest gate; post-ingest FTA re-run pending |
| T6 gold bootstrap | 48/57 ready/partial | 9 bootstrap_failed (fta q1_financial_statements ×3, profiler ×6) |
| T6 harness baseline | `baseline_0ec50347353a` | Informational retrieval attestation only |

**Sequencing (updated 2026-08-19):** Ingest gap **closed** (T8). FTA golden checklist scored **8.5/18** on Chip B row after gate — **do not** attribute to model until post-ingest FTA re-run completes.

## Decision matrix (operator)

| If… | Then likely… | Next action |
|-----|--------------|-------------|
| SPG missing FINANCIAL statement filenames in ingest | **Ingest / corpus gap** | Expand SharePoint ingest; re-run FTA |
| SPG corpus rich but harness recall low (post-T6) | **Model / retrieval gap** | Ablation on worst FTA intents |
| Clearsulting FTA high but harness recall low | **Checklist ≠ retrieval** (expected) | Do not use Clearsulting FTA to gate retrieval promotion |
| Elder Care 16/18 stable across run_ids | **Ratified reference** | Compare new companies against checklist **and** harness |

## Onboarding context (framing only)

Per `eval/program/onboarding_queue.yaml`: Clearsulting is **W1** (second scored company target); GKF/SPG are **W2** retrieval+baseline wave — **T6 complete** for both. Inventory ranks GKF/Clearsulting ingest completeness at 1.0 vs SPG/Elder Care ~0.98 — FTA variance does **not** correlate with ingest rank alone.
