Section:      data-contract-registry
Version:      1.7.0
Last updated: 2026-08-25

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
  - product_backlog items[]: id, company, surface, kind, severity, summary, evidence_refs, fix_lane, closes_when, registry_ref?, closed_at? (optional), closed_evidence_refs? (optional) — no status field. M4/W4: 21 items; 12 closed (`closed_at` 2026-08-20 ×4 caveat + 2026-08-21 ×8 product); open M4 leftovers `PB-legal_register-extraction-depth-contracts`, `PB-legal_register-retrieval-ip`; new open `PB-exec_summary-008-locator-mismatch`
  - eval_debt: open_debt_high_water_mark (14), debts[] {id: "{company}:{surface|global}:{kind}", opened_at, evidence_refs, closes_when, closed_at?, closed_evidence_refs?} — post-M2/W0: 20 total / 1 open
Validators:     test_eval_program_registry.py (TSHIRT_VALUES, FROZEN_ACTIONABLE_TSHIRT_ROW_COUNT=54, GAP-109 row), test_product_backlog_schema.py (validate_product_backlog_closure_shape, test_product_backlog_closed_row_set), test_eval_debt.py (ratchet + SPG 44038 closure)
Consumers:      eval_debt.py, trust_statement.py, eval/eval_program_playbook.md §3.1
Last changed:   2026-08-25 (eval-signal-foldback M7/W2c T8; live eval_debt.yaml re-read 20 total / 1 open)
Landed (M7/T7): `OI-eval-harness-profiler-re-run-clearsulting-gkf-spg` status=closed (terminal; Clearsulting, GKF, and SPG discharged). Evaluate-promotion row stays closed with SPG `RUN_ID` `445878b36e06407385b9498dcab265c7`.
Landed (M7/T8): Governance-block eval_debt count corrected from the stale "20 total / 2 open" to the live ledger **20 total / 1 open** (open id `elder_care:global:g1_legal_score_regression`, HWM **14**).
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

> **M3/T5:** The D9 `exec_summary` sample is the git-tracked file `eval/content/calibration_samples/calibration_sample_exec_summary.yaml` (T2), not the gitignored `.dev/eval-program/` path above. No `calibration_sample*.yaml` files exist under `.dev/` at T5 execution. `fta_numeric` sample path remains `eval/content/calibration_samples/calibration_sample_fta_numeric.yaml` (frozen adjacent this wave). See the M3 contracts below.

```
Contract:       SampleComposition
Module:         eval/content/agreement.py:SampleComposition
Serialization:  frozen dataclass (in-memory); not a persisted table
Version:        unversioned — tracked by git blame (landed T1 `214d5a76`)
Purpose:        P1–P4 sample-composition summary passed into evaluate_thresholds
Fields:
  - retained_count: int — len(sample["claims"]) including unlabeled rows
  - verdict_counts: dict[str, int] — keys ⊆ CLAIM_VERDICTS {supported, contradicted, unsupported}
  - distinct_expected_chunk_ids: int — distinct non-null (expected_span or {}).chunk_id
Validators:     test_agreement.py::test_compute_sample_composition_round_trip / test_compute_sample_composition_empty_claims; test_calibration_sample_power.py::test_exec_summary_sample_composition_pins
Consumers:      evaluate_thresholds, calibration.py:run_calibration
Last changed:   2026-08-20 (eval-signal-foldback M3/W1 T1)
```

```
Contract:       ThresholdResult / unevaluated_pins channel
Module:         eval/content/agreement.py:ThresholdResult ; eval/content/calibration.py:run_calibration `--out` dict
Serialization:  frozen dataclass → JSON keys on calibration `--out`
Version:        unversioned — tracked by git blame (landed T1 `214d5a76`; live JSON key proven T3/T4)
Purpose:        Replaces the retired evaluate_thresholds 2-tuple. Fail-closed composition pins and C5 figure failures share one result object; unevaluated_pins records pins that were not scored (omitted composition or numeric-inapplicable), never a pin that also appears in failure_reasons.
Fields:
  - passed: bool — False when sample_composition is None; else len(failure_reasons)==0
  - failure_reasons: list[str] — evaluated-and-failed pins prefixed "P1:"–"P4:"; C5 / HALT-29 strings unprefixed
  - unevaluated_pins: list[str] — "P{n}: omitted (sample_composition is None)" or "P{n}: inapplicable (numeric surface)"
Validators:     test_evaluate_thresholds_omitted_composition_fail_closed_verdict / _numeric; test_evaluate_thresholds_numeric_pins_skipped_not_defaulted; test_evaluate_thresholds_channel_disjointness_matrix; T4 post-check on T3 JSON unevaluated_pins==[]
Consumers:      calibration.py --out; T3 signoffs JSON; T4 wave note
Last changed:   2026-08-20 (eval-signal-foldback M3/W1 T1+T3)
```

