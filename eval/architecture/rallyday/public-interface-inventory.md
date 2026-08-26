Section:      public-interface-inventory
Version:      3.1.0
Last updated: 2026-08-20

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
| `semantic_search` | `databricks/agents/shared/retrieval.py` | function | VS query + merge-rank (`sim × tier_weight`, `merge_rank_mode` kwarg for ablation) + optional VS metadata filter pushdown (`vs_metadata_filters=False` default — item 29 not activated M-PHV4) + keyword fallback → `RouteResult`; new `intent_id` param; keyword-fallback `chunks`↔`doc_relevance` join now keyed on **`doc_id`** (was `file_name`+`company_name`, M0 refactor); emits eval-harness provenance via lazy-imported `eval.retrieval.provenance.ProvenanceEmitter` when an agent run is open (`RE2_PROVENANCE_REQUIRED=1` raises on failure) | BMA/CQA/KPI/Legal/QoE agents; FTA via `context_utils` thin delegator; `EvalHarness.dispatch_retrieval` | active |
| `_TYPE_ORDER` | `databricks/agents/shared/retrieval.py` | constant | Canonical source-type sort order `{"table": 0, "vision": 1, "text": 2}`; imported by `context_utils.py` (M-PHV4 R-09) | retrieval.semantic_search merge-rank tie-break; `build_focused_context` sort | active |
| `RouteResult` | `databricks/agents/shared/_types.py` | dataclass | `{ chunks, mode, scores }` — `mode`: `semantic` \| `keyword` \| `empty`; scores parallel to chunks | `retrieval.py`, `context_utils`, agent wrappers, FTA sub-agents, eval harness | active |
| `semantic_search_with_fallback` | `databricks/agents/subagents/workstream/financial/context_utils.py` | function | Thin delegator to `agents.shared.fallback.semantic_search_with_fallback`; returns `(RouteResult, used_fallback)`; threads `catalog=_default_catalog()`; no `retrieval_mode` param (M-PHV4 T2) | FTA sub-agents (`revenue`, `opex`, `ebitda`) | active |
| `semantic_search_with_fallback` | `databricks/agents/shared/fallback.py` | function | Shared filename-filter retry for BMA/Legal/FTA; returns `(RouteResult, used_fallback)`; explicit `catalog` param (no env default inside) | BMA/Legal `_semantic_search_with_fallback` (aliased `_shared_fallback_search`); FTA via `context_utils` delegator; harness `dispatch_retrieval` production path | active |
| `build_focused_context` | `databricks/agents/subagents/workstream/financial/context_utils.py` | function | CIM-first, source-type-aware chunk truncation → `(context_str, stats)` | FTA sub-agents; `LegalContractsAgent._domain_extract_pass` (importlib) | active |
| `assemble_labeled_context` | `databricks/agents/subagents/workstream/financial/context_utils.py` | function | `(chunk_groups, budgets?, section_labels?) → (context_str, allocations)` — per-query char budgets + section headers (M-RE2 OPEX) | `OpexSubAgent` three query groups | active |
| `OPEX_QUERY_BUDGETS` | `databricks/agents/subagents/workstream/financial/context_utils.py` | constant | `(8000, 3000, 4000)` per OPEX query group char caps | `assemble_labeled_context`, `OpexSubAgent` | active |
| `basis_cross_check` | `databricks/agents/subagents/workstream/financial/basis_cross_check.py` | function | `(opex_records, revenue_records) → list[discrepancy]` — projection vs historical source_location mismatch detection (Option D) | `financial_trends_agent` merge path | active |
| `classify_basis` | `databricks/agents/subagents/workstream/financial/basis_cross_check.py` | function | `(record) → "historical" \| "projection" \| "ambiguous" \| "unknown"` | `basis_cross_check` | active |
| `set_pipeline_thread` | `databricks/agents/shared/run_context.py` | function | `(thread_id: str) → None` — bind pipeline envelope UUID from notebook Cell 1 | `test_pipeline.ipynb`, `open_agent_run` | active |
| `open_agent_run(spark=)` / `close_agent_run` | `databricks/agents/shared/run_context.py` | function | Context-managed pipeline manifest lifecycle → `HarnessRun` with `run_type=pipeline`; **`spark=`** binds `DeltaEvalStore` directly (worker-thread safe) | all seven workstream `main()` + profiler entrypoints | active |
| `load_affected_intents` | `databricks/agents/shared/run_context.py` | function | `(agent_prefix) → list[str]` — registry-backed intent scope from repo-root `intent_registry.yaml` | workstream agents inside `open_agent_run` | active |
| `get_agent_run_id` / `get_pipeline_thread` | `databricks/agents/shared/run_context.py` | function | ContextVar readers for provenance attribution | `retrieval._emit_provenance`, tests | active |
| `WorkstreamAgent` | `databricks/agents/shared/agent_base.py` | class | Base for diligence agents; `run(company_name, spark, llm_endpoint)` | workstream agents | active |
| `FinancialTrendsAgent.run` | `databricks/agents/workstreams/financial_trends_agent.py` | method | Orchestrates 3 parallel sub-agents via `ThreadPoolExecutor`; `(company_name, spark, llm_endpoint, …, catalog)` — no `retrieval_mode` param (M-PHV4 T2); `main(spark=None)` signature; assessment generator's `_as_dicts()` defensively `json.loads`-guards all `*_json` fields and `flags`; new `_append_basis_cross_check_discrepancies()` deterministic flag writer | `test_pipeline.ipynb` Cell 12 | active |
| `BusinessModelAgent.run` | `databricks/agents/workstreams/business_model_agent.py` | method | `catalog` is now a **required keyword-only** param; extraction `max_tokens` 8192→16000; `main(spark=None)`; `main()` forces Sonnet override when widget `extraction_endpoint` is Haiku/Llama (R-1 truncation fix); `generate_business_model_assessment()` defensively `json.loads`-guards `flags`/`data_room_gaps` STRING columns (R-3) | `test_pipeline.ipynb` Cell 11, DAG | active |
| `IndexSyncError` | `databricks/jobs/scripts/ingestion_parser.py` | exception | Message-only `Exception` subclass; raised on fatal vector-index sync paths inside `_wait_for_index_sync` (terminal `FAILED`/`CANCELED`, timeout, outer catch-all) | `main()`, `ensure_coverage.ingest_missing()` (via `ip._wait_for_index_sync` alias), `tests/test_ingestion_parser_sync.py` | active |
| `_wait_for_index_sync` | `databricks/jobs/scripts/ingestion_parser.py` | function | `(spark, catalog, schema, index_suffix, table_embeddings, poll_interval=30, max_wait_seconds=1800) → None`; triggers VS Delta Sync, polls DLT pipeline state, prints `✓ Index ready` / `✗ Sync failed — halting`; raises `IndexSyncError` on fatal paths | `ingestion_parser.main()`, `ensure_coverage.ingest_missing()` | active |
| `ingestion_parser.main` | `databricks/jobs/scripts/ingestion_parser.py` | function | **M0–M4 rewrite:** no more whole-company DELETE+APPEND — builds `ParseManifest`, drives `DocWorker.run()` per-doc; new params `force`, `coverage_per_workstream`, `skip_sync`, `sync_only`, `file_whitelist`; `make_doc_id` **removed from this module** (moved to `doc_id.py`); `MAX_CHUNKS_PER_FILE=2000` cap; legacy `.xls`/SpreadsheetML parsers added | notebooks, jobs, `run_ingestion_pipeline.py` | active |
| `doc_id.make_doc_id` | `databricks/jobs/scripts/doc_id.py` | function | `(catalog, schema, company, folder_path, file_name) → md5` — canonical doc identity, extracted from `ingestion_parser.py` (byte-compatible with old single-arg form) | `parse_manifest.py`, `document_classifier.py`, `ensure_coverage.py`, `ingestion_parser._resolve_force()`, `download_upload.py` | active |
| `DocWorker` | `databricks/jobs/scripts/doc_worker.py` | class | `.run(work_list) → RunSummary` — per-doc claim→parse→embed state machine; writes `doc_status` via `status_store.py`; `format_run_summary()` | `ingestion_parser.main()` per-doc loop | active |
| `ParseManifest` | `databricks/jobs/scripts/parse_manifest.py` | class | `.build(...) → list[ManifestItem]` incremental work-list + coverage sub-pass; `build_file_whitelist_filter()` | `ingestion_parser.main()`, `manifest_dry_run.py` | active |
| `run_manifest_dry_run` | `databricks/jobs/scripts/manifest_dry_run.py` | function | Read-only M0 checkpoint harness — previews `ParseManifest` output without writing | operator preflight | active |
| `StatusStore` | `databricks/jobs/scripts/status_store.py` | class | `ensure_doc_status()` DDL; `.read_status_map()`, `.upsert()`, `.has_newer_complete_than()`, `.max_complete_updated_at()`; status constants `PENDING…ZERO_CHUNKS` | `ingestion_parser.main()`, `doc_worker.py`, `parse_manifest.py` | active |
| `sync_state.ensure_sync_state` / `read_watermark` / `advance_watermark` | `databricks/jobs/scripts/sync_state.py` | function | Vector-index SyncGate watermark table — sync only re-runs after new COMPLETE doc rows | `ingestion_parser.main()` | active |
| `cim_detection.detect_cim` / `select_cim_files` | `databricks/jobs/scripts/cim_detection.py` | function | CIM filename/path detection + Teaser/IOI/NDA exclusion; `CIM_NAME_PATTERNS` shared with `download_upload.py` | `run_vdr_rainmaker.py`, `download_upload.py` | active |
| `download_upload.apply_file_whitelist` | `databricks/jobs/scripts/download_upload.py` | function | Filters SharePoint file list against a `file_whitelist` JSON param (CIM-scoped ingest) | `run_vdr_rainmaker.py` via `main()` widget `file_whitelist` | active |
| `setup_vector_search.main` | `databricks/jobs/scripts/setup_vector_search.py` | function | One-time VS endpoint + Delta Sync index DDL/columns | notebooks, `uc13_ingestion_pipeline.yml` task `setup_vector_search` | active |
| `ensure_coverage.ingest_missing` | `databricks/jobs/scripts/ensure_coverage.py` | function | Append-only gap fill for missing workstream coverage; new `file_names_whitelist` param; builds `doc_id` via `doc_id.make_doc_id` before calling `parse_file(fpath, entry["doc_id"], …)`; new `main_coverage_backfill()` manual Phase 2c entry point | notebooks | active |
| `run_vdr_rainmaker` | `databricks/jobs/scripts/run_vdr_rainmaker.py` | function | `(table_name, record_id, special_folder="") → None` — CIM-first VDR POC: detect CIM → scoped ingest on `uc13_preview` → Phase 3–4 (`run_orchestrator=False`) → bundle → Rainmaker narrative/render → VDR volume; no-op skip (not fallback) if no CIM found | `run_vdr_rainmaker_job.py` notebook, `vdr_rainmaker_poc.yml` | active |
| `rainmaker_view` | `databricks/agents/exec_summary/rainmaker_view.py` | function | `(bundle) → dict` — pure/deterministic view projection (financial table, stat tiles, CAGR/rule-of-X, metadata, enriched risks/diligence Qs) for Rainmaker HTML template; `severity_label/_color_var/_bg_var()` helpers | `renderers.render_rainmaker()`, `rainmaker_narrative.synthesize_rainmaker_narrative()` | active |
| `synthesize_rainmaker_narrative` | `databricks/agents/exec_summary/rainmaker_narrative.py` | function | `(bundle, llm_endpoint, spark=None) → dict` — two bounded LLM calls for prose sections; never raises, degrades to `None` fields + `synthesis_status` | `run_vdr_rainmaker.py` | active |
| `render_rainmaker` | `databricks/agents/exec_summary/renderers.py` | function | Renders `rainmaker_opportunity_summary.html.j2` (3-page A4 HTML, autoescaped) with `bundle`/`rainmaker`/`narrative`/`brand_logo_data_uri` context; optional PDF via WeasyPrint → PyMuPDF Story fallback; writes to same VDR/Volume paths as `render_to_volume` but with `.html`/`.pdf` names | `run_vdr_rainmaker.py` | active |
| `agent_base.accumulate_tokens` / `reset_token_counter` / `get_token_totals` / `get_token_breakdown` / `print_token_summary` | `databricks/agents/shared/agent_base.py` | function | Thread-safe global LLM token counters, populated by `_call_llm()`; `MLFLOW_HTTP_REQUEST_TIMEOUT=600` also set here (fixes 120s read timeout on long Sonnet generations) | `run_vdr_pipeline.py` cost reporting | active |
| `vs_filter_pushdown_probe.main` | `databricks/jobs/scripts/vs_filter_pushdown_probe.py` | function | `(spark, catalog, company_name) → probe summary dict` for M-RE3 workstream/tier `filters_json` spike (direct `query_index`, no retrieval fallback) | cluster operator attestation per eval/retrieval/README.md | active |
| `set_retrieval_mode` | `databricks/jobs/notebooks/test_pipeline.ipynb` Cell 1a | function | Sets `retrieval_mode` widget + `os.environ` without re-running Cell 1 | A/B eval operator | active |
| SharePoint connector | `databricks/agents/ingestion/tools/connector.py` | module | MSAL auth, list/download from SharePoint | `download_upload.py` | active |
| `LegalContractsAgent` | `databricks/agents/workstreams/legal_contracts_agent.py` | class | `agent_name = "legal_contracts"`; M1 five-pass domain loop | `main()`, `test_pipeline.ipynb` Cell 16 | active |
| `LegalContractsAgent.run` | `databricks/agents/workstreams/legal_contracts_agent.py` | method | `(company_name, spark, extraction_endpoint, catalog) → M1 interim dict` — pass-owned registers populated; roll-ups `[]`, `flags=[]`, `executive_summary=null` | `main()` | active |
| `_DOMAIN_PASSES` | `databricks/agents/workstreams/legal_contracts_agent.py` | constant | Five `(pass_id, budget_dict)` tuples per spec §5.11 | `_bind_domain_passes`, `run()` | active |
| `_bind_domain_passes` | `databricks/agents/workstreams/legal_contracts_agent.py` | function | Materialize retrieve/extract callables for each pass ID | `LegalContractsAgent.run()` | active |
| `_semantic_search_with_fallback` | `databricks/agents/workstreams/legal_contracts_agent.py` | method | Thin delegator to `agents.shared.fallback.semantic_search_with_fallback` (aliased import); catalog-threaded; emits `retrieval_fallback` trace | `_domain_retrieve_pass` | active |
| `_domain_retrieve_pass` | `databricks/agents/workstreams/legal_contracts_agent.py` | method | Per-pass LEGAL retrieval using `_DOMAIN_PASS_QUERIES` + budgets; trace `domain_retrieve_{pass_id}` | `_domain_retrieve_*` delegates | active |
| `_domain_extract_pass` | `databricks/agents/workstreams/legal_contracts_agent.py` | method | `build_focused_context` (importlib) → `_call_llm` → `_parse_json_response`; halved `max_chars` retry; trace `domain_extract_{pass_id}` | `_extract_*` delegates | active |
| `legal_contracts_agent.main` | `databricks/agents/workstreams/legal_contracts_agent.py` | function | `get_param`: `sp_company_name`, `catalog` (default `uc13`), `extraction_endpoint`, `llm_endpoint`; D6a Haiku/Llama → Sonnet override; DDL + DELETE/append `{catalog}.analysis.legal` | `uc13_ingestion_pipeline.yml`, notebook Cell 16 | active |
| `_ensure_legal_storage` | `databricks/agents/workstreams/legal_contracts_agent.py` | function | Idempotent `CREATE TABLE analysis.legal` + `CREATE OR REPLACE VIEW legal_contracts` | `main()` | active |
| `BundleBuilder` | `databricks/agents/exec_summary/bundle_builder.py` | class | Deterministic M2 builder; stages 0–8 per §5.6 | `test_pipeline.ipynb` Cell 19, `test_bundle_builder.py`, `test_orchestrator_bundle_builder.py` | active |
| `BundleBuilder.build` | `databricks/agents/exec_summary/bundle_builder.py` | method | `(company_name, catalog, spark, llm_endpoint?) → bundle dict` — `demo_mode: false`, validate-before-persist; stage-6 LLM when `llm_endpoint` set | Cell 19, optional workflow | active |
| `GapAggregator` | `databricks/agents/exec_summary/bundle_builder.py` | class | `merge_data_room_gaps(snapshots) → list`; `build_diligence_questions(bundle, snapshots) → list` | `BundleBuilder`, `populate.py`, tests | active |
| `merge_risks_from_flags` | `databricks/agents/exec_summary/bundle_builder.py` | function | `(snapshots) → list[dict]` — Delta flags → `risks[]`, top 8 by severity | `BundleBuilder`, `populate.py`, `__init__` lazy export | active |
| `apply_fill_state` | `databricks/agents/exec_summary/bundle_builder.py` | function | `(bundle) → dict` — applies `FILL_STATE_RULES` per Appendix B | `BundleBuilder`, `populate.py`, `__init__` lazy export | active |
| `synthesize_executive_narrative` | `databricks/agents/exec_summary/bundle_builder.py` | function | `(bundle, snapshots, llm_endpoint) → None` — stage-6 LLM overlay on `executive.*` only; structural fields restored after LLM | `BundleBuilder.build` when `llm_endpoint` set | active |
| `collect_synthesis_gaps` / `freshness` / `write_bundle_yaml` | `databricks/agents/exec_summary/bundle_builder.py` | function | TL;DR gap audit; Delta `created_at` freshness; YAML persist to Volume | `BundleBuilder`, `populate.py` | active |
| `ConfidenceEngine` | `databricks/agents/exec_summary/confidence.py` | class | `compute_by_area(bundle, snapshots) → dict` (7 areas); `compute_overall(by_area, risks) → str` incl. `medium_low` | `BundleBuilder`, `populate.py`, `test_confidence.py`, `__init__` eager export | active |
| `apply_field_mappings` | `databricks/agents/exec_summary/field_mapping.py` | function | `(snapshots, profile, meta) → dict` — Appendix B stage-2 deterministic mapping | `BundleBuilder` | active |
| `FIELD_MAPPINGS` / `FieldMapping` | `databricks/agents/exec_summary/field_mapping.py` | constant / dataclass | 17 Appendix B rows: `bundle_path`, `agent`, `yaml_json_path`, `transform`, `required_for_tldr` | `apply_field_mappings`, tests | active |
| `tldr_bundle_paths` | `databricks/agents/exec_summary/field_mapping.py` | function | `() → set[str]` — Appendix B path coverage set | tests | active |
| `FILL_STATE_RULES`, `TLDR_REQUIRED_FIELDS`, `AGENT_DELTA_TABLE_SUFFIXES`, `AGENTS_PRESENT_KEYS` | `databricks/agents/exec_summary/constants.py` | constant | Single source for Delta suffixes, TL;DR paths, fill-state rules | field_mapping, bundle_builder, ingest, tests | active |
| `ingest_snapshots` | `databricks/agents/exec_summary/ingest.py` | function | `(company_name, catalog, spark?) → dict[agent_key, {delta_row, yaml_dict, report_path}]`; flags from Delta only | `BundleBuilder`, `populate.py` | active |
| `populate_bundle` | `databricks/agents/exec_summary/populate.py` | function | `(company_name, catalog, spark, llm_endpoint) → bundle dict` — M1 LLM demo path (`demo_mode: true`); production callers use `BundleBuilder` | orchestrator render cell fallback only | active |
| `validate_bundle` / `BundleValidationError` | `databricks/agents/exec_summary/validate.py` | function / exception | `(bundle, schema_path?) → None` or raises; jsonschema draft-07 | `BundleBuilder`, populate, render cell, demo_walkthrough | active |
| `compress_for_tldr` | `databricks/agents/exec_summary/tldr_compress.py` | function | `(bundle) → dict` — lossy `tldr_view` projection; does not mutate input | `render_to_volume`, `test_tldr_compression.py` | active |
| `format_diligence_entry` / `normalize_gap` / `format_agent_flag` / `is_operator_gap` | `databricks/agents/exec_summary/formatters.py` | function | Shared gap/risk/KPI diligence string formatting | `tldr_compress`, `GapAggregator`, `bundle_builder` | active |
| `render` / `render_to_volume` | `databricks/agents/exec_summary/renderers.py` | function | Jinja2 markdown render; `TLDR_RENDER_MODE` compressed (default) vs legacy; writes `full_report.md`, `tldr_one_pager.md` | orchestrator notebook cell | active |
| `ReportRenderer` | `databricks/agents/exec_summary/renderers.py` | class | `render(bundle, template_path, tldr=None) → str` — optional `tldr` projection for compressed template | `render_to_volume`, tests | active |
| `tldr_quality_check.run` | `databricks/agents/exec_summary/tldr_quality_check.py` | function | `(company_name?, catalog?) → int` — soft gates on rendered TL;DR (word count, dict leak, headline/risk labels) | cluster verification, `test_tldr_compression.py` | active |
| `demo_walkthrough.run` | `databricks/agents/exec_summary/demo_walkthrough.py` | function | `(company_name?, catalog?) → int` — M1 cluster verification harness; exit 0 = pass | `python -m agents.exec_summary.demo_walkthrough`, notebook demo cell | active |
| `get_param` | `databricks/agents/exec_summary/demo_walkthrough.py` | function | Widget/env dual-source param reader (`TLDR_RENDER_MODE`, `catalog`, etc.) | renderers, demo_walkthrough, notebook cells | stable |
| `company_safe` / `reports_volume_dir` | `databricks/agents/exec_summary/paths.py` | function | Normalize company name for Volume path segments; `/Volumes/{catalog}/analysis/reports/{company_safe}` | ingest, renderers, DOCX cells, demo_walkthrough | stable |
| `__init__` lazy exports | `databricks/agents/exec_summary/__init__.py` | module | Eager: `ConfidenceEngine`, `FIELD_MAPPINGS`, `apply_field_mappings`, constants; lazy: `BundleBuilder`, `GapAggregator`, `apply_fill_state`, `merge_risks_from_flags`; `__getattr__` imports sibling modules by name | external imports | active |

