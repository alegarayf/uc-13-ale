Section:      integration-seams
Version:      1.4.0
Last updated: 2026-08-20

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
Protocol:      databricks-sdk vector_search_indexes.query_index (+ mlflow.deployments for BGE embed)
Auth:          workspace token (runtime)
Data sent:     Embedding queries (BGE endpoint); optional filters_json={"company_name": "..."} pushdown (T4)
Data received: Chunk hits from uc13.ingestion.embeddings_index with similarity scores in trailing column
Error modes:   Index missing, endpoint down, filter pushdown rejected → keyword fallback in retrieval.py; empty VS hits when index lacks company_name column
Retry policy:  filters_json try/except → unfiltered query; full VS failure → Spark LIKE keyword fallback
Owner module:  databricks/agents/shared/retrieval.py
```

```
Seam:          FTA eval harness → Delta snapshot table
Direction:     outbound (write)
Protocol:      Spark SQL DELETE + INSERT
Auth:          cluster / job identity
Data sent:     FTA agent JSON output keyed by (company_name, retrieval_mode)
Data received: none
Error modes:   Overwritten if snapshot cell skipped before arm switch; main table keeps only latest run per company
Retry policy:  backfill_fta_snapshot_from_main() helper in test_pipeline.ipynb
Owner module:  databricks/jobs/notebooks/test_pipeline.ipynb
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

```
Seam:          Phase 3 workstream agents → UC13 orchestrator ingest
Direction:     inbound (read)
Protocol:      Spark SQL latest-row SELECT + optional Volume YAML report paths
Auth:          cluster / job identity
Data sent:     none (read-only)
Data received: Per-agent Delta snapshots (business_model, financial_trends, customer_quality, kpi, legal, quality_of_earnings)
Error modes:   Missing table/row omitted without raise; stale flags shape; KPI/legal report_path Volume fallback
Retry policy:  none — BundleBuilder HALTs on validate_bundle failure; synthesis LLM parse failures fail-open (print only, deterministic narrative retained)
Owner module:  databricks/agents/exec_summary/ingest.py, bundle_builder.py
```

```
Seam:          BundleBuilder → Databricks model serving (stage-6 executive synthesis — Rainmaker Rev3)
Direction:     outbound
Protocol:      mlflow.deployments HTTP via WorkstreamAgent._call_llm
Auth:          Databricks workspace credentials
Data sent:     Assembled bundle context JSON; Rev3 prompt for preliminary_digest, thesis_bullets, key_watchouts, business snapshot paragraph
Data received: JSON executive narrative overlay (allowlisted keys only)
Error modes:   Invalid JSON, markdown fences, LLM timeout — fail-open; structural fields restored from snapshot
Retry policy:  none — fail-open on synthesis errors
Owner module:  databricks/agents/exec_summary/bundle_builder.py (synthesize_executive_narrative)
```

```
Seam:          Orchestrator → UC Volume reports directory
Direction:     outbound (write)
Protocol:      FUSE filesystem (/Volumes/{catalog}/analysis/reports/{company_safe}/)
Auth:          cluster / job identity
Data sent:     orchestrator_bundle.yaml, full_report.md, tldr_one_pager.md, optional .docx
Data received: Per-agent YAML report reads during ingest_snapshots
Error modes:   FUSE write failures (md_to_word uses /tmp workaround for DOCX)
Retry policy:  none
Owner module:  databricks/agents/exec_summary/bundle_builder.py, renderers.py, paths.py
```

```
Seam:          Pipeline DAG → Delta analysis tables (data bus)
Direction:     bidirectional
Protocol:      Spark SQL per-agent writes; orchestrator reads latest rows
Auth:          cluster / job identity
Data sent:     Structured agent outputs to {catalog}.analysis.*
Data received: Downstream agents read upstream tables (FTA→QoE/forecast, CQA→legal soft dep)
Error modes:   HARD dep failure → agent SKIPPED; SOFT dep failure → degraded mode via _load_* fallbacks
Retry policy:  per-agent retries inside PipelineOrchestrator (configurable max_attempts)
Owner module:  databricks/agents/orchestration/pipeline.py
```

