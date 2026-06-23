Section:      open-questions
Version:      1.0.0
Last updated: 2026-06-20

```
Question:     Will Garden rules (python_source) be executed at runtime against opportunity_silver, and if so where?
Impact:       backend-ai codegen, backend-api storage, future execution service
Closes when:  Execution host and contract are specified (in-process, Databricks job, or deferred)
```

```
Question:     What is the production auth model for frontend → backend-api and frontend → backend-ai?
Impact:       integration-seams.md, CORS, deployment topology
Closes when:  Auth mechanism chosen and implemented (e.g. SSO, API gateway, none for internal VPN)
```

```
Question:     Should DATABRICKS_CATALOG/SCHEMA always be `garden` for rules, matching create_rules_table.sql?
Impact:       known-coupling-surfaces garden.rules entry, deployment docs
Closes when:  Catalog/schema convention documented in .env.example or infra config
```

```
Question:     Will UC13 diligence outputs (uc13.analysis.*) surface in the Rallyday Garden UI?
Impact:       module-map coupling note, future frontend modules
Closes when:  Product decision and API seam defined or explicitly deferred
```

```
Question:     Is a shared types package (Rule, Company, ruleConfig) warranted across frontend, backend-api, and backend-ai?
Impact:       dependency-graph duplicate-type coupling
Closes when:  Monorepo tooling decision (OpenAPI codegen, shared npm package, or status quo)
```

```
Question:     Production deployment target for backend-api, backend-ai, and frontend (Databricks Apps, containers, static CDN)?
Impact:       integration-seams, environment variable strategy
Closes when:  Deployment architecture documented outside this folder
```
