Section:      data-contract-registry
Version:      1.0.0
Last updated: 2026-06-20

```
Contract:       Rule (API entity)
Module:         backend-api/src/types/rule.ts
Serialization:  TypeScript class + JSON (REST)
Version:        unversioned — tracked by git blame
Purpose:        Persisted Garden rule with form or AI provenance
Fields:
  - id: number — server-generated identity
  - name: string — display name
  - description: string | null
  - status: "active" | "inactive"
  - rule_source: "form" | "ai"
  - nl_prompt: string | null — original NL user text (AI rules)
  - nl_summary: string | null — AI interpretation summary
  - rule_definition: string | null — JSON string of rule config object
  - python_source: string | null — generated Python function source
  - python_entrypoint: string | null — function name (e.g. evaluate_opportunity)
  - created_at, updated_at: ISO-8601 string
  - last_updated_by: string | null
Validators:     status and rule_source enums; name required on create; python fields enriched from rule_definition when absent
Consumers:      frontend/src/types/rule.ts, backend-api repositories, Databricks SQL table
Last changed:   2026-06-20
```

```
Contract:       CreateRuleInput / ReplaceRuleInput / UpdateRuleInput
Module:         backend-api/src/types/rule.ts
Serialization:  JSON request body
Version:        unversioned — tracked by git blame
Purpose:        Client payloads for rule CRUD (audit fields optional on create)
Fields:
  - (subset of Rule business fields; id and timestamps server-owned)
Validators:     RulesService + validation.ts (normalizeStatus, requireLastUpdatedBy, etc.)
Consumers:      frontend rule forms, buildAiRuleApiInput.ts
Last changed:   2026-06-20
```

```
Contract:       Company (API entity)
Module:         backend-api/src/types/company.ts
Serialization:  TypeScript class + JSON (REST)
Version:        unversioned — tracked by git blame
Purpose:        Read-only opportunity/company row from salesforce silver
Fields:
  - id, project_name, account_name, industry, annual_revenue, employee_head_count,
    year_founded, ebitda, ebitda_margin, days_since_last_activity, website,
    source_scrub_url, linked_in_company_id, zoom_info_company_id,
    growth_rate_12_months, growth_rate_9_months, growth_rate_6_months,
    investors, name, description, stage_name, type, lead_source,
    opportunity_owner, opportunity_owner_role, opportunity_owner_email, status
Validators:     none at API layer (read-only from warehouse)
Consumers:      frontend/src/types/company.ts, companyDetailFields.ts
Last changed:   2026-06-20
```

```
Contract:       RuleConfig (AI interpretation)
Module:         backend-ai (dict) → serialized in Rule.rule_definition
Serialization:  JSON object (nested in Rule.rule_definition string)
Version:        unversioned — tracked by git blame
Purpose:        Structured rule produced by Genie/mock NL pipeline
Fields:
  - name: string
  - description: string
  - intent: string (e.g. evaluate_opportunity)
  - source: string (genie_text | nl_prompt | …)
  - conditions: array of { field, operator, value, … }
  - actions: array
  - metadata: object (e.g. user_prompt, mock flag)
  - python_function: { source: string, entrypoint: string }
Validators:     response_parser (JSON + python_function.source ast.parse); opportunity_silver_fields.normalize_rule_config; rule_python_codegen.ensure_rule_python_function
Consumers:      frontend buildAiRuleApiInput.ts, backend-api ruleDefinition.ts
Last changed:   2026-06-20
```

```
Contract:       InterpretRequest / InterpretResponse
Module:         backend-ai/app/routes/rules_nl.py
Serialization:  Pydantic BaseModel ↔ JSON
Version:        unversioned — tracked by git blame
Purpose:        NL rules interpret and deny-retry API
Fields:
  - InterpretRequest.prompt: string (1–8000 chars)
  - InterpretResponse.sessionId, summary, ruleConfig (dict), aiMode, canDeny
Validators:     Pydantic Field constraints; session deny_count vs rules_ai_max_denies
Consumers:      frontend/src/types/nlRule.ts, nlRules.ts
Last changed:   2026-06-20
```

```
Contract:       ApiListResponse<T>
Module:         backend-api routes (convention)
Serialization:  JSON
Version:        unversioned — tracked by git blame
Purpose:        Wrapper for collection and single-entity reads
Fields:
  - data: T | T[]
Validators:     none
Consumers:      frontend api clients
Last changed:   2026-06-20
```

```
Contract:       garden.rules (Databricks Delta)
Module:         databricks/jobs/sql/create_rules_table.sql
Serialization:  SQL DDL / Delta table
Version:        unversioned — tracked by git blame
Purpose:        Persistent rules storage when DATA_STORE=databricks
Fields:
  - Mirrors Rule API fields; id BIGINT IDENTITY; timestamps TIMESTAMP
Validators:     CHECK constraints on status and rule_source enums
Consumers:      backend-api Databricks rules repository
Last changed:   2026-06-20
```

```
Contract:       salesforce_silver.opportunity_silver
Module:         Unity Catalog (external to repo)
Serialization:  Databricks SQL materialized view
Version:        unversioned — warehouse-managed
Purpose:        Company/opportunity records for My Garden
Fields:
  - Same as Company API entity (see OPPORTUNITY_SILVER_FIELDS in backend-ai)
Validators:     none in app layer
Consumers:      backend-api companies repository, backend-ai NL rule field normalization
Last changed:   2026-06-20
```

```
Contract:       UC13 ingestion chunk (Delta)
Module:         databricks/jobs/scripts/ingestion_parser.py
Serialization:  Spark DataFrame / Delta table uc13.ingestion.chunks
Version:        unversioned — _EXPECTED_COLS guards in agents
Purpose:        Parsed document chunks for vector search
Fields:
  - company_name, file_name, chunk_text, section_header, page_start, source_type, workstream, priority_tier, …
Validators:     schema guards in parser and ensure_coverage scripts
Consumers:      retrieval.semantic_search, Phase 3 agents
Last changed:   2026-06-20
```

```
Contract:       WorkstreamAgent.run result
Module:         databricks/agents/workstreams/*.py
Serialization:  dict → Delta analysis tables (per agent)
Version:        unversioned — per-agent _EXPECTED_COLS
Purpose:        Structured diligence output per workstream
Fields:
  - Agent-specific JSON columns; common trace/flags/citations via agent_base
Validators:     _parse_json_response, schema migration guard in main()
Consumers:      Databricks notebooks, downstream reporting
Last changed:   2026-06-20
```
