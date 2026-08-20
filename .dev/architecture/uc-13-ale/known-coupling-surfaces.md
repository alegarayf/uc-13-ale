Section:      known-coupling-surfaces
Version:      1.2.0
Last updated: 2026-08-20

> **Cross-reference:** Retrieval-specific coupling surfaces live in [`eval/architecture/rallyday/known-coupling-surfaces.md`](../../eval/architecture/rallyday/known-coupling-surfaces.md). This folder is the charter-named program-wide standing reference; it does not supersede the rallyday tree.

```
Surface:      Catalog name split — `uc13` (production) vs `uc13_ale` (eval/harness/notebook default)
Shared by:    databricks/jobs/scripts (default uc13) ↔ test_pipeline.ipynb / workflow YAML (uc13_ale) ↔ eval/retrieval (uc13_ale.ops) ↔ backend-api (configurable DATABRICKS_CATALOG)
Failure mode: Agent writes to uc13 but harness reads uc13_ale — promotion scores appear empty or stale
Confirmed:    yes — databricks/CLAUDE.md catalog convention; tests/test_catalog_convention.py
Landed (M3/T5): This exact split caused a live defect — `document_classifier.py::_backfill_missing_doc_ids` hashed `doc_relevance.doc_id` with the table's own catalog (`uc13_ale`) while the corresponding `chunks.doc_id` had been hashed at ingestion time with a different catalog (`uc13`), producing a 99.80% join-orphan rate (M3 audit Finding F2; CHANGELOG "Operator actions"). Fixed by an explicit, optional `hash_catalog` parameter on `_build_classification_record`/`_backfill_missing_doc_ids` (defaults to `catalog`, i.e. unchanged for same-run production behavior) plus a loud print warning on divergence and an operator-facing `doc_id_hash_catalog` job param for out-of-band re-backfills. See `.dev/planning/uc13-ingestion-parser/M3/decisions/T5.md`. This confirms the pre-existing scout-incomplete finding (M3 audit §10): a catalog-resolution grep belongs in this surface's standard coupling checklist for any future hash/key computation spanning a write path and a read/backfill path.
```

```
Surface:      `legal` table vs `legal_contracts` VIEW vs registry key `legal_contracts`
Shared by:    legal_contracts_agent (writes analysis.legal) ↔ pipeline.AGENT_REGISTRY (key legal_contracts) ↔ orchestrator _SECTIONS ↔ exec_summary constants (key legal)
Failure mode: Orchestrator loads empty section or exec_summary ingest misses legal block if VIEW dropped or key mismatched
Confirmed:    yes — databricks/CLAUDE.md; agent writes legal, pipeline reads legal_contracts view
```

```
Surface:      Join column name mismatch — `chunks.file_name` = `doc_relevance.filename`
Shared by:    ingestion_parser (writes file_name) ↔ document_classifier (writes filename) ↔ retrieval.py (JOIN)
Failure mode: Hydration returns zero workstream/priority_tier; workstream_filter starves agents
Confirmed:    yes — retrieval.py JOIN
Landed (M3):  Production retrieval JOIN migrated to `c.doc_id = r.doc_id` in `_hydrate_chunks_sql` and `_keyword_fallback_sql`; `doc_relevance.doc_id` populated via frozen `make_doc_id` at classifier write (`_build_classification_record`) + `_backfill_missing_doc_ids`. Legacy `file_name`+`company_name` key remains on `eval/retrieval/gold/bootstrap.py` and `ensure_coverage.py` `relevance_map` (out of M3 charter scope — Tier-2 amendment candidates). Orphan-rate before/after falsifier: `eval/retrieval/measure_join_orphan_rate.py::measure_orphan_rate` (operator-run; G4).
Landed (M3/T5): `_build_classification_record`/`_backfill_missing_doc_ids` now accept an optional `hash_catalog` param (defaults to `catalog`) guarding against exactly the catalog-mismatch failure mode that produced a live 99.80% orphan rate before the initial M3 landing was corrected — see the Catalog name split surface above and `.dev/planning/uc13-ingestion-parser/M3/decisions/T5.md`.
```

```
Surface:      `company_name` partition key
Shared by:    All ingestion and analysis Delta tables ↔ all agent main() DELETE filters ↔ retrieval queries
Failure mode: Cross-company data leak or orphan rows if DELETE predicate omitted in new table
Confirmed:    yes — pervasive in agent main() patterns
```

```
Surface:      Workstream tag string constants (BUSINESS_MODEL, FINANCIAL, QUALITY_EARNINGS, KPI_OPS, LEGAL, etc.)
Shared by:    document_classifier.py ↔ ingestion_parser chunk tagging ↔ retrieval workstream_filter ↔ ensure_coverage workstream coverage check
Failure mode: Agent retrieves zero chunks for renamed tag; coverage backfill misses workstream
Confirmed:    yes — grep across classifier and retrieval
```

```
Surface:      `source_type` enum — text | table | vision
Shared by:    ingestion_parser Chunk dataclass ↔ ensure_coverage schema ↔ retrieval._TYPE_ORDER ↔ context_utils sort
Failure mode: New source type silently dropped or mis-sorted in CIM-first context building
Confirmed:    yes — databricks/CLAUDE.md source_type rules
```

