Section:      known-coupling-surfaces
Version:      2.6.0
Last updated: 2026-08-20

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

```
Surface:      retrieval_mode widget + os.environ mirror (legacy notebook only post-M-PHV4)
Shared by:    test_pipeline.ipynb Cell 1 ↔ Cell 1a set_retrieval_mode() ↔ financial_trends_eval_snapshot rows
Failure mode: Operator assumes widget still threads into FTA production retrieval; stale snapshot arm labels if Cell 12a skipped
Confirmed:    yes — M-PHV4 T2 removed `retrieval_mode` from FTA orchestrator/sub-agents; widget retained for legacy snapshot cells only; production path is context_utils → fallback.py
```

```
Surface:      VS columns_to_sync list
Shared by:    setup_vector_search.py ↔ ingestion_parser.py embeddings DDL ↔ 00_setup_vector_search.ipynb ↔ tests/test_setup_vector_search.py
Failure mode: company_name filter pushdown returns empty or index sync omits metadata columns
Confirmed:    yes — static contract tests added in T3
```

```
Surface:      enhanced_semantic ≡ semantic code path
Shared by:    context_utils.semantic_search_with_fallback ↔ tests/test_context_utils.py pytest guard (RB D7a)
Failure mode: Eval arms diverge if enhanced_semantic gains distinct behavior without updating guard
Confirmed:    yes — identical semantic_search kwargs asserted in test_enhanced_semantic_matches_semantic_kwargs
```

```
Surface:      _TYPE_ORDER source-type ranking dict (R-09 — closed M-PHV4 T1)
Shared by:    retrieval.py module constant ↔ context_utils.py import (same object identity)
Failure mode: Reintroducing a local shadow constant in either module re-opens merge-rank vs context-assembly rank drift
Confirmed:    yes — test_type_order_is_canonical_across_retrieval_and_context_utils; prior duplicate closed per m-phv4-t1-r09-type-order-dedup.md
```

```
Surface:      financial_trends vs financial_trends_eval_snapshot
Shared by:    financial_trends_agent.main() (one row per company, delete-before-write) ↔ snapshot cell (one row per company+mode)
Failure mode: A/B eval loses prior arm output if snapshot cell not run between arms
Confirmed:    yes — RT7 scorecard used eval_snapshot table; operator runbook documents sequence
```

```
Surface:      Eval catalog default (`uc13_ale`) vs production `_default_catalog()` (`uc13`)
Shared by:    IntentRegistryExtractor.DEFAULT_CATALOG ↔ intent_registry.yaml ↔ gold_labels/elder_care.yaml ↔ harness_cli `--catalog` ↔ context_utils._default_catalog() ↔ legal_contracts_agent catalog threading
Failure mode: Harness baseline runs against wrong VS index; production agents retrieve empty while eval passes (or vice versa)
Confirmed:    yes — D5-A: registry/harness `uc13_ale`; `_default_catalog()` unchanged; global catalog default change deferred to multi-company rollout
```

```
Surface:      intent_registry.yaml ↔ registry_extractor ↔ harness registry_hash
Shared by:    IntentRegistryExtractor ↔ committed `intent_registry.yaml` ↔ `compute_registry_hash` in harness ↔ `RegistryHashMismatchError`
Failure mode: CI drift gate fails or harness compares against stale intent set after agent retrieval edits without re-extract
Confirmed:    yes — `test_registry_hash_stable_for_ci_drift_gate` in test_registry_extractor.py
```

```
Surface:      gold_labels ingestion_snapshot single-value contract
Shared by:    GoldLabelBootstrap.format_ingestion_snapshot ↔ committed elder_care.yaml ↔ harness validate_baseline_ref ↔ `IngestionSnapshotMismatchError`
Failure mode: Baseline compare invalid after Cell 7 rebuild without gold rebootstrap
Confirmed:    yes — normative `{catalog}:{chunk_count}:{ingestion_date}` in bootstrap.py; T6 decision log
```

```
Surface:      uc13.ops DDL ↔ EvalStore backends
Shared by:    eval/retrieval/scripts/apply_ops_ddl.sql ↔ apply_ops_ddl.py ↔ SqliteEvalStore schema ↔ DeltaEvalStore (`{catalog}.ops.*`)
Failure mode: Cluster delta harness writes fail if DDL not applied; sqlite/delta column drift
Confirmed:    yes — T7 ships DDL + CLI; test_apply_ops_ddl_sql_contains_catalog_placeholder
```

```
Surface:      RouteResult mode vocabulary production vs harness normalization
Shared by:    retrieval.semantic_search ↔ context_utils wrappers ↔ EvalHarness.normalize_mode (`vector`→`semantic`, `keyword_fallback`→`keyword`)
Failure mode: fallback_rate under-reported if wrappers hardcode `mode="semantic"` on keyword path (fixed D3-A)
Confirmed:    yes — D3-A mode propagation; test_semantic_search_returns_route_result falsifiers
```

