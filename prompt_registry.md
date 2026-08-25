# UC-13: Prompt identity layer

**Status:** proposal — not chartered, not scheduled  
**Date:** 25 August 2026  
**Audience:** delivery sponsor, PM, platform architect, engineering  
**Home:** Wave 4 adjacent. Does **not** replace M5–M8, Legal taxonomy, or beta wiring.

This is the write-up of an internal design pass (24–25 Aug). It is not a spec and not a request to buy a prompt product.

---

## In one minute

UC-13’s diligence reports are produced by a small set of large language model calls. Each call is driven by a **prompt** — the written instructions that tell the model what to extract, how to write, or how to score a claim.

We store the **answer**. We do not store **which instructions** produced it.

That gap matters now because Wave 4’s quality story is “measure, fix, re-run, prove it.” Without a recipe stamp on the run, a quality delta can be model noise, a silent prompt edit, a leftover demo path, or a different scoring judge. We cannot defend “we improved this” to an IC reader, a beta stakeholder, or a later sprint.

**Proposal:** a thin **prompt identity** layer — name every model call, hash the instruction template, write that identity onto the run. Git remains the source of truth. No new service.

**Not the proposal:** a prompt CMS, Langfuse, versioned markdown folders, or PMs editing Legal JSON outside a deploy.

**Ask:** a small slice (days, not a wave), before the next prompt rewrite we want to call a fix.

---

## Why this showed up in this system

UC-13 is a private-equity diligence pipeline: ingest a data room, extract structured workstreams (business model, financials, legal, KPIs, …), assemble a memo and a one-pager.

Three facts from the current program make prompts a control problem, not a copy-editing problem:

1. **Quality is a claim we have to prove.** M3 made scores honest; M4–M8 close issues with re-runs, not vibes. Beta is not yet feeding that loop (`eval_next_steps.md`). CIM preview and full-room diligence are different products and must not share a score line (`horizon-map.md`, `CIM_VS_FULL_VDR_ANALYSIS.md`).
2. **Many “model” failures are not the model.** Legal leftovers may be retrieval, extraction, schema, or a missing corpus. Horizon already says: decide which, and **do not rewrite Legal prompts** until that taxonomy exists. CIM-only is structurally blind on legal / real KPIs / forecast / customer concentration — that is the room, not a nicer system prompt.
3. **Call structure is already a standing decision.** Business-model extraction stays one model call over full context (merge reject: two-pass split). Moving prompt *files around* does not change that.

So the useful object is not “a registry of all the words.” It is **being able to say which instructions ran**, so the next quality sprint is attributable.

---

## What we have today

Rough inventory (lab scan, 24 Aug 2026): on the order of **34 named prompt constants**, ~**93k characters** of static instruction text, plus inline prompts (document classifier, company profiler, vision, every section writer). **Zero** `prompt_id` or hash on the analysis row.

They are not one asset class:

| Kind | Job | If you treat them like blog copy |
|---|---|---|
| **Extract** | Force a JSON shape out of retrieved chunks | You fork the schema. Field names already live in the prompt, the parser, and the tests. |
| **Narrative** | Write prose from already-extracted JSON | Highest editorial value (Stage-6 one-pager, Rainmaker, memo sections). |
| **Route** | Tag files, pick overlay, skip junk | One silent miss starves every downstream agent. |
| **Perceive** | Turn a page image into text | Short, local, low leverage to relocate. |
| **Judge** | Score a claim against evidence (eval) | Changes the **score**, not the memo. Must be pinned with the extract prompt. |

What already exists — so we do not rebuild it:

- **Legal** already has a pass-level dict (`_DOMAIN_PASS_EXTRACT`): pass id → prompt + register keys. That is a registry for the one agent that needed one.
- **Git + `CHANGELOG.MD` + pytest** already version prompt text. Stage-6 has been rewritten under named tasks; tests lock retired phrases and Legal field names.
- **`eval/program/registry.yaml`** already owns the word “registry” in this repo (defect catalog). A second object with that name will be misread.

Git versions files. Markdown folders would not add versioning. They would add a third copy of a schema.

---

## Proposal

**Name:** prompt identity layer  
**Job:** make every diligence and eval model call attributable.

| Do | Do not |
|---|---|
| Classify every call site: extract / narrative / route / perceive / judge | One folder titled “all prompts” |
| Hash the system + user **template** at call time (not the filled document context) | Fetch prompts from a network service at job run |
| Write `prompt_id` + hash onto the analysis row / run card | Treat git SHA as enough (same commit, different endpoint or leftover path) |
| Keep extract prompts next to the parser until the schema is a real schema | Move Legal/BMA JSON blobs into `.md` as a PoC |
| Pin eval judges to the same identity story as extract | Version extract prompts while judges float |
| Mark the M1 demo synthesis path (`populate.py`) non-production | Auto-index leftovers as “v1” |

