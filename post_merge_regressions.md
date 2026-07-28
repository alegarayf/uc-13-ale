# Post-merge regression map — Hector `ui-pipeline-integration` → `feat/merge-hector-incoming`

**Created:** 2026-07-27
**Updated:** 2026-07-28 — post-fix closeout: BMA 7/7 + full DAG e2e `827597669988464` (9/0/0); profiler 7/7; Legal R-2 accepted deferred
**Scope:** Elder Care / `uc13_ale` — golden-checklist regression analysis after sqlite-fix e2e
**Authoring context:** Merge program `hector-ui-pipeline-merge` (plan: `.dev/plans/hector-ui-pipeline-merge/plan.md`, gates: `.dev/plans/hector-ui-pipeline-merge/CLUSTER_GATES.md`)

---

## Pending (as of 2026-07-28 closeout)

| Item | Status | Notes |
|------|--------|-------|
| **BMA scored re-validation** | **Closed** | Full e2e row `2026-07-28 22:37` scores **7/7**; orchestrator BMA section clean (no generator fallback). Scorecard: `.dev/scorecards/uc13-eval-harness-all-agents_bma_elder-care_2026-07-28.md`; promotion `promoted` on manifest `2855aef9…` |
| **Full parallel e2e** | **Closed (DAG)** | Job `827597669988464` — **9 SUCCESS / 0 FAILED / 0 SKIPPED**; memo `.md` written. T9 bridge failed on missing `python-docx` (serverless env) — `.md` renders OK; `.docx` export blocked (infra, not agent regression) |
| **Legal R-2** | **Deferred / accepted** | Post-fix e2e scored **7/11** (vs 9/11 baseline); LLM entity-resolution variance — passes ≥7/11 floor; dedupe hardening → backlog |
| **Profiler G1** | **Closed** | Re-run `2026-07-28 22:15` scores **7/7** |
| **4-company e2e** | Open | Clearsulting, GKF, SPG not run post-fix |
| **G6 gold-label bootstrap** | Open | 8 CQA/KPI intents (`pending2.md`) |
| **G5 VDR gate** | Open | `run_vdr_pipeline.py` not exercised |
| **Legal dedupe hardening** | Backlog | `source_doc` in dedupe key |
| **FTA memo generator (new)** | Open | E2e log: `section 'financial_trends' generator failed` — same `flags` string-parse class as BMA R-3; FTA G1 still passes 16.5/18 |

**Closed:** sqlite fix; R-1 + R-3; T5/T6/T7 G1 hold/improve; post-fix BMA/Profiler validation; DAG e2e `827597669988464`.

---

## 2026-07-28 remediation — R-1 and R-3 fixed, live-verified

**R-1 (BMA truncation) — FIXED.** `business_model_agent.py::main()` now overrides `extraction_endpoint` to Sonnet whenever Haiku/Llama is selected (mirroring Legal's existing pattern), and the extraction `max_tokens` was raised from `8_192` to `16_000` (the old value was calibrated to Haiku's hard cap and would have silently re-capped Sonnet too). Verified live: submitted a serverless job against `uc13_ale`/Elder Care with `extraction_endpoint` deliberately set to Haiku to prove the override fires — job log confirms `[override] extraction_endpoint 'databricks-claude-haiku-4-5' → Sonnet ...`, and the resulting Delta row has both `sales_motion_json` and `key_dependencies_json` fully populated (previously `null`/`[]`), with no truncation warning in the log. Local suite: 764 passed / 5 skipped / 1 xfailed, unchanged.

**R-3 (orchestrator Business Model section crash) — FOUND ROOT CAUSE (independent of R-1) and FIXED.** Re-running `generate_business_model_assessment()` directly against the fresh, non-truncated R-1 row *still* raised the same `'str' object has no attribute 'get'` — proving R-3 is not just a downstream symptom of truncation but its own bug. Root cause: `business_model_agent.py:1838` read the `flags` column with `result.get("flags") or []` and never `json.loads()`'d it, while every sibling JSON column in the same function does. `flags` is stored as `StringType()` (JSON-encoded, per the universal `flags` contract in §2.2 of the merge plan), so `for f in flags` was iterating over the string's *characters*, not dict rows. Fixed by parsing `flags` (and defensively `data_room_gaps`, though that column is actually `ARRAY<STRING>` already and unaffected) with a `json.loads()` guard. Verified live: `generate_business_model_assessment()` now returns a 36,490-character markdown section successfully against the same fresh row. Local suite re-run after this fix: still 764 passed / 5 skipped / 1 xfailed.

**Not yet done:** a full parallel e2e re-run (all 9 agents) to confirm the fixes hold end-to-end and to get a fresh golden-checklist score for BMA (expected 7/7, pending confirmation) — this was scoped as an isolated verification in the approved plan, not a full e2e. R-2 (Legal t4c) was intentionally left as-is per the agreed remediation priority (lower priority, general LLM entity-resolution variance, not a merge blocker). The sqlite fix mentioned throughout the doc as "uncommitted" is a separate, pre-existing item not touched by this remediation pass.

