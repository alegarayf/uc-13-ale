Section:      integration-seams
Version:      1.0.0
Last updated: 2026-06-20

```
Seam:          Frontend → backend-api
Direction:     outbound (browser)
Protocol:      HTTP REST JSON
Auth:          none (local dev) [needs confirmation for production]
Data sent:     Rule CRUD bodies, company list/detail requests
Data received: { data: … } envelopes, health/config
Error modes:   4xx validation/not-found, 5xx store errors
Retry policy:  none (client throws)
Owner module:  frontend/src/api
```

```
Seam:          Frontend → backend-ai
Direction:     outbound (browser)
Protocol:      HTTP REST JSON
Auth:          none (local dev) [needs confirmation for production]
Data sent:     NL rule prompts, deny feedback
Data received: InterpretResponse (sessionId, summary, ruleConfig)
Error modes:   502 Genie failures, 404/409 session errors, 422 validation
Retry policy:  user-driven deny flow (max rules_ai_max_denies per session)
Owner module:  frontend/src/api/aiClient.ts
```

```
Seam:          backend-api → Databricks SQL warehouse
Direction:     outbound
Protocol:      Databricks SQL (@databricks/sql)
Auth:          DATABRICKS_TOKEN + HTTP path
Data sent:     Parameterized INSERT/UPDATE/DELETE/SELECT on rules; SELECT on opportunity_silver
Data received: Row sets mapped to Rule/Company entities
Error modes:   Connection/auth failure, missing catalog/schema, SQL errors
Retry policy:  none
Owner module:  backend-api/src/db/databricksClient.ts
```

```
Seam:          backend-ai → Databricks Genie
Direction:     outbound
Protocol:      databricks-sdk WorkspaceClient.genie
Auth:          DATABRICKS_SERVER_HOSTNAME + DATABRICKS_TOKEN
Data sent:     User prompts + rules-engine instructions; conversation continuations on deny
Data received: Genie message text (JSON or markdown-wrapped JSON)
Error modes:   Missing space ID/token, Genie FAILED status, empty response
Retry policy:  deny endpoint re-invokes Genie with feedback (bounded)
Owner module:  backend-ai/app/services/genie_rules.py
```

```
Seam:          UC13 SharePoint → Databricks Volume
Direction:     inbound
Protocol:      Microsoft Graph REST (MSAL client credentials)
Auth:          SP_CLIENT_ID, SP_CLIENT_SECRET, tenant/site config
Data sent:     Graph API requests
Data received: File binaries written to /Volumes/uc13/.../raw_files/{company}/
Error modes:   Auth failure, pagination errors, download timeouts
Retry policy:  connector-internal retries [needs confirmation]
Owner module:  databricks/agents/ingestion/tools/connector.py
```

```
Seam:          UC13 → Databricks Vector Search
Direction:     bidirectional
Protocol:      databricks-sdk vector_search_indexes.query_index
Auth:          workspace token (runtime)
Data sent:     Embedding queries (BGE endpoint)
Data received: Chunk hits from uc13.ingestion.embeddings_index
Error modes:   Index missing, endpoint down → keyword fallback in retrieval.py
Retry policy:  fallback to Spark LIKE search on failure
Owner module:  databricks/agents/shared/retrieval.py
```

```
Seam:          UC13 agents → Databricks model serving
Direction:     outbound
Protocol:      mlflow.deployments HTTP
Auth:          Databricks workspace credentials
Data sent:     LLM prompts (extraction + narrative); vision prompts for figure pages
Data received: Model text / JSON completions
Error modes:   Timeout (large max_tokens), token cap truncation, invalid JSON
Retry policy:  none at base class; agents may re-prompt manually
Owner module:  databricks/agents/shared/agent_base.py
```

```
Seam:          UC13 scripts → Delta Lake (Unity Catalog uc13.*)
Direction:     bidirectional
Protocol:      Spark SQL / DataFrame writes
Auth:          cluster / job identity
Data sent:     Ingestion, classification, analysis row writes
Data received: Reads for coverage checks and agent inputs
Error modes:   Schema drift (guarded by _EXPECTED_COLS), merge failures
Retry policy:  job-level retry (Databricks Workflows) [needs confirmation]
Owner module:  databricks/jobs/scripts, databricks/agents/workstreams
```
