# Eval consolidation program — pending / open-items checklist

**Generated:** 2026-08-13 · **Updated:** 2026-08-14 (M4 rev 2 intake)  
**Scope:** M0–M4 auditor handoffs (M3 = rev 5; M4 = rev 2, governing)  
**Charter:** `.dev/specs/eval-consolidation-program/eval_consolidation_program_milestone_charter.md` v0.1.4 (+ Amendments A3, A5)

**Status legend**

| Label | Meaning |
|-------|---------|
| **Open** | Action still owed; not dispositioned |
| **Half-open** | Gate waived / program record closed; substantive residual remains |
| **Deferred** | Explicitly accepted; fix-or-accept at operator discretion |
| **Closed** | Resolved or archival-only waiver |

## Quick open items

| P | ID | Milestone | Status | One-line |
|---|-----|-----------|--------|----------|
| 1 | ESC-T12-1 | M1 | Half-open | Bench `filename_closure` — Tier-3 spec §19/D4 note still OPEN |
| 2 | W-F-3 | M0 | **Closed** | `validate_row` §16 null-side conditionals + mutation tests — landed via T2; see M0 table validation |
| 3 | R-1 | M3 | **Closed** | Stale self-hash quotes — annotated pointer-only via T3; see M3 table validation |
| 4 | R-2 | M3 | **Closed** | Plan §8.4 rows stale — corrected via T3; see M3 table validation |
| 5 | UGA-1 | M3→M4 | Open | Upstream grounding audit — M4 entry-gate item |
| 6 | F-14 | M3 | Half-open | No rung-3 `assessment_metrics` rows (named waiver) |
| 7 | ESC-T2-3 residuals | M2 | Half-open | Disposition closed; M2 figures not upgrade evidence |
| 8 | F-11 | M1 | **Closed** | M1 plan §8 tree SHA — annotated via T5; see M1 table validation |
| 9 | F-21 | M2 | **Closed** | Wrong test names cited in M2 plan — verified already correct via T6; ledger was stale |
| 10 | GAP-104 + OI×2 | M0 | Open | Three registry rows still `pending` |
| 11 | Product / m3_backlog #3 | M3 | Open | Broken vision-extraction chunk mapping (product track) |
| 12 | F-2-01 + F-15 | M4 | **Closed** | Folded-slug enforcement on `load_gold_exclusions` + `default_gold_path` library path — landed via T1; see M4 table validation |
| 13 | F-2-02 | M4 | **Closed** | T11/T12/T13 changelog + Files-to-touch record drift (merge archaeology) — record half corrected via T4; see M4 table validation |
| 14 | §8.4.3 T3 | M4 | **Closed** | Unnormalizable `--company-name` on `harness_cli run` (incl. `--gold-path` path @ `:121`) — landed via T1; see M4 table validation |
| 15 | M4-F-14 | M4 | Half-open | M4 context map stale @ `3126c2b` — waived rev 2; treat-as-prediction |

*Deferred items (F-9, F-10, F-16, F-20, M4 observations, coverage gaps, etc.) are in the milestone sections below.*

---

## Program gate summary

| Milestone | Audit (governing rev) | Verdict | `audit_status` | Blocks next gate? |
|-----------|----------------------|---------|----------------|-------------------|
| M0 | rev 2 | pass-with-conditions | accepted-with-waivers | No (M1 entered) |
| M1 | rev 2 | pass-with-conditions | accepted-with-waivers | No (M2 entered) |
| M2 | rev 2 | pass-with-conditions | accepted-with-waivers | No (M3 entered) |
| M3 | **rev 5** | pass-with-conditions | accepted-with-waivers | **No — M4 entry satisfied** |
| M4 | **rev 2** | pass-with-conditions | accepted-with-waivers | **No — M5 entry satisfied** |

---

## M0 — Canon & Hygiene

