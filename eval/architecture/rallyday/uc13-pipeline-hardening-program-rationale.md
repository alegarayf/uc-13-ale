# UC13 Pipeline Hardening & Validation — Program Rationale

**Produced:** Phase 1 · Step 1 (Idea Orchestrator) — reverse-engineered Genesis validation pass, run against an already-synthesized spec draft rather than a blank-canvas session
**Updated:** 2026-07-06 (spec v0.3.0 — Phase 2 Engineering Audit cycle 1 absorbed: workflow YAML declared non-live and M-PHV1's primary mutation surface corrected from `uc13_ingestion_pipeline.yml` to `test_pipeline.ipynb`; R-03 resolved to drop a confirmed-dead `retrieval_mode` parameter; numeric non-regression bar added to R-02; `ensure_coverage` fail-closed inheritance made explicit)
**Spec:** `.dev/specs/pipeline/uc13_pipeline_hardening_spec.md`
**Pain registry:** `.dev/uc-13_pain_central_v1.1.0.md` v1.1.2

---

## Design intent

RE² closed the retrieval architecture question (Route B + merge-rank validated by cluster ablation, 2026-07-06) and built the measurement platform. What remains open is not "which retrieval algorithm wins" but **"does the pipeline actually stop when it should, has the validated retrieval change been proven on more than one agent and one company, is the codebase on one branch, and is the residual retrieval debt worth fixing now."** Those are four different kinds of work with four different failure modes and four different primary mutation surfaces (`ingestion_parser.py`, scorecards/notebooks, git, `retrieval.py`) — which is why PHV is four sequential milestones rather than one program-sized change.

PHV's defining constraint is that it is a **hardening and validation program, not a redesign program**. Every item in scope traces to a pain-central ID that already exists and is already understood; PHV's job is to close operational gaps and prove existing decisions generalize, not to invent new retrieval mechanisms. This is why Garden (S-05), production auth (M-04), deep agent rewrites (A-03 full), and the RE² §5.18 triggers (BM25, cross-encoder, section_class Option B) are explicit non-goals — none of them are validation or hardening of something already built; they are new build surfaces with different consumers and different Phase 2 review needs.

The spec that this rationale accompanies was **not produced through a live Genesis dialectical session** — it was synthesized directly from the pain-central priority queue (P0–P2) as a v0.1.0 draft. That is a legitimate way to seed a spec when the underlying problem set is already well-documented, but it means the spec's decisions had not yet been tensioned, red-teamed, or checked against the actual code and git state. This rationale document, and the v0.2.0 spec revision it accompanies, is that missing validation pass, done retroactively: every P0–P1 technical claim in the spec was checked against `databricks/jobs/scripts/ingestion_parser.py`, `databricks/agents/shared/retrieval.py`, `eval/retrieval/harness.py`, and live git state before any decision was locked.

---

## Key tensions surfaced

### Was the spec's technical grounding trustworthy, or did it need re-verification?

- **Options:** Trust the pain-central synthesis as-is and proceed straight to Phase 2; re-verify every P0–P1 claim against source before locking anything.
- **Chosen:** Re-verify against source. Found five confirmations (O-07 fail-open, P-07 endpoint mismatch, R-09 duplication, R-03 partial consolidation, R-08 join coupling all reproduced exactly as described) and four corrections (see below).
- **Why:** A spec synthesized directly from a living pain document inherits that document's staleness. Pain-central was itself dated the same day as the spec and already contained at least one stale item (Q-E01) at time of writing — trusting it without a grounding pass would have carried that staleness into a program that gates Phase 2 review and orchestrator planning.

### M-PHV3 merge target — conflict-bearing merge vs. fast-forward

- **Options:** (a) Keep the spec's original framing — `dev2` merges into a `develop` branch with Genie chatbot conflict risk requiring explicit resolution; (b) verify actual git state and correct the spec to match.
- **Chosen:** (b). `git rev-list dev ^dev2` = 0 and `git rev-list upstream/dev ^dev2` = 0 — both `dev` and `upstream/dev` are strict ancestors of `dev2` (65–73 commits behind, zero unique commits on either side). No `develop` branch exists locally or on `upstream`. `backend-ai/app/services/genie_rules.py` is byte-identical between `dev` and `dev2`.
- **Why:** The original framing would have allocated M-PHV3 subtask budget to conflict resolution and a chatbot keep/port/remove decision that the evidence does not support needing. Getting the merge target's branch name wrong is a hard blocker discovered only at execution time if not caught now. The fast-forward is time-bound, not permanent — item 20 re-verifies immediately before executing, and the spec explicitly documents the fallback (standard merge) if `dev`/`upstream/dev` move first.

### Index sync gate — is FAILED/CANCELED detection sufficient, or does fail-closed require a bound on "never terminates"?

- **Options:** (a) Ship the FAILED/CANCELED → `IndexSyncError` fix as originally scoped, treating "timeout" as a documentation-only concept already implied by Design Principle 1; (b) verify whether a timeout mechanism exists in code, and if not, add one as new surface, not a fix.
- **Chosen:** (b). `_wait_for_index_sync`'s poll loop (`ingestion_parser.py:1353-1396`) has no upper bound — it only exits on `FAILED`/`CANCELED`. A pipeline stuck in a non-terminal state (e.g. `RUNNING` indefinitely, or a DLT scheduling issue that never produces an update) polls forever. Added `max_wait_seconds` (default 1800s) as new build surface within M-PHV1 item 1, not an afterthought.
- **Why:** A stuck-but-non-terminal pipeline is the same failure class as O-07 — Phase 3 agents never get an unambiguous signal — just reached by a different trigger (hang vs. terminal failure). Design Principle 1 ("must not proceed") is incomplete if it only covers the terminal-failure branch. The 1800s default is a conservative round number sized against observed sync duration for the Elder Care corpus (35K embeddings); it is explicitly flagged for revisit once a second company's sync duration is observed in M-PHV2, rather than invented as a permanent constant.
- **The outer exception swallow is a second instance of the same gap:** the current `except Exception as e:` block (line 1398) catches *everything*, including `WorkspaceClient` construction failures, and returns silently. PHV closes both silent-return paths, not just the FAILED/CANCELED one.

### R-02 activation — formal harness ablation gate vs. manual A/B

- **Options:** (a) Ship M-PHV2 item 16 / M-PHV4 item 29 as originally scoped ("optional ablation arm on cluster" / "harness gate `gate_pass=true`"); (b) verify the harness actually supports dispatching this ablation arm before locking the mechanism; if not, redesign the mechanism.
- **Chosen:** (b), and the verification failed the original framing. `eval/retrieval/harness.py::ablation_arm_to_merge_rank_mode` explicitly raises `PreconditionError` for `vs_filter_pushdown` — the dispatcher is a 1-D mapping keyed on `merge_rank_mode` string values (`sim_tier`, `off`, `sim_only`, `tier_only`); `vs_metadata_filters` is an orthogonal boolean flag on `semantic_search()` with no representable slot in that model. Descoped R-02's PHV activation path to a manual A/B: flip the flag directly via kwarg, run the harness twice, diff results by hand, document in `eval/retrieval/README.md` — no formal `gate_pass` field for this decision in v0.1.0.
- **Why:** Extending the harness dispatcher to a second, orthogonal ablation dimension is real code (a second dispatch axis, likely a tuple or composite key, threading through `EvalHarness.run`/`compare`) — not a checkbox inside an "optional" checklist item. Under Design Principle 9 (minimal blast radius), a one-time production-flag decision does not justify that extension. This mirrors the RE² program's own precedent of deferring `vs_filter_pushdown` dispatch wiring rather than rushing it into M-RE3 (see `eval/retrieval/README.md` §"Not in scope for cluster matrix").
- **Revisit condition:** if R-02 needs periodic re-gating (not a one-time decision), or a second boolean-style ablation dimension is needed elsewhere for an unrelated reason — at that point the dispatcher extension pays for itself across two use cases instead of one.

### Q-E01 evidence-commit step — commit task vs. verification task

- **Options:** (a) Keep M-PHV2 item 9 as "commit M-RE3 evidence," per pain-central's OPEN status and audit F1 (evidence uncommitted at `896f741`); (b) check current git HEAD before assuming the audit snapshot is still accurate.
- **Chosen:** (b). `CHANGELOG.MD`, `eval/retrieval/README.md`, and all four ablation CSVs are already committed at HEAD (`754dec8`), with zero uncommitted diff, as of the spec validation pass — hours after the audit that flagged them as missing.
- **Why:** Pain-central is explicitly a living document, and this is a direct demonstration of why "living" matters operationally — a same-day audit snapshot had already gone stale by the time PHV's own validation pass ran. Downgrading item 9 to a verification step removes false urgency from the M-PHV2 entry gate without weakening it (the check still exists — it just confirms rather than performs the commit).

### Second-company selection — lock now vs. defer to execution

- **Options:** (a) Name a specific second company now, locking Q-E03's validation target at design time; (b) leave it as an operator decision at M-PHV2 entry, per the original spec's framing.
- **Chosen:** (b) — no change from v0.1.0. No second company was named or evidenced as ready during this validation pass (no SharePoint data-room readiness signal found in the repo beyond a passing mention of "Project Silo" in an unrelated scratch note). This is a genuine deferred decision, not a design gap: the trigger condition (operator confirms a company with non-trivial data room available) is external to the codebase and cannot be resolved by code inspection.
- **Why not lock it:** Locking a company name without evidence it is actually ready to validate against would be a decision made for the sake of having decided, not because the engineering case supports it yet — exactly the anti-pattern Stage 4 warns against ("soft lock").

### Was the workflow YAML actually the build surface the spec assumed it was?

- **Options:** (a) accept the Idea Orchestrator's v0.2.0 grounding as sufficient and let Phase 2 review proceed against the spec as written; (b) have Phase 2 independently verify whether `uc13_ingestion_pipeline.yml` is runnable before treating it as a load-bearing M-PHV1/M-PHV3 surface.
- **Chosen:** (b), and it failed. Phase 2's cycle 1 audit (H-1) found all five non-agent task `python_file` paths in the YAML reference filenames that were renamed away in commit `4079922` (2026-05-27) — the job cannot execute task 1 if triggered. Independent re-verification during absorption found the compounding evidence: `databricks/workflows/README.md` documents the identical stale names, and no `databricks.yml` bundle configuration exists anywhere in the repository, meaning the README's own "recommended" `databricks bundle deploy` path was never functional in the first place. A commit five weeks later (`2935e63`) touched this exact file for an unrelated catalog-default change and did not catch the break.
- **Why this matters beyond one file:** the v0.2.0 Genesis pass's stated methodology was "verify against code and git state, not spec claims" — and it did that rigorously for git branch topology, harness dispatch code, and duplication targets. It did not extend that scrutiny to whether the infrastructure artifacts named as primary mutation surfaces were themselves live and runnable. That is a narrower, but real, gap in what "grounded" meant in cycle 1 of validation. Phase 2's contribution here was applying the same discipline to a category of artifact (deployment config) that code-reading alone does not surface as suspicious — a YAML file with plausible-looking task definitions gives no textual signal that it silently references deleted files.
- **Resolution:** M-PHV1's fail-closed and Sonnet-default work (items 4–6) retarget `test_pipeline.ipynb` — the artifact every M-RE1–3 cluster wet-run in `CHANGELOG.MD` actually exercises, and the one `databricks/CLAUDE.md`'s own "Testing workflow" section documents as the run procedure. The YAML path fix survives only as a non-blocking hygiene addendum in M-PHV3 — cheap to do, removes a landmine for a future deploy attempt, but does not gate anything.
- **Revisit condition:** the job is ever actually deployed (a `databricks.yml` appears, or an operator confirms a live Databricks Workflow using this definition) — at that point, the fail-closed and Sonnet-default work would need a corresponding workflow-task implementation, not just a notebook one.

### R-03: was `retrieval_mode` a real contract difference to design around, or dead code to remove?

- **Options:** (a) treat the `fallback.py` / `context_utils.py` signature mismatch as a real contract difference and extend `fallback.py` to accommodate `retrieval_mode`; (b) verify whether `retrieval_mode` has any actual runtime effect before deciding.
- **Chosen:** (b). `context_utils.py`'s own docstring states `retrieval_mode` "does not alter dispatch after Route A removal," and grep-level tracing confirms its only consumer is a diagnostic print statement — not a conditional branch anywhere in the retrieval path. It is a live-looking but functionally inert parameter, threaded from a notebook toggle (`Cell 1a: Switch retrieval_mode (RUX)`) through three FTA sub-agents into a wrapper that ignores its value. This is the inverse of the H-1 pattern: H-1 was an artifact that looked runnable but wasn't; this is a parameter that looks meaningful (configurable, threaded through multiple layers, named suggestively) but has been inert since Route A's removal (M-RE1 T3) and nobody updated the call sites or the notebook cell to reflect that.
- **Why not extend `fallback.py` anyway, to be safe:** extending a shared module's contract to preserve a parameter with zero behavioral effect adds surface area (a new kwarg every future caller must understand or ignore) for no benefit, and risks a future engineer assuming the parameter does something because it is present in the signature. Minimal blast radius favors removing dead surface, not preserving it defensively.
- **Revisit condition:** a future need reintroduces a genuine Route-A-style dispatch distinction that `retrieval_mode` could represent again.

---

## Architectural commitments

1. **PHV validates and hardens; it does not redesign.** No new retrieval algorithm, no new agent architecture, no new eval metric layer. Two-layer eval (harness recall + per-agent golden checklists) is extended in breadth (all agents, second company), not replaced.
2. **Fail closed on index sync, completely.** Both silent-return paths in `_wait_for_index_sync` (terminal FAILED/CANCELED, and unbounded non-terminal polling) raise `IndexSyncError`. A parser run that cannot affirmatively confirm index currency — for any reason, within a bounded time — must not let Phase 3 agents start.
3. **`merge_rank_on`/`sim_tier` remains the production ranking default.** M-RE3 ablation evidence closed this (Q-R01); PHV must not regress it. This is inherited from RE², not re-litigated here.
4. **One active milestone touches `retrieval.py`'s ranking semantics at a time.** M-PHV4 owns post-RE² retrieval hub extensions; M-PHV1–3 do not touch `semantic_search()` signature or ranking behavior.
5. **Operator evidence is only real once it is at HEAD.** Working-tree-only or uncommitted evidence does not close a gate — this was validated directly by finding Q-E01 already resolved in this exact way.
6. **Branch-integration assumptions are re-verified at execution time, not trusted from design time.** The fast-forward finding (Decision 7) is correct as of 2026-07-06; M-PHV3 item 20 re-checks it immediately before acting, with an explicit documented fallback if it has changed.
7. **Extend the harness dispatcher only when a second real use case exists.** One-time production-flag decisions (R-02) use manual comparison; the dispatcher is not extended speculatively.
8. **Catalog resolution has exactly one documented convention.** `uc13_ale` for eval/harness/PHV validation runs; `uc13` for production defaults per existing `CLAUDE.md`. No implicit catalog drift between job parameter defaults and documentation.
9. **Minimal blast radius over architectural rewrites**, unless a carryability check inside a milestone's subtask budget explicitly passes (R-06/R-07 in M-PHV4).
10. **Every build-checklist item traces to a pain-central ID.** No item exists in PHV without a corresponding OPEN/WATCH/partial entry in the registry this program consumes.
11. **A build surface is only "primary" if it is confirmed live, not merely present in the repo.** `uc13_ingestion_pipeline.yml` exists, is well-formed YAML, and reads as plausible infrastructure — none of which means it runs. Grounding a spec's claims requires checking whether a named mutation surface is actually exercised (evidence: recent commits touching it, evidence: other documentation/tests referencing it, evidence: it appearing in the artifact that operational evidence — `CHANGELOG.MD` wet-runs — actually attributes results to), not just that it parses and its tasks look sequenced correctly.
12. **A parameter threaded through multiple call sites is not thereby proven functional.** `retrieval_mode` passed the "is it referenced" test at every layer (notebook widget → agent → sub-agent → wrapper) while failing the "does it change behavior" test at the one layer that mattered. Verification of a parameter's relevance requires reading what the terminal consumer does with the value, not just confirming it is threaded through the call chain.

---

## Explicitly rejected approaches

| Rejected | In favor of | Why | Revisit if |
|----------|-------------|-----|------------|
| Garden API / UC13 → Garden UI (S-05) in PHV scope | Separate product charter | Different hub, auth, and frontend contracts; no shared Phase 2 consumer | Never in PHV |
| Changing `merge_rank_on` default | Keep `sim_tier` | M-RE3 ablation proved alt arms regress sharply (e.g. 46%→7.7% recall) | New company evidence contradicts |
| Silent index-sync warning-only | Fail closed (both terminal and timeout paths) | Root cause of empty-retrieval operational pain (O-07); a warning that can be missed is not a gate | Never |
| Standard merge + conflict resolution for M-PHV3 | Fast-forward `dev2` → `dev`/`upstream/dev` | Git confirms 0 unique commits on either target branch not already in `dev2`; Genie file byte-identical — no divergence exists to resolve | `dev`/`upstream/dev` accumulate independent commits before M-PHV3 executes |
| Leaving `_wait_for_index_sync` unbounded | Bounded `max_wait_seconds` (default 1800s) | Same failure class as O-07 (agents can proceed on an unconfirmed index) via a hang instead of a terminal failure — fail-closed must cover both | Never — this is a completion of Design Principle 1, not a separate feature |
| Formal `ablation_arm` dispatch wiring for R-02 in v0.1.0 | Manual A/B comparison | Extends the harness dispatch model for a one-time flag decision; violates minimal-blast-radius for a non-recurring need | R-02 needs periodic re-gating, or a second boolean-style ablation dimension is needed elsewhere |
| Trusting pain-central's Q-E01 OPEN status without re-checking git | Direct HEAD verification | Same-day audit snapshot had already gone stale (evidence committed at `754dec8` after the audit) | — |
| Locking a specific second company at spec-validation time | Deferred operator decision at M-PHV2 entry | No evidenced-ready second company found during this pass; locking without readiness evidence is a soft-lock anti-pattern | Operator identifies and confirms a company with non-trivial data room |
| Full R-07 + R-09 + R-06 + R-02 in one M-PHV4 plan | Bounded M-PHV4 slice + explicit deferrals | Exceeds single orchestrator's 4–10 subtask budget | Charter splits M-PHV4a/4b |
| Treating `uc13_ingestion_pipeline.yml` as M-PHV1's live mutation surface (Phase 2 audit H-1) | Redirecting to `test_pipeline.ipynb`; YAML fix as non-blocking M-PHV3 hygiene | Five stale script paths survived a month and a same-file unrelated commit untouched — no evidence this job has ever run; "fixed but never exercised" does not make the fail-closed gate verifiable | The job is ever actually deployed (`databricks.yml` appears, or an operator confirms a live Workflow) |
| Extending `fallback.py`'s signature to preserve `retrieval_mode` for R-03 (Phase 2 audit S-3) | Dropping `retrieval_mode` at FTA call sites | Confirmed non-functional since Route A's removal (docstring + print-only consumer); preserving dead surface for "safety" adds ongoing confusion cost for no behavioral benefit | A future need reintroduces a genuine dispatch distinction |

---

## Deferred

| Item | Trigger |
|------|---------|
| `vs_metadata_filters` formal `ablation_arm` dispatch wiring | A second flag-style ablation dimension is needed beyond R-02, or R-02's manual A/B result is borderline enough to need repeatable statistical gating |
| R-07 full retrieval service extraction | Second company latency unacceptable, or retrieval called from a non-notebook service |
| Corpus-size-proportional index-sync timeout model | A real sync legitimately exceeds the 1800s default on an observed run (M-PHV2 second-company sync gives first additional data point) |
| Deep agent rewrite (A-03) | M-PHV2 scorecard shows systematic failure on a workstream, not just a flat/unchanged score |
| BM25 / cross-encoder / `section_class` Option B | RE² §5.18 triggers fire — new ablation shows a plateau PHV validation does not explain |
| Ingestion instrumentation program | Operator pain on file-drop visibility resurfaces as a priority (separate design, `P_ingestion_instrumentation.md`) |
| Multi-company shared index (Q-R03) | Production confirms a multi-tenant deployment model |
| Second-company selection | Operator identifies a SharePoint company with a non-trivial data room, at M-PHV2 entry |

---

## Retrospective note (flagged for post-milestone capture)

Phase 2's cycle 1 audit named a single blind spot spanning three of its findings (H-1, S-2, S-3): the v0.2.0 Genesis pass verified externally-observable facts rigorously (git topology, harness dispatch code, byte-for-byte diffs) but did not execute or lint the specific infrastructure artifacts it planned to hand to an executor — "checked the facts, didn't run the code." `.dev/architecture/rallyday/failure-taxonomy.md` does not yet register this as a named failure class (this is PHV's first build), so Phase 2's D9 check reduced to model self-assessment rather than a taxonomy-backed lookup this cycle. Once a milestone closes, this pattern is worth a retrospective entry and, if it recurs, a named failure-taxonomy class so future validation passes (Phase 1 Genesis, Phase 2 audit, or auditor-review) check it systematically rather than relying on whichever reviewer happens to think to run the artifact.

---

*Phase 1 · Step 1 · Idea Orchestrator v0.3.0 methodology*
*This rationale accompanies spec v0.3.0. Future Design Flaw absorptions from Phase 2 feedback that change an architectural commitment or reverse a rejected approach must update this document per the Update-mode rationale maintenance rule.*
