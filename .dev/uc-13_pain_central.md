Section:      uc-13_pain_central
Version:      1.0.0
Last updated: 2026-06-20
Scope:         Central registry of UC-13 pains, blockers, issues, open questions, and operational failure modes
Status:        living document — update when pains close or new ones are discovered

# UC-13 pain central

Single entry point for **documented** problems, blockers, risks, and unresolved decisions affecting **Use Case 13** (PE data-room diligence pipeline) and **retrieval**. Synthesized from repo docs and commit history — not a live incident log.

**How to use**

| Action | Where |
|--------|-------|
| Understand retrieval design debt | §1 Active — Retrieval layer |
| Debug empty/wrong context at runtime | §2 Operational symptoms |
| See what was painful historically | §6 Historical (mitigated) |
| Plan Route A/B work and remediation | [uc13-remediation-plan.md](./uc13-remediation-plan.md) |
| Decide strategic direction (keep VS?) | §7 Open questions + [uc13-retrieval-alternatives-assessment.md](./uc13-retrieval-alternatives-assessment.md) |
| Deep dive on one pain | Follow **Source** links |

**Status legend**

| Status | Meaning |
|--------|---------|
| **OPEN** | Documented, not resolved in code or product |
| **MITIGATED** | Workaround or partial fix exists; root cause may remain |
| **WATCH** | Depends on deployment assumptions or unvalidated in production |
| **DEFERRED** | Explicitly out of Phase 1 scope per spec or team decision |

---

## Executive summary

| Category | OPEN | MITIGATED | WATCH | DEFERRED |
|----------|------|-----------|-------|----------|
| Retrieval layer design | 7 | 2 | 3 | — |
| Pipeline / ingestion ops | 4 | 5 | 2 | — |
| Agent maturity | 4 | 2 | — | — |
| Product / spec gaps | 3 | — | — | 4 |
| Monorepo / integration | 4 | — | — | — |
| **Total distinct items** | **~22** | **~9** | **~5** | **~4** |

**Headline:** Retrieval **works as batch glue** but carries **documented design debt** (ranking discarded, filters post-hoc, no observability). **Upstream** pains (index sync, workstream coverage, chunk quality) still cause empty retrieval in ops. **Downstream**, six of seven Phase 3 agents exist but non-financial agents need iteration; Cross-Analysis and Orchestrator are unbuilt. **No Garden API** exposes UC13 outputs.

---

## 1. Active — Retrieval layer

Source of truth for design critique: [retrieval-layer-review.md](./retrieval-layer-review.md). Consolidated context: [uc13-retrieval-reference.md](./uc13-retrieval-reference.md) §5.

| ID | Pain | Status | Impact | Source |
|----|------|--------|--------|--------|
| R-01 | **Semantic ranking discarded** — VS similarity order thrown away; SQL `ORDER BY priority_tier`; Python may re-sort again. Final chunks are tier-biased, not query-similar. | OPEN | Wrong/off-topic context; misleading `semantic_search` name | retrieval-layer-review §1 |
| R-02 | **Metadata filters not pushed to Vector Search** — `workstream`, `priority_tier` indexed but unused at `query_index`; fetch `top_k×3` globally, filter on driver. | OPEN | Starved results under aggressive filters; wasted VS work | retrieval-layer-review §2 |
| R-03 | **Filename-filter retry band-aid** — BMA and FTA duplicate `semantic_search_with_fallback`; retries re-embed + re-query. | OPEN | Double cost; duplicated logic | retrieval-layer-review §2; uc13-retrieval-map |
| R-04 | **No company scoping at search time** — `company_name` not in `columns_to_sync`; global NN then SQL discard. | WATCH | Latency/cost if multi-company index; isolation risk | retrieval-layer-review §3 |
| R-05 | **Blunt keyword fallback** — any exception (incl. empty VS) → `LIKE` on 5 tokens; no `mode` in return or traces. | OPEN | Silent degradation; confidence scoring blind | retrieval-layer-review §4; failure-taxonomy |
| R-06 | **SQL string interpolation** — `company_name`, chunk IDs, keywords not parameterized. | OPEN | Breakage / injection risk with special chars in names | retrieval-layer-review §5 |
| R-07 | **Driver-bound two-hop** — embed → VS → Spark SQL → `.collect()` → Python per tool call (~45–55/run). | OPEN | Slow runs; doesn't compose as a service | retrieval-layer-review §6 |
| R-08 | **Join coupling** — `chunks.file_name = doc_relevance.filename`; drift drops workstream/tier at hydrate. | WATCH | Empty `workstream_filter` results | retrieval-layer-review §7 |
| R-09 | **Split priority logic** — `source_type_priority` in retrieval; CIM-first + char limits in `context_utils`; BMA has own path. | OPEN | Inconsistent context assembly across agents | retrieval-layer-review §7 |
| R-10 | **No similarity scores / typed return** — `-> list` of Spark Rows. | OPEN | Can't tune ranking or debug recall | retrieval-layer-review §7 |
| R-11 | **Strategic: embeddings may be unnecessary** — current behavior ≈ metadata routing; VS adds infra without using similarity. | OPEN | Cost/complexity vs simpler SQL router | uc13-retrieval-alternatives-assessment |

