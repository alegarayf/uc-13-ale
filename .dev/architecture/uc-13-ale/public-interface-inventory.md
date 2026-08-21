Section:      public-interface-inventory
Version:      1.5.0
Last updated: 2026-08-21

> **Cross-reference:** Retrieval-specific interfaces live in [`eval/architecture/rallyday/public-interface-inventory.md`](../../eval/architecture/rallyday/public-interface-inventory.md). This folder is the charter-named program-wide standing reference; it does not supersede the rallyday tree.

## Databricks pipeline

| Symbol | Module | Kind | Signature summary | Consumed by | Stability |
|--------|--------|------|-------------------|-------------|-----------|
| `semantic_search` | `databricks/agents/shared/retrieval.py` | function | Vector-search + Delta hydrate; returns `RouteResult` with ranked chunks | All Phase 3 workstream agents, FTA subagents, eval harness | stable |
| `semantic_search_with_fallback` | `databricks/agents/shared/fallback.py` | function | Wraps `semantic_search`; retries without `file_name_filter` when results sparse. M4/W4 T4-bis: additive `vs_metadata_filters: bool = False` forwarded to `retrieval.py::semantic_search`; only `legal_contracts_agent` `ip_privacy` pass sets it `True` | BMA, Legal, FTA `context_utils` | stable |
| `WorkstreamAgent` | `databricks/agents/shared/agent_base.py` | class | Base LLM/tool-call infrastructure: `_call_llm`, `_tool_call`, flag/citation accumulation | Workstream agents (direct subclass or via `self._base`) | stable |
| `RouteResult` | `databricks/agents/shared/retrieval.py` | type | `{chunks, mode, scores}` retrieval result envelope | Agents, subagents, harness | stable |
| `Flag`, `Citation`, `ToolResult` | `databricks/agents/shared/agent_base.py` | type | Standard flag/citation/trace dataclasses written to Delta JSON columns | All workstream agents, orchestrator, exec_summary ingest | stable |
| `AGENT_REGISTRY` | `databricks/agents/orchestration/pipeline.py` | constant | Canonical DAG: agent keys, module paths, table suffixes, hard/soft deps | `PipelineOrchestrator`, `cross_analysis_agent` | stable |
| `AgentSpec` | `databricks/agents/orchestration/pipeline.py` | type | Per-agent DAG node metadata | `PipelineOrchestrator` | stable |
| `to_result_card` | `databricks/agents/orchestration/pipeline.py` | function | Builds size-bounded summary card from agent Delta row for downstream phases | Cross-Analysis, Orchestrator | stable |
| `collect_result_cards` | `databricks/agents/orchestration/pipeline.py` | function | Collects result cards for all Phase 3 agents | Orchestrator | stable |
| `PipelineOrchestrator` | `databricks/agents/orchestration/pipeline.py` | class | Wave-scheduled parallel agent runner with retry and failure isolation | `run_pipeline` | stable |
| `run_pipeline` | `databricks/agents/orchestration/pipeline.py` | function | Job/notebook entry for Phases 3–5 | `run_diligence_pipeline.py`, `run_full_pipeline.py` | stable |
| `main` (per workstream) | `databricks/agents/workstreams/*.py` | function | Agent entry: DELETE-by-company + extract + write `{catalog}.analysis.*` | Pipeline DAG, notebooks, tests | active |
| `generate_*_assessment` | workstream modules | function | Narrative markdown section from agent's own Delta row (bounded context) | `orchestrator_agent.py` | active |
| `OrchestratorAgent` | `databricks/agents/orchestration/orchestrator_agent.py` | class | Phase 5 memo assembly, coherence checks, executive summary | `run_pipeline` | stable |
| `build_exec_summary` | `databricks/agents/exec_summary/` | function | VDR bridge: Delta ingest → bundle → TL;DR one-pager | `run_vdr_pipeline.py` | active |
| `BundleBuilder` | `databricks/agents/exec_summary/bundle_builder.py` | class | Assembles orchestrator bundle from agent outputs | exec_summary pipeline | active |
| `convert_md_to_word` | `databricks/jobs/scripts/md_to_word.py` | function | Markdown diligence report → styled `.docx` | Orchestrator, exec_summary, VDR pipeline | stable |
| `main` (ingestion jobs) | `databricks/jobs/scripts/*.py` | function | Phase 1–2 script entry points callable from notebooks or jobs | Workflow YAML tasks, `run_ingestion_pipeline.py` | stable |
| `main_coverage_backfill` | `databricks/jobs/scripts/ensure_coverage.py` | function | APPEND-only workstream gap filler (Phase 2c; manual path — automatic coverage folded into ParseManifest sub-pass in M2) | operator manual invoke | stable |
| `make_doc_id` | `databricks/jobs/scripts/doc_id.py` | function | `make_doc_id(catalog, schema, company, folder_path, file_name) -> str` — frozen M0 doc_id constructor | `parse_manifest.py`, `doc_worker.py`, `document_classifier.py`, `ingestion_parser.parse_file` callers | stable |
| `ensure_doc_status`, `StatusStore`, `StatusRow` | `databricks/jobs/scripts/status_store.py` | function/class | §8.1 `doc_status` DDL ensure; company-filtered `read_status_map`; per-transition `upsert`; catalog-wide `has_newer_complete_than` / `max_complete_updated_at` (M2 SyncGate) | `parse_manifest.py`, `doc_worker.py`, `ingestion_parser.main`, `ensure_coverage.get_coverage_report` | stable |
| `ParseManifest`, `ManifestItem`, `ManifestSummary` | `databricks/jobs/scripts/parse_manifest.py` | class | Read-only S1 work-list builder (NEW/STALE/RETRY/SKIP + coverage sub-pass) | `ingestion_parser.main`, `manifest_dry_run.py` | stable |
| `DocWorker`, `RunSummary`, `format_run_summary` | `databricks/jobs/scripts/doc_worker.py` | class/function | Per-doc claim→clean→parse→chunks→embed→complete/fail loop | `ingestion_parser.main` | stable |
| `ensure_sync_state`, `read_watermark`, `advance_watermark` | `databricks/jobs/scripts/sync_state.py` | function | §8.4 `sync_state` DDL ensure; watermark read/advance (sole writer, M2) | `ingestion_parser.main` SyncGate | stable |
| `run_manifest_dry_run`, `format_run_summary` (dry-run) | `databricks/jobs/scripts/manifest_dry_run.py` | function | M0 runnable checkpoint — S0+S1 read-only manifest dry-run | operator / notebook | stable |
| `list_companies`, download helpers | `databricks/agents/ingestion/tools/connector.py` | function | SharePoint → file bytes via Microsoft Graph | `download_upload.py` | stable |
| `upload_files` | `databricks/agents/ingestion/tools/uploader.py` | function | `FilePayload` → UC Volume (LOCAL REST or cluster FUSE) | `download_upload.py` | stable |

