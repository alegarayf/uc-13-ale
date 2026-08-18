# Registry hygiene — dangling `OPEN_ITEMS.md` source_refs (Flag 8)

**Plan:** eval-multi-company-coverage-expansion · **Subtask:** T8 · **Date:** 2026-08-18  
**Registry row:** `HYGIENE-open-items-md-dangling-source-refs`

## Finding

At execution time, workspace `Glob **/OPEN_ITEMS.md` returned **zero tracked matches**; `git ls-files '**/OPEN_ITEMS.md'` is likewise empty. A **gitignored** local copy exists at repo root (`/OPEN_ITEMS.md`, listed in `.gitignore` line 235, last modified 2026-08-10) but is **not part of the tracked tree** — registry `source_refs` still do not resolve for other clones, CI, or auditors.

Despite this, **49** rows in `eval/program/registry.yaml` cite `OPEN_ITEMS.md#…` anchors in `source_refs`.

The eval program spec (§9) states markdown trackers such as OPEN_ITEMS are **never canonical**; the canonical hub is `eval/program/registry.yaml`. During M0 canon hygiene, open-item narrative was consolidated into `.dev/pending/eval-consolidation-open-items.md`, but registry `source_refs` were not repointed to that replacement path (or to milestone signoff artifacts that now ground closed rows).

This document records the hygiene gap. It does **not** change `disposition` or `status` on any affected row — those statuses reflect program truth independent of the broken citation.

## Affected rows (complete inventory)

| ID | Title | Disposition | Stage | Status | Only `OPEN_ITEMS.md` refs? |
|----|-------|-------------|-------|--------|----------------------------|
| A-03 | Agent depth uneven (A-03) | staged | S1 | pending | yes |
| A-07 | Excel cell-level citations (A-07) | staged | S1 | pending | yes |
| A-09 | Clearsulting KPI overlay conflict (A-09) | staged | S1 | pending | yes |
| M-02 | M-02 Genie chatbot product fate | staged | S1 | pending | yes |
| NEW-1 | phv4 NEW-1 | staged | S1 | pending | yes |
| O-11 | O-11 / GKF–SPG fallback re-verify | staged | S0 | closed | no |
| O-14.13 | O-14.13 | staged | S1 | pending | yes |
| O-14.3 | O-14.3 — 6 FTA `bootstrap_failed` rows | staged | S0 | closed | no |
| OI-agent-quality-backlog-clearsulting-stakeholder-narrative | Clearsulting stakeholder narrative | staged | S2 | pending | yes |
| OI-data-ingest-quality-cell-8c-never-in-smoke-path | Cell 8c never in smoke path | staged | S3 | pending | yes |
| OI-data-ingest-quality-elder-care-ingest-gap | Elder Care ingest gap | staged | S3 | pending | no |
| OI-data-ingest-quality-incremental-parser-status-table | Incremental parser / status table | staged | S3 | pending | yes |
| OI-data-ingest-quality-indexsyncerror-job-exit-behavior | IndexSyncError job exit behavior | staged | S3 | pending | yes |
| OI-data-ingest-quality-spg-ingest-borderline | SPG ingest borderline | staged | S3 | pending | yes |
| OI-eval-harness-elder-care-slice-json-refresh-trigger | `elder_care_slice.json` refresh trigger | staged | S1 | closed | no |
| OI-eval-harness-evaluate-promotion-clearsulting-gkf-spg | `evaluate_promotion` — Clearsulting / GKF / SPG | staged | S1 | pending | yes |
| OI-eval-harness-evaluate-promotion-elder-care-post-fix-full-refresh | `evaluate_promotion` — Elder Care post-fix full refresh | staged | S0 | closed | no |
| OI-eval-harness-fta-rubric-eval-fta | FTA rubric → `eval/FTA/` | staged | S1 | closed | no |
| OI-eval-harness-legal-litigation-chunk-id-diff-debug | `legal.litigation` chunk_id diff debug | staged | S1 | pending | yes |
| OI-eval-harness-m-phv4-readme-t2-gate | M-PHV4 README T2 gate | staged | S0 | closed | yes |
| OI-eval-harness-phase-c-multi-company-gold-yaml | Phase C — multi-company gold YAML | staged | S1 | in_progress | no |
| OI-eval-harness-profiler-re-run-clearsulting-gkf-spg | Profiler re-run — Clearsulting / GKF / SPG | staged | S1 | pending | yes |
| OI-housekeeping-do-today-chip-a-plan-status-auditor-handoff | Chip A plan status + auditor handoff | staged | S0 | pending | yes |
| OI-housekeeping-do-today-commit-gold-guardrails | Commit gold guardrails | staged | S0 | closed | yes |
| OI-housekeeping-do-today-doc-sync-stale-reality | Doc sync (stale → reality) | staged | S0 | closed | yes |
| OI-housekeeping-do-today-runbook-g6-sha | Runbook G6 SHA | staged | S0 | closed | yes |
| OI-housekeeping-do-today-t2-working-note-fix | T2 working note fix | staged | S0 | pending | yes |
| OI-merge-gates-cqa-cosmetic | CQA cosmetic | staged | S1 | pending | yes |
| OI-merge-gates-g2-g4-formal-sign-off | G2–G4 formal sign-off | staged | S0 | closed | no |
| OI-merge-gates-g6-gate-file-note-stale | G6 gate file note stale | staged | S0 | closed | yes |
| OI-merge-gates-legal-dedupe-hardening | Legal dedupe hardening | staged | S1 | pending | yes |
| OI-orchestrator-charter-product-charter-m3-gate-condition-halt-1-pager-flow | Charter M3 — gate/condition + halt → 1-pager flow | staged | S1 | pending | yes |
| OI-orchestrator-charter-product-dataset-pre-training-exploration | Dataset / pre-training exploration | staged | S1 | pending | yes |
| OI-orchestrator-charter-product-exec-summary-experiments | Exec-summary experiments | staged | S1 | pending | yes |
| OI-orchestrator-charter-product-merge-scout-decisions-q1-q6 | MERGE_SCOUT decisions Q1–Q6 | staged | S1 | pending | yes |
| OI-orchestrator-charter-product-route-chunks-cleanup | `route_chunks` cleanup | staged | S1 | pending | yes |
| OI-runbook-program-milestones-cell-7-full-parser-rebuild | Cell 7 full parser rebuild | staged | S1 | pending | yes |
| OI-runbook-program-milestones-m-phv4-deferred | M-PHV4 deferred | staged | S1 | pending | yes |
| OI-runbook-program-milestones-phase-7-data-room-completeness-scorecard | Phase 7 — data room completeness scorecard | staged | S3 | pending | yes |
| OI-runbook-program-milestones-phase-9-hector-merge | Phase 9 — Hector merge | staged | S3 | pending | yes |
| OI-runbook-program-milestones-t9-docx-on-serverless | T9 `.docx` on serverless | staged | S1 | pending | yes |
| P-07 | P-07 Workflow YAML Llama 70B vs notebook Sonnet | staged | S1 | pending | yes |
| Q-E03 | Multi-company harness gold matrix (Q-E03) | staged | S1 | pending | yes |
| Q-R03 | Q-R03 shared index topology | staged | S1 | pending | yes |
| R-06 | R-06 SQL bound parameters | staged | S1 | pending | yes |
| R-07 | R-07 driver-bound two-hop retrieval | staged | S1 | pending | yes |
| R-08 | Join / hydration drift (R-08) | staged | S1 | pending | yes |
| R-2 | Legal R-2 (t4c variance) | staged | S1 | pending | yes |
| S-05 | S-05 / M-04 — Garden UI + prod auth | staged | S1 | pending | yes |

