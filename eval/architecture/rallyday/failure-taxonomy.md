Section:      failure-taxonomy
Version:      1.4.0
Last updated: 2026-07-28

**Layer framework:**

```
L0  Input integrity   — failures attributable to input data before any processing begins
L2  Model behavior    — failures in model output relative to the prompt
L3  Output validation — failures in structural or semantic validity of output
L5  Infrastructure    — failures in external systems or environment
```

**Additional layers:** none declared.

```
Taxonomy version: 1.4.0
Last updated:     2026-07-28

L0.retrieval_wrong_document_set — Metadata or keyword routing selects chunks from the wrong subsidiary, period, or document class for the target company. Evidence: RT7 Route A on Elder Care returned Guided Living 2022 subsidiary monthly P&L (1/18 golden fields). **Route A removed M-RE1 T3** — class retained for historical RT7 evidence only.

L3.context_basis_mismatch — Retrieved chunks are structurally valid but mix accounting bases (e.g. pro forma vs historical reported), causing field-level extraction errors. Evidence: RT7 field 9 payroll COGS — T4 merge-rank shifted OPEX context to Pro Forma IS ($26,197) vs Control Historical P&L ($20,290). Partial mitigation: M-RE2 `basis_cross_check` + OPEX labeled context; ranking fix still open.

L3.bundle_validation_failure — Orchestrator bundle fails jsonschema validation against orchestrator_bundle.schema.yaml. Evidence: BundleValidationError raised by validate_bundle; Cell 19 HALT path in notebook.

L3.tldr_dict_leakage — Rendered TL;DR markdown contains Python dict repr (e.g. `{'kpi_name': ...}`) instead of human-readable diligence text. Evidence: pre-T8 KPI missing-KPI bug; tldr_quality_check._check_dict_leak gate; fixed by routing dict entries through format_diligence_entry.

L5.vector_search_degraded — Vector Search unavailable, filter pushdown rejected, or index column missing; system falls back to unfiltered VS or keyword LIKE search. Evidence: retrieval.py try/except on filters_json; T1 M-RE3 probe attested PASS on Elder Care (all filters_json candidates sdk_accepted).

L5.delta_concurrent_write — Concurrent Delta MERGE/UPDATE transactions on shared provenance table raise ConcurrentAppendException or corrupt rows via shared temp views. Evidence: M-RE2 FTA ThreadPoolExecutor wet-run; fixed by contextvars propagation, retry_on_delta_conflict, batched patch MERGE, and _provenance_write_lock.

L5.genie_unavailable — Genie API returns FAILED status or credentials missing. Evidence: GenieRulesError → HTTP 502 in backend-ai.

L2.llm_output_truncation — Model output exceeds token cap; JSON/schema incomplete. Evidence: databricks/CLAUDE.md documents Sonnet vs Haiku caps; financial_trends_agent uses explicit max_tokens overrides.

L3.invalid_python_function — Model-generated python_function.source fails ast.parse. Evidence: response_parser ParseError guard.

L5.sqlite_provenance_fallback — ThreadPoolExecutor worker inherits SqliteEvalStore via resolve_store() when open_agent_run called without spark= on cluster; FTA sub-agent pool then crashes with ProgrammingError. Evidence: sqlite_removal.md; fixed 2026-07-27 with spark= injection + fail-closed resolve_store.

L2.extraction_truncation_haiku — Haiku/Llama 8192 output cap silently truncates large JSON extraction schemas; tail fields empty in Delta. Evidence: BMA R-1 post_merge_regressions.md; Sonnet override + max_tokens=16_000 remediation.

L3.flags_json_string — Delta flags column read as dict without json.loads when SQL returns serialized JSON string. Evidence: BMA generate_business_model_assessment R-3 crash; json.loads guard added.

L3.promotion_regression — Golden checklist score drops below prior e2e baseline; evaluate_promotion returns promotion_blocked. Evidence: M3 test_promotion_gate.py; scorecards in .dev/scorecards/.
```

Code-observed failure modes not yet registered as cause classes:

| Observed / anticipated | Likely layer | One-line description |
|------------------------|--------------|----------------------|
| Genie returns plain text instead of JSON | L2 / L3 | `ParseError` in response_parser |
| Databricks SQL connection / missing catalog | L5 | Health check or query throws |
| Session deny limit exceeded | L0 | HTTP 409 on deny endpoint |
| Provenance emit with no open agent run | L5 | Silent no-op unless RE2_PROVENANCE_REQUIRED=1 |
| Ablation alt-arm recall collapse under broken merge-rank | L0 | Expected gate_fail on merge_rank_off/sim_only/tier_only vs production default (M-RE3 attestation) |
