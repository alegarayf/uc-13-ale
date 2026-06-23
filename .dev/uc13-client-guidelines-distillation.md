Section:      uc13-client-guidelines-distillation
Version:      1.0.0
Last updated: 2026-06-23
Scope:         Client (Austin / Rallyday) product guidelines — outputs, conditions, flags, agents, thresholds — distilled with implementation checklist
Status:        living reference (read-only synthesis)

# UC-13 client guidelines — distillation

Single entry point for **what Rallyday wants** from the PE diligence agent: product intent, output contracts, flag philosophy, thresholds, multi-agent architecture, and **what is built vs missing** in this repo.

**Primary sources (read these for authority):**

| Source | Path | Author / role |
|--------|------|---------------|
| Client diligence brief | [`databricks/Guidelines/Austin_email_guidelines.txt`](../databricks/Guidelines/Austin_email_guidelines.txt) | Austin Hough, Rallyday Partners |
| Engineering & product spec v2 | [`databricks/Guidelines/PE_Diligence_Agent_Spec_v2.pdf`](../databricks/Guidelines/PE_Diligence_Agent_Spec_v2.pdf) | Rallyday × Nimble Gravity; thresholds sourced from Austin email (May 2026) |
| Implementation mapping | [uc13-retrieval-reference.md](./uc13-retrieval-reference.md) §3, §11 | Repo synthesis |
| Pain / gap registry | [uc-13_pain_central.md](./uc-13_pain_central.md) §4–5 | Repo synthesis |
| Runtime contracts | [`databricks/agents/shared/agent_base.py`](../databricks/agents/shared/agent_base.py) | `Flag`, `Citation`, `ToolResult` |

**Companion docs:** [uc13-retrieval-reference.md](./uc13-retrieval-reference.md) (pipeline + retrieval), [uc13-retrieval-team-brief.md](./uc13-retrieval-team-brief.md) (retrieval routes).

---

## 1. Executive summary

UC-13 should behave like an **Associate doing first-pass diligence**: orient to the business, test whether the data supports the story, surface red flags, generate diligence questions, and help the deal team form an initial underwriting view.

| Principle | Source |
|-----------|--------|
| **Analysis > download automation** | Austin email, summary notes |
| **Source-linked work product** with confidence scoring | Austin email §9; PE spec §0.2 |
| **Thresholds are flags, not verdicts** — never block a deal | PE spec §0.5; Austin explicit in working session |
| **Phase 1: stated metrics as source of truth** — no cohort recomputation | PE spec §0.1 (v2 changes); §12.5 |
| **No composite deal scores** | PE spec §12.5 (v1 decision maintained) |

---

## 2. Core philosophy

### 2.1 What matters to the client

From **Austin email** (summary notes):

- Data-room download is a **low priority** — team will log in and save to their drive.
- **High value:** highlight new data-room additions, flag them, summarize them *(not built)*.
- **Highest value:** associate-style first-pass diligence.

Associate behavior (Austin email):

1. Orient us to the business; identify what matters.
2. Test whether the data supports the story.
3. Surface red flags.
4. Generate diligence questions.
5. Help form an initial underwriting view.

Overall goal (Austin email): *"Build an agent that can rapidly triage a data room, surface diligence questions, identify risk areas, and help our deal team form an initial underwriting view before we go deep with advisors."*

### 2.2 Non-negotiable design rules (PE spec v2)

| Rule | Detail | Source |
|------|--------|--------|
| **Flags, not verdicts** | Surface every threshold breach with context; present neutrally; investment professional decides materiality | PE spec §0.5 |
| **Never block a deal** | Threshold breach must not halt or veto a process | PE spec §0.5; §2 executive summary |
| **Citation & provenance** | Every fact: document name, page/tab/cell, raw quote, extraction confidence (high / medium / low) | PE spec §0.2 |
| **Phase 1 posture** | Extract stated figures; do not recompute NRR from cohorts, DSO from AR, etc. | PE spec §0.1; §4.3; §5.1 |
| **Prefer questions over heavy compute** | For red flags needing analytical lift, surface management questions rather than computing from raw data in Phase 1 | PE spec §0.5 |
| **Human-in-the-loop memory** | Overrides, “known/accepted” flags, cross-deal benchmarks in Databricks memory | PE spec §0.2 — **not implemented** |