```
Surface:      analysis.legal (TABLE write) vs analysis.legal_contracts (compat VIEW)
Shared by:    legal_contracts_agent._ensure_legal_storage() ↔ main() DELETE/append ↔ test_pipeline.ipynb Cell 18 ↔ databricks/CLAUDE.md ↔ uc13_ingestion_pipeline.yml task description
Failure mode: Legacy consumers query dropped TABLE; new writes target wrong relation; Cell 18 inspects wrong object type
Confirmed:    yes — T3 DROP TABLE + CREATE VIEW; M0 workflow documents standalone `analysis.legal` writes
```

```
Surface:      CQA contract_trigger_list optional read
Shared by:    customer_quality_agent.py (writes `contract_trigger_list`) ↔ legal_contracts_agent._load_contract_triggers()
Failure mode: Missing CQA run blocks legal agent (should not — M0 workflow has no CQA dependency)
Confirmed:    yes — `_load_contract_triggers` returns [] on miss and logs gap; legal_contracts_agent depends_on company_profiler only in workflow YAML
```

```
Surface:      legal module filename vs spec target name (A2 rename waiver)
Shared by:    legal_contracts_agent.py ↔ charter M0 waiver ↔ architecture docs ↔ workflow python_file
Failure mode: M1+ executor imports `legal_agent` and HALTs; docs drift to renamed module before code lands
Confirmed:    yes — charter v0.1.2 A2 deferred; architecture retains `legal_contracts_agent.py` / `LegalContractsAgent`
```

```
Surface:      _DOMAIN_PASS_* module registries (budgets, queries, extract prompts)
Shared by:    legal_contracts_agent._DOMAIN_PASSES ↔ _bind_domain_passes ↔ _domain_retrieve_pass ↔ _domain_extract_pass ↔ tests/test_legal_contracts_agent*.py
Failure mode: Pass ID rename or budget key drift breaks loop binding or AST contract tests without coordinated update
Confirmed:    yes — five pass IDs frozen in M1 plan §2; AST tests assert delegation wiring
```

```
Surface:      Legal retrieval catalog threading (D3a)
Shared by:    legal_contracts_agent._semantic_search_with_fallback ↔ retrieval.semantic_search(catalog=self._catalog) ↔ M0 catalog param on run()
Failure mode: Empty retrieval against wrong VS index when catalog widget is uc13_ale but search defaults to uc13
Confirmed:    yes — T2 decision log; test_semantic_search_calls_pass_catalog AST guard
```

```
Surface:      Legal must NOT use context_utils.semantic_search_with_fallback
Shared by:    legal_contracts_agent (instance _semantic_search_with_fallback) ↔ context_utils (_default_catalog → uc13)
Failure mode: Silent wrong-catalog retrieval if legal adopts FTA adapter without catalog override
Confirmed:    yes — T2 decision log D7a; test_does_not_import_financial_semantic_search_with_fallback
```

```
Surface:      build_focused_context importlib binding (legal extract)
Shared by:    legal_contracts_agent._domain_extract_pass ↔ context_utils.build_focused_context ↔ test_legal_contracts_agent_extract.py AST
Failure mode: Static `from context_utils import` breaks AST guard; circular import if top-level import added carelessly
Confirmed:    yes — T3 decision log; importlib preserves T2 static import ban
```

```
Surface:      D2a normative extraction field names vs M2 roll-up helpers
Shared by:    §5.8 user prompts (restrictive_covenants, liability_indemnity) ↔ dormant _build_restrictive_covenant_map / _apply_legal_flags (exclusivity_mfn_noncompete, liability_cap)
Failure mode: M2 roll-ups/flags silently empty or wrong if helpers wired without field-name reconciliation
Confirmed:    yes — M1 auditor F-OBS-1; roll-up helpers not invoked in M1 run()
```

```
Surface:      D6a extraction_endpoint Haiku/Llama → Sonnet override
Shared by:    legal_contracts_agent.main() ↔ test_pipeline.ipynb Cell 1 widget default (Haiku) ↔ uc13_ingestion_pipeline.yml job default (Sonnet)
Failure mode: Truncated JSON / empty pass registers when notebook runs with Haiku widget and override removed
Confirmed:    yes — T4 decision log; test_main_sonnet_override_for_haiku_llama AST; M1 wet-run CHANGELOG
```

```
Surface:      Legal domain trace step vocabulary
Shared by:    legal_contracts_agent run loop ↔ reasoning_trace JSON ↔ M1 exit gate (5× domain_retrieve_* + 5× domain_extract_* + load_company_profile + retrieval_fallback)
Failure mode: Observability/regression checks fail if tool_name strings change without updating eval harness
Confirmed:    yes — M1 T5 cluster wet run (Elder Care 2026-06-26); no pytest step-count guard (D4a waived)
```