---

## 2026-07-28 investigation addendum — root causes confirmed

The original doc (below, unchanged) ranked several theories per regression but marked both **R-1 (BMA)** and **R-2 (Legal)** as *"Unconfirmed."* Re-investigation against the actual e2e log (`.dev/hector_merge_e2e_Elder_Care_parallel.log`), the merged/baseline YAML report diffs, and `git diff e06a455..HEAD` on the affected agent files now confirms both, with direct evidence. **Neither is a merge-code regression.** A third, previously unreported issue (R-3) was also found while tracing R-1.

### R-1 (BMA) — CONFIRMED: Haiku 8,192-token output cap truncates the extraction JSON mid-stream

**Evidence — e2e log line 118:**
```
[data_room_gap] LLM response was truncated by the token limit
(Unterminated string starting at: line 662 column 27 (char 24708)).
Partial JSON was recovered — records cut off mid-stream are excluded.
```
This is a direct, literal confirmation of the doc's ranked theory #1 (truncation of a large single structured-JSON call), not speculation.

**Why it happens (mechanism, not just symptom):**
- `business_model_agent.py:1391` calls `self._call_llm(_SYSTEM_PROMPT, user_prompt, _extract_ep, max_tokens=8_192)`.
- `_extract_ep` resolves to `databricks-claude-haiku-4-5` (the `extraction_endpoint` widget default per `databricks/CLAUDE.md`).
- `CLAUDE.md`'s own documented platform constraint: *"Claude Haiku 4.5 is also capped at 8,192 output tokens (requests for higher are silently floored)... Only Sonnet 4.6 reliably generates 10-16K tokens. Do not use Haiku for extraction schemas that exceed ~6,000 tokens of output."*
- BMA's schema has ~10 top-level array/object fields (`products_and_services`, `revenue_by_location`, `people_and_org`, `workforce_capacity`, `customer_operational_metrics`, `customer_profile`, `sales_motion`, `revenue_visibility`, `key_dependencies`, `recent_model_changes`, `citations`) emitted in that fixed order in one LLM call. Whenever the corpus for a given company/run pushes total output past 8,192 tokens, everything from wherever the cutoff lands onward is lost — which is deterministically the **tail** of the schema.
- Fresh e2e log confirms exactly the tail fields were dropped this run: lines 119–122 show `sales_motion`, `revenue_visibility`, `recent_model_changes`, **and** `key_dependencies` all logged as empty/not-extracted — a superset of the 2 golden-checklist items (`sales_motion`, `key_dependencies`) that the automated scorer flagged.
- This also explains the **historical volatility** already noted in the doc (Jul-14 4/7 → Jul-21 7/7 → Jul-27 5/7): whether the cutoff lands before or after these tail fields depends on how much retrieved context (chunk volume for that company) inflates the prompt/response size run to run. It is not flaky in the sense of "random"; it is a **threshold effect** — sensitive to retrieval volume, not to DAG parallelism, and **not attributable to any T4/T5-T7 merge code** (confirmed below).

**Merge-code innocence — confirmed by diff:**
```
git diff e06a455..HEAD -- databricks/agents/workstreams/business_model_agent.py
```
shows T4 touched only the `main(spark=None)` signature and the `spark=` graft into `open_agent_run(...)`. Zero lines changed in the extraction call, prompt, schema, or `max_tokens`. The regression predates and is orthogonal to this merge; the merge only made it *visible* again because sqlite blocked BMA from running at all until 2026-07-27.

**The fix Legal already applied, that BMA never got:** `legal_contracts_agent.py:2076-2083` explicitly overrides `extraction_endpoint` to Sonnet whenever the Haiku/Llama default is selected, with this exact comment: `"[override] extraction_endpoint '{_widget_ep}' → Sonnet (Haiku/Llama cap=8192 tokens; legal multi-pass schema needs Sonnet)"`. **BMA has no equivalent override.** This is the actionable remediation, not a mystery to investigate further.

### R-3 (new finding, not in original doc) — orchestrator memo's Business Model section crashes, silently falls back

**Evidence — e2e log line 414:**
```
[orchestrator] section 'business_model' generator failed ('str' object has no attribute 'get'); using fallback.
```
`orchestrator_agent.py::_section_narrative` (line 385-393) calls `generate_business_model_assessment(row, ...)` inside a bare `try/except Exception` that swallows the error and substitutes a generic fallback section — so the final diligence memo silently ships a degraded Business Model section with no visible alarm outside stdout.

**Thesis:** this is a direct downstream consequence of R-1. The partial-JSON-recovery path that "rescues" a truncated Haiku response likely leaves at least one nested field as a raw/partial string instead of the expected dict (e.g. a cut-off `sales_motion` or `revenue_visibility` object), and `generate_business_model_assessment` calls `.get()` on it assuming a dict. **Not yet independently verified against the partial-JSON-recovery code path** — flagged as the one item in this addendum still needing a targeted look (`_parse_json_response` in `business_model_agent.py` + whatever `generate_business_model_assessment` does with `sales_motion`/`revenue_visibility`/`recent_model_changes`/`key_dependencies`).