**Audit:** `.dev/audits/eval-consolidation/M0/2026-08-10-eval-consolidation-m0-audit.md` (rev 2)

| ID | Item | Source | Status | Validation (2026-08-13) |
|----|------|--------|--------|-------------------------|
| W-F-3 / F-3 | Tighten `validate_row` §16 null-side conditionals (`method` null outside probe-backed ingest; `rung` on non-content layers) + mutation tests. Condition: before S1 rung-bearing content. | M0 §8 waiver | **Closed** | Landed via T2 (`eval-consolidation-debt-cleanup`): two new raise branches (`method must be null outside ingest_completeness`, `rung must be null outside content_correctness`) mirroring the existing `content_surface` pattern; 4 hermetic tests (`test_validate_row_rejects_method_outside_ingest_completeness`, `test_validate_row_rejects_rung_outside_content_correctness_on_attested`, `test_validate_row_accepts_method_on_ingest_completeness`, `test_validate_row_accepts_rung_on_content_correctness`) plus 2 mutation-check observations (guard disabled → named test failed → restored). Independently re-verified: both guard raises present at `trust_statement.py:223,239`; named tests collected and pass. **[eval-consolidation-debt-cleanup T7, 2026-08-14]** |
| W-F-1 / F-1 | Pre-audit `audit_status: clean` in early `handoff.md` — archival only. | M0 waiver | **Closed** | Supersession banner + rev 2 audit record. |
| W-F-4 / F-4 | Context-map staleness (execution-inherent). | M0 waiver | **Closed (accepted)** | Informational; surfaces re-verified at audit time. |
| W-F-5 / F-5 | README absent from scout §File map. | M0 waiver | **Closed (accepted)** | Scout feedback only. |
| F-2 | Canary SELECT grant on `baseline_complete_companies`. | M0 major → resolved rev 2 | **Closed** | Grant re-applied; S-50 evidence addendum. |
| F-6 | Post-DDL grant re-verification protocol. | M0 → resolved rev 2 | **Closed** | Protocol note in S-50 addendum. |
| — | Standing caution: any `apply_ops_ddl` re-apply drops view-level grants — re-grant + `SHOW GRANTS`. | M0 handoff summary | **Deferred (standing)** | Operational runbook item, not a finding. |

### M0 registry pendings (handoff §11, not audit findings)

| Registry ID | Status |
|-------------|--------|
| `GAP-104-no-enhancement-gate-hash-c` | **Open** — still `pending` |
| `OI-housekeeping-do-today-chip-a-plan-status-auditor-handoff` | **Open** — still `pending` (partially superseded by real M0 audit) |
| `OI-housekeeping-do-today-t2-working-note-fix` | **Open** — still `pending` |

---

## M1 — Metric & Guardrail Hardening

**Audit:** `.dev/audits/eval-consolidation/M1/2026-08-11-eval-consolidation-m1-audit.md` (rev 2)

| ID | Item | Source | Status | Validation (2026-08-13) |
|----|------|--------|--------|-------------------------|
| W-1 / F-2 | **`kpi.retrieve_bench_and_capacity`** retained as `filename_closure` / ~2,925 positives (recall@10 ≤ 0.34%). Tier-3 spec note for §19/D4. | M1 waiver → `ESC-T12-1` | **Half-open** | Program side closed (T12, GAP-103 rationale). **`ESC-T12-1` still OPEN** — no spec §19/D4 amendment; gold still `filename_closure`. |
| F-9 bundle | Coverage gaps: packet-named resolution pytest, README↔CLI CI, registry↔ratification CI, g1 AST-only guard, `POSITIVE_FALLBACK_CHAIN` direct test. | M1 waiver | **Deferred** | Ledgered in plan §8.4; no evidence landed. |
| F-10 | Charter M1 block paraphrase drift (`retrieval_rubric_v0.1.md`, `runs`/`slice_metrics`, `trust_statement.py` absent from charter block). | M1 waiver | **Deferred** | Charter M1 checkpoint cell still paraphrases; routed to Tier-2 charter touch-up. |
| F-11 | Plan §8 handoff still cites tree SHA `ad25fea` (pre-T12–T14). | M1 waiver | **Closed** | Annotated via T5 (`eval-consolidation-debt-cleanup`): header's dangling "will be re-issued" promise resolved in place (T12/T14 landed, rev 2 graded, but M1's T13 left no tracked commit to re-anchor a fresh snapshot to); §8.1 Tree SHA row retains `ad25fea6ead980763d4a8e32cde19931e654be69` and is now explicitly labeled as the tree the Result row was measured at. No re-measurement performed (explicit non-goal). Independently re-verified: `ad25fea` still present at `plan.md:345`, labeled as measured tree. **[eval-consolidation-debt-cleanup T7, 2026-08-14]** |
| F-4, F-5 | Context-map / scout-incomplete feedback. | M1 rev 2 | **Closed (accepted)** | Non-blocking. |

