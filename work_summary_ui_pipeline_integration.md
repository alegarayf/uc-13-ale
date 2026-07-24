# Work Summary — `feature/ui-pipeline-integration` (since June 20, 2026)

> Branch chain: `develop` → `feature/databricks-new-agents-qoef` → `feature/databricks-orchestrator-dag` → `feature/ui-pipeline-integration`
> Author: Hector Corro
> Period covered: 2026-06-28 → 2026-07-21
> Last updated: 2026-07-23

---

## Methodology note

`feature/ui-pipeline-integration` is the tip of a linear chain of three feature branches, all created after June 20, 2026. It was **not** diffed against the current tip of `develop`, because `develop` has advanced independently with 72 unrelated commits (KPI dashboards, auth, general UI work) since the two histories split.

Instead, this summary is built from the **merge-base** — the exact commit where the chain diverged from `develop`:

```bash
git merge-base develop feature/ui-pipeline-integration
# → 0cb8791c2fce9e22098b4b1cf4e3add01b58a59d  ("Fixing auth issues", 2026-06-23)

git log --oneline 0cb8791^..feature/ui-pipeline-integration   # commit list
git diff 0cb8791 feature/ui-pipeline-integration               # file diff
```

This isolates exactly what was built in this line of work, with no noise from `develop`'s parallel changes.

---

## Headline numbers

| Metric | Value |
|---|---|
| Commits since divergence | **36** |
| Date range | 2026-06-28 → 2026-07-21 (24 days) |
| Files changed | 30 (14 added, 16 modified) |
| Lines added / removed | +10,985 / -2,410 |
| `develop` commits in the same window (parallel, unrelated) | 72 |

---

## Timeline of major work

### 1. Quality of Earnings (QoFE) agent hardening — Jun 28–30

- Defaulted the extraction endpoint to **Sonnet 4.6** and set an explicit `max_tokens` to stop silent addback-schedule truncation.
- Fixed a **SQL injection / breakage risk**: `company_name` is now parameterized instead of inlined into SQL for quoted company names.
- Wired a working-capital passthrough, added period-end maneuver flags, and added a Net Working Capital (NWC) peg scope item.
- Added two new adjustment flag types per client guideline 6: `unusual_credits_rebates_refunds` and `ar_aging_writeoffs`.
- Added `generate_qoe_assessment()` — a Markdown QoE report generator mirroring the existing Financial Trends Agent (FTA) pattern — plus a Word export (`test_pipeline.ipynb` Cells 17b/17c).
- Fixed the ingestion connector path and added a new table schema for the QoFE agent.

**Files touched:** `quality_of_earnings_agent.py` (+824/-lines), `agents/ingestion/tools/connector.py`, `CLAUDE.md`, `test_pipeline.ipynb`.

### 2. Customer Quality Agent (CQA) — full guideline 2 coverage — Jun 29–30

- Extended CQA with complete guideline 2 coverage: cohort analysis, customer health, contract terms, revenue mix, renewals, and gross margin per customer.
- Added **Task 5b**: profitability outlier detection inside the QoE workstream.
- Added `generate_customer_quality_assessment()` plus notebook cells for the Markdown report, Word export, and field inspection (Cells 14b/14c/14d).
- Fixed table schema and a module-method bug in the agent.

**Files touched:** `customer_quality_agent.py` (+841/-lines), `test_pipeline.ipynb`.

### 3. KPI Agent enhancements — Jun 30

- Shipped an "enhanced" KPI agent and a new schema for KPI agent execution/output.

**Files touched:** `kpi_agent.py` (+1,022/-lines).

### 4. Phase 3→5 orchestration DAG — new subsystem — Jul 7–10

The largest single addition in this branch: a full DAG-based orchestrator that runs the Phase 3 workstream agents, reconciles them, and assembles the final diligence memo.

- **New files:**
  - `agents/orchestration/pipeline.py` (565 lines) — `PipelineOrchestrator`: the Phase 3→5 DAG, wave-based parallelism (`ThreadPoolExecutor`), per-agent retries, failure isolation (hard/soft dependency skip vs. degraded run), and the run manifest.
  - `agents/orchestration/orchestrator_agent.py` (656 lines) — Phase 5 agent that assembles the final Markdown + Word diligence memo.
  - `agents/workstreams/forecast_agent.py` (1,300 lines) — new Phase 3 agent: assumption credibility scoring (Supported/Plausible/Stretch), revenue build vs. trailing performance, downside sensitivities.
  - `agents/workstreams/cross_analysis_agent.py` (836 lines) — new Phase 4 agent: cross-workstream reconciliation, CIM-claims vs. data-room checks, top-10 issue ranking.
  - `jobs/scripts/run_diligence_pipeline.py` (78 lines) — Phase 3-5 entry point.
  - `jobs/scripts/run_full_pipeline.py` (228 lines) — Phase 1-5 end-to-end entry point.
  - `jobs/scripts/run_ingestion_pipeline.py` (297 lines) — Phase 1-2 entry point (download → classify → parse → coverage backfill → profile).
  - `workflows/uc13_diligence_pipeline.yml` (75 lines) — single-task Databricks job wrapping the DAG.
  - `workflows/uc13_full_pipeline.yml` (185 lines) — two-task end-to-end job (ingestion → diligence).
- **Follow-up fixes to the new orchestrator:**
  - Fixed Spark session propagation into `ThreadPoolExecutor` worker threads (twice — session registration, then current-session injection).
  - Added a thread handler shared across all workstream agents.
  - Fixed a time-format bug in the orchestrator agent.
  - Defaulted DAG execution to Tier 1 + Tier 2 documents.
  - Fixed report schema/format and the table index for multi-report scenarios.
  - Marked the forecast report (`frpt`) flag as done in the report-flags logic.
  - Added missing dependencies to `requirements.txt` for the Databricks job runtime.
  - Fixed `__file__` not being defined when running inside a Databricks job context (as opposed to a notebook).