## eval/retrieval — RE² harness (M-RE1)

| Symbol | Module | Kind | Signature summary | Consumed by | Stability |
|--------|--------|------|-------------------|-------------|-----------|
| `EvalHarness` | `eval/retrieval/harness.py` | class | `run`, `compare`, `validate_baseline_ref`; dispatches production `semantic_search`; dual-write to `EvalStore` + JSON reports | `harness_cli`, cluster baseline runbook, `test_harness_fixture.py` | active |
| `EvalStore` | `eval/retrieval/store.py` | protocol | `insert_run`, `append_results`, `append_provenance`, `append_deltas`, `finalize_run`, `get_run`, `list_runs`, `get_latest_baseline`, `promote_sqlite_run` | `EvalHarness`, `harness_cli`, `test_eval_store.py` | active |
| `SqliteEvalStore` | `eval/retrieval/store.py` | class | Local SQLite mirror of `{catalog}.ops.*` (Appendix I) | CI fixtures, offline harness runs | active |
| `DeltaEvalStore` | `eval/retrieval/store.py` | class | Spark/Delta backend for `{catalog}.ops.*` | cluster baseline (`--store-backend delta`) | active |
| `IntentScopeResolver` | `eval/retrieval/scope_resolver.py` | class | `resolve(git_diff_paths, registry, …) → {affected_intents, gated_intents}` for enhancement PR scope | CI `scope_resolver_cases.yaml`, `test_scope_resolver.py` | active |
| `IntentRegistryExtractor` | `eval/retrieval/registry_extractor.py` | class | AST extraction of retrieval call sites → `intent_registry.yaml` (`catalog=uc13_ale`) | `test_registry_extractor.py`, committed registry | active |
| `GoldLabelBootstrap` | `eval/retrieval/gold/bootstrap.py` | class | Two-pass gold label bootstrap from Spark + registry; normative `ingestion_snapshot` | `gold_labels/elder_care.yaml`, `test_gold_bootstrap.py` | active |
| `RetrievalIntent`, `GoldLabel`, `HarnessRun`, `HarnessResult`, `HarnessDelta`, `HarnessReport`, `ProvenanceRecord` | `eval/retrieval/models.py` | Pydantic v2 | Spec §5.8 eval artifact models; YAML/JSON round-trip | harness, store, registry, gold bootstrap, tests | active |
| `dispatch_retrieval` / `compare_results` / `compute_metrics` | `eval/retrieval/harness.py` | function | Harness metric math (`basis_conflict_at_10` gate, MRR audit-only), production retrieval dispatch — production `with_fallback` path calls `fallback.py` (M-PHV4 T3 Surface 11); inline filename-filter retry retained when `merge_rank_mode` set (ablation-only); **`ablation_arm` → `merge_rank_mode` threading** | `EvalHarness`, golden `compare_gate_cases.yaml` | active |
| `resolve_ablation_arm` / `ablation_arm_to_merge_rank_mode` | `eval/retrieval/harness.py` | function | Parse `{"arm": ...}`; map D7 arms to `merge_rank_mode`; `PreconditionError` on unknown/malformed (`vs_filter_pushdown` accepted but dispatch deferred) | `EvalHarness.run`, `harness_cli` | active |
| `ABLATION_ARMS` / `VALID_ABLATION_ARMS` | `eval/retrieval/models.py` | constant | Four merge-rank arms + conditional `vs_filter_pushdown` name | `resolve_ablation_arm`, tests | active |
| `GLOBAL_RETRIEVAL_PATHS` | `eval/retrieval/scope_resolver.py` | constant | Includes `retrieval.py`, `context_utils.py`, **`fallback.py`** — changes trigger full harness suite scope | `IntentScopeResolver` | active |
| `harness_cli.main` | `eval/retrieval/harness_cli.py` | CLI | `run --store-backend {sqlite,delta} --run-type … --ablation-config <json> …`; `validate-baseline` — **unchanged M-PHV4** (no `compare` subcommand) | cluster operator, T9/T6 baseline runbooks | active |
| `apply_ops_ddl` | `eval/retrieval/scripts/apply_ops_ddl.py` | CLI | `spark.sql` loop over Appendix I DDL; default `--catalog uc13` | one-time cluster preflight before delta store writes | active |
| `intent_registry.yaml` | `eval/retrieval/intent_registry.yaml` | artifact | 57 intents across 9 agent partitions (+8 CQA/KPI from hector merge); `catalog: uc13_ale` | harness, scope resolver, gold bootstrap | active |
| `gold_labels/elder_care.yaml` | `eval/retrieval/gold_labels/elder_care.yaml` | artifact | Per-intent gold labels + gate eligibility | harness compare/baseline validation | active |
| `ProvenanceEmitter` | `eval/retrieval/provenance.py` | class | `emit(route_result, …)` append; `patch_context_allocations(allocations)` upsert chars_allocated/context_section | `retrieval._emit_provenance` (lazy import), `OpexSubAgent` | active |
| `build_provenance_record` / `normalize_mode` / `resolve_store` | `eval/retrieval/provenance.py` | function | Shared provenance row builder, mode normalization, Spark-aware store resolution (D5) | `ProvenanceEmitter`, `EvalHarness` | active |
| `retry_on_delta_conflict` | `eval/retrieval/store.py` | function | Decorator — jittered backoff on Delta concurrent MERGE/UPDATE exceptions | `DeltaEvalStore.append_provenance`, `patch_context_allocations` Delta branch | active |
| `record_e2e_linkage` | `eval/retrieval/scripts/record_e2e_linkage.py` | CLI | `--run-id` + `--e2e-checklist-score/total` + required `--e2e-agent-id` (7-value allowlist) → updates `HarnessRun.e2e_*` on pipeline manifest | FTA/Legal direct CLI; BMA/CQA/KPI/QoE/Profiler via `evaluate_promotion` | active |

