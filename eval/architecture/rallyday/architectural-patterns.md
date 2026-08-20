Section:      architectural-patterns
Version:      1.6.0
Last updated: 2026-08-20

```
Pattern:      FTA retrieval adapter boundary
Description:  All Financial Trends sub-agent retrieval must go through context_utils.semantic_search_with_fallback and unpack RouteResult.chunks before build_focused_context. Direct semantic_search or route_chunks calls from FTA sub-agents are forbidden.
Falsifier:    rg 'semantic_search\(' databricks/agents/subagents/workstream/financial/*_sub_agent.py — should only appear inside context_utils import path, not in _retrieve bodies
```

```
Pattern:      Notebook widget → os.environ mirror
Description:  Every dbutils.widgets value used by imported script modules must be copied to os.environ in test_pipeline.ipynb Cell 1 (or Cell 1a for mid-session overrides). Scripts read via get_param(), not dbutils.widgets.get() directly.
Falsifier:    Script get_param() returns empty when run from notebook after widget set but before os.environ sync
```

```
Pattern:      VS index columns_to_sync contract tests
Description:  setup_vector_search.py columns_to_sync must match ingestion_parser embeddings DDL and 00_setup_vector_search.ipynb; tests/test_setup_vector_search.py asserts parity.
Falsifier:    pytest tests/test_setup_vector_search.py fails on columns_to_sync drift
```

```
Pattern:      Non-FTA agents consume raw semantic_search list
Description:  RouteResult structured return is confined to the FTA context_utils boundary. BMA, CQA, KPI, QoE, and company_profiler call semantic_search directly and expect list[Row]. Legal also calls semantic_search directly (via `_semantic_search_with_fallback`) but may import `build_focused_context` from context_utils via importlib — not `semantic_search_with_fallback`.
Falsifier:    rg 'semantic_search_with_fallback' databricks/agents/workstreams/legal_contracts_agent.py — must not appear; rg 'RouteResult' databricks/agents/workstreams/ — should not appear outside financial_trends_agent import chain
```

```
Pattern:      Legal domain pass loop
Description:  LegalContractsAgent.run() must iterate `_DOMAIN_PASSES` (five pass IDs), emitting `domain_retrieve_{pass_id}` and `domain_extract_{pass_id}` trace steps per pass; monolithic single-LLM extraction path is retired.
Falsifier:    rg '_USER_PROMPT_TEMPLATE|_tool_retrieve_' databricks/agents/workstreams/legal_contracts_agent.py — should not match; test_legal_contracts_agent.py asserts _DOMAIN_PASSES count and run signature
```

```
Pattern:      Legal extraction_endpoint + Sonnet override
Description:  `run()` accepts `extraction_endpoint` (not `llm_endpoint`); `main()` forces Sonnet when widget value contains haiku or llama (D6a) before calling run().
Falsifier:    test_main_passes_extraction_endpoint_to_run_not_llm_endpoint and test_main_sonnet_override_for_haiku_llama in tests/test_legal_contracts_agent.py
```

```
Pattern:      M2 deterministic BundleBuilder production path
Description:  Production executive summary synthesis must use `agents.exec_summary.BundleBuilder.build()` with demo_mode: false (package renamed from `agents.orchestrator` in T1 merge). populate_bundle is M1 demo fallback only. Notebook Cell 19 is the production entry; render cell must not call populate_bundle when ORCHESTRATOR_USE_BUILDER=1 or on-Volume bundle has demo_mode: false.
Falsifier:    tests/test_notebook_symbol_references.py — zero `agents.orchestrator` imports; Cell 19 uses BundleBuilder from exec_summary
```

```
Pattern:      Dual orchestration — DAG then exec_summary
Description:  Hector diligence DAG (`agents.orchestration.pipeline.run_pipeline`) must complete before `build_exec_summary()` — exec_summary ingest reads analysis.* rows and Volume YAML reports produced by DAG agents only.
Falsifier:    run_full_pipeline.py source order: run_pipeline before build_exec_summary; pipeline_entry.py module docstring
```

```
Pattern:      Delta provenance on worker threads (spark= injection)
Description:  Every instrumented agent `main()` and profiler must pass `spark=` to `open_agent_run()` on cluster runs; `RE2_STORE_BACKEND=delta` without Spark must fail closed, never sqlite-fallback.
Falsifier:    tests/test_pipeline_agent_run_context.py AST guard; tests/test_run_context.py worker-thread falsifier
```

```
Pattern:      Stage-6 executive synthesis fail-open
Description:  When llm_endpoint is set, synthesize_executive_narrative overlays allowlisted Rev3 executive keys only (preliminary_digest, thesis_bullets, key_watchouts, business_snapshot_narrative, etc.). Structural fields captured before LLM and restored after. LLM failures do not HALT the build.
Falsifier:    test_orchestrator_bundle_builder synthesis tests; bundle_builder.py structural capture/restore; Rainmaker Rev3 allowlist in _EXECUTIVE_LLM_NARRATIVE_KEYS
```

