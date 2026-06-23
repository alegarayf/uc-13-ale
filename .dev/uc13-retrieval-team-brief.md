Section:      uc13-retrieval-team-brief
Version:      1.0.1
Last updated: 2026-06-22
Status:        team sync — findings and proposed direction
Scope:         UC13 retrieval current state, remediations, and route options (A / B / C)

# UC13 retrieval — team brief

Concise summary of **how retrieval works today**, **what we plan to try next**, and **three architectural routes** — for team alignment before I commit implementation effort.

**Execution plan (Routes A & B + remediation):** [uc13-remediation-plan.md](./uc13-remediation-plan.md)

This is a factual description of the inherited design and its tradeoffs, not a critique of prior work. The layer works as batch orchestration glue; several choices would feel wrong in a production RAG service but were reasonable for shipping the pipeline.

---

## Executive summary

| Topic | Headline |
|-------|----------|
| **Current behavior** | `semantic_search()` behaves closer to **tier-biased metadata routing** than true semantic ranking. |
| **Cost** | ~45–55 embed + Vector Search calls per full pipeline run, while similarity order is largely discarded. |
| **Immediate priority** | **Route A** (prove SQL/metadata router) and **Route B** (fix Vector Search in place) — not Route C yet. |
| **Near-term experiment** | Corpus size stats on **1–2** real companies → **one-agent A/B** (`route_chunks` vs `semantic_search`). |
| **Corpus sizing (open)** | ~1,241 files ingested (`8704b3b`); post-classification chunk counts per workstream **unknown** — Step 0 blocker before route commitment. |
| **Route C** | ReAct / adaptive retrieval loop — **long-term production pattern** for interactive Q&A; Phase 2 unless timeline opens up. |

---

## How retrieval works today

UC13 is a **batch diligence pipeline**: classify docs → parse to chunks + embeddings → workstream agents fire many handcrafted retrieval queries → LLM extraction with citations.

Shared entry point: `databricks/agents/shared/retrieval.py` → `semantic_search()`.

```
embed query (BGE) → Vector Search (top_k × 3, no metadata filters)
  → SQL hydrate (chunks ⋈ doc_relevance)
  → Python post-filters (workstream, tier, filename, length, source_type)
  → cap to top_k
  (on any exception → keyword LIKE on first 5 query tokens)
```

Agents never see unparsed files. Document-level routing (classifier → workstream tags, `priority_tier`, `should_parse`) is largely in place. What retrieval still must solve is **within-corpus chunk selection**: e.g. which FINANCIAL chunks answer “headcount by geography” vs “addback schedule.”

---

## As is

| # | Finding | Why it matters | Source |
|---|---------|----------------|--------|
| 1 | **Similarity ranking is discarded** | VS returns nearest neighbors; hydration re-sorts with `ORDER BY priority_tier ASC`. Python may re-sort again (`source_type_priority`). Final `top_k` ≈ “tier-biased candidates,” not “most similar to query.” | `retrieval.py`; `09a0388` fixing priority tiers order |
| 2 | **Metadata filters run after global vector search** | `workstream` and `priority_tier` are synced to the index but **not used at `query_index`**. Flow: fetch globally → join Delta → filter on driver. Aggressive filters can **starve results** (wrong workstream chunks consume the `top_k × 3` budget). | `retrieval.py`; `957dcad` fixing vector search fields; `0ca5a05` fixing retrieval query |
| 3 | **No company scoping at search time** | `company_name` is not in `columns_to_sync`. Search is global; company isolation happens only in follow-up SQL. | `retrieval.py`; `setup_vector_search.py` |
| 4 | **No reranking** | Top-k cap only; no cross-encoder or score merge. Paying embed + VS cost without exploiting similarity. | `retrieval.py` |
| 5 | **Blunt keyword fallback** | Any exception (including empty VS) triggers keyword `LIKE`. No `retrieval_mode` in traces — degradation is silent. | `retrieval.py` |
| 6 | **Filename-filter retries duplicated** | BMA and FTA each have `semantic_search_with_fallback`; retries re-embed and re-query (double cost). | `44c4a17` refactoring enhancements for retrieval agents |
| 7 | **~45–55 searches per full run** | Many static NL queries per agent; functionally declarative routing specs (workstream + filename hints + tier), not open-ended search. | `8f77543` agents notebook creation and first retrieval techniques |
| 8 | **Split context assembly** | `source_type_priority` in retrieval; CIM-first + char caps in `context_utils`; BMA has its own path. FTA caps at ~25k chars; BMA does not. | `context_utils.py`; BMA agent path |
| 9 | **Embeddings may be optional for batch UC13** | Given tier-biased behavior, a SQL metadata router may match current quality with less infra — **hypothesis to test**, not a foregone conclusion. | Route A experiment (Step 0–1) |