---

## M2 — S2 pre-plan (Rung Selection & Calibration)

**Audit:** `.dev/audits/eval-consolidation/M2/2026-08-12-eval-consolidation-m2-audit.md` (rev 2)

| ID | Item | Source | Status | Validation (2026-08-13) |
|----|------|--------|--------|-------------------------|
| W-1 / F-4 | `exec_summary` sample majority baseline (0.93) > C5 verdict threshold (0.80) — cannot support rung upgrade. | M2 waiver → ESC-T2-3 item 1 | **Half-open** | **ESC-T2-3 Option A (caveat-and-carry) closed** via M3 P2 / registry CHK-27. Residual accepted; figures not upgrade evidence. |
| W-2 / F-5 | `fta_numeric` span half ~2-way (2 chunk_ids over N=30). | M2 waiver → ESC-T2-3 item 2 | **Half-open** | Same disposition as W-1. |
| W-3 / F-6 | `span_agreement: 0.0` confounded by undeclared BGE retrieval; pre-T9 run unrecoverable. | M2 waiver → ESC-T2-3 item 3 | **Half-open** | Instrument fixed at T9. **Run-of-record** CHK-26a caveat still live; post-M3 re-calibration gated. |
| F-11 | All `.dev/` plan artifacts on-disk-only (Option C). | M2 waiver | **Deferred (by design)** | Standing CI-provability gap; named in ESC-T2-3 item 3 sub-residual. |
| F-16 | Raw `chunk_id` SQL interpolation in `calibration.py`. | M2 waiver | **Deferred** | Still present; T9 decision log hygiene deferral. |
| F-19 | Plan §8.2 content-SHA chain partially stale post-T10. | M2 waiver | **Half-open → largely closed at M3** | M3 rev 5: 12/12 declared v5 hashes verify; residue is **prose citations** of hashes (see M3 R-1). |
| F-20 | C5 threshold tests pin intervals, not points (subtle re-pin 0.90→0.87 ships green). | M2 waiver | **Deferred** | `test_evaluate_thresholds_numeric_*` bracket intervals only. |
| F-21 | Plan cites wrong test names (`test_value_threshold_boundary_pin` vs landed names). | M2 waiver | **Closed — ledger was stale; no artifact edit required** | T6 (`eval-consolidation-debt-cleanup`) verified 2026-08-14 that both citation sites (`plan.md:138`, `:515`) already cite the correct landed names (`test_evaluate_thresholds_numeric_value_pass_and_fail`, `test_evaluate_thresholds_numeric_span_pass_and_fail`); content-SHA before==after proves a deliberate no-op. Independently re-verified: repo-wide search for the two stale names returns zero matches; correct names confirmed at `eval/content/tests/test_agreement.py:231,247`. **[eval-consolidation-debt-cleanup T7, 2026-08-14]** |

---

## M3 — S2 build (Verifiers, Judge Harness & Content Tier)

