Section:      data-contract-registry
Version:      1.13.0
Last updated: 2026-08-20

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
  - company_name, file_name, chunk_text, section_header, page_start, source_type, workstream, priority_tier, chunk_id, chunk_index, …
Validators:     schema guards in parser and ensure_coverage scripts
Consumers:      retrieval.semantic_search, Phase 3 agents
Last changed:   2026-07-01
```

```
Contract:       UC13 embeddings Delta Sync source + VS index columns
Module:         databricks/jobs/scripts/setup_vector_search.py, ingestion_parser.py
Serialization:  Delta table uc13.ingestion.embeddings → Vector Search index uc13.ingestion.embeddings_index
Version:        unversioned — contract-tested in tests/test_setup_vector_search.py
Purpose:        BGE vectors and metadata synced to VS for semantic retrieval
Fields:
  - chunk_id, doc_id, file_name, workstream, priority_tier, company_name, source_type, embedding vector
Validators:     columns_to_sync parity across setup script, ingestion DDL, and notebook Cell 2b
Consumers:      retrieval.semantic_search (_query_vector_index filters_json on company_name)
Last changed:   2026-06-25
```

```
Contract:       RouteResult
Module:         databricks/agents/shared/_types.py
Serialization:  Python dataclass (in-process only)
Version:        unversioned — tracked by git blame
Purpose:        Spec-normative retrieval return at production boundary; mode trace + parallel scores for eval harness
Fields:
  - chunks: list[Spark Row] — chunk_id, file_name, chunk_text, section_header, page_start, source_type, workstream, priority_tier
  - mode: str — "semantic" | "keyword" | "empty" (aliases normalized at harness read: vector→semantic, keyword_fallback→keyword)
  - scores: list[float] — parallel to chunks; merge-rank float on semantic, 0.0 per chunk on keyword, [] on empty
Validators:     tests/test_retrieval.py parallel length + no None elements; eval/retrieval/tests/test_route_result_migration.py AST guard
Consumers:      retrieval.semantic_search, context_utils wrappers, BMA/Legal _semantic_search_with_fallback, direct agent callers, EvalHarness.dispatch_retrieval
Last changed:   2026-07-03
```

```
Contract:       semantic_search merge_rank_mode (M-RE3 ablation)
Module:         databricks/agents/shared/retrieval.py
Serialization:  Python kwarg Literal["sim_tier","sim_only","tier_only","off"] | None
Version:        unversioned — tracked by git blame
Purpose:        Ablation dispatch for merge-rank ordering; None and "sim_tier" preserve pre-T4 default
Fields:
  - merge_rank_mode: optional; "sim_only" raw VS score sort; "tier_only" priority_tier asc; "off" hydrate-SQL collect order (skips merge-rank + source_type_priority)
Validators:     tests/test_retrieval.py; eval/retrieval/tests/test_ablation.py
Consumers:      EvalHarness.dispatch_retrieval(ablation_arm=...), harness_cli --ablation-config
Last changed:   2026-07-03
```

```
Contract:       semantic_search vs_metadata_filters (M-RE3 T2 capability)
Module:         databricks/agents/shared/retrieval.py
Serialization:  Python bool kwarg (default False)
Version:        unversioned — tracked by git blame
Purpose:        Optional VS metadata filter pushdown for workstream list any-of and priority_tier <= alongside company_name
Fields:
  - vs_metadata_filters: False preserves pre-T2 production behavior; True merges predicates in single filters_json AND dict
Validators:     tests/test_retrieval.py mocked SDK filters_json assertions; T1 probe matrix operator attestation; M-PHV4 item 16 Elder Care A/B (2026-07-15) PG5 bar fail — default remains False
Consumers:      vs_filter_pushdown ablation arm name valid but dispatch deferred; no production call site passes True; item 29 activation declined per m-phv4-t5-r02-activation-gate.md
Last changed:   2026-07-15
```

```
Contract:       Shared fallback (BMA/Legal/FTA R-03)
Module:         databricks/agents/shared/fallback.py
Serialization:  Python function semantic_search_with_fallback → (RouteResult, used_fallback: bool)
Version:        unversioned — tracked by git blame
Purpose:        Consolidated filename-filter retry for BMA, Legal, and FTA (via context_utils thin delegator since M-PHV4 T2)
Fields:
  - catalog: str | None — explicit only; no env default inside shared function (D5); FTA threads via context_utils._default_catalog()
  - intent_id, source_type_priority: optional kwargs (FTA sub-agents pass intent_id for provenance)
Validators:     tests/test_shared_fallback.py; test_business_model_agent.py; test_legal_contracts_agent.py; tests/test_context_utils.py (11 tests); eval/retrieval/tests/test_harness_fixture.py (dispatch delegation)
Consumers:      BusinessModelAgent._semantic_search_with_fallback, LegalContractsAgent._semantic_search_with_fallback, context_utils.semantic_search_with_fallback, EvalHarness.dispatch_retrieval (production path)
Last changed:   2026-07-15
```

```
Contract:       Ablation config + arms (M-RE3)
Module:         eval/retrieval/models.py, eval/retrieval/harness.py
Serialization:  JSON {"arm": "<name>"} on HarnessRun.ablation_config; ablation_arm on manifest/results when run_type=ablation
Version:        unversioned — tracked by git blame
Purpose:        Merge-rank ablation matrix (4 arms minimum) with HarnessDelta vs baseline_ref
Fields:
  - ABLATION_ARMS: merge_rank_on | merge_rank_off | sim_only | tier_only
  - VALID_ABLATION_ARMS: ABLATION_ARMS + vs_filter_pushdown (name only; dispatch deferred)
  - ablation_arm_to_merge_rank_mode mapping per plan D7
  - baseline_ref_run_id pin: `baseline_299063e87806` (M-RE3 post-hardening authoritative per retrieval_harness_latest_baseline)