### 2.3 Positive vs negative outcomes (vocabulary)

The system does **not** use pass/fail or composite scores.

| Construct | Meaning | Source |
|-----------|---------|--------|
| **Green / Yellow / Red** | Per-metric or durability flags | PE spec §3.3–§6; `agent_base.Flag` |
| **Supported / Plausible / Stretch** | Forecast assumption credibility | PE spec §9.1 |
| **Critical / Material / Track** | Cross-Analysis issue severity | PE spec §10.3 — **Phase 4 not built** |
| **`_data_room_gaps`** | Missing expected documents → information requests | Agents via `agent_base`; Austin §8–9 |
| **Confidence** high / medium / low | On extractions and citations | Austin §9; PE spec §11.3 |

**Negative signals:** Red/Yellow flags, data room gaps, reconciliation mismatches, missing expected KPIs, reduced confidence (e.g. non-banked deal without CIM).

**Positive signals:** Green ratings, Supported forecast assumptions, corroborated high-confidence citations — still evidence for the deal team, not an automated go/no-go.

---

## 3. Nine diligence categories → agents

Austin’s nine categories (Austin email §1–9) map to the PE spec workstream agents (PE spec §3–§11).

| # | Austin category | Spec agent | Primary workstream tags | Built? |
|---|-----------------|------------|-------------------------|--------|
| 1 | Business model overview | Business Model Agent | `BUSINESS_MODEL` | **Yes** |
| 2 | Customer quality & concentration | Customer Quality Agent | `CUSTOMER` | **Yes** |
| 3 | Financial trend analysis | Financial Trends Agent (+ sub-agents) | `FINANCIAL`, `QUALITY_EARNINGS` | **Yes** |
| 4 | KPI & operating metrics | KPI Agent | `KPI_OPS` | **Yes** |
| 5 | Contract & legal risk | Legal & Contracts Agent | `LEGAL` | **Yes** |
| 6 | Quality of revenue & earnings | Quality of Earnings Agent | `QUALITY_EARNINGS` | **Yes** |
| 7 | Forecast & underwriting support | Forecast Agent | `FORECAST`, `FINANCIAL` | **Partial** — folded into FTA `opex_sub_agent` |
| 8 | Red flags & diligence questions | Cross-Analysis Agent | — | **No** — local flags/gaps per agent only |
| 9 | Deal team workflow / output format | Orchestrator Agent | — | **No** — partial via `md_to_word.py` |

---

## 4. Multi-agent architecture & subagents

### 4.1 Five-phase target (PE spec §0.1)

```
Phase 1 · Ingestion          → indexed store; Priority Tier flagged
Phase 2 · Dual classification → Document Classifier + Company Profiler (parallel)
Phase 3 · Parallel workstreams → 7 agents (structured fact store + flags per workstream)
Phase 4 · Cross-Analysis     → reconciliation, CIM vs data room, top 10 issues
Phase 5 · Synthesis          → Orchestrator: memo, deck, grids, question lists
```

### 4.2 Implementation vs spec

| Spec phase | Spec agent(s) | Repo implementation | Status |
|------------|---------------|---------------------|--------|
| 1 | Ingestion Agent | `download_upload.py`, `ingestion_parser.py`, `ensure_coverage.py` | **Partial** — scripts, not LLM wrapper |
| 2 | Document Classifier + Company Profiler | `document_classifier.py`, `company_profiler.py` | **Yes** — sequential in workflow, not parallel |
| 3 | 7 workstream agents | 6 agent modules + FTA sub-agents | **6 of 7** — no standalone Forecast Agent |
| 4 | Cross-Analysis Agent | — | **No** |
| 5 | Orchestrator Agent | — | **No** |

