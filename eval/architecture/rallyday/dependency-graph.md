Section:      dependency-graph
Version:      1.6.0
Last updated: 2026-08-20

## Internal dependencies

| Dependent | Depends on | Nature of coupling | Risk if changed independently |
|-----------|-----------|--------------------|------------------------------|
| `frontend` | `backend-api` REST shapes | Duplicate TypeScript types for `Rule` and `Company`; no shared package | Field renames break UI without coordinated TS updates |
| `frontend` | `backend-ai` REST shapes | `NlRuleInterpretResponse` mirrors FastAPI models (camelCase) | AI response shape changes break Garden Rules AI panel |
| `frontend` | `ruleConfig.python_function` | Implicit JSON contract in `buildAiRuleApiInput.ts` | Codegen output shape break rule save |
| `backend-api` | `rule_definition` JSON | `pythonFromRuleDefinitionJson` expects nested `python_function` | AI codegen changes leave python columns null |
| `backend-ai` | `backend-api` (logical) | `opportunity_silver_fields` must match `company.ts` and `companyDetailFields.ts` | NL rules reference invalid column names in generated Python |
| `backend-ai` | Databricks Genie | Two-round Genie conversation (interpret + implementation) shares `conversation_id` | SDK or Genie API behavior change breaks deny/retry flow |
| `backend-api` | Unity Catalog table names | `tableRef.ts` hard-codes `salesforce_silver.opportunity_silver`; rules use env catalog/schema | Warehouse rename breaks companies or rules queries |
| `databricks/agents/workstreams` | `databricks/agents/shared` | Shared retrieval, LLM helpers, dataclasses | `semantic_search` signature change breaks all agents |
| `PipelineOrchestrator` | workstream `main()` entrypoints | Dynamic import via `AGENT_REGISTRY`; passes `spark=` to each agent | Signature drift on `main()` breaks DAG invocation |
| `cross_analysis_agent` | `to_result_card` / `collect_result_cards` | Reads compact cards from all Phase 3 tables — never raw chunks | Card schema change breaks cross-analysis reconciliation |
| `build_exec_summary` | completed DAG outputs | `BundleBuilder` ingest reads `analysis.*` rows + Volume YAML reports written by agents | Running exec_summary before DAG yields empty bundle |
| `legal_contracts_agent` | `context_utils.build_focused_context` | Runtime importlib load in `_domain_extract_pass` | Import path or signature change breaks per-pass extraction |
| `legal_contracts_agent` | `retrieval.semantic_search` | Direct call via `_semantic_search_with_fallback` with explicit `catalog=` | Accidental switch to `context_utils` reintroduces uc13 default catalog |
| `databricks/agents/subagents/workstream/financial` | `context_utils` | FTA retrieval via `semantic_search_with_fallback` thin delegator | Bypassing adapter breaks filename retry and provenance |
| `open_agent_run(spark=)` | `DeltaEvalStore` | Worker threads must not call `resolve_store()` → sqlite fallback | FTA ThreadPoolExecutor cascade failure on sqlite connection |
| `financial_trends_agent` | `run_context` + `contextvars` | ThreadPoolExecutor fan-out must wrap with `contextvars.copy_context().run` | Worker threads lose agent_run_id → 0 provenance rows |
| `EvalHarness.dispatch_retrieval` | `fallback.py` (production path) | Surface 11 unification — harness matches production retry semantics | Harness/prod divergence if inline retry reintroduced |
| `evaluate_promotion` | `select_prior_e2e_baseline` + `record_e2e_linkage` | H1-R: e2e fields written only on promoting outcomes | Double-write or blocked-run score pollution |
| `BundleBuilder` (exec_summary) | `ingest_snapshots` + stage pipeline | Same M2 stage graph as pre-rename orchestrator hub | Package rename without import updates breaks Cell 19 |
| `tldr_compress` | `formatters` | Rev3 template projection — removed Vertical/Top Risks sections | Template/compress drift if only one side updated |
| `renderers` | `tldr_compress` | Render-time projection when `TLDR_RENDER_MODE=compressed` | Legacy mode bypasses compress entirely |
| Garden app | UC13 pipeline | No code import; VDR seam is Databricks-job-driven | Accidental schema drift between `garden.*` and `uc13.*` |
| `retrieval.py` chunks↔doc_relevance JOIN | `doc_id.make_doc_id` | Join key changed from `(file_name, company_name)` to `doc_id` (M0 refactor) | Stale/NULL `doc_id` rows silently drop from retrieval; catalog-mismatch hash collision if `doc_id_hash_catalog` guard bypassed |
| `ingestion_parser.main` | `doc_worker.DocWorker` + `parse_manifest.ParseManifest` + `status_store` + `sync_state` | Parser no longer owns file enumeration or whole-company rebuild; per-doc resumable state machine | Skipped/incomplete runs leave `doc_status` rows PENDING; VS sync watermark drifts if `sync_state` bypassed |
| `run_vdr_rainmaker.py` | `cim_detection.py` + `run_ingestion_pipeline()` (scoped, `uc13_preview`) + `agents.orchestration.run_pipeline(run_orchestrator=False)` + `exec_summary.rainmaker_view`/`rainmaker_narrative` | CIM-first POC composes existing ingestion/DAG functions against a sandbox catalog, not a new pipeline | Catalog isolation bug would leak preview writes into production `uc13` |
| `eval/content/*` | `eval/retrieval/companies.py` | Only cross-package Python import from eval/content; all other coupling to eval/program and databricks/agents is via warehouse data (`analysis.*`, `eval.s2_scores`), not imports | Slug-fold drift breaks cross-referencing between S2 rows and registry/trust-statement company keys |
| `eval/retrieval/trust_statement.py` | `eval/program/registry.yaml` + `eval_exemptions.yaml` + `eval.s2_scores` | Reads three independent stores to derive the generated trust rollup | Any of the three drifting out of sync with company/company-slug conventions silently mis-attributes a trust row |
| `eval/retrieval/gold/bootstrap.py` | `eval/retrieval/gold/gold_exclusions.yaml` + `gold/kpi_claim_intent_map.yaml` | Company-scoped exclusion/claim-map inputs now gate bootstrap pass 1 and KPI backfill | New company onboarding without these files produces incomplete/incorrect gold labels silently (no hard fail) |