Validators:     resolve_ablation_arm raises PreconditionError; eval/retrieval/tests/test_ablation.py; operator attestation 2026-07-06 (merge_rank_on control validation)
Consumers:      harness_cli run --ablation-config, EvalHarness.run
Last changed:   2026-07-06
```

```
Contract:       retrieval_mode (FTA eval widget — legacy notebook only post-M-PHV4)
Module:         test_pipeline.ipynb Cell 1/1a (legacy widget retained)
Serialization:  dbutils widget + os.environ string
Version:        unversioned — tracked by git blame
Purpose:        Historical A/B eval arm label for `financial_trends_eval_snapshot` rows; **production FTA no longer reads or threads `retrieval_mode`** (M-PHV4 T2)
Fields:
  - "semantic" / "enhanced_semantic" — legacy snapshot labels only
Validators:     tests/test_context_utils.py no longer asserts retrieval_mode dispatch; FinancialTrendsAgent.run signature test (inspect) proves param absent
Consumers:      Legacy eval snapshot cells only; production FTA sub-agents call context_utils → fallback.py without mode threading
Last changed:   2026-07-15
```

```
Contract:       financial_trends_eval_snapshot (Delta)
Module:         databricks/jobs/notebooks/test_pipeline.ipynb (snapshot cell)
Serialization:  Delta table {catalog}.analysis.financial_trends_eval_snapshot
Version:        unversioned — tracked by git blame
Purpose:        Preserve one FTA output row per (company_name, retrieval_mode) for A/B scorecard
Fields:
  - company_name: string
  - retrieval_mode: string
  - snapshot_json: string — serialized FTA agent output
  - created_at: timestamp
Validators:     DELETE+INSERT per (company, mode) before append
Consumers:      RT7 scorecard, eval-protocol operator runbook
Last changed:   2026-06-25
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
Consumers:      Databricks notebooks, downstream reporting, eval snapshot
Last changed:   2026-06-20
```

```
Contract:       uc13_ale.analysis.legal (Delta table)
Module:         databricks/agents/workstreams/legal_contracts_agent.py
Serialization:  Spark DataFrame / Delta table {catalog}.analysis.legal
Version:        unversioned — Appendix A _EXPECTED_COLS (21 columns); M0 DDL via _CREATE_LEGAL_TABLE_SQL
Purpose:        M0 legal agent write target — contract registers, flags, gaps, trace
Fields:
  - company_name, executive_summary, section_confidence
  - contract_register_json, vendor_register_json, platform_dependency_register_json
  - employment_register_json, litigation_register_json, privacy_security_register_json
  - ip_register_json, insurance_register_json, coc_consent_list_json
  - termination_exposure_json, restrictive_covenant_map_json
  - unable_to_assess_json, recommended_diligence_json
  - flags, data_room_gaps (ARRAY<STRING>), citations, reasoning_trace, created_at
Validators:     _ensure_legal_storage() idempotent DDL; DELETE+append per company in main()
Consumers:      legal_contracts_agent.main(), test_pipeline.ipynb Cell 18 (`"legal"` key), uc13_ingestion_pipeline.yml
Last changed:   2026-06-26
```

```
Contract:       uc13_ale.analysis.legal_contracts (compat VIEW)
Module:         databricks/agents/workstreams/legal_contracts_agent.py
Serialization:  SQL VIEW over {catalog}.analysis.legal
Version:        unversioned — _CREATE_LEGAL_CONTRACTS_VIEW_SQL
Purpose:        Legacy consumer surface; subset of analysis.legal columns + triggered_reviews_loaded=0
Fields:
  - company_name, executive_summary, contract_register_json, litigation_register_json
  - coc_consent_list_json, termination_exposure_json, restrictive_covenant_map_json
  - triggered_reviews_loaded (literal 0), flags, data_room_gaps, citations, reasoning_trace, created_at
Validators:     DROP TABLE IF EXISTS legal_contracts before CREATE VIEW in _ensure_legal_storage()
Consumers:      test_pipeline.ipynb Cell 18 (`"legal_contracts"` key), legacy notebooks/queries expecting old table name
Last changed:   2026-06-26
```

```
Contract:       Legal domain pass registry (_DOMAIN_PASSES)
Module:         databricks/agents/workstreams/legal_contracts_agent.py
Serialization:  Python module-level list + dict companions (_DOMAIN_PASS_BUDGETS, _DOMAIN_PASS_QUERIES, _DOMAIN_PASS_EXTRACT)
Version:        unversioned — tracked by git blame
Purpose:        Five-pass M1 retrieval/extraction loop per spec §5.11
Fields:
  - pass_id: contracts_vendors_platform | employment | litigation | ip_privacy | insurance
  - budget_dict: top_k, min_chunk_length, max_chars, max_tokens, file_name_filter (per pass)
  - query: per-pass semantic query string in _DOMAIN_PASS_QUERIES
  - extract: user_prompt template + register_keys per pass in _DOMAIN_PASS_EXTRACT