### 4.3 Financial Trends sub-agents (implementation detail)

Not separate spec agents; FTA orchestrator delegates extraction:

| Sub-agent | Path | Role |
|-----------|------|------|
| `RevenueSubAgent` | `databricks/agents/subagents/workstream/financial/revenue_sub_agent.py` | Revenue trends, segments, geography |
| `EbitdaSubAgent` | `databricks/agents/subagents/workstream/financial/ebitda_sub_agent.py` | EBITDA, margins, addback awareness |
| `OpexSubAgent` | `databricks/agents/subagents/workstream/financial/opex_sub_agent.py` | Cost structure, projections (partial Forecast) |

Shared retrieval wrapper: `context_utils.semantic_search_with_fallback` (3–6 searches per sub-agent).

### 4.4 Agent hand-offs (conditions)

| Trigger | From → To | Source |
|---------|-----------|--------|
| Customer >20–25% revenue | Customer Quality → Legal | PE spec §4.4; Austin working session |
| `contract_trigger_list` in CQA output | → Legal agent input | `legal_contracts_agent.py`; workflow YAML |
| Addback schedule from FTA | → Quality of Earnings | PE spec §5.4; workflow YAML |
| Industry overlay confirmed | Company Profiler → all Phase 3 | PE spec §0.4; `company_profiler.py` |

---

## 5. Document priority tier

Austin: **5–10 documents contain ~90% of diligence-relevant signal** (PE spec §0.3).

| Priority | Document type | Banked? | Non-banked fallback |
|----------|---------------|---------|---------------------|
| 1 | CIM / OM | Always | Move to P2–3; absence = flag + reduced confidence |
| 2 | QofE report | Often | Skip; surface absence as flag |
| 3 | Financial forecast / model | Often Excel | P&L PDFs |
| 4 | KPI / dashboard file | Sometimes in CIM | Request if absent |
| 5 | Customer revenue workbook | Often standalone | Extract from CIM if embedded |
| 6 | Pipeline / backlog | Often standalone | Request explicitly |
| 7 | Cap table | Usually Excel | Request from founders |
| 8–10 | Top customer contracts | Varies | Flag if absent when concentration >20–25% |

**Non-banked condition (PE spec §0.3):** No CIM → note reduced confidence across sections; start with financials folder.

---

## 6. Output expectations

### 6.1 Per-agent Phase 3 contract (all workstream agents)

Each agent writes to `uc13.analysis.*` Delta tables with:

| Output element | Schema / behavior | Source |
|----------------|-------------------|--------|
| Structured facts | JSON tables, registers, ledgers per agent | PE spec §3.4–§8.3 |
| `flags` | `Flag`: metric, value, threshold, Red/Yellow/Green, note, source_doc, confidence | `agent_base.py`; PE spec thresholds |
| `citations` | document, location, ≤30-word quote, confidence | `agent_base.py`; PE spec §0.2 |
| `data_room_gaps` | Missing expected docs | `agent_base._add_gap`; Austin §8 |
| `reasoning_trace` | Retrieval steps (`ToolResult`) | `agent_base._tool_call` |

**Extraction discipline (agent prompts — reflects client bar):**

- Extract **only** what is explicitly stated; `null` if absent.
- Do **not** infer, reconcile across documents, or hallucinate.
- Company Profile block is **metadata only** — never cite as source.
- Limited same-document arithmetic only (e.g. margin % from stated revenue + GP in same doc).
- Conflicting figures → extract both, flag discrepancy; do not pick a winner.
- Legal agent: **facts only**, no legal advice (PE spec §7).

### 6.2 Austin example deliverables (category 9)

From Austin email §9:

- One-page company overview
- Deal risks and mitigants grid
- Diligence tracker
- Data room gap list
- Customer concentration summary
- Financial trend summary
- KPI dashboard
- Management question list
- Source-linked analysis with citations to documents / tabs / pages
- Confidence scoring: high / medium / low support for each conclusion

