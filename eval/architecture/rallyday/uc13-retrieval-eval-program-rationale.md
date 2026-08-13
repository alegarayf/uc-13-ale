# UC13 Retrieval Eval + Enhancement — Program Rationale

**Produced:** Phase 1 · Step 1 (Idea Orchestrator Genesis)  
**Updated:** 2026-07-01 (spec v0.1.12 — cycle 8: normative `ingestion_snapshot` value, `gold_snapshot` canonical JSON required for all backends; cycle 7: `basis_conflict@k` gate direction, cross-run comparability pins, `gold_snapshot` hash algorithm)  
**Spec:** `.dev/specs/retrieval/uc13-retrieval-eval-enhancement-spec.md`

---

## Design intent

RT7 closed route architecture: Route B (`semantic_search` + merge-rank) is production for all agents. This program builds **platform retrieval measurement** (~50 intents) and **gated enhancement** — not another route experiment.

The problem is not "which retrieval route wins" but "can we prove the right chunks reach each intent, gate changes on measured delta, and fix known failures (OPEX basis mismatch) without reopening RT7." Eval data is **organic** (real Elder Care chunks in `uc13_ale`), with **intent-scoped positive and rule-derived negative labels**. We do not fabricate a synthetic mock corpus. CI uses a **frozen slice** of real chunk rows with mocked VS/embed only.

---

## Key tensions surfaced

### Eval data

**Positives only vs positives + negatives**

- **Options:** Recall-only with positives; positives + complement negatives (all non-gold chunks); positives + rule-derived hard negatives.
- **Chosen:** Positives + rule-derived hard negatives (`basis_rule`, `section_rule`, `cross_intent_positive`, `bad_run_replay`).
- **Why:** Recall-only missed OPEX basis regression (Projection chunks ranked highly for historical intents). Complement negatives (~35K chunks) produce unusable precision signal.

**Synthetic mock docs vs organic DB**

- **Options:** Invented chunk text + parallel test index; organic `uc13_ale` corpus; hybrid (organic + synthetic edge cases).
- **Chosen:** Organic corpus + frozen fixture export (`elder_care_slice.json`) for CI; mock VS/embed only.
- **Why:** Eval must reflect real VS hydrate, merge-rank, and metadata behavior — synthetic text hides index and join failures.

**Agent-wide vs per-intent labels**

- **Options:** One gold set per agent; per-intent positives/negatives.
- **Chosen:** Per-intent — same physical chunk may be positive for `fta.opex.q3_projected_financials` and negative for `fta.opex.q1_financial_statements`.
- **Why:** Basis conflicts are intent-scoped, not agent-scoped; agent-wide labels would false-pass wrong-basis ranking.

**Recall-only vs precision/basis metrics**

- **Options:** Recall@k only; classical positive-label precision; negative-free rate + `basis_conflict@k`.
- **Chosen:** Recall@k + negative-free rate@k (field: `precision_at_10`) + `basis_conflict@k` where negatives defined.
- **Why:** Hard-negative metrics catch wrong-chunk-in-top-k without requiring full positive coverage; classical precision needs complete positive labeling we do not have.

**@k denominator semantics (cycle 5 — D7)**

- **Options:** Fixed denominator `k=10` with unfilled slots as non-negative (vacuous slots improve scores); `effective_k = min(eval_k, result_count)` with omission when `result_count == 0`.
- **Chosen:** `eval_k = min(10, intent.top_k)`; `effective_k = min(eval_k, result_count)`; omit `precision_at_10` / `basis_conflict_at_10` when `result_count == 0` or negatives undefined. Retrieval invoked with registry `top_k` (production-faithful).
- **Why:** Fixed-k denominators inflate precision/basis when retrieval under-fills or returns zero results — false gate pass on OPEX basis intents. Field names stay `*_at_10` for continuity; `eval_k` on `HarnessResult` records actual depth.

**Vacuous gate scope (cycle 5 — D9)**

- **Options:** `gate_pass: true` when `gated_intents == []` (vacuous AND); `gate_pass: null` with operator waiver required.
- **Chosen:** `null` — enhancement merges fail without documented waiver; triggers D9 revisit when majority bootstrap_failed.
- **Why:** PR gate must not approve with zero evaluated recall evidence.