**Audit (governing):** `.dev/audits/eval-consolidation/M3/2026-08-13-eval-consolidation-m3-audit-rev5.md` (rev 5)

### Rev 5 — conditions / waivers (documentation-only; M4 gate satisfied)

| ID | Item | Source | Status | Validation (2026-08-13) |
|----|------|--------|--------|-------------------------|
| **R-1** | Stale self-hash **quotations**: `CHANGELOG.MD` R23 entry says `542daaf4…`; `r23-selfhash-evidence.md` Forward says `8a878904…`; binding row 0⁴ is `65bc48c4…` (guard PASS). Adopt OD-v5-1: only row 0⁴ prints the literal; others pointer-only. | M3 rev 5 §9–§10 | **Closed** | Annotated via T3 (`eval-consolidation-debt-cleanup`): the R23 `CHANGELOG.MD` line is retained verbatim (RH-1, historical record) with a pointer-only correction added under a new dated section; `r23-selfhash-evidence.md`'s Forward statement corrected pointer-only; plan §8.2 row 0⁴ re-derived and re-filled as the terminal edit. Independently re-verified: `python .dev/audits/eval-consolidation/M3/verify_plan_selfhash.py` → `STATUS: PASS`. **[eval-consolidation-debt-cleanup T7, 2026-08-14]** |
| **R-2** | §8.4.3 assumption 24 marked closed but false (v5 stale citations exist). §8.4.1 Q-6 row still `open (carried)` though worktree removed. | M3 rev 5 §9–§10 | **Closed** | Corrected via T3: §8.4.3 assumption 24 rationale corrected (names the two additional stale-value sites); §8.4.1 Q-6 and §8.4.5 sibling Q-6 rows flipped to `closed`, brought into agreement. Independently re-verified alongside R-1's `verify_plan_selfhash.py` PASS (same edit, same terminal re-fill). **[eval-consolidation-debt-cleanup T7, 2026-08-14]** |
| R-3 | R20 packet contradicts itself (non-goals forbid CHANGELOG vs Outputs require changelog). | M3 observation | **Closed (record)** | Packet-authoring signal; executor followed Outputs. |
| R-4 | `q6-worktree-cleanup-evidence.md` absent from §8.2 (v5) artifact chain. | M3 observation | **Deferred** | Record-only; sibling Q-5 file is chained. |
| R-5 | General-scoring test covers section-pattern term only; page-match, raw `source_location`, tie-break unexercised. | M3 observation | **Deferred** | Disclosed in §8.4.5; dominant term mutation-verified (Q-4 closed). |

### M3 rev 5 — coverage gaps (carried / disclosed)

| # | Gap | Status |
|---|-----|--------|
| 1 | No automated guard that prose self-hash citations stay aligned with row 0⁴ | **Open** (same family as R-1) |
| 2 | No hermetic pytest for `verify_plan_selfhash.py` | **Deferred** |
| 3 | `ChunkIndex.lookup` single-candidate no-score path (R16 deferral) | **Deferred** |
| 4 | No hermetic guard that `pytest.ini testpaths` includes `eval/content` (R18) | **Deferred** |
| 5 | No test for non-ISO-8601 `run_ts`; no rung-1 explicit falsifier on `fta_numeric` | **Deferred** |
| 6 | F-16 context-map stale (rev 1 → carried) | **Deferred (standing)** |

### M3 rev 4 → rev 5 — resolved (for archive)

All six rev-4 findings **Q-1…Q-6** closed at rev 5 (self-hash guard, R10 banner, R17 CHANGELOG byte-restore, general-scoring falsifier + mutation probe, collect/run arithmetic, worktree cleanup). **P-2** and **O-13** (clean tree) also closed.

### M3 — charter / prior-wave residuals (still relevant for M4)

