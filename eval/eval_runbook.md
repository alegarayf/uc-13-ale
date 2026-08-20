# UC-13 Eval Runbook

**What this is:** a plain-language guide to the eval system that lives under `eval/` — what it measures, what the commands do, how to read what they produce, how to bring a new company onto it, and how to use its output to make the product better. No project history, no process jargon — just the system as it exists today and how to drive it.

**Companion:** [`eval_program_playbook.md`](eval_program_playbook.md) — current company coverage, trust boundaries, ledger map, open items, product backlog from signals, rollout waves, and execution order for full pipelines + baselines across SharePoint companies.

---

## 1. What problem this solves

The pipeline (parser → 7 diligence agents → executive summary) makes claims about a company based on documents in its data room. Two things can go wrong that are easy to miss by eye:

1. **The right document never gets found.** An agent asks a retrieval question and the system returns the wrong chunks, or none.
2. **The claim doesn't match what the document actually says.** The agent found something, but paraphrased it wrong, cited the wrong page, or invented a number.

This eval system exists to catch both, per company, with numbers instead of vibes — and to give you a single place to see, for any company, "how much of this can I actually trust right now."

It is not a code-quality test suite (that's `pytest`). It's a **measurement system for the product's actual output on real corpora.**

---

## 2. The five things it measures

Every company gets scored on five independent layers. A company can be strong on one and weak on another — they don't average together.

| Layer | Question it answers | How it's measured | Where the result lives |
|---|---|---|---|
| **Ingest completeness** | Did the company's documents actually make it into the corpus? | Chunk/document counts compared against what should have been parsed | `trust_statement.md`, layer `ingest_completeness` |
| **Retrieval** | When an agent asks a question, does the search return the right chunks? | Recall/precision/basis-conflict per named "intent" (a specific retrieval question), measured against hand-verified correct chunks ("gold") | Harness runs, `eval/retrieval/reports/*.json`, `trust_statement.md` layer `retrieval` |
| **Agent fields** | Did the agent produce the fields it's supposed to produce, structurally? | Golden checklists (per-agent, hand-written pass/fail rubrics) | `eval/<AGENT>/golden_checklist_elder_care.md`, promotion gate |
| **E2E / pipeline** | Did a full pipeline run for this company actually complete and link to a scored checklist? | Presence of a linked, scored pipeline run | `trust_statement.md` layer `e2e` |
| **Content correctness** | Is what the agent *wrote* actually supported by the document it cites? | Per-claim verdicts (`supported` / `contradicted` / `unsupported`) checked by a deterministic verifier, an LLM judge, or a human, depending on how much that surface is trusted yet | `eval.s2_scores` table, `trust_statement.md` layer `content_correctness` |

**Content correctness only exists today for three "surfaces":** `fta_numeric` (financial numbers), `legal_register` (legal contract/register claims), and `exec_summary` (executive summary prose claims). Everything else in the pipeline (BMA, CQA, KPI, QoE, Profiler outputs) is checked structurally via golden checklists, not claim-by-claim.

---

## 3. Where everything lives

```
eval/
├── eval_runbook.md              ← this file (commands + layer definitions)
├── eval_program_playbook.md     ← coverage, trust, ledger, backlog, rollout
├── retrieval/                   ← the retrieval measurement engine
│   ├── intent_registry.yaml     ← the ~57 named retrieval questions ("intents")
│   ├── gold_labels/<slug>.yaml  ← per-company hand-verified correct chunk ids
│   ├── gold/
│   │   ├── bootstrap.py         ← auto-generates gold labels from the corpus
│   │   ├── gold_exclusions.yaml ← per-company list of intents excluded from aggregate scoring
│   │   └── kpi_claim_intent_map.yaml
│   ├── harness.py               ← runs retrieval against gold, computes metrics
│   ├── harness_cli.py           ← command-line entry point for harness.py
│   ├── store.py                 ← where run results get written (SQLite locally, Delta on cluster)
│   ├── promotion_gate.py        ← links a golden-checklist score to a pipeline run
│   ├── companies.py             ← turns a display name ("Elder Care") into a slug (elder_care)
│   ├── ingest_preflight.py      ← checks whether a company's docs actually ingested
│   ├── exemptions.py            ← records "this intent can't be honestly gold-labeled for this company, here's why"
│   ├── eval_debt.py             ← records "this is a known, tracked gap, here's what would close it"
│   ├── trust_statement.py       ← rolls all five layers into one report
│   └── reports/                 ← JSON output of each harness run
├── content/                     ← the content-correctness (claim-level) measurement engine
│   ├── agreement.py             ← the rules for "do these two values/verdicts agree"
│   ├── calibration.py           ← measures how well an LLM judge agrees with a human on a sample
│   ├── s2_writer.py             ← writes claim-level verdicts to the score table
│   ├── legal_register_verifier.py  ← deterministic checker for legal_register claims
│   ├── spot_check.py            ← tooling for human spot-checks
│   └── extract_rubric_manifests.py
├── program/                     ← the durable, cross-company records
│   ├── registry.yaml            ← the master ledger: every open/closed decision, deferral, and disposition
│   ├── onboarding_runbook.md    ← the exact step-by-step for adding a company (this file summarizes it in §7)
│   ├── trust_statement.md       ← the current, generated trust report (regenerate — don't hand-edit)
│   ├── eval_exemptions.yaml     ← the exemption store (see above)
│   └── eval_debt/eval_debt.yaml ← the eval-debt ledger (see above)
├── FTA/, BMA/, CQA/, KPI/, QOE/, PROFILER/, LCA/   ← per-agent golden checklists + baselines
└── architecture/rallyday/       ← standing reference docs on the wider repo (not eval-specific)
```

---

## 4. The commands, what they do, and how to read the output

All commands below are run from the repo root. Company names are the SharePoint display name (`"Elder Care"`, `"Clearsulting"`) — the tools fold this into a lowercase-underscore slug internally (`elder_care`) and use that slug for file names and lookups.

### 4.1 Ingest preflight — "did the documents actually land?"

```bash
python -m eval.retrieval.ingest_preflight --company "<Display Name>" --catalog uc13_ale --backend sql_chunk_count
```

**What it does:** counts distinct documents that should have been parsed for this company (per the classifier) vs. how many actually have chunks in the corpus.

**How to read it:** prints a completeness ratio and a per-document-type breakdown. Exit code `0` means the probe ran (not that ingestion is complete — read the ratio). Exit code `1` with a stderr message means the probe itself failed (e.g. bad catalog, no warehouse connection) — this never crashes silently, it always returns a typed status: `measured`, `probe_failed`, or `denominator_undefined` (no expected-document baseline exists yet to compare against).

There's a second backend, `doc_status`, for document-level detail; it's currently always `denominator_undefined` (no expected-count baseline wired for it yet) — use it for qualitative status breakdown only, not a completeness percentage.

### 4.2 Gold-label bootstrap — "what are the correct answers for retrieval?"

Gold labels are the hand-verified (or heuristically-derived) correct chunk ids for each of the ~57 registered retrieval intents, per company. The harness can't score retrieval without them.

```bash
python -m eval.retrieval.gold.bootstrap --company "<Display Name>" --catalog uc13_ale
```

This needs a live Spark session (it queries the corpus directly), so from a laptop with no cluster attached you submit it as a Databricks job instead — see `.dev/agent-databricks-recipes.md` for the submit helper. Output lands at `eval/retrieval/gold_labels/<slug>.yaml`.

**How to read a gold file:** each row is one intent for one company, with:

| Field | Meaning |
|---|---|
| `gold_status` | `ready` (usable), `partial` (usable but incomplete), or `bootstrap_failed` (no usable positives found — this intent is skipped in scoring, not silently zeroed) |
| `gold_method` | how the positives were derived: `citation_backfill` (traced from an agent's actual citations — most trustworthy), `section_range`, `filename_closure` (every chunk in a matched file is a positive — can bloat badly, see below), `provenance_replay`, `manual_audit` |
| `positive_chunk_ids` | the correct answers |
| `aggregate_exclude` / `exclude_reason` | if true, this intent is deliberately left out of aggregate/rollup recall numbers (currently only reason in use: `no_citation_source`) — it still exists and can be read per-intent, it's just not folded into the summary |

**Watch for "bloated" gold:** `filename_closure` gold can produce thousands of positives for one intent if the whole matched file is huge (e.g. a full financial statement PDF). When that happens, recall@10 becomes mathematically incapable of exceeding ~1% even for a perfect retriever — it's not a retrieval failure, it's a measurement artifact. `eval/program/eval_debt/eval_debt.yaml` names any intent currently in this state per company (see §4.7). Treat a bloated intent's recall number as not-interpretable, not as "broken retrieval."

### 4.3 Intent exemptions — "this can't be honestly gold-labeled"

Some intents simply can't get real gold for some companies (e.g. a company has zero documents in the `legal_register` category). Instead of forcing a fake gold label, record an exemption.

```bash
python -m eval.retrieval.exemptions add \
  --company "<Display Name>" --intent-id <intent_id> \
  --surface <fta_numeric|legal_register|exec_summary|null> \
  --coverage <eliminates|narrows|null> \
  --reason <corpus_absent|corpus_thin|overlay_mismatch> \
  --evidence <key=value> [--evidence <key=value> ...] \
  --approved-by <name>

python -m eval.retrieval.exemptions list --company "<Display Name>"
```

**Field meaning:**
- `surface`/`coverage` are `null`/`null` together, or both set (`eliminates` = the surface can never be scored for this company; `narrows` = it's scored on a reduced population).
- `reason` is one of: `corpus_absent` (zero relevant docs), `corpus_thin` (some, not enough), `overlay_mismatch` (the wrong industry overlay is being applied).
- `--evidence` is free-form `key=value` pairs backing the reason (e.g. `legal_doc_count=0`).

Exemptions feed straight into the trust statement's `known_gap` rows — they're the mechanism for "we know this is missing and here's why," not a workaround to hide a gap.

### 4.4 Harness runs — "how good is retrieval, right now, for this company?"

This is the core measurement tool. It runs every registered intent's retrieval query against the live corpus, compares results to gold, and records per-intent and aggregate metrics.

```bash
python -m eval.retrieval.harness_cli run \
  --store-backend <sqlite|delta> \
  --run-type <baseline|enhancement|ablation|ci_fixture> \
  --company-name "<Display Name>" \
  --catalog uc13_ale \
  [--gold-path <path>] \
  [--baseline-ref-run-id <run_id>] \
  [--affected-intents <intent_id> ...] \
  [--ablation-config '{"arm": "<name>"}']
```

**`--store-backend`:** `sqlite` is for laptop iteration (writes to a local, gitignored file at `eval/retrieval/.local/re2_store.sqlite`); `delta` writes to the shared warehouse tables under `<catalog>.ops.*` and is what you use for anything meant to be compared or shared. Cluster runs must use `delta`.

**`--run-type`, what each one is for:**

| Run type | Use it for | Intent scope |
|---|---|---|
| `baseline` | Establishing "this is where we stand" for a company — the reference point everything else compares against | Defaults to **all** registered intents when `--affected-intents` is omitted |
| `enhancement` | Measuring the effect of a specific retrieval/prompt/config change on specific intents | **Requires** `--affected-intents` — you name exactly what you changed |
| `ablation` | Systematically comparing retrieval "arms" (see below) against a pinned baseline | Defaults to all intents; `--ablation-config '{"arm": "<name>"}'` picks the arm |
| `ci_fixture` | Running against the frozen CI test slice, not the live corpus | n/a — used by automated tests |

**Ablation arms available today** (`--ablation-config '{"arm": "merge_rank_on"}'`, etc.): `merge_rank_on`, `merge_rank_off`, `sim_only`, `tier_only` — these toggle how retrieved chunks get ranked/merged. Each produces its own run and a set of deltas against `--baseline-ref-run-id`.

**Validating a baseline before comparing against it:**

```bash
python -m eval.retrieval.harness_cli validate-baseline \
  --store-backend <sqlite|delta> --catalog uc13_ale \
  --baseline-ref-run-id <run_id> --current-run-id <run_id>
```

This checks that the baseline you're about to compare against shares the same intent registry version, gold snapshot, and ingestion snapshot as the current run. If any of those drifted (e.g. the corpus was re-ingested since that baseline was recorded), comparing against it is meaningless and the tool raises rather than silently producing a number.

**Reading a run's output** — every run writes a JSON report to `eval/retrieval/reports/<run_id>.json` and (on `delta`) rows to `<catalog>.ops.retrieval_harness_runs` / `retrieval_harness_results` / `retrieval_harness_deltas`. Key fields:

| Field | Meaning |
|---|---|
| `run_id` | Unique id for this run — always quote it when referring to a result |
| `harness_status` | `complete` (finished normally), `incomplete` (didn't finish), `invalid` (finished, but shouldn't be trusted or compared — e.g. a known infra issue during the run) |
| `gate_pass` | Whether this run cleared the pass/fail thresholds on the gate metrics, across the gate-eligible intent scope |
| `eval_status` (per intent) | `evaluated`, or `skipped_bootstrap_failed` (no usable gold for this intent — excluded from scoring, not scored as a zero) |
| `recall_at_10` | Of the correct chunks, what fraction showed up in the top 10 results (higher is better) |
| `precision_at_10` | Of the top 10 results, what fraction were actually correct (higher is better) |
| `basis_conflict_at_10` | Rate of retrieving chunks that actively contradict the correct basis (lower is better) |
| `mrr` | Mean reciprocal rank — how high up the first correct result appeared, on average (higher is better; tracked but not gating) |
| `ablation_arm` | Which arm produced this run, if it's an ablation run |
| `baseline_ref_run_id` | The baseline this run's deltas were computed against |

**Comparing two runs (`HarnessDelta` rows):** each row is one intent × one metric, with `before`, `after`, `delta`, and whether that delta passed or failed the gate for that intent. This is what an ablation or enhancement run's real payload looks like — read the deltas, not just the aggregate.

### 4.5 Golden checklists — all seven agents

Every diligence agent (FTA, Legal/LCA, BMA, CQA, KPI, QoE, Profiler) has a hand-written **golden checklist**: a git-tracked markdown rubric an operator scores after a pipeline run. Checklists measure **structural extraction fidelity** — did the agent populate the fields it should, with citation-backed grounding — not claim-by-claim content correctness (that is the separate S2 layer in §2 for FTA numeric, legal register, and exec summary only).

**Canonical path:** `eval/<AGENT>/golden_checklist_<slug>.md` (Elder Care → `golden_checklist_elder_care.md`). FTA also has Clearsulting and SPG checklists on disk; the other six agents are Elder Care–only today.

#### Shared file shape

| Section | Contents |
|---|---|
| Metadata table | `catalog`, `company`, source table or YAML path, `spec ref`, pipeline `run_id` / git SHA / E2E timestamp when scored |
| Verdict key | Per-agent legend — see table below |
| Checklist table | `item_id` · `display_name` · `verdict` · `notes` — one row per rubric item |
| Summary | Pass counts and the integer `N/M` score used as `candidate_score` / `candidate_total` at promotion time |

Scoring is **manual**: a human reads the agent's live output against the rubric. It is not an automated LLM-judge step. Structural contract (row count vs in-code `GOLDEN_CHECKLIST_COVERAGE`) is enforced by `tests/test_golden_checklist_elder_care.py` (parameterized hub for BMA/CQA/KPI/QoE/Profiler/LCA) and `tests/test_golden_checklist_fta.py` for FTA.

#### Verdict vocabulary (agent layer)

| Verdict | Meaning | Scoring weight |
|---|---|---|
| `pass` | Field meets rubric threshold | Counts toward numerator (all agents) |
| `partial` | Thin or incomplete extraction | **FTA only:** 0.5 in weighted score. **All others:** documented for legend parity; **no half-credit** — integer pass-count only |
| `gap-correct` | Agent correctly reported its own limitation (`data_room_gaps`, structured nulls, `unable_to_assess`) | Stays in denominator; credited as a pass-row for Legal-style agents; counts as pass for promotion numerator where the checklist Summary says so |
| `n/a` | Not applicable — two distinct cases: **corpus-inapplicable** (Legal convention; stays in denominator per that rubric) vs **precondition-exclusion** (QoE only — item removed from both numerator and denominator; see QoE quirks below) |
| `miss` | **FTA only** — field absent or fails threshold | 0 in weighted score |

The promotion gate always compares **integer** `candidate_score` values. FTA's weighted points (pass=1, partial=0.5, miss=0) are rounded/summed to an integer before linkage (e.g. 16/18).

#### Per-agent reference

| Agent | Folder | `e2e_agent_id` | Checklist rows (`candidate_total`) | Elder Care regression floor | Output source | Linkage |
|---|---|---|---:|---|---|---|
| **FTA** (Financial Trends) | `eval/FTA/` | `fta` | 18 | ≥ **16/18** weighted points | `uc13_ale.analysis.financial_trends` | `evaluate_promotion(...)` **or** direct `record_e2e_linkage` CLI (§4.6) |
| **Legal / LCA** | `eval/LCA/` | `legal` | 11 | ≥ **7/11** `pass` rows (4 `gap-correct` rows stay in denominator) | `uc13_ale.analysis.legal` + `legal_report.yaml` | same as FTA |
| **BMA** | `eval/BMA/` | `bma` | 7 | No fixed floor — beat prior promoted baseline | `uc13_ale.analysis.business_model` | `evaluate_promotion(...)` |
| **CQA** | `eval/CQA/` | `cqa` | 6 | same | `uc13_ale.analysis.customer_quality` | `evaluate_promotion(...)` |
| **KPI** | `eval/KPI/` | `kpi` | 3 | same | `uc13_ale.analysis.kpi` | `evaluate_promotion(...)` |
| **QoE** | `eval/QOE/` | `qoe` | **6 or 5** (precondition-adjusted — see below) | same | `uc13_ale.analysis.quality_of_earnings` | `evaluate_promotion(...)` |
| **Profiler** | `eval/PROFILER/` | `profiler` | 7 | same | `uc13_ale.classification.company_profile` | `evaluate_promotion(...)` |

For BMA/CQA/KPI/QoE/Profiler, the **first** scored run for a company hits `baseline_bootstrap` (§4.6) — there is no prior baseline to regress against. After that, any score below the last **promoted** baseline blocks unless waived.

Deterministic rule/flag logic (BMA revenue-durability, CQA thresholds, KPI overlay selection, QoE downstream addback math) lives in **pytest fixtures**, not checklist rows — checklists judge LLM extraction fidelity only.

#### Agent-specific quirks (still accurate)

| Agent | Quirk |
|---|---|
| **FTA** | Weighted scoring (`partial`=0.5); floor ≥16/18 is the operational bar, separate from the promotion gate's "beat last promoted score" rule |
| **Legal / LCA** | Canonical checklist is **`eval/LCA/golden_checklist_elder_care.md`** (git-tracked). A gitignored `.dev/legal_agent/eval/` copy may exist for structural tests — score against the tracked path only |
| **BMA** | `revenue_durability_flag` rule correctness is unit-test owned, not a checklist row |
| **CQA** | `contract_trigger_list` → Legal handoff is documented in the checklist header as an integration note, **not** a scored row |
| **KPI** | Overlay-selection **rule** is unit-test owned; checklist checks whether the LLM's overlay-relevant extraction matched the corpus |
| **QoE** | **Precondition gate:** tier-classification item (`tier_classification_fidelity`) is scorable only when FTA's `addback_schedule_json` parses to a **non-empty** array for the company (same bar QoE's `_load_addback_passthrough` applies at run time). On failure, mark that row precondition-exclusion `n/a` and pass **`candidate_total=5`** (exclude 1 item) instead of 6. At manual re-score time, re-derive the presence check from FTA's latest `financial_trends` row — the passthrough value is not persisted on QoE's output table |
| **Profiler** | Requires `open_agent_run`/`close_agent_run` in `company_profiler.py` so a pipeline manifest `run_id` exists before linkage — instrumentation is shipped. **Notebook path only** for eval: headless workflow runs may write manifests to a different catalog unless `RE2_CATALOG` and `set_pipeline_thread` match the eval notebook setup |

**Do not invent scores.** If a company lacks a scored checklist or a real pipeline `run_id`, skip promotion for that agent and open an eval-debt row (§4.7) instead.

### 4.6 Promotion gate — "does this pipeline run's checklist score count as an improvement?"

The promotion gate applies to **all seven agents** (§4.5). It decides whether a newly scored checklist `N/M` becomes the next **promoted baseline** in `uc13_ale.ops.retrieval_harness_runs`, or is rejected as a regression. FTA and Legal may also call `record_e2e_linkage` directly via CLI (bypasses this gate — use only when you intentionally skip regression checking; see `eval/retrieval/README.md`).

This is a Python function, not a CLI (there is no `promotion_gate` command):

```python
from eval.retrieval.promotion_gate import evaluate_promotion
from eval.retrieval.store import DeltaEvalStore

store = DeltaEvalStore(spark, catalog="uc13_ale")
result = evaluate_promotion(
    store,
    "<pipeline_agent_run_id>",     # from the agent's own main() run — NOT a harness run_id
    e2e_agent_id="fta",            # one of: fta, legal, bma, cqa, kpi, qoe, profiler
    company_name="<Display Name>",
    catalog="uc13_ale",
    candidate_score=<int>,          # from a scored golden checklist
    candidate_total=<int>,          # checklist denominator (agent-specific, e.g. FTA=18, Legal=11, BMA=7)
    e2e_snapshot_table="<catalog>.analysis.<agent_table>",
)
print(result.status)
```

**Reading `result.status`:**

| Status | Meaning |
|---|---|
| `baseline_bootstrap` | First-ever recorded score for this (agent, company) — nothing to compare against yet, so it's accepted unconditionally |
| `promoted` | Score matched or beat the prior recorded baseline |
| `promotion_blocked` | Score regressed against the prior baseline, and no waiver was supplied |
| `promotion_waived` | Score regressed, but an operator-supplied `waiver_id` (format `W<number>`) explicitly accepted the regression |

**Do not invent `candidate_score`/`candidate_total`/`run_id` values.** If a company doesn't have a scored golden checklist yet, don't call this function for that agent — open an eval-debt row instead (§4.7) and move on. A missing promotion input is a documented gap, not a blocker to work around with made-up numbers.

#### State machine (all agents)

```
pipeline run completes (run_id in manifest)
        │
        ▼
operator scores golden checklist → candidate_score / candidate_total
        │
        ▼
evaluate_promotion(...) compares candidate vs prior promoted baseline
        │
   ┌────┴────────────────────────────────────────────┐
   │ no prior row with non-null e2e_checklist_score │ prior promoted baseline exists
   ▼                                                 ▼
baseline_bootstrap ──────────────► promoted    candidate >= prior ?
(auto-accept)    record_e2e_linkage writes          │              │
                 score to manifest                  yes            no
                                                    ▼              ▼
                                              promoted      promotion_blocked
                                              (writes)      (NO manifest write —
                                                             score stays NULL)
                                                                   │
                                                     waiver_id=W<number> supplied
                                                                   ▼
                                                          promotion_waived
                                                          (writes score)
```

**Write-on-promote invariant:** `record_e2e_linkage` persists `e2e_checklist_score` to the manifest **only** on `baseline_bootstrap`, `promoted`, or `promotion_waived`. A blocked regression leaves the manifest score **NULL**, so it can never silently become the next comparison bar.

**Prior-baseline selection:** the gate queries the most-recent `retrieval_harness_runs` row where `run_type='pipeline'`, `harness_status='complete'`, `e2e_checklist_score IS NOT NULL`, matching `e2e_agent_id` + `company_name` + `catalog`, ordered by `completed_at DESC` — excluding the run being scored. Combined with write-on-promote, "most-recent non-null score" equals "last promoted baseline."

**Waiver escape hatch:** when `candidate_score < prior_score`, pass `waiver_id="W<number>"` (regex `^W\d+$`) to accept the regression anyway. Waivers must be documented (regression amount + rationale) in the registry/scorecard — same convention as other program waivers. Malformed waiver IDs raise `InvalidWaiverIdError`.

Per-agent `candidate_total` values and QoE's precondition-adjusted denominator are in §4.5.

### 4.7 Eval debt — "known gaps, tracked, with a defined closing condition"

```bash
python -m eval.retrieval.eval_debt open --company "<Display Name>" --surface <surface|null> --kind <kind> --closes-when "<condition>"
python -m eval.retrieval.eval_debt list --company "<Display Name>"
```

Every open row must cite at least one piece of evidence that resolves to a real file, a real trust-statement row, or a real registry entry — you can't open a debt row that points at nothing. There's also a hard ceiling (`open_debt_high_water_mark` in `eval/program/eval_debt/eval_debt.yaml`) on how many rows can be open at once; you raise that ceiling deliberately before opening a row that would exceed it, rather than it silently growing unbounded.

Read the current ledger directly (`eval/program/eval_debt/eval_debt.yaml`) to see what's open right now, per company — this file is the live source of truth and will have moved since this runbook was written.

### 4.8 Trust statement — the one-page rollup

```bash
python -m eval.retrieval.trust_statement generate --catalog uc13_ale --registry eval/program/registry.yaml
```

Regenerates `eval/program/trust_statement.md` from live warehouse state, the exemption store, and the eval-debt ledger. **Never hand-edit this file** — it's fully generated; re-run the command after anything changes.

**How to read a row:**

| Field | Meaning |
|---|---|
| `company` / `layer` / `surface` | Which of the five layers (§2), and which content-correctness surface if applicable |
| `attestation` | `attested` (fully checked, no caveats), `partial` (checked, with named gaps), `not_attested` (nothing to report yet — usually `no_completed_run`), `known_gap` (deliberately excluded, with a reason — see exemptions) |
| `reason` | Why the attestation is what it is, when not `attested` (e.g. `no_completed_run`, `claim_failures`, `incomplete_corpus`) |
| `method` | How the measurement was taken, where applicable (e.g. `sql_chunk_count` for ingest) |
| `rung` | For `content_correctness` rows only — see §4.9 |
| `evidence_refs` | Pointers to the actual run ids / files backing this row — always traceable, never just an assertion |
| `known_gaps` | Human-readable notes on what's missing or caveated |

### 4.9 Rungs — how much a content-correctness surface is trusted to check itself

A "rung" says who/what is allowed to verify claims on a given surface, based on how well that method has been shown to agree with a human:

| Rung | Meaning | Who checks the claim |
|---|---|---|
| `deterministic` | A hand-written verifier resolves it (e.g. cross-referencing a structured register field against corpus text) | Code — no LLM judgment involved |
| `judge` | An LLM judge has been calibrated against human labels and cleared the agreement threshold for this surface | The judge model |
| `human` | The judge hasn't (yet) cleared the calibration threshold for this surface | A human, via spot-check tooling (`eval/content/spot_check.py`) |

**Today:** `legal_register` is `deterministic`. `fta_numeric` and `exec_summary` are `human` — meaning no surface has yet earned `judge` rung. A surface moves from `human` to `judge` only after a calibration run (`eval/content/calibration.py`) shows the judge agreeing with human/operator labels above the required threshold for that surface. Nothing here is prompt-tuning to "pass" the calibration — the calibration measures agreement with true labels, and a failing result is treated as an accurate finding about the current judge stack, not a bug in the eval.

**Claim verdicts** you'll see in `eval.s2_scores` and in trust-statement `known_gaps`: `supported`, `contradicted`, `unsupported`. A `known_gaps` note like "20/23 claims failed on legal_register" means 20 of 23 checked claims did not come back `supported` — that's real product signal about that company's output quality on that surface, not an eval defect.

---

## 5. Bringing a company onto the system

This is the exact, runnable sequence — the same one `eval/program/onboarding_runbook.md` documents in full detail (read that file for the complete version with all edge cases; this is the plain-English summary).

1. **Check the registry** (`eval/program/registry.yaml`) — see if anything already applies to this company.
2. **Ingest preflight** (§4.1) — confirm the documents actually landed before measuring anything downstream.
3. **Gold bootstrap** (§4.2) — generate the correct-answer set for retrieval. Needs a cluster; submit as a job from the laptop.
4. **Exemptions** (§4.3) — for any intent the corpus genuinely can't support (e.g. no legal documents at all), record why instead of forcing bad gold.
5. **Harness baseline** (§4.4, `--run-type baseline`) — establish the retrieval reference point for this company.
6. **Golden checklists + promotion** (§4.5, §4.6) — score each agent's checklist against live output, then link via `evaluate_promotion` (or FTA/Legal direct CLI). Skip agents that don't have both a scored checklist and a real pipeline `run_id` yet.
7. **Eval debt** (§4.7) — for anything skipped in step 6, or any other known shortfall, open a debt row naming exactly what would close it.
8. **Regenerate the trust statement** (§4.8) — confirm the new company's rows look right: expected `known_gap` entries from step 4, ingest status from step 2.

**If any step requires a judgment call that isn't covered above** — a new metric, a fabricated label, an improvised flag that doesn't exist in any command's `--help` — stop. That's a real gap in this runbook, not something to work around. Note it in the registry and resolve it before continuing that company's walk.

**Repeating this for more companies (including ones added later, from beta usage):** the sequence is identical for every company — there's nothing Elder-Care-specific or Clearsulting-specific baked into it. Just substitute the new SharePoint display name at every step. The two things that reliably need a human decision per new company are: (a) which intents need exemptions because that company's corpus genuinely lacks certain document types, and (b) whether its gold bootstrap produced any bloated `filename_closure` intents (§4.2) that need a debt row.

---

## 6. Using the results to improve the product

The eval system is a **measurement loop**, not a pass/fail gate you clear once. The intended cycle:

**For retrieval:**
1. Run a `baseline` (§4.4) to know where you stand.
2. Make a targeted change (chunking, embedding, ranking, prompts) and run `enhancement` (naming the affected intents) or `ablation` (comparing named arms) against that baseline.
3. Read the per-intent `HarnessDelta` rows, not just the aggregate — a change can help most intents and quietly hurt a specific one.
4. Decide, promote the new baseline if it's a net improvement, repeat.

**For content correctness:**
1. Look at `eval.s2_scores` verdicts and the trust statement's `known_gaps` for a surface (e.g. "20/23 claims failed on legal_register").
2. Pull the actual failing claims and look at them — for each one, decide whether the *agent* is wrong (bad extraction, hallucinated citation, wrong page) or the *gold/label* is wrong (operator mislabeled, ambiguous claim).
3. Fix whichever is actually broken — agent logic/prompt, or the label — and re-run to confirm.
4. This disagreement list **is** your product-quality backlog for that surface. Low agreement isn't a verdict that the eval is broken; it's the eval doing its job.

**For getting a surface onto `judge` rung** (so an LLM, not a human, can check it going forward): run `eval/content/calibration.py` against a labeled sample for that surface. If judge-vs-human agreement clears the threshold, the surface can be recorded as `judge` rung. If it doesn't, that's an honest measurement of the current judge/prompt/retrieval stack for that surface — improving the judge prompt, model, or the retrieval feeding it and re-calibrating is the path forward, not lowering the threshold.

**After any of the above**, regenerate the trust statement (§4.8) — it's your before/after scorecard across every company and layer at once.

---

## 7. Quick reference — command index

| I want to... | Command |
|---|---|
| Check if a company's docs ingested | `python -m eval.retrieval.ingest_preflight --company "<Name>" --catalog uc13_ale --backend sql_chunk_count` |
| Generate gold labels for a company | `python -m eval.retrieval.gold.bootstrap --company "<Name>" --catalog uc13_ale` (cluster) |
| Record a corpus gap that blocks gold-labeling an intent | `python -m eval.retrieval.exemptions add --company "<Name>" --intent-id <id> --surface <s> --coverage <c> --reason <r> --evidence k=v --approved-by <you>` |
| List exemptions for a company | `python -m eval.retrieval.exemptions list --company "<Name>"` |
| Establish/refresh a company's retrieval baseline | `python -m eval.retrieval.harness_cli run --store-backend delta --run-type baseline --company-name "<Name>" --catalog uc13_ale` |
| Measure the effect of a specific change | `... --run-type enhancement --affected-intents <id> [<id> ...] --baseline-ref-run-id <id>` |
| Run a comparative ablation arm | `... --run-type ablation --ablation-config '{"arm": "<name>"}' --baseline-ref-run-id <id>` |
| Sanity-check a baseline before comparing against it | `python -m eval.retrieval.harness_cli validate-baseline --store-backend <b> --catalog uc13_ale --baseline-ref-run-id <id> --current-run-id <id>` |
| Link a checklist score to a pipeline run | `evaluate_promotion(...)` — Python only, see §4.5–§4.6 |
| Open/list a known-gap ledger row | `python -m eval.retrieval.eval_debt open|list --company "<Name>" ...` |
| Regenerate the one-page trust rollup | `python -m eval.retrieval.trust_statement generate --catalog uc13_ale --registry eval/program/registry.yaml` |

---

## 8. Glossary

| Term | Meaning |
|---|---|
| **Intent** | A single named retrieval question (e.g. "find revenue figures") registered in `intent_registry.yaml`. There are ~57 of them. |
| **Gold** | The hand-verified or bootstrapped set of correct chunk ids for one intent, for one company. |
| **Slug** | The lowercase-underscore form of a company display name (`Elder Care` → `elder_care`), used in file names and internal lookups. |
| **Run** (harness run) | One execution of the retrieval harness against a company's corpus, producing a `run_id` and a report. |
| **Baseline** | A harness run designated as the reference point other runs get compared against. |
| **Ablation arm** | One named configuration variant (e.g. `merge_rank_on`) run for systematic comparison. |
| **Gate / gate_pass** | Whether a run's gate metrics (recall/precision/basis-conflict) cleared their pass thresholds on the gate-eligible intent scope. |
| **Rung** | How much a content-correctness surface is trusted to self-check: `deterministic` (code), `judge` (calibrated LLM), or `human` (not yet calibrated — humans spot-check). |
| **Surface** | One of the three claim-level content-correctness domains: `fta_numeric`, `legal_register`, `exec_summary`. |
| **Verdict** | The outcome of checking one claim: `supported`, `contradicted`, or `unsupported`. |
| **Attestation** | The trust-statement's status word for a layer/row: `attested`, `partial`, `not_attested`, `known_gap`. |
| **Exemption** | A recorded, approved reason why an intent/surface can't be honestly measured for a company. |
| **Eval debt** | A tracked, named gap with an explicit condition for when it closes — the alternative to silently skipping something. |
| **Promotion** | The decision of whether a new checklist score for an agent+company counts as a kept improvement over the prior one — see §4.5–§4.6. |
| **Golden checklist** | Per-agent hand-written rubric (`eval/<AGENT>/golden_checklist_<slug>.md`) scored manually after a pipeline run; feeds the agent-fields layer (§2). |
| **Write-on-promote** | Manifest `e2e_checklist_score` is written only when promotion succeeds (`baseline_bootstrap`, `promoted`, or `promotion_waived`); blocked regressions stay NULL. |

---

Sources: `.dev/specs/uc13-eval-harness-all-agents-spec.md` (verified against on-disk checklists under `eval/{FTA,BMA,CQA,KPI,QOE,PROFILER,LCA}/`, `eval/retrieval/promotion_gate.py`, `eval/retrieval/README.md` § record_e2e_linkage / promotion gate invocation, agent `GOLDEN_CHECKLIST_COVERAGE` constants).
