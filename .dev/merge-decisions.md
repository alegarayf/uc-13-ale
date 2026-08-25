# Merge decisions

Standing record of merge/integration decisions that must survive future merges or re-proposals — **read this before merging any branch that touches files listed below.**

Each entry documents a change that was proposed on an incoming branch, evaluated, and explicitly accepted or rejected by the repo owner. Do not silently re-apply rejected hunks when re-merging the same or a similar branch.

---

## 2026-08-25 — BMA extraction: authorize context-size-gated two-pass fallback (C37)

> Supersedes the 2026-08-18 rejection **in scope only**. The 2026-08-18 entry is retained below and must not be deleted.

| Field | Detail |
|---|---|
| **Source** | Operator ruling 2026-08-25 (T3-bis halt-v5 / plan v1.6): reopen the 2026-08-18 two-pass rejection as a context-size-gated fallback, not a blanket reversal. Packet `.dev/plans/cim-vs-full-vdr-fair-experiment/packets/T3-bis.md`. |
| **File affected** | `databricks/agents/workstreams/business_model_agent.py` — routing + two-pass path in `BusinessModelAgent._extract_structured()` |
| **What was authorized** | When `len(combined_chunk_text) > _TWO_PASS_CONTEXT_CHARS` (`40_000`, first-cut pending calibration via `RunCard.bma_context_chars`), split extraction into two `max_tokens=8_000` calls over the **same full unbounded** input (commercial vs organizational field groups), then merge. Below the threshold, keep the landed C36 single call (`max_tokens=8_000`, `executive_summary` first) byte-identical. |
| **Decision** | **ACCEPTED, scoped.** Two-pass is permitted only as this fallback. It remains forbidden as a default, as an ad-hoc per-run choice, and as a substitute for fixing a genuine extraction bug. |
| **Why 2026-08-18 did not cover this case** | That comparison used a smaller corpus / non-vision case and a **bounded/capped input** (CIM → Tier 1 → other, 90K-char budget). It never faced Arm A's 55,819-chunk Elder Care room in `uc13_ale` (larger than production `uc13` across every company combined). Post-C36 Arm A `833694093064269` proved 8K clears the serving floor but cannot complete the schema on that context; 12K/16K complete more schema but die at the ~120s floor. No single `max_tokens` satisfies both constraints on this arm. |
| **Action for future agents** | Do not delete the 2026-08-18 entry. Do not make two-pass unconditional. Do not raise `max_tokens` above 8_000 on either call. Do not bound/filter/cap input context on either call. Recalibrate `_TWO_PASS_CONTEXT_CHARS` from measured `bma_context_chars`, not from guesswork. |
| **Developer-context pointer** | `databricks/CLAUDE.md` → `_call_llm()` — serving-timeout section (C37 fallback). Decision log: `.dev/plans/cim-vs-full-vdr-fair-experiment/decisions/T3-bis-c37.md`. |

---

## 2026-08-18 — BMA extraction: reject two-pass split (keep single call)

> Superseded by T3-bis C37 (2026-08-25): a context-size-gated two-pass fallback is now authorized for large-context rooms only. The original test and rejection stay readable so the trail survives. Do not treat this entry as a standing ban on the C37 fallback.

| Field | Detail |
|---|---|
| **Source** | Hector's `hector/merge-ale-base-hector-incoming-results` branch (local checkout: `dev3-incoming`), commit `0d520eb` ("fix: three post-merge gaps Ale's M0-M4 program leaves for the CIM preview") or nearby |
| **File affected** | `databricks/agents/workstreams/business_model_agent.py` — `BusinessModelAgent.run()` |
| **What was proposed** | Split the single `max_tokens=16_000` extraction call into two bounded `max_tokens=8_000` calls over disjoint field groups (commercial vs organizational), with retrieved chunk context sorted/capped by tier (CIM → Tier 1 → other, per-chunk char caps, 90,000-char total budget), then merged into one dict |
| **Decision** | **REJECTED** by Ale. Keep the single-call, unbounded-context version (as on `dev2`). |
| **Rationale** | Empirically compared both versions against real Elder Care data — no crashes or truncation either way, but the two-pass version lost a real diligence insight (`overlay_conflict_evidence`) and added noise (misclassifying third-party tax preparers as `key_executives`), for no clear token-cost or latency win in the tested (non-vision) case |
| **Action for future agents** | When re-merging `dev3-incoming` (or any branch carrying this same change) into `dev2`/main, **exclude/revert this specific hunk** in `business_model_agent.py`. Do not silently accept a reintroduction of the two-pass pattern for BMA. |
| **Developer-context pointer** | `databricks/CLAUDE.md` → `_call_llm()` — max_tokens override → Serving read timeout section (BMA single-call rule) |