**Cross-run comparability pins (cycle 6–7 — D8)**

- **Options (cycle 6):** Write `gold_snapshot` to manifest only; enforce at `compare()` with HALT; auto-invalidate and require re-baseline; recompute current metrics against baseline gold at compare time.
- **Chosen (cycle 6):** `compare()` HALTs with `GoldSnapshotMismatchError` when baseline and current `gold_snapshot` differ — operator override requires documented forced re-baseline. `EvalStore.append_provenance()` as sole provenance write path for harness and pipeline.
- **Options (cycle 7):** Enforce only `gold_snapshot`; add `registry_hash` + `ingestion_snapshot` at `compare()`; document mandatory re-baseline on registry/corpus change without compare assertion.
- **Chosen (cycle 7):** Extend `compare()` pins to **`registry_hash`** (`RegistryHashMismatchError`) and **`ingestion_snapshot`** (`IngestionSnapshotMismatchError`) — same forced re-baseline override pattern as gold. Normative `gold_snapshot` = SHA-256 over canonical JSON of sorted `GoldLabel` rows (YAML and Delta paths).
- **Options (cycle 8):** Leave `ingestion_snapshot` computation to implementer discretion (first row / max timestamp / hash) with `GoldLabel.ingestion_snapshot` optional; define a normative company-level algorithm and make the field required; allow a Delta table-version shortcut for `gold_snapshot` without a cross-backend equivalence guarantee.
- **Chosen (cycle 8):** `ingestion_snapshot` is a single company-level value (`"{catalog}:{chunk_count}:{ingestion_date}"`), computed once at Cell 7 completion and written identically to every `GoldLabel` row; `EvalHarness.run()` HALTs with `PreconditionError` if loaded rows disagree. `gold_snapshot` canonical JSON SHA-256 is required for **all** backends in v1 — the Delta table-version shortcut is removed until a normative cross-backend equivalence test exists (deferred, M-RE4+).
- **Why:** Label, registry, or corpus drift between baseline and enhancement masquerades as retrieval delta — merge gates false-pass or false-fail. Manifest pins must be enforced at comparison for all three dimensions, not only labels. An optional, per-row `ingestion_snapshot` let two implementers derive incompatible manifest values from the same gold store; a Delta-only hash shortcut for `gold_snapshot` let a YAML baseline and a Delta enhancement diverge on identical label content — both defeat the pin's purpose of isolating retrieval delta from label/corpus drift.

**MRR gate surface (cycle 6 — D7)**

- **Options:** Include MRR in `intent_gate_pass` AND; remove MRR from `HarnessDelta.metric`; keep MRR deltas audit-only.
- **Chosen:** Audit-only — `HarnessDelta` rows with `metric: mrr` excluded from `intent_gate_pass` AND; recall + precision/basis remain gate metrics.
- **Why:** MRR is useful for diagnosis but was never part of PR merge policy; including it in delta enum without gate aggregation created implementer ambiguity.

**`basis_conflict@k` gate direction (cycle 7 — D7)**

- **Options:** Treat `basis_conflict_at_10` as higher-is-better (same as recall/precision); invert metric to `1 - conflict_rate` and rename field; lower-is-better non-regression (`after <= before`).
- **Chosen:** Lower-is-better — `basis_conflict_at_10` measures conflict rate in top-k; gate passes when `after <= before` (equivalently `delta <= 0`). Per-metric direction table on `HarnessDelta` prevents reintroduction.
- **Why:** Higher conflict rate means more basis negatives in top-k — the primary OPEX regression signal (RT7 field 9 / L3.context_basis_mismatch). Applying `≥ baseline` inverted the program's core gate and would approve merges on basis degradation.

### Program scope

**Platform harness vs FTA-only eval (D1)**

- **Options:** FTA-only (route experiment scope); per-agent separate harnesses; single platform harness with agent partitions.
- **Chosen:** Single harness, ~50 intents partitioned by `agent_id`.
- **Why:** FTA was the RT7 experiment target, not the platform boundary; retrieval bugs in profiler/BMA/Legal affect downstream agents. Revisit if registry exceeds ~100 intents without audit automation.