| ID | Item | Source | Status | Validation |
|----|------|--------|--------|------------|
| F-14 (charter A3 / D5) | **`assessment_metrics`** carries no rung-3 spot-check metric rows although conditional fired. Named waiver — not GREEN. | Charter Amendment A3; M3 audit | **Half-open** | Operator attestation + warehouse runs exist; registry metric rows still absent. |
| ESC-T2-3 | Measure-validity (F-4/F-5/F-6) — caveat-and-carry. | M2 → M3 P2 | **Half-open** | Disposition **closed** (Option A); reuse of M2 figures for upgrade still forbidden. |
| UGA-1 | Upstream per-workstream grounding audit (`exec_summary` transitive grounding). | Operator attestation D6; M4 entry-gate item | **Open** | Prompt filed: `.dev/audits/eval-consolidation/M3/upstream-grounding-audit-prompt.md` |
| Product | Broken vision-extraction chunk family (`027ec667…`); m3_backlog #3. | Operator attestation | **Open (product track)** | Eval overrides scoped to run scoring only. |
| exec.claim.027 | No resolvable VDR chunk after R5 backfill; verdict `unsupported`. | Operator attestation | **Deferred (exception)** | Does not block attestation of remaining claims. |
| REG-CANON-1 | `sync_registry_mirror` test-module placement note. | M3 rev 5 charter cross-check | **Deferred** | Pending M4. |

---

## M4 — S3 Company Onboarding Runbook

**Audit (governing):** `.dev/audits/eval-consolidation/M4/2026-08-14-eval-consolidation-m4-onboarding-runbook-audit.md` (rev 2)

*Rev 1 remains on disk as `2026-08-14-eval-consolidation-m4-onboarding-runbook-audit.rev1.md`.*

**Plan:** `.dev/plans/eval-consolidation-m4-onboarding-runbook/plan.md` v1.6 · audit HEAD `c8a36fc` · suite **1201 / 1 skip / 0 fail** (1202 collected)

### Rev 2 — conditions / waivers (M5 gate satisfied)