```
Surface:      Delta flags shape → orchestrator ingest
Shared by:    Phase 3 agent analysis tables (flags JSON) ↔ orchestrator/ingest.py snapshot readers
Failure mode: populate_bundle omits or mis-parses agent metrics when flags column shape drifts
Confirmed:    suspected — ingest reads latest row per agent; no unified flags schema module
```

```
Surface:      company_safe Volume path segments
Shared by:    paths.company_safe ↔ reports_volume_dir ↔ orchestrator DOCX cells ↔ demo_walkthrough artifact checks
Failure mode: Files written under spaced company dir while readers expect Elder_Care (or vice versa)
Confirmed:    yes — D-M1-2 closed; orchestrator uses company_safe not raw sp_company_name for Volume paths
```

```
Surface:      catalog widget / os.environ default
Shared by:    test_pipeline.ipynb Cell 1 widgets ↔ get_param() in agents and demo_walkthrough
Failure mode: Demo walkthrough reads wrong catalog Volume when widget unset locally
Confirmed:    yes — demo_walkthrough defaults catalog=uc13_ale, sp_company_name=Elder Care per M1 packet
```

```
Surface:      AGENT_DELTA_TABLE_SUFFIXES single source (D-M2-8)
Shared by:    constants.AGENT_DELTA_TABLE_SUFFIXES ↔ ingest.py ↔ bundle_builder provenance.agent_delta_tables
Failure mode: Table name drift if suffix dict updated in one module but not the other
Confirmed:    yes — deduped in M2 T1; ingest imports from constants
```

```
Surface:      FIELD_MAPPINGS transform registry keys
Shared by:    field_mapping.FIELD_MAPPINGS ↔ apply_field_mappings transform dispatch ↔ test_bundle_builder expectations
Failure mode: New Appendix B row added without transform handler → empty bundle field at runtime
Confirmed:    yes — 17 rows in FIELD_MAPPINGS; Elder Care fixtures in tests/fixtures/
```

```
Surface:      TLDR_REQUIRED_FIELDS ↔ collect_synthesis_gaps ↔ demo_walkthrough gates
Shared by:    constants.TLDR_REQUIRED_FIELDS ↔ bundle_builder.collect_synthesis_gaps ↔ demo_walkthrough synthesis gap checks
Failure mode: TL;DR gate passes with missing fields or fails on intentional gaps
Confirmed:    yes — Appendix B path list in constants.py
```

```
Surface:      TLDR_RENDER_MODE widget + os.environ mirror
Shared by:    test_pipeline.ipynb Cell 1 ↔ renderers.render_to_volume ↔ get_param()
Failure mode: Stale render mode after widget change without os.environ sync; full_report accidentally coupled to mode
Confirmed:    yes — K4 falsifier in test_tldr_compression.py asserts full_report independence
```

```
Surface:      ORCHESTRATOR_USE_BUILDER env gate
Shared by:    test_pipeline.ipynb orchestrator render cell ↔ Cell 19 BundleBuilder output on Volume
Failure mode: Render cell re-runs populate_bundle (demo_mode: true) over production bundle
Confirmed:    yes — CHANGELOG.MD T6; render cell checks on-Volume bundle demo_mode flag
```

```
Surface:      SEVERITY_RANK dict (risks ordering)
Shared by:    tldr_compress.SEVERITY_RANK ↔ bundle_builder.merge_risks_from_flags severity sort
Failure mode: Risk table order diverges between canonical bundle and compressed TL;DR if ranks drift
Confirmed:    yes — comment in tldr_compress.py references populate L117 parity
```

```
Surface:      format_diligence_entry dict vs str branches
Shared by:    formatters._diligence_text_from_entry ↔ GapAggregator.build_diligence_questions ↔ bundle_builder KPI missing-KPI loop
Failure mode: KPI diligence rows render as Python dict repr in TL;DR (pre-T8 bug)
Confirmed:    yes — T8 routes dict entries through format_diligence_entry; test_kpi_missing_dict_diligence_question_readable
```

```
Surface:      pipeline_thread_id + agent_run_id run attribution
Shared by:    agents/shared/run_context.py ↔ EvalStore pipeline manifests ↔ uc13.ops.retrieval_harness_runs ↔ uc13.ops.retrieval_provenance.run_id
Failure mode: Provenance rows orphaned or attributed to wrong pipeline envelope when Cell 1 omits set_pipeline_thread or agent main() skips open/close
Confirmed:    yes — M-RE2 T1/T4; test_run_context.py + test_pipeline_agent_run_context.py AST guards
```

