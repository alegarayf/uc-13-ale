# Decision log — T3-bis C40

**Subtask:** T3-bis
**Tier:** architectural
**Date:** 2026-08-25

## Chosen approach

Add explicit brevity/length guidance to the two-pass organizational call's prompt in `business_model_agent.py`, scoped strictly to the `_use_two_pass=True` branch, targeting the overflow field measured on post-C39 Arm B plus the two next-largest organizational lists named in the C40 packet: `recent_model_changes` (required; 7632 chars on the failing job), `key_dependencies`, and `citations`. The guidance bounds output length directly (item count and word guidance), the same class of fix C39 proved on commercial. Field-group membership (C38), routing/threshold/call-count/`max_tokens`/merge (C37), and C39's commercial guidance are all unchanged. The `_use_two_pass=False` single-call prompt is untouched.

Implementation: module constant `_C40_ORGANIZATIONAL_BREVITY` concatenated only when `_format_two_pass_user_prompt(..., group="organizational")`. Commercial call still uses `_C39_COMMERCIAL_BREVITY` byte-identical to `0aab321`.

## Alternatives rejected

- **3-way split (3 calls).** Would reopen the call-count ceiling C37 settled as operator-only. Held in reserve if C40 also fails.
- **Raise `max_tokens` past 8,000.** Packet forbids per-call token-budget deviation; already proven (C33/C34/pre-C34) to exceed the serving floor.
- **Move a field out of organizational.** Two field-rebalances already failed on commercial (C37/C38); C39's length-bound is the proven lever, not another membership shuffle.
- **Bound only `recent_model_changes`.** Rejected as under-insurance: C39's lesson is that the next-verbose sibling (`citations`=4335, `key_dependencies`=2968 on the failing Arm B) can absorb the saved budget. Packet authorizes extending to those two fields when C39/C40 evidence supports it.
- **Bound / filter / cap input context.** Packet forbids it.

## Assumptions made

- Soft prompt-level length guidance will bind reliably enough on this model/corpus to keep the organizational call's total output inside 8K tokens, as C39's identical mechanism did on commercial. Not proven until the wet run — the kill criteria still HALT (not retry) if either post-C40 arm truncates.
- Bounding `recent_model_changes`/`key_dependencies`/`citations` verbosity is an acceptable, scoped quality tradeoff on `_use_two_pass=True` runs only; production/normal-size rooms stay on the C36 single-call path.
- Re-submitting the previously-clean Arm A under C40 will not regress commercial or organizational. If it does, that is new evidence, not noise.

## Items deferred

- A 3-way split, further guidance tightening, or accepting the gap, if either post-C40 arm still truncates. Reserved for a fresh operator decision. Do not retry.
- Whether the brevity guidance measurably reduces extraction quality on the three targeted fields even when it fits — noted as a caveat for T9's shareable report, not a C40 kill criterion.

## Required C40 points

### (a) Arm B measured evidence motivating the organizational guidance

Job `884181519217064` (post-C39 Arm B, `uc13_preview`): two-pass triggered at `bma_context_chars=80145` (above `40_000`). Commercial's C39 bound held (`products_services=2697`, `people_and_org=4270`, `workforce_capacity=3103`). Organizational truncated: `Unterminated string starting at: line 524 column 23 (char 25276)`, driven by `recent_model_changes=7632` chars. Other organizational lengths on that row: `customer_profile=3776`, `sales_motion=1811`, `revenue_visibility=1128`, `key_dependencies=2968`, `citations=4335`, `customer_operational_metrics=2561`. `(a)=true (b)=true (c)=true (d)=false`. This is the same length-variance class C39 fixed on commercial, now on the call C39 did not touch.

Post-C39 Arm A `517156035655991` had succeeded fully with organizational `recent_model_changes=5135` (still two-pass at `bma_context_chars=121977`), so the overflow is corpus-and-draw dependent, not a C39 regression.

### (b) Exact guidance text and target fields

Literal `_C40_ORGANIZATIONAL_BREVITY` concatenated only onto the `_use_two_pass=True` organizational prompt. Targets `recent_model_changes` (required), plus `key_dependencies` and `citations` (packet-authorized extension: next-largest recovered organizational lists on the failing Arm B):

```
C40_BREVITY: Bound recent_model_changes, key_dependencies, and citations so this organizational JSON finishes inside 8K output tokens. recent_model_changes: at most 10 dated events; each description and impact_note at most 40 words; omit duplicate or undated events. key_dependencies: at most 10 named dependencies; each description at most 25 words. citations: at most 16 rows; quotes stay at most 30 words. Prefer the highest-impact or named items. Do not expand customer_profile, sales_motion, revenue_visibility, or customer_operational_metrics to compensate.
```

### (c) Confirmation the commercial prompt (C39) and single-call prompt are untouched

Executor `git diff 0aab321686f0ef8ceee2326caee8454dbff99cc1 -- databricks/agents/workstreams/business_model_agent.py` (working tree, pre-commit):

```
@@ -794,6 +794,20 @@ _C39_COMMERCIAL_BREVITY = (
     "revenue_model, or revenue_by_location to compensate.\n"
 )
 
+# C40: two-pass organizational output bound. Concatenated only when
+# group == "organizational". Commercial (C39) and C36 single-call
+# prompts must stay byte-identical to C39.
+_C40_ORGANIZATIONAL_BREVITY = (
+    "C40_BREVITY: Bound recent_model_changes, key_dependencies, and citations "
+    "so this organizational JSON finishes inside 8K output tokens. "
+    "recent_model_changes: at most 10 dated events; each description and "
+    "impact_note at most 40 words; omit duplicate or undated events. "
+    "key_dependencies: at most 10 named dependencies; each description at most 25 words. "
+    "citations: at most 16 rows; quotes stay at most 30 words. "
+    "Prefer the highest-impact or named items. Do not expand customer_profile, "
+    "sales_motion, revenue_visibility, or customer_operational_metrics to compensate.\n"
+)
+

 def _format_two_pass_user_prompt(
     *,
@@ -816,7 +830,12 @@ def _format_two_pass_user_prompt(
         deal_type_context=deal_type_context,
         combined_chunk_text=combined_chunk_text,
     )
-    brevity = _C39_COMMERCIAL_BREVITY if group == "commercial" else ""
+    if group == "commercial":
+        brevity = _C39_COMMERCIAL_BREVITY
+    elif group == "organizational":
+        brevity = _C40_ORGANIZATIONAL_BREVITY
+    else:
+        brevity = ""
     return (
         f"{preamble}\n"
         f"C37_FIELD_GROUP={group}\n"
```

Two hunks only: the C40 constant plus an organizational-only `brevity` insert. `_C39_COMMERCIAL_BREVITY` is byte-identical to `0aab321`. `_USER_PROMPT_TEMPLATE` (C36 single-call), `_COMMERCIAL_FIELD_KEYS` / `_ORGANIZATIONAL_FIELD_KEYS` (C38 membership), `_TWO_PASS_CONTEXT_CHARS`, `_should_use_two_pass`, both `max_tokens=8_000` call sites, and the merge `{**commercial_result, **organizational_result}` are unchanged. Companion test is additive (`test_bma_two_pass_organizational_prompt_has_c40_brevity`); the existing C37/C38/C39 falsifiers are unmodified.

### (d) Measured `bma_context_chars` and per-field char counts (post-C40 arms)

Pending wet run of wrapper-submitted post-C40 Arm A then Arm B. Back-filled after those jobs complete.
