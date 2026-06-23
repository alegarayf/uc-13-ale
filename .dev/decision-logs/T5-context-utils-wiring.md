# T5 — context_utils unified wiring

**Subtask:** T5 · uc13-remediation-plan v1.0.1  
**Date:** 2026-06-23

## Chosen approach

- Adapter-only dispatch in `context_utils.semantic_search_with_fallback`: `retrieval_mode` selects Route A (`route_chunks`) vs semantic paths (`semantic_search` from `retrieval.py`).
- Return type changed from `list` to `RouteResult` (imported from `agents.shared._types` shim created by T2).
- All three FTA sub-agents unpack `.chunks` before aggregating or passing to `build_focused_context`.
- `retrieval_mode` is an explicit function argument; `context_utils` does not read `os.environ` (T6 owns propagation from widget/env).
- Logging: `print(f"  retrieval_mode={retrieval_mode} returned {len(result.chunks)} chunks")` on every return path.

## Alternatives rejected

- **Define `RouteResult` in `context_utils.py`:** Rejected — T2 already placed it in `_types.py` to break the `context_utils ↔ route_chunks` circular import.
- **Change `semantic_search` return type to `RouteResult`:** Rejected per D2a — non-FTA agents (BMA, CQA, KPI, Legal, QoE) must keep receiving `list` from `retrieval.py`.
- **Set `RouteResult.mode = "enhanced_semantic"` for Route B arm:** Rejected — packet dispatch binds both `"semantic"` and `"enhanced_semantic"` to `mode="semantic"`; arm distinction is via the `retrieval_mode` argument / widget, not `RouteResult.mode`.

## Assumptions made

- T2 `RouteResult.chunks` row shape matches fields used by `build_focused_context` (`file_name`, `chunk_text`, `priority_tier`, `source_type`, `section_header`).
- T4 leaves `semantic_search` returning `list[Row]`; T5 wraps that list without inspecting VS scores (scores left `None` on semantic path for now).
- T6 will thread `retrieval_mode` from `get_param` through FTA `run()` → sub-agent `_retrieve()`; T5 only adds the parameter surface on `semantic_search_with_fallback`.

## Items deferred

- **Score passthrough on semantic path:** `RouteResult.scores` is always `None` for semantic/enhanced_semantic arms in T5; T4 may expose scores in row metadata but wiring them into `RouteResult.scores` is out of T5 scope.
- **`keyword_fallback` mode string:** If `semantic_search` hits its exception fallback, T5 does not intercept to set `mode="keyword_fallback"` — that would require inspecting `retrieval.py` internals; deferred to a follow-on if the scorecard needs it.
- **Adversarial gap — `enhanced_semantic` vs `semantic` mode discrimination in `RouteResult`:** Tests assert both map to `mode="semantic"` per packet; E2E scorecard uses widget `retrieval_mode` value, not `RouteResult.mode`, for Route B labeling.