```
Surface:      ProvenanceEmitter lazy import from semantic_search
Shared by:    databricks/agents/shared/retrieval.py _emit_provenance ↔ eval/retrieval/provenance.py ↔ run_context open agent run
Failure mode: Silent no-op provenance when RE2_PROVENANCE_REQUIRED=0 and no open run; ImportError if REPO_ROOT not on sys.path on cluster
Confirmed:    yes — lazy import inside emit hook; test_semantic_search_emits_provenance_when_run_open
```

```
Surface:      test_pipeline.ipynb Cell 1 + Cell 12 / Cell 12a ordering
Shared by:    set_pipeline_thread (Cell 1) ↔ fta.main() (Cell 12) ↔ financial_trends_eval_snapshot snapshot (Cell 12a) ↔ retrieval_mode widget
Failure mode: Wrong eval snapshot arm or missing pipeline_thread_id when agents run before Cell 1; snapshot lost if Cell 12a skipped before mode switch
Confirmed:    yes — M-RE2 T4/T9 runbook; eval/retrieval/README.md M-RE2 section
```

```
Surface:      _TYPE_ORDER rank vocabulary (retrieval.py vs context_utils.py) — **CLOSED M-PHV4 T1**
Shared by:    agents/shared/retrieval.py merge-rank ↔ context_utils.py build_focused_context sort (shared constant)
Failure mode: Reintroducing independent dict definitions would re-open provenance rank vs context assembly rank drift
Confirmed:    yes — identity test; superseded M-RE2 plan non-goal deferral
```

```
Surface:      run_context ContextVars (agent_run_id, active_store, pipeline_thread_id) vs threading fan-out
Shared by:    agents/shared/run_context.py open_agent_run/get_agent_run_id ↔ financial_trends_agent.FinancialTrendsAgent.run() ThreadPoolExecutor(max_workers=3)
Failure mode: ThreadPoolExecutor.submit() does not inherit the submitting thread's contextvars.Context; worker threads see agent_run_id=None and silently no-op provenance emission (0 rows, fallback_rate/empty_rate NULL) despite a successful, complete pipeline run
Confirmed:    yes — M-RE2 T4 post-landing cluster wet-run fix; each .submit() now wraps the callable with contextvars.copy_context().run(...); any future agent adding thread/process fan-out under an open agent run must do the same
```

```
Surface:      DeltaEvalStore shared instance ↔ concurrent MERGE/UPDATE from FTA sub-agent threads
Shared by:    eval/retrieval/store.py DeltaEvalStore.append_provenance (MERGE) ↔ eval/retrieval/provenance.py patch_context_allocations Delta branch (UPDATE) ↔ financial_trends_agent.py ThreadPoolExecutor(max_workers=3)
Failure mode: Concurrent Delta MERGE/UPDATE transactions against the same retrieval_provenance table from multiple threads raise ConcurrentAppendException/DELTA_CONCURRENT_APPEND_ROW_LEVEL_CHANGES even when row sets are logically disjoint (per-thread intent_id); a fixed-name temp view shared across the one SparkSession all three threads use was a second, silent-corruption risk (no exception, just wrong data)
Confirmed:    yes — M-RE2 T4 follow-on fix; retry_on_delta_conflict() wraps both write paths with backoff, and the temp view name is now UUID-suffixed per call. Second follow-on (A2, commit 71ce047) implemented the batch-per-sub-agent fallback: patch_context_allocations's Delta branch now batches all chunk updates for one call into a single MERGE (previously one UPDATE per allocated chunk), and DeltaEvalStore._provenance_write_lock serializes both write paths (append_provenance's MERGE and this batched MERGE) across the three FTA sub-agent threads sharing one store instance — eliminating self-collision by construction; retry_on_delta_conflict remains as defense-in-depth against other concurrent writers
```

```
Surface:      CREATE TABLE IF NOT EXISTS is a no-op on a pre-existing Delta table; sqlite's additive-migration guard had no Delta-side equivalent
Shared by:    eval/retrieval/scripts/apply_ops_ddl.py (reconcile_additive_columns) ↔ eval/retrieval/store.py DeltaEvalStore schema (_DELTA_RUNS_SCHEMA / _DELTA_PROVENANCE_SCHEMA) ↔ sqlite _ensure_schema ALTER TABLE guard
Failure mode: DELTA_METADATA_MISMATCH on open_agent_run() when a Delta table predates a schema-widening commit (e.g. pipeline_thread_id added in M-RE2 T1) — CREATE TABLE IF NOT EXISTS silently no-ops instead of widening the existing table
Confirmed:    yes — M-RE2 T1/A1 post-landing fix (commit 846eb1f); reconcile_additive_columns() diffs live table columns against the store schema after the CREATE TABLE IF NOT EXISTS loop and issues ALTER TABLE ADD COLUMNS for any gap, mirroring sqlite's pre-existing guard; eval/retrieval/tests/test_apply_ops_ddl_migration.py; .dev/decision-logs/T1-m-re2-run-context.md ("Post-landing fix")
```

