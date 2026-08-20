Section:      data-contract-registry
Version:      1.2.0
Last updated: 2026-08-20

> **Cross-reference:** Retrieval-specific contracts live in [`eval/architecture/rallyday/data-contract-registry.md`](../../eval/architecture/rallyday/data-contract-registry.md). This folder is the charter-named program-wide standing reference; it does not supersede the rallyday tree.

```
Contract:       eval/program governance artifacts (registry.yaml, product_backlog.yaml, eval_debt.yaml)
Module:         eval/program/registry.yaml, product_backlog.yaml, eval_debt/eval_debt.yaml
Serialization:  YAML, schema_version: 1
Version:        1
Purpose:        Cross-company program governance ledgers — work-item decisions/waivers (registry), product signals (product_backlog), tracked-gap ledger with high-water-mark ratchet (eval_debt)
Fields:
  - registry items[]: id, title, source_refs, source_id, disposition, stage, status, trigger, rationale, tshirt, evidence_refs, rung_assignments, assessment_metrics
  - registry tshirt vocabulary (D3): xs | s | m | l | xl | unsizable — enforced on actionable (pending/in_progress) rows; unsizable requires rationale naming missing scope/falsifier
  - product_backlog items[]: id, company, surface, kind, severity, summary, evidence_refs, fix_lane, closes_when, registry_ref?, closed_at? (optional), closed_evidence_refs? (optional) — no status field
  - eval_debt: open_debt_high_water_mark (14), debts[] {id: "{company}:{surface|global}:{kind}", opened_at, evidence_refs, closes_when, closed_at?, closed_evidence_refs?} — post-M2/W0: 20 total / 2 open
Validators:     test_eval_program_registry.py (TSHIRT_VALUES, FROZEN_ACTIONABLE_TSHIRT_ROW_COUNT=54, GAP-109 row), test_product_backlog_schema.py (validate_product_backlog_closure_shape), test_eval_debt.py (ratchet + SPG 44038 closure)
Consumers:      eval_debt.py, trust_statement.py, eval/eval_program_playbook.md §3.1
Last changed:   2026-08-20 (eval-signal-foldback M2/W0 ledger truth-up)
```

```
Contract:       RouteResult
Module:         databricks/agents/shared/retrieval.py
Serialization:  dataclass
Version:        unversioned — tracked by git blame
Purpose:        Standard envelope returned by semantic_search and consumed by all retrieval callers
Fields:
  - chunks: list[dict] — chunk_id, file_name, chunk_text, section_header, page_start, source_type, workstream, priority_tier
  - mode: str — retrieval path used (vector_search, keyword_fallback, etc.)
  - scores: list[float] — relevance scores aligned with chunks
Validators:     none
Consumers:      workstream agents, FTA subagents, eval/retrieval harness
Last changed:   2026-08-03
```

```
Contract:       Flag
Module:         databricks/agents/shared/agent_base.py
Serialization:  dataclass → JSON string in Delta `flags` column
Version:        unversioned — tracked by git blame
Purpose:        Structured diligence flag emitted by agents and rendered in memos
Fields:
  - metric: str — metric or topic name
  - value: str | number — observed value
  - threshold: str | number — comparison threshold
  - severity: str — red | yellow | green (or project-specific)
  - note: str — human-readable explanation
  - source_doc: str — originating document name
  - confidence: str — high | medium | low
Validators:     none (LLM-produced)
Consumers:      orchestrator, cross_analysis, exec_summary ingest, to_result_card
Last changed:   2026-08-03
```

```
Contract:       Citation
Module:         databricks/agents/shared/agent_base.py
Serialization:  dataclass → JSON string in Delta `citations` column
Version:        unversioned — tracked by git blame
Purpose:        Source attribution for agent claims
Fields:
  - claim: str — asserted fact
  - document: str — source file name
  - location: str — page/section/cell reference
  - confidence: str — high | medium | low
  - raw_text: str — supporting excerpt
Validators:     none
Consumers:      orchestrator, exec_summary, assessment generators
Last changed:   2026-08-03
```

```
Contract:       to_result_card
Module:         databricks/agents/orchestration/pipeline.py
Serialization:  dict (in-memory interchange; not persisted as standalone table)
Version:        unversioned — tracked by git blame
Purpose:        Size-bounded agent summary for Cross-Analysis and Orchestrator (no raw chunks)
Fields:
  - workstream: str — agent registry key
  - present: bool — whether agent row exists
  - rating: str — agent quality rating when present
  - headline: str — short summary
  - key_metrics: dict — selected numeric fields
  - flags: list — subset of Flag objects
  - flag_count: int
  - data_room_gaps: list[str]
  - citations_ref: str — reference hint, not full citations
  - created_at: str — ISO timestamp
Validators:     built from known Delta columns only; never includes reasoning_trace
Consumers:      cross_analysis_agent, orchestrator_agent
Last changed:   2026-08-03
```

```
Contract:       agent_run_manifest
Module:         databricks/agents/orchestration/pipeline.py → diligence_report.agent_run_manifest_json
Serialization:  JSON string in Delta
Version:        unversioned — tracked by git blame
Purpose:        Per-agent run status for memo appendix and failure diagnostics
Fields:
  - per-agent entries: status (SUCCESS | FAILED | SKIPPED), attempts, error, degraded_from
Validators:     DAG hard-dep skip rules enforced in PipelineOrchestrator
Consumers:      orchestrator_agent, operator runbooks
Last changed:   2026-08-03
```

```
Contract:       ingestion_chunk_row
Module:         databricks/jobs/scripts/ingestion_parser.py
Serialization:  Spark StructType → Delta `{catalog}.ingestion.chunks`
Version:        unversioned — tracked by git blame
Purpose:        Parsed document chunk stored for retrieval hydration
Fields:
  - chunk_id: str — unique chunk identifier
  - company_name: str — partition key
  - file_name: str — source document (display/filter; legacy join key pre-M3)
  - doc_id: str — canonical volume-path hash (joins to doc_relevance.doc_id post-M3)
  - chunk_text: str — extracted text or markdown table
  - section_header: str — document section
  - page_start: int — PDF page
  - source_type: str — text | table | vision
  - workstream: array[str] — inherited tags
  - priority_tier: int — 1 (highest) through 3
Validators:     source_type enum enforced at parse time
Consumers:      retrieval.py, ensure_coverage.py
Last changed:   2026-08-04
```

```
Contract:       doc_relevance_row
Module:         databricks/jobs/scripts/document_classifier.py
Serialization:  Spark StructType → Delta `{catalog}.classification.doc_relevance`
Version:        unversioned — tracked by git blame
Purpose:        LLM classification output per document; retrieval hydration join target
Fields:
  - company_name: str — partition key
  - document_id: str — per-classify-run uuid (not reused as join key)
  - filename: str — source file basename
  - folder_path: str — relative volume folder (`.` for root-level files)
  - doc_id: str — nullable STRING; canonical join key via `make_doc_id(catalog, schema, company_name, folder_path, filename)` (M3)
  - workstream: array[str] — inherited tags
  - priority_tier: int — 1 (highest) through 3
  - priority_reason, should_parse, extraction_confidence, mod_date, format: classification metadata
Validators:     `doc_id` stamped by `_build_classification_record` on write; NULL rows backfilled by `_backfill_missing_doc_ids` (MERGE on company_name + filename + coalesce(folder_path,'')). Both functions take an optional `hash_catalog` param (defaults to `catalog`) — required whenever the table's catalog differs from the catalog `chunks.doc_id` was hashed under at ingestion time (M3/T5; guards the live catalog-mismatch incident, see known-coupling-surfaces.md "Catalog name split").
Consumers:      retrieval.py (`_hydrate_chunks_sql`, `_keyword_fallback_sql`), ensure_coverage.py (filename-only legacy path), eval harness
Last changed:   2026-08-05 (M3/T5 amendment)
```

```
Contract:       embedding_row
Module:         databricks/jobs/scripts/ingestion_parser.py
Serialization:  Spark StructType → Delta `{catalog}.ingestion.embeddings`
Version:        unversioned — tracked by git blame
Purpose:        BGE embedding vector indexed by Vector Search
Fields:
  - chunk_id: str — FK to chunks
  - embedding: array[float] — bge-large-en vector
  - workstream: array[str]
  - priority_tier: int
  - source_type: str
Validators:     index sync required before Phase 3 (IndexSyncError on failure)
Consumers:      retrieval.py, Vector Search index
Last changed:   2026-08-03
```

```
Contract:       orchestrator_bundle
Module:         databricks/agents/exec_summary/orchestrator_bundle.schema.yaml
Serialization:  JSON Schema (validated by exec_summary/validate.py)
Version:        unversioned — tracked by git blame
Purpose:        Normalized executive-summary input assembled from agent Delta rows
Fields:
  - meta: object — company, run metadata
  - headline_metrics: object — key KPIs
  - executive, company_framing, financials, revenue_quality: objects
  - kpi_dashboard: array
  - qoe, legal: objects
  - risks: array
  - diligence_questions, data_room_gaps: arrays
  - confidence_by_area: object
  - provenance: object
Validators:     jsonschema validation in validate.py
Consumers:      BundleBuilder, TL;DR renderers, VDR pipeline
Last changed:   2026-08-03
```

```
Contract:       Rule (Garden rules API)
Module:         backend-api/src/types/rule.ts (mirrored in frontend/src/types/rule.ts)
Serialization:  JSON over REST; Delta row in `{catalog}.{schema}.rules`
Version:        unversioned — tracked by git blame
Purpose:        CRUD entity for Garden rules (form or AI-generated)
Fields:
  - id: str
  - name, description: str
  - status: active | inactive
  - rule_source: form | ai
  - nl_prompt, nl_summary: str (AI fields)
  - rule_definition: str — JSON-serialized full rule config
  - python_source, python_entrypoint: str — denormalized from rule_definition
  - created_at, updated_at, last_updated_by: audit fields
Validators:     backend-api validation middleware
Consumers:      frontend Garden rules UI, backend-api repositories
Last changed:   2026-08-03
```

```
Contract:       Company (My Garden opportunity)
Module:         backend-api/src/types/company.ts
Serialization:  JSON over REST; sourced from salesforce_silver.opportunity_silver
Version:        unversioned — tracked by git blame
Purpose:        Opportunity card data for My Garden UI
Fields:
  - id, project_name, account_name: str
  - financial fields: revenue, ebitda, growth rates (~27 fields, snake_case API mapping from PascalCase DB)
Validators:     owner-email scope filter in CompaniesService
Consumers:      frontend My Garden page
Last changed:   2026-08-03
```

```
Contract:       Genie ruleConfig
Module:         backend-ai/app/services/response_parser.py
Serialization:  Pydantic-normalized dict
Version:        unversioned — tracked by git blame
Purpose:        Structured rule output from Databricks Genie NL interpretation
Fields:
  - name, description, intent: str
  - conditions, actions: list[object]
  - python_function: { source, entrypoint }
Validators:     normalized against opportunity_silver_fields canonical schema
Consumers:      frontend buildAiRuleCreateInput, backend-api rule persistence
Last changed:   2026-08-03
```

```
Contract:       analysis_table_row (per workstream)
Module:         databricks/agents/workstreams/*.py
Serialization:  Spark StructType → Delta `{catalog}.analysis.{workstream_table}`
Version:        unversioned — _EXPECTED_COLS guard drops table on schema drift
Purpose:        Structured diligence output per workstream
Fields:
  - company_name: str — partition key
  - executive_summary: str
  - flags, citations, reasoning_trace: JSON strings
  - data_room_gaps: array[str]
  - *_json columns: workstream-specific structured payloads (e.g. revenue_trend_json, contract_register_json)
  - created_at: timestamp
Validators:     _EXPECTED_COLS schema guard in each agent main()
Consumers:      pipeline DAG (soft/hard deps), orchestrator, exec_summary, eval harness
Last changed:   2026-08-03
```

**Note:** `analysis.legal` is the write target; `analysis.legal_contracts` is a compatibility VIEW consumed by the pipeline registry key `legal_contracts`.

```
Contract:       calibration_sample (§8.7)
Module:         .dev/eval-program/calibration_sample_{surface}.yaml
Serialization:  YAML (schema_version: 1)
Version:        1 — pinned at spec §8.7 / M2 C3
Purpose:        Operator-labelled judge-capability calibration claims per §16 trust surface
Fields:
  - surface: str — fta_numeric | legal_register | exec_summary (must match filename suffix)
  - assessed_by: operator; assessed_at: ISO date
  - claims[]: claim_id, claim_text, source_ref (diagnostics only), verdict
  - fta_numeric only: expected_value {magnitude (exact decimal), unit}, expected_span {chunk_id, locator?}
Validators:     eval/retrieval/tests/test_calibration_samples.py (item 23b)
Consumers:      eval/content/calibration.py (item 26a), G5 gate presence half
Last changed:   2026-08-12
```
