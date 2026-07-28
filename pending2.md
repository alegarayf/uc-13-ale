## Post-merge closeout — DONE 2026-07-28

- **BMA scored validation:** Closed — isolated + full e2e **7/7**; orchestrator section 36k chars, no R-3 fallback; `evaluate_promotion` → `promoted` (scorecard `2026-07-28`).
- **Full parallel e2e:** DAG **9/0/0** (`run_id=827597669988464`). T9 `.docx` export failed (`python-docx` missing on serverless); `.md` memo + exec-summary renders OK.
- **Profiler:** Re-run **7/7** (`2026-07-28 22:15`).
- **Legal R-2:** Deferred — post-fix e2e **7/11** (LLM variance); dedupe hardening → backlog ticket.

---

## Still open (out of this pass)

- G6: Bootstrap the 8 labels on `uc13_ale` (`elder_care.yaml`)
- 4-company e2e (Clearsulting, GKF, SPG)
- G5 VDR gate
- FTA memo generator: same `flags` parse bug as BMA R-3 (G1 still 16.5/18)
- phv4 NEW-1/NEW-2 (insurance filter + registry hash)