## databricks — orchestration DAG (hector-ui-pipeline-merge)

| Symbol | Module | Kind | Signature summary | Consumed by | Stability |
|--------|--------|------|-------------------|-------------|-----------|
| `PipelineOrchestrator` | `databricks/agents/orchestration/pipeline.py` | class | Wave-scheduled DAG over `AGENT_REGISTRY` (9 agents); `run(only_phases?)` → manifest dict | `run_pipeline()`, `run_diligence_pipeline.py`, notebook Cell 24 | active |
| `run_pipeline` | `databricks/agents/orchestration/pipeline.py` | function | `(company_name, catalog?, spark?, …) → manifest` — Phase 3–4 via DAG, Phase 5 orchestrator with manifest | `run_full_pipeline.py`, `run_diligence_pipeline.py`, notebook | active |
| `to_result_card` | `databricks/agents/orchestration/pipeline.py` | function | `(agent_key, catalog, company_name, spark) → bounded dict` — compact interchange for cross-analysis / orchestrator; no chunks/embeddings | `cross_analysis_agent.py`, `orchestrator_agent.py` | active |
| `collect_result_cards` | `databricks/agents/orchestration/pipeline.py` | function | All Phase 3 result cards for cross-analysis input | `cross_analysis_agent.py` | active |
| `AGENT_REGISTRY` | `databricks/agents/orchestration/pipeline.py` | constant | 9 `AgentSpec` entries — 7 workstreams + cross_analysis + orchestrator | `PipelineOrchestrator` | active |
| `orchestrator_agent.main` | `databricks/agents/orchestration/orchestrator_agent.py` | function | `(manifest=, …) → diligence memo`; writes `analysis.diligence_report` | DAG phase 5 | active |
| `generate_*_assessment` | `databricks/agents/workstreams/*_agent.py` | function | Per-agent markdown narrative generators (BMA, FTA, CQA, KPI, QoE, forecast, cross_analysis) | notebook Cells 11d–17c, orchestrator memo | active |