```
Seam:          run_full_pipeline / VDR job → DAG + exec_summary
Direction:     internal orchestration
Protocol:      Python function calls (run_pipeline → build_exec_summary)
Auth:          cluster / job identity
Data sent:     company_name, catalog, spark, llm_endpoint
Data received: Combined manifest + exec_summary path dict
Error modes:   DAG failure may skip exec_summary; VDR marks companies_vdr_history error
Retry policy:  Databricks Workflow job-level retry
Owner module:  databricks/jobs/scripts/run_full_pipeline.py, run_vdr_pipeline.py
```

```
Seam:          VDR UI → companies_vdr_history → VDR volume
Direction:     inbound trigger + outbound artifact copy
Protocol:      Spark SQL status updates + shutil copy to /Volumes/rallyday_partners_llc/default/vdr/{company_snake}/{timestamp}/
Auth:          cluster job identity (last_updated_by: vdr-backend-ai)
Data sent:     full_report.docx, executive_summary.docx (from build_exec_summary tldr_docx)
Data received: VDR submission row (processing_status, source_data_location)
Error modes:   Pipeline failure → status=error; partial copy if exec_summary fails after DAG success
Retry policy:  none documented
Owner module:  databricks/jobs/scripts/run_vdr_pipeline.py, databricks/workflows/vdr_pipeline.yml
```

```
Seam:          Pipeline agents → eval ops store (provenance + manifest)
Direction:     outbound (write)
Protocol:      Delta MERGE/INSERT to {catalog}.ops.retrieval_harness_runs + retrieval_provenance
Auth:          cluster identity via Spark session
Data sent:     HarnessRun manifest pins, per-retrieval ProvenanceRecord rows
Data received: none
Error modes:   sqlite fallback on cluster (fixed: RE2_STORE_BACKEND=delta + spark=); Delta concurrent write
Retry policy:  retry_on_delta_conflict on provenance writes
Owner module:  agents/shared/run_context.py, eval/retrieval/provenance.py, eval/retrieval/store.py
```

```
Seam:          Operator → promotion gate / golden checklists
Direction:     inbound (manual scoring) + outbound (manifest update)
Protocol:      evaluate_promotion Python API or record_e2e_linkage CLI
Auth:          operator notebook session
Data sent:     candidate_score, candidate_total, e2e_snapshot_table, optional waiver_id
Data received: PromotionResult; updated HarnessRun e2e_* fields on promote/bootstrap
Error modes:   promotion_blocked on regression; InvalidWaiverIdError on bad waiver
Retry policy:  none — operator re-runs agent and re-scores
Owner module:  eval/retrieval/promotion_gate.py, eval/<AGENT>/golden_checklist_elder_care.md
```

```
Seam:          VDR UI (Rainmaker POC variant) → SharePoint CIM detection → uc13_preview sandbox
Direction:     inbound trigger + outbound artifact copy
Protocol:      Same companies_vdr_history trigger row as production VDR + Microsoft Graph download; run_vdr_rainmaker_job.py notebook widgets
Auth:          cluster job identity; SharePoint MSAL client credentials (shared with main ingestion)
Data sent:     CIM-scoped file_whitelist to download_upload/ingestion; only a Phase 3-4 subset (no orchestrator memo) runs
Data received: companies_vdr_history status update; rainmaker_opportunity_summary.html + executive_summary.pdf copied to VDR volume
Error modes:   No CIM found -> no-op skip with completion_status=success + explanatory error_message (not a fallback to full pipeline)
Retry policy:  none documented — manual/POC trigger only, no UI wiring yet
Owner module:  databricks/jobs/scripts/run_vdr_rainmaker.py, databricks/workflows/vdr_rainmaker_poc.yml
```

```
Seam:          eval/content verification (calibration + spot-check + legal verifier) -> eval.s2_scores
Direction:     outbound (write) + inbound (read for trust rollup)
Protocol:      Delta append via S2Writer (SQL executor abstraction, not direct Spark writes)
Auth:          cluster / operator warehouse credentials
Data sent:     Per-claim verdict rows (claims-then-marker sequencing); rung: deterministic_verifier | judge_harness | human_spot_check
Data received: eval/retrieval/trust_statement.py reads s2_scores for content_correctness tier derivation
Error modes:   S-61 fail-closed if cited_chunk_id present but unresolved; SpotCheckIngestionError on unknown claim_id/invalid verdict vocab
Retry policy:  none — ingestion is all-or-nothing per run_id (no partial writes)
Owner module:  eval/content/s2_writer.py, spot_check.py, legal_register_verifier.py, eval/retrieval/trust_statement.py
```