```
Surface:      `priority_tier` integer (1 highest) and merge-rank weights {1: 1.0, 2: 0.7, 3: 0.4}
Shared by:    document_classifier ↔ chunks/embeddings ↔ retrieval merge-rank
Failure mode: Tier mislabeling deprioritizes critical CIM/financial chunks
Confirmed:    yes — retrieval.py
```

```
Surface:      Databricks secrets scope name `uc13` (hardcoded in connector.py)
Shared by:    SharePoint connector ↔ setup scripts
Failure mode: Connector fails if secrets moved to different scope without code change
Confirmed:    yes — connector.py
```

```
Surface:      Model serving endpoint widget names — llm_endpoint, extraction_endpoint, vision_endpoint, embedding_endpoint
Shared by:    Notebook Cell 1 widgets ↔ os.environ mirroring ↔ PipelineOrchestrator._sync_env ↔ agent_base._call_llm defaults
Failure mode: Agents call wrong model or default Sonnet/Haiku mismatch causes truncation
Confirmed:    yes — pipeline _sync_env; databricks/CLAUDE.md endpoint table
```

```
Surface:      RE2 environment variables — RE2_CATALOG, RE2_STORE_BACKEND, RE2_INGESTION_SNAPSHOT, RE2_REGISTRY_HASH, RE2_GOLD_SNAPSHOT, RE2_PROVENANCE_REQUIRED
Shared by:    PipelineOrchestrator._sync_env ↔ run_context.py ↔ retrieval.py lazy provenance
Failure mode: Provenance emission silently disabled or written to wrong store backend
Confirmed:    yes — run_context and pipeline code
```

```
Surface:      Flag and Citation JSON shapes
Shared by:    All workstream agents ↔ to_result_card ↔ orchestrator ↔ exec_summary ingest
Failure mode: Memo rendering breaks or bundle validation fails on unexpected field
Confirmed:    yes — agent_base dataclasses used consistently
```

```
Surface:      Mock user email — DEFAULT_OPPORTUNITY_OWNER_EMAIL in backend-api ↔ frontend constants/user.ts
Shared by:    CompaniesService ↔ My Garden UI
Failure mode: UI shows empty garden or wrong owner's opportunities
Confirmed:    yes — both hardcode mcrysler@nimblegravity.com
```

```
Surface:      Garden rules UC table FQN — {DATABRICKS_CATALOG}.{DATABRICKS_SCHEMA}.rules
Shared by:    backend-api tableRef ↔ databricks/jobs/sql/create_rules_table.sql DDL
Failure mode: API CRUD fails if DDL run in different catalog than API env
Confirmed:    yes — backend-api config and SQL DDL
```

```
Surface:      Duplicated get_param / _get_dbutils / find_repo_root helpers
Shared by:    Each workstream agent module ↔ orchestrator_agent ↔ job scripts
Failure mode: Widget/env drift between notebook and imported module copies
Confirmed:    yes — copy-paste pattern noted in databricks/CLAUDE.md
```

```
Surface:      salesforce_silver.opportunity_silver fixed FQN
Shared by:    backend-api companies repository only
Failure mode: My Garden breaks if table moved or renamed; not governed by catalog convention test
Confirmed:    yes — companiesRepository.databricks.ts
```

```
Surface:      Registry `rung_assignments` judge/human values ↔ item-23b presence half
Shared by:    `.dev/eval-program/registry.yaml` (T5 writes CHK-26a) ↔ `eval/retrieval/tests/test_calibration_samples.py::derive_judge_human_surfaces`
Failure mode: Stale green if item-23b suite is not re-run after item 26a closes — presence half skipped when population empty (T4); G5 requires post-26a re-run (M2 plan §5.4 coupling 2)
Confirmed:    yes — T7 G5 close-out: 11/11 calibration-sample tests pass including `test_sample_presence_half`
Landed (M2):  Operational reading of G5 "all four sample files" = every §8.7 sample file present (three surfaces, two conditional); legal_register sample absent on item 23a go path.
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
Confirmed:    yes — test_eval_debt.py::test_committed_ledger_ratchet_passes asserts committed ledger (**20 total / 2 open**, HWM **14**) passes ratchet; HWM is a manual, reviewed field
Landed (M2/W0): SPG `spg:global:post_m4_corpus_dedup_baseline_stale` closed with live warehouse count **44038** (T3); prior stale doc count 5 open / 18 total superseded
```

```
Surface:      product_backlog.yaml ↔ eval_debt.yaml closure-field shape parity
Shared by:    eval/program/product_backlog.yaml ↔ eval/program/eval_debt/eval_debt.yaml ↔ validate_product_backlog_closure_shape in test_product_backlog_schema.py
Failure mode: A closure recorded with `closed_evidence_refs` but no `closed_at`, or a `status` field introduced on either ledger, breaks ratchet/validator assumptions and diverges from playbook §3.1 prose
Confirmed:    yes — four M2/W0 product_backlog closures and SPG eval_debt closure share `closed_at` + `closed_evidence_refs`; registry.yaml retains `status`/`disposition` instead (by design)
Landed (M2/W0): first product_backlog closure-field adoption (T4); playbook cross-ref (T5)
```

[needs confirmation] — additional coupling surfaces from operator knowledge welcome via interview.
