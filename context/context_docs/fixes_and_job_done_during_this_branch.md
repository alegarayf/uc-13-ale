# VDR Pipeline — Integration & Fixes Session

> **Branch:** `feature/uc13-after-merge-job-test`
> **Workspace:** Rallyday/NimbleGravity Databricks (Azure) · CLI profile `rallyday`
> **VDR job:** `VDR Diligence Pipeline` (job_id `617196299594076`)
> **Test companies:** Clearsulting ("Project Infinity"), GKF ("Project Ajax"), Elder Care
> **Final HEAD at end of session:** `381e1e2` (all commits below are on `feature/uc13-after-merge-job-test`, pushed to `origin` and synced to the Databricks Git folder that the job reads)
> **Next-session backlog:** [`to_do/next_session_backlog.md`](./to_do/next_session_backlog.md)
> **Handoff:** see [§0 below](#0-handoff--current-state) for what's validated, what's in flight, and how to pick this up.

This document summarizes everything **implemented, modified, and fixed** during the session that got the VDR pipeline running end-to-end from the UI with the merged (post-Ale) code, and hardened it against the failures found on real runs.

---

## 0. Handoff — current state

**Validated end-to-end (9/9 agents, no errors):**
- Clearsulting (run 31) — small data room (~29 files), confirms the core pipeline + BMA split + profiler recall.
- GKF (run 36) — small-medium data room (42 files), confirms the shared-VS-index fix under back-to-back runs and the chunk-explosion fixes don't regress normal-sized files.

**In flight when the session ended:** Elder Care (~1,386 files) was about to be reprocessed on HEAD `381e1e2` — the run that should validate the chunk-explosion fix at scale (previously 253K chunks / VS sync timeout). **Check its outcome first** before doing anything else — if it's still failing, the chunk cap or classifier exclusion may need tuning (see `MAX_CHUNKS_PER_FILE` in `ingestion_parser.py` and `_RAW_DATA_DUMP_PATTERNS` in `document_classifier.py`).

**Everything below is pushed to `origin/feature/uc13-after-merge-job-test` and already synced to the Databricks Git folder the job reads** — no deploy step needed to pick this up. If you `git pull` this branch, sync the Git folder with:
```bash
databricks repos update 63672178662438 --branch feature/uc13-after-merge-job-test --profile rallyday
```

**Not yet done (see backlog for full list):**
- No validation run on GKF/Clearsulting/Elder Care has been QA'd for *content* correctness (numbers, overlay accuracy) — only pipeline mechanics (SUCCESS/FAILED, chunk counts, no crashes).
- Two known concurrency-adjacent items: the shared VS index now waits instead of failing, but two ingestions still serialize on it — fine for correctness, just not parallel-fast.
- Orphaned `companies_vdr_history` records from earlier failed attempts (see §"Known remaining items").

---

## 1. UI → Job wiring (make the VDR job run the integrated code)

- **Integration verification** — Confirmed all of Hector's `feature/ui-pipeline-integration` work landed intact in the merge branch, and documented Ale's additions (`exec_summary/` package, financial sub-agents, retrieval eval harness, Legal agent rewrite, catalog convention, the Rev3 one-pager bridge).
- **Git folder → merged branch** — Switched the Databricks Git folder `Rallyday` (repo id `63672178662438`, the code source the job actually reads) from `feature/ui-pipeline-integration` (pre-merge) to `feature/uc13-after-merge-job-test`. The job's `git_source` block was dead config; the real source is the Workspace Git folder.
- **Branch pushed to `origin`** — The merge branch existed only locally; pushed to GitHub (`Nimble-Gravity/Rallyday`).
- **UI trigger fix** (`c5abb12`, `d53611d`, `13c02f8`):
  - Added a thin entry **notebook** `databricks/jobs/notebooks/run_vdr_job.py`.
  - Reconfigured the job task from `spark_python_task` (fixed positional params) to **`notebook_task` with NO parameters**.
  - Read the record id from the **`record_id`** widget (the name the VDR UI actually sends; the relayed example said `id`).
  - Root cause: fixed task parameters blocked the UI's widget-based trigger, so UI submissions were never picked up.

## 2. Catalog & infrastructure provisioning

- **Created `uc13.ops`** — Ran the project's own DDL (`eval/retrieval/scripts/apply_ops_ddl.sql`, `{catalog}`→`uc13`) via the SQL warehouse: schema + 4 tables + 2 views. Additive, `IF NOT EXISTS`, non-destructive.
  - Root cause: `pipeline.py` forces `RE2_STORE_BACKEND=delta`, so **every** agent's retrieval writes provenance to `{catalog}.ops.retrieval_harness_runs`. That table existed only in `uc13_ale`, so all agents crashed with `TABLE_OR_VIEW_NOT_FOUND`. Result went from **1 SUCCESS / 5 FAILED / 3 SKIPPED** → **8 SUCCESS**.
- **Recreated the Vector Search index** `uc13.ingestion.embeddings_index` with `columns_to_sync` (including `company_name`, `workstream`, `priority_tier`, `source_type`).
  - Root cause: the deployed index was created by old code before `columns_to_sync` was specified and `setup_vector_search` is idempotent (skips existing), so it synced **no metadata columns** → filter pushdown never worked ("VS filter pushdown unavailable: company_name"). Recreation enabled pushdown → correct isolation + full recall for all agents.

## 3. Code fixes (by commit)

**Reading guide:** every item below has already been merged to `feature/uc13-after-merge-job-test` and pushed. The **STATUS** line tells you whether it's been *exercised on a real VDR run* (✅ VALIDATED — seen working with your own eyes in a run's logs) or only *verified by reading the code* (⚠️ CODE-COMPLETE, NOT YET RUN) — i.e. logically correct but not yet proven against Databricks/live data in this exact shape. None of the items in this section are "still broken" — if something reads that way, it's describing the *diagnosis process* (an earlier attempt that didn't work), not the current state.

