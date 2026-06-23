# Changelog

## uc13-remediation-plan — 2026-06-23

- T2 (Route A metadata router): Added `databricks/agents/shared/_types.py` (`RouteResult`), `route_chunks.py` (SQL metadata routing with post-SQL filters), and `tests/test_route_chunks.py` (mocked Spark filter/shape/error coverage). Circular-import shim and `tier_filter=None` default preserve control-arm parity for T5 wiring. See `.dev/decision-logs/T2-route-chunks.md`.
- T5 (FTA context_utils adapter wiring): Updated `semantic_search_with_fallback` to dispatch on `retrieval_mode` and return `RouteResult`; all three FTA sub-agents unpack `.chunks` before context build. Added `tests/test_context_utils.py` for dispatch, mode, fallback-retry, and error-propagation coverage. See `.dev/decision-logs/T5-context-utils-wiring.md`.
- T6 (FTA retrieval_mode propagation): Added `retrieval_mode` widget + `os.environ` mirror in `test_pipeline.ipynb` Cell 1; wired `main()` → `FinancialTrendsAgent.run()` → all three sub-agent `_retrieve()` → `semantic_search_with_fallback(retrieval_mode=...)` call chain. Deferred pytest for the 4-hop propagation chain — T7 notebook harness owns E2E arm verification per plan §2.
- T4 (retrieval.py Route B enhancements): Added VS `company_name` filter pushdown with SDK fallback, merge-rank ordering (`sim × tier_weight`), score extraction from `query_index`, and SQL literal escaping for hydrate/keyword paths; return type remains `list`. See `.dev/decision-logs/T4-retrieval-enhancements.md`.
