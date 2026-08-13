Section:      module-map
Version:      2.0.0
Last updated: 2026-07-28

| Module path | Role | Key files | Stability |
|-------------|------|-----------|-----------|
| `frontend/` | React SPA — My Garden (companies), Garden Rules (form + NL AI editor) | `App.tsx`, `pages/`, `api/`, `components/rules/` | active |
| `frontend/src/api` | HTTP clients for backend-api and backend-ai | `client.ts`, `aiClient.ts`, `rules.ts`, `nlRules.ts` | active |
| `frontend/src/components` | Layout and domain UI (companies, rules) | `layout/`, `companies/`, `rules/` | active |
| `frontend/src/pages` | Route-level screens | `MyGarden.tsx`, `GardenRules.tsx`, `Dashboard.tsx` | active |
| `frontend/src/utils` | Display, search, and AI→API payload mapping | `buildAiRuleApiInput.ts`, `companyDetailFields.ts` | active |
| `backend-api/` | Express REST API for rules and companies; pluggable data store | `src/app.ts`, `src/index.ts` | active |
| `backend-api/src/routes` | HTTP route handlers (thin) | `rules.ts`, `companies.ts` | stable |
| `backend-api/src/services` | Business logic and validation | `rulesService.ts`, `companiesService.ts`, `ruleDefinition.ts` | active |
| `backend-api/src/repositories` | Persistence adapters (memory / Databricks SQL) | `rulesRepository.ts`, `companiesRepository.ts`, `create*Repository.ts` | active |
| `backend-api/src/stores` | Data-store abstraction and health ping | `DataStore.ts`, `memoryStore.ts`, `databricksStore.ts` | stable |
| `backend-api/src/db` | Databricks SQL client and table name helpers | `databricksClient.ts`, `tableRef.ts` | stable |
| `backend-api/src/types` | API entity models and input DTOs | `rule.ts`, `company.ts`, `baseApiModel.ts` | active |
| `backend-ai/` | FastAPI service for natural-language Garden rules (Genie / mock) | `app/main.py` | active |
| `backend-ai/app/routes` | AI HTTP endpoints | `rules_nl.py` | active |
| `backend-ai/app/services` | Genie orchestration, parsing, codegen, sessions | `genie_rules.py`, `response_parser.py`, `rule_python_codegen.py` | active |
| `backend-ai/app/prompts` | Genie instruction prompts for rules engine | `rules_engine.py` | active |
| `backend-ai/app` | Canonical opportunity-silver field registry for NL rules | `opportunity_silver_fields.py` | active |
| `databricks/jobs/scripts` | UC13 batch scripts — ingestion, classification, profiling, VS setup, **pipeline entry points** | `ingestion_parser.py`, `document_classifier.py`, `setup_vector_search.py`, `download_upload.py`, `company_profiler.py`, `run_ingestion_pipeline.py`, `run_diligence_pipeline.py`, `run_full_pipeline.py`, `run_vdr_pipeline.py`, `md_to_word.py`, `vs_filter_pushdown_probe.py` | active |
| `databricks/jobs/notebooks` | Pipeline test, orchestration, and A/B eval harness | `test_pipeline.ipynb` | active |
| `databricks/jobs/sql` | DDL and seed SQL for Garden rules table | `create_rules_table.sql`, `seed_rules.sql` | stable |
| `databricks/agents/shared` | Base classes, retrieval hub (`semantic_search` → `RouteResult`), pipeline run context (M-RE2 + **sqlite→Delta spark=**), shared types, consolidated fallback | `agent_base.py`, `retrieval.py`, `run_context.py`, `_types.py`, `fallback.py`, `sql_utils.py` | active |
| `databricks/agents/workstreams` | Phase 3–4 diligence agents — BMA, FTA, CQA, KPI, Legal, QoE, **forecast**, **cross_analysis** | `business_model_agent.py`, `financial_trends_agent.py`, `legal_contracts_agent.py`, `quality_of_earnings_agent.py`, `forecast_agent.py`, `cross_analysis_agent.py`, … | active |
| `databricks/agents/orchestration` | **Hector DAG** — wave-scheduled Phase 3→5 pipeline, result cards, diligence memo | `pipeline.py` (`PipelineOrchestrator`, `run_pipeline`, `to_result_card`), `orchestrator_agent.py` | active |
| `databricks/agents/exec_summary` | **Rainmaker executive summary** hub (renamed from `agents.orchestrator` T1 merge) — bundle build, Rev3 templates, quality gates, DAG bridge | `bundle_builder.py`, `field_mapping.py`, `tldr_compress.py`, `pipeline_entry.py` (`build_exec_summary`), `orchestrator_bundle.schema.yaml`, `templates/`, `demo_walkthrough.py` | active |
| `databricks/agents/orchestrator` | Legacy duplicate of pre-rename package — **deprecated**; production imports use `agents.exec_summary` | (mirror files with stale `agents.orchestrator` imports) | deprecated |
| `databricks/agents/subagents/workstream/financial` | FTA autonomous sub-agents (revenue, OPEX, EBITDA) + shared retrieval adapter + basis cross-check | `*_sub_agent.py`, `context_utils.py`, `basis_cross_check.py`, `shared_prompts.py` | active |
| `databricks/agents/ingestion` | SharePoint connector and upload tools | `tools/connector.py`, `tools/uploader.py` | active |
| `databricks/workflows` | Databricks Workflow YAML definitions | `uc13_ingestion_pipeline.yml`, `uc13_diligence_pipeline.yml`, `uc13_full_pipeline.yml`, `vdr_pipeline.yml` | active |
| `eval/retrieval/` | RE² measurement package — intent registry (57 intents), gold labels, harness, eval store, provenance, **promotion gate** | `harness.py`, `store.py`, `provenance.py`, `promotion_gate.py`, `scope_resolver.py`, `registry_extractor.py`, `models.py`, `intent_registry.yaml`, `gold_labels/`, `scripts/`, `harness_cli.py`, `tests/` | active |
| `eval/BMA/`, `eval/CQA/`, `eval/KPI/`, `eval/QOE/`, `eval/PROFILER/`, `eval/LCA/` | Per-agent **golden checklists** (Elder Care) + promotion-gate evidence | `golden_checklist_elder_care.md` | stable |
| `.dev/scorecards/` | Eval-harness promotion scorecards and INDEX | `INDEX.md`, `uc13-eval-harness-all-agents_*_elder-care_*.md` | active |
| `tests/` | Repo-root pytest — agents, retrieval, exec_summary, pipeline, golden checklists, architecture falsifiers | `test_bundle_builder.py`, `test_tldr_compression.py`, `test_run_context.py`, `test_pipeline_agent_run_context.py`, `test_pipeline_entry.py`, `test_golden_checklist_elder_care.py`, `test_promotion_gate.py` (under `eval/retrieval/tests/`), `test_notebook_symbol_references.py`, `fixtures/elder_care_*.yaml` | active |
| `scripts/` | Root dev helpers (e.g. launch backend-ai) | `dev-ai.mjs` | stable |