### OPEX basis without exclusion (D3)

**Options:** Denylist Projection/Forecast chunks at retrieval; retrieval-only ranking fix; extraction prompt only; separate per-query budgets (C) + labeled sections (A) + post-extraction cross-check (D); ingest `section_class` boost (B).

- **Chosen:** C + A + D always for FTA OPEX; B only if harness shows cross-intent conflicts beyond OPEX.
- **Why:** User constraint rejects chunk-type exclusion — projection data must remain retrievable for forward-looking intents. Pooling all OPEX queries into one budget caused basis mismatch on field 9 (`1st_run.md`). Assembly + validation fixes the failure mode without hiding data.

### Merge-rank as production default (D4)

- **Options:** Pure similarity; pure tier (Route A); `sim × tier_weight` hybrid (Route B / T4).
- **Chosen:** `sim × tier_weight` remains default; pure sim and pure tier are ablation arms only.
- **Why:** RT7 committed Route B; tier-only failed categorically on Elder Care (1/18 FTA). Revisit only if ablation shows tier-only wins aggregate recall.

### Two-layer eval gates (D5)

- **Options:** Harness-only; E2E-only; harness gates retrieval code + E2E checklists gate production output.
- **Chosen:** Two-layer — harness for retrieval boundary; per-agent golden checklists (FTA 18-field, Legal 11-item) for production output.
- **Why:** Layers measure different things; recall gain can coexist with extraction regression. Not reversible without losing attribution.

### Enhancement ordering (D6)

- **Options:** Complete R-01–R-11 hardening before any eval; eval before any code change; structured API return in observability milestone (M-RE2) after harness (M-RE1).
- **Chosen:** M-RE1 includes `RouteResult` return (`mode` + `scores`) **before** first harness baseline; M-RE2 provenance emitter + FTA context assembly; M-RE3 VS/filter hardening gated on G-B1 spike + harness delta; M-RE4 enrichment on plateau.
- **Why:** Harness cannot observe fallback-rate or mode without production API contract — scheduling API change after harness produced false confidence (Phase 2 HALT). Measurement and API shape are co-requisites for M-RE1, not sequential across milestones.

### Retrieval execution mode vocabulary (Phase 2 absorption)

- **Options:** Three incompatible vocabularies (`vector`/`keyword`/`empty`, `semantic`/`keyword`/`routed`/`empty`, `routed`/`semantic`/`keyword_fallback`); dual-field model (`retrieval_mode` + `execution_mode`).
- **Chosen:** Single canonical `retrieval_execution_mode`: `semantic | keyword | routed | empty` on `RouteResult`, provenance, and harness; registry retains separate caller-intent `retrieval_mode` (`semantic | routed`).
- **Why:** Fallback-rate rollups and provenance aggregation require one string per runtime state; alias map handles legacy emitters without splitting fields everywhere.

### Eval persistence and attribution (D8)

- **Options:** Git JSON reports only; separate eval catalog per company; Delta-only cluster store; local SQLite only; `uc13.ops` Delta + SQLite mirror + one-way sync.
- **Chosen:** `uc13.ops.retrieval_harness_*` + `retrieval_provenance` as canonical; dual-write `HarnessReport` JSON for PR/git; local SQLite (`eval/retrieval/.local/re2_store.sqlite`) for fast iteration; `sync_eval_store.py` promotes local runs to Delta. E2E snapshots stay in `{catalog}.analysis.financial_trends_eval_snapshot` (RT7) — linked via `HarnessRun.e2e_*`, not merged into harness tables.
- **Why:** "What changed what" requires queryable `run_id` lineage across metrics, provenance, and optional extraction checklists. Corpus (`uc13_ale`) and ops metadata (`uc13.ops`) stay separated.

### Gate-eligible vs registered intents (D9 — cycle 3)

