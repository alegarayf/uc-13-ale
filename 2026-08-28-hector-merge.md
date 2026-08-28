# Ale `dev3` → Hector `feature/vdr-cim-all-flow-connection`

Merge + deploy only. Not a team status. Local file — do not commit.

**Remote:** `hector` = `https://github.com/Nimble-Gravity/Rallyday.git`  
**Merge-base:** `f99f720`  
**Do not force-push.** Hector is **5 commits ahead**. A push of `dev3` onto this branch name without merging drops the unified VDR job.

Hector-only (keep):

| SHA | What |
|---|---|
| `30feffe` | Unify CIM-preview **and** full-room into one job |
| `7795af0` | Austin R2 executive-review content |
| `85aa9c4` | CQA `revenue_quality` field-name fix |
| `3abf62e` | KPI `end_market_mix` / concentration overlay |
| `5ce3fca` | FTA phantom P&L column + location-overwritten gross margin |

Ale is ~219 commits ahead of that base (eval program + iterate-pack). Most of that is lab. It must not clobber the five above.

---

## 1. Catalogs — this is the deploy risk

Three names. Not interchangeable. `doc_id` hashes the catalog; data does not migrate.

| Catalog | Role now | Who writes it |
|---|---|---|
| **`uc13_preview`** | **Live VDR job, both modes** | Hector unified runner (`VDR_CATALOG`). CIM-scoped **and** full-room. |
| **`uc13`** | Frozen production | Legacy `run_vdr_pipeline.py` only (hardcoded). Do **not** point the UI job here. No Appendix A promotion in this merge. |
| **`uc13_ale`** | Ale lab / eval | `test_pipeline.ipynb` + **`uc13_ingestion_pipeline.yml` only**. Do **not** point the UI job here. |

YAML defaults are split (same on both trees): ingestion job → `uc13_ale`; diligence + full pipeline jobs → `uc13`. Script `main()` defaults are `uc13`. The live UI job ignores all of that and writes `uc13_preview`.

Hector’s standing call: `uc13_preview` is the only catalog already on the M0–M4 schema and proven end-to-end. Production `uc13` is still documented as **not** M0–M4 ready (2026-08-10; no later retract). Do not retarget the UI job there this merge.

`.env.example`, `app.yml`, `backend-api`, `frontend`: **no diff** vs Hector. Backend `DATABRICKS_CATALOG` is garden/rules SQL, not the diligence catalog. Leave it.

`apply_ops_ddl.py` CLI default is `uc13`. Pass the catalog you mean (`uc13_preview` for the live job).

---

## 2. What the live job actually runs

- Job name **VDR Diligence Pipeline**, id **`617196299594076`**.
- Code source = Databricks **Git folder** `Rallyday` (Hector’s workspace path), **not** the job `git_source` block.
- Live task notebook: `jobs/notebooks/run_vdr_rainmaker_job` → `run_vdr_rainmaker.py`.
- `vdr_pipeline.yml` still describes `run_vdr_job` / `run_vdr_pipeline.py`. That YAML is **stale vs the deployed job**. Check `databricks jobs get 617196299594076` before assuming.
- YAML examples still show notebook param `"id"`. The notebook requires **`record_id`** (`id` is a fallback).
- **No job/task parameters.** UI sends notebook widgets. Adding fixed params blocks the UI trigger.

Widgets that matter after Hector’s unify:

| Widget | Default | Meaning |
|---|---|---|
| `table_name` | `rallyday_partners_llc.default.companies_vdr_history` | VDR record table |
| `record_id` / `id` | (required) | Row to process |
| `special_folder` | `""` | Optional CIM-detection folder |
| `no_cim_mode` | **`full`** | No CIM → full Phase 1–5. `noop` = old message-only kill switch |
| `vision_endpoint` | Haiku | `""` disables vision |

Decision (Hector runner):

- CIM files found (or `special_folder` listing) → CIM-scoped ingest (`file_whitelist`, `force="company"`, `parse_priority_tiers="all"`) → 7 agents, **`run_orchestrator=False`** → `build_rainmaker_summary`.
- None, and `no_cim_mode="full"` → `run_full_pipeline` on the same catalog (no force, no whitelist). Fail-closed: `ingestion_parser` must be `SUCCESS` and ≥1 diligence agent must succeed.
- `no_cim_mode="noop"` → old skip.

Both write **`uc13_preview`**.

Outputs under `/Volumes/rallyday_partners_llc/default/vdr/{company}/{ts}/`:

- both modes: `executive_summary.pdf`, `rainmaker_opportunity_summary.html`
- full-room only: `full_report.docx`
- Rev3 `executive_summary.docx` may be written on disk by `run_full_pipeline`; **not** copied to the VDR volume.

---

## 3. Conflict resolution (only the files that matter)

Ale’s tree still has the **old** rainmaker POC (CIM-only, `PREVIEW_CATALOG`, no full-room fallback, no `no_cim_mode`). Take **Hector** for the VDR path.

