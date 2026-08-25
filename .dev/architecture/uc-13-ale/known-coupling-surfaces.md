Section:      known-coupling-surfaces
Version:      1.5.0
Last updated: 2026-08-25

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
Landed (M4/W4 T12): twelve closed ids (4 pre-M4 + 8 M4); item count 21; gate test renamed `test_product_backlog_closed_row_set`; no `status` field
```

```
Surface:      Coupling Surface 1 — exec_summary claim_id → analysis-table evidence coverage (calibration.py vs spot_check.py)
Shared by:    eval/content/calibration.py:exec_claim_analysis_evidence ↔ eval/content/spot_check.py:_exec_claim_source_from_cache / _EXEC_TOP10_RANK_MAP / _ELDER_CARE_STATIC_CLAIM_SOURCES
Failure mode: Selecting a source_extension claim that spot_check resolves to a (source_doc, source_location) but exec_claim_analysis_evidence has no matching branch silently downgrades that claim from dual-source (analysis-table + chunk-RAG) to chunk-RAG-only inside run_calibration, with no error
Confirmed:    yes — re-read at T5 from landed files (spot_check.py / calibration.py were frozen-adjacent this wave; T2 added none of these ids)
Landed (M3/T5 verification):
  Gap set (no exec_claim_analysis_evidence branch and not in _EXEC_TOP10_RANK_MAP): {exec.claim.029, 030, 031, 032, 033, 034, 037, 046, 047}.
  Dual-source-covered 16-claim set (source_extension ids that ARE keys of _EXEC_TOP10_RANK_MAP at spot_check.py:435–454): {035, 036, 038, 039, 040, 041, 042, 043, 044, 045, 048, 049, 050, 051, 052, 053}.
  Notes: 037 is in _ELDER_CARE_STATIC_CLAIM_SOURCES (spot_check.py:432) so exec_claim_source may still return a static (source_doc, source_location), but exec_claim_analysis_evidence leaves payload None — 037 is in the gap set. Rank 1 in _EXEC_TOP10_RANK_MAP is exec.claim.038, not 037. 031/034 are grouped with 011/013 in _exec_claim_source_from_cache (spot_check.py:490) but have no calibration.py analysis-table branch. 032/033 and 046/047 have spot_check branches (lines 521–524 and 511–517) and no calibration.py branch.
  T2 added zero members of the 16-claim set (P3 already met at 13 distinct chunk ids; N stays 28). Consistent with T4 wave note claim_count=28 and T2 honest-instrument P2 fail on the rebalanced sample.
```

```
Surface:      Stale skip-guard comment on tracked exec_summary sample parity test
Shared by:    eval/content/tests/test_exec_summary_spot_check_rubric.py:74–79 (test_calibration_sample_ids_001_028_match_rubric_verbatim) ↔ SAMPLE path at line 15 (`eval/content/calibration_samples/calibration_sample_exec_summary.yaml`)
Failure mode: A reader of the skip message ("operator-local (gitignored .dev/ per Option C)") could think the parity test is skipped on a fresh clone; if SAMPLE were absent the test would skip and the gate could report green without checking claim-text parity
Confirmed:    observation only this wave (file not in M3 Files to touch; not edited)
Landed (M3/T5): SAMPLE is git-tracked (`git ls-files` lists the yaml). The skip at line 75 (`if not SAMPLE.exists()`) does not fire on a clean checkout. T4 wave note: the stale skip-guard did not fire; the parity test PASSED in the 128-test gate. T5 clean-checkout must show the same parity test in the worktree passed counts (packet C4). Comment text is stale; behavior is fail-open only when the file is missing, which a clean checkout does not do.
```

```
Surface:      M3/W1 declared-scope sweep + clean-checkout (T5 verification)
Shared by:    plan Files-to-touch union (T1–T4 tracked code/data) ↔ working tree vs 78f303e
Failure mode: Tracked edits outside the declared code/data union, or a green in-tree gate that fails on a clean checkout (gitignored-input dependence)
Confirmed:    T5 kill criteria (a)(b) — results below
Landed (M3/T5 sweep at T4 HEAD `f04d592`, re-checked after T5 CHANGELOG commit):
  git diff --stat 78f303e..HEAD tracked paths: CHANGELOG.MD; eval/content/agreement.py; eval/content/calibration.py; eval/content/calibration_samples/calibration_sample_exec_summary.yaml; eval/content/tests/test_agreement.py; eval/content/tests/test_calibration_sample_power.py.
  Code/data union honored: those five eval/content paths. CHANGELOG.MD is the executor-skill required emission (T1 `214d5a7`, T2 `d8f490c`, T3 `f96fda8`, T4 `f04d592`, plus this T5 commit) — recorded, not treated as a sixth code/data file.
  Exclusions (git log 78f303e..HEAD empty on each, then excluded by name): pre-existing dirty `databricks/jobs/notebooks/test_pipeline.ipynb` (`git status --porcelain` shows ` M`; last commits on the path are `e3ce0bd` / `347c448` / `22d91f4`, all before 78f303e); untracked/gitignored `eval/retrieval/reports/ablation_*.json` and `baseline_*.json` (`.gitignore:235`; `git log 78f303e..HEAD -- eval/retrieval/reports/` empty; not in porcelain).
  T5 Files to touch (D10): `.dev/architecture/uc-13-ale/{module-map,public-interface-inventory,data-contract-registry,known-coupling-surfaces}.md` remain in the index from M2 T6 (`78f303e`, `git ls-files` lists them despite `.gitignore` `.dev/`). T5 edits them and leaves them uncommitted per packet D10. Porcelain ` M` on those four paths is this subtask's documentation working tree, not a code/data-union path.
  Clean-checkout counts: filled after the T5 CHANGELOG commit (see block below).
