# UC13 Pipeline — Project Status & Near-Term Plan

**Author:** Alejandro Garay  
**Audience:** Project management  
**As of:** 2026-07-13

---

## Summary

The UC13 diligence pipeline ingests PE data rooms, runs seven workstream agents (financial trends, legal, business model, customer quality, KPI, quality of earnings, company profiler), and produces structured analysis plus stakeholder reports.

I have already shipped **index sync safety** (parser stops if the vector index is stale), **broad validation** (all agents on Elder Care plus a second company, Clearsulting), and **integration cleanup** (consistent catalog naming across agents and scripts). Retrieval evaluation exists for Elder Care with recorded baselines; financial trends and legal have scored golden checklists.

**Current blocker:** a live smoke test on Databricks—code and automated tests are done, but I need to run the pipeline, capture output, and sign off. Each run takes **~2 hours** on the cluster.

**Still in the hardening sequence:** close out integration (smoke + audit), then **retrieval consolidation**—the first pass of shared retrieval improvements with regression checks.

**Also on my radar:** evaluation for every agent, a data-room completeness score, executive summary improvements, and eventually merging Hector’s repo.

---

## Where I am now

### Blocking: post-integration smoke test

I need to run a short end-to-end path on Databricks—full ingestion for Elder Care, then the business model agent—and confirm the pipeline still produces results and that company profile data loads correctly for that tenant. This is the last live proof that the merged codebase behaves on real infrastructure before I call integration done and move on to retrieval work. I will save the run output and commit reference for the attestation record.

- **Time:** ~2 hours per Databricks session (ingestion rebuild, index sync, one agent).

### After smoke passes

- Wrap up integration: housekeeping on workflow config (not deployed yet), exit checklist, changelog, sync to remote.
- **Closing audit:** validation expansion was audited in early July; integration still needs a formal review and sign-off to close the loop before retrieval changes begin.

---

## What I have already completed

| Area | Outcome |
|------|---------|
| **Index sync safety** | Parser halts on sync failure instead of continuing with a stale vector index |
| **Validation expansion** | All seven agents exercised on Elder Care; Clearsulting as second company; full pipeline end-to-end attested |
| **FTA / Legal scores** | Financial trends **16/18**; Legal **7/11** on Elder Care—held through validation |
| **Retrieval evaluation** | Harness, Elder Care gold labels, stored baselines; ablation runs proved current ranking defaults |
| **Catalog convention (code)** | Naming rules enforced in automated tests across agents and scripts |
| **Stakeholder report path** | Bundle builder and one-pager compression shipped; LLM narrative on executive sections when configured |
| **Legal agent** | Schema guards, stakeholder report, golden checklist |

---

## Next: retrieval consolidation

This is the last planned hardening phase before the pipeline hardening track is complete. It is the first work that touches the **shared retrieval layer** (search, fallback, financial context assembly), which I intentionally left unchanged during integration.

**Why it matters:**

- **Context assembly:** OPEX pools multiple queries into one large budget; revenue and EBITDA do similar things. Consolidating how context is built reduces duplication and makes behavior easier to test and tune.
- **Financial fallback:** Financial sub-agents still use a path that diverges from other agents; aligning them reduces silent drift.
- **Join integrity check:** Catches cases where classified documents and embedded chunks get out of sync, which can return empty context with no obvious error.
- **Optional metadata filters:** Vector search can filter by workstream and priority tier; the capability is built but turned off. Turning it on requires a controlled comparison on Elder Care (recall must not materially drop) and a second person reviewing the results—not me alone.

**Done when:** Retrieval scores match the established baseline; financial trends and legal spot-checks still pass; assembly tests green. **Starts after:** integration smoke and closing audit.

---

## Other tracks (can overlap once integration is closed)

### Evaluation harness for all agents

| Agent | Today |
|-------|--------|
| Retrieval | Full harness + Elder Care gold labels |
| Financial trends | 18-field checklist, scores linked to runs |
| Legal | 11-item checklist |
| Business model, customer quality, KPI, QoE, profiler | Smoke only—run completes and writes output; **no golden checklists yet** |

I want to: package the existing runbooks into one repeatable procedure; add golden sets for the five agents that only have smoke today; record baselines per agent and company; re-score after any retrieval change. I also have partial local test runs to finish or discard before declaring new baselines.

### Data room completeness

Analysis quality depends on what was uploaded, classified, and embedded—not only how we search. Clearsulting legal (**0/11 scored pass—all gaps**) shows agents working on a thin data room. I have coverage diagnostics today but not a single completeness score (e.g. “75% of expected document types present”) or a preflight that flags gaps before agents run. That would help routing, set expectations, and explain why Elder Care analyses are more trustworthy than another company’s.

### Executive summary / one-pager

Deterministic compression and bundle-driven LLM narrative on executive sections are in place. Still open: rename “TL;DR” to “Executive Summary” in templates, sharper bullets (e.g. mitigants), fuller wiring from bundle JSON, and clearer halt/flow from agents to final one-pager. I have a presentation experiment in mind for more LLM-generated sections.

### Hector’s repo

I need to merge his agents and auxiliaries at some point—first inventory what each side has, then align eval artifacts and baselines. Genie chatbot and Garden UI surfacing of analysis outputs remain separate product decisions.

---

## Risks & things easy to miss

- **~2 hr Databricks runs** — Smoke, full pipeline, harness baselines, and comparison runs each need real cluster time; order matters.
- **Integration not formally closed** — Smoke and a closing audit/review still outstanding; validation was reviewed in early July, integration was not.
- **Metadata filter comparison not run yet** — Only affects whether optional filters get turned on; hardening can still finish with them off.
- **Scheduled workflow job** — Config cleanup planned; production path remains the notebook, not an automated job.
- **Full stakeholder report path** — Validated through agent cells; orchestrator render path not in the same validation scope.

---

## My focus, this week, and what success looks like

**What I am doing now**  
Run the post-integration smoke on Databricks (~2 hr), document the result, then complete integration closeout and the closing audit so retrieval consolidation can start on a verified baseline.

**Rough sequence**

1. **Now** — Smoke test (ingestion + business model agent + profile check).
2. Integration wrap-up and closing audit.
3. Retrieval consolidation (design, implement, regression on cluster).
4. Optional: metadata filter comparison if cluster time allows.
5. **In parallel when possible** — Eval harness for all agents; data-room completeness metric.
6. **Later** — Executive summary work, Hector merge, Garden UI.

**This week**  
Finish smoke and integration closeout. If cluster time remains, start scoping retrieval consolidation.

**Carryover**  
Retrieval work and eval expansion involve more ~2 hr runs; completeness scoring and one-pager improvements can spill without blocking integration exit.

**Success for the week**  
Smoke signed off, integration formally closed with audit, no open question on whether the merged pipeline runs correctly on Elder Care, and retrieval consolidation at least scoped—or started if time allows.
