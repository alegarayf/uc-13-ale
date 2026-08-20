Section:      open-questions
Version:      1.6.0
Last updated: 2026-08-20

```
Question:     Will Garden rules (python_source) be executed at runtime against opportunity_silver, and if so where?
Impact:       backend-ai codegen, backend-api storage, future execution service
Closes when:  Execution host and contract are specified (in-process, Databricks job, or deferred)
```

```
Question:     What is the production auth model for frontend → backend-api and frontend → backend-ai?
Impact:       integration-seams.md, CORS, deployment topology
Closes when:  Auth mechanism chosen and implemented (e.g. SSO, API gateway, none for internal VPN)
```

```
Question:     Should DATABRICKS_CATALOG/SCHEMA always be `garden` for rules, matching create_rules_table.sql?
Impact:       known-coupling-surfaces garden.rules entry, deployment docs
Closes when:  Catalog/schema convention documented in .env.example or infra config
```

```
Question:     Will UC13 diligence outputs (uc13.analysis.*) surface in the Rallyday Garden UI?
Impact:       module-map coupling note, future frontend modules
Closes when:  Product decision and API seam defined or explicitly deferred
```

```
Question:     Is a shared types package (Rule, Company, ruleConfig) warranted across frontend, backend-api, and backend-ai?
Impact:       dependency-graph duplicate-type coupling
Closes when:  Monorepo tooling decision (OpenAPI codegen, shared npm package, or status quo)
```

```
Question:     Production deployment target for backend-api, backend-ai, and frontend (Databricks Apps, containers, static CDN)?
Impact:       integration-seams, environment variable strategy
Closes when:  Deployment architecture documented outside this folder
```

```
Question:     How should OPEX sub-agent context ranking deprioritize Projection/Forecast chunks to fix L3.context_basis_mismatch without regressing other fields?
Impact:       context_utils.build_focused_context, FTA opex_sub_agent retrieval queries
Closes when:  Basis-aware sort or filename filter landed and re-scored on Elder Care golden checklist
Note:         M-RE2 added basis_cross_check discrepancy detection and OPEX labeled context with per-query budgets; 7/02 FTA re-score 16/18 restored field 9 (OPEX basis). Ranking-level fix remains open.
```

```
Question:     How should M2 reconcile D2a normative extraction field names with dormant roll-up/flag helpers that still reference legacy names (exclusivity_mfn_noncompete, liability_cap)?
Impact:       legal_contracts_agent _build_restrictive_covenant_map, _apply_legal_flags, coc_consent_list_json, termination_exposure_json, restrictive_covenant_map_json population
Closes when:  Legal-agent M2 roll-up/flag wiring landed with field-name alignment and cluster proof on Elder Care baseline (orchestrator M2 BundleBuilder is complete; legal roll-ups remain deferred)
```

```
Question:     Should legal agent adopt pytest guard for 10+ domain trace steps (5+5 retrieve/extract), or remain cluster-only per D4a waiver?
Impact:       tests/test_legal_contracts_agent.py, M2+ regression surface
Closes when:  M3 charter or auditor records decision on trace step-count falsifier
```

```
Question:     When should populate_bundle be removed vs retained indefinitely as demo-only?
Impact:       orchestrator module-map, public-interface-inventory, notebook fallback complexity
Closes when:  M3+ charter explicitly deprecates M1 demo path or documents permanent demo role
```

```
Question:     When should the legacy `databricks/agents/orchestrator/` duplicate folder be deleted?
Impact:       module-map, import confusion, stale self-references in deprecated copy
Closes when:  Confirmed no CI/notebook path imports from legacy folder; grep clean except git history
```

```
Question:     Should `set_pipeline_thread` be wired in PipelineOrchestrator._invoke for pipeline_thread_id attribution on DAG runs?
Impact:       known-coupling-surfaces pipeline_thread_id entry; ops manifest join queries
Closes when:  sqlite_removal.md debt item closed or explicitly deferred with falsifier
Note:         sqlite Phase 3 closed on store_backend=delta; pipeline_thread wiring still open per handoff docs.
```

```
Question:     G6 gold-label bootstrap for 8 new CQA/KPI retrieval intents — when to re-run elder_care.yaml bootstrap?
Impact:       intent_registry.yaml (57 intents), harness baseline compare, RegistryHashMismatchError risk
Closes when:  Operator completes GOLD_LABEL_BOOTSTRAP_HANDOFF.md procedure and promotes updated gold snapshot
Note:         elder_care.yaml reverted at hector-merge e2e stop; G6 explicitly deferred. Update 2026-08-20: gold_labels/ now covers all 57 intents for elder_care, clearsulting, gkf, spg via GoldLabelBootstrap CLI + company-scoped gold_exclusions.yaml — bootstrap mechanism itself is current, but whether the specific 8 hector-merge intents are fully clean in elder_care.yaml is unconfirmed.
```

```
Question:     Should Profiler be added to AGENT_REGISTRY or remain a separate pre-DAG job?
Impact:       DAG e2e freshness of company_profile; Profiler golden checklist vs pipeline run_id linkage
Closes when:  Product/operator decision on profiler-in-DAG vs manual Cell run
```

```
Question:     When (if ever) does the Rainmaker POC (run_vdr_rainmaker.py, vdr_rainmaker_poc.yml) move from manual/no-UI-trigger to a wired VDR UI path, and does it replace or coexist with the production run_vdr_pipeline.py (.docx) flow?
Impact:       databricks/workflows/vdr_rainmaker_poc.yml, VDR UI trigger wiring, companies_vdr_history last_updated_by convention, module-map dual-VDR-path note
Closes when:  Product decision on Rainmaker POC promotion path is made and documented; job name vs notebook path divergence noted in databricks/CLAUDE.md (job 617196299594076) is resolved
```

```
Question:     Should GKF and SPG (smoke-tier per eval/eval_program_playbook.md) receive full retrieval harness baselines in trust_statement.md before any promotion decision, or remain gold-label-only indefinitely?
Impact:       eval/retrieval/trust_statement.py e2e/agent_fields row derivation, eval/program/onboarding_queue.yaml wave sequencing, product_backlog.yaml scope
Closes when:  eval-multi-company-coverage-expansion (M5) charter or a successor explicitly schedules GKF/SPG retrieval baseline runs
```

```
Question:     Who owns lowering eval_debt.yaml's open_debt_high_water_mark as tracked debts close, and on what cadence?
Impact:       eval/program/eval_debt/eval_debt.yaml ratchet semantics, eval_debt.assert_ledger_ratchet gate behavior
Closes when:  Onboarding runbook or a program charter documents an explicit HWM review cadence/owner (currently a manual, undocumented field per exploration)
```