```

## M3/W1 T5 clean-checkout verification

Procedure: after this subtask's tracked `CHANGELOG.MD` commit `bab8f7a7cb5edc4ae1feec90a67d226d147be0e2`, detached git worktree at that SHA (`C:\Users\AlejandroGaray\Documents\Repos\uc-13-ale-t5-m3-verify`); `python -m pytest eval/content/tests/ -q`. Import path confirmed as the worktree (`eval.content.agreement.__file__` = `...\uc-13-ale-t5-m3-verify\eval\content\agreement.py`). Expected = in-tree 128 (T4/T5) + T5 net new tests (none).

- In-tree (pre-commit, T5 added no tests): `128 passed in 2.10s`; collected 128; failed=0; skipped=0; errors=0; exit 0
- Worktree at `bab8f7a7cb5edc4ae1feec90a67d226d147be0e2`: `128 passed in 2.38s`; collected 128 (`128 tests collected in 1.63s`); failed=0; skipped=0; errors=0; exit 0
- Rubric parity `test_calibration_sample_ids_001_028_match_rubric_verbatim`: collected in the worktree 128; targeted re-run **PASSED**; did not skip (stale guard at line 75 did not fire)
- No in-tree vs worktree divergence (kill criterion b did not fire)

```
Surface:      chunk_id UUID vs gold/calibration/spot-check pins (FU-M4-PINKEY)
Shared by:    ingestion_parser.py (`uuid.uuid4()` per parse) ↔ elder_care.yaml ↔ calibration_sample_fta_numeric.yaml ↔ spot_check.py LOCATION_CHUNK_OVERRIDE ↔ T6 mapping artifacts
Failure mode: Every CIM re-parse mints new ids; pins dangle unless remapped. Durable fix is a stable semantic locator — out of M4 (new architectural fork)
Confirmed:    yes — T6 re-parse; T6-quater 72-entry mapping; T7-bis / T8 refresh
```

```
Surface:      legal_register_verifier.py charter boundary (H8 / D-M4-B)
Shared by:    eval/content/legal_register_verifier.py (M4 T5 cascade) ↔ charter M8/W5 documented non-hub
Failure mode: M8 plans against the charter's M8-only classification and silently reverts T5's locator cascade
Confirmed:    yes — D-M4-B; T13 wave-note Tier-2 charter note + M8 handoff warning
```

```
Surface:      fallback.py vs_metadata_filters additive default (H10)
Shared by:    agents/shared/fallback.py ↔ legal_contracts_agent.py (ip_privacy True) ↔ BMA / context_utils delegator (must keep default False)
Failure mode: A non-default value on a non-legal caller silently pushes workstream_filter into that caller's ANN query
Confirmed:    yes — T4-bis; context_utils.semantic_search_with_fallback does not pass vs_metadata_filters
```

```
Surface:      C13 six-failure baseline (FU-M4-GATE)
Shared by:    python -m pytest eval/retrieval/tests eval/content/tests -q ↔ committed calibration samples / registry / exemptions / gold snapshot / excel-tab tests
Failure mode: Reporting the suite as green hides the six pre-M4 failures; a seventh failure is an M4 halt
Confirmed:    T13 in-tree run 2026-08-21: 6 failed, 622 passed, 1 skipped — same six names as §2 C13
```

```
Surface:      M4/W4 declared-scope sweep + D-M4-F pin regime
Shared by:    plan Files-to-touch union (incl. R4–R6 amendment files) ↔ working tree vs bab8f7a7 ↔ gitignored .dev/ evidence
Failure mode: Tracked edits outside the reconstructed union, or evidence refs without content-SHA pins
Confirmed:    T13 kill criteria — results in the M4 wave note and plan §8.1
Landed (M4/W4 T13 sweep at T12 HEAD `8e7c0619`, re-checked after this closeout commit):
  git diff --name-only bab8f7a7..HEAD tracked paths (15): CHANGELOG.MD; databricks/agents/shared/fallback.py; databricks/agents/subagents/workstream/financial/revenue_sub_agent.py; databricks/agents/workstreams/legal_contracts_agent.py; eval/content/calibration.py; eval/content/calibration_samples/calibration_sample_fta_numeric.yaml; eval/content/legal_register_verifier.py; eval/content/spot_check.py; eval/content/tests/test_legal_register_chunk_resolver.py; eval/program/product_backlog.yaml; eval/retrieval/fixtures/elder_care_slice.json; eval/retrieval/fixtures/gold_positive_counts.yaml; eval/retrieval/gold_labels/elder_care.yaml; eval/retrieval/tests/test_product_backlog_schema.py; tests/test_revenue_sub_agent.py.
  Packet T13 printed union was the original-plan snapshot. Extras vs that snapshot, all declared on the plan: fallback.py (T4-bis), gold_positive_counts.yaml (T7-bis), calibration_samples/calibration_sample_fta_numeric.yaml (T8 actual path), test_legal_register_chunk_resolver.py (T5 §2.2), tests/test_revenue_sub_agent.py (T2 §2.2).
  C15 frozen-path git diff bab8f7a7..HEAD empty on eval_debt, non-Elder gold, tracked signoffs, slices (no tracked slice files).
  Exclusions: pre-existing dirty `databricks/jobs/notebooks/test_pipeline.ipynb` (git log bab8f7a7..HEAD empty); untracked `eval_next_steps.md` not staged.
  Architecture four files were already index-tracked despite `.gitignore` `.dev/`; T13 commits the M4 refresh (and the previously uncommitted M3/W1 T5 prose already on disk).
  INDEX.md / architecture changelog.md were not in T13 Files to touch — versions in INDEX.md remain 1.0.0 / Last verified 2026-08-03 (discrepancy flagged, not edited).