## eval/program — governance registry (eval-signal-foldback M2/W0)

| Symbol | Module | Kind | Signature summary | Consumed by | Stability |
|--------|--------|------|-------------------|-------------|-----------|
| `registry.yaml` | `eval/program/registry.yaml` | artifact | Work-item ledger; actionable rows carry D3 `tshirt` (`xs`–`xl`, `unsizable`); 54 actionable rows ratcheted in `test_eval_program_registry.py` | `trust_statement.py`, playbook §3.1, eval_debt evidence resolution | active |
| `GAP-109-cross-company-legal-kpi-g1-weakness` | `eval/program/registry.yaml` | registry row | Cross-company Legal/KPI G1 root-cause investigation (`tshirt: l`); distillation-era rationale | prioritization, playbook M2/W0 consolidation | active |
| `OI-eval-harness-spg-residual-filename-closure-gold-completeness` | `eval/program/registry.yaml` | registry row | D8 residual SPG `filename_closure` gold-completeness debt (`tshirt: m`); cross-ref in closed `product_backlog` rows | `product_backlog.yaml` closure evidence, playbook | active |
| `product_backlog.yaml` | `eval/program/product_backlog.yaml` | artifact | S2 product-signal ledger; optional `closed_at` + `closed_evidence_refs` on closed rows (no `status` field). M4/W4: `schema_version` 1, **21** items, **12** closed ids (`CLOSED_TARGET_IDS`); 8 M4 closures + 4 pre-M4 caveat closures; open handoff `PB-exec_summary-008-locator-mismatch` | `test_product_backlog_schema.py`, playbook §3.1 | active |
| `eval_debt.yaml` | `eval/program/eval_debt/eval_debt.yaml` | artifact | Tracked-gap ledger — 20 total / 2 open, HWM 14; same closure-field pair as product_backlog | `eval_debt.py`, `test_eval_debt.py` | active |
| `TSHIRT_VALUES` | `eval/retrieval/tests/test_eval_program_registry.py` | constant | `frozenset({"xs","s","m","l","xl","unsizable"})` — D3 vocabulary enforced on actionable registry rows | `test_actionable_registry_rows_have_d3_tshirt_sizes` | stable |
| `FROZEN_ACTIONABLE_TSHIRT_ROW_COUNT` | `eval/retrieval/tests/test_eval_program_registry.py` | constant | `54` — ratchet count for pending/in_progress registry rows with in-vocabulary `tshirt` | registry sizing CI guard | stable |
| `eval_program_playbook.md` | `eval/eval_program_playbook.md` | doc | Operator playbook; §3.1 lists `product_backlog.yaml`; §13 last-consolidated cites M2/W0 ledger truth-up | human operators | active |

