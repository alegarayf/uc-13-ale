# T2 — Route A `route_chunks.py` module

**Subtask:** T2 (uc13-remediation-plan v1.0.1)  
**Date:** 2026-06-23

## Chosen approach

- **`RouteResult` shim:** Defined in `databricks/agents/shared/_types.py` so `route_chunks.py` and future `context_utils.py` (T5) can import without circular dependency (D2 resolution).
- **SQL router:** `route_chunks()` joins `uc13.ingestion.chunks` to `uc13.classification.doc_relevance` on `c.file_name = r.filename AND c.company_name = r.company_name`, enforces `r.should_parse = true`, orders by `priority_tier ASC NULLS LAST, file_name, chunk_index`, and fetches `top_k * 3` rows before Python post-filters (parity with `semantic_search` margin).
- **Workstream overlap:** Primary path uses `arrays_overlap(r.workstream, array(...))` with a runtime probe; on probe failure, falls back to `(array_contains(...) OR ...)` OR-chain.
- **Keyword filter:** First five alphanumeric words from `keyword_filter` become sanitized `LIKE` predicates on `chunk_text` and `section_header` (SQL-side).
- **`tier_filter` default `None`:** No SQL tier cap when unset (D4a control-arm parity — FTA sub-agents do not pass `tier_filter` to `semantic_search` today).

## Alternatives rejected

- **Import `RouteResult` from `context_utils.py`:** Rejected — would create `context_utils → route_chunks → context_utils` circular import once T5 wires the adapter.
- **Apply `file_name_filter` in SQL:** Rejected — `semantic_search` applies filename matching in Python (case-insensitive substring); post-SQL filter preserves A/B comparability and matches existing control behavior.
- **Hard-code `priority_tier <= 2` in Route A SQL:** Rejected — D4a requires `tier_filter=None` default so Route A does not over-filter relative to control until callers opt in.

## Assumptions made

- **`uc13.ingestion.chunks` and `uc13.classification.doc_relevance` exist** in target workspaces (created by `ingestion_parser.py` / `document_classifier.py`). Verified via DDL in `ingestion_parser.py` (`chunk_index INT` at line ~1463) — live `SHOW TABLES` not run in local executor environment.
- **`chunk_index` column exists** on `uc13.ingestion.chunks` per production DDL; used in `ORDER BY` tiebreaker per A-W3.
- **`arrays_overlap` available on DBR 11+** used by this workspace; runtime probe + OR-chain fallback covers older runtimes without HALT.

## Items deferred

- **Live Spark verification** (`SHOW TABLES`, `arrays_overlap` probe on cluster): deferred to T7 E2E notebook — local pytest uses mocked `spark.sql().collect()`.
- **Adversarial test gap — SQL injection via `company_name` with backslash escapes:** deferred; mitigation is `'` doubling only (matches `retrieval.py` pattern). A test with adversarial company strings would require contract change for parameterized binding (out of T2 scope).