Validators:     _bind_domain_passes binds retrieve/extract methods; AST tests in test_legal_contracts_agent.py
Consumers:      LegalContractsAgent.run(), tests/test_legal_contracts_agent_extract.py
Last changed:   2026-06-26
```

```
Contract:       LegalContractsAgent.run M1 interim return
Module:         databricks/agents/workstreams/legal_contracts_agent.py
Serialization:  dict → JSON columns in analysis.legal via _map_legacy_result_to_legal_row
Version:        unversioned — D1a interim bridge until M2 roll-ups
Purpose:        Per-pass register extraction output without cross-pass merge or flags
Fields:
  - company_name: string
  - executive_summary: null (M2)
  - contract_register_json, vendor_register_json, platform_dependency_register_json: JSON arrays
  - employment_register_json, litigation_register_json, ip_register_json, privacy_security_register_json, insurance_register_json: JSON arrays
  - coc_consent_list_json, termination_exposure_json, restrictive_covenant_map_json: empty arrays (M2)
  - triggered_reviews_loaded: int — len(contract_triggers) from CQA read
  - flags: empty array (M2)
  - data_room_gaps, citations, reasoning_trace: from agent trace state
  - created_at: ISO-8601 UTC
Validators:     per-pass _normalize_pass_payload enforces §5.8 register keys; empty registers on LLM/parse failure (run continues)
Consumers:      legal_contracts_agent.main(), _write_stakeholder_report
Last changed:   2026-06-26
```

```
Contract:       Legal per-pass extraction schema (§5.8 normative field names, D2a)
Module:         databricks/agents/workstreams/legal_contracts_agent.py
Serialization:  JSON object per LLM call (parsed via _parse_json_response)
Version:        unversioned — normative names per legal agent spec D2a
Purpose:        Structured register rows per domain pass with tri-state clause tokens
Fields:
  - restrictive_covenants (not exclusivity_mfn_noncompete) on contract records
  - liability_indemnity (not liability_cap) on vendor/platform records
  - register_keys per pass: see _DOMAIN_PASS_EXTRACT
Validators:     test_normative_schema_names_in_user_prompts; M2 roll-up helpers still use legacy field names until reconciled
Consumers:      _domain_extract_pass, future M2 _merge_registers / _apply_legal_flags
Last changed:   2026-06-26
```

```
Contract:       Orchestrator bundle (orchestrator_bundle.yaml)
Module:         databricks/agents/orchestrator/orchestrator_bundle.schema.yaml
Serialization:  YAML on UC Volume; validated via jsonschema draft-07
Version:        meta.schema_version const "0.1.0"
Purpose:        Canonical orchestrator synthesis artifact per uc13_orchestrator_deliverables_spec §5.8
Fields:
  - meta: company_name, company_safe, catalog, demo_mode, disclaimer_text, render_state, agents_present, …
  - headline_metrics, executive, company_framing, financials, revenue_quality, kpi_dashboard, qoe, legal
  - risks[], diligence_questions[], data_room_gaps[], confidence_by_area (7 areas), provenance.synthesis_gaps[]
Validators:     validate_bundle() in validate.py
Consumers:      BundleBuilder.build, populate_bundle (demo), renderers, demo_walkthrough
Last changed:   2026-07-01
```

```
Contract:       FIELD_MAPPINGS (Appendix B stage-2 registry)
Module:         databricks/agents/orchestrator/field_mapping.py
Serialization:  Python list[FieldMapping] dataclass
Version:        unversioned — tracked by git blame
Purpose:        Data-driven mapping from agent YAML/Delta snapshots to bundle top-level blocks
Fields:
  - bundle_path: dot-path in orchestrator bundle
  - agent: source agent key or "param" | "profiler"
  - yaml_json_path: comma-separated paths in agent YAML
  - transform: named transform function key (e.g. headline_ltm_revenue, fta_table_rows)
  - required_for_tldr: bool
Validators:     tests in test_bundle_builder.py; tldr_bundle_paths() coverage set
Consumers:      apply_field_mappings, BundleBuilder.build stage 2
Last changed:   2026-06-30
```

```
Contract:       AGENT_DELTA_TABLE_SUFFIXES
Module:         databricks/agents/orchestrator/constants.py
Serialization:  Python dict[str, str]
Version:        unversioned — D-M2-8 single source (deduped from ingest)
Purpose:        Maps six workstream keys → `{catalog}.analysis.{suffix}` table names
Fields:
  - business_model, financial_trends, customer_quality, kpi, legal, quality_of_earnings
Validators:     must match AGENTS_PRESENT_KEYS agent set
Consumers:      ingest_snapshots, BundleBuilder provenance.agent_delta_tables
Last changed:   2026-06-30
```

```
Contract:       TLDR_REQUIRED_FIELDS / FILL_STATE_RULES
Module:         databricks/agents/orchestrator/constants.py
Serialization:  Python list[str] and dict[str, str]
Version:        unversioned — Appendix B
Purpose:        TL;DR synthesis gap audit paths and expected fill_state enums per path
Fields:
  - TLDR_REQUIRED_FIELDS: 17 dot-paths incl. wildcards headline_metrics.*, kpi_dashboard[]
  - FILL_STATE_RULES: path → filled_cited | filled_synthesized | gap_correct | not_attempted
Validators:     collect_synthesis_gaps, apply_fill_state, demo_walkthrough gates
Consumers:      BundleBuilder, demo_walkthrough
Last changed:   2026-06-30
```

```
Contract:       Agent snapshot (internal ingest shape)
Module:         databricks/agents/orchestrator/ingest.py
Serialization:  in-memory dict per agent key
Version:        unversioned — tracked by git blame
Purpose:        Unified read surface for BundleBuilder and populate_bundle
Fields:
  - delta_row: latest Spark row as dict; flags parsed from Delta JSON column only
  - yaml_dict: parsed Volume YAML report or None
  - report_path: resolved path under reports Volume
