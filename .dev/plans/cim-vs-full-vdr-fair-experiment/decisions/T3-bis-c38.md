# Decision log — T3-bis C38

**Subtask:** T3-bis
**Tier:** architectural
**Date:** 2026-08-25

## Chosen approach

Rebalance C37's two literal field-group lists in `business_model_agent.py` by moving `customer_operational_metrics` from the commercial call (7→6 fields) to the organizational call (8→9 fields). C37's routing predicate (`_use_two_pass = len(combined_chunk_text) > _TWO_PASS_CONTEXT_CHARS`), the `40_000` threshold, the 2-call ceiling, `max_tokens=8_000` per call, and the merge expression (`{**commercial_result, **organizational_result}`) are all unchanged. `_SKELETON_SPLIT` / `_two_pass_skeletons()` stay at `customer_profile` (not authorized to change); the move is the emit-key lists only.

## Alternatives rejected

- **3-way split (3 calls).** Would reopen the call-count ceiling C37 explicitly settled as operator-only. Not exercised because the imbalance (roughly one field's worth) does not require a structural change, only a rebalance.
- **Raise `max_tokens` past 8,000 on the commercial call only.** Packet forbids per-call token-budget deviation; C33/C34/pre-C34 already proved 12K/16K exceed the serving floor.
- **Recalibrate `_TWO_PASS_CONTEXT_CHARS`.** The threshold is not the miss — `bma_context_chars=121977` is well above `40_000`, so two-pass correctly triggered. Changing the threshold would not address an unbalanced split.
- **Move a different field (e.g. `workforce_capacity`, the largest commercial field).** Rejected in favor of the field that was actually cut (`customer_operational_metrics`) and is also the smallest — the minimal move most likely to resolve the overflow without over-correcting into organizational.
- **Also move `_SKELETON_SPLIT` so the commercial skeleton no longer contains the `customer_operational_metrics` schema.** Packet Files-to-touch and the `git diff 8f3a9d1` kill allow only the one-field list move. Skeleton stay is deliberate, not an omission.

## Assumptions made

- Organizational's measured headroom on job `917857674928` (all six known fields under ~5.1K chars each, against an ~8K-token / ~24-32K-char ceiling) is large enough to absorb one more field. Not proven until the post-C38 wet run.
- Moving only the truncated field is sufficient; if commercial's remaining 6 fields still overflow (unlikely given `workforce_capacity`=5799 was the last field to complete before the truncated field), or if organizational's added field pushes it over 8K, the packet requires a fresh decision log before any further move — not a silent retry.
- The commercial prompt's `Emit ONLY these top-level keys` list (now 6 keys, no `customer_operational_metrics`) is enough to stop the model filling that field even though `_COMMERCIAL_SKELETON` still contains the schema block (split still at `customer_profile`). If the commercial call still emits and truncates on that leftover skeleton, that is a C38 HALT, not an inline skeleton edit.

## Items deferred

- A third rebalance or 3-way split, if the post-C38 Arm A also truncates. Reserved for a fresh operator decision.
- Recalibrating `_TWO_PASS_CONTEXT_CHARS` from further data points beyond this arm's `121977`.
- Moving `_SKELETON_SPLIT` to follow the rebalanced lists. Not authorized this round.

## Required C38 points

### (a) Measured per-field char counts (job `917857674928`) motivating the move

Pasted from the halt-v6 warehouse verification (`uc13_ale.analysis.business_model` latest in-window row `created_at=2026-08-25T15:23:19.894Z`; also `runs/T3-bis-c37-brief.md`):

Organizational (completed): `customer_profile`=1804, `sales_motion`=1842, `revenue_visibility`=1107, `key_dependencies`=3459, `recent_model_changes`=4792, `citations`=5055 chars — sum ≈18,059 chars plus `overlay_conflict_evidence`=0 and `extraction_notes` (unmeasured, small), against an ~8K-token (~24–32K char) ceiling: measured headroom.

Commercial (truncated): `products_services`=3128, `revenue_by_location`=3620, `people_and_org`=4699, `workforce_capacity`=5799 chars written before the call died mid-`customer_operational_metrics` (`Unterminated string starting at: line 619 column 7`, char 24120; `customer_operational_metrics`=2 / `"{}"`) — the group ran out of budget before completing its 7th field.

### (b) Why `customer_operational_metrics`, not a different field

It is the field that was actually cut by the truncation (evidence-based, not a guess), and it is the smallest of commercial's seven fields (empty `"{}"` at cut; a short structured metrics object when complete), making it the lowest-risk single move: minimal addition to organizational's budget, exact removal of the field that overflowed commercial.

### (c) Confirmation that no other C37 term changed

Executor `git diff 8f3a9d1 -- databricks/agents/workstreams/business_model_agent.py` (working tree, pre-commit):

```
@@ -730,7 +730,6 @@ _COMMERCIAL_FIELD_KEYS = (
     "revenue_by_location",
     "people_and_org",
     "workforce_capacity",
-    "customer_operational_metrics",
 )
 _ORGANIZATIONAL_FIELD_KEYS = (
     "customer_profile",
@@ -741,6 +740,7 @@ _ORGANIZATIONAL_FIELD_KEYS = (
     "overlay_conflict_evidence",
     "citations",
     "extraction_notes",
+    "customer_operational_metrics",
 )
```

No other hunk. `_TWO_PASS_CONTEXT_CHARS`, `_should_use_two_pass`, both `max_tokens=8_000` call sites, the merge `{**commercial_result, **organizational_result}`, `_SKELETON_SPLIT`, and `_use_two_pass=False` single-call path are byte-identical to C37. Companion test delta is only `test_bma_two_pass_merges_disjoint_field_groups`'s key-membership assertion (other 3 falsifiers unmodified).

### (d) Measured `bma_context_chars` (post-C38 Arm A)

`121977` (job `595667448217011`, `RunCard.bma_context_chars` and stdout `bma_context_chars=121977`). Well above `40_000`, so two-pass triggered. No `TimeoutError`. Agent-manifest BMA SUCCESS 401.8s. Warehouse latest in-window row `created_at=2026-08-25T16:29:42.282Z` (driver card recorded `2026-08-25T16:11:44.086383`; latest-row-wins). `(a)=true (b)=true (c)=true (d)=false`.

Commercial still truncation-marked: first-save gap `Unterminated string starting at: line 617 column 23 (char 24354)`; surviving row `Expecting property name enclosed in double quotes: line 594 column 34 (char 23483)`. Field lengths on the surviving row: `products_services`=7900, `revenue_by_location`=5201, `people_and_org`=4828, `workforce_capacity`=2, `customer_operational_metrics`=2, `customer_profile`=1791, `sales_motion`=2106, `revenue_visibility`=1250, `key_dependencies`=3607, `recent_model_changes`=5034, `citations`=4164. Moving the one field did not untruncate commercial; `customer_operational_metrics` stayed empty on organizational (skeleton still splits at `customer_profile`). See `runs/T3-bis-c38-brief.md`.