**Refactor backlog** (ordered, not scheduled): company_name + source_type in index → VS metadata filters → explicit ranking merge → structured `{chunks, mode, scores}` → consolidate fallbacks → parameterized SQL. See retrieval-layer-review § Refactor priorities.

---

## 2. Operational — Runtime symptoms & fixes

Documented troubleshooting paths. Symptom → cause → fix.

| ID | Symptom | Likely cause | Fix / mitigation | Status | Source |
|----|---------|--------------|------------------|--------|--------|
| O-01 | **Company profiler all nulls** | Parser incomplete or **index not synced** after embeddings write | Wait for `_wait_for_index_sync`; check VS UI | MITIGATED (if sync honored) | workflows/README §7 |
| O-02 | **Empty agent retrieval** (0 chunks) | Workstream tag mismatch; missing coverage; aggressive filters | Cell 8c coverage report → `ensure_coverage.ingest_missing` | MITIGATED (manual) | uc13-retrieval-reference §10.3 |
| O-03 | **Profiler run before parser** | Workflow ordering violation | Run parser first; dependency in YAML | MITIGATED | workflows/README §6 |
| O-04 | **Vector Search unavailable** | Endpoint down, missing index | Keyword fallback (degraded) | MITIGATED | failure-taxonomy; integration-seams |
| O-05 | **Workstream tag drift** | No single const module for `BUSINESS_MODEL`, etc. | Convention only; classifier + agents must stay aligned | WATCH | known-coupling-surfaces |
| O-06 | **`ensure_coverage` not in workflow** | Gap fill is ad hoc | Run from `test_pipeline.ipynb` 8c/8d when needed | OPEN | uc13-retrieval-map; CLAUDE.md |
| O-07 | **Index sync failure ignored** | `_wait_for_index_sync` prints warning; run may continue | Manual `sync_index`; do not run agents | OPEN | ingestion_parser.py |
| O-08 | **`data_room_gaps`: No CIM found** | CIM absent from data room | Add to SharePoint; re-run Phase 1 | — | workflows/README §7 |
| O-09 | **Classifier all BACKGROUND** | LLM endpoint down / rate limited | Check serving; retry | — | workflows/README §7 |

---

## 3. Active — Pipeline & ingestion

| ID | Pain | Status | Impact | Source |
|----|------|--------|--------|--------|
| P-01 | **Chunking / embedding quality** — bad boundaries, wrong vector fields → retrieval misses | MITIGATED | Historical; may recur on new doc types | PROJECT_HISTORY blockers |
| P-02 | **Excel merged cells** — `read_only=True` hid headers → bad table chunks | MITIGATED | `_expand_merged_cells()` required | CLAUDE.md; PROJECT_HISTORY |
| P-03 | **Image-only financial PDF pages** — no text without vision path | MITIGATED | Vision + sparse-page detection | PROJECT_HISTORY |
| P-04 | **`ai_parse_document` v2.0** — `page_id` on `bbox[0]` | MITIGATED | Fixed in parser | PROJECT_HISTORY |
| P-05 | **Parser full rebuild required** after parser changes — Cell 7 must re-run | OPEN | Stale chunks if forgotten | CLAUDE.md |
| P-06 | **Index sync blocks pipeline** — post-parse wait; failure path unclear | OPEN | Stale or empty retrieval | ingestion_parser `_wait_for_index_sync` |
| P-07 | **Workflow LLM default mismatch** — YAML defaults Llama 70B; notebooks use Sonnet | WATCH | Truncation if wrong endpoint used | uc13-retrieval-reference §7.2 |
| P-08 | **Performance** — slow retrieval + agent runs | MITIGATED | Sub-agents, Haiku aux; still heavy | PROJECT_HISTORY |