Validators:     flags never read from Volume YAML (_parse_flags on Delta only)
Consumers:      BundleBuilder, populate_bundle, GapAggregator, ConfidenceEngine
Last changed:   2026-06-30
```

```
Contract:       tldr_view (render-time projection)
Module:         databricks/agents/orchestrator/tldr_compress.py
Serialization:  in-memory dict (not persisted)
Version:        unversioned — tracked by git blame
Purpose:        Lossy compressed projection for tldr_one_pager_compressed.md.j2
Fields:
  - headline, in_one_line, business_snapshot, financial, revenue_quality, kpi, legal, qoe, risks, open_items, questions
Validators:     tldr_quality_check soft gates; test_tldr_compression.py regression suite
Consumers:      render_to_volume when TLDR_RENDER_MODE=compressed
Last changed:   2026-06-30
```

```
Contract:       TLDR_RENDER_MODE
Module:         test_pipeline.ipynb Cell 1, renderers.render_to_volume
Serialization:  dbutils widget + os.environ string
Version:        unversioned — tracked by git blame
Purpose:        Select compressed vs legacy TL;DR template at render time
Fields:
  - "compressed" (default) — compress_for_tldr + tldr_one_pager_compressed.md.j2
  - "legacy" — full bundle via tldr_one_pager.md.j2
Validators:     full_report path must not depend on mode (K4 falsifier in test_tldr_compression.py)
Consumers:      render_to_volume, cluster verification
Last changed:   2026-06-30
```

```
Contract:       Elder Care builder fixtures
Module:         tests/fixtures/elder_care_*.yaml
Serialization:  YAML test fixtures
Version:        unversioned — tracked by git blame
Purpose:        Regression baselines for BundleBuilder, compression, and agent snapshots
Fields:
  - elder_care_agent_snapshots.yaml, elder_care_builder_expectations.yaml, elder_care_bundle_compression.yaml
Validators:     test_bundle_builder.py, test_orchestrator_bundle_builder.py, test_tldr_compression.py
Consumers:      M2 orchestrator pytest suite
Last changed:   2026-06-30
```

```
Contract:       Orchestrator Volume artifact paths
Module:         databricks/agents/orchestrator/paths.py
Serialization:  filesystem paths under /Volumes/{catalog}/analysis/reports/{company_safe}/
Version:        unversioned — D-M1-2 company_safe convention
Purpose:        Bundle, rendered markdown, and DOCX deliverables on UC Volume
Fields:
  - orchestrator_bundle.yaml — canonical bundle
  - full_report.md, tldr_one_pager.md — Jinja renders
  - full_report.docx, tldr_one_pager.docx — md_to_word exports
Validators:     demo_walkthrough gate 7 file-existence check
Consumers:      render_to_volume, test_pipeline.ipynb orchestrator + DOCX cells, demo_walkthrough, tldr_quality_check
Last changed:   2026-07-01
```

```
Contract:       RetrievalIntent (eval registry row)
Module:         eval/retrieval/models.py
Serialization:  Pydantic v2 ↔ YAML in intent_registry.yaml
Version:        unversioned — tracked by git blame
Purpose:        Frozen retrieval intent definition extracted from agent call sites
Fields:
  - intent_id, agent_id, company_name, catalog, source_file, query, top_k, workstream_filter, file_name_filter, tier_filter, min_chunk_length, wrapper_path, …
Validators:     IntentRegistryExtractor AST bounds; test_registry_extractor.py Appendix C ±2 counts
Consumers:      EvalHarness, IntentScopeResolver, GoldLabelBootstrap
Last changed:   2026-07-01
```

```
Contract:       GoldLabel (eval gold row)
Module:         eval/retrieval/models.py
Serialization:  Pydantic v2 ↔ YAML in gold_labels/{company_slug}.yaml
Version:        unversioned — tracked by git blame
Purpose:        Per-intent positive/negative chunk IDs and gate eligibility for harness compare
Fields:
  - intent_id, company_name, catalog, gold_status, positive_chunk_ids, negative_chunk_ids, ingestion_snapshot (`{catalog}:{chunk_count}:{ingestion_date}`), gate_eligible, …
Validators:     GoldLabelBootstrap single-value ingestion_snapshot; validate_ingestion_snapshot_consistency
Consumers:      EvalHarness, IntentScopeResolver, compare/baseline validation
Last changed:   2026-07-01
```

```
Contract:       HarnessRun / HarnessResult / HarnessReport (eval run envelope)
Module:         eval/retrieval/models.py
Serialization:  Pydantic v2 ↔ JSON reports + EvalStore rows
Version:        unversioned — tracked by git blame
Purpose:        Harness manifest, per-intent results, and finalized report with gate summary; also pipeline agent-run envelope (M-RE2)
Fields:
  - HarnessRun: run_id, run_type (`baseline` | `enhancement` | `ablation` | `ci_fixture` | `pipeline`), pipeline_thread_id, company_name, catalog, registry_hash, gold_snapshot, intent_count, harness_status, ablation_config, ablation_arm, baseline_ref_run_id, fallback_rate, empty_rate, e2e_agent_id, e2e_snapshot_table, e2e_checklist_score, e2e_checklist_total, …
  - HarnessResult: intent_id, mode, ranked_chunk_ids, recall_at_k, mrr, basis_conflict_at_10, eval_status, ablation_arm, …
  - HarnessReport: manifest + results + deltas + provenance + intent_gate_summary