```

```
Surface:      Promotion / e2e_linkage / golden-checklist agent-id vocabulary (`LCA` directory vs `legal` CLI/code vs `Legal` spec-prose), plus the `DeltaEvalStore` catalog default on this write path
Shared by:    `eval/LCA/` (directory) ↔ `eval/retrieval/scripts/record_e2e_linkage.py` argparse `--e2e-agent-id` `choices` ↔ `.dev/g1_score_all_agents.py` `_AGENTS` tuple / `BASELINES[...]` keys ↔ golden-checklist `rubric source` headers (`score_legal()`) ↔ `eval/program/promote_w2a_clearsulting.py` (`LEGAL_AGENT_ID`). Catalog call site only: `DeltaEvalStore.__init__` — cross-reference **Catalog name split** (top of this file); do not restate that surface.
Failure mode: An executor pattern-matching the directory name would pass `--e2e-agent-id lca` (rejected by argparse `choices`) or look up `BASELINES[...]["lca"]` (`KeyError`). Omitting `catalog=` at `DeltaEvalStore(...)` on this path applies **Catalog name split** to promotion evidence (constructor default is production).
Confirmed:    yes — argparse `choices` and `_AGENTS` both use `"legal"`; directory is `eval/LCA/`. Identified, not yet triggered as a live defect.
Landed (M5/T5): T5 job `370562481484117` (`eval/program/promote_w2a_clearsulting.py`) did not hit either failure mode. Frozen `record_e2e_linkage` used `e2e_agent_id='legal'` (HarnessRun and `ops.e2e_linkage` row); post-check `n=7` for `run_id='6e1b4f5d95284b33bbd08942b3595dd6'` is `bma` 7/7, `cqa` 4/6, `fta` 17/18 (pre-existing, `linked_at` 2026-08-18 unchanged), `kpi` 0/3, `legal` 0/11 (`linked_at` 2026-08-24T21:00:30.580Z), `profiler` 5/7, `qoe` 4/6 — no `lca` key. Cluster driver constructed `DeltaEvalStore(spark, catalog="uc13_ale")` explicitly; HarnessRun `catalog='uc13_ale'`. A prior submit (`168063648078361`) failed at import before any write and did not exercise these modes.
```

[needs confirmation] — additional coupling surfaces from operator knowledge welcome via interview.