## databricks — exec_summary DAG bridge (T9)

| Symbol | Module | Kind | Signature summary | Consumed by | Stability |
|--------|--------|------|-------------------|-------------|-----------|
| `build_exec_summary` | `databricks/agents/exec_summary/pipeline_entry.py` | function | `(company_name, catalog, spark, llm_endpoint?) → {tldr_md, full_report_md, tldr_docx, full_report_docx}` — build → validate → render → DOCX | `run_full_pipeline.py`, `run_vdr_pipeline.py` | active |

## eval/retrieval — promotion gate (M3–M4)

| Symbol | Module | Kind | Signature summary | Consumed by | Stability |
|--------|--------|------|-------------------|-------------|-----------|
| `PromotionResult` | `eval/retrieval/promotion_gate.py` | dataclass | Frozen outcome: `status`, `candidate_score/total`, `prior_run_id/score`, `waiver_id` | `evaluate_promotion` callers, scorecards | stable |
| `evaluate_promotion` | `eval/retrieval/promotion_gate.py` | function | Checklist-regression gate — bootstrap, promote (`>=`), block, waive (`^W\d+$`); H1-R write-on-promote via `record_e2e_linkage` only on promoting outcomes | operator notebook, `.dev/scorecards/` | stable |
| `select_prior_e2e_baseline` | `eval/retrieval/store.py` | method | `EvalStore` protocol — prior `run_type=pipeline` row with non-null `e2e_checklist_score` | `evaluate_promotion` | stable |
| `InvalidWaiverIdError` | `eval/retrieval/errors.py` | exception | Malformed waiver ID on named override path | `evaluate_promotion` | stable |
| `GOLDEN_CHECKLIST_COVERAGE` | `business_model_agent.py`, `customer_quality_agent.py`, `kpi_agent.py`, `quality_of_earnings_agent.py`, `company_profiler.py` | constant | Per-agent checklist row count `N` with in-module asserts | `tests/test_golden_checklist_elder_care.py` hub | stable |