```
Surface:      BMA/Legal/FTA shared fallback vs harness dispatch (M-RE3 R-03 + M-PHV4 Surface 11)
Shared by:    databricks/agents/shared/fallback.py::semantic_search_with_fallback ↔ BMA/Legal wrappers ↔ context_utils thin delegator (FTA) ↔ eval/retrieval/harness.py::dispatch_retrieval (production path)
Failure mode: Harness inline duplicate diverges from production retry semantics; Legal imports FTA adapter and loses catalog threading; registry extractor double-counts intents if shared function called under bare name at call site
Confirmed:    yes — M-RE3 T3 landed BMA+Legal; M-PHV4 T2/T3 landed FTA + harness unification; D4 aliased import at BMA/Legal call sites; test_harness_fixture.py delegation falsifiers
```

```
Surface:      registry_extractor RETRIEVAL_CALLS ↔ shared fallback import aliasing (D4)
Shared by:    eval/retrieval/registry_extractor.py _IntentVisitor ↔ databricks/agents/shared/fallback.py ↔ BMA/Legal wrapper methods
Failure mode: Bare `semantic_search_with_fallback(...)` call inside BMA/Legal wrapper doubles intent count in registry_extractor (breaks expected_intent_counts.yaml ±2 bound)
Confirmed:    yes — T3 decision log D4; aliased import at BMA/Legal call site only
```

```
Surface:      semantic_search merge_rank_mode ablation dispatch (M-RE3 D7)
Shared by:    eval/retrieval/harness.py dispatch_retrieval(ablation_arm=...) ↔ retrieval.semantic_search(merge_rank_mode=...) ↔ EvalHarness.run() manifest/result ablation_arm fields
Failure mode: Ablation arm name accepted but no ordering change — false HarnessDelta signal; `None`/`sim_tier` drift from pre-T4 default breaks baseline compare
Confirmed:    yes — T4 landed; tests/test_retrieval.py merge-rank falsifiers + eval/retrieval/tests/test_ablation.py fixture matrix proof
```

```
Surface:      vs_metadata_filters capability gated off (M-RE3 T2; M-PHV4 item 29 declined)
Shared by:    retrieval.semantic_search(vs_metadata_filters=False) ↔ _build_vs_filters_dict ↔ _query_vector_index filters_json AND merge ↔ R-02 README hub ↔ operator attestation m-phv4-r02-vs-metadata-filters-ab-elder-care-2026-07-15.md
Failure mode: Silent production behavior change if default flipped True without PG5 pass; partial-dimension FAIL at T1 gate would have blocked T2 (both dimensions PASS at M-RE3 execution)
Confirmed:    yes — capability landed M-RE3 T2; default False; item 16 A/B completed 2026-07-15 with PG5 numeric bar **fail** (max drop 5.88pp legal.litigation; aggregate recall@10 4.23%→4.16%); item 29 not activated; second-reviewer sign-off **waived for M-PHV4 exit** (packet sent 2026-07-15); `legal.litigation` debug deferred
```

```
Surface:      GLOBAL_RETRIEVAL_PATHS ↔ harness full-suite scope (§5.12.1)
Shared by:    eval/retrieval/scope_resolver.py GLOBAL_RETRIEVAL_PATHS += fallback.py ↔ retrieval.py kwargs ↔ IntentScopeResolver changed-intent-scope table row 1
Failure mode: Post-hardening baseline or ablation run with narrowed --affected-intents under-scopes gate computation relative to retrieval code changes
Confirmed:    yes — T3 registered fallback.py; T6 runbook requires omitting --affected-intents on post-hardening baseline
```

```
Surface:      baseline_ref_run_id authority / retrieval_harness_latest_baseline (Flag 7)
Shared by:    EvalHarness.validate_baseline_ref ↔ retrieval_harness_latest_baseline view ↔ ablation baseline_ref_run_id pins ↔ local eval/retrieval/reports/*.json exports
Failure mode: Incomplete or fixture baseline promoted as authoritative; ablation HarnessDelta computed against wrong reference; multiple baseline run_ids without operator designation
Confirmed:    yes — **W3 comparison epoch (D4, per-company):** Elder Care `baseline_2fa3a9056bd0`, Clearsulting `baseline_488f70f13570`, GKF `baseline_7510d1d14449`, SPG `baseline_3992534e412f` — operator-pinned M1 multi-company baselines; T4 evidence (`.dev/wave4-foldback-2026-08-20/m1-w3-retrieval-loop.md`) records all four `merge_rank_off` enhancements `gate_pass=false` → reject (successor `baseline_ref_run_id` unchanged). Supersedes single-baseline M-RE3 pin `baseline_299063e87806` for W3 loop compare authority. Incomplete local reports not promoted per runbook
```

