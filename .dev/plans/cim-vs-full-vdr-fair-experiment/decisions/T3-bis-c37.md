# Decision log — T3-bis C37

**Subtask:** T3-bis  
**Tier:** architectural  
**Date:** 2026-08-25  
**Files added:** `tests/test_bma_two_pass_routing.py` (C37 falsifiers; conventional `tests/test_*.py` path per executor §2.2)

## Chosen approach

Context-size-gated two-pass fallback in `business_model_agent.py`: `_use_two_pass = len(combined_chunk_text) > _TWO_PASS_CONTEXT_CHARS` (`40_000`). Below the threshold the landed C36 single call (`max_tokens=8_000`, `executive_summary` first, full unbounded input) is unchanged. Above it, two `max_tokens=8_000` calls over the **same** full unbounded `combined_chunk_text` and `company_profile_json`, split commercial vs organizational, merged with `{**commercial, **organizational}`. Every run logs `bma_context_chars` on the result, in a `reasoning_trace` step, and on `RunCard` (driver passthrough from that trace).

## Alternatives rejected

- **Raise `max_tokens` above 8_000 on a single call.** C34 (12K) and pre-C34 (16K) complete more of the schema but die at the Databricks serving ~120s floor (`TimeoutError: Timed out after 0:10:00`). Packet forbids this lever.
- **Unconditional / default two-pass.** Reopens the 2026-08-18 quality loss on every room, including production-sized ones that C36 already serves. Rejected; C37 is gated.
- **Bound / cap / filter input context (the 2026-08-18 incoming pattern).** Packet forbids it. The 2026-08-18 quality loss (`overlay_conflict_evidence`, tax-preparer-as-`key_executives`) was observed on that *bounded* input, not on an output-only split.
- **Continuation / chaining loop or a third call.** Packet forbids it. Two calls is the authorized ceiling.

## Assumptions made

- Arm A's `combined_chunk_text` will exceed `40_000` chars, so this run actually exercises the two-pass path. If it does not, C37 is landed but unproven on the wet corpus (threshold calibration still gets a real `bma_context_chars`).
- Splitting the *output schema* while keeping the full input on both calls is enough to finish JSON under 8K tokens per call on this arm. If either call still truncates, the packet requires HALT — not a silent retry or a third split.
- Existing C36 AST pins stay green because the single-call site remains `self._call_llm(_SYSTEM_PROMPT, …, max_tokens=8_000)` and two-pass passes the system prompt via a local (`system = _SYSTEM_PROMPT`).
- Adding `RunCard.bma_context_chars: int = 0` is additive and does not break T1's required-key round-trip (default keeps `_sample_run_card` constructible).

## Items deferred

- Recalibrating `_TWO_PASS_CONTEXT_CHARS` from the measured Arm A `bma_context_chars` (landing gate: this same T3-bis wet run + future threshold review). First-cut `40_000` is unmeasured until that figure exists.
- Whether the 2026-08-18 quality tradeoff (lost `overlay_conflict_evidence`; tax-preparer-as-`key_executives` noise) reappears on the *unbounded-input* two-pass path. Accepted as scoped to large-context runs; Wave 1 (T6) / shareable report can note it. Not a C37 kill.
- Promoting `bma_context_chars` to a Delta column. Out of scope (would trip `_EXPECTED_COLS` drop+recreate). Trace + RunCard is the authorized log.

## Required C37 points

### (a) Why 2026-08-18's test did not cover this case

That comparison ran both single-call and two-pass against Elder Care and saw no crash or truncation either way. The incoming two-pass **capped input** (CIM → Tier 1 → other, per-chunk caps, 90K-char budget) and the corpus was not Arm A's 55,819-chunk `uc13_ale` room (Elder Care alone exceeds production `uc13` across every company). Quality loss there was an input-bounding artifact. It did not measure an 8K output ceiling against this arm's denser top-k fill. Post-C36 job `833694093064269` is the covering evidence: 8K cleared the serving floor (BMA 202.7s, no `TimeoutError`) and still length-truncated (`Unterminated string` at JSON line 647; 8 of 14 top-level sections empty).

### (b) Threshold provenance

`_TWO_PASS_CONTEXT_CHARS = 40_000` is a first-cut. No prior run logged `len(combined_chunk_text)`. The constant is documented in-source as pending calibration. `RunCard.bma_context_chars` exists so a later change is evidence-based.

**Measured Arm A `bma_context_chars`:** `121977` (job `917857674928`, both in-window BMA writes; also on `RunCard.bma_context_chars` and `reasoning_trace` tool `bma_context_chars`). Well above the `40_000` first-cut, so two-pass did trigger. Threshold itself is not the miss — commercial-group 8K output still truncated.

### (c) Field-group split rationale

The split mirrors the existing 8 retrieval-tool boundaries already used to build `combined_chunk_text`:

- **Commercial** (people/org + workforce + overview + pricing + location/metrics tools): `executive_summary`, `revenue_model`, `products_services`, `revenue_by_location`, `people_and_org`, `workforce_capacity`, `customer_operational_metrics`.
- **Organizational** (sales/customers + visibility + changes/dependencies tools, plus overlay/citations): `customer_profile` (incl. `overlay_specific`), `sales_motion`, `revenue_visibility`, `key_dependencies`, `recent_model_changes`, `overlay_conflict_evidence`, `citations`, `extraction_notes`.

Skeletons are sliced from the landed C36 `_USER_PROMPT_TEMPLATE` at `customer_profile` so the single-call skeleton is not rewritten.

### (d) Accepted quality tradeoff (scoped)

The 2026-08-18 test lost `overlay_conflict_evidence` and misclassified third-party tax preparers as `key_executives`. C37 accepts that risk **only** on `_use_two_pass=True` runs. `_use_two_pass=False` (production and normal-size rooms) stays on C36 and does not take that tradeoff. Input is not capped this time, which may reduce the original failure mode; that is hoped, not proven.

### (e) Measured `bma_context_chars` (Arm A)

`121977`. Source: job `917857674928` stdout `bma_context_chars=121977`, `uc13_ale.analysis.business_model.reasoning_trace` tool `bma_context_chars`, and the FAILED Arm A `RunCard`. Two-pass triggered. Commercial call still truncation-marked (`Unterminated string` at JSON line 619); `customer_operational_metrics` empty. See `runs/T3-bis-c37-brief.md`.