## eval/retrieval — company canon, eval-debt/exemptions, onboarding, trust rollup (eval-consolidation M2–M5)

| Symbol | Module | Kind | Signature summary | Consumed by | Stability |
|--------|--------|------|-------------------|-------------|-----------|
| `canonical_company_slug` / `resolve_company_slug` / `require_folded_company_slug` | `eval/retrieval/companies.py` | function | §8.2 canonical display-name → slug fold; widest coupling hub in eval/retrieval | `harness`, `harness_cli`, `gold/bootstrap.py`, `ingest_preflight`, `exemptions`, `eval_debt`, `trust_statement`, `eval/content/*`, `onboarding_cluster_submit` | active |
| `GoldLabelBootstrap` | `eval/retrieval/gold/bootstrap.py` | class | Two-pass bootstrap (citation_backfill/section_range/filename_closure positives + basis/section/cross-intent negatives); **CLI + `--company`**, output `gold_labels/<slug>.yaml`; consumes company-scoped `gold_exclusions.yaml` and `kpi_claim_intent_map.yaml` (Excel/PDF KPI claim backfill) | `harness`, `harness_cli`, `refresh_elder_care_slice.py`, `onboarding_cluster_submit.py` | active |
| `load_gold_exclusions` | `eval/retrieval/gold/gold_exclusions.yaml` (data) + `gold/bootstrap.py` (loader) | artifact/function | Company-scoped `aggregate_exclude`/`exclude_reason` pre-population per intent | `GoldLabelBootstrap._bootstrap_pass1`, `scope_resolver.is_gate_eligible` | active |
| `load_kpi_claim_intent_map` | `eval/retrieval/gold/kpi_claim_intent_map.yaml` (data) + `gold/bootstrap.py` (loader) | artifact/function | Fail-closed Excel/PDF claim→intent totality map for 7 KPI intents across 4 companies' industry-specific claim shapes | `GoldLabelBootstrap` KPI citation backfill | active |
| `EvalDebtRow` / `load_debts` / `open_debt` / `close_debt` / `assert_ledger_ratchet` | `eval/retrieval/eval_debt.py` | dataclass/function | Eval-debt ledger I/O + CLI; `assert_ledger_ratchet` enforces open-count ≤ `open_debt_high_water_mark` | onboarding runbook CLI; `eval/program/eval_debt/eval_debt.yaml` | active |
| `IntentExemption` / `load_exemptions` / `write_exemption` | `eval/retrieval/exemptions.py` | dataclass/function | §8.3 intent-level corpus-gap annotation store I/O + CLI | `trust_statement.generate_trust_statement` (content `known_gap`/`narrows` relabel) | active |
| `run_ingest_preflight` / `IngestProbeResult` | `eval/retrieval/ingest_preflight.py` | function/dataclass | §8.4 two-backend ingest completeness probe; never raises across the boundary | Onboarding runbook Step 2; reused by `trust_statement.run_ingest_probe` | active |
| `run_attestation_query` / `run_vision_share_query` | `eval/retrieval/measure_attestation.py` | function | G5 gate: `doc_status` histogram + error detail; vision-chunk share query | Standalone/notebook operator use | active |
| `compute_orphan_stats` / `measure_orphan_rate` | `eval/retrieval/measure_join_orphan_rate.py` | function | G4/R-08 chunks↔doc_relevance orphan-rate measurement before/after join-key migration | Standalone + `test_measure_join_orphan_rate.py` | active |
| `TrustStatementRow` / `derive_rows` / `generate_trust_statement` / `render_trust_statement_markdown` | `eval/retrieval/trust_statement.py` | dataclass/function | C6 five-layer trust generator v1 — reads `eval/program/registry.yaml` + `eval_exemptions.yaml` + `eval.s2_scores`; writes `eval/program/trust_statement.md` (generated, never hand-edited) | CLI (`python -m eval.retrieval.trust_statement generate`) | active |