```
Surface:      merge_rank_on ≡ production default (M-RE3 ablation control validation)
Shared by:    retrieval.semantic_search(merge_rank_mode=None|sim_tier) ↔ EvalHarness ablation arm merge_rank_on ↔ baseline compare HarnessDelta rows
Failure mode: False ablation PASS if merge_rank_on diverges from production path; false FAIL if control arm regresses vs post-hardening baseline
Confirmed:    yes — operator cluster attestation 2026-07-06: merge_rank_on gate_pass=true with zero HarnessDelta rows |delta|>0.001 vs baseline_299063e87806; alt arms (merge_rank_off, sim_only, tier_only) gate_pass=false with expected recall@10 regressions (e.g. fta.revenue.q5_quickbooks_pl 46%→7.7%)
```

```
Surface:      Harness vs pipeline manifest run_id for provenance/E2E linkage
Shared by:    EvalHarness baseline/ablation run_id ↔ open_agent_run pipeline run_id ↔ record_e2e_linkage CLI ↔ retrieval_provenance.run_id
Failure mode: Querying provenance or e2e_* fields with harness baseline run_id instead of pipeline agent_run_id returns empty/wrong rows
Confirmed:    yes — M-RE2 T9 + M-RE3 T6 runbook; record_e2e_linkage targets pipeline run_id from fta.main()
```

```
Surface:      _wait_for_index_sync ↔ ensure_coverage.ingest_missing (M-PHV1 Surface 1)
Shared by:    ingestion_parser._wait_for_index_sync ↔ ensure_coverage.py live `ip._wait_for_index_sync` import alias (no production-code fork)
Failure mode: Cell 7 full rebuild or Cell 8d incremental ingest proceeds on unconfirmed/stale vector index — silent wrong-data retrieval in Phase 3 agents (pre-M-PHV1: terminal-state path printed warning and returned; outer except printed warning and returned)
Confirmed:    yes — M-PHV1 T1+T2: both call paths now fail-closed — raise `IndexSyncError` on terminal `FAILED`/`CANCELED`, `elapsed >= max_wait_seconds` (default 1800), and outer sync errors; `tests/test_ingestion_parser_sync.py` proves inheritance through `main()` and `ingest_missing()` with zero `ensure_coverage.py` production changes; notebook Cells 7/8 markdown + `databricks/CLAUDE.md` M-PHV1 exit-gate runbook document halt-on-failure; `IndexSyncOutcome` enum explicitly not implemented (see `.dev/decision-logs/m-phv1-t1-index-sync-error.md`)
```

```
Surface:      Workflow YAML python_file paths ↔ jobs/scripts filenames (M-PHV3 H-1 hygiene)
Shared by:    databricks/workflows/uc13_ingestion_pipeline.yml `python_script_task.python_file` ↔ databricks/jobs/scripts/*.py on-disk names ↔ databricks/workflows/README.md task references
Failure mode: Databricks job task fails with file-not-found if numbered prefixes (`00_setup_vector_search.py`) drift from renamed scripts (`setup_vector_search.py`); workflow YAML is non-live but must stay internally consistent per charter Design Flaw H-1
Confirmed:    yes — M-PHV3 T7 aligned five ingestion task paths to bare script names; grep falsifier for `0[0-9]_` prefixes documented in exit-gate-checklist (no pytest surface)
```

```
Surface:      chunks ↔ doc_relevance join integrity (R-08)
Shared by:    retrieval._hydrate_chunks_sql ↔ eval/retrieval/gold/bootstrap.py hydrate ↔ tests/test_join_integrity.py ↔ eval/retrieval/README.md § join integrity
Failure mode: Orphan chunks (filename mismatch) silently excluded from retrieval and gold bootstrap without operator awareness
Confirmed:    yes — M-PHV4 T4; structural pytest + README operator LEFT JOIN orphan-count SQL; cluster orphan parse not automated in CI
```

```
Surface:      Module-level _CATALOG shadow constant ↔ get_param catalog resolution (M-PHV3 item 21a)
Shared by:    business_model_agent.py, financial_trends_agent.py, kpi_agent.py, customer_quality_agent.py, quality_of_earnings_agent.py `run(catalog)` ↔ `self._catalog` SQL reads ↔ `tests/test_catalog_convention.py` rule 3
Failure mode: Agent reads `company_profile` or addbacks from wrong catalog when widget says `uc13_ale` but module constant hardcodes `uc13`; post-T4 removal means `catalog` kwarg is the sole authority inside `run()`
Confirmed:    yes — T4 removed `_CATALOG`; T5 static scan enforces absence; item 23 cluster smoke is operator proof that BMA `self._catalog` reads resolve against widget catalog
```