## Eval harness

| Symbol | Module | Kind | Signature summary | Consumed by | Stability |
|--------|--------|------|-------------------|-------------|-----------|
| `run_harness` | `eval/retrieval/harness.py` | function | Executes retrieval scenarios against gold labels | CI, promotion gate, operator runs | active |
| `evaluate_promotion` | `eval/retrieval/promotion_gate.py` | function | Compares harness scores against baseline for promotion decision | Chip A/B validation workflows | active |
| `ProvenanceEmitter` | `eval/retrieval/provenance.py` | class | Emits retrieval provenance records to eval store | `retrieval.py` (lazy), RE2-enabled agents | active |
| `measure_orphan_rate` | `eval/retrieval/measure_join_orphan_rate.py` | function | Join-orphan count/rate against live `chunks`/`doc_relevance` in `file_name` (before) or `doc_id` (after) key mode; notebook-callable `main()` | Operator G4 falsifier runs (R-08 before/after) | active |
| `run_attestation_query` | `eval/retrieval/measure_attestation.py` | function | G5-gated `doc_status` status histogram + non-COMPLETE error detail for one company | Operator G5 rollout attestation | active |
| `run_vision_share_query` | `eval/retrieval/measure_attestation.py` | function | Informational `chunks` `source_type` composition companion (spec §15) — separate from G5 attestation | Operator rollout reporting | active |
| `format_attestation_phv_line` | `eval/retrieval/measure_attestation.py` | function | PHV stdout shape: *"N approved, M complete, K failed with reason X"* | `measure_attestation.main` | active |
| `build_parser` / CLI (`--catalog`, `--schema`, `--company`) | `eval/retrieval/measure_attestation.py` | function/CLI | Frozen argparse surface for standalone attestation runs (defaults: `uc13_ale`, `ingestion`, `Elder Care`) | Operator G5 falsifier | active |

## S2 content-tier pre-plan (eval/content)

| Symbol | Module | Kind | Signature summary | Consumed by | Stability |
|--------|--------|------|-------------------|-------------|-----------|
| `spans_agree` | `eval/content/agreement.py` | function | §8.7 span-half agreement over operator/judge `expected_span` dicts | `calibration.py`, hermetic tests | stable |
| `values_agree` | `eval/content/agreement.py` | function | §8.7 value-half agreement with exact-decimal unit normalization | `calibration.py`, hermetic tests | stable |
| `verdicts_agree` | `eval/content/agreement.py` | function | Non-numeric verdict equality over §16 claim-verdict vocabulary | `calibration.py`, hermetic tests | stable |
| `compute_metrics` | `eval/content/agreement.py` | function | Class-conditional agreement metrics (C6 figure sets) per surface sample | `calibration.py`, hermetic tests | stable |
| `evaluate_thresholds` | `eval/content/agreement.py` | function | C5 + P1–P4 composition pins; returns `ThresholdResult` (2-tuple **retired**). Full signature in the M3/W1 table below. | `calibration.py:run_calibration`, `test_agreement.py`, `test_calibration_sample_power.py` | active |
| `main` (calibration driver) | `eval/content/calibration.py` | function | `python -m eval.content.calibration` — `--surface` `--sample` `--company` `--catalog` `--endpoint` `--out` (`calibration.py:677–684`) | Operator D9 / item 26a runs | active |

## eval/content — calibration power (eval-signal-foldback M3/W1)

Re-read from landed files at T5 execution (T1 commit `214d5a76`). The 2-tuple `(passed, failure_reasons)` return of `evaluate_thresholds` is **retired**; callers use `ThresholdResult` fields (`test_agreement.py` migrated sites assert `result.passed` / `result.failure_reasons`, e.g. the empty-population test at `test_agreement.py:225–228`).

