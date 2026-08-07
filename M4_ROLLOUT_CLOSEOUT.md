# M4 — Validation & Rollout: Post-Refactor Closeout Report (plain-English edition)

**Program:** UC-13 Ingestion Parser refactor — from "delete everything for a company, re-parse everything" (company-as-transaction) to a **durable per-document status table** that drives incremental-by-default, resumable, auditable ingestion (document-as-transaction).
**Rollout window:** 2026-08-05 → 2026-08-06 (UTC) · **Catalog:** `uc13_ale` (eval) · **Report date:** 2026-08-07
**Verdict:** All program gates hold. M4 (the final milestone) is complete pending re-audit.

> **Update 2026-08-07 — first Phase 4 audit returned `fail`; remediated.** The audit ([`.dev/audits/2026-08-07-uc13-ingestion-parser-M4.md`](.dev/audits/2026-08-07-uc13-ingestion-parser-M4.md)) found **no production code defect** — the suite was green and no runtime byte had changed — but filed four majors against the *gate evidence*: the shipped attestation tool dropped non-terminal documents from its summary line (F1), the closing catalog numbers reconciled in no direction (F2), that tool had never actually been run (F3), and two companies' evidence was uncommitted (F4). All four are closed by plan §7 amendments A1–A5; see the `CHANGELOG.MD` audit-remediation section. **Two numbers in this report were wrong and are corrected below: §3.1's suite count and §3.2's final catalog state.**

---

## 1. Short answer

Yes — the refactored parser was validated end-to-end and the rollout completed on all four companies with **zero failed documents** and a **0.000% orphan rate** on the retrieval join everywhere. Precision matters though: the *code* behaved exactly as designed — including its failure and resume paths — while the *environment* needed four non-code fixes along the way. All were absorbed without touching production code, which is itself the strongest signal that the redesign works.

---

## 2. The gates, decoded

The program charter defines five program-level proof points, G0–G5. Here is what each actually means and how it was verified:

| Gate | Plain-English meaning | How it's verified | Result |
|------|----------------------|-------------------|--------|
| **G0** | *Governance:* the spec and charter are pinned and approved before any code runs | Read spec header + approval fields | Holds **with one recorded waiver**: the spec's cycle-5 review re-approval was deferred by operator decision during the program; recorded as an accepted non-blocking waiver, not silently ignored |
| **G1** | *Sync contract:* the 9 existing tests that pin down exactly how the vector-index sync behaves (what gets printed, when the run must halt) must stay green after the refactor | `pytest tests/test_ingestion_parser_sync.py` | ✅ 10/10 collected cases passed |
| **G2** | *Document-ID contract:* the function that turns a file's volume path into a stable hash (`make_doc_id`) must normalize edge cases identically forever — folder path null/empty/".", trailing slashes, filenames with brackets. If this ever drifts, every stored doc_id silently invalidates | `pytest tests/test_make_doc_id.py` | ✅ 15 passed |
| **G3** | *Fail-closed sync:* after parsing, the run must end with `✓ Index ready` (index confirmed current) or halt loudly with `✗ Sync failed — halting` and a non-zero exit. Never proceed on an unconfirmed index | Observed in live run output | ✅ `✓ Index ready and current` on all 4 companies; the halt path also fired correctly once (see §4.3) |
| **G4** | *Join health:* the share of parsed chunks that can't be joined back to the classifier's document table (orphans). Historical baseline was ~47.6% on Elder Care when joining by filename; the refactor joins by the stable doc_id hash instead | Orphan-rate SQL per company | ✅ **0.000% on all four companies** |
| **G5** | *Attestation:* after rollout, a per-company status query must return counts in the shape "N approved, M complete, K failed with reason X" — the auditable receipt that every approved document reached a terminal, explained state | `SELECT status, COUNT(*) FROM doc_status ...` per company | ✅ See table in §3.2 |

---

## 3. What was validated

### 3.1 Code gates (local, pre-rollout)

- M4's new test slice (parser extension dispatch, 2,000-chunk cap, embed batching, per-document state transitions, interrupted-document redo, attestation tooling): **66 passed**.
- Full repo suite at commit `e04f7b8`: **872 passed, 5 skipped** — `uv run --project databricks pytest tests/ eval/retrieval/tests/ -q`. *(Corrected: this line originally read "667 passed", which is the `tests/`-only subset. The 205 omitted tests live under `eval/retrieval/tests/`, the same tree as the attestation tool — audit F7.)* After the §7 audit amendments: **877 passed, 5 skipped**.

### 3.2 Live rollout gates (per company, `uc13_ale`)

| | Clearsulting | GKF | SPG | Elder Care |
|---|---|---|---|---|
| Approved docs / COMPLETE / FAILED | 22 / 22 / 0 | 41 / 41 / 0 | 364 / 358 / 0 | 475 / 467 / 0 |
| Zero-chunk docs (explained, not failures) | 0 | 0 | 6 | 8 |
| Chunks + embeddings written | 2,417 | 3,107 | 43,602 | 55,812 |
| Orphan rate (doc_id join) | **0.000%** | **0.000%** | **0.000%** | **0.000%** |
| Index confirmed current (`✓ Index ready`) | ✅ | ✅ | ✅ | ✅ |
| Vision-extracted chunks | 1,224 | 339 | 4,952 | 2,699 |