Git will only auto-conflict **`databricks/CLAUDE.md`**. Take Hector’s **VDR-wiring** paragraphs only. Keep Ale’s C37 + eval-harness section. Drop Hector’s “BMA is split into TWO bounded passes / do not collapse to a single 16K call.” Everything else is disjoint after merge-base — checkout direction can silently drop a side. Do **not** point the Git folder at raw `dev3`.

| File | Keep |
|---|---|
| `run_vdr_rainmaker.py` / `run_vdr_rainmaker_job.py` / `vdr_rainmaker_poc.yml` | **Hector** (`VDR_CATALOG`, `_run_full_room_flow`, `no_cim_mode`, timeout 32400) |
| `exec_summary/rainmaker_entry.py`, `absence_check.py` + their tests | **Hector** (Ale does not have them) |
| `field_mapping.py`, `rainmaker_view.py`, `rainmaker_narrative.py`, template | **Hector**. This is where 85aa9c4 / 3abf62e / 5ce3fca live: CQA `concentration_summary`/`payor_mix` (Ale still reads missing `customer_concentration`), KPI overlay mix when CQA is blank, drop phantom P&L periods, prefer unqualified GM so a location line cannot overwrite consolidated. |
| `revenue_sub_agent.py` | **Ale** (dedupe + `source_location`). Hector did not change this file after merge-base. |
| `business_model_agent.py` | **Ale C37**. Hector’s tip still has the **rejected** 2026-08-18 design: unconditional two-pass (`_GROUP_A`/`_GROUP_B`) **and** `_TOTAL_BUDGET = 90_000` CIM→T1→other input cap. His 5 commits did not touch the file; taking his copy re-lands that hunk. |
| `legal_contracts_agent.py` | **Ale** (2-query employment/IP, empty `ip_register` → `corpus_absent`) |
| `ingestion_parser.py` | **Ale** (SpreadsheetML / legacy `.xls`) |
| `agent_base.py` | **Ale** (`MLFLOW_HTTP_REQUEST_TIMEOUT=1800`) |
| `eval/**` + C37 tests | Lab / routing tests. Ship the tests; do not run eval against `uc13` or `uc13_preview` as a prod smoke. |

`kpi_agent.py` / `financial_trends_agent.py` / `customer_quality_agent.py` / `run_vdr_pipeline.py` / `run_vdr_job.py` / `cim_detection.py`: no tree-level diff.

---

## 4. After the merge, before anyone clicks Run

1. Merge Hector’s 5 into Ale (or rebase), resolve per §3, then push to `hector` `feature/vdr-cim-all-flow-connection`. No `--force`.
2. Point the Git folder at that branch: `databricks repos update <id> --branch feature/vdr-cim-all-flow-connection`. This swaps code for **both** VDR jobs on the next trigger, including mid-run if a serverless task is live.
3. Confirm job `617196299594076` still uses `run_vdr_rainmaker_job` and has **no** task parameters.
4. Confirm `uc13_preview` has: M0–M4 tables (`doc_status`, `sync_state`, `doc_id` on `doc_relevance`), `{catalog}.ops` from `eval/retrieval/scripts/apply_ops_ddl.sql` (agents crash without it), vector index with filter columns (`company_name`, `workstream`, `priority_tier`, `source_type`, `file_name`, `chunk_id`, `doc_id`). A pre-existing index does **not** pick up new columns — drop + recreate if filters fail.
5. Do **not** `bundle deploy` `uc13_ingestion_pipeline.yml` as a substitute for the UI job. Its catalog default is `uc13_ale`. Diligence/full YAML default `uc13` is equally wrong for this job.
6. Smoke: one CIM company (preview path) and one no-CIM company (`no_cim_mode=full`). Check `created_at` on chunks, not just job SUCCESS — a failed parse can still look green and serve stale rows. Serverless may lack `python-docx`; PDF + `.md` memo can still land.

---

## 5. What this push also does (gitignore)

Root operator dumps are now ignored and **unstaged from the index** (files stay on disk). `.dev/` and `.claude/` were already ignored.

Leaving the tree: analysis HTML/canvas, CIM-vs-VDR writeup, horizon/eval-next/prompt-registry notes, runbooks, `brief_eval_*`, `_confidence_score_draft.md`, harness report JSONs, signoff stdout/collect dumps.

Still tracked (keep): `AGENTS.md`, `CHANGELOG.MD`, `README.md`, `app.yml`, `.env.example`, `conftest.py`, `connector.py`, `package.json`, `pytest.ini`, `tsconfig.base.json`, `.cursor/skills/databricks-access/SKILL.md` (force-tracked on purpose), `signoffs/*.md`, `eval/retrieval/reports/.gitkeep`.

Hector’s `pending2.md` / `sqlite_removal.md` are already ignore-listed — do not re-add them.

---

## 6. Out of scope this merge

- Promoting `uc13_preview` → `uc13`
- Rewiring the UI job back to `run_vdr_job`
- Changing YAML catalog defaults from `uc13_ale` to `uc13`
- Shipping `.dev/` or eval warehouse state
- Making BMA two-pass the default