### 6.3 Orchestrator deliverables (Phase 5 — spec, not built)

From PE spec §11.2:

| Deliverable | Format | Primary use |
|-------------|--------|-------------|
| Diligence memo | Word (.docx) | IC pre-read |
| Executive deck | PowerPoint (~15 slides) | IC meeting |
| One-page company overview | PDF | Senior partner / pre-LOI |
| Risks & mitigants grid | Word / PPT | Risk × severity × evidence × mitigant |
| KPI dashboard | PDF / PPT | Value vs benchmark, trend, flag |
| Management question list | Word | Top 10 each: mgmt, banker, advisor |
| Reconciliation log | PDF | QofE / counsel kickoff |
| Data room gap list | PDF | Information request to seller/banker |
| Diligence tracker | Word / Excel | Living flag tracker |

**Partial today:** `databricks/jobs/scripts/md_to_word.py` — not full Orchestrator assembly.

**Citation format (PE spec §11.4):**

> `"[Claim]. ([Document name], [page/tab/cell], [extraction confidence])"`

### 6.4 Cross-Analysis outputs (Phase 4 — not built)

From PE spec §10.4:

- Reconciliation log (match / mismatch / cannot check)
- CIM claims vs data room list
- Top 10 diligence issues (severity × deal relevance)
- Consolidated data room gap list

Example Austin outputs for category 8 (Austin email §8): Top 10 diligence issues, Top 10 questions, missing data request list, “things that do not reconcile,” “claims in CIM not supported by data room.”

### 6.5 Section-level confidence (Orchestrator — spec)

From PE spec §11.3:

| Confidence | Trigger |
|------------|---------|
| **High** | Primary source (audited financials, signed contract, structured extract); corroborated by ≥1 other doc |
| **Medium** | Single source or CIM only; partial corroboration |
| **Low** | Narrative/unsourced; contradicted; or inferred because data missing. **Non-banked deal → all sections Medium until financials confirmed** |

---

## 7. Austin capability questions — product bar

From Austin email (summary notes + questions for NG):

| Question | Retrieval / implementation relevance | Status |
|----------|--------------------------------------|--------|
| Cite exact source document, page, Excel tab/cell? | Chunks: `file_name`, `section_header`, `page_start`, `source_type` | **Partial** — page/section yes; cell refs inconsistent ([uc-13_pain_central.md](./uc-13_pain_central.md) A-07) |
| Compare across documents / flag inconsistencies? | Cross-Analysis Agent | **Deferred** — not a retrieval feature |
| Structured outputs by diligence category? | Six agents → `uc13.analysis.*` | **Yes** |
| Customize by industry / business model? | `company_profiler` overlays | **Yes** — healthcare, tech_services, b2b_saas, industrial, consumer |
| Data request list for missing items? | `_data_room_gaps` per agent | **Yes** |
| Leverage prior deals in same industry? | Databricks memory layer | **Deferred** (Austin email; PE spec §0.2) |
| Flag new data-room additions? | — | **Not built** (Austin summary notes) |

---

## 8. Threshold reference (Austin primary)

PE spec **Appendix A** reproduces Austin Hough email (May 20, 2026) as authoritative. Agents use `Flag` with `severity` Red / Yellow / Green.

### 8.1 Tech services

