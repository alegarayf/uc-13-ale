# UC13 / VDR Pipeline — Next-Session Backlog

> Open items to tackle in future sessions, ordered roughly by priority.
> Context: see [`../fixes_and_job_done_during_this_branch.md`](../fixes_and_job_done_during_this_branch.md).
> Branch: `feature/uc13-after-merge-job-test`.

## 🟣 Product roadmap — next few days (Hector's priorities)

Three product-facing initiatives, independent of the bugfix work above. Ordered as given.

### 1. Rainmaker format layer — visual executive summary (PDF/slide-style)
Build a schema/template so the generated `executive_summary` content can render as a **slide-style, visual PDF** (not just the current prose one-pager `.docx`) — more digestible for a stakeholder skim than a text document.
- Likely lands near `agents/exec_summary/` (the existing Rev3 one-pager bridge / `bundle_builder.py` / `pipeline_entry.py`) — check whether "Rainmaker format" already has partial scaffolding there (Ale's naming) before building from scratch.
- Needs a rendering choice: HTML→PDF, a slide library, or a fixed-layout template engine. Decide based on what's already in the stack (ReportLab is already a dependency for `run_vdr_pipeline.py`'s PDF generation — evaluate reusing it vs. a different tool for a visual/slide layout).
- Scope: define the schema (what fields map to what visual blocks: KPIs, flags, exec narrative, top issues) before picking the rendering tech.

