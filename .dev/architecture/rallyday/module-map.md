Section:      module-map
Version:      1.0.0
Last updated: 2026-06-20

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
| `databricks/jobs/scripts` | UC13 batch scripts (ingestion, classification, profiling) | `ingestion_parser.py`, `document_classifier.py`, `download_upload.py` | active |
| `databricks/jobs/notebooks` | Pipeline test and orchestration notebooks | `test_pipeline.ipynb` | active |
| `databricks/jobs/sql` | DDL and seed SQL for Garden rules table | `create_rules_table.sql`, `seed_rules.sql` | stable |
| `databricks/agents/shared` | Base classes and retrieval for Phase 3 workstream agents | `agent_base.py`, `retrieval.py` | active |
| `databricks/agents/workstreams` | One agent per diligence workstream (BMA, FTA, etc.) | `business_model_agent.py`, `financial_trends_agent.py`, … | active |
| `databricks/agents/subagents` | Nested financial sub-agents | `workstream/financial/*_sub_agent.py` | experimental |
| `databricks/agents/ingestion` | SharePoint connector and upload tools | `tools/connector.py`, `tools/uploader.py` | active |
| `databricks/workflows` | Databricks Workflow YAML definitions | `uc13_ingestion_pipeline.yml` | active |
| `scripts/` | Root dev helpers (e.g. launch backend-ai) | `dev-ai.mjs` | stable |

**Notes**

- `databricks/` UC13 pipeline and the Garden app (`frontend` + `backend-*`) share the repo but deploy independently; coupling is via Unity Catalog tables and env config, not imports. `[needs confirmation]` on whether UC13 analysis outputs will surface in the Garden UI.
- SQL DDL references `garden.rules`; runtime table ref in `backend-api` uses `{DATABRICKS_CATALOG}.{DATABRICKS_SCHEMA}.rules`. `[needs confirmation]` that catalog/schema are always set to `garden` in production.