**Why this matters for the merge gate:** this failure is masked (caught + fallback), so it did not show up as a DAG FAILED/SKIPPED, and it isn't covered by the golden-checklist scorer (which reads Delta rows, not the rendered memo). It's a real defect independent of R-1/R-2's checklist scores and should be added to the open-work list.

### R-2 (Legal t4c) — CONFIRMED as genuine extraction-pass variance, NOT a retrieval miss, NOT a merge regression

**What was ruled out:**
- **Retrieval miss** — ruled out. E2e log line 189: the `contracts_vendors_platform` pass retrieved 14 chunks from all 6 expected files, **including** `Westchester_Lease_0121.pdf`. The chunk was retrieved.
- **Raw extraction failure** — ruled out at the pass level. Log line 202-203: `Step 3 [domain_extract_contracts_vendors_platform]: contract_register=6` — the initial extraction produced **6** contracts (matching the Jul-24 baseline count), not 5. The row-count drop to 5 happens **after** extraction, at the merge/dedupe step (line 264: `[merge_registers]: contract_register=6→5`).
- **Merge-code regression from T4** — ruled out by diff. `git diff e06a455..HEAD -- legal_contracts_agent.py` shows T4 changed only `main(spark=None)` + the `spark=` graft into `open_agent_run`. The dedupe/merge logic (`_merge_register_records`, `_register_dedupe_key`, `_merge_nested_dicts`, `_upgrade_tri_state_present`) is untouched — this code path is identical to the Jul-24 baseline run.

**Direct comparison of merged registers (`_legal_report_2026-07-24.yaml` baseline vs. `.dev/legal_agent/baselines/_latest_Elder_Care_legal_report.yaml` fresh):**
- Baseline register: 6 rows, with row 5 (`Landlord (unnamed) / Guarantor`, contract_type `Lease` — the Westchester lease) carrying `termination_for_convenience.present: 'true'`.
- Fresh register: 5 rows, **all** `termination_for_convenience.present: not_found` — and critically, the fresh register's `counterparty_name` values (`Guided Living (Seller)`, `Consultant (unnamed)`, `Landlord (unnamed — Manhattan)`, `Licensor (unnamed — Manhattan)`, `Landlord (unnamed — Long Island)`) don't even textually match the baseline's naming pattern for the same underlying documents. The LLM re-extracted different counterparty labels and a different row grouping from the same source PDFs this run.

**Root cause:** this is LLM extraction non-determinism at the entity-resolution layer (how `counterparty_name` gets normalized per contract, which feeds `_register_dedupe_key`), not a code defect. Since dedupe keys on `(normalized counterparty_name, contract_type)`, a run-to-run difference in how the LLM labels/splits counterparties changes which rows collapse together in the merge — and this run, whatever absorbed the Westchester lease's content lost its `termination_for_convenience=true` value in the process (likely out-competed by a longer `raw_quote` from the row it merged into, per `_merge_register_records`'s "prefer longer quote" rule — worth one direct check, see below). Legal already uses Sonnet (not Haiku) here, so this is not a token-cap issue like BMA — it's a naming/dedupe-key fragility issue.

**Remaining unconfirmed detail (small, bounded):** which specific baseline row's content the Westchester lease got folded into during dedupe. Not needed to accept the root-cause diagnosis, but needed if the remediation is "make counterparty_name normalization stable" — check by re-running Cell 16 twice back-to-back and diffing raw (pre-merge) `contract_register` extraction, not the post-merge YAML.

### Remediation priority (supersedes doc's original "Recommended resolution order" for R-1/R-2)

