Section:      public-interface-inventory
Version:      1.0.0
Last updated: 2026-06-20

## HTTP — backend-api (Express)

| Symbol | Module | Kind | Signature summary | Consumed by | Stability |
|--------|--------|------|-------------------|-------------|-----------|
| `GET /health` | `backend-api/src/app.ts` | route | Returns service status and data-store ping | ops, frontend (indirect) | stable |
| `GET /api/config` | `backend-api/src/app.ts` | route | Returns `dataStore`, `aiBaseUrl`, cache settings | `frontend/src/api/config.ts` | stable |
| `GET /api/rules` | `backend-api/src/routes/rules.ts` | route | List all rules → `{ data: Rule[] }` | `frontend/src/api/rules.ts` | stable |
| `GET /api/rules/:id` | `backend-api/src/routes/rules.ts` | route | Get rule by numeric id | frontend | stable |
| `POST /api/rules` | `backend-api/src/routes/rules.ts` | route | Create rule from `CreateRuleInput` | frontend (form + AI save) | active |
| `PUT /api/rules/:id` | `backend-api/src/routes/rules.ts` | route | Full replace from `ReplaceRuleInput` | frontend | active |
| `PATCH /api/rules/:id` | `backend-api/src/routes/rules.ts` | route | Partial update from `UpdateRuleInput` | frontend | active |
| `DELETE /api/rules/:id` | `backend-api/src/routes/rules.ts` | route | Delete rule (204) | frontend | stable |
| `GET /api/companies` | `backend-api/src/routes/companies.ts` | route | List companies from opportunity silver | `frontend/src/api/companies.ts` | stable |
| `GET /api/companies/:id` | `backend-api/src/routes/companies.ts` | route | Get company by id | frontend | stable |
| `createApp` | `backend-api/src/app.ts` | function | Build Express app with injectable services (tests) | `src/index.ts`, tests | stable |

## HTTP — backend-ai (FastAPI)

| Symbol | Module | Kind | Signature summary | Consumed by | Stability |
|--------|--------|------|-------------------|-------------|-----------|
| `GET /health` | `backend-ai/app/main.py` | route | Service status + `rulesAiMode` | ops | stable |
| `POST /api/ai/rules/interpret` | `backend-ai/app/routes/rules_nl.py` | route | NL prompt → summary + `ruleConfig` + session | `frontend/src/api/nlRules.ts` | active |
| `POST /api/ai/rules/sessions/{id}/deny` | `backend-ai/app/routes/rules_nl.py` | route | Retry interpretation with feedback | frontend | active |

## backend-api — services & repositories

| Symbol | Module | Kind | Signature summary | Consumed by | Stability |
|--------|--------|------|-------------------|-------------|-----------|
| `RulesService` | `backend-api/src/services/rulesService.ts` | class | CRUD + validation + python field enrichment | `routes/rules.ts` | active |
| `CompaniesService` | `backend-api/src/services/companiesService.ts` | class | Read-only company queries | `routes/companies.ts` | stable |
| `RulesRepository` | `backend-api/src/repositories/rulesRepository.ts` | type | `findAll`, `findById`, `create`, `replace`, `delete` | `RulesService`, tests | stable |
| `createRulesRepository` | `backend-api/src/repositories/createRulesRepository.ts` | function | Factory: memory \| databricks + optional TTL cache | `app.ts` | stable |
| `createCompaniesRepository` | `backend-api/src/repositories/createCompaniesRepository.ts` | function | Factory: memory \| databricks + cache | `app.ts` | stable |
| `pythonFromRuleDefinitionJson` | `backend-api/src/services/ruleDefinition.ts` | function | Extract `python_function` from `rule_definition` JSON string | `RulesService` | active |
| `rulesTableRef` | `backend-api/src/db/tableRef.ts` | function | `{catalog}.{schema}.rules` FQN | Databricks repositories | stable |
| `opportunitySilverTableRef` | `backend-api/src/db/tableRef.ts` | function | `salesforce_silver.opportunity_silver` FQN | companies repository | stable |
| `RULE_SOURCES`, `RULE_STATUSES` | `backend-api/src/types/rule.ts` | constant | Allowed enum values for rules | services, SQL CHECK | stable |

## backend-ai — services

| Symbol | Module | Kind | Signature summary | Consumed by | Stability |
|--------|--------|------|-------------------|-------------|-----------|
| `interpret_prompt` | `backend-ai/app/services/genie_rules.py` | function | `(settings, prompt, …) → summary, rule_config, raw, conv_id, msg_id` | `routes/rules_nl.py` | active |
| `parse_rules_interpretation` | `backend-ai/app/services/response_parser.py` | function | Parse Genie/model text → `(summary, rule_config dict)` | `genie_rules.py` | active |
| `ensure_rule_python_function` | `backend-ai/app/services/rule_python_codegen.py` | function | Attach valid `python_function` block to rule config | `genie_rules.py` | active |
| `normalize_rule_config` | `backend-ai/app/opportunity_silver_fields.py` | function | Canonicalize condition field names against silver schema | codegen, genie pipeline | active |
| `get_session_store` | `backend-ai/app/services/session_store.py` | function | In-process NL rule session store (interpret/deny) | `rules_nl.py` | active |
| `resolve_rules_ai_mode` | `backend-ai/app/config.py` | function | `auto` \| `mock` \| `genie` from env | health, routes | stable |

## frontend — API helpers

| Symbol | Module | Kind | Signature summary | Consumed by | Stability |
|--------|--------|------|-------------------|-------------|-----------|
| `apiGet`, `apiPost`, … | `frontend/src/api/client.ts` | function | Typed fetch wrapper for backend-api | rules, companies APIs | stable |
| `aiPost` | `frontend/src/api/aiClient.ts` | function | Typed fetch wrapper for backend-ai | `nlRules.ts` | stable |
| `buildAiRuleCreateInput` | `frontend/src/utils/buildAiRuleApiInput.ts` | function | Map AI `ruleConfig` → `CreateRuleInput` | Garden Rules AI panel | active |
| `buildAiRuleReplaceInput` | `frontend/src/utils/buildAiRuleApiInput.ts` | function | Map AI `ruleConfig` → `ReplaceRuleInput` | Garden Rules AI panel | active |

## databricks — agents & jobs

| Symbol | Module | Kind | Signature summary | Consumed by | Stability |
|--------|--------|------|-------------------|-------------|-----------|
| `semantic_search` | `databricks/agents/shared/retrieval.py` | function | Vector search + keyword fallback over `uc13.ingestion.embeddings_index` | all Phase 3 agents | active |
| `WorkstreamAgent` | `databricks/agents/shared/agent_base.py` | class | Base for diligence agents; `run(company_name, spark, llm_endpoint)` | workstream agents | active |
| `ingestion_parser.main` | `databricks/jobs/scripts/ingestion_parser.py` | function | Full-rebuild parse: docs → chunks + embeddings | notebooks, jobs | active |
| `ensure_coverage.ingest_missing` | `databricks/jobs/scripts/ensure_coverage.py` | function | Append-only gap fill for missing workstream coverage | notebooks | active |
| SharePoint connector | `databricks/agents/ingestion/tools/connector.py` | module | MSAL auth, list/download from SharePoint | `download_upload.py` | active |
