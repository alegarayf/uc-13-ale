Section:      known-coupling-surfaces
Version:      1.0.0
Last updated: 2026-06-20

```
Surface:      OPPORTUNITY_SILVER_FIELDS / Company type field list
Shared by:    backend-ai/app/opportunity_silver_fields.py ↔ backend-api/src/types/company.ts ↔ frontend/src/utils/companyDetailFields.ts
Failure mode: NL-generated rule conditions reference non-existent columns; UI shows fields API does not return
Confirmed:    yes — explicit comment in opportunity_silver_fields.py ("Keep in sync with …")
```

```
Surface:      salesforce_silver.opportunity_silver table name
Shared by:    backend-api/src/db/tableRef.ts ↔ backend-ai OPPORTUNITY_SILVER_VIEW constant
Failure mode: Companies query or NL rule codegen targets wrong relation
Confirmed:    yes — identical string in both modules
```

```
Surface:      Rule python_function JSON shape { source, entrypoint }
Shared by:    backend-ai rule_python_codegen.py ↔ frontend buildAiRuleApiInput.ts ↔ backend-api ruleDefinition.ts
Failure mode: python_source/python_entrypoint columns empty after save despite valid AI output
Confirmed:    yes — parallel extraction logic in three languages
```

```
Surface:      rule_definition serialized as JSON string (not JSON column in API)
Shared by:    backend-api Rule entity ↔ frontend types ↔ AI ruleConfig stringify
Failure mode: Double-encoding or parse failures in display/search utilities
Confirmed:    yes — grep across rule.ts, buildAiRuleApiInput, rulesService
```

```
Surface:      RULE_STATUSES / RULE_SOURCES enum values
Shared by:    backend-api/src/types/rule.ts ↔ SQL CHECK in create_rules_table.sql ↔ frontend rule forms
Failure mode: Insert rejected by warehouse or UI sends invalid status/source
Confirmed:    yes — matching literal sets ('active'|'inactive', 'form'|'ai')
```

```
Surface:      DATABRICKS_* environment variable names
Shared by:    root .env.example ↔ backend-api config.ts ↔ backend-ai config.py (host/token/genie space)
Failure mode: AI service in mock mode while API uses Databricks store, or Genie auth mismatch
Confirmed:    yes — backend-ai falls back to DATABRICKS_SERVER_HOSTNAME / DATABRICKS_TOKEN
```

```
Surface:      garden.rules vs {catalog}.{schema}.rules
Shared by:    databricks/jobs/sql/create_rules_table.sql (garden.rules) ↔ backend-api rulesTableRef (env-driven)
Failure mode: API queries wrong table if DATABRICKS_CATALOG/SCHEMA not set to garden
Confirmed:    suspected — DDL comment vs runtime FQN builder
```

```
Surface:      UC13 Delta table and index names (uc13.ingestion.*, uc13.analysis.*)
Shared by:    All databricks/jobs scripts ↔ agents/shared/retrieval.py ↔ workstream agents
Failure mode: Agent retrieval returns empty; writes target wrong table after rename
Confirmed:    yes — documented in databricks/CLAUDE.md delta catalog
```

```
Surface:      Databricks model endpoint names (databricks-bge-large-en, databricks-claude-sonnet-4-6, …)
Shared by:    Notebook widgets / os.environ ↔ agent_base.py ↔ retrieval.py defaults
Failure mode: Job fails if workspace endpoints renamed
Confirmed:    yes — databricks/CLAUDE.md endpoint table
```

```
Surface:      VITE_API_BASE_URL / VITE_AI_API_BASE_URL
Shared by:    root .env ↔ frontend Vite envDir ↔ runtime fetch clients
Failure mode: Frontend calls wrong host in deployed environments
Confirmed:    yes — frontend/src/api/config.ts and aiClient.ts
```

```
Surface:      Workstream tag strings (BUSINESS_MODEL, FINANCIAL, …)
Shared by:    document_classifier.py ↔ ingestion embeddings ↔ retrieval workstream_filter ↔ agents
Failure mode: Coverage gaps or empty agent retrieval when tags drift
Confirmed:    suspected — convention across pipeline; no single const module in repo
```