```
Contract:       calibration_sample_exec_summary (tracked D9 sample)
Module:         eval/content/calibration_samples/calibration_sample_exec_summary.yaml
Serialization:  YAML (schema_version: 1)
Version:        1
Purpose:        Operator-labelled exec_summary calibration sample after T2 maximal honest rebalance
Fields:
  - surface: exec_summary; assessed_by: operator; assessed_at: '2026-08-13'
  - claims[]: claim_id exec.claim.001–028, claim_text, source_ref, verdict, expected_span?: {chunk_id} only (no locator; 027 unlabeled)
  - Post-rebalance composition (re-read at T5 via agreement.py:compute_sample_composition): retained_count=28; verdict_counts={supported: 26, unsupported: 1, contradicted: 1}; distinct_expected_chunk_ids=13
  - P3 met (13 ≥ MIN_DISTINCT_EXPECTED_CHUNK_IDS=8) with zero additions from the dual-source-covered 16-claim set
  - 001/012/020 remain supported (no flips). No-relabel set 003/004/017/019/025/026 stay supported (026 sample supported vs backfill contradicted — drift recorded, not resolved)
Validators:     test_calibration_sample_power.py (composition pins, honest-instrument P2 fail, unlabeled 027, no-relabel); test_exec_summary_spot_check_rubric.py::test_calibration_sample_ids_001_028_match_rubric_verbatim
Consumers:      calibration.py --sample; D9 T3 run; T4 wave note
Last changed:   2026-08-20 (eval-signal-foldback M3/W1 T2)
```

**D9 evidence-of-record (T4 wave note; do not rephrase the T3 figures):** `passed=false`; `failure_reasons=["P2: majority class fraction 0.9286 > 0.6", "P4: verdict_agreement 0.8214 < majority baseline 0.9286 + 0.1"]`; `unevaluated_pins=[]`; `claim_count=28`; `figures.verdict_agreement=0.8214285714285714`. Promotion inadmissible this wave (`exec_summary` stays `human`). W3 waives the runnable checkpoint's P2 component only; P2 enforcement in `evaluate_thresholds` is unwaived (`test_exec_summary_sample_honest_instrument_fails_p2`). Follow-up `m3-exec-summary-discriminative-probe-build`. No write to `eval/program/registry.yaml`.

```
Contract:       gold_labels_elder_care (M4/W4 epoch re-pin)
Module:         eval/retrieval/gold_labels/elder_care.yaml
Serialization:  YAML
Version:        unversioned — tracked by git blame (T7-bis `699e682`)
Purpose:        Elder Care retrieval gold; CIM pins remapped after T6 re-parse; all labels share one ingestion_snapshot
Fields:
  - ingestion_snapshot: uc13_ale:55819:2026-08-20 (57/57 labels; validate_ingestion_snapshot_consistency)
  - positive_chunk_ids / negative_chunk_ids: remapped via T6-quater mapping (72 unique old pins; splits + many-to-one disclosed in T7-bis)
  - gold_method / gold_status / aggregate_exclude: unchanged (C9 magnitude contract)
Validators:     test_gold_bootstrap.py (snapshot string still pinned to pre-M4 epoch in the test constant — FU-M4-GATE); test_elder_care_slice_ready_intents_match_committed_gold
Consumers:      eval harness, elder_care_slice.json, gold_positive_counts.yaml
Last changed:   2026-08-21 (M4/W4 T7-bis)
```