- **Options:** Block `retrieval.py` merges until all ~50 intents bootstrap; remove failed intents from registry; invoke all registered intents but gate only gold-ready subset.
- **Chosen:** Harness runs all **affected** registered intents; merge gates apply to **gate-eligible** intents only (`gold_status` not `bootstrap_failed`). Skipped intents get `eval_status: skipped_bootstrap_failed` — attribution without fabricated recall.
- **Why:** Citation backfill will fail for some intents on first Elder Care baseline; blocking global retrieval hardening on every bootstrap gap would stall M-RE1. Gates must not divide by zero or force fake metrics.

---

## Architectural commitments

1. Route B production; `route_chunks` eval-only.
2. Two-layer eval (harness + E2E checklists where they exist).
3. Elder Care `uc13_ale` reference corpus; same-catalog A/B only.
4. Provenance mandatory on retrieval changes (`{intent_id, chunk_id, score, rank, mode}`); `semantic_search` returns `RouteResult` with canonical `mode` + `scores` — **M-RE1 gate, not deferred**.
5. No chunk-type exclusion at retrieval — basis via assembly (C+A) + post-check (D).
6. Intent-scoped `positive_chunk_ids` + `negative_chunk_ids` from programmatic bootstrap.
7. `eval/retrieval/fixtures/elder_care_slice.json` for CI — real rows, mocked VS/embed.
8. Merge-rank `sim × tier_weight` as production default; ablation before algorithm change.
9. Per-intent harness gates — aggregate rollups for reporting only, not merge approval. **PR gate uses `intent_gates` AND rollup** across recall + precision/basis where fields present (omitted metrics excluded, not vacuous pass). **`basis_conflict_at_10` is lower-is-better** — gate passes on `after <= before`, not `≥ baseline`.
10. Minimal blast radius — enhance `retrieval.py` and shared wrappers; agent-specific changes only where context assembly requires (FTA first).
11. **Eval attribution store** — every harness run writes `HarnessRun` manifest + results to `uc13.ops` (and optional SQLite locally); deltas vs `baseline_ref_run_id`; provenance via `EvalStore.append_provenance()`; E2E snapshots linked, not merged. Manifest persists `affected_intents` + `gated_intents` for queryable gate scope (D8). **`compare()` enforces `gold_snapshot`, `registry_hash`, and `ingestion_snapshot` equality** — label, registry, or corpus drift without re-baseline cannot produce merge gate signal. `gold_snapshot` uses canonical JSON SHA-256 for **all** backends (no Delta shortcut in v1); `ingestion_snapshot` is a single company-level value computed once at Cell 7 completion — `EvalHarness.run()` HALTs if loaded `GoldLabel` rows disagree.
12. **Gate-eligible scope** — `bootstrap_failed` intents are harnessed for attribution but excluded from `gated_intents` and merge approval; global `retrieval.py` changes gate on gate-eligible partition only. **`gate_pass: null`** when zero gate-eligible intents — no vacuous merge approval.
13. **Metric evaluation depth** — harness invokes retrieval with registry `top_k`; metrics computed at `eval_k = min(10, top_k)` with `effective_k` denominators per §5.8 — production-faithful invocation, comparable cross-intent scoring cap.
14. **MRR audit-only** — `HarnessDelta.metric: mrr` rows are traceability detail; PR gates use recall + precision/basis via `intent_gates` only.
15. **`compare()` gate golden tests** — `compare_gate_cases.yaml` CI kill criterion on `EvalHarness.compare()` aggregation; prevents structurally valid but semantically inverted gate logic.

---

## Explicitly rejected approaches