| Symbol | Module | Kind | Signature summary | Consumed by | Stability |
|--------|--------|------|-------------------|-------------|-----------|
| `SampleComposition` | `eval/content/agreement.py:SampleComposition` | type | `@dataclass(frozen=True)`: `retained_count: int`; `verdict_counts: dict[str, int]` (keys ⊆ `CLAIM_VERDICTS`); `distinct_expected_chunk_ids: int` | `evaluate_thresholds`, `compute_sample_composition`, tests | active |
| `ThresholdResult` | `eval/content/agreement.py:ThresholdResult` | type | `@dataclass(frozen=True)`: `passed: bool`; `failure_reasons: list[str]`; `unevaluated_pins: list[str]` | `calibration.py:run_calibration` `--out` JSON; hermetic tests | active |
| `compute_sample_composition` | `eval/content/agreement.py:compute_sample_composition` | function | `sample: dict[str, Any] -> SampleComposition`. Pure. `retained_count = len(sample.get("claims") or [])`; `verdict_counts` over `CLAIM_VERDICTS` only; `distinct_expected_chunk_ids` counts distinct non-null `(c.get("expected_span") or {}).get("chunk_id")`. Empty/missing `claims` → `retained_count=0`. | `calibration.py:645`; `test_agreement.py`; `test_calibration_sample_power.py` | active |
| `evaluate_thresholds` | `eval/content/agreement.py:evaluate_thresholds` | function | `(surface, figures, *, verdict_threshold=0.80, value_threshold=0.90, span_threshold=0.80, sample_composition: SampleComposition \| None = None) -> ThresholdResult`. Keyword-only `sample_composition` defaults `None`. | `calibration.py:642–646` (always passes composition); tests | active |
| `MIN_SAMPLE_COUNT` | `eval/content/agreement.py` | constant | `25` (P1) | `_append_composition_pin_reasons` | active |
| `MAX_MAJORITY_CLASS_FRACTION` | `eval/content/agreement.py` | constant | `0.60` (P2) | `_append_composition_pin_reasons` | active |
| `MIN_DISTINCT_EXPECTED_CHUNK_IDS` | `eval/content/agreement.py` | constant | `8` (P3) | `_append_composition_pin_reasons` | active |
| `DEGENERATE_FLOOR_MARGIN` | `eval/content/agreement.py` | constant | `0.10` (P4) | `_append_composition_pin_reasons` | active |
| `unevaluated_pins` | `ThresholdResult` field **and** `run_calibration` `--out` JSON key | field | `list[str]`. Pin id never in both `failure_reasons` and `unevaluated_pins` (`test_evaluate_thresholds_channel_disjointness_matrix`). Entries carry the reason in the string: omitted = `"P{n}: omitted (sample_composition is None)"` (`agreement.py:_OMITTED_REASON`); numeric inapplicable = `"P2: inapplicable (numeric surface)"` / `"P4: inapplicable (numeric surface)"` (`agreement.py:_NUMERIC_INAPPLICABLE_REASON`). | T3 signoffs JSON; T4 post-check | active |
| `calibration_sample_exec_summary.yaml` | `eval/content/calibration_samples/calibration_sample_exec_summary.yaml` | artifact | Tracked D9 `exec_summary` sample. Header `assessed_by: operator`, `assessed_at: '2026-08-13'`. Claims `exec.claim.001`–`028` only (no dual-source additions). | `run_calibration --sample`; `test_calibration_sample_power.py`; `test_calibration_sample_ids_001_028_match_rubric_verbatim` | active |

**`evaluate_thresholds` behavior (landed `agreement.py:361–405`):**

- Any surface + `sample_composition=None` → `passed=False` unconditionally; P1–P4 in `unevaluated_pins` with the omitted reason; C5 figure checks still populate `failure_reasons` (`test_evaluate_thresholds_omitted_composition_fail_closed_verdict` / `_numeric`).
- Verdict surface + composition → P1–P4 evaluated; existing `verdict_threshold` (0.80) retained as an additional unprefixed reason. Failed evaluated pins are prefixed `"P1:"`–`"P4:"`.
- Numeric surface (`NUMERIC_SURFACES = frozenset({"fta_numeric"})`, membership frozen) + composition → P1 and P3 evaluated; P2/P4 recorded in `unevaluated_pins` as inapplicable (`test_evaluate_thresholds_numeric_pins_skipped_not_defaulted`); C5 value/span/HALT-29 unchanged.
- Never raises on `None` or degenerate composition (`test_evaluate_thresholds_degenerate_composition_does_not_raise`).