```
Surface:      RE2_STORE_BACKEND + RE2_CATALOG env mirror
Shared by:    eval/retrieval/provenance.py::resolve_store ↔ agents/shared/run_context.py::open_agent_run(spark=) ↔ pipeline._sync_env ↔ e2e runner env setup
Failure mode: `RE2_STORE_BACKEND=delta` without Spark raises ProvenanceEmitError; worker threads silently fall back to SqliteEvalStore if `spark=` omitted on open_agent_run (FTA cascade failure)
Confirmed:    yes — sqlite_removal.md Phase 3; tests/test_run_context.py + test_pipeline_agent_run_context.py AST guard requiring spark= or store=
```

```
Surface:      agents.orchestrator → agents.exec_summary package rename (T1 merge)
Shared by:    exec_summary/* modules ↔ test_pipeline.ipynb Cells 11d/12c/19–22 ↔ tests/test_notebook_symbol_references.py ↔ build_exec_summary imports
Failure mode: Stale `agents.orchestrator` imports break notebook cells and pipeline bridge; legacy orchestrator/ folder on disk still has stale self-imports (deprecated)
Confirmed:    yes — T1 merge; zero `agents.orchestrator` in active notebook paths per test_notebook_symbol_references.py
```

```
Surface:      Dual orchestration composition order (DAG then exec_summary)
Shared by:    run_full_pipeline.py ↔ run_vdr_pipeline.py ↔ pipeline_entry.build_exec_summary docstring
Failure mode: exec_summary ingest reads empty/missing agent rows if called before run_pipeline completes
Confirmed:    yes — T9 bridge; run_full_pipeline calls run_pipeline then build_exec_summary sequentially
```

```
Surface:      GOLDEN_CHECKLIST_COVERAGE ↔ eval/<AGENT>/golden_checklist_elder_care.md row count
Shared by:    In-module constants (BMA N=7, CQA N=6, KPI N=3, QoE N=6, Profiler N=7) ↔ tests/test_golden_checklist_elder_care.py CHECKLIST_CASES hub
Failure mode: Promotion gate denominator mismatch; structural test failure on row-count drift
Confirmed:    yes — M1-T1; M4 scorecards recorded per-agent N/M in .dev/scorecards/INDEX.md
```

```
Surface:      analysis.* flags column JSON string vs dict
Shared by:    All workstream agents (flags serialized to Delta) ↔ generate_business_model_assessment and orchestrator ingest readers
Failure mode: `'str' object has no attribute 'get'` when assessment code assumes dict without json.loads guard (BMA R-3 post-merge fix)
Confirmed:    yes — post_merge_regressions.md R-3; json.loads guard added in business_model_agent.py
```

```
Surface:      extraction_endpoint token caps (Haiku 8192 vs Sonnet 16K)
Shared by:    Notebook Cell 1 widget default (Haiku) ↔ business_model_agent.main() Sonnet override ↔ BusinessModelAgent.run() max_tokens=16_000
Failure mode: Truncated JSON drops tail schema fields (sales_motion, key_dependencies) — BMA checklist regression (R-1)
Confirmed:    yes — post_merge_regressions.md R-1; live-verified override + Delta row population 2026-07-28
```

```
Surface:      intent_registry.yaml intent count (+8 CQA/KPI post-merge) ↔ gold_labels/elder_care.yaml
Shared by:    intent_registry.yaml (57 intents) ↔ GoldLabelBootstrap ↔ harness registry_hash ↔ G6 gold-label bootstrap handoff
Failure mode: RegistryHashMismatchError on baseline compare; gold bootstrap incomplete for new intents (G6 deferred — elder_care.yaml reverted)
Confirmed:    yes — hector merge T5–T7; GOLD_LABEL_BOOTSTRAP_HANDOFF.md open work
```

```
Surface:      Profiler not in DAG AGENT_REGISTRY
Shared by:    PipelineOrchestrator AGENT_REGISTRY (9 agents, no profiler) ↔ classification.company_profile table ↔ Profiler golden checklist scorecard
Failure mode: Stale company_profile row when only DAG e2e run; Profiler checklist scored against old created_at
Confirmed:    yes — post_merge_regressions.md; profiler runs via separate company_profiler.py job only
```

```
Surface:      doc_id join key migration (chunks/doc_relevance/doc_status) — M0 ingestion refactor
Shared by:    doc_id.make_doc_id() ↔ retrieval.py _hydrate_chunks_sql JOIN ↔ document_classifier._backfill_missing_doc_ids ↔ status_store.py doc_status
Failure mode: NULL doc_id on either side of the JOIN silently drops chunks from retrieval and gold bootstrap (pre-M0 join key was file_name+company_name); doc_id_hash_catalog mismatch produces a differently-hashed, orphaned doc_id if catalog name changes between classification and parsing
Confirmed:    yes — 2026-08-06 M0-M4 rollout; company-analysis-diff-pre-vs-post-refactor.md documents Elder Care 44.5%→98.3%, SPG 88.7%→100% completeness after this migration
```

