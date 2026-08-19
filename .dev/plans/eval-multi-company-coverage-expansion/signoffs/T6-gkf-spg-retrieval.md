# T6 signoff — GKF/SPG retrieval onboarding

**Plan:** eval-multi-company-coverage-expansion · **Packet:** T6  
**Disposition:** COMPLETE (retry 3) · **Date:** 2026-08-19  
**Operator:** Cursor executor (composer-2.5-fast)

## Scope

Onboarding-runbook steps 1–5 (ingest preflight → gold bootstrap → exemptions → harness baseline) for **GKF** and **SPG** on catalog `uc13_ale`. Informational retrieval baselines only — **G1 floors not ratified** (deferred operator decision per GAP-102-per-company-g1-floors).

## Bootstrap unblock (retry 3)

Attempt 2 HALT on Excel tab ambiguity (`Revenue` vs `Revenue Cash Proof`) fixed in `eval/retrieval/gold/bootstrap.py`:

1. **Exact-tab preference** — `_tabs_matching_excel_candidate` returns exact pool match before prefix matches.
2. **Section suffix strip** — `_excel_tab_candidate_from_location` strips `, Section:` and `/ Section:` before tab resolution (SPG `SUMMARY-Bonus / Section: Summary`).

Hermetic tests: `test_excel_tab_exact_match_preferred_over_prefix`, `test_excel_location_form_iii_slash_section_suffix`.

## GKF

| Step | Result | Evidence |
|------|--------|----------|
| 1 Registry / queue | W2 priority per `onboarding_queue.yaml` | rank_score 1.0 |
| 2 Ingest preflight | PASS completeness **1.0000** (41/41) | `python -m eval.retrieval.ingest_preflight --company GKF` |
| 3 Gold bootstrap | **48/57** ready/partial | cluster `675267203645809` → `eval/retrieval/gold_labels/gkf.yaml` snapshot `uc13_ale:3107:2026-08-19` |
| 4 Exemptions | 5× legal_register `corpus_thin` (legal_doc_count=4) | `eval/program/eval_exemptions.yaml` |
| 5 Harness baseline | SUCCESS | **`baseline_4e098a2a2252`** (cluster `351938197046482`, `--gold-path eval/retrieval/gold_labels/gkf.yaml`) |

**Bootstrap_failed (9):** cqa.retrieve_account_size, cqa.retrieve_contract_terms, cqa.retrieve_customer_concentration, kpi.retrieve_kpi_dashboard, legal.* (5 — exempted), plus harness skips these.

**Bloated gold (filename_closure >500 positives):** 26 intents (max 1991). Not opened in `eval_debt.yaml` — HWM already 13/14 (Clearsulting bloated rows).

## SPG

**Borderline ingest (documented before score interpretation):** preflight completeness **0.9863** (359/364) — treat agent/retrieval scores as provisional until ingest gap closed.

| Step | Result | Evidence |
|------|--------|----------|
| 1 Registry / queue | W2, rank below GKF due to ingest | `onboarding_queue.yaml` |
| 2 Ingest preflight | **Borderline 0.9863** | noted above |
| 3 Gold bootstrap | **48/57** ready/partial | cluster `554237868108774` → `eval/retrieval/gold_labels/spg.yaml` snapshot `uc13_ale:43602:2026-08-19` |
| 4 Exemptions | none required (legal.* bootstrapped; 181 LEGAL-classified docs) | — |
| 5 Harness baseline | SUCCESS | **`baseline_0ec50347353a`** (cluster `1062540922662656`, `--gold-path eval/retrieval/gold_labels/spg.yaml`) |

**Bootstrap_failed (9):** fta.{ebitda,opex,revenue}.q1_financial_statements (3), profiler.{banked_vs_nonbanked,business_description,deal_type,industry_overlay,revenue_model,vertical_subsector} (6).

**Bloated gold:** 20 intents (max 5750). Not opened in eval_debt — HWM guard.

## Kill-criterion evidence

- `--gold-path` passed explicitly for both harness runs (non–Elder Care).
- SPG borderline ingest documented above before baseline interpretation.

## Prior HALT runs (superseded)

| Company | Attempt | run_id | Reason |
|---------|---------|--------|--------|
| GKF | 1 | 136947278578356 | KPI claim-map gap (fixed retry 1 `d1e0e8a`) |
| SPG | 1 | 345260152779304 | KPI claim-map gap (fixed retry 1) |
| GKF/SPG | 2 | 431220525137269 (GKF) | Excel tab ambiguity (fixed retry 3) |

## Notes

- G1 floors remain unset for GKF/SPG (`BASELINES` None in `.dev/g1_score_all_agents.py`) — separate operator ratification.
- Adversarial gap covered: hermetic exact-tab + slash-section tests; warehouse falsifiers = harness run_ids above.