**Notes**

- `databricks/` UC13 pipeline and the Garden app (`frontend` + `backend-*`) share the repo but deploy independently; coupling is via Unity Catalog tables and env config, not imports. `[needs confirmation]` on whether UC13 analysis outputs will surface in the Garden UI.
- **Dual orchestration model (post hector-ui-pipeline-merge):** `agents.orchestration` runs the diligence DAG (Phase 3→5) and writes `analysis.diligence_report`; `agents.exec_summary` builds the Rainmaker Rev3 one-pager + full report from completed agent outputs via `build_exec_summary()`. They are composed sequentially in `run_full_pipeline.py` / `run_vdr_pipeline.py`, not merged into one orchestrator class.
- **T1 rename (2026-07-24):** `agents.orchestrator` → `agents.exec_summary`. Notebook and tests assert zero surviving `agents.orchestrator` imports in active paths (`tests/test_notebook_symbol_references.py`).
- **sqlite→Delta provenance (2026-07-27):** `open_agent_run(spark=)` binds `DeltaEvalStore` on worker threads; `resolve_store()` fail-closed when `RE2_STORE_BACKEND=delta` without Spark. All 7 instrumented agent `main()` + profiler pass `spark=`.
- **Eval harness M1–M4 (2026-07-21):** Golden checklists for BMA/CQA/KPI/QoE/Profiler; `evaluate_promotion` gate; `.dev/scorecards/` INDEX with Elder Care baselines. Program `uc13-eval-harness-all-agents` complete.
- **Rainmaker Rev3 (2026-07-22):** Compressed template restructure (`thesis_bullets`, `key_watchouts`, `workforce_notes`); Elder Care validation ACCEPT at 1,344 words.
- **Post-merge regressions (2026-07-28):** BMA Haiku truncation + `flags` JSON string parse fixed; parallel DAG e2e `run_id=1074138209208842` — 9 SUCCESS / 0 FAILED. See `post_merge_regressions.md`.
- SQL DDL references `garden.rules`; runtime table ref in `backend-api` uses `{DATABRICKS_CATALOG}.{DATABRICKS_SCHEMA}.rules`. `[needs confirmation]` that catalog/schema are always set to `garden` in production.
- **Catalog convention:** production scripts default `uc13`; eval/notebook/harness use `uc13_ale` — `tests/test_catalog_convention.py` is PG3 gate.
- **M-PHV4 retrieval consolidation (2026-07-15):** `_TYPE_ORDER` dedup, FTA+harness fallback unification, R-08 join integrity; item 29 (`vs_metadata_filters` default flip) **not activated**.