---

## 4. Active — Agent & extraction maturity

| ID | Pain | Status | Impact | Source |
|----|------|--------|--------|--------|
| A-01 | **LLM output truncation** on large JSON schemas (FTA, EBITDA) | MITIGATED | Sonnet + explicit `max_tokens`; still fragile | PROJECT_HISTORY |
| A-02 | **Haiku / Llama 8K silent floor** | MITIGATED | Documented; Sonnet required for 10–16K | CLAUDE.md |
| A-03 | **Non-financial agents shallow** — CQA, Legal, QoE, KPI need BMA/FTA-level iteration | OPEN | Weaker outputs vs spec | PROJECT_HISTORY pending |
| A-04 | **Financial agent hardening** — P&L/EBITDA/addbacks recent (Jun 17–19) | OPEN | Unvalidated on 2+ companies | PROJECT_HISTORY |
| A-05 | **KPI / sub-agent retriever fixes** — latest commit `1aed882` | MITIGATED | Recent; may need more tuning | PROJECT_HISTORY |
| A-06 | **E2E validation pending** — full `test_pipeline.ipynb` after merge | OPEN | Unknown regressions | PROJECT_HISTORY |
| A-07 | **Citation depth variable** — page/section yes; Excel cell refs inconsistent | WATCH | Austin spec bar | uc13-retrieval-reference §3.1 |

---

## 5. Product & spec gaps

| ID | Gap | Status | Notes | Source |
|----|-----|--------|-------|--------|
| S-01 | **Forecast Agent** — spec Phase 3 agent #7 | DEFERRED | Partially in FTA `opex_sub_agent` | PE spec; uc13-retrieval-reference §11 |
| S-02 | **Cross-Analysis Agent** — reconciliation, CIM vs data room | DEFERRED | Not built | PE spec |
| S-03 | **Orchestrator Agent** — memo, one-pager, risk grid | DEFERRED | Not built | PE spec |
| S-04 | **Databricks memory / HITL overrides** | DEFERRED | Spec §0.2 | PE spec |
| S-05 | **UC13 → Garden UI** — no API for `uc13.analysis.*` | OPEN | Product decision pending | open-questions; PROJECT_HISTORY |
| S-06 | **Cross-document inconsistency detection** | DEFERRED | Not a retrieval feature; needs Phase 4 | Austin brief |
| S-07 | **Prior-deal / portfolio benchmarks** | DEFERRED | Spec memory layer | Austin brief |

---

## 6. Monorepo & integration

| ID | Pain | Status | Impact | Source |
|----|------|--------|--------|--------|
| M-01 | **Branch divergence** — feature branch +42 / develop −3 (chatbot) | OPEN | Blocks merge + E2E | PROJECT_HISTORY |
| M-02 | **Genie chatbot fate** — on develop, absent on feature branch | OPEN | Merge conflict | PROJECT_HISTORY |
| M-03 | **`garden` vs `uc13` catalog convention** unconfirmed | OPEN | Wrong table refs in deploy | open-questions |
| M-04 | **Production auth** — frontend → API/AI none in dev | OPEN | Blocks production Garden | open-questions |
| M-05 | **Workflow scheduling** — not wired to `npm run dev` | OPEN | Manual/job-only UC13 runs | PROJECT_HISTORY |
| M-06 | **`semantic_search` signature change** — breaks all Phase 3 agents | WATCH | High blast radius on retrieval refactor | dependency-graph |

---

## 7. Open questions

### Retrieval-specific (unresolved)

| ID | Question | Impact | Closes when | Source |
|----|----------|--------|-------------|--------|
| Q-R01 | Is **tier-biased ranking** intentional product behavior? | Refactor priority; prompt assumptions | Product decision + eval set | retrieval-layer-review |
| Q-R02 | Should **keyword fallback** be explicit in traces (`retrieval_mode`)? | L5 observability; ToolResult confidence | Trace schema updated | retrieval-layer-review |
| Q-R03 | **Multi-company** shared `embeddings_index` in production? | Urgency of R-04 fix | Deployment model confirmed | retrieval-layer-review |
| Q-R04 | **How married are we to semantic retrieval?** | Architecture fork: VS vs SQL router + digests | Team decision | [qs_for_sync.md](../qs_for_sync.md) |
| Q-R05 | How often does keyword fallback fire in real runs? | Accept vs fix R-05 | Log analysis on one full pipeline | retrieval-layer-review §C |