```
Surface:      Whole-company rebuild retired — per-doc resumable state (doc_status, sync_state) replaces DELETE+APPEND
Shared by:    ingestion_parser.main() ↔ parse_manifest.ParseManifest ↔ doc_worker.DocWorker ↔ status_store.py ↔ sync_state.py
Failure mode: Operator running old mental model (full rebuild) may expect DELETE+APPEND semantics; force/coverage_per_workstream/skip_sync/sync_only knobs must be understood before re-running a partial ingest
Confirmed:    yes — M0-M4 program; workflow YAML wires force/coverage_per_workstream/skip_sync/sync_only as job params
```

```
Surface:      Rainmaker uc13_preview sandbox catalog isolation
Shared by:    run_vdr_rainmaker.py PREVIEW_CATALOG constant ↔ run_ingestion_pipeline() scoped call ↔ run_pipeline(run_orchestrator=False) ↔ production uc13 catalog convention
Failure mode: If PREVIEW_CATALOG hardcoding is ever removed or the widget/env override bypasses it, CIM-scoped POC ingest could write into production uc13 tables
Confirmed:    yes — run_vdr_rainmaker.py hardcodes PREVIEW_CATALOG = "uc13_preview"; deliberate sandbox per exploration finding
```

```
Surface:      rainmaker_view dict shape ↔ rainmaker_opportunity_summary.html.j2 template contract
Shared by:    rainmaker_view._financial_table() (`cells` key, not `values`) ↔ rainmaker_narrative._financials_summary() (_FINANCIAL_TABLE_ROW_SPECS metric names) ↔ template `{% for val in row.cells %}` / narrative JSON keys (one_liner, investment_thesis.value_drivers, commercial_revenue_quality items)
Failure mode: `row.values` in Jinja would silently resolve to the dict .values() method and render empty columns; narrative key rename breaks template branch silently (fail-open produces blank sections, not an error)
Confirmed:    yes — exploration confirmed `cells` naming convention and exact key list; template does not reference rainmaker.risks/financial_availability/confidence_rows (dead fields, not wired)
```

```
Surface:      eval.s2_scores writer vocabulary ↔ trust_statement content-correctness tier derivation
Shared by:    eval/content/s2_writer.py WRITERS vocabulary (deterministic_verifier | judge_harness | human_spot_check) ↔ eval/retrieval/trust_statement.py derive_content_rows ↔ verification rung model (deterministic → judge → human)
Failure mode: A new writer value added to S2Writer without updating trust_statement's rung mapping produces an unattributed or misclassified trust row
Confirmed:    yes — trust_statement.py imports S2Writer.WRITERS / S2ScoreRow directly (not a duplicated string list)
```

```
Surface:      eval/program/registry.yaml is a work-item ledger, NOT a company registry (naming collision risk)
Shared by:    eval/program/registry.yaml (decisions/waivers/debt) ↔ eval/retrieval/intent_registry.yaml (57 retrieval intents) — distinct artifacts, same "registry" name
Failure mode: Operator or new contributor edits the wrong "registry.yaml" expecting intent/gold-label semantics, or a script defaults to the wrong path
Confirmed:    yes — onboarding_runbook.md explicitly disambiguates the two; test_onboarding_runbook.py asserts CLI paths reference the correct one
```

```
Surface:      eval_debt.yaml high-water-mark ratchet
Shared by:    eval/program/eval_debt/eval_debt.yaml open_debt_high_water_mark ↔ eval_debt.assert_ledger_ratchet ↔ CI/onboarding gate
Failure mode: A new open debt pushes the open count above HWM without a corresponding HWM bump — ratchet must be raised deliberately, not silently, or the gate blocks
Confirmed:    yes — test_eval_debt.py asserts committed ledger (5 open / 18 total, HWM 14) passes ratchet; HWM is a manual, reviewed field
```

```
Surface:      Company slug canon (companies.py) as cross-package join key
Shared by:    eval/retrieval/companies.canonical_company_slug ↔ gold_labels/{slug}.yaml filenames ↔ eval/program/onboarding_queue.yaml `slug` field ↔ eval/content/* company params ↔ trust_statement company rows
Failure mode: A company added via one path (e.g. manual gold bootstrap) without going through canonical_company_slug produces a differently-folded slug, splitting one company's evidence across two identities
Confirmed:    yes — companies.py is the widest import hub in eval/retrieval per exploration; require_folded_company_slug() rejects unfolded display names at call sites that must not silently accept them
```
