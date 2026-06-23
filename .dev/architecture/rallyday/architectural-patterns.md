Section:      architectural-patterns
Version:      1.0.0
Last updated: 2026-06-20

none at this time — pending user input (2026-06-20)

Patterns are added via Phase 8 interview or the "new architectural pattern confirmed" update trigger. Code-derived candidates (not yet recorded — require user-supplied falsifiers):

- Repository factory pattern (`createRulesRepository`, `createCompaniesRepository`) switching memory vs Databricks
- Thin routes → service → repository layering in backend-api
- AI rule flow: interpret in backend-ai → persist via backend-api (two-service split)
- UC13 ingestion full-rebuild vs append-only gap-fill (`ingestion_parser.main` vs `ensure_coverage.ingest_missing`)