**One-line verdict:** Prototype RAG glue that accumulated filters and fallbacks in Python — not a retrieval layer designed around ranking, tenancy, and observability from the start. It is **good enough for batch orchestration** but carries documented design debt.


---

## Planned remediations

### If we stay on Vector Search (Route B — fix in place)

Ordered by priority:

1. Push filters to `query_index`: `company_name`, workstream overlap, optional `priority_tier`.
2. Preserve VS scores; replace SQL `ORDER BY priority_tier` with explicit merge (e.g. `similarity × tier_weight`).
3. Return structured `{chunks, mode, scores}`; make keyword fallback explicit in agent traces.
4. Optional: cross-encoder rerank on top 30–50 after pre-filter.
5. Consolidate BMA + FTA filename-filter fallback into one wrapper.
6. Parameterize SQL; typed result dataclass aligned with `ToolResult`.

### Regardless of route (instrumentation)

- Add `retrieval_mode: vector | keyword | routed` to traces before A/B comparison.
- Unify context budgets across agents (BMA vs FTA) for fair evaluation.

---

## My three routes

These answer **different questions**. Route C is **orthogonal** to A vs B — it needs a retrieval tool underneath (either A or B).

| Route | Core bet | Optimizes for | Priority |
|-------|----------|---------------|----------|
| **A — Metadata router** | Classification + tier + section/filename (+ optional ingest digests) is enough chunk selection | Batch cost, simplicity, determinism | **Primary** |
| **B — Fix Vector Search** | Similarity matters once filters and ranking are fixed | Incremental gain without agent rewrite | **Primary** |
| **C — ReAct loop** | Dynamic query generation closes the loop (plan → search → assess → widen → extract) | Adaptive recall, future interactive Q&A | **Horizon / Phase 2** |

### Route A — Prove routing is enough

- Add `route_chunks()` — SQL mirror of current `semantic_search` filter params (no embed at query time).
- Agent `query` strings become keyword/section predicates or digest section IDs.
- Optional later: ingest-time structured digests per tier-1 doc; gap-driven widening (tier ↑, drop filename filter) without LangGraph initially.
- **Exit criteria (after corpus stats + A/B):** pivot away from bare metadata routing if (a) any target workstream exceeds context budget after tier/filename filters *and* ingest digests aren’t in scope, or (b) treatment systematically misses tier-1 fields vs `semantic_search` control. Thresholds like 100 / 300 / 500 chunks per workstream are **placeholders** until Step 0 sizing runs — we only know ~1,241 raw files today (`8704b3b`), not parsed chunk density per workstream.

### Route B — Fix existing Vector Search

- Same agents and query shapes; fix filter pushdown, ranking, observability.
- **Exit criteria:** filter pushdown shows no recall gain, or tier reorder still dominates blind review.

### Route C — ReAct + retrieval tool (long-term pattern)

- One tool: `search_chunks(query, workstreams, filters, top_k) → {chunks, mode, scores}` (A or B underneath).
- Replace fixed N-tool scripts with adaptive rounds (max 3–5, hard cost caps).
- Wire `_data_room_gaps` to **trigger** widening retrieval, not only log gaps.
- Justifies the VDB more cleanly than today’s single-shot design — but adds LLM round cost and determinism risk for **batch** runs.
- MCP only if retrieval must be shared outside Databricks agents.

