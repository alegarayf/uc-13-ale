# Decision log — T3-bis C39

**Subtask:** T3-bis
**Tier:** architectural
**Date:** 2026-08-25

## Chosen approach

Add explicit brevity/length guidance to the two-pass commercial call's prompt in `business_model_agent.py`, scoped strictly to the `_use_two_pass=True` branch, targeting the three fields responsible for both prior truncation failures' overflow: `products_services`, `people_and_org`, `workforce_capacity`. The guidance bounds output length directly (item count and word guidance) rather than relying on field ordering to predict where truncation will land. Field-group membership (C38), routing/threshold/call-count/`max_tokens`/merge (C37) are all unchanged. The organizational prompt and the `_use_two_pass=False` single-call prompt are untouched.

Implementation: module constant `_C39_COMMERCIAL_BREVITY` concatenated only when `_format_two_pass_user_prompt(..., group="commercial")`. Organizational call uses `brevity = ""`.

## Alternatives rejected

- **A third field move.** Rejected on evidence: two consecutive field-rebalances (C37's original split, C38's one-field move) failed with the identical signature — commercial overflowed 8K and the specific field cut relocated between runs because `products_services` varied 2.5× in length. A third move would only relocate the truncation point again, not resolve it.
- **3-way split (3 calls).** Would reopen the call-count ceiling C37 explicitly settled as operator-only. Held in reserve as the next lever if C39 also fails.
- **Raise `max_tokens` past 8,000.** Packet forbids per-call token-budget deviation; already proven (C33/C34/pre-C34) to exceed the serving floor.
- **Accept the gap now, without trying a length-bound.** Rejected as premature — a prompt-level length bound is a direct, low-risk attack on the actual measured cause (output-length variance) and hadn't been tried yet.

## Assumptions made

- Soft prompt-level length guidance will bind reliably enough on this model/corpus to keep the commercial call's total output inside 8K tokens. Not proven until the wet run — LLMs sometimes only partially honor length instructions, which is why the kill criteria still HALT (not retry) if truncation recurs.
- Bounding `products_services`/`people_and_org`/`workforce_capacity` verbosity is an acceptable, scoped quality tradeoff on `_use_two_pass=True` runs only (same posture as C37/C38's prior tradeoff notes); production/normal-size rooms are unaffected.

## Items deferred

- A 3-way split or accepting the gap, if the post-C39 Arm A also truncates. Reserved for a fresh operator decision.
- Whether the brevity guidance measurably reduces extraction quality on the three targeted fields even when it fits — noted as a caveat for T9's shareable report, not a C39 kill criterion.

## Required C39 points

### (a) Prior rebalance failures' measured evidence motivating a prompt-level fix

Job `917857674928` (post-C37): commercial truncated with `customer_operational_metrics` empty; `products_services=3128`, `revenue_by_location=3620`, `people_and_org=4699`, `workforce_capacity=5799` chars written before the cutoff.

Job `595667448217011` (post-C38, `customer_operational_metrics` moved out): commercial truncated again, this time with `workforce_capacity` empty; `products_services=7900` (grew 2.5× from the prior run), `revenue_by_location=5201`, `people_and_org=4828` chars. `customer_operational_metrics` (now organizational's 9th field) also ended up empty (`"{}"`) on this run, suggesting organizational's own margin was tighter than expected too.

The identical failure signature across two different field-group boundaries, with the overflow point moving each time in step with `products_services`'s length swing, is the evidence that the boundary is not the controlling variable — the fields' own generated length is.

### (b) Exact brevity guidance text and target fields

Literal `_C39_COMMERCIAL_BREVITY` concatenated only onto the `_use_two_pass=True` commercial prompt. Targets `products_services`, `people_and_org`, `workforce_capacity`:

```
C39_BREVITY: Bound products_services, people_and_org, and workforce_capacity so this commercial JSON finishes inside 8K output tokens. products_services: at most 8 items; each prose field at most 40 words; keep numeric literals short; omit duplicate service lines. people_and_org: at most 8 key_executives and 8 ownership rows; background_note, management_depth_note, and entity_structure_note at most 25 words each. workforce_capacity: at most 10 headcount_by_function rows; workforce_model and hiring_and_growth notes at most 40 words each. Prefer the highest-revenue or named items. Do not expand executive_summary, revenue_model, or revenue_by_location to compensate.
```

### (c) Confirmation the single-call and organizational prompts are untouched

Executor `git diff 69e7dd8 -- databricks/agents/workstreams/business_model_agent.py` (working tree, pre-commit):

```
@@ -778,6 +778,22 @@ def _two_pass_skeletons() -> tuple[str, str]:

 _COMMERCIAL_SKELETON, _ORGANIZATIONAL_SKELETON = _two_pass_skeletons()

+# C39: two-pass commercial output bound. Concatenated only when
+# group == "commercial". Organizational and C36 single-call prompts
+# must stay byte-identical to C38.
+_C39_COMMERCIAL_BREVITY = (
+    "C39_BREVITY: Bound products_services, people_and_org, and workforce_capacity "
+    "so this commercial JSON finishes inside 8K output tokens. "
+    "products_services: at most 8 items; each prose field at most 40 words; "
+    "keep numeric literals short; omit duplicate service lines. "
+    "people_and_org: at most 8 key_executives and 8 ownership rows; "
+    "background_note, management_depth_note, and entity_structure_note at most 25 words each. "
+    "workforce_capacity: at most 10 headcount_by_function rows; "
+    "workforce_model and hiring_and_growth notes at most 40 words each. "
+    "Prefer the highest-revenue or named items. Do not expand executive_summary, "
+    "revenue_model, or revenue_by_location to compensate.\n"
+)
+

 def _format_two_pass_user_prompt(
     *,
@@ -800,9 +816,11 @@ def _format_two_pass_user_prompt(
         deal_type_context=deal_type_context,
         combined_chunk_text=combined_chunk_text,
     )
+    brevity = _C39_COMMERCIAL_BREVITY if group == "commercial" else ""
     return (
         f"{preamble}\n"
         f"C37_FIELD_GROUP={group}\n"
+        f"{brevity}"
         f"Emit ONLY these top-level keys: {keys}. "
         "The retrieved document context above is the full unbounded context; "
         "do not reduce, filter, or cap it.\n"
```

Two hunks only: the constant plus a commercial-only `brevity` insert. `_USER_PROMPT_TEMPLATE` (C36 single-call), `_COMMERCIAL_FIELD_KEYS` / `_ORGANIZATIONAL_FIELD_KEYS` (C38 membership), `_TWO_PASS_CONTEXT_CHARS`, `_should_use_two_pass`, both `max_tokens=8_000` call sites, and the merge `{**commercial_result, **organizational_result}` are byte-identical to C38. Organizational prompt receives `brevity = ""`. Companion test is additive (`test_bma_two_pass_commercial_prompt_has_c39_brevity`); the 4 existing C37/C38 falsifiers are unmodified.

### (d) Measured `bma_context_chars` and per-field char counts (post-C39 Arm A)

Pending — to be back-filled from the post-C39 Arm A job once run, per the plan's C39 contract row.