**`--out` JSON (landed `calibration.py:648–658`):** `passed`, `failure_reasons`, `unevaluated_pins`, `figures`, `claim_count` populated from `ThresholdResult` + `compute_metrics`. `rung_assignment` is `"judge" if threshold_result.passed else "human"` — driver output only, not a write to `eval/program/registry.yaml`. T3 artifact (quoted by the T4 wave note, re-read at T5): `passed=false`; `failure_reasons=["P2: majority class fraction 0.9286 > 0.6", "P4: verdict_agreement 0.8214 < majority baseline 0.9286 + 0.1"]`; `unevaluated_pins=[]`; `claim_count=28`; `figures.verdict_agreement=0.8214285714285714`; `rung_assignment=human`. Consistent with T4: D9 promotion inadmissible; W3 does not convert this fail into a pass.

## eval/content + agents — product fixes (eval-signal-foldback M4/W4)

Re-read from landed files at T13 closeout (T12 commit `8e7c0619254cbefcb44aa1cfb68b17730ef035fe` plus this closeout). `SUBSTRING(chunk_text, 1, 1200)` / `excerpt` are **retired** in `calibration.py`.

| Symbol | Module | Kind | Signature summary | Consumed by | Stability |
|--------|--------|------|-------------------|-------------|-----------|
| `ChunkIndex.fetch_text` | `eval/content/spot_check.py:243` | instance-method | `fetch_text(chunk_ids: frozenset[str]) -> dict[str, str]` — on-demand SQL text for resolved ids; `from_sql` stays metadata-only (`CAST(NULL AS STRING)`) | exec_summary spot-check resolution | active |
| `dedupe_rows_by_key` | `databricks/agents/subagents/workstream/financial/revenue_sub_agent.py:103` | function | `dedupe_rows_by_key(rows, key_fields) -> list[dict]` — first-occurrence; rows missing a key field retained | FTA revenue parse path | active |
| `make_warehouse_chunk_resolver` | `eval/content/legal_register_verifier.py` | function | Locator→chunk cascade: split `" | "` `source_doc`, then section+page, file+section, file-only; deterministic order; miss → `None` | `verify_legal_register` | active |
| `CLOSED_TARGET_IDS` | `eval/retrieval/tests/test_product_backlog_schema.py` | constant | 12-id frozenset; `test_product_backlog_closed_row_set` (renamed from `test_product_backlog_exactly_four_closed_rows`) | schema gate | active |
| `BROKEN_CHUNK_ID` / `SIBLING_CHUNK_ID` / `LOCATION_CHUNK_OVERRIDE` | `eval/content/spot_check.py:53–57` | constant | Post-re-parse: broken `aee7745d…`; sibling/override `2d238ee0…` (repoint, not retire) | exec_summary Layer-B | active |

## Backend API (Express)

| Symbol | Module | Kind | Signature summary | Consumed by | Stability |
|--------|--------|------|-------------------|-------------|-----------|
| `GET/POST/PUT/PATCH/DELETE /api/rules` | `backend-api/src/routes/rules.ts` | REST | CRUD for Garden rules | `frontend/src/api/rules.ts` | active |
| `GET /api/companies` | `backend-api/src/routes/companies.ts` | REST | List opportunities for configured owner email | `frontend/src/api/companies.ts` | active |
| `GET /api/config` | `backend-api/src/app.ts` | REST | `{ dataStore, aiBaseUrl, cache }` runtime config | `frontend/src/api/config.ts` | stable |
| `createRulesRepository` | `backend-api/src/repositories/createRulesRepository.ts` | factory | Returns memory or Databricks rules repository | `rulesService` | stable |

## Backend AI (FastAPI)

| Symbol | Module | Kind | Signature summary | Consumed by | Stability |
|--------|--------|------|-------------------|-------------|-----------|
| `POST /api/ai/rules/interpret` | `backend-ai/app/routes/rules_nl.py` | REST | NL prompt → `{ sessionId, summary, ruleConfig, aiMode }` | `frontend/src/api/nlRules.ts` | experimental |
| `POST /api/ai/rules/sessions/{id}/deny` | `backend-ai/app/routes/rules_nl.py` | REST | Retry interpretation with user feedback | `frontend/src/api/nlRules.ts` | experimental |

## Frontend API clients

| Symbol | Module | Kind | Signature summary | Consumed by | Stability |
|--------|--------|------|-------------------|-------------|-----------|
| `apiGet`, `apiPost`, `apiPut`, `apiDelete` | `frontend/src/api/client.ts` | function | Typed fetch wrapper for backend-api | rules, companies pages | stable |
| `aiGet`, `aiPost` | `frontend/src/api/aiClient.ts` | function | Typed fetch wrapper for backend-ai | Garden rules AI panel | stable |
| `buildAiRuleCreateInput` | `frontend/src/components/rules/buildAiRuleApiInput.ts` | function | Maps Genie `ruleConfig` → API rule create payload | `NlRuleFormModal` | active |