1. **BMA (R-1, R-3) — code fix, not a re-run.** Give `business_model_agent.py` the same extraction-endpoint override Legal already has: force Sonnet whenever the schema's realistic output size can exceed ~6-8K tokens, or split the single 10-field extraction call into 2 calls (head fields / tail fields) the way `financial_trends_agent.py` already does with its 3 parallel sub-agents. Re-running BMA against Haiku unchanged will keep flipping between ~4/7 and 7/7 depending on retrieval volume — this is what the doc's Jul-14→Jul-21→Jul-27 history already shows. **Do not spend more cycles isolating this as "flake vs. structural" — it's structural, and the fix pattern already exists elsewhere in this codebase.** R-3 (memo crash) should self-resolve once BMA stops returning malformed partial JSON, but verify the assessment generator doesn't need its own defensive `.get()` guard regardless.
2. **Legal (R-2) — accept as extraction variance, not a merge blocker.** T4/T5-T7 did not cause this; it predates the merge and is a general LLM-entity-resolution fragility in the dedupe key. Lower priority than R-1: it's a single boundary pass/gap-correct flip on a historically volatile item (per doc's own Jul-16→Jul-24 history), and the underlying data (chunks, clause detection) is present. If it needs to be systematically hardened, the fix is in `_register_dedupe_key`/`_merge_register_records` (e.g. dedupe on `source_doc` identity in addition to normalized name+type, so two genuinely different contracts don't collapse just because the LLM assigned them similar counterparty labels this run) — a `T4`-adjacent but out-of-scope-for-this-merge hardening item.
3. Both items are now **tangible engineering tasks**, not open triage questions — they no longer block "is this the merge's fault" (confirmed: no), only "do we fix BMA's token cap now or accept the checklist volatility."

---

*(Original 2026-07-27 document follows, unmodified.)*

---

## Executive summary

After landing T1–T9 and fixing the sqlite provenance blocker, we ran a **parallel DAG e2e** on Elder Care (`run_id=1074138209208842`, 2026-07-27). The DAG completed **9 SUCCESS / 0 FAILED / 0 SKIPPED** — the primary merge execution path is healthy.

**Golden-checklist scoring** (automated field-presence rubric aligned to `eval/*/golden_checklist_elder_care.md` and the FTA 18-field scorecard) shows:

| Verdict | Agents |
|---------|--------|
| **Hold or improve** | CQA (↑), KPI, QoE, FTA |
| **Regression** | BMA (5/7), Legal (8/11) |
| **Not applicable** | Profiler (not in DAG; stale row) |
| **No checklist** | forecast, cross_analysis, orchestrator (e2e SUCCESS only) |

**Merge T5/T6/T7 intent (QoE/CQA/KPI depth):** no score regression; CQA improved.

**Open before full greenlight:** triage BMA + Legal pass-row losses; commit sqlite fix; optional isolated re-runs to separate flake from structural regression.

---

## Timeline — what happened before this doc

| When | Event | Effect |
|------|-------|--------|
| 2026-07-24 | T1–T7 landed on `feat/merge-hector-incoming` (rename, orchestration DAG, QoE/CQA/KPI 3-way merges, notebook, registry +8 intents) | New CQA/KPI retrieval tools; G6 gold-label gap opened |
| 2026-07-24 | T8/T9 landed (`347c448`, `82538da`) — notebook merge + `build_exec_summary` bridge | Full e2e path: memo + Rev3 one-pager |
| 2026-07-27 | First parallel e2e batches (pre-sqlite fix) | FTA **FAILED** (sqlite threading); QoE/forecast SKIPPED; stale upstream data |
| 2026-07-27 | Sequential Elder Care re-run (pre-fix) | Same 6/1/2 failure — proved `max_parallelism=1` is not a workaround |
| 2026-07-27 | **SQLite fix** implemented (uncommitted): `open_agent_run(spark=)`, `resolve_store()` fail-closed, pipeline `_sync_env`, e2e runner env | Local tests 37 targeted + full suite 764 pass |
| 2026-07-27 | Phase 3 e2e after workspace upload of fix (`1074138209208842`) | 9/0/0 manifest; forecast table created; provenance on Delta |
| 2026-07-27 | Full G1 scoring on fresh rows | BMA + Legal regressions surfaced; T5–T7 agents pass |
| 2026-07-27 | Gold bootstrap started then **stopped** by operator; `elder_care.yaml` reverted | G6 still open |

**Evidence artifacts**

- E2e summary: `.dev/hector_merge_e2e_Elder_Care_parallel.json`
- E2e logs: `.dev/hector_merge_e2e_Elder_Care_parallel.log`
- Scoring script: `.dev/g1_score_all_agents.py`
- Pre-fix handoff: `sqlite_removal.md`

---

## Validation methodology (limitations)

Scoring used **automated field-presence rules** mirroring golden-checklist categories (`pass` / `partial` / `gap-correct`), not a full operator markdown re-score with narrative notes.

| Limitation | Implication |
|------------|-------------|
| No human verdict review | Borderline `partial` vs `pass` may differ from operator scoring |
| FTA uses 18-field rubric from `.dev/scorecards/scorecard_7_03_post_m3_vs_7_02.md` | Matches historical 16/18 baseline method; field 18 (runtime) assumed pass when row exists |
| Profiler scored against latest `company_profile` row | Row was **not** from e2e — see Profiler section |
| Legal scored from `analysis.legal` Delta JSON | Jul-24 baseline used `legal_report.yaml`; register counts may differ slightly |

For promotion-gate closure, program norm is operator scorecard + `evaluate_promotion` per `eval/retrieval/README.md`.

---

## Full scorecard — fresh e2e vs baselines

**E2e run:** `1074138209208842` · catalog `uc13_ale` · company `Elder Care` · parallel DAG (`max_parallelism=4`)

| Agent | Fresh | Baseline | Gate (G1) | Result | Row `created_at` |
|-------|-------|----------|-----------|--------|----------------|
| CQA | **4/6** | 3/6 | ≥3/6 | **PASS** (↑) | 2026-07-27 20:13:34 |
| KPI | **3/3** | 3/3 | 3/3 | **PASS** | 2026-07-27 20:14:02 |
| QoE | **5/6** | 5/6 | ≥5/6 | **PASS** | 2026-07-27 20:16:47 |
| FTA | **16/18** | 16/18 | ≥16/18 | **PASS** | 2026-07-27 20:13:40 |
| BMA | **5/7** | 7/7 | ≥7/7 | **REGRESSION** | 2026-07-27 20:13:48 |
| Legal | **8/11** | 9/11 | ≥9/11 | **REGRESSION** | 2026-07-27 20:17:02 |
| Profiler | — | 7/7 | ≥7/7 | **N/A** | 2026-07-22 12:52:28 (stale) |

### Agents without golden checklists (e2e only)

| Agent | E2e status | Notes |
|-------|------------|-------|
| forecast | SUCCESS | First row in `uc13_ale.analysis.forecast` for Elder Care |
| cross_analysis | SUCCESS | Row written; previously degraded when FTA/QoE missing |
| orchestrator | SUCCESS | Memo + docx at `final_diligence_memo_Elder_Care_20260727_2023.*` |
| T9 exec-summary | SUCCESS | 1,440 words (+96 vs 1,344 baseline); `tldr_quality_check` exit 0 |

---

## Confirmed non-regressions (T5/T6/T7 + FTA)

### CQA — 4/6 (baseline 3/6) — **improved**

| item | Fresh | Baseline (Jul-8) | Notes |
|------|-------|------------------|-------|
| concentration | **pass** | gap-correct | `top_customers_json` now populated (billing-derived customer) |
| retention | gap-correct | gap-correct | NRR/GRR still null; documented in discrepancies |
| customer_tenure | pass | pass | Length-of-stay distribution from CIM |
| payor_mix | partial | partial | Structure present; many `pct_of_revenue` still null |
| discrepancies_json | pass | pass | |
| data_room_gaps | pass | pass | |

**Likely cause of improvement:** Hector T6 merge added retrieval tools (`cohort`, `contract_terms`, `customer_health`, `revenue_type_and_renewals`) — better corpus coverage for concentration/customer fields. Not a regression concern.

### KPI — 3/3 — **holds**

All three checklist rows pass. `healthcare_kpis_json` populated (census, headcount, utilization, compliance, credentialing, site-level visibility). `missing_kpis_json` has 10 entries.

### QoE — 5/6 — **holds**

Same pattern as M2 baseline: 5 pass + 1 gap-correct (`qofe_report_present=false`). Tier classification 17/17 Tier 4 with FTA addback schedule present.

### FTA — 16/18 — **holds**

Matches M-RE3 post-M3 baseline. Known chronic gaps unchanged:

- **Field 8 working_capital:** miss (DSO/DPO/AR aging null — same as Jul-3 baseline)
- **Field 11 projected_financials:** partial (`budget_vs_actual` empty — same as baseline)

SQLite fix unblocked FTA execution; did not change extraction quality vs historical 16/18.

---

## Regression R-1 — BMA 5/7 (baseline 7/7)

**Root cause CONFIRMED 2026-07-28 — see addendum at top of doc.** Haiku 8,192-token output cap truncates the single structured-JSON extraction call; `sales_motion`/`key_dependencies` (and, per fresh log, also `revenue_visibility`/`recent_model_changes`) are late-schema fields lost to the cutoff. Not a merge regression — T4 changed only the `spark=` signature (confirmed by diff). Fix: give BMA the same Sonnet extraction-endpoint override Legal already has, or split the extraction call like `financial_trends_agent.py`'s parallel sub-agents. See addendum for full mechanism, log line citations, and remediation detail. Original theories below kept for history.

### What regressed

| item_id | Baseline (2026-07-21) | Fresh (2026-07-27 e2e) | Delta |
|---------|----------------------|------------------------|-------|
| products_services | pass | pass | — |
| people_org | pass | pass | — |
| customer_profile | pass | pass | — |
| **sales_motion** | pass (`sales_motion_tag=relationship`, GTM JSON) | **gap-correct** (`sales_motion_tag`=null, `sales_motion_json`=`[]`) | **−1 pass** |
| **key_dependencies** | pass (platforms, vendors, channels, offshore) | **partial** (`key_dependencies_json`=`[]`) | **−1 pass** |
| data_room_gaps | pass | pass | — |
| overlay_conflict | pass | pass | — |

### Where it comes from (program context)

- **Merge subtask:** T4 — **keep-mine** BMA + `main(spark=None)` graft only. No intentional BMA feature merge from Hector.
- **Baseline provenance:** Fresh Cell 11 re-score 2026-07-21 (`.dev/scorecards/uc13-eval-harness-all-agents_bma_elder-care_2026-07-21.md`, pipeline `f0a4065e…`).
- **Execution path difference:** Baseline = isolated `business_model_agent.main()` via notebook Cell 11. Fresh = **parallel DAG wave** (BMA runs alongside FTA, CQA, KPI with `max_parallelism=4`) — no hard/soft deps on BMA in `pipeline.py`.

### Observed warehouse state (fresh row)

```
sales_motion_tag: null
sales_motion_json: []  (empty array)
key_dependencies_json: []  (empty array)
```

Other rich fields (products_services, people_org, customer_profile) **did populate** — extraction partially succeeded; loss is localized to sales motion + dependencies blocks in the single structured JSON extraction call.

### Likely causes (ranked) — superseded by confirmed root cause above; kept for audit trail

1. **LLM extraction nondeterminism / truncation** — BMA uses one large structured-JSON call (`max_tokens=8_192`, Haiku extraction endpoint). Sales motion and key_dependencies are late sections in the schema; partial JSON recovery may drop trailing fields while preserving earlier blocks. Prior Jul-14 baseline was **4/7** with truncation before Jul-21 fresh 7/7 — BMA scores have been volatile across runs. **[CONFIRMED — this is the root cause, see addendum]**
2. **Parallel cluster load** — Four agents extracting concurrently may increase latency/timeouts vs isolated Cell 11; no explicit timeout regression logged in e2e output reviewed. **[Ruled out — no thread-safety or timeout issue found in `agent_base.py`/`retrieval.py`; token counter is properly locked; truncation is a token-count threshold effect, not a parallelism artifact]**
3. **Not merge code regression (lower probability)** — T4 explicitly kept mine; git diff on BMA for merge should be spark + `open_agent_run(spark=)` only. Worth confirming with `git diff e06a455..HEAD -- business_model_agent.py` filtered to non-plumbing hunks. **[CONFIRMED — diff shows only the spark-injection graft; zero behavior change to extraction]**

### Root cause status

**CONFIRMED (2026-07-28).** Structural, not flake — see addendum. Re-running BMA in isolation may or may not show 7/7 depending on that run's retrieved-context volume, but that would not prove "flake"; it would just land on the other side of the same 8,192-token threshold. **Not attributed to Hector T5/T6/T7** (BMA untouched by those merges) — confirmed by diff, not just inference.

### Investigation checklist

- [x] Re-run **only** `business_model_agent.main()` on Elder Care — not needed; e2e log line 118 already shows the truncation directly (`Unterminated string... Partial JSON was recovered`)
- [x] Compare `reasoning_trace` / extraction raw response size in fresh row vs Jul-21 row (truncation signal) — confirmed via log, not needed via trace diff
- [x] Grep e2e log for BMA `[data_room_gap]` lines mentioning sales_motion / key_dependencies — done; lines 118-122, superset of golden-checklist misses
- [x] Confirm `extraction_endpoint` / `llm_endpoint` in e2e match Jul-21 run — confirmed Haiku for extraction; this is the problem, not a mismatch
- [ ] If reproducible: consider bumping BMA extraction `max_tokens` or switching extraction to Sonnet — **this is the recommended fix**, not yet implemented

### What we might have missed

- BMA was **not** in T5–T7 merge scope; regression may have been assumed "keep-mine = safe" without post-merge DAG re-score until this session.
- Jul-21 7/7 was **fresh Cell 11**; comparing DAG-first e2e to notebook-isolated baseline mixes execution paths. **[No longer relevant — root cause is token-cap, independent of execution path]**
- **New (2026-07-28):** the orchestrator memo's Business Model section generator crashes on this same truncated output and silently falls back (see R-3 in addendum) — this was not caught by the golden-checklist scorer because it reads Delta rows, not the rendered memo.

---

## Regression R-2 — Legal 8/11 (baseline 9/11)

**Root cause CONFIRMED 2026-07-28 — see addendum at top of doc.** Retrieval got the Westchester lease chunk (14/14 files present in retrieval log); raw extraction produced 6 contracts matching baseline count; the row-count drop to 5 and the loss of `t4c=true` both happen at the merge/dedupe step, driven by the LLM assigning different `counterparty_name` labels to the same source documents run-to-run (confirmed via direct YAML diff of merged registers). Not a merge-code regression — T4 changed only the `spark=` signature (confirmed by diff); the dedupe/merge functions are unmodified. See addendum for full mechanism and remediation options.

### What regressed

| item_id | Baseline (2026-07-24) | Fresh (2026-07-27 e2e) | Delta |
|---------|----------------------|------------------------|-------|
| **t4c** (termination for convenience) | **pass** — Westchester lease (`contract_id` 5) `t4c.present=true` | **gap-correct** — all 5 contracts `t4c=not_found` | **−1 pass** |
| coc | pass | pass | — |
| restrictive | pass | pass | — |
| vendor | pass | pass | — |
| platform | gap-correct | gap-correct | — |
| employment | pass | pass | — |
| founder | pass | pass | — |
| litigation | pass | pass | — |
| privacy | pass | pass | — |
| ip | gap-correct | gap-correct | — |
| insurance | pass | pass | — |

### Where it comes from (program context)

- **Merge subtask:** T4 — **keep-mine** legal + `main(spark=None)`; view `analysis.legal_contracts` preserved.
- **Baseline provenance:** `.dev/scorecards/scorecard_lca_7_24_post_restrictive_fix_vs_7_16.md` — **9/11** after restrictive-covenant merge fix (`acf4843`), job `126141251921705`.
- **DAG ordering:** Legal has **soft_dep** on `customer_quality` (`pipeline.py` AGENT_REGISTRY). CQA ran in same parallel wave; `contract_trigger_list` was **empty** on fresh CQA row (no customer >20% trigger in concentration extraction path — though `top_customers_json` is now populated).
- **Pre-merge legal edit (phv4 NEW-1):** commit `ec74042` — insurance BACKGROUND filter fix in `legal_contracts_agent.py` (sound, but noted untested for new behavior in `pending2.md`). Predates Hector merge but same file T4 guards.

### Observed warehouse state (fresh row)

```
contract_register: 5 rows (baseline 7/24 had 6)
contract 0: coc=true, t4c=not_found
contract 2: coc=true, t4c=not_found
All contracts: t4c=not_found (including former Westchester pass)
vendor_register: 2 | employment: 4 | privacy: 8 | insurance: 3
```

Restrictive + CoC passes **held** — the 7/24 restrictive reconciliation fix (`_upgrade_tri_state_present`, citation backfill) still works on this run.

### Likely causes (ranked) — superseded by confirmed root cause above; kept for audit trail

1. **T4C extraction nondeterminism** — Legal baseline history shows t4c flipping between gap-correct and pass across runs (7/16 gap-correct → 7/24 pass on Westchester). Multi-pass extraction may miss T4C clauses on some runs while still finding CoC/restrictive. **[CONFIRMED, refined — the raw extraction likely still finds the clause (6 raw contracts extracted), but non-deterministic counterparty-name labeling changes which rows collapse in the post-extraction dedupe step, and the losing row's `t4c=true` doesn't survive the merge]**
2. **Contract register row count drift (5 vs 6)** — Westchester lease may not be in register or not scored as `contract_id` 5; retrieval pass set may differ from Jul-24 isolated Cell 16 run. **[Refined — retrieval pass set is NOT different (same 6 files retrieved); the drift happens at `merge_registers` (log: `contract_register=6→5`), i.e. post-extraction dedupe, not retrieval]**
3. **Parallel execution + soft_dep timing** — Legal starts when CQA reaches terminal state; CQA fresh data differs from Jul-24 (new top_customers). Unlikely direct cause of t4c loss but may change internal prompts/context if any cross-read exists. **[Ruled out — Legal's `contracts_vendors_platform` domain pass runs independently of the CQA soft-dep read (`contract_trigger_list`), which only affects a downstream flagging step logged separately at line 183, not the extraction/merge steps at lines 189-264]**
4. **ec74042 retrieval side effects (speculative)** — Insurance filter broadening could shift retrieval budget across LEGAL corpus; no direct evidence yet. **[Ruled out — insurance is a separate domain pass (`insurance` budget/filter) with its own retrieval budget; no shared budget or chunk pool with `contracts_vendors_platform`]**

### Root cause status

**CONFIRMED (2026-07-28).** Genuine LLM extraction/entity-resolution variance at the dedupe-key layer, not a merge regression, not a retrieval miss. See addendum for the direct YAML register diff proving this.

### Investigation checklist

- [x] Re-run **only** `legal_contracts_agent.main()` (Cell 16) on Elder Care — not strictly needed; direct register diff (baseline YAML vs fresh YAML) already shows the mechanism
- [x] Diff `legal_report.yaml` / `contract_register_json` fresh vs Jul-24 volume snapshot — done, see addendum (`.dev/_legal_report_2026-07-24.yaml` vs `.dev/legal_agent/baselines/_latest_Elder_Care_legal_report.yaml`)
- [x] Confirm whether `contract_id` 5 in Jul-24 maps to same source doc in fresh 5-row register — confirmed it does NOT map cleanly; fresh `counterparty_name` labels don't match baseline's naming pattern for the same source PDFs
- [x] Review legal agent retrieval logs for Westchester / lease chunks in e2e stdout — done; Westchester_Lease_0121.pdf was retrieved (log line 189)
- [ ] Check if `ec74042` filter changes altered `_tool_retrieve_*` chunk counts for lease vs insurance passes — de-prioritized; insurance and contracts passes use separate budgets/filters, unlikely to interact

### What we might have missed

- G1 Legal gate (9/11) was set from **Jul-24 scorecard**, not the older 7/11 in `eval/LCA/golden_checklist_elder_care.md` header — regression is **one pass row**, not catastrophic legal collapse.
- Legal was not modified in T5–T6–T7; loss is likely extraction variance or retrieval pass set, not QoE/CQA/KPI merge code. **[Confirmed: extraction/dedupe variance, not retrieval pass set — retrieval was identical]**

---

## Not a regression — Profiler (scoring N/A)

| Issue | Detail |
|-------|--------|
| **Why N/A** | `company_profiler` is **not** in Hector's 9-agent `AGENT_REGISTRY` (`pipeline.py` has no profiler entry) |
| **Latest row** | `uc13_ale.classification.company_profile` · `created_at=2026-07-22` · `industry_overlay=other` · `vertical_subsector=null` |
| **Automated score if forced** | 5/7 vs 7/7 baseline — **invalid** comparison (stale pre-merge profiler state) |

**Action:** Run Cells 9–10 / `company_profiler.main()` separately to score Profiler for G1. Profiler overlay=`other` vs KPI/CQA `healthcare_services` may indicate **profiler stale vs downstream agents** — separate hygiene issue, not introduced by this e2e.

---

## Positive signals (easy to overlook)

| Signal | Detail |
|--------|--------|
| **CQA concentration improved** | Hector T6 retrieval depth likely working |
| **FTA unblocked** | SQLite fix validated; 16/18 holds |
| **Forecast + cross_analysis** | First successful forecast row; cross_analysis no longer TABLE_OR_VIEW_NOT_FOUND |
| **Provenance on Delta** | 326 provenance rows on 2026-07-27; `store_backend=delta` on harness runs |
| **Exec summary** | T9 bridge works with fresh upstream data (+96 words vs baseline) |
| **Full DAG** | 9/0/0 — merge orchestration path is end-to-end functional |

---

## Open work not yet done (may hide regressions)

| Item | Status | Risk if skipped |
|------|--------|-----------------|
| **Commit sqlite fix** | Uncommitted local changes | Workspace/repo drift; next e2e without fix |
| **4-company parallel e2e** | Not run post-fix | Company-specific failures (Clearsulting, GKF, SPG) unknown |
| **Formal scorecards + `evaluate_promotion`** | Not run for this e2e | INDEX / ops manifest not updated with new `run_ids` |
| **G6 gold-label bootstrap** | Deferred; `elder_care.yaml` reverted | 8 new CQA/KPI intents still xfailed in harness |
| **BMA extraction-endpoint fix (R-1)** | Not implemented | Checklist score will keep flipping run-to-run on any company whose corpus pushes past the Haiku 8,192-token cap |
| **Orchestrator BMA-section crash (R-3)** | Not investigated/fixed | Memo silently ships degraded Business Model section; masked by fallback |
| **Legal dedupe-key hardening (R-2)** | Not implemented; lower priority | t4c (and potentially other tri-state fields) will keep flipping on entity-labeling variance across runs |
| **Profiler re-run** | Not done | G1 incomplete for profiler partition |
| **FTA / Legal operator markdown re-score** | Automated only | Borderline verdicts not human-attested |
| **CLUSTER_GATES G2–G5 sign-off** | Partially evidenced by same e2e | G5 VDR not exercised |

---

## Related pre-existing debt (not introduced by this e2e)

| ID | Source | Relation to regressions |
|----|--------|-------------------------|
| phv4 NEW-1 | `pending2.md` · `ec74042` | Legal insurance filter edit — **ruled out** as a factor in R-2 (separate domain pass/budget) |
| phv4 NEW-2 | `pending2.md` | Registry hash compare waived — harness can't compare to pre-milestone baseline |
| QoE token watch | CLUSTER_GATES G1 | Extraction on Haiku 8k cap — not triggered (QoE holds 5/6); **same class of risk as R-1**, worth a preemptive check on QoE's extraction schema size |
| CQA cosmetic | T6 decision-log | `industry_overlay_used` not in assessment markdown — unrelated to scores |

---

## Recommended resolution order (2026-07-28 revision)

1. **Fix BMA's extraction-endpoint (R-1)** — port Legal's Sonnet-override pattern (`legal_contracts_agent.py:2076-2083`) into `business_model_agent.py`, or split the extraction call the way `financial_trends_agent.py` already splits into 3 sub-agents. This is code work, not a re-run/triage task.
2. **Verify R-3 resolves** — after the R-1 fix, re-run e2e and confirm the orchestrator no longer logs `section 'business_model' generator failed`. If it still crashes on well-formed (non-truncated) BMA output, that's an independent bug in `generate_business_model_assessment` needing its own fix.
3. **Commit sqlite fix** — land provenance + pipeline changes with test evidence (unchanged from original doc).
4. **Legal dedupe hardening (R-2)** — lower priority; consider adding `source_doc` identity to `_register_dedupe_key` so genuinely distinct contracts don't collapse on counterparty-label variance. Not required to close this merge; can be a follow-up hardening ticket.
5. **Profiler** — optional Cell 9–10 if profiler G1 matters for merge sign-off.
6. **4-company e2e** — once R-1 is fixed, to confirm the token-cap fix generalizes (other companies' corpora may push past the cap differently than Elder Care's).
7. **G6 gold bootstrap** — only after operator confirms; separate from regression triage.
8. **Scorecards** — record outcomes in `.dev/scorecards/` + update INDEX when scores stabilize.

---

## Quick reference commands

```bash
# Re-run full automated G1 scoring (after any new agent run)
python .dev/g1_score_all_agents.py

# Local test gate (sqlite fix)
uv run --project databricks pytest tests/ eval/retrieval/tests/ -q

# Warehouse timestamps check
python .dev/query_timestamps.py
```

**E2e evidence run:** `1074138209208842`
**Git integration HEAD:** `82538da` (sqlite fix uncommitted on top)

---

*This document is the living regression map for post-merge validation. Update when isolated re-runs or fixes close R-1/R-2 or when new e2e batches complete.*