**The sequence I'd pick:** sync questions → corpus stats → **1-week A/B** on one agent → commit A, B-lite, or escalate upstream — **defer C** unless interactive UI is on the roadmap.

---

## Current experimental focus

### Step 0 — Prerequisite

On **1–2 companies**:

**Known:** Phase 1 ingested ~1,241 files to UC volume (`8704b3b` — *feat: complete phase 1 - full corpus ingested 1241 files to UC volume*). **Unknown:** how many survive `should_parse` + tier filters, and chunk count per workstream — required to interpret Route A viability and the placeholder thresholds in the A/B decision table below.

1. **Cell 8c** — coverage report; fix gaps via 8d if needed.
2. **Corpus stats** — chunks per workstream after `should_parse` + `tier ≤ 2` (decides whether “dump routed set” is viable).
3. **Pick test agent:** From already working ones.
4. **Golden checklist:** 15–20 required output fields for that agent.

```sql
SELECT r.company_name, ws AS workstream, COUNT(*) AS chunk_count
FROM uc13.ingestion.chunks c
JOIN uc13.classification.doc_relevance r
  ON c.file_name = r.filename AND c.company_name = r.company_name
LATERAL VIEW explode(r.workstream) t AS ws
WHERE r.should_parse = true AND r.priority_tier <= 2
GROUP BY 1, 2
ORDER BY 1, 3 DESC;
```

### Step 1 — A/B (after `route_chunks` shim)

| Arm | Retrieval | Everything else identical |
|-----|-----------|---------------------------|
| Control | Current `semantic_search` | Same prompts, filters, `top_k` |
| Treatment | `route_chunks` | Same |

**Score:** field pass/partial/miss, `_data_room_gaps` count, citation presence, runtime, retrieval `mode`.

| Outcome | Decision |
|---------|----------|
| Treatment ≥ control; corpus <100 chunks/ws* | **Commit A** for test agent |
| Treatment misses tier-1 fields; corpus >300 chunks/ws* | **Try B-lite** (VS filter pushdown only) |
| Both fail on same fields | **Upstream** — classifier, parser, or extraction prompt |
| Batch only + treatment wins | **Defer C** to Phase 2 |

\*Chunk-per-workstream thresholds are **provisional** until Step 0 corpus stats land.


---

## Sources (repo history & code)

Findings in **As is** come from reading `databricks/agents/shared/retrieval.py` and agent callers (inherited design). Recurring operational themes from commit history:

| Theme | Evidence |
|-------|----------|
| Corpus scale | `8704b3b` — feat: complete phase 1 - full corpus ingested 1241 files to UC volume |
| Retrieval / VS iteration | `0ca5a05` fixing retrieval query; `957dcad` fixing vector search fields; `09a0388` fixing priority tiers order |
| Chunking → retrieval quality | `10cb778` fixing chunking strategy and ingestion embedding; `ca97c3c` fixing chunking boundaries |
| Retrieval agent refactors | `44c4a17` refactoring enhancements for retrieval agents; `8f77543` agents notebook creation and first retrieval techniques |
| Performance / retrieval cost | `e1a687c` speeding up retrieval with haiku agents LLM calling |
| Coverage / empty retrieval ops | `12af382` adding coverage script for all agents |
| Recent retriever tuning | `1aed882` fix: financial subagents and kpis retrievers |
| Non-financial agents shallow vs BMA/FTA | BMA iterations `81d4ed1`–`6f39911`; FTA `3d73c93`–`3ee6c10`; CQA/Legal/QoE scaffolded `b3bbec9` with less enhancement depth |

---

## Document history

| Version | Date | Change |
|---------|------|--------|
| 1.0.1 | 2026-06-22 | Corpus sizing flag, exit criteria, commit sources, 1–2 company scope |
| 1.0.0 | 2026-06-22 | Initial team brief from retrieval review |