| ID | Item | Source | Status | Validation (2026-08-14) |
|----|------|--------|--------|-------------------------|
| **F-2-01** | T13 contract bindings claim `PreconditionError` for a missing/**unfolded** `company_slug`; `load_gold_exclusions` silently returns `{}` for an unfolded display name (e.g. `"Elder Care"`). Same failure shape as rev-1 **F-15** on the new loader surface. Sole production caller folds first — library-path trap only. | M4 rev 2 §6, §9 cond. 1; waiver W1 | **Closed** | Landed via T1 (`eval-consolidation-debt-cleanup`): `require_folded_company_slug` added to `eval/retrieval/companies.py`, called from `load_gold_exclusions` and `default_gold_path` (covers `EvalHarness.__init__` transitively); raises `PreconditionError` (`company_slug must be canonical`) matching the T13 contract text. 8 tests incl. positive-preservation for an unregistered-but-folded slug. Paired with F-15. Independently re-verified: guard present at `companies.py:45`; named tests collected and pass. **[eval-consolidation-debt-cleanup T7, 2026-08-14]** |
| **F-2-02** | Packet Files-to-touch vs actual diff drift, disclosed but split across four artifacts: T11 edited `test_eval_debt.py` outside scope; T13 edited `test_eval_debt.py` + `test_gold_kpi_pdf_branch.py` outside scope; T11 Step 6 runbook sentence landed in **T12's** commit; T12 changelog says "Step 3 serverless only" against its own diff; T11 changelog claims Step 6 surface its commit lacks. End state correct; **record** inaccurate. | M4 rev 2 §6, §9 cond. 2; waiver W2 | **Closed** | Record half corrected via T4: T11/T12 changelog attribution and T11 decision-log deferral annotated with git-evidence-backed corrections (Step 6 hunk landed in commit `2ceb25d`, not T11's `0e86004`; signoff signed at `87e194e`). T13's separate `test_eval_debt.py` / `test_gold_kpi_pdf_branch.py` drift and packet Files-to-touch amendment are explicit non-goals of this plan — not addressed here. Independently re-verified: `git show 29c0c68` diff matches T4's reported before/after strings exactly. **[eval-consolidation-debt-cleanup T7, 2026-08-14]** |
| **F-15** | Unfolded display name reaching `default_gold_path` / `EvalHarness(company_slug=…)` resolves wrong path and fails late; CLI path safe. | M4 rev 1 → carried; §8.4.4; waiver W3 | **Closed** | Fixed together with F-2-01 via T1's single fold-enforcement patch (`require_folded_company_slug`), as this row's own Validation column anticipated. **[eval-consolidation-debt-cleanup T7, 2026-08-14]** |
| **M4-F-14** | Context map @ planning SHA `3126c2b` vs audit HEAD `c8a36fc` — stale by construction across original execution **and** remediation. | M4 rev 1 → carried; rev 2 operator waiver; waiver W4 | **Half-open** | Waived for rev-2 re-audit per operator instruction; treat-as-prediction per plan §8.4.4. Not the M3 charter **F-14** (`assessment_metrics`). Not touched by `eval-consolidation-debt-cleanup` (operator disposition; out of scope). |
| **§8.4.3 T3** | Unnormalizable `--company-name` on `harness_cli run` — fold sits outside try/except on the explicit `--gold-path` path (`harness_cli.py:121`), so traceback can follow a successful run. Pre-remediation gap; gains second manifestation (O-2-2). | M4 plan §8.4.3 carried; rev 2 §9 | **Closed** | Landed via T1: the fold previously at the old line 121 (outside any `try`) was removed; `canonical_company_slug(args.company_name)` now runs inside the existing fail-handled `try` block alongside `EvalHarness(...)` construction. `test_run_unnormalizable_company_name_fails_before_harness_run` proves failure precedes `EvalHarness.run(...)`. Also closes O-2-2's `--gold-path` manifestation. Independently re-verified: named test collected and passes; `build_parser()` and frozen CLI strings untouched. **[eval-consolidation-debt-cleanup T7, 2026-08-14]** |

### M4 rev 2 — coverage gaps (carried / disclosed)

| # | Gap | Status |
|---|-----|--------|
| 1 | No falsifier for unfolded `company_slug` on `load_gold_exclusions` | **Closed** — landed via T1: `test_load_gold_exclusions_rejects_unfolded_company_slug` **[eval-consolidation-debt-cleanup T7, 2026-08-14]** |
| 2 | §8.4.3 T3 unnormalizable `--company-name` (O-2-2 `--gold-path` manifestation) | **Closed** — landed via T1: `test_run_unnormalizable_company_name_fails_before_harness_run` **[eval-consolidation-debt-cleanup T7, 2026-08-14]** |
| 3 | T10-bis mixed Excel+PDF hermetic note-composition test | **Deferred (treat-as-prediction)** | Production data exhibits the behavior; disclosed in plan. |
| 4 | T11 registry-title-honesty hermetic test | **Deferred (disclosed)** | Per-intent title + signoff table are the falsifiers. |
| 5 | T12 `display_name_from_company_slug` non-round-tripping-slug rejection test | **Deferred (disclosed)** | Domain is two slugs; committed store carries no others. |

### M4 rev 2 — observations (non-blocking)

| ID | Item | Status |
|----|------|--------|
| O-2-1 | Unmotivated function-level import of `canonical_company_slug` in `_gold_exclusions` (`bootstrap.py:644`); no cycle exists | **Deferred (cosmetic)** |
| O-2-2 | §8.4.3 T3 gap second manifestation at `harness_cli.py:121` on `--gold-path` path | **Open** (tracked as §8.4.3 T3 above) |
| O-2-3 | Per-company exclusion invariant invoked for `{elder_care, clearsulting}` only; third company needs manual test at onboarding | **Deferred (onboarding discipline)** |
| O-2-4 | T11 decision log "Items deferred — operator signature (placeholder)" not back-annotated after signoff @ `87e194e`; §8.2 records signing correctly | **Closed** — back-annotated via T4; deferral discharged, signed `87e194e` **[eval-consolidation-debt-cleanup T7, 2026-08-14]** |
| O-2-5 | F-05 no-page falsifier pins document-wide matching as intended — matches remedy letter | **Closed (observation)** |
| O-2-6 | Option C on-disk-only persists for packets + `ESC-M4-1` escalation; remediation tracked more (changelogs, decision logs, signoff in HEAD) | **Deferred (by design)** |
| O-2-7 | T13 packet asked cross-company contradiction falsifier; landed within-company with leak guards — substantively equivalent | **Closed (wording)** |
| O-2 (rev 1) | Exact-state pin `len(debts) == 14` in `test_committed_ledger_ratchet_passes` — deletion guard behind F-08 | **Deferred (standing)** |
| O-4 (rev 1) | Dead `import sys` at `bootstrap.py` module-main guard | **Deferred (cosmetic)** |

### M4 rev 1 → rev 2 — resolved (for archive)

All eight rev-1 **majors** (**F-01…F-08**) resolved via ESC-M4-1 / charter **Amendment A5**, T11/T12/T13 remediation, and byte-identical `elder_care.yaml` restoration. Rev-1 recommended minors **F-09**, **F-10**, **F-13** also resolved. **F-11**, **F-12** superseded (historical; recurrence guard is F-2-02 disclosure pattern).

### M4 — charter / handoff surfaces (landed @ rev 2)

| Surface | Owning file |
|---------|-------------|
| `load_gold_exclusions(path, *, company_slug)`; `_gold_exclusions` company-keyed cache | `eval/retrieval/gold/bootstrap.py` |
| Company-keyed `gold_exclusions.yaml` | `eval/retrieval/gold/gold_exclusions.yaml` |
| `display_name_from_company_slug` | `eval/retrieval/trust_statement.py` |
| §2.4 summary lines (`run`, `validate-baseline`) | `eval/retrieval/harness_cli.py` |
| Cluster-submit parse guard | `eval/retrieval/tests/test_onboarding_runbook.py` |
| `GAP-M4-1` registry row; 13 ledger rows; runbook caveats; disposition signoff | `eval/program/registry.yaml`, `eval/program/eval_debt/eval_debt.yaml`, `eval/program/onboarding_runbook.md`, `signoffs/` |

---

## Cross-milestone — priority queue

Ordered by impact for M5 / program close.

| P | Item | Milestone | Tier | Action |
|---|------|-----------|------|--------|
| 1 | **ESC-T12-1** — spec §19/D4 bench exception | M1 | **Tier 3** | idea-orch Update mode; absorb or explicitly waive |
| 2 | **W-F-3** — `validate_row` §16 conditionals + tests | M0 | Tier 1 | **Closed via T2** — 2 raise branches + 4 tests incl. 2 mutation-verified guards `[eval-consolidation-debt-cleanup T7, 2026-08-14]` |
| 3 | **F-2-01 + F-15** — folded-slug enforcement (`load_gold_exclusions` + library path) | M4 | Tier 1 | **Closed via T1** — `require_folded_company_slug`, 3 call sites, 8 tests `[eval-consolidation-debt-cleanup T7, 2026-08-14]` |
| 4 | **R-1 / R-2** — self-hash citation hygiene + plan disposition rows | M3 | Tier 1 | **Closed via T3** — pointer-only annotations landed; `verify_plan_selfhash.py` → PASS `[eval-consolidation-debt-cleanup T7, 2026-08-14]` |
| 5 | **UGA-1** — upstream grounding audit | M3 → M4 | Operator | Execute per attestation D6 / M4 entry gate |
| 6 | **F-2-02** — T11/T12/T13 changelog + Files-to-touch record drift | M4 | Tier 1 | **Closed via T4** — T11/T12 changelog + decision-log record half corrected; packet Files-to-touch amendment declined (non-goal) `[eval-consolidation-debt-cleanup T7, 2026-08-14]` |
| 7 | **§8.4.3 T3** — unnormalizable `--company-name` on `harness_cli run` | M4 | Tier 1 | **Closed via T1** — fold relocated inside fail-handled try block; falsifier landed `[eval-consolidation-debt-cleanup T7, 2026-08-14]` |
| 8 | **F-14** — rung-3 `assessment_metrics` rows | M3 | Tier 2 / waiver | Land rows or extend named waiver with residual risk |
| 9 | **M1 F-11** — re-issue M1 plan §8 @ post-T12–T14 HEAD | M1 | Tier 1 | **Closed via T5** — annotated in place; no re-issue (no post-T14 tracked SHA exists) `[eval-consolidation-debt-cleanup T7, 2026-08-14]` |
| 10 | **M2 F-21** — correct cited test names in M2 plan | M2 | Tier 1 | **Closed via T6** — already correct on disk; ledger was stale `[eval-consolidation-debt-cleanup T7, 2026-08-14]` |
| 11 | **O-2-4** — T11 decision-log placeholder back-annotation | M4 | Tier 1 | **Closed via T4** — back-annotated; deferral discharged `[eval-consolidation-debt-cleanup T7, 2026-08-14]` |
| 12 | **M1 F-9** coverage bundle | M1 | Deferred | Fix-or-accept |
| 13 | **M1 F-10** — charter M1 block touch-up | M1 | Tier 2 | Charter amendment |
| 14 | **M0 registry** — GAP-104, OI housekeeping rows | M0 | Housekeeping | Close or re-scope registry rows |
| 15 | **M4-F-14** — M4 context map stale @ `3126c2b` | M4 | Deferred | Treat-as-prediction; refresh map when M5 planning starts |
| 16 | **M2 F-20** — tighter C5 threshold pinning | M2 | Optional | Harden interval tests or assert literal defaults |
| 17 | **M2 F-16** — SQL chunk_id escaping | M2 | Optional | Hygiene when touching `calibration.py` |

---

## Escalation index

| Escalation | Path | Status |
|------------|------|--------|
| ESC-T12-1 (bench spec note) | `.dev/plans/eval-consolidation-m1-metric-guardrail-hardening/escalations/ESC-T12-1-bench-spec-note.md` | **OPEN** |
| ESC-T2-3 (measure validity C5/C8) | `.dev/plans/eval-consolidation-m2-s2-preplan-assessments/escalations/ESC-T2-3-measure-validity-c5-c8.md` | **Closed Option A** (residuals carry) |
| ESC-M4-1 (Clearsulting gold / A5 grant) | `.dev/plans/eval-consolidation-m4-onboarding-runbook/escalations/ESC-M4-1-rb-defect-t9-1-gold-corpus.md` | **Closed / RULED** → charter Amendment A5 |

---

## Audit artifact index

| Milestone | Governing audit report |
|-----------|------------------------|
| M0 | `.dev/audits/eval-consolidation/M0/2026-08-10-eval-consolidation-m0-audit.md` |
| M1 | `.dev/audits/eval-consolidation/M1/2026-08-11-eval-consolidation-m1-audit.md` |
| M2 | `.dev/audits/eval-consolidation/M2/2026-08-12-eval-consolidation-m2-audit.md` |
| M3 | `.dev/audits/eval-consolidation/M3/2026-08-13-eval-consolidation-m3-audit-rev5.md` |
| M4 | `.dev/audits/eval-consolidation/M4/2026-08-14-eval-consolidation-m4-onboarding-runbook-audit.md` (rev 2) |

*Prior M3 revisions (rev 1–4) and M4 rev 1 (`.rev1.md`) remain on disk as historical record only.*