| Metric | Severity | Threshold | Austin note (abridged) |
|--------|----------|-----------|------------------------|
| Net Revenue Retention | Red | <~90% | Churn pressure, weaker stickiness, project/transactional model |
| Gross Revenue Retention | Red | <~80–85% | Explicit threshold |
| Gross margin | Red | <~40% | Lower-value work, weak utilization; premium digital 45–50%+ preferred |
| Top customer concentration | Red | >~25% revenue | Concentration risk if project-driven, uncommitted |
| Organic revenue growth | Red | <~10–15% | Questions on positioning, sales engine, demand |
| EBITDA margin | Yellow | <~10–15% | Depends on stage — flag anyway |
| Average account size | Yellow | <~$100–200K ACV | SMB exposure, lower durability |
| Revenue model | Yellow | Mostly one-time project work | Not necessarily deal-killer — deserves flag |
| Delivery model | Yellow | Contractor-heavy or single-geography (esp. India) | Delivery model risk |
| Utilization | Green ≥75%; Yellow 65–75%; Red <65% | Public benchmark — Austin did not specify directly |
| Backlog / pipeline coverage | Yellow | <6 months revenue | Key to forecast credibility |

### 8.2 Healthcare services

| Metric | Severity | Threshold | Austin note (abridged) |
|--------|----------|-----------|------------------------|
| Revenue growth (same-store) | Red | <~5–10% | Prompt questions on referral, reimbursement, competition, labor |
| Gross margin | Red | <~30–35% | Wage pressure, utilization, payor mix |
| EBITDA margin | Red | <~10% | Labor inefficiency, reimbursement, scheduling, scale |
| Referral / customer concentration | Red | >~20–25% | Treat like tech customer concentration |
| Government / payor concentration | Yellow | >~50% Medicare/Medicaid/VA/managed care | Heavy govt reimbursement dependency |
| Episodic / event-driven revenue | Yellow | Hard to forecast, inconsistent referrals | Similar to project revenue in tech |
| Employee turnover | Red | >~30–40% | Quality, hiring cost, capacity, compliance, margin |
| Recruiting funnel | Yellow | Constrained | Can cap growth |
| Utilization / productivity | Yellow | Low for clinic/home/field | Major margin driver; flag if absent |
| Compliance / quality | Red | **Any** history of audits, surveys, licensing, billing | Not just open issues |
| Multi-site visibility | Yellow | Cannot produce location-level metrics | Management capability flag |

### 8.3 Business Model — revenue durability (PE spec §3.3)

| Rating | Condition |
|--------|-----------|
| **Green** | ≥70% recurring or contracted, OR repeat-rate >80% with multi-year tenure |
| **Yellow** | 40–70% recurring/contracted, or strong informal repeat relationships |
| **Red** | <40% recurring AND no demonstrated repeat; OR mostly one-time project work |

Implemented in `business_model_agent.py` (`_apply_revenue_durability_flag`).

### 8.4 Legal — clause risk flags (PE spec §7.2)

Examples (not exhaustive):

| Condition | Severity |
|-----------|----------|
| CoC consent required + customer >20% revenue | Red |
| Termination for convenience <60 days, no penalty + material customer | Red |
| Anti-assignment captures CoC + material counterparty | Yellow |
| No contract found for customer >20% | **Data room gap** (high-priority info request) |

### 8.5 Quality of Earnings — addback tiers (PE spec §8.1)

| Tier | Description |
|------|-------------|
| Tier 1 | Strong one-time, documented |
| Tier 2 | Defensible owner/private costs |
| Tier 3 | Stretch — execution risk post-close |
| Tier 4 | Reach — immediate management question |

Rules: no supporting doc → auto Tier 4; single addback >5% reported EBITDA without VDR docs → flag.

### 8.6 Forecast — credibility rubric (PE spec §9.1)

| Rating | Definition |
|--------|------------|
| **Supported** | Consistent with 3-year history OR backed by contracted/pipeline/documented price change |
| **Plausible** | Step-change from history but named driver exists |
| **Stretch** | Outside historical envelope or contradicted by trends |

Downside sensitivities (PE spec §9.3): top-customer loss, growth haircut, margin compression, addback erosion, pipeline miss — for deal team LBO model.

### 8.7 Cross-Analysis severity (PE spec §10.3 — not built)

| Severity | Definition |
|----------|------------|
| **Critical** | Could change LOI price/structure or block close |
| **Material** | Needs understanding; may shape underwriting |
| **Track** | Worth noting; not deal-shaping |