Jobs keep running from the Databricks Git folder. No new runtime dependency.

---

## Value

**What it solves**

- “We fixed Legal / the one-pager / KPI” becomes: same recipe, re-run, score moved.
- Two rows a week apart stop looking like unexplained model drift when they were a prompt edit.
- CIM-preview vs full-room vs eval-judge stay separable products with separable instruction ids.
- Confidence scores and checklist metrics stay comparable across weeks and companies.

**What it does not solve**

- Empty legal register when the CIM has no contracts.
- Retrieval that never found the IP file.
- Schema field-name drift.
- Quiet production / beta not wired into measurement.

Those stay on the Wave 4 spine. This layer makes work *on* those problems claimable.

**Downstream**

| Later use | Why identity has to exist first |
|---|---|
| Stakeholder “since your last run” story | Same recipe, or we say the recipe changed |
| A/B retrieval vs extract vs copy | Horizon already wants “same extract prompt” as a pin |
| Confidence-score distributions | Unreadable if the recipe is silent |
| Fine-tune / SFT | Explicitly not a leftover. A prompt CMS is not a back door into training. Identity is the minimum if that program is ever opened. |

---

## Risks

| Risk | Why it is real here | Mitigation |
|---|---|---|
| **Misdiagnosis** | Legal S2 got worse after retrieval widening. Prompt edits without taxonomy ship another regression with a version bump. | Identity first. No Legal prompt rewrite until retrieval vs extract vs schema vs corpus is named. |
| **Eval incomparability** | A judge-prompt change already moved agreement ~0.39 → ~0.86. Unpinned versions make “fixed” unverifiable. | Judges get ids too. Promotion still requires a re-run. |
| **Schema split-brain** | Extract prompts *are* the JSON contract. A third copy in markdown is how registers go silently empty. | Do not relocate extract prompts in the first slice. |
| **Second source of truth** | Cluster jobs already have a “which button / which Git folder” problem. A live prompt server is a second checkout. | Repo + hash only. No hot-reload from a Volume or vendor. |
| **Brace / load-path bugs** | User templates are format strings with doubled braces. Moving them is a new crash class under a green job. | Leave extract templates in Python until schema-as-schema. |
| **Name collision** | “Registry” already means the eval defect catalog. | Call this **prompt identity**. Do not stand up a second “registry.” |
| **Scope creep** | Easy to sell as a prompt product and eat a wave. | Charter as a thin slice. Kill criteria below. |
| **Wrong bottleneck** | M5–M8, unowned Legal rows, claim 008, beta Phase A are the must pile. | Parallel only if cheap. Does not block Clearsulting sign-off. |

**Kill if:** the slice grows a service, a prompt UI, or a Legal rewrite; or we cannot write the hash on the existing run record without a catalog migration fight.

---

## Options (threads, not a menu)

Do these in order. Later threads are optional.

| # | Thread | Outcome | When |
|---|---|---|---|
| **0** | **Classify** every LLM site. Mark `populate.py` non-production. One-page index of ids (not the prompt bodies). | Shared map. Stops demo-path confusion. | Now — one session |
| **1** | **Identity** — hash at the shared caller; persist on the analysis / run card. | Next prompt change is claimable. | Before the next rewrite we want to call a fix |
| **2** | **Legal taxonomy** (already on the horizon) — retrieval vs extract vs schema vs corpus. Own leftover Legal rows. | Decide *whether* a prompt change is the lever. | Before M8, as already implied |
| **3** | **Schema as schema** — one typed schema generates the extract user template. | Field names have one home. | Only after #2 says the failure is extract |
| **4** | **Narrative files** — Stage-6 / Rainmaker / assessment tone in repo files, still hashed, still pytest-imported. | Non-engineers can review copy without touching parsers. | After Wave 4, or if Stage-6 churn continues |

**Rejected as MVP / PoC**

- External prompt CMS (Langfuse, PromptLayer, or equivalent) as a runtime source.
- Per-prompt `CHANGELOG.md` (the root changelog and decision logs already do this).
- Version folders (`prompts/legal/v3.md`) beside git.
- Mixing Garden / Genie (untrusted user language) with diligence extract.
- Treating CIM-preview prompts as the same product as full-room extract.
- Fine-tune / LoRA as a follow-on of this slice.

**Decision the room should lock**