```
Contract:       FTA revenue_by_segment / revenue_by_customer parse rows (M4/W4)
Module:         databricks/agents/subagents/workstream/financial/revenue_sub_agent.py
Serialization:  JSON → analysis.financial_trends revenue_by_segment_json / revenue_by_customer_json
Version:        unversioned — tracked by git blame (T2 `00e3583`)
Purpose:        Deduped, located revenue arrays after LLM parse
Fields:
  - segment/customer identity keys used in live T2 wiring: ("segment", "period", "revenue_dollars") / ("customer_name", "period", "revenue_dollars") — C3's planning-time names differed; landed keys are the contract
  - source_location: str | None — required schema key; None when the model omits it; row kept
Validators:     tests/test_revenue_sub_agent.py (closes D-M4-E for C3); T10 warehouse 0 duplicate groups, 40/40 nonempty source_location on segments
Consumers:      financial_trends_agent merge, basis_cross_check, fta_numeric spot-check
Last changed:   2026-08-21 (M4/W4 T2+T10)
```

```
Contract:       legal coverage-gap reason vocabulary (M4/W4 C7)
Module:         databricks/agents/workstreams/legal_contracts_agent.py::_assess_coverage_gaps
Serialization:  reason strings in analysis.legal data_room_gaps
Version:        unversioned — tracked by git blame (T4 `ca98e9b`)
Purpose:        Distinguish zero retrieved chunks from chunks-with-no-terms
Fields:
  - no_chunks_retrieved: zero chunks retrieved
  - retrieved_no_terms: chunks retrieved, no extractable terms
  - existing gap prose retained (additive vocabulary)
Validators:     T9-bis warehouse payload (no no_chunks_retrieved on the two widened passes)
Consumers:      product_backlog closes_when, T12
Last changed:   2026-08-21 (M4/W4 T4+T9-bis)
```

```
Contract:       PromotionResult / HarnessRun / ops.e2e_linkage (three faces of the promotion / checklist-linkage mechanism)
Module:         eval/retrieval/promotion_gate.py, eval/retrieval/scripts/record_e2e_linkage.py, eval/retrieval/store.py (DeltaEvalStore); HarnessRun defined in eval/retrieval/models.py
Serialization:  PromotionResult frozen dataclass; HarnessRun Pydantic BaseModel; ops.e2e_linkage Delta table (`eval/retrieval/scripts/apply_ops_ddl.sql`)
Version:        unversioned — tracked by git blame
Purpose:        Record golden-checklist scores against a pipeline HarnessRun and persist per-(run, agent) linkage for promotion
Fields:
  - PromotionResult: status (baseline_bootstrap | promoted | promotion_blocked | promotion_waived), candidate_score, candidate_total, prior_run_id, prior_score, waiver_id
  - ops.e2e_linkage columns: run_id, e2e_agent_id, e2e_snapshot_table, e2e_checklist_score, e2e_checklist_total, linked_at
  - HarnessRun e2e_* face (return type of record_e2e_linkage): e2e_agent_id, e2e_snapshot_table, e2e_checklist_score, e2e_checklist_total plus run_id / catalog / company_name
Validators:     eval/retrieval/tests/test_promotion_gate.py (evaluate_promotion; M3 spec §5 / G3); eval/retrieval/tests/test_record_e2e_linkage.py (record_e2e_linkage / ops.e2e_linkage INSERT; M-RE2 T9). M5 T5 also pins the Clearsulting driver in eval/retrieval/tests/test_promote_w2a_clearsulting.py (AST; not a substitute for those suites).
Consumers:      evaluate_promotion, record_e2e_linkage, `.dev/g1_score_all_agents.py` rubric-source convention (every golden checklist header cites `.dev/g1_score_all_agents.py::score_<agent>()` — Legal is `score_legal()`, never `score_lca()`)
Last changed:   2026-08-25 (eval-signal-foldback M5/W2a T7; mechanism landed by T5 job 370562481484117 — Clearsulting run_id 6e1b4f5d95284b33bbd08942b3595dd6, 7 e2e_linkage rows)
Landed (M6/T6-bis): T6-bis job `770829212065786` (`eval/program/promote_w2b_gkf.py`) — GKF run_id `cd3abe7b4c3b4b9a91ffa977c5d2c1ce`, 7 `ops.e2e_linkage` rows
Landed (M7/T6): T6 job `943705359150431` (`eval/program/promote_w2c_spg.py`) — SPG Legal-intent-group run_id `445878b36e06407385b9498dcab265c7` (GKF analogue `cd3abe7b4c3b4b9a91ffa977c5d2c1ce`), 7 `ops.e2e_linkage` rows; FTA floor **8/18** (checklist **8.5/18**; recorded beside GKF **14/18**); QoE `candidate_total=5` (vs GKF/Clearsulting `6`)
```