- **`9a31829`** — Two fixes. **STATUS: ✅ VALIDATED** (both confirmed in Clearsulting runs 27+).
  - **Phase-5 manifest accuracy** (`pipeline.py`): the orchestrator now shows **SUCCESS** in the persisted report. It was mislabeled "SKIPPED — phase 5 not in scope" because the manifest snapshot was captured before the orchestrator marked itself done; it actually ran and produced the memo.
  - **Cross-company contamination** (`company_profiler.py`): both `semantic_search()` calls now pass `company_name`. Previously omitted → retrieval hit the shared index across all companies and pulled Elder Care / Ajax CIM chunks into Clearsulting runs, producing the wrong industry overlay (which every Phase-3 agent then reads).
- **`d72443f`** — **Vision extraction ON by default (Haiku)** in the VDR path, controllable via a `vision_endpoint` widget. The CIM is ~70% image pages; with vision off they were never transcribed, so agents couldn't "see" the CIM. **STATUS: ✅ VALIDATED** — confirmed CIM content retrievable in every run since.
- **`7ff1157` → `2d22931`** — **BMA extraction timeout — two-step fix, both commits are part of the SAME final solution (not competing attempts):**
  - `7ff1157` bounded the BMA input context (CIM-first, per-chunk caps, 90K-char budget) and tried setting an LLM read-timeout env var. This alone was not sufficient — the read timeout is enforced by the Databricks serving layer itself (~120s), not something an env var on the client side can raise.
  - `2d22931` is the fix that actually resolved it: **split the BMA extraction into two bounded passes** (commercial / organizational field groups, 8K tokens each), combined by taking each group's fields from its own pass. Splitting the call keeps each request under the 120s wall instead of trying to extend the wall. No output truncation; both passes see the full context.
  - **STATUS: ✅ VALIDATED** — BMA completed without timeout in Clearsulting run 31 and GKF run 36.