## eval/program — governance registry (eval-consolidation M2–M5)

| Symbol | Module | Kind | Signature summary | Consumed by | Stability |
|--------|--------|------|-------------------|-------------|-----------|
| `registry.yaml` | `eval/program/registry.yaml` | artifact | `schema_version: 1`; work-item ledger (`id`, `disposition`, `stage`, `trigger`, `rationale`, `tshirt`, `evidence_refs`, `rung_assignments`); **not** a company registry — companies appear in item titles/evidence | `trust_statement.registry_gap_titles_for_company`, `eval_debt.evidence_ref_resolves`, `eval/content/spot_check.py` (`DEFAULT_REGISTRY_PATH`), playbook (human) | active |
| `product_backlog.yaml` | `eval/program/product_backlog.yaml` | artifact | `schema_version: 1`; Elder Care S2 product-signal ledger (`company`, `surface`, `kind`, `severity`, `evidence_refs`, `fix_lane`, `closes_when`) | `test_product_backlog_schema.py`; playbook (human) | active |
| `eval_debt.yaml` | `eval/program/eval_debt/eval_debt.yaml` | artifact | `schema_version: 1`; `open_debt_high_water_mark` + `debts[]` keyed `{company}:{surface\|global}:{kind}` | `eval_debt.py` CLI, `test_eval_debt.py` | active |
| `eval_exemptions.yaml` | `eval/program/eval_exemptions.yaml` | artifact | `schema_version: 1`; intent-level corpus-gap rows (`company`, `intent_id`, `surface`, `coverage`, `reason`, `approved_by`) | `exemptions.py` load/write | active |
| `onboarding_queue.yaml` | `eval/program/onboarding_queue.yaml` | artifact | `schema_version: 1`; ranked SharePoint onboarding queue (`chunk_count`, `ingest_completeness_ratio`, `doc_type_diversity_score`, `rank_score`, `wave`) | `eval/program/build_onboarding_queue.py`, `test_onboarding_queue_schema.py` | active |
| `source_manifest.yaml` | `eval/program/source_manifest.yaml` | artifact | `schema_version: 1`, `frozen_at`; import-time provenance join partner (`registry.items[].source_id` → `sources[].id`) | `test_eval_program_registry.py` | active |
| `trust_statement.md` | `eval/program/trust_statement.md` | artifact | **Generated** five-layer trust rollup per company × layer × surface; regenerate via `trust_statement generate`, never hand-edit | operator dashboard/runbook | active |
| `onboarding_cluster_submit.py` | `eval/program/onboarding_cluster_submit.py` | CLI | M4 runbook Steps 3 & 5 — syncs `eval/retrieval/` + `databricks/agents/` to workspace, submits bootstrap/harness-baseline serverless jobs, `export-gold` pulls workspace gold back (UTF-8-safe) | cluster operator runbook | active |
| `run_harness_enhancement` | `eval/program/onboarding_cluster_submit.py` | function | `(company, catalog, *, run_type, baseline_ref_run_id, affected_intents?, ablation_config?, gold_path?, sync?) → int` — serverless submit for `--run-type enhancement|ablation` via `HARNESS_ENHANCEMENT_DRIVER`; delta backend hardcoded; rejects enhancement without `--affected-intents` and ablation with narrowed intents | M1 W3 retrieval loop; `test_onboarding_runbook.py` | active |
| `harness-run` | `eval/program/onboarding_cluster_submit.py` | CLI subcommand | `--company --run-type {enhancement,ablation} --baseline-ref-run-id [--affected-intents] [--ablation-config] [--catalog uc13_ale] [--gold-path] [--no-sync]` | cluster operator playbook §6; T3 live enhancement/ablation submits | active |

