Section:      uc13-retrieval-decision
Version:      1.0.0
Last updated: 2026-06-22
Status:        decision worksheet — pre-commit
Scope:         Route selection for UC13 retrieval architecture (thesis vs fix VS vs ReAct loop)

# UC13 retrieval — decision worksheet

One-page gate sheet to choose a retrieval direction before implementation. Synthesizes [uc13-retrieval-alternatives-assessment.md](./uc13-retrieval-alternatives-assessment.md), [uc-13_pain_central.md](./uc-13_pain_central.md), and [qs_for_sync.md](../qs_for_sync.md).

**Related:** [retrieval-layer-review.md](./retrieval-layer-review.md) · [uc13-retrieval-reference.md](./uc13-retrieval-reference.md)

---

## Executive summary

Three routes answer **different** questions. **ReAct (Route C) is orthogonal to thesis vs fix-VS** — it needs a retrieval tool underneath (SQL router or improved `semantic_search`). **MCP is optional**; use it only if retrieval must be shared across runtimes (Garden chat, local dev). Databricks agents can call a Python `search_chunks()` tool directly.

**Recommended sequence:** Gate 0 (sync questions) → Gate 1 (corpus stats) → **1-week A/B** (`route_chunks` vs `semantic_search` on one agent) → commit A, B, or defer C.

---

## The three routes

| Route | Core bet | Optimizes for |
|-------|----------|---------------|
| **A — Thesis** | Classification + tier + section/filename (+ optional ingest digests) is enough chunk selection | Batch cost, simplicity, determinism |
| **B — Fix VS** | Similarity matters once filters and ranking are fixed | Incremental gain without agent rewrite |
| **C — ReAct loop** | Dynamic query generation is the missing piece | Adaptive recall, future interactive Q&A |

### Route A — Metadata router (+ optional digests)

1. Add `route_chunks()` — SQL mirror of `semantic_search` filter params.
2. A/B on one small agent (Legal or CQA): same extraction prompt, swap retrieval backend.
3. If corpus exceeds context budget: ingest digests for tier-1 docs; raw chunks on gaps.
4. Optional lightweight loop: extract → gaps → widen tier / drop filename filter (no LangGraph required initially).

### Route B — Fix existing Vector Search

1. Push filters to `query_index`: `company_name`, `workstream` overlap, optional `priority_tier`.
2. Preserve VS scores; replace SQL `ORDER BY priority_tier` with explicit merge (e.g. `sim × tier_weight`).
3. Return `{chunks, mode, scores}`; make keyword fallback explicit in traces.
4. Optional: cross-encoder rerank on top 30–50 after pre-filter.
5. Consolidate BMA + FTA filename-filter fallback wrappers.

### Route C — ReAct + retrieval tool

1. One tool: `search_chunks(query, workstreams, filters, top_k) → {chunks, mode, scores}` (A or B underneath).
2. Replace fixed N-tool scripts with plan → search → assess → search or extract (max 3–5 rounds, hard cost caps).
3. Wire `_data_room_gaps` to **trigger** widening retrieval, not only log gaps.
4. MCP only if retrieval lives outside Databricks agents.

---

## Meta-gates (answer in sync — closes the fork)

| ID | Question | Impact |
|----|----------|--------|
| **G0-1** | How much time before retrieval must be "unblocked"? | Days → A only; quarter → C becomes viable |
| **G0-2** | What does "unblocked" mean? | One agent green / full pipeline / Garden demo |
| **G0-3** | How married are we to Vector Search? (Q-R04) | Yes → lean B; No → lean A |
| **G0-4** | Batch reports only vs future chat Q&A? (S-05) | Batch → A; interactive → C as Phase 2 |
| **G0-5** | Is tier-biased ranking intentional? (Q-R01) | Yes → embeddings/rerank are secondary |

### Quick routing from sync answers

| If… | Lean toward |
|-----|-------------|
| <2 weeks, batch only, VS not sacred | **A** (router A/B) |
| VS required, large rooms, bad filenames | **B** (filter pushdown + score merge) |
| Quarter+, interactive UI, open questions | **C** on top of A or B |
| Corpus <100 chunks/workstream after filters | **A** without VS; skip rerank |

---

## Per-route commit gates

All gates must be evaluated on **2–3 real companies** with a scored field checklist (15–20 required fields per test agent).

### Route A gates

| Gate | Metric | Kill if |
|------|--------|---------|
| G-A1 Corpus size | Chunks per workstream after `should_parse` + tier≤2 | >500 chunks/ws and no digest path |
| G-A2 Recall | Field coverage vs current `semantic_search` on same agent | Systematic misses on tier-1 docs |
| G-A3 Citations | `source_doc` + `location` on extracted facts | Digest path loses anchors |
| G-A4 Runtime | Full agent run time | Slower than today without quality gain |
| G-A5 Politics | VS required for compliance/narrative | Team blocks VS removal |

### Route B gates

| Gate | Metric | Kill if |
|------|--------|---------|
| G-B1 Filter pushdown | Recall@k with workstream filter vs post-hoc Python | No improvement; still starved results |
| G-B2 Ranking | Blind review: 10 queries, top chunks more on-topic? | Tier reorder still dominates |
| G-B3 Cost | Embed + VS + rerank per full pipeline run | >20% runtime for no extraction gain |
| G-B4 Ops | Index sync + multi-company (R-04) | Sync pain remains the real blocker |