```
Pattern:      TL;DR render-time compression (lossy projection)
Description:  Canonical bundle in orchestrator_bundle.yaml is never mutated by compression. compress_for_tldr runs at render time only; TLDR_RENDER_MODE=compressed (default) uses tldr_one_pager_compressed.md.j2 with separate tldr= context. full_report.md always renders from full bundle regardless of mode.
Falsifier:    test_tldr_compression.py K4 mode-independence test; compress_for_tldr uses copy.deepcopy on input bundle
```

```
Pattern:      Orchestrator validate-or-HALT + Volume render
Description:  BundleBuilder.build and notebook orchestrator cell must call validate_bundle before persisting bundle or rendering; render sets meta.render_state=rendered; demo_walkthrough is the M1 cluster exit gate (D-M1-5).
Falsifier:    demo_walkthrough.run() returns 1 with [orchestrator] DEMO FAIL when any Volume artifact or bundle gate fails; tests/test_demo_walkthrough.py; BundleBuilder.build raises BundleValidationError before write_bundle_yaml
```

```
Pattern:      Orchestrator DOCX export via md_to_word /tmp workaround
Description:  Notebook DOCX cells call jobs.scripts.md_to_word.convert_md_to_word on company_safe Volume paths; md_to_word copies to /tmp before python-docx write (FUSE workaround).
Falsifier:    demo_walkthrough gate 7 fails when full_report.docx or tldr_one_pager.docx missing after export cell
```

```
Pattern:      Repository factory (Garden API)
Description:  backend-api persistence switches memory vs Databricks via createRulesRepository / createCompaniesRepository factories driven by DATA_STORE env.
Falsifier:    DATA_STORE=databricks with missing DATABRICKS_* env still constructs Databricks repository (health ping fails)
```

```
Pattern:      UC13 ingestion mode separation
Description:  Full rebuild (ingestion_parser.main DELETE+APPEND) vs append-only gap fill (ensure_coverage.ingest_missing) must never be mixed in the same remediation step.
Falsifier:    ensure_coverage called without prior get_coverage_report showing gaps
```

```
Pattern:      Per-doc resumable ingestion (M0 incremental refactor)
Description:  ingestion_parser.main() must never DELETE+APPEND a whole company's chunks/embeddings. Work is enumerated by parse_manifest.ParseManifest.build(), executed one doc at a time by doc_worker.DocWorker, and state tracked per (company_name, doc_id) in status_store.py. VS Delta Sync is gated behind sync_state.py's watermark, not run unconditionally every parse.
Falsifier:    rg 'DELETE FROM.*chunks|DELETE FROM.*embeddings' databricks/jobs/scripts/ingestion_parser.py — should not match on the default path; tests/test_docworker_state_transitions.py
```

```
Pattern:      doc_id as the sole chunks↔doc_relevance join key
Description:  All new code joining chunk rows to classification/coverage rows must use doc_id (from doc_id.make_doc_id), not (file_name, company_name). Classifiers must backfill doc_id via MERGE, not leave it NULL.
Falsifier:    rg 'file_name.*=.*filename|c\.file_name = r\.filename' databricks/agents/shared/retrieval.py — should not match on the production JOIN path; tests/test_measure_join_orphan_rate.py
```

```
Pattern:      Rainmaker POC catalog sandboxing
Description:  run_vdr_rainmaker.py must scope all ingestion and DAG calls to PREVIEW_CATALOG ("uc13_preview"), never the production catalog default. CIM-first scoping (file_whitelist) must be threaded through download_upload/ingestion_parser, not silently widened to the full data room.
Falsifier:    rg 'catalog\s*=\s*"uc13"' databricks/jobs/scripts/run_vdr_rainmaker.py — should not match; PREVIEW_CATALOG constant must be the sole catalog value used
```

```
Pattern:      eval/content writes only through S2Writer (append-only, claims-then-marker)
Description:  Any new content-correctness verifier (deterministic, judge, or human) must write via eval/content/s2_writer.S2Writer, never with a bespoke INSERT. Claim rows are written before the completion marker for a given run_id; no partial/duplicate run_id writes.
Falsifier:    rg 'INSERT INTO.*s2_scores' eval/ — matches should appear only inside s2_writer.py; tests/test_s2_writer.py completion-marker sequencing test
```

```
Pattern:      eval/program governance ledgers are hand-authored except trust_statement.md
Description:  registry.yaml, product_backlog.yaml, eval_debt.yaml, eval_exemptions.yaml, onboarding_queue.yaml, source_manifest.yaml are operator/PR-edited; trust_statement.md is the one generated artifact in eval/program/ and must be regenerated via `python -m eval.retrieval.trust_statement generate`, never hand-edited.
Falsifier:    Manual edit to trust_statement.md diverges from a fresh `generate` run with no other inputs changed
```

Code-derived candidates still requiring user-supplied falsifiers:

- Thin routes → service → repository layering in backend-api `[aspiration — falsifier pending]`
- AI rule two-service split (backend-ai interpret → backend-api persist) `[aspiration — falsifier pending]`