Are we funding **reviewable, attributable prompt changes** (threads 0–1), or **prompt changes without a deploy** (a CMS)?

Those look similar on a slide. In this repo they are opposites. The first belongs here. The second fights the Git-folder job, eval pinning, and the hollow-success failure mode we already paid for.

---

## Role-specific reads

### Delivery sponsor

**Why a slice, not a wave.** We are not buying a prompt platform. We are buying the ability to stand behind a quality claim the way M4 already stands behind a product fix: evidence, not anecdote.

**What you get.** A run that can say which instructions produced the legal register, the KPI block, or the one-pager — so “since last time” is a sentence we can defend to an IC or a beta reader.

**What you do not get.** Faster memos, cheaper tokens, or Legal suddenly seeing contracts that are not in the room.

**Ask.** A small engineering slice, parallel to M5–M8 if it stays thin. Not a new program. Not instead of company sign-off.

**Red flag.** If the proposal grows a vendor, a UI, or “let’s rewrite all the prompts,” pull the scope back to identity only.

### Product / PM

**User-visible problem.** Stakeholders cannot tell whether a worse (or better) report is the deal, the data room, or us changing how we ask the model. Preview vs full diligence already confuses that story; silent prompt edits make it worse.

**What ships.** Nothing the IC reads on day one. What ships is **trust in the quality loop**: when we say a checklist item moved, we can name the recipe.

**Downstream PM value.** Feedback (“Legal is thin,” “the snapshot overclaimed census”) can be triaged to corpus vs retrieval vs extract vs copy, instead of a generic “tune the prompt” ticket that cannot close.

**Do not staff.** A prompt-editing workflow for deal teams. Extract prompts are contracts, not marketing copy.

### Platform architect

**Placement.** Shared LLM caller (`_call_llm` and the few jobs that bypass it) plus the existing analysis / run-manifest write. Git folder remains the only checkout the job sees.

**Dependencies.**

- **Requires:** one write path for `prompt_id` + hash; eval readers that persist or log the same ids (calibration judges included).
- **Does not require:** new service, Unity Catalog volume of prompt files, Langfuse, Garden/Genie, or changing BMA’s single-call rule.
- **Couples to:** run-card / `reasoning_trace` / `agent_run_manifest_json` shape — decide the column vs JSON-key once. Prefer additive JSON over a table rebuild.
- **Name:** keep this out of `eval/program/registry.yaml`’s noun. Identity is provenance, not a defect row.

**Adoptability.** Agents keep their prompts. They pass through the shared caller. Legal’s pass dict already looks like the extract half of this. Fail closed if a new call site bypasses the hasher.

**Non-goals that would make this a platform project.** Runtime prompt fetch, per-environment prompt override, or generating extract prompts from schema (thread 3) — that last one is a later architecture change, not this slice.

### Engineer (pipeline / eval)

**Adopt.** Stamp hash of the **template**, not the filled context (context is the documents; identity is the recipe). Same helper for extract, narrative, classifier, vision, and judges.

**Do not.** Relocate BMA / Legal / FTA user templates in the same PR. Do not teach the index to publish `populate.py`. Do not A/B Legal copy before the taxonomy.

**Tests.** Pytest already locks Stage-6 strings and Legal schema tokens — keep that. Add a static check that production call sites go through the hasher.

**Eval.** A judge id change is a new epoch, same as a gold rebase. Do not compare CHK-* across unpinned judge prompts.

**Size.** Thread 0–1 is a confined diff if we refuse scope. Thread 3–4 is a different plan.

---

## How this sits next to open work

| Work already named | Relationship |
|---|---|
| Wave 4 M5–M7 company sign-off | Unaffected. Do not park Clearsulting on this. |
| M8 Legal / KPI | Taxonomy first; identity makes an M8 prompt change *if any* claimable. |
| Unowned Legal rows / claim 008 | Still unowned. This does not home them. |
| Beta Phase A / which-button | Different gap (usage). Same class of honesty: know what actually ran. |
| CIM-only vs full-VDR experiment | Corpus is the variable. Pin prompts so the experiment stays fair. |
| Confidence-score distributions | Should-do on the horizon; lies without recipe identity. |
| Agent-quality A-03 | Deferred. Identity is cheaper and unblocks later depth work. |

---

## Suggested decision record

If this is accepted, write one line into the horizon map / backlog:

> **Prompt identity (classify + hash on run).** Thin slice. Not a CMS. Not a Legal rewrite. Not a Wave 4 blocker.

If deferred, the honest reason should be capacity on M5–M8 — not “prompts are already in git, so we are fine.” Git versions the file. It does not stamp the run.