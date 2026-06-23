# T4 — `retrieval.py` enhancements (B-W2/3/4/8)

**Subtask:** T4 (uc13-remediation-plan v1.0.1)  
**Date:** 2026-06-23

## Chosen approach

- **B-W2 filter pushdown:** `_query_vector_index()` passes `filters_json=json.dumps({"company_name": company_name})` to `query_index` when `company_name` is set. On SDK/index error, logs a message and retries without `filters_json` (packet kill criterion #3). Hydrate SQL still applies `c.company_name = ...` as defense-in-depth.
- **B-W3 score preservation:** `_extract_score_map()` reads the VS similarity score from the trailing column of each `data_array` row (SDK convention: requested columns + score). Hydrate SQL **removed** `ORDER BY r.priority_tier ASC NULLS LAST`.
- **B-W4 merge rank:** `_sort_by_merge_rank()` orders by `sim_score × tier_weight` with documented constants `_TIER_WEIGHT = {1: 1.0, 2: 0.7, 3: 0.4}` and `_DEFAULT_TIER_WEIGHT = 0.3` for `None`/unknown tiers. When no scores are available, falls back to tier-only ascending sort (pre-T4 hydrate behavior).
- **B-W8 SQL parameterization:** String literals escaped via `_escape_sql_literal()` (`'` → `''`) for `company_name`, chunk IDs, and keyword `LIKE` operands. `chunk_id IN (...)` built from per-id escaping. No `spark.sql(query, args)` — not used elsewhere in this module; escaping matches existing repo pattern.
- **`source_type_priority` interaction:** When `source_type_priority=True` and scores exist, sort key is `(-merge_score, source_type_order)` so FTA structured-chunk preference remains a tie-breaker within merge rank.
- **`_TYPE_ORDER` duplication:** Added `# TODO: consolidate with context_utils._TYPE_ORDER` per packet; deduplication deferred to a future subtask.

## Alternatives rejected

- **Wrap `semantic_search` return in `RouteResult`:** Rejected — contract binds `RouteResult` to T5 `context_utils.py` only; BMA/CQA/KPI/Legal/QoE/profiler consume raw `list`.
- **`use_merge_rank: bool` toggle on public signature:** Rejected — adds surface area to 8+ callers; tier-only fallback when `score_map` is empty provides safe degradation without a new parameter.
- **Push `workstream` / `priority_tier` filters to `filters_json`:** Rejected for T4 — VS filter dict syntax for array overlap and tier ranges is unverified on this workspace; `company_name` is the minimum required pushdown per packet.

## Assumptions made

- **T3 not confirmed complete in repo at execution time:** `setup_vector_search.py` `columns_to_sync` still lists only `chunk_id, doc_id, file_name, workstream, priority_tier` (no `company_name`). Live `status.ready` not polled in local executor environment. B-W2 code is landed with try/except fallback; full filter pushdown verification deferred to T3 completion + T7 E2E.
- **VS SDK returns similarity score as the last element** of each `data_array` row when querying with `columns=["chunk_id", "doc_id", "file_name"]` (Databricks SDK / `query_index` documented behavior).
- **`priority_tier` remains populated** via unchanged hydrate JOIN on `doc_relevance` — field shape unchanged for `build_focused_context` (T5 consumer).

## Merge rank weight rationale

Weights mirror remediation-plan tier semantics: Tier 1 (critical diligence) retains full similarity signal (1.0); Tier 2 dampened to 0.7; Tier 3 to 0.4; unknown/NULL tier uses 0.3 so high-sim low-tier chunks can still surface but rank below tier-1 matches. Chosen to preserve tier signal while letting strong semantic matches from Tier 2/3 outrank weak Tier 1 hits — the failure mode of pure `ORDER BY priority_tier` was discarding VS relevance entirely.

## Items deferred

- **Live VS filter pushdown verification** (`company_name` in index + non-empty filtered results): blocked on T3 `columns_to_sync` + re-sync; T7 E2E harness.
- **Adversarial test gap — `filters_json` accepted but index lacks `company_name` column, returning empty VS hits:** deferred to T7; mitigation is hydrate `company_name` SQL filter + keyword fallback path.
- **Spot-check before/after T4 on non-FTA callers (BMA/CQA):** deferred to T7 notebook; local pytest uses mocks only.