**Files touched:** the 9 new files above, plus `agent_base.py`, `business_model_agent.py`, `financial_trends_agent.py`, `legal_contracts_agent.py`, `test_pipeline.ipynb`, `requirements.txt`.

### 5. Virtual Data Room (VDR) pipeline — Jul 14–16

A parallel workstream to generate a standalone VDR-level report (separate from the diligence memo).

- **New files:**
  - `jobs/scripts/run_vdr_pipeline.py` (630 lines) — VDR report pipeline entry point.
  - `workflows/vdr_pipeline.yml` (86 lines) — Databricks job for the VDR pipeline.
- Delivered real PDF output with condensed report sections (`feat(vdr)`).
- Added LLM token-usage tracking into `companies_vdr_history` (`feat(tokens)`).
- Fixed an italic-regex bug that produced malformed XML in ReportLab PDF paragraphs.
- Added a new token-count storage path to a dedicated Volume and stripped invalid colons from file names.
- Added the DOCX write path for the VDR pipeline.
- Fixed a file-duplication bug and issues with max chunk size / capped sizes.

**Files touched:** `run_vdr_pipeline.py`, `vdr_pipeline.yml`, `ingestion_parser.py`, `document_classifier.py`, `ensure_coverage.py`, `company_profiler.py`.

### 6. Cost estimation — Jul 21

- Added endpoint-execution cost estimation to the VDR pipeline (most recent commit on the branch, `fdca51f`).

---

## Full file inventory (merge-base → `feature/ui-pipeline-integration`)

### Added (14 files)

| File | Lines |
|---|---|
| `agents/orchestration/orchestrator_agent.py` | 656 |
| `agents/workstreams/forecast_agent.py` | 1,300 |
| `agents/workstreams/cross_analysis_agent.py` | 836 |
| `agents/orchestration/pipeline.py` | 565 |
| `jobs/scripts/run_vdr_pipeline.py` | 630 |
| `jobs/scripts/run_full_pipeline.py` | 228 |
| `jobs/scripts/run_ingestion_pipeline.py` | 297 |
| `jobs/scripts/run_diligence_pipeline.py` | 78 |
| `workflows/uc13_full_pipeline.yml` | 185 |
| `workflows/vdr_pipeline.yml` | 86 |
| `workflows/uc13_diligence_pipeline.yml` | 75 |
| `Guidelines/Austin_guidelines_bussines_type.txt` | 30 |
| `agents/shared/sql_utils.py` | 19 |
| `agents/orchestration/__init__.py` | 0 |

### Modified (16 files)

| File | Delta |
|---|---|
| `jobs/notebooks/test_pipeline.ipynb` | +5,152 (net; notebook JSON) |
| `agents/workstreams/kpi_agent.py` | +1,022 |
| `agents/workstreams/quality_of_earnings_agent.py` | +824 |
| `agents/workstreams/customer_quality_agent.py` | +841 |
| `databricks/CLAUDE.md` | 148 |
| `jobs/scripts/ingestion_parser.py` | 147 |
| `jobs/scripts/ensure_coverage.py` | 96 |
| `agents/shared/agent_base.py` | 89 |
| `agents/ingestion/tools/connector.py` | 23 |
| `jobs/scripts/document_classifier.py` | 18 |
| `agents/workstreams/business_model_agent.py` | 17 |
| `jobs/scripts/company_profiler.py` | 10 |
| `agents/workstreams/financial_trends_agent.py` | 10 |
| `requirements.txt` | 3 |
| `agents/workstreams/legal_contracts_agent.py` | 5 |
| `agents/shared/retrieval.py` | 5 |

---

## Net effect on the pipeline

Before this branch, the repo covered Phase 1-2 (ingestion) and a partial set of Phase 3 workstream agents. This branch:

1. Completed/hardened three Phase 3 agents (QoFE, CQA, KPI).
2. Introduced Phase 3's remaining agents (**Forecast**, **Cross-Analysis**) and the entire **Phase 4-5 orchestration layer** (`PipelineOrchestrator` DAG + Orchestrator memo agent), turning the project from a set of independent agents into an end-to-end, DAG-driven diligence pipeline with failure isolation and a run manifest.
3. Added a second, independent deliverable pipeline (**VDR report generation**) with PDF/DOCX output and LLM cost/token tracking.
4. Added three new Databricks Workflow job definitions (`uc13_full_pipeline.yml`, `uc13_diligence_pipeline.yml`, `vdr_pipeline.yml`) and the corresponding runner scripts, so all of the above is deployable as Databricks Jobs, not just runnable from a notebook.

---

## Caveat: divergence from `develop`

`develop` has moved 72 commits ahead of the merge-base (`0cb8791`) in this same window. Breaking those 72 commits down by top-level folder:

| Folder | Files changed on `develop` |
|---|---|
| `frontend/` | 210 |
| `backend-api/` | 163 |
| `backend-ai/` | 14 |
| `databricks/` | 11 |
| root (`package.json`, `README.md`, `app.yml`, `.env.example`, `.cursor/`, `docs/`) | 6 |

> **This branch's work is entirely scoped to `databricks/`, and it has zero file-level overlap with `develop`'s parallel changes.** The 11 `databricks/` files touched on `develop` are all under `databricks/jobs/sql/` (garden signals, sourcing criteria, user configuration, group management — an unrelated feature area) and do not intersect with any of the 30 files listed in this summary. In other words: nothing you built in this branch was touched or duplicated by anyone else on `develop` — a rebase/merge before the PR is still recommended as good hygiene, but it is not expected to produce conflicts in `databricks/`.