**Summary:** 49 rows cite `OPEN_ITEMS.md`; 41 cite it as their **only** `source_refs` entry; 8 rows also cite `.dev/eval_state_of_affairs_2026-08-03.md` or other tracked paths.

## Operator recommendations

Choose one (or a hybrid):

1. **Reconstruct** — Commit a tracked `OPEN_ITEMS.md` (or repoint all `source_refs` to `.dev/pending/eval-consolidation-open-items.md` with stable anchors) so citations resolve again.
2. **Retire citations** — For each row, replace dangling `OPEN_ITEMS.md` refs with the signoff / audit / pending-ledger path that now grounds its disposition (especially for `status: closed` rows still pointing only at the missing file).

Closing `HYGIENE-open-items-md-dangling-source-refs` is appropriate once citations resolve repo-wide or an operator records a formal retirement decision.

## §4b — Phase 7 scorecard program note (separate from Flag 8)

**Registry ID:** `OI-runbook-program-milestones-phase-7-data-room-completeness-scorecard`  
**Current state:** `staged` / `S3` / `pending` (unchanged by this subtask)

The **eval-multi-company-coverage-expansion** program (M5) explicitly treats the Phase 7 data-room completeness scorecard as **design-only**. This pass does not attempt the production UI scorecard surface; an analysis script or design artifact may suffice per program rationale §2 non-goals. The row's `pending` status reflects real product incompleteness, not the dangling-reference problem above — do **not** mark it `closed` under M5 scope.

---

*Verification:* `git ls-files '**/OPEN_ITEMS.md'` → empty (2026-08-18). Gitignored local `/OPEN_ITEMS.md` present but not tracked. Replacement narrative: `.dev/pending/eval-consolidation-open-items.md`.
