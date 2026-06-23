Section:      dependency-graph
Version:      1.0.0
Last updated: 2026-06-20

## Internal dependencies

| Dependent | Depends on | Nature of coupling | Risk if changed independently |
|-----------|-----------|--------------------|------------------------------|
| `frontend` | `backend-api` REST shapes | Duplicate TypeScript types for `Rule` and `Company`; no shared package | Field renames break UI without coordinated TS updates |
| `frontend` | `backend-ai` REST shapes | `NlRuleInterpretResponse` mirrors FastAPI models (camelCase) | AI response shape changes break Garden Rules AI panel |
| `frontend` | `ruleConfig.python_function` | Implicit JSON contract in `buildAiRuleApiInput.ts` | Codegen output shape change breaks rule save |
| `backend-api` | `rule_definition` JSON | `pythonFromRuleDefinitionJson` expects nested `python_function` | AI codegen changes leave python columns null |
| `backend-ai` | `backend-api` (logical) | `opportunity_silver_fields` must match `company.ts` and `companyDetailFields.ts` | NL rules reference invalid column names in generated Python |
| `backend-ai` | Databricks Genie | Two-round Genie conversation (interpret + implementation) shares `conversation_id` | SDK or Genie API behavior change breaks deny/retry flow |
| `backend-api` | Unity Catalog table names | `tableRef.ts` hard-codes `salesforce_silver.opportunity_silver`; rules use env catalog/schema | Warehouse rename breaks companies or rules queries |
| `databricks/agents/workstreams` | `databricks/agents/shared` | Shared retrieval, LLM helpers, dataclasses | `semantic_search` signature change breaks all agents |
| `databricks/jobs/scripts` | Delta table schemas | `mergeSchema=true` and `_EXPECTED_COLS` guards assume column sets | New chunk columns require coordinated parser + retrieval + agent updates |
| Garden app | UC13 pipeline | No code import; both use Databricks UC `[needs confirmation]` on future data dependencies | Accidental schema drift between `garden.*` and `uc13.*` |

## External dependencies

| Dependency | Version pinned | Role in project | Sensitivity |
|------------|---------------|-----------------|-------------|
| `express` | ^4.21.2 | backend-api HTTP server | low |
| `@databricks/sql` | ^1.14.0 | Databricks SQL warehouse queries (rules, companies) | medium |
| `react` / `react-dom` | ^19.0.0 | frontend UI | low |
| `vite` | ^6.0.3 | frontend build/dev | medium |
| `vitest` | ^3.0.5 | unit tests (api + frontend) | low |
| `fastapi` | 0.115.6 | backend-ai HTTP | low |
| `uvicorn` | 0.34.0 | backend-ai ASGI server | low |
| `pydantic-settings` | 2.7.0 | backend-ai configuration | low |
| `databricks-sdk` | >=0.40.0,<0.56.0 | Genie API via WorkspaceClient | high |
| `mlflow` | (Databricks runtime) | LLM deployments, agent serving | high |
| `msal` | >=1.28.0 | SharePoint connector auth | medium |
| Databricks model endpoints | workspace-configured | BGE embeddings, Claude Sonnet/Haiku for UC13 | high |
| Databricks Vector Search | `uc13.ingestion.embeddings_index` | Semantic retrieval for agents | high |
| Microsoft Graph API | v1.0 | SharePoint file list/download | medium |
| Unity Catalog | `uc13`, `garden`, `salesforce_silver` | All warehouse persistence | high |
