Section:      module-map
Version:      1.3.0
Last updated: 2026-08-20

> **Cross-reference:** Retrieval-specific contracts and harness surfaces live in [`eval/architecture/rallyday/module-map.md`](../../eval/architecture/rallyday/module-map.md). This folder is the charter-named program-wide standing reference; it does not supersede the rallyday tree.

| Module path | Role | Key files | Stability |
|-------------|------|-----------|-----------|
| `databricks/jobs/scripts/` | Phase 1–2 batch scripts and Phase 1–5 pipeline runners (ingestion, classification, parsing, coverage, profiling, diligence) | `ingestion_parser.py`, `document_classifier.py`, `ensure_coverage.py`, `run_ingestion_pipeline.py`, `run_diligence_pipeline.py`, `run_full_pipeline.py`, `run_vdr_pipeline.py` | active |
| `databricks/jobs/scripts/` (ingestion-parser program — M0–M2) | Document-as-transaction ingestion state, manifest, per-doc worker, sync watermark | `doc_id.py`, `status_store.py`, `sync_state.py`, `parse_manifest.py`, `doc_worker.py`, `manifest_dry_run.py` | stable |
| `databricks/jobs/notebooks/` | Databricks notebook entry points and operator test harness | `test_pipeline.ipynb`, `run_vdr_job.py`, `02_ingestion_parser.ipynb` | active |
| `databricks/jobs/sql/` | Unity Catalog DDL and seed data for Garden rules and related tables | `create_rules_table.sql`, `seed_rules.sql` | stable |
| `databricks/agents/shared/` | Shared agent infrastructure: retrieval, base LLM/tool-call class, fallback search, run-context/provenance hooks | `retrieval.py`, `agent_base.py`, `fallback.py`, `run_context.py` | stable |
| `databricks/agents/workstreams/` | Phase 3–4 diligence agents — one module per workstream plus cross-analysis | `business_model_agent.py`, `financial_trends_agent.py`, `customer_quality_agent.py`, `kpi_agent.py`, `legal_contracts_agent.py`, `quality_of_earnings_agent.py`, `forecast_agent.py`, `cross_analysis_agent.py` | active |
| `databricks/agents/subagents/workstream/financial/` | Parallel FTA sub-extractors (revenue, EBITDA, OPEX) with CIM-first context building | `revenue_sub_agent.py`, `ebitda_sub_agent.py`, `opex_sub_agent.py`, `context_utils.py` | active |
| `databricks/agents/orchestration/` | Phase 3→5 DAG scheduler, bounded result-card interchange, Phase 5 memo assembler | `pipeline.py`, `orchestrator_agent.py` | stable |
| `databricks/agents/exec_summary/` | Post-DAG executive one-pager / orchestrator bundle pipeline | `bundle_builder.py`, `ingest.py`, `validate.py`, `orchestrator_bundle.schema.yaml` | active |
| `databricks/agents/ingestion/tools/` | SharePoint download and UC Volume upload (used by jobs, not Phase 3 agents) | `connector.py`, `uploader.py` | stable |
| `databricks/workflows/` | Databricks Workflow YAML job definitions | `uc13_ingestion_pipeline.yml`, `uc13_diligence_pipeline.yml`, `uc13_full_pipeline.yml`, `vdr_pipeline.yml` | stable |
| `eval/program/` | Eval program governance ledgers — registry decisions/waivers, product-signal backlog, eval-debt ratchet, exemptions, onboarding queue, playbook | `registry.yaml`, `product_backlog.yaml`, `eval_debt/eval_debt.yaml`, `eval_exemptions.yaml`, `onboarding_queue.yaml`, `normative_reference.md`, `eval_program_playbook.md` (companion to `eval_runbook.md`) | active |
| `eval/retrieval/` | Offline retrieval evaluation harness (RE² / M-RE1), gold labels, promotion gate, ingestion-parser rollout falsifiers | `harness.py`, `store.py`, `promotion_gate.py`, `measure_join_orphan_rate.py`, `measure_attestation.py`, `gold_labels/` | active |
| `eval/content/` | S2 content-tier pre-plan: §8.7 agreement predicates, judge-capability calibration driver, rung-3 human spot-check rubrics | `agreement.py`, `calibration.py`, `exec_summary_spot_check_rubric.md`, `*_rubric_claims.json` | active |
| `.dev/eval-program/` | Eval-program registry and operator-labelled §8.7 calibration samples (gitignored; content SHA tracked at gate review) | `registry.yaml`, `calibration_sample_{fta_numeric,legal_register,exec_summary}.yaml` | active |
| `eval/{BMA,CQA,FTA,KPI,LCA,PROFILER,QOE}/` | Per-workstream golden checklists for manual/agent QA | `golden_checklist_elder_care.md` (per agent) | active |
| `tests/` | Repo-root pytest suite for Databricks pipeline, agents, ingestion, architecture compliance | `test_*_agent.py`, `test_catalog_convention.py`, `test_retrieval.py`, `test_ingestion_parser_extensions.py`, `test_docworker_state_transitions.py`, `test_make_doc_id.py`, `test_sync_gate_watermark.py`, `test_measure_attestation.py` | stable |
| `frontend/` | React SPA — My Garden opportunities, Garden rules (NL/AI), placeholder dashboard | `src/pages/`, `src/api/`, `src/components/rules/` | active |
| `backend-api/` | Express REST BFF for UI; pluggable memory or Databricks SQL store | `src/routes/`, `src/repositories/`, `src/services/` | active |
| `backend-ai/` | FastAPI service for NL rule interpretation via Databricks Genie (or mock) | `app/routes/rules_nl.py`, `app/services/genie_rules.py` | experimental |
| `scripts/` | Dev orchestration helper for backend-ai | `dev-ai.mjs` | stable |
| `rules-config/` | Gitignored experiment sink for AI-generated rule JSON artifacts | (empty / placeholder) | experimental |
| `context/` | Design docs, backlog, and session context (not runtime) | `context_docs/` | [needs confirmation] — reference material only |

## eval/program ledger closure convention (M2/W0)

`eval_debt.yaml` and `product_backlog.yaml` share the same optional closure-field shape: `closed_at` + `closed_evidence_refs` (no `status` field on either ledger). `registry.yaml` uses `status` / `disposition` lifecycle fields instead — by design, only the two debt-like ledgers adopt the closure-field pair. Landed M2/W0: four `product_backlog.yaml` measurement-caveat rows closed (T4); SPG `spg:global:post_m4_corpus_dedup_baseline_stale` eval-debt closed with live count **44038** (T3); playbook §3.1 documents `product_backlog.yaml` and §13 last-consolidated line updated (T5).