## eval/retrieval — epoch-pin preflight (eval-signal-foldback M1 W3)

| Symbol | Module | Kind | Signature summary | Consumed by | Stability |
|--------|--------|------|-------------------|-------------|-----------|
| `check_epoch_pins` | `eval/retrieval/scripts/preflight_epoch_pins.py` | function | `(store, *, catalog, registry_path, gold_paths_by_company, pinned_baselines?) → list[EpochPinCheck]` — read-only ops manifest lookup; compares stored `gold_snapshot`/`registry_hash` on pinned baseline runs against current computed pins (same helpers/filter as `EvalHarness.run`) | T3 live submit preflight; `test_preflight_epoch_pins.py` | active |
| `EpochPinCheck` | `eval/retrieval/scripts/preflight_epoch_pins.py` | dataclass | Per-company pin outcome: `baseline_valid`, `gold_snapshot_match`, `registry_hash_match`, stored vs current snapshots | preflight CLI stdout/JSON | active |
| `WarehouseEvalStore` | `eval/retrieval/scripts/preflight_epoch_pins.py` | class | Read-only `EvalStore` over Databricks SQL warehouse for `{catalog}.ops.retrieval_harness_runs` manifest columns | `check_epoch_pins`, preflight CLI | active |
| `PINNED_EPOCH_BASELINES` | `eval/retrieval/scripts/preflight_epoch_pins.py` | constant | D4 default pins: Elder Care `baseline_2fa3a9056bd0`, Clearsulting `baseline_488f70f13570`, GKF `baseline_7510d1d14449`, SPG `baseline_3992534e412f` | preflight CLI when `--company` omitted | active |
| `preflight_epoch_pins` | `eval/retrieval/scripts/preflight_epoch_pins.py` | CLI | `python -m eval.retrieval.scripts.preflight_epoch_pins [--catalog uc13_ale] [--company …]` — warehouse-backed D4 epoch pin + gold-drift check before `harness-run` | M1 W3 operator runbook | active |