Validators:     EvalStore finalize_run intent_count match; golden compare_gate_cases.yaml; record_e2e_linkage raises on missing run_id
Consumers:      EvalHarness, SqliteEvalStore, DeltaEvalStore, harness_cli, open_agent_run/close_agent_run, record_e2e_linkage
Last changed:   2026-07-06
```

```
Contract:       ProvenanceRecord (per retrieval call)
Module:         eval/retrieval/models.py, eval/retrieval/provenance.py
Serialization:  Pydantic v2 ↔ Delta/SQLite `{catalog}.ops.retrieval_provenance`
Version:        unversioned — tracked by git blame
Purpose:        Ranked chunk attribution per intent with optional context allocation patch fields
Fields:
  - intent_id, company_name, query, mode, chunks: list[ProvenanceChunk] (chunk_id, rank, score, file_name, …)
  - chars_allocated, context_section: optional — patched post-context-build by ProvenanceEmitter.patch_context_allocations
  - run_id: pipeline agent_run_id (not harness baseline run_id)
Validators:     normalize_mode aliases; test_provenance_emitter.py; test_delta_concurrency_retry.py
Consumers:      retrieval._emit_provenance, OpexSubAgent allocation patch, eval harness provenance export
Last changed:   2026-07-06
```

```
Contract:       uc13.ops eval store tables (Delta + SQLite mirror)
Module:         eval/retrieval/scripts/apply_ops_ddl.sql, eval/retrieval/store.py
Serialization:  Delta tables `{catalog}.ops.harness_runs`, `harness_results`, `harness_deltas`, `provenance_records` (+ sqlite mirror)
Version:        unversioned — Appendix I shapes
Purpose:        Durable harness manifests, results, deltas, and provenance for baseline/enhancement compare
Fields:
  - Upsert keys per spec §5.12.9: (run_id), (run_id, intent_id), (run_id, intent_id, metric), (run_id, intent_id, chunk_id, rank)
Validators:     test_eval_store.py sqlite round-trip; apply_ops_ddl CLI
Consumers:      EvalHarness dual-write, harness_cli `--store-backend delta`, promote_sqlite_run
Last changed:   2026-07-01
```

```
Contract:       IndexSyncError (pipeline error envelope)
Module:         databricks/jobs/scripts/ingestion_parser.py
Serialization:  Python exception (message-only; no custom fields or JSON envelope)
Version:        unversioned — tracked by git blame
Purpose:        Fail-closed halt when vector-index Delta Sync cannot complete — closes O-07/P-06 fail-open risk on notebook mutation surface
Fields:
  - message: str — binding templates per fatal path:
    - timeout: `sync exceeded max_wait_seconds={max_wait_seconds}s — pipeline state={state_str}, indexed={indexed_rows}/{total_emb}`
    - terminal FAILED/CANCELED: `index sync halted — {index_name}: pipeline state={state_str}, indexed={indexed_rows}/{total_emb}`
    - outer except: `index sync failed for {index_name}: {e}` (original exception chained via `from e`)
Validators:     Raised only inside `_wait_for_index_sync`; `except IndexSyncError: raise` guard prevents double-wrap by generic handler; stdout must contain `✗ Sync failed — halting` before raise on all three fatal paths; success path must contain `✓ Index ready`; all three fatal paths (terminal FAILED/CANCELED, timeout, outer generic-exception wrap) covered by `tests/test_ingestion_parser_sync.py`
Consumers:      `ingestion_parser.main()` (Cell 7), `ensure_coverage.ingest_missing()` (Cell 8d, inherited via `ip._wait_for_index_sync`), `tests/test_ingestion_parser_sync.py`, M-PHV1 exit-gate runbook in `databricks/CLAUDE.md`
Last changed:   2026-07-07
```

```
Contract:       _TYPE_ORDER canonical source-type rank (R-09)
Module:         databricks/agents/shared/retrieval.py (canonical); imported by context_utils.py
Serialization:  Python module-level dict constant
Version:        unversioned — tracked by git blame
Purpose:        Single mutation surface for table/vision/text sort order in merge-rank tie-break and build_focused_context
Fields:
  - {"table": 0, "vision": 1, "text": 2}
Validators:     test_type_order_is_canonical_across_retrieval_and_context_utils asserts identity binding (context_utils._TYPE_ORDER is retrieval._TYPE_ORDER)
Consumers:      retrieval.semantic_search source_type_priority branch; context_utils.build_focused_context
Last changed:   2026-07-15
```

```
Contract:       Join integrity preflight (R-08)
Module:         tests/test_join_integrity.py; eval/retrieval/README.md § `## join integrity (R-08)`
Serialization:  pytest synthetic fixture + operator SQL runbook
Version:        unversioned — tracked by git blame
Purpose:        CI regression guard that chunks↔doc_relevance inner join (`c.file_name = r.filename`, `c.company_name = r.company_name`) does not silently drop orphan chunks
Fields:
  - Synthetic orphan/non-orphan rows; predicate presence checks on _hydrate_chunks_sql and gold/bootstrap.py