- **`0faacd8`** — **Profiler recall** (`company_profiler.py`): the CIM file is named "…Confidential Information **Memorandum**.pdf", which does not contain the substring "CIM", so the `["CIM", …]` filename filter silently excluded it → every dimension returned 0 chunks and the overlay came out `other`. Added "Memorandum" to all filters, and made the retry a pure company-scoped semantic search (drop filename/workstream/tier). Company isolation preserved via `company_name`. **STATUS: ✅ VALIDATED** — Clearsulting run 31 correctly classified as `tech_services` (high confidence).
- **`67467aa` → `f47a7c1`** — **Financial Trends memo-section crash — two diagnosis attempts, one real fix. This is fully resolved; both commits are kept for the record of HOW it was diagnosed, not as two separate open problems.**
  - **What broke:** the orchestrator's per-workstream memo section for Financial Trends was crashing with `'str' object has no attribute 'get'` and silently falling back to a generic placeholder section instead of the real narrative.
  - **`67467aa` (attempt 1 — turned out to be the wrong hypothesis):** added `_as_dicts()` to filter out non-dict elements from the numeric JSON arrays (`revenue_trend`, `ebitda`, etc.) before iterating them. Ran a validation pass afterward and **the crash still happened** — those arrays were already clean dicts, so this wasn't the actual cause. The fix itself is harmless (defensive, no-op on clean data) so it was kept, but it did not close the bug.
  - **`f47a7c1` (attempt 2 — the actual root cause, confirmed by inspecting the live table):** the `flags` column in `uc13.analysis.financial_trends` is persisted as a **STRING** (it holds a JSON-encoded array, not a native array type) — confirmed via `typeof(flags) = string` in a direct query. When the orchestrator loaded a row from Delta and did `sorted(flags, key=lambda f: f.get('severity'))`, Python iterated the *characters of the string* (since `flags` was still a raw string, not a parsed list) and called `.get()` on each character → crash. Fix: deserialize `flags` with `json.loads()` before using it, keeping only dict elements — the same defensive pattern already used in `business_model_agent.py`.
  - **STATUS: ✅ VALIDATED AND CLOSED** — confirmed fixed in Clearsulting run 31 and GKF run 36: no more fallback, the real Financial Trends narrative renders in the memo. No further action needed on this item.
- **`f4de18b`** — Two robustness fixes surfaced by the Elder Care failure. **STATUS: ✅ VALIDATED** — GKF run 36 exercised both (pipeline succeeded fully, no need for the guard to trigger, but the exec-summary path ran on a live company and completed with no 400 error).
  - **`run_vdr_pipeline.py` guard**: bail out *before* building the memo/one-pager when the pipeline aborted (ingestion failed → no embeddings) or every diligence agent failed. Previously it still called `build_exec_summary` over empty data.
  - **`bundle_builder.py` (exec_summary) endpoint cap**: `synthesize_executive_narrative` requested a fixed `max_tokens=12_000`; capped to `8_000` when the endpoint is Haiku/Llama (their output cap is 8192) to avoid an HTTP 400. Root cause of *why* Llama was even in play: on the aborted path, `os.environ["llm_endpoint"]` stays at the Phase 1-2 default (Llama) because Phase 3-5 — which normally overrides it to Sonnet — never ran.
- **`3477a65`** — **Chunk-explosion fix (Elder Care root cause)**, two layers. **STATUS: ⚠️ CODE-COMPLETE, VALIDATION IN FLIGHT** — the logic is in place and reasoned through carefully, but the one run that would prove it at scale (reprocessing Elder Care itself) was starting as this session ended. **Check that run's outcome before assuming this is fully proven** — see §0 Handoff.
  - `ingestion_parser.py`: new `MAX_CHUNKS_PER_FILE = 2_000` hard cap applied in `parse_file()` for every file type — truncates and logs instead of letting one spreadsheet balloon into tens of thousands of chunks (Elder Care had raw "Performance Data/Detail" exports that alone produced 30K–80K chunks each, 253,237 total).
  - `document_classifier.py`: added `_RAW_DATA_DUMP_PATTERNS = ("performance data", "performance detail")` — a conservative deterministic override that forces `should_parse=false` for filenames matching those patterns (regardless of what the LLM classifier said), plus a strengthened prompt exclusion. Intentionally does **not** match "... Data Summary" files, which are useful.