---

## 9. Industry overlays

From PE spec §0.4; implemented in `company_profiler.py`:

| Overlay | Primary thresholds source |
|---------|---------------------------|
| `tech_services` | Austin email (primary) |
| `healthcare` | Austin email (primary) |
| `b2b_saas`, `industrial`, `consumer` | Public benchmarks (secondary) until Rallyday deal data accumulates |

KPI extraction sets differ per overlay (PE spec §6.3). Overlay-specific BMA fields under `customer_profile_json → overlay_specific`.

---

## 10. Explicitly deferred (not Phase 1)

From PE spec §12.5 and Austin email:

- Cross-document reconciliation (recomputing NRR, DSO, etc.)
- Composite deal scoring
- Cross-Analysis Agent
- Orchestrator Agent + full deliverable assembly
- Standalone Forecast Agent
- Databricks memory / HITL overrides
- Prior-deal / portfolio benchmarks
- Voice-of-customer, market sizing, 100-day plan
- Flagging new data-room additions (Austin wish — not in PE spec phases)

---

## 11. Agent-by-agent implementation checklist

Quick reference: **spec contract vs repo today**. Sources: PE spec §3–§11, file inventory in [uc13-retrieval-map.md](./uc13-retrieval-map.md), maturity notes in [uc-13_pain_central.md](./uc-13_pain_central.md) §4.

### 11.1 Pipeline & cross-cutting

| Component | Spec output / behavior | Implemented | Gap |
|-----------|------------------------|-------------|-----|
| Ingestion Agent | Priority Tier first; indexed store | Scripts only | No LLM ingestion wrapper; no “new file” alerting |
| Document Classifier | Workstream tags, priority tier, `should_parse` | `document_classifier.py` | — |
| Company Profiler | Industry overlay, deal type | `company_profiler.py` | — |
| Citation layer | Every fact cited | `Citation` + agent prompts | Excel cell depth variable |
| Flag layer | Red/Yellow/Green vs Austin thresholds | `Flag` + per-agent `_add_flag` | Not all agents at BMA/FTA depth |
| HITL memory | Overrides persist per deal | — | **Not built** |
| Cross-Analysis | Reconciliation, top 10, CIM vs VDR | — | **Not built** |
| Orchestrator | Memo, deck, grids, questions | `md_to_word.py` partial | **Not built** |

### 11.2 Phase 3 workstream agents

| Agent | Delta table | Spec outputs (abridged) | Code | Flags / thresholds | Maturity |
|-------|-------------|-------------------------|------|-------------------|----------|
| **Business Model** | `uc13.analysis.business_model` | Revenue model tag, durability G/Y/R, overlay confirmation, gaps | `business_model_agent.py` | Revenue durability G/Y/R | **Strong** — most iterated |
| **Customer Quality** | `uc13.analysis.customer_quality` | Top 10 concentration, NRR/GRR, `contract_trigger_list`, gaps | `customer_quality_agent.py` | Austin tech + healthcare thresholds | **Built** — needs BMA/FTA-level hardening |
| **Financial Trends** | `uc13.analysis.financial_trends` | Revenue/margin trends, WC, addback passthrough, gaps | `financial_trends_agent.py` + 3 sub-agents | Austin FTA thresholds | **Strong** — recent retriever work (`1aed882`) |
| **KPI** | `uc13.analysis.kpi` | KPI table, missing KPI list, delivery model flag | `kpi_agent.py` | Austin KPI thresholds per overlay | **Built** — recent retriever fixes |
| **Legal & Contracts** | `uc13.analysis.legal_contracts` | Contract register, CoC list, litigation, gaps | `legal_contracts_agent.py` | Clause rules §7.2 | **Built** — scaffolded; less depth than BMA/FTA |
| **Quality of Earnings** | `uc13.analysis.quality_of_earnings` | Addback ledger, revenue quality flags, EBITDA range | `quality_of_earnings_agent.py` | Tier 1–4 framework | **Built** — needs iteration; depends on FTA |
| **Forecast** | *(no dedicated table)* | Credibility table, revenue build, downside sensitivities | Partial in `opex_sub_agent.py` | Supported/Plausible/Stretch | **Partial** — no `forecast_agent.py` |

