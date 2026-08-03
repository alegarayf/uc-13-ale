## Post-merge closeout — DONE 2026-07-28

- **BMA scored validation:** Closed — isolated + full e2e **7/7**; orchestrator section 36k chars, no R-3 fallback; `evaluate_promotion` → `promoted` (scorecard `2026-07-28`).
- **Full parallel e2e:** DAG **9/0/0** (`run_id=827597669988464`). T9 `.docx` export failed (`python-docx` missing on serverless); `.md` memo + exec-summary renders OK.
- **Profiler:** Re-run **7/7** (`2026-07-28 22:15`).
- **Legal R-2:** Deferred — post-fix e2e **7/11** (LLM variance); dedupe hardening → backlog ticket.

---

## Chip A G6 gold magnitude remediation — DONE 2026-07-30

Audit F2 (undisclosed T2 rebootstrap magnitude shift) — Phases 1–3 closed:

- **Disclosure:** `harness-baseline-2026-07-30.md` §Gold magnitude shift; T2 decision log; handoff §11; D-14.5 / phv4 NEW-2 accepted (`.dev/attestations/chip-a-g6-d14-5-baseline-sign-off.md`)
- **Guardrails:** `.dev/scripts/diff_gold_labels.py`, `eval/retrieval/fixtures/gold_positive_counts.yaml`, T2 magnitude kill criterion in plan/packet
- **Validation:** Databricks spot-check PASS on 5 intents (`.dev/scripts/spot_check_gold_citations.py`) — accepted precision upgrade, no yaml revert

### Still pending (this thread)

- [ ] **Plan housekeeping (audit F1):** `.dev/plans/chip-a-g6-gold-bootstrap/plan.md` — update Status banner (T1–T8 landed) and §8 Auditor handoff (still reads "not executed")
- [ ] **T2 working note (audit F3):** `.dev/plans/chip-a-g6-gold-bootstrap/T2-cluster-bootstrap.md` — fix wrong prior `bootstrap_failed` status for `fta.opex.q3_projected_financials` and `legal.contracts_vendors_platform` (were already `ready` pre-T2)
- [ ] **Runbook SHA (audit F4):** `my_runbook.md` G6 T7 row cites `dc2ce284` (T5) — should be `2457cf9` (T7)
- [ ] **Commit tracked artifacts:** `eval/retrieval/fixtures/gold_positive_counts.yaml`, `eval/retrieval/tests/test_gold_bootstrap.py` manifest test, scripts under `.dev/scripts/` (if not already committed)

---

## Still open (out of this pass)

- ~~G6: Bootstrap the 8 labels on `uc13_ale` (`elder_care.yaml`)~~ **DONE 2026-07-30** — 57 rows, `baseline_544eb3f2a0e2`, G6 PASS
- **Chip B:** 4-company e2e (Clearsulting, GKF, SPG) — post-merge agent validation
- G5 VDR gate
- FTA memo generator: same `flags` parse bug as BMA R-3 (G1 still 16.5/18)
- phv4 NEW-1 (insurance filter — `ec74042` untested for new behavior)