- **`381e1e2`** — **Shared Vector Search index contention fix** (`ingestion_parser.py`, also covers `ensure_coverage.py` which reuses this function). **STATUS: ✅ VALIDATED** — GKF run 36 hit exactly this scenario (running right after Elder Care's heavy sync) and completed cleanly.
  - The VS index is shared across all companies. If a prior run's sync is still `RUNNING` when a new run tries to trigger its own sync, `sync_index()` previously raised immediately ("Index is not ready to sync yet") and failed the whole parse. Now it waits (`poll_interval`) and retries the trigger until the shared pipeline frees up, bounded by `max_wait_seconds`. **This is what directly caused GKF run 35 to fail** — fixed and confirmed working in GKF run 36.

## 4. Teammate integration

- **`82fd044`** — Merged 2 "post-merge regression fix" commits from the base branch `merge-ale-base-hector-incoming-results` after reviewing they didn't break the core. Business Model agent robustness: extraction `max_tokens` 8192→16000, defensive JSON parse of `flags`/`data_room_gaps`, and force Sonnet when the widget resolves to Haiku/Llama (whose 8192 output cap is too small for the BMA schema).

## 5. Persistent memory (for future sessions)

- Saved: workspace access (profile `rallyday`, job id, Git folder id, warehouse id), the `uc13` vs `uc13_ale` catalog convention, and the requirement that any catalog needs `uc13.ops` created once (via `apply_ops_ddl.sql`).

---

## Result timeline (VDR runs, in order)

| Run (record id, company) | Outcome |
|---|---|
| 26 (Clearsulting) | 1 SUCCESS / 5 FAILED — all agents crashed on missing `uc13.ops` |
| 27 (Clearsulting) | 8 SUCCESS — after creating `uc13.ops`; `analysis.legal` created; deliverables real |
| 29 (Clearsulting) | 8 SUCCESS / 1 FAILED — `business_model` timed out (16K single call); profiler still low recall; FT memo section fell back |
| 31 (Clearsulting) | **9 SUCCESS / 0 FAILED** — BMA split worked (2 passes, no timeout); profiler correct (`tech_services`, high confidence, CIM retrieved on all 7 dimensions); overlay propagated to all agents. FT memo section STILL fell back (the `flags` bug). |
| 34 (Elder Care) | **FAILED** — large data room (~1,386 files). Raw-data Excel files exploded to **253,237 chunks** → VS sync exceeded the 1800s cap → parser fail-closed → Phase 3-5 aborted → then exec_summary hit Llama with 12K tokens (env leak on abort path) → HTTP 400. Root causes fixed in `f4de18b` + `3477a65`. |
| 35 (GKF) | **FAILED** — unrelated to Elder Care's own root cause, but a *side effect* of it: GKF tried to sync the (shared) VS index right after Elder Care's massive sync left the underlying DLT pipeline `RUNNING` → `sync_index()` rejected immediately → parser fail-closed → Phase 3-5 aborted. Fixed in `381e1e2`. |
| 36 (GKF) | **9 SUCCESS / 0 FAILED** — clean run on `381e1e2`. Confirms: shared-index wait/retry works, chunk counts stayed sane (2,991 chunks, no explosion), FT memo section rendered fully (no `flags` fallback), BMA split held. |
| next: Elder Care reprocess | **In flight at end of session** — validates the chunk-explosion fix at the scale that originally broke it. Check this first when resuming. |

## Known remaining items

- **Elder Care reprocess outcome** — verify first (see §0 Handoff).
- **Integrity Risk** (records 18–24, `submitted`): its `source_data_location` points to a dated subfolder (`…/Integrity Risk/7.24.2026`), but the folder resolver looks for `…/Example Data Room/Integrity Risk` (no date) — verify before processing.
- Orphaned `submitted` records (25 failed on the widget, 18–24 never ran) — clean up or reprocess.
- Optional hardening: make the FTA **writer** never persist non-dicts into the JSON arrays (the memo-section fix already neutralizes the symptom).
- `MAX_CHUNKS_PER_FILE=2000` and `_RAW_DATA_DUMP_PATTERNS` are conservative first passes — if Elder Care (or any future large data room) still produces an unreasonable chunk count, tune these rather than re-deriving from scratch.
- Full backlog with priority tiers: [`to_do/next_session_backlog.md`](./to_do/next_session_backlog.md) — this session's fixes have been checked off there; it also covers items from the *first* half of the session (job/UI wiring, `uc13.ops`, VS index recreation, memo section, etc.) not repeated here.