## External dependencies

| Dependency | Version pinned | Role in project | Sensitivity |
|------------|---------------|-----------------|-------------|
| `express` | ^4.21.2 | backend-api HTTP server | low |
| `@databricks/sql` | ^1.14.0 | Databricks SQL warehouse queries (rules, companies) | medium |
| `react` / `react-dom` | ^19.0.0 | frontend UI | low |
| `vite` | ^6.0.3 | frontend build/dev | medium |
| `vitest` | ^3.0.5 | unit tests (api + frontend) | low |
| `pytest` | (repo root) | UC13 agent contract tests | low |
| `fastapi` | 0.115.6 | backend-ai HTTP | low |
| `uvicorn` | 0.34.0 | backend-ai ASGI server | low |
| `pydantic-settings` | 2.7.0 | backend-ai configuration | low |
| `databricks-sdk` | >=0.40.0,<0.56.0 | Genie API, Vector Search query_index | high |
| `mlflow` | >=3.1 (databricks/pyproject.toml) | LLM deployments, embedding predict, agent tracing | high |
| `pydantic` | >=2.0 | eval/retrieval models, agent schemas | medium |
| `msal` | >=1.28.0 | SharePoint connector auth | medium |
| Databricks model endpoints | workspace-configured | BGE embeddings, Claude Sonnet/Haiku for UC13 | high |
| Databricks Vector Search | `{catalog}.ingestion.embeddings_index` | Semantic retrieval for agents | high |
| Microsoft Graph API | v1.0 | SharePoint file list/download | medium |
| `jinja2` | >=3.1.0 | exec_summary Jinja2 templates | low |
| `jsonschema` | >=4.0.0 | validate_bundle against orchestrator_bundle.schema.yaml | medium |
| `pyyaml` | >=6.0 | bundle YAML, intent registry, gold labels, test fixtures | low |
| `python-docx` | (cluster) | md_to_word DOCX export | medium |
| Unity Catalog | `uc13`, `uc13_ale`, `uc13_preview`, `garden`, `salesforce_silver`, `rallyday_partners_llc` | All warehouse persistence + VDR volume; `uc13_preview` is the Rainmaker POC sandbox catalog | high |
| `weasyprint` | (cluster, `vdr_rainmaker_poc_environment`) | Rainmaker HTML→PDF render (falls back to PyMuPDF Story on failure) | medium |
| `pymupdf` | (cluster) | Vision-extracted chart/table pages; Rainmaker PDF fallback renderer | medium |