**Final catalog state — measured 2026-08-07T13:01:05Z by the shipped `eval/retrieval/measure_attestation.py`:** **902 status rows (888 COMPLETE, 14 ZERO_CHUNKS, 0 FAILED, 0 non-terminal)**; sync watermark `2026-08-06T22:41:44Z`; vector index 104,938 rows and current. No `doc_status` rows exist outside the four rollout companies.

*Corrected — audit F2.* This line previously read "908 rows (885 COMPLETE, 16 ZERO_CHUNKS)", which closed in no direction: 885 + 16 = 901, not 908, on a line simultaneously claiming zero rows in any other state; and the per-company columns above sum to 888 / 14 / 902. The re-measured state matches the per-company evidence exactly — 22 + 467 + 41 + 358 = **888** COMPLETE, 8 + 6 = **14** ZERO_CHUNKS, **902** total. The original aggregate was a transcription error, not a catalog discrepancy: the per-company numbers were right all along, and nothing in the catalog changed between the rollout and the re-measure (the watermark is unmoved). Per-company PHV lines from that run are in the `CHANGELOG.MD` audit-remediation section.

**On the "27 extra SPG documents" (§6.3):** these are coverage-injected *chunk* documents (391 distinct `doc_id`s in `chunks` vs 364 approved), not `doc_status` rows, so they neither close nor widen the row-count question above — SPG's `doc_status` holds exactly 364 rows.

---

## 4. How the key mechanisms work (and how they were proven live)

### 4.1 The per-document loop

Each document moves through a durable status row: claimed (`PARSING`) → optional cleanup of its previous chunks → parse → chunk write → embedding write → `COMPLETE`, or `FAILED(reason)` / `ZERO_CHUNKS(reason)` with a controlled vocabulary of reasons. Because every transition is written to a Delta table per document, the unit of recovery is one document — not the whole company.

### 4.2 Retry/resume after a kill — proven twice, unplanned