Validators:     tests/test_join_integrity.py; README operator LEFT JOIN orphan-count SQL (cluster preflight, not CI-substitute)
Consumers:      CI gate; operator cluster orphan-count procedure before gold rebootstrap
Last changed:   2026-07-15
```

```
Contract:       Catalog convention (production vs eval)
Module:         databricks/jobs/scripts/*, databricks/agents/workstreams/*, `databricks/CLAUDE.md` § Catalog convention
Serialization:  `get_param("catalog", default="uc13")` on production entrypoints; notebook Cell 1 widget default `uc13_ale`
Version:        M-PHV3 (spec §5.12.3)
Purpose:        Separate production Unity Catalog (`uc13`) from eval/PHV harness catalog (`uc13_ale`); prevent module-level shadow constants bypassing widget/env resolution
Fields:
  - production default: `"uc13"` — all `main()` in jobs/scripts and workstream agents
  - eval default: `"uc13_ale"` — `test_pipeline.ipynb` Cell 1 widget + workflow YAML job parameter default
  - instance state: `self._catalog` on BMA/FTA/CQA/KPI/QoE agents (set in `run()` from `catalog` kwarg)
Validators:     `tests/test_catalog_convention.py` — rule 1 (`get_param` defaults), rule 2 (notebook widget pin), rule 3 (no `_CATALOG` shadow / bare literal bypass)
Consumers:      All Phase 2–3 pipeline scripts and agents; workflow YAML `catalog` parameter; eval harness
Last changed:   2026-07-13
```

```
Contract:       PromotionResult
Module:         eval/retrieval/promotion_gate.py
Serialization:  frozen dataclass
Version:        M3 (Decision M3-C)
Purpose:        Typed outcome of checklist-regression promotion gate
Fields:
  - status: Literal["baseline_bootstrap", "promoted", "promotion_blocked", "promotion_waived"]
  - candidate_score: int
  - candidate_total: int
  - prior_run_id: str | None
  - prior_score: int | None
  - waiver_id: str | None (^W\d+$ when present)
Validators:     test_promotion_gate.py — all five branches + InvalidWaiverIdError
Consumers:      evaluate_promotion, operator scorecards (.dev/scorecards/)
Last changed:   2026-07-21
```

```
Contract:       DAG run manifest (in-memory + persisted)
Module:         databricks/agents/orchestration/pipeline.py
Serialization:  Python dict → JSON in analysis.diligence_report.agent_run_manifest_json
Version:        unversioned — tracked by git blame
Purpose:        Per-agent SUCCESS/FAILED/SKIPPED status, attempts, errors, timing for Phase 3–5 DAG
Fields:
  - company_name, catalog, generated_at
  - summary: {SUCCESS, FAILED, SKIPPED counts}
  - runs: [{agent, status, attempts, error, duration_s, degraded_from, …}]
  - report_md_path, report_docx_path (after Phase 5)
Validators:     none automated — operator e2e gate
Consumers:      orchestrator_agent.main(manifest=), run_full_pipeline.py return dict
Last changed:   2026-07-24
```

```
Contract:       build_exec_summary return paths
Module:         databricks/agents/exec_summary/pipeline_entry.py
Serialization:  Python dict[str, str]
Version:        T9 (hector-ui-pipeline-merge)
Purpose:        Volume paths for Rev3 executive summary artifacts after DAG completion
Fields:
  - tldr_md, full_report_md, tldr_docx, full_report_docx: absolute Volume paths
Validators:     tests/test_pipeline_entry.py — stage order via mocks
Consumers:      run_full_pipeline.py, run_vdr_pipeline.py (copies tldr_docx → executive_summary.docx)
Last changed:   2026-07-24
```

```
Contract:       orchestrator_bundle Rev3 executive extensions
Module:         databricks/agents/exec_summary/orchestrator_bundle.schema.yaml
Serialization:  JSON Schema draft-07
Version:        Rainmaker Rev3 (2026-07-22)
Purpose:        Optional Rainmaker synthesis fields for compressed one-pager
Fields:
  - executive.thesis_bullets: string[] (optional)
  - executive.key_watchouts: string[] (optional)
  - company_framing.workforce_notes: string | null (optional)
  - executive.preliminary_digest: string — drives Preliminary View in Rev3 template
Validators:     tests/test_orchestrator_bundle_builder.py round-trip + additionalProperties guards
Consumers:      BundleBuilder stage-6, tldr_compress, tldr_one_pager_compressed.md.j2
Last changed:   2026-07-22
```

```
Contract:       Golden checklist row (per-agent)
Module:         eval/<AGENT>/golden_checklist_elder_care.md
Serialization:  Markdown table (item_id, field, verdict, notes)
Version:        M1–M2 (uc13-eval-harness-all-agents)
Purpose:        Manual golden evidence for promotion gate scoring
Fields:
  - item_id, field/criterion, verdict (pass | gap-correct), evidence notes
  - summary row: N/M score
Validators:     tests/test_golden_checklist_elder_care.py CHECKLIST_CASES hub — row count vs GOLDEN_CHECKLIST_COVERAGE
Consumers:      evaluate_promotion operator workflow, .dev/scorecards/
Last changed:   2026-07-21
```

```
Contract:       doc_id (canonical document identity)
Module:         databricks/jobs/scripts/doc_id.py
Serialization:  Python function → md5 string; persisted as `doc_id STRING` column
Version:        unversioned — tracked by git blame (M0 ingestion refactor)
Purpose:        Single join key across ingestion tables, replacing the (file_name, company_name) composite key
Fields:
  - make_doc_id(catalog, schema, company, folder_path, file_name) -> str  (md5 hex digest)
  - doc_id column added to: {catalog}.ingestion.chunks, {catalog}.ingestion.doc_relevance (classification), doc_status
Validators:     document_classifier._backfill_missing_doc_ids MERGE fills NULL doc_id; doc_id_hash_catalog widget guards catalog-mismatch orphaning
Consumers:      retrieval.py chunks↔doc_relevance JOIN, parse_manifest.py, ensure_coverage.py, ingestion_parser._resolve_force(), download_upload.py
Last changed:   2026-08-06
```

```
Contract:       doc_status (per-document ingestion state)
Module:         databricks/jobs/scripts/status_store.py
Serialization:  Delta table {catalog}.ingestion.doc_status
Version:        unversioned — tracked by git blame (M0 ingestion refactor)
Purpose:        Per-(company_name, doc_id) resumable ingestion state machine, replacing whole-company DELETE+APPEND
Fields:
  - company_name, doc_id, status: PENDING | PARSING | EMBEDDING | COMPLETE | FAILED | ZERO_CHUNKS
  - updated_at, error_reason (on FAILED)
Validators:     status_store.ensure_doc_status() DDL; DocWorker state transitions; tests/test_docworker_state_transitions.py
Consumers:      doc_worker.DocWorker, ingestion_parser.main() (skip-if-COMPLETE), sync_state.py (has_newer_complete_than), measure_attestation.py (G5 gate)
Last changed:   2026-08-06
```

```
Contract:       sync_state (vector-index SyncGate watermark)
Module:         databricks/jobs/scripts/sync_state.py
Serialization:  Delta table {catalog}.ingestion.sync_state
Version:        unversioned — tracked by git blame (M0 ingestion refactor)
Purpose:        Gate VS Delta Sync so it only re-triggers after new COMPLETE doc rows since the last watermark
Fields:
  - catalog_scope, last_synced_at (or max COMPLETE doc updated_at at last advance)
Validators:     ensure_sync_state() DDL; read_watermark/advance_watermark round-trip
Consumers:      ingestion_parser.main() (skip_sync / sync_only operator knobs)
Last changed:   2026-08-06
```

```
Contract:       companies_vdr_history (VDR trigger/status row)
Module:         rallyday_partners_llc.default.companies_vdr_history (no DDL in repo — table pre-exists)
Serialization:  Delta table row
Version:        unversioned — tracked by git blame; shared by run_vdr_pipeline.py and run_vdr_rainmaker.py
Purpose:        Operator-submitted VDR trigger + lifecycle status for both the production docx pipeline and the Rainmaker POC
Fields:
  - processing_status: submitted → processing → done | error
  - completion_status, error_message, results_location, updated_at, last_updated_by ("vdr-backend-ai" | "vdr-rainmaker-poc")
Validators:     none automated — operator-observed; Rainmaker sets completion_status=success with explanatory error_message on no-CIM skip
Consumers:      run_vdr_pipeline.py, run_vdr_rainmaker.py, VDR UI
Last changed:   2026-08-19
```

```
Contract:       eval.s2_scores (content-correctness append-only store)
Module:         databricks/ddl/s2_scores.sql; eval/content/s2_writer.py
Serialization:  Delta table {catalog}.eval.s2_scores
Version:        spec §8.8/§9 (eval-consolidation program)
Purpose:        Append-only claim-verdict + completion-marker rows for the three-rung content-correctness model (deterministic | judge | human)
Fields:
  - company, surface, run_id (YYYYMMDDTHHMMSSZ-<suffix>), run_ts, row_type: claim | completion_marker
  - claim_id, verdict, rationale, writer: deterministic_verifier | judge_harness | human_spot_check
  - magnitude/unit fields (rung-scoped), citation locator fields, judge_verdict_advisory
Validators:     S2Writer claims-then-marker write ordering; S-61 fail-closed cited-chunk resolution; tests/test_s2_writer.py
Consumers:      eval/content/legal_register_verifier.py, eval/content/spot_check.py, eval/retrieval/trust_statement.py (content_correctness tier derivation)
Last changed:   2026-08-13
```

```
Contract:       exec_summary_rubric_claims.json / fta_numeric_rubric_claims.json (whole-surface claim manifests)
Module:         eval/content/exec_summary_rubric_claims.json, eval/content/fta_numeric_rubric_claims.json
Serialization:  JSON, schema_version: 1
Version:        1
Purpose:        Committed whole-surface claim enumeration used by calibration and spot-check as the closed claim universe
Fields:
  - exec: 53 claims (exec.claim.001–053); source_query, created_at, generator, calibration_sample pointer, claims[{section, claim_id, claim_text, origin}]
  - fta_numeric: 276 claims (fta.claim.001–276); surface, source_query, probe_report, claims[{claim_id, claim_text, source_doc, source_location}]
Validators:     tests/test_exec_summary_spot_check_rubric.py — rubric ↔ manifest ↔ calibration sample ↔ source fixture alignment (HALT-15 coverage)
Consumers:      spot_check.load_claim_enumeration, calibration.py, extract_rubric_manifests.py (regenerates from rubric markdown)
Last changed:   2026-08-13
```

```
Contract:       calibration_samples (*.yaml) — CHK-26a judge calibration input
Module:         eval/content/calibration_samples/calibration_sample_exec_summary.yaml, calibration_sample_fta_numeric.yaml
Serialization:  YAML, schema_version: 1 (Decimal-safe custom loader)
Version:        1
Purpose:        Operator-labeled samples used to calibrate the LLM judge against human verdicts (subset of the full claim manifest)
Fields:
  - exec_summary: N=28 — claim_id, claim_text, source_ref, verdict (supported | contradicted | unsupported)
  - fta_numeric: N=30 — adds expected_value {magnitude: decimal string, unit}, expected_span {chunk_id, locator?}
Validators:     agreement.evaluate_thresholds (verdict≥0.80 exec; value≥0.90, span≥0.80 fta_numeric); tests/test_calibration_dual_source.py, test_calibration_locator.py
Consumers:      calibration.run_calibration
Last changed:   2026-08-13
```

```
Contract:       spot-check artifact family (*.presentation.yaml / *.verdicts.yaml / *.draft_audit.json / *.review_queue.md / *.escalations.md / *.failure_modes.md / *.m3_backlog.md / *.backfill.yaml)
Module:         eval/content/spot-check/ (FORMAT.md is the authoritative contract doc)
Serialization:  Mixed — YAML (schema_version: 1) for presentation/verdicts/backfill; JSON (schema_version: 1) for draft_audit; Markdown for review_queue/escalations/failure_modes/m3_backlog
Version:        spot_check_presentation_v1 / spot_check_backfill_v1 (format tags); schema_version: 1
Purpose:        Human rung-3 spot-check lifecycle artifacts — claim packet → operator adjudication → S2 write → audit trail
Fields:
  - presentation.yaml: enumerated claims + citations for operator review
  - verdicts.yaml: operator verdicts, optional status: operator_approved
  - draft_audit.json: agent draft verdicts + confidence + retrieval metadata (status: draft)
  - backfill.yaml: historical citation backfill audit trail (supersedes prior run_id)
Validators:     spot_check.write_spot_check_results — fail-closed on unknown claim_id / invalid verdict vocab / missing required rationale; tests/test_spot_check.py
Consumers:      eval/content/spot_check.py prepare/ingest pipeline; operator review workflow
Last changed:   2026-08-13
```

```
Contract:       eval/program governance artifacts (registry.yaml, product_backlog.yaml, eval_debt.yaml, eval_exemptions.yaml, onboarding_queue.yaml, source_manifest.yaml)
Module:         eval/program/registry.yaml, product_backlog.yaml, eval_debt/eval_debt.yaml, eval_exemptions.yaml, onboarding_queue.yaml, source_manifest.yaml
Serialization:  YAML, schema_version: 1 (all six)
Version:        1 (source_manifest.yaml additionally carries frozen_at; onboarding_queue.yaml carries generated_at)
Purpose:        Durable cross-company program governance ledgers — work-item decisions/waivers (registry), Elder Care product signals (product_backlog), tracked-gap ledger with high-water-mark ratchet (eval_debt), intent-level corpus-gap annotations (eval_exemptions), ranked SharePoint onboarding queue (onboarding_queue), import-time provenance join partner for registry (source_manifest)
Fields:
  - registry: items[] {id, title, source_refs, source_id, disposition, stage, status, trigger, rationale, tshirt, evidence_refs, rung_assignments, assessment_metrics}
  - product_backlog: items[] {id, company, surface, kind, severity, summary, evidence_refs, fix_lane, closes_when, registry_ref?}
  - eval_debt: open_debt_high_water_mark, debts[] {id: "{company}:{surface|global}:{kind}", opened_at, evidence_refs, closes_when, closed_at?, closed_evidence_refs?}
  - eval_exemptions: exemptions[] {company, intent_id, surface, coverage: eliminates|narrows|null, reason, corpus_evidence, approved_by}
  - onboarding_queue: catalog, generated_at, companies[] {display_name, slug, chunk_count, ingest_completeness_ratio, doc_type_diversity_score, rank_score, wave, notes}
  - source_manifest: frozen_at, sources[] {id, source_ref, title}
Validators:     test_eval_program_registry.py, test_product_backlog_schema.py, test_eval_debt.py (HWM ratchet), test_onboarding_queue_schema.py
Consumers:      eval_debt.py, exemptions.py, trust_statement.py, onboarding_cluster_submit.py, .dev/eval-program/build_onboarding_queue.py
Last changed:   2026-08-19
```

```
Contract:       gold_exclusions.yaml / kpi_claim_intent_map.yaml (company-scoped gold bootstrap inputs)
Module:         eval/retrieval/gold/gold_exclusions.yaml, eval/retrieval/gold/kpi_claim_intent_map.yaml
Serialization:  YAML
Version:        unversioned — tracked by git blame
Purpose:        gold_exclusions pre-populates per-intent aggregate_exclude/exclude_reason for company-specific corpus gaps; kpi_claim_intent_map is a fail-closed claim↔intent totality map for 7 KPI intents across four companies' industry-specific claim shapes (Excel/PDF backfill)
Fields:
  - gold_exclusions: companies.{slug}.excluded[] {intent_id, exclude_reason}
  - kpi_claim_intent_map: claims{}, intents{} totality block
Validators:     GoldLabelBootstrap._bootstrap_pass1 consumption; test_gold_exclusions.py
Consumers:      eval/retrieval/gold/bootstrap.py, scope_resolver.is_gate_eligible
Last changed:   2026-08-18
```

```
Contract:       gold_labels/{clearsulting,gkf,spg}.yaml (multi-company gold coverage)
Module:         eval/retrieval/gold_labels/clearsulting.yaml, gkf.yaml, spg.yaml (new; elder_care.yaml pre-existing)
Serialization:  YAML — same schema as elder_care.yaml (GoldLabel per intent)
Version:        unversioned — tracked by git blame
Purpose:        Extends gold-label coverage from Elder Care only to four companies, all 57 intents, per eval-multi-company-coverage-expansion (M5)
Fields:
  - clearsulting: 28 ready, 9 partial, 20 bootstrap_failed, 13 aggregate_exclude
  - gkf: 22 ready, 35 bootstrap_failed, 26 aggregate_exclude
  - spg: 35 ready, 3 partial, 19 bootstrap_failed, 13 aggregate_exclude
Validators:     tests/test_gold_bootstrap.py (registry-id parity, ingestion_snapshot consistency)
Consumers:      harness.py compare/baseline, trust_statement.py (28-row domain = 4 companies × 7 layer/surface rows)
Last changed:   2026-08-18
```