### Sync / planning (repo root)

| ID | Question | Source |
|----|----------|--------|
| Q-S01 | **How much time** do we actually have? | qs_for_sync.md |

### Product / platform (adjacent)

See [architecture/rallyday/open-questions.md](./architecture/rallyday/open-questions.md): Garden rules execution, UC13 UI surfacing, deployment topology, shared types package.

---

## 8. Historical — Mitigated pains (commit-driven)

From [PROJECT_HISTORY.md](../PROJECT_HISTORY.md) § Blockers & pain points. Listed so repeat failures are recognizable.

| Theme | Manifestation | Resolution commits (examples) |
|-------|---------------|-------------------------------|
| Retrieval query bugs | Wrong VS fields, bad query | `0ca5a05`, `957dcad` |
| Chunking strategy | Bad boundaries, embedding mismatches | `10cb778`, `ca97c3c` |
| Priority tier order | Wrong tier sort | `09a0388` |
| Retrieval agent refactor | Structural cleanup | `44c4a17` |
| Speed | Slow retrieval runs | `e1a687c` (Haiku aux), `2ff08db` (sub-agents) |
| Financial retrievers | Sub-agent + KPI retriever gaps | `1aed882` |
| SharePoint / upload | Early connectivity | `710ef5b`, `7d667e2` |
| Databricks runtime | spark, dbutils, volumes | `9a413af`, `7916561` |

**Note:** Historical fixes do not close R-01–R-11 design debt; they addressed **correctness and performance within the current architecture**.

---

## 9. Investigation backlog

Not yet done — checklist from [retrieval-layer-review.md](./retrieval-layer-review.md) § Follow-ups.

| Area | Key question | Done when |
|------|--------------|-----------|
| A. Index vs table drift | Embeddings columns vs `columns_to_sync` vs filter needs | Comparison table written |
| B. Ranking / recall | Empty or sub-`min_results` retrievals in real notebook runs | Spot-check logs |
| C. Fallback frequency | Vector vs keyword mode in production | Metric or decision |
| D. Duplicate fallbacks | Diff BMA vs `context_utils` wrappers | Diff documented |
| E. Multi-tenant | Cross-company chunk IDs before SQL filter | SQL count confirmed |
| F. Context assembly | CIM-first vs `source_type_priority` interaction | Sequence documented |
| G. SQL safety | Special chars in filenames / company names | Risk assessment |
| H. Refactor blast radius | Files to touch if `semantic_search` API changes | Checklist complete |

---

## 10. Failure taxonomy (candidates)

From [architecture/rallyday/failure-taxonomy.md](./architecture/rallyday/failure-taxonomy.md) — **not yet registered** as formal cause classes:

| Observed mode | Layer | UC13 retrieval link |
|---------------|-------|---------------------|
| Vector Search unavailable | L5 Infrastructure | R-05 keyword fallback |
| LLM truncation | L2 Model | A-01 (extraction, not retrieval) |
| Workstream tag invalid | L0 Input | O-05, O-02 |

---

## 11. Related documentation

| Document | Role |
|----------|------|
| [uc13-retrieval-reference.md](./uc13-retrieval-reference.md) | Master UC13 + retrieval reference |
| [retrieval-layer-review.md](./retrieval-layer-review.md) | Adversarial retrieval design review |
| [uc13-retrieval-map.md](./uc13-retrieval-map.md) | File inventory, call graph |
| [uc13-retrieval-alternatives-assessment.md](./uc13-retrieval-alternatives-assessment.md) | Whether VS is required; router alternative |
| [uc13-remediation-plan.md](./uc13-remediation-plan.md) | **Central plan** — Routes A & B, shared fixes, weak spots, A/B protocol |
| [uc13-retrieval-decision.md](./uc13-retrieval-decision.md) | Route gates, adversarial summary, 1-week A/B experiment |
| [PROJECT_HISTORY.md](../PROJECT_HISTORY.md) | Branch status, historical blockers |
| [databricks/CLAUDE.md](../databricks/CLAUDE.md) | Developer constraints, test order |
| [databricks/workflows/README.md](../databricks/workflows/README.md) | Ops troubleshooting |

---

## 12. Changelog

| Version | Date | Change |
|---------|------|--------|
| 1.0.0 | 2026-06-20 | Initial centralization from retrieval-layer-review, PROJECT_HISTORY, architecture folder, workflows README, uc13-retrieval-reference, uc13-retrieval-alternatives-assessment, qs_for_sync.md |