## eval/content — S2 content-correctness verification (eval-consolidation M2–M3)

| Symbol | Module | Kind | Signature summary | Consumed by | Stability |
|--------|--------|------|-------------------|-------------|-----------|
| `values_agree` / `spans_agree` / `verdicts_agree` / `compute_metrics` / `evaluate_thresholds` | `eval/content/agreement.py` | function | §8.7 (C4/C5) pure agreement predicates + threshold pass/fail (verdict≥0.80, value≥0.90, span≥0.80) for judge calibration | `calibration.run_calibration` | active |
| `run_calibration` / `judge_claim` / `main` | `eval/content/calibration.py` | function | CHK-26a judge-vs-operator calibration driver; dual-source evidence assembly for `exec_summary` (analysis.* tables + chunk RAG) | CLI/runbook | active |
| `extract_exec_claims` / `extract_fta_claims` / `write_exec_manifest` | `eval/content/extract_rubric_manifests.py` | function | One-shot generator: rubric markdown tables → committed JSON claim manifests (53 exec, 276 FTA claims) | operator regeneration; no runtime import | active |
| `derive_locator` / `build_claim_rows` / `verify_legal_register` | `eval/content/legal_register_verifier.py` | function | Rung-1 deterministic whole-surface verifier for `legal_register` — quote-in-chunk matching, HALT-31 locator derivation | `eval/content/__init__.py`; registry CHK-23a | active |
| `S2ScoreRow` / `S2Writer` / `apply_s2_scores_ddl` | `eval/content/s2_writer.py` | dataclass/class | Shared append-only §8.8/§9 writer for `{catalog}.eval.s2_scores` (claims-then-marker sequencing, S-61 fail-closed cited-chunk resolution) | `legal_register_verifier`, `spot_check`, `eval/retrieval/trust_statement.py` | active |
| `SpotCheckConfig` / `ChunkIndex` / `prepare_spot_check` / `write_spot_check_results` | `eval/content/spot_check.py` | class/function | Rung-3 human spot-check enumerate → adjudicate → record pipeline; `DEFAULT_REGISTRY_PATH` → `eval/program/registry.yaml` | CLI/workflow; `calibration.py` (analysis cache reuse) | active |
| `s2_scores.sql` | `databricks/ddl/s2_scores.sql` | DDL | `{catalog}.eval.s2_scores` (+ `{catalog}.eval` schema) — append-only claim/completion-marker rows | Applied once per catalog; read by `trust_statement.py` | stable |

