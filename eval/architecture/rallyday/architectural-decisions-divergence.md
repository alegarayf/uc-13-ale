# Architectural decisions — execution-time divergence log

Runtime counterpart to program rationale. Entries record accepted intent drift at milestone audit.

---

## M-RE1 — 2026-07-02

**Spec intent:** Charter G4 and M-RE1 runnable checkpoint (5) require cluster baseline `harness_status: complete` in both `uc13.ops` and committed `eval/retrieval/reports/{run_id}.json`.

**Execution decision:** G4 closed on operator-attested Delta state (`baseline_f0f4f68ac7af`); committed JSON export retained with `harness_status: incomplete` because export predates cluster `mark_complete`.

**Rationale:** Plan §8.4 accepted waiver; auditor finding F-05; operator verification on cluster is authoritative for ops gate.

**Status:** needs-ph1-review

---

## M-PHV2 — 2026-07-08

**Spec intent:** Charter item 18 "scorecard index committed at HEAD" plus T8's exit-gate-checklist closure procedure and INDEX.md Notes fields were expected to be fully self-consistent and current at T10 closeout.

**Execution decision:** Accepted as non-blocking, disclosed drift: (1) exit-gate-checklist.md's own closure-procedure step 3 and bottom self-pin table remain stale post-Gate-4 (say "remaining"/"partial" though already landed); (2) INDEX.md's two Elder Care FTA/Legal row Notes still read "Flag 6 fresh re-run not confirmed" though Flag 6 resolved "yes"; (3) three files under .dev/scorecards/ (_tmp_fta_legal_export.json, scorecard_elder_care_vs_clearsulting_sync.md, scorecard copy.md) sit outside any subtask's declared Files-to-touch.

**Rationale:** None of these affect Gate 1-4 correctness or any §2 contract; plan.md v1.2 §8.4 already disclosed items (1)-(3) accurately (audit `.dev/audits/2026-07-08-uc13-m-phv2-validation-expansion.md` independently confirmed 3 of its 4 stray-file claims; corrected the 4th — prereqs.md — as a separate, non-accepted finding F4 in that audit, since prereqs.md is actually load-bearing for T2/T9's own outputs, not unrelated). Cosmetic documentation lag, not a scope or correctness violation. Note: the same audit found a critical, non-accepted finding (F1 — undeclared production-code edit to `test_pipeline.ipynb` in T10's commit) that is *not* logged here as accepted drift; it remains an open condition of that audit's pass-with-conditions verdict.

**Status:** accepted-non-blocking