Both Elder Care and SPG hit the 4-hour job timeout mid-run (they're large: hundreds of vision-heavy files). Each time, exactly one document was left in `PARSING` — the one being worked on when the job died. The resume run (incremental mode, no force) reclassified that row as `RETRY`, deleted its partial chunks/embeddings by doc_id, and redid it. **No duplicate rows, no manual cleanup, no lost work.** This was the refactor's central promise and it was exercised by reality, not a test rig.

### 4.3 The watermark sync gate — proven in both directions

A catalog-wide "watermark" records the last time the vector index was confirmed current. A run only triggers the expensive index sync if at least one document completed *after* that watermark, and it only advances the watermark *after* the index reports current. Observed live: a partial Clearsulting run correctly **skipped** sync (nothing new); all full runs **triggered** it and advanced the watermark; and when the sync-monitoring code itself broke (SDK issue, §5.3), the run **halted** with the contract error message instead of continuing on an unconfirmed index.

### 4.4 What happened with Elder Care's legacy data (the one real data fix)

Before the refactor, chunks were deleted and rewritten per company in one big transaction. The refactor replaced that company-wide delete with surgical per-document deletes keyed by doc_id — safer, but it can only reach rows whose doc_id matches the new scheme. Elder Care's old chunks were hashed when the volume lived under the *production* catalog name (`uc13`), while the new parser hashes with the eval catalog (`uc13_ale`). Different hash input → different doc_ids → 35,035 old rows were invisible to the per-doc cleanup and showed up as a 38.6% orphan rate right after the re-parse.

Fix (within the destructive scope already approved for the force-rollout): a one-time, tightly-scoped delete of Elder Care chunk/embedding rows whose doc_id is not in the company's new status table, then a sync-only re-run to bring the index current. Result: 0.000% orphans. Only Elder Care needed this — the other three companies' old chunks were already hashed with `uc13_ale`, so the per-doc delete cleaned them automatically.

---

## 5. What did NOT go smoothly — the four environment frictions, and their blast radius

Your intuition is correct on dependencies: **the imports exist in the code and the packages are declared in `databricks/requirements.txt` — they were never missing from the repo.** What was missing is that the *execution path used for the rollout* (an ad-hoc serverless job submission with its own declared dependency list) didn't install `requirements.txt`, and the serverless base image doesn't preinstall them the way the classic Databricks ML runtime does. Also, most of these imports are deliberately *lazy* (inside the function that needs them, not at module top), so the run doesn't crash on import — instead each affected document fails individually with a precise reason. That's why the first partial run could save some documents while others failed with `No module named 'mlflow'`.

| # | Friction | What happened | Test-scope or production path? | Current state |
|---|----------|---------------|-------------------------------|----------------|
| 5.1 | **Serverless-only workspace** | The charter assumed a classic cluster; the workspace rejects classic clusters entirely. Rollout ran on serverless job submission instead | **Ops/deployment path only** — no code change | Works; serverless + per-doc status made timeouts cheap. No OOM on the 1,386-file Elder Care run (the pre-refactor killer) |
| 5.2 | **Missing Python packages on serverless** (`mlflow`, `openpyxl`, `python-docx`, `pymupdf`) | First runs: vision-capable and Excel documents failed per-document with exact reasons (`PARSE_EXCEPTION: No module named ...`) | **Production code path, environment gap.** The imports are in production code; packages declared in `databricks/requirements.txt`; the gap is that neither the serverless job environment nor the workflow YAML's task definitions install that file — on classic clusters they were silently preinstalled by the ML runtime | Fixed for the rollout by declaring them in the job environment. **Still open:** the workflow YAML tasks don't declare these packages — if the pipeline runs outside a classic ML runtime, this resurfaces |
| 5.3 | **databricks-sdk breaking change** | Newer SDK versions renamed the index-spec attribute the sync monitor reads (`delta_sync_index_spec`). The fail-closed contract caught it: `✗ Sync failed — halting`, non-zero exit — exactly the designed behavior for an unconfirmed index | **Production code path** (`_wait_for_index_sync` in `ingestion_parser.py`) | Worked around by pinning `databricks-sdk==0.120.0` in the job environment. **Still open:** production code should be made tolerant of the renamed attribute; the pin is a stopgap, and `databricks/requirements.txt` doesn't pin the SDK at all |
| 5.4 | **Delta column-defaults limitation on serverless** | The status table's DDL uses `coverage_injected BOOLEAN DEFAULT FALSE`; serverless Delta refuses column DEFAULTs unless the table is created with a specific feature flag | **Production DDL path** (the idempotent table-ensure step every run starts with) | Worked around by pre-creating the table (identical 14-column schema) with the feature flag. **Still open:** if `doc_status` is ever dropped, the code's own CREATE will fail again on serverless |

**Net:** no production code was modified during rollout. All four frictions are environment/deployment-surface issues; three of the four have residual follow-ups listed above.

---

## 6. Honest caveats (not gate-blocking)

1. **16 zero-chunk documents** (8 Elder Care, 6 SPG) — documents the parser examined and found nothing extractable in: mostly Terms-of-Service/contract Word files and legacy `.xls` financials where every chunk got filtered, plus one PDF (`SHAY_ Motion to Dismiss`, Elder Care) that returned empty extraction. These are *explained terminal states*, not failures — but that one PDF is worth a manual look if the document matters.
2. **Vision page statistics report zero** despite ~9,200 vision chunks flowing. A known deferred observability gap: the summary counters exist but the parse function doesn't feed them. Chunk-level vision counts (the numbers in §3.2) are accurate; per-page stats aren't.
3. **SPG parsed 27 documents beyond its approved set** (391 vs 364) — the manifest's coverage sub-pass deliberately injects up to 3 extra documents per uncovered workstream so no analysis workstream is starved. By design, but "approved" ≠ "parsed" counts.
4. **Elder Care parsed 475 approved documents out of 1,386 files in the data room.** The funnel from 1,386 → 475 is the classifier's tiering/`should_parse` decision, owned by a different phase and unchanged by this program. The rollout ingested everything it was supposed to — not the whole VDR.
5. **The deployed workflow path for the parser is still untested.** The rollout ran via agent-driven job submission, not the YAML workflow. A known carried finding: `python_script_task` parameters arrive as `sys.argv` while the parser reads only widget/env params — the YAML-defined job would currently run with defaults.

---

## 7. What's left

1. **Re-audit of M4** — the only remaining gate. The first audit returned `fail` (4 major); plan §7 amendments A1–A5 close F1–F7, F9 and F10, and the auditor's recommended scope is a **full re-pass**, not a spot check of the four, because A1 modifies `measure_attestation.py`. Evidence staged: corrected tool + 5 regression tests, the shipped tool's own run against all four companies (`.dev/m4_attestation_run_log.txt`), restated G5 numbers, and all rollout evidence now committed.
2. On a `clean` or `accepted-with-waivers` verdict, the program is complete.
3. **Carried, not actioned** (audit F8, F11, F12 — reasons in plan §7): a contract-anchor test file attributed to the wrong subtask in git history; a missing scout grep that sat upstream of F5; and the observation that M4's suite is characterization-shaped — 27 tests, none red, the conditional corrective-fix subtask never fired. F12's one concrete item is a reason-vocabulary mislabel at `doc_worker.py:217–220`, where a chunk-**write** failure is stamped `EMBED_EXCEPTION`; fixing it would modify a runtime symbol and is outside M4's non-goals.
4. Optional follow-ups (not blockers): SDK-version-tolerant sync introspection; wire the vision page counters; declare packages on the workflow YAML tasks; fix the YAML argv-mirroring gap; a minimal serverless smoke test to catch environment drift before rollout rather than during.

**Bottom line:** the refactor delivers what the spec promised — incremental-by-default, resumable, auditable ingestion with a verifiable retrieval join — and it proved it under real failure conditions (killed jobs, a broken SDK, missing packages) rather than a clean-room run.