### Route C gates

| Gate | Metric | Kill if |
|------|--------|---------|
| G-C1 Determinism | Same company, 3 runs — output stability | Unacceptable variance for batch |
| G-C2 Cost ceiling | Total retrieval + LLM rounds per agent | >2× current run cost |
| G-C3 Termination | % runs hitting max rounds without extract | >30% |
| G-C4 vs static | Extraction completeness vs fixed tools | ReAct doesn't beat scripted queries |
| G-C5 Eval harness | Golden fields per agent | Can't measure — don't ship |

---

## Adversarial summary

| Risk | A | B | C |
|------|---|---|---|
| Wrong layer (extraction not retrieval) | Digests lose cell refs | Polishing unused similarity | ReAct won't fix truncation (A-01) or weak prompts (A-03) |
| Ops | Digest pipeline + storage | Index sync still blocks (P-06) | Unbounded LLM rounds |
| False negative | Large FINANCIAL rooms exceed budget | Multi-tag arrays / bad filenames | Agent stops early on "no data" |
| Hidden cost | Ingest LLM per tier-1 doc | 45 embeds + rerank per run | Embeds + N reasoning rounds |

**Strongest read:** Debating architecture while E2E validation is open (A-06) and non-financial agents need iteration (A-03). Highest ROI: **corpus stats + one-agent A/B** before committing.

**Upstream masquerading as retrieval:** Empty results often come from classifier/coverage/sync (O-02, P-06, O-06) — run Cell 8c coverage before architecture commits.

**Out of scope for any route:** Cross-Analysis Agent (S-02), Orchestrator (S-03), cross-doc reconciliation (S-06).

---

## Recommended 1-week experiment

### Day 0 — Prerequisites (notebook, no code fork)

Run on **2 companies** already parsed in `test_pipeline.ipynb`:

1. **Cell 8c** — coverage report; fix gaps via 8d if needed.
2. **Corpus stats (Gate 1)** — record in experiment log:

```sql
-- Per company: chunks per workstream (tier ≤ 2)
SELECT r.company_name, ws AS workstream, COUNT(*) AS chunk_count
FROM uc13.ingestion.chunks c
JOIN uc13.classification.doc_relevance r
  ON c.file_name = r.filename AND c.company_name = r.company_name
LATERAL VIEW explode(r.workstream) t AS ws
WHERE r.should_parse = true AND r.priority_tier <= 2
GROUP BY 1, 2
ORDER BY 1, 3 DESC;
```

3. Pick **test agent:** Legal (`legal_contracts_agent.py`) or CQA (`customer_quality_agent.py`) — smaller corpus, fixed schema.
4. Define **golden checklist:** 15–20 required output fields for that agent (from spec / `_EXPECTED_COLS`).

### Days 1–2 — Implement `route_chunks()` shim

- New module: `databricks/agents/shared/route_chunks.py` (or extend `retrieval.py`).
- Mirror params: `company_name`, `workstream_filter`, `tier_filter`, `file_name_filter`, `min_chunk_length`, `source_type_filter`, `top_k`.
- SQL + keyword predicates on `chunk_text` / `section_header`; order by `priority_tier`, `file_name`, `chunk_index`.
- Optional: `semantic_search()` delegates to `route_chunks()` behind a feature flag for A/B.

### Days 3–4 — A/B run

| Arm | Retrieval | Everything else identical |
|-----|-----------|---------------------------|
| Control | Current `semantic_search` | Same prompts, same `top_k` / filters |
| Treatment | `route_chunks` | Same |

Score each arm: field pass/partial/miss, `_data_room_gaps` count, citation presence, runtime, retrieval `mode` if instrumented.

### Day 5 — Decision

| Outcome | Decision |
|---------|----------|
| Treatment ≥ control on recall; corpus <100 chunks/ws | **Commit A** — deprecate query-time embeds for test agent; roll out shim |
| Treatment misses tier-1 fields; corpus >300 chunks/ws | **Try B-lite** (VS filter pushdown only) on same agent |
| Both fail on same fields | **Upstream** — classifier, parser, or extraction prompt; not retrieval arch |
| Batch only + treatment wins | **Defer C** to Phase 2 |
| Interactive UI committed (G0-4) | Plan **C** on winning backend after A/B |

---

## Migration notes

- **`semantic_search` blast radius** (M-06): all Phase 3 agents import it. Use compat shim + per-agent flag; don't change signature until one agent is green.
- **Instrument traces:** add `retrieval_mode: vector | keyword | routed` to `ToolResult` (Q-R02) before comparing arms fairly.
- **Context budgets:** unify BMA with FTA's `build_focused_context` cap before comparing agents fairly (R-09).

---

## Decision log (fill after experiment)

| Field | Value |
|-------|-------|
| Date | |
| Companies tested | |
| Test agent | |
| Corpus stats (max chunks/ws) | |
| Control field score | /20 |
| Treatment field score | /20 |
| Winner | A / B / C-deferred / upstream |
| Committed next step | |
| Q-R04 answer (VS marriage) | |
| Q-R01 answer (tier bias intentional) | |

---

## Document history

| Version | Date | Change |
|---------|------|--------|
| 1.0.0 | 2026-06-22 | Initial decision worksheet from sync prep and retrieval alternatives synthesis |