### 11.3 FTA sub-agents (implementation)

| Sub-agent | Spec scope covered | Retrieval | Notes |
|-----------|-------------------|-----------|-------|
| `RevenueSubAgent` | Revenue trend, by segment/geography | 5–6 `semantic_search_with_fallback` | — |
| `EbitdaSubAgent` | EBITDA, margins, addback schedule extract | 4 searches | Passes addbacks to QoE |
| `OpexSubAgent` | Cost structure, **partial** forecast/projections | 3 searches | Closest to Forecast Agent |

### 11.4 Austin category → deliverable checklist

| Austin § | Category | Structured extraction | Local flags/gaps | Consolidated top-10 / memo |
|----------|----------|----------------------|------------------|---------------------------|
| 1 | Business model | ✅ BMA | ✅ | ❌ Orchestrator |
| 2 | Customer quality | ✅ CQA | ✅ | ❌ Cross-Analysis |
| 3 | Financial trends | ✅ FTA | ✅ | ❌ |
| 4 | KPIs | ✅ KPI | ✅ | ❌ |
| 5 | Legal / contracts | ✅ Legal | ✅ | ❌ |
| 6 | QoE flags | ✅ QoE | ✅ | ❌ |
| 7 | Forecast / underwriting | ⚠️ Partial | ⚠️ | ❌ |
| 8 | Red flags / questions | ⚠️ Per-agent only | ✅ | ❌ Cross-Analysis |
| 9 | Workflow outputs | ⚠️ `md_to_word` | ✅ gaps | ❌ Orchestrator |

**Legend:** ✅ implemented at Phase 3 level · ⚠️ partial · ❌ not built

### 11.5 Build sequence (PE spec §12.3 — for context)

| Sprint | Agent(s) | Repo status (Jun 2026) |
|--------|----------|------------------------|
| 2 | Financial Trends | **Done** (ongoing tuning) |
| 3 | CQA + BMA | **Done** (BMA stronger) |
| 4 | KPI + QoE | **Done** (QoE needs depth) |
| 5 | Legal + Forecast | Legal done; Forecast partial |
| 6 | Cross-Analysis | **Not started** |
| 7 | Orchestrator + full output | **Not started** |

---

## 12. Runtime primitives (code ↔ spec)

From [`databricks/agents/shared/agent_base.py`](../databricks/agents/shared/agent_base.py):

```python
# Flag — maps to PE spec threshold presentation
@dataclass
class Flag:
    metric: str
    value: str          # as extracted — never recomputed
    threshold: str      # e.g. "<~40%"
    severity: str       # "Red" | "Yellow" | "Green"
    note: str           # Austin's note — presented neutrally
    source_doc: str
    confidence: str     # "high" | "medium" | "low"

# Citation — maps to PE spec §0.2
@dataclass
class Citation:
    claim: str
    document: str
    location: str       # page, tab, section, cell
    confidence: str
    raw_text: str       # ≤30 words
```

Shared financial extraction rules: [`databricks/agents/subagents/workstream/financial/shared_prompts.py`](../databricks/agents/subagents/workstream/financial/shared_prompts.py).

---

## 13. One-line summary

**Austin wants an associate that produces source-linked, structured diligence by category, flags directional risks (never blocking deals), surfaces gaps as questions, and eventually reconciles across documents into IC-ready deliverables — with Phase 1 treating stated figures as truth and FTA sub-agents handling deep financial extraction within the workstream layer.**

---

## Document history

| Version | Date | Change |
|---------|------|--------|
| 1.0.0 | 2026-06-23 | Initial distillation from Austin email, PE spec v2 PDF, uc13-retrieval-reference, agent code |