### 2. CIM-first staged flow — cheap preview before full pipeline
Architectural change to the execution flow, gated by CIM presence:
- **If a CIM-like file exists** in the data room: run a cheap pre-step that generates an **executive preview** (using the Rainmaker format from #1) from just the CIM (+ a small set of user-provided key files in a VDR SharePoint folder) — *not* the full Phase 1-5 pipeline.
- **User reviews the preview in the UI.** If approved, the UI triggers the **full pipeline** (all 7 workstream agents + Cross-Analysis + Orchestrator) to produce the full report — this is today's existing flow, just gated behind an approval step.
- **If no CIM exists:** skip the preview step, fall back to today's behavior (or use the user-provided "most important files" folder directly as the basis — needs definition).
- Motivation: saves tokens/compute on data rooms where the user might not even want a full report, or wants to sanity-check direction first. This is a **new gate/step in `run_vdr_pipeline.py` / `run_full_pipeline.py`**, likely needs a new `companies_vdr_history` status (e.g. `preview_ready` between `submitted`/`processing` and `done`) and a corresponding UI action to trigger the second stage.
- Depends on #1 existing (the preview needs a format to render into).

### 3. Report refinement (~33p target) + Word/PDF formatting iteration
Iterate on report *content* (not just pipeline mechanics) based on feedback from **Austin** (primary stakeholder):
- Target length ~33 pages for the full report (current length varies — check `Elder Care`/`GKF`/`Clearsulting` current page counts as a baseline).
- Depends on Austin's feedback loop — no fixed technical scope yet; expect iteration on `orchestrator_agent.py` (`_fmt_manifest_md`, section assembly) and `md_to_word.py` (Word styling) once feedback lands.
- Related to the still-open backlog item above: "QA the generated memo / one-pager content" — that spot-check should inform what Austin actually reacts to.

---

## 🔴 Elder Care large-data-room failure (runs 34, 35) — HIGH PRIORITY, IN FLIGHT
Elder Care (~1,386 files) failed twice, plus caused a side-effect failure on GKF. Root causes + fixes:
- **[DONE `3477a65`] Chunk explosion (root)** — per-file cap `MAX_CHUNKS_PER_FILE=2000` in `parse_file` (all types, truncate+log) + `document_classifier` forces should_parse=false for raw data exports ("Performance Data/Detail"). **STILL NEEDS a validation run on Elder Care itself** to confirm chunk count drops from 253k to a sane range and the VS sync completes end-to-end. This was in flight when the session ended — check its outcome first.
- **[DONE `381e1e2`] Shared VS index contention** — GKF run 35 failed because Elder Care's massive sync left the shared index's DLT pipeline `RUNNING`, and `sync_index()` rejected immediately instead of waiting. Fixed: wait-and-retry loop in `ingestion_parser.py` (bounded by `max_wait_seconds`). **Validated in GKF run 36** (9/9 SUCCESS, clean sync).
- **[DONE `f4de18b`] exec_summary Llama 400** — capped `synthesize_executive_narrative` max_tokens to 8000 for Haiku/Llama endpoints in `bundle_builder.py`.
- **[DONE `f4de18b`] run_vdr guard** — `run_vdr_pipeline` now bails before building reports when the pipeline aborted / all agents failed.
- **Incremental ingestion** — full re-download + re-parse + re-embed every run is the amplifier here. Consider skip-if-already-ingested.
- If Elder Care still produces too many chunks after the cap, tune `MAX_CHUNKS_PER_FILE` (`ingestion_parser.py`) and/or extend `_RAW_DATA_DUMP_PATTERNS` (`document_classifier.py`) rather than re-deriving the approach.

## 🔴 Validated this session (for reference — do not re-fix)
- ✅ FTA `flags` JSON-string fallback (`f47a7c1`) — confirmed fixed in runs 31 → 36, no more `generator failed`.
- ✅ GKF re-run with all fixes (vision, recreated index, BMA split, shared-index wait, chunk caps) — run 36, 9/9 SUCCESS, clean.
- ⏳ **Still open:** QA the generated memo / one-pager *content* for Clearsulting and GKF — 9/9 SUCCESS confirms pipeline mechanics, not that numbers/overlay/narrative are correct. Spot-check before treating output as client-ready.

## 🟠 Data / ingestion
- **Integrity Risk**: its `source_data_location` points to a dated subfolder (`…/Integrity Risk/7.24.2026`), but the folder resolver builds `…/Example Data Room/Integrity Risk` (no date) → data would not be found. Fix before processing.
- **Orphaned `submitted` records** in `companies_vdr_history` (id 25 failed on the widget; 18–24 never ran) — clean up or reprocess.
- **"Dropping oversized chunk (7,502 chars > 7,500)"** — a chunk is silently dropped in ingestion (possible loss of a financial table). Review `MAX_CHUNK_CHARS` handling / split instead of drop.
- **Full re-ingestion on every VDR run** — each reprocess re-downloads SharePoint, re-parses, and re-embeds ~180K rows (expensive/slow, esp. with vision). Consider incremental ingestion / skip-if-already-ingested.

## 🟡 Robustness / tech debt
- **The real 120s serving read timeout is still not raised** — worked around by splitting the BMA into two 8K-token passes. Other agents run near the limit at ~12K; if any grows, same timeout. Find/set the correct Databricks SDK read-timeout knob so large single calls can complete.
- **Audit `flags` / `data_room_gaps` in the other assessment generators** (CQA, KPI, QoE, Legal, Forecast). The "column persisted as STRING but iterated with `.get()`" bug was fixed in BMA and FTA; it may be latent elsewhere.
- **Standardize resilient retrieval** — the profiler broke on narrow filters. Prefer `semantic_search_with_fallback` (retry without `file_name_filter`) everywhere instead of hand-rolled narrow filters.
- **Harden the *writer*** so agents never persist non-dict elements into JSON array columns (root of the intermittent `'str'.get()`), rather than only patching the render side.

## 🟢 Infrastructure / provisioning
- **`uc13.ops` was created manually this session** — fold it into `setup_vector_search` / an environment-setup step so any new catalog gets the RE2 provenance schema automatically (DDL: `eval/retrieval/scripts/apply_ops_ddl.sql`). Without it, all agents crash.
- **VS index recreation was manual** — document that the index must include `columns_to_sync` (with `company_name`, `workstream`, `priority_tier`, `source_type`) for filter pushdown, and that a pre-existing index is NOT auto-updated (drop + recreate required).
- **`uc13` vs `uc13_ale` parity** — production `uc13` has no scored eval baselines (Ale's are in `uc13_ale`). If eval/regression gating is wanted on production, run the retrieval harness against `uc13`.

## 🔵 Deployment / portability
- **Job points at a personal path** (`/Workspace/Users/hector.corro@…/Rallyday`) — not portable; breaks if the account/folder changes. Move to a shared Repo or job-level `git_source`.
- **Dead `git_source`** on the VDR job — remove it (code is served from the Git folder, not from it).
- **PR** of `feature/uc13-after-merge-job-test` → `dev`/`main` when stable.
- **Repo hygiene** — clean up the many root-level `.md` / temp files.

## ⚪ Testing / CI
- **Unit tests** for the defensive parsing (flags as JSON string, `_as_dicts`, `record_id` widget) so these regressions are caught.
- **Coverage for the VDR wrapper / entry notebook** — currently untested.

## 💲 Cost / performance
- **~$2.00–2.30 and ~1–1.7M tokens per run (~13-15 min)** for Clearsulting/GKF with vision on. Elder Care (large) cost ~$14 in a failed run (mostly embeddings on the chunk explosion) — should drop sharply once the chunk cap is validated. Monitor cost; evaluate Haiku for more agents and parse caching.
- **Concurrency** — the VDR job allows `max_concurrent_runs=3`. The shared VS index now waits instead of failing when busy (`381e1e2`), so concurrent runs are *correct*, but they still serialize on the index sync — not a true parallel speedup. Consider a per-catalog or per-company index if concurrent throughput matters.