| Rejected | In favor of | Why | Revisit if |
|----------|-------------|-----|------------|
| Route A (`route_chunks`) production | Route B `semantic_search` | 1/18 FTA on Elder Care; RT7 closed | Never for batch diligence |
| Route C ReAct adaptive loop | Fixed intents + harness | Batch scope; cost; determinism | Interactive Q&A product |
| Chunk-type exclusion (Projection denylist) | Separate budgets + labeled sections | User constraint; preserves forward-looking data | — |
| FTA-only eval scope | Platform intent registry | FTA was experiment target, not boundary | — |
| Catalog-mixed A/B (`uc13` vs `uc13_ale`) | Same-catalog `uc13_ale` | Documented confound in `1st_run.md` | — |
| Synthetic invented chunk corpus | Organic + frozen fixture | Does not reflect real VS/hydrate behavior | — |
| Complement negatives (all non-gold) | Rule-derived hard negatives | ~35K noise; unusable precision signal | — |
| Recall-only harness | Recall + negative-free rate + basis_conflict | Misses OPEX basis / wrong-chunk-in-top-k | — |
| Manual hand-label all ~50 intents | Programmatic bootstrap + audit sample | Citations exist in DB | Bootstrap fails for majority |
| Cross-encoder rerank before ablation | Merge-rank ablation first | Cost without measurement | Ablation gap proven |
| E2E-only retrieval tuning | Two-layer eval | Cannot attribute chunk misses | — |
| Harness-only wrapper duplicating fallback detection | `RouteResult` from `semantic_search` | Fragile divergence from production path; false mode in baseline | Never as sole measurement path |
| M-RE1 baseline without structured API return | API change in M-RE1 before harness | Phase 2 HALT — fallback-rate gates non-functional | — |
| Git-only harness metrics (no ops tables) | `uc13.ops` dual-write | No SQL attribution across runs | — |
| Block global retrieval merge until all intents bootstrap | Gate-eligible subset only (D9) | Citation gaps are expected; fabricated metrics worse than excluded denominators | Majority bootstrap_failed after M-RE1 |
| Fixed `k=10` metric denominators with unfilled slots as non-negative | `effective_k = min(eval_k, result_count)`; omit precision/basis at `result_count == 0` | Inflates scores on under-filled or empty retrieval; false OPEX basis gate pass | — |
| Vacuous `gate_pass: true` on empty `gated_intents` | `gate_pass: null` + operator waiver | Zero evaluated recall evidence must not auto-approve merge | — |
| `compare()` without `gold_snapshot` check | `GoldSnapshotMismatchError` + forced re-baseline override | Label drift masquerades as retrieval delta | — |
| `compare()` without `registry_hash` / `ingestion_snapshot` check | `RegistryHashMismatchError` / `IngestionSnapshotMismatchError` + forced re-baseline | Registry or corpus drift masquerades as retrieval delta | — |
| Per-row / aggregated `ingestion_snapshot` derived from `GoldLabel` rows at compare time | Single company-level value computed at Cell 7 completion, copied to all rows | Optional per-row field let implementers derive incompatible manifest values (first row, max timestamp, hash) | — |
| Delta table-version `gold_snapshot` shortcut without cross-backend equivalence test (v1) | Canonical JSON SHA-256 for all backends | YAML-path and Delta-path runs would produce incompatible `gold_snapshot` for identical label content | Equivalence test implemented + Delta-exclusive gold store (M-RE4+) |
| `basis_conflict@k` as higher-is-better gate (`≥ baseline`) | Lower-is-better non-regression (`after <= before`) | Inverts OPEX basis regression gate — approves merges when conflict rate rises | — |
| Direct SQL / divergent provenance write paths | `EvalStore.append_provenance()` only | Harness and pipeline must share one contract | — |
| Delta → SQLite sync | One-way sqlite → delta only | Cluster is canonical; reverse sync causes drift | Local-only dev sufficient |

---

## Deferred

| Item | Trigger |
|------|---------|
| `bad_run_replay` negative automation | Manual freeze from provenance top-3 sufficient initially; after harness provenance stable |
| Expand fixture to >5 intents | M-RE1 cluster baseline stable |
| `section_class` for negative rules (Option B) | Harness cross-intent conflicts beyond OPEX; basis_rule regex insufficient |
| `retrieval_harness_*` BI dashboards | SQL views sufficient for v1 |
| Contextual prefix at ingest | Recall plateau after M-RE3 |
| Cross-encoder rerank / BM25 hybrid | >5pt Recall@10 gap post-ablation |
| Multi-company gold labels | Second company onboarded |
| BMA context char budget | BMA harness shows context overflow |
| Provenance-replay gold method | After first provenance-enabled full run |
| Roll context assembly to non-FTA agents | FTA E2E pass + harness stable |
