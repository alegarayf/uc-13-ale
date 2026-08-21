# ESC-M4-1 — Carryability HALT and split proposal for M4 / W4

> **M4 closeout (T13, 2026-08-21):** Operator decision D-M4-A declined this split and waived the §Budget ceiling. This file is force-added as a tracked path so the carryability record is no longer informational-only. Authorized executable count grew 13 → 20 via R1–R6. The `Status: open` line below is the historical planning HALT, not the live plan state (`run_status: amended`, D-M4-A present).

**Raised by:** orchestrator-planning v0.9, plan construction for M4 / W4 — Product Fixes
**Date:** 2026-08-20
**Charter:** `.dev/specs/eval-signal-foldback/eval_signal_foldback_milestone_charter.md` v0.1.0 §3 M4, §6 Stub M4
**Context map:** `.dev/plans/eval-signal-foldback-m4-product-fixes/context-map.md` (CONDITIONAL, commit `bab8f7a`)
**Escalation tier:** 2 (charter amendment) — the §7 amendment path is unavailable because the findings cross milestone boundaries and extend surfaces the charter assigns to other milestones.
**Status:** open — awaiting operator/charter decision. No packets emitted. No plan finalized.

---

## 1. Why planning halted

Three independent conditions fire. Each alone is a Tier-2 escalation; together they make M4 as chartered unbuildable in one orchestrator plan.

### 1.1 Carryability ceiling exceeded (orchestrator §Budget, validation item 19)

The operator's scope decision on the two ingestion rows is a **live CIM re-parse plus gold re-bootstrap plus epoch re-pin** (rather than an eval-side override or a deferral). With that decision, the honest decomposition is:

| # | Subtask (honest, uncompressed) | Rows served |
|---|---|---|
| 1 | `calibration.py` 1200-char truncation removal at both call sites + hermetic guard | 2 |
| 2 | FTA `revenue_by_segment` row dedupe + `source_location` schema addition | 2 |
| 3 | Legal contracts pass: t4c / coc extraction depth | 1 |
| 4 | Legal `ip_privacy` / `contracts_vendors_platform` retrieval reach + exemption evidence | 2 |
| 5 | Legal verifier locator chunk resolution | 1 |
| 6 | CIM re-parse (`force=<CIM path>`) via serverless submit | 2 |
| 7 | Gold re-bootstrap for affected Elder Care intents + epoch re-pin | — |
| 8 | Chunk-id pin refresh across the five pinning artifacts + `spot_check.py` constants | — |
| 9 | Legal agent re-run + `verify_legal_register` S2 re-run (evidence of record) | 4 |
| 10 | FTA agent re-run + narrowed spot-check re-run (evidence of record) | 4 |
| 11 | `product_backlog.yaml` closure writes + `closed_evidence_refs` | 10 |
| 12 | Closeout: architecture folder, changelog, §8 handoff, declared-scope sweep | — |

**12 subtasks against a declared ceiling of 10.** Per the orchestrator skill this is a HALT with a split proposal, not a compression exercise — compressing here would silently drop the epoch-refresh bookkeeping, which is precisely the work whose omission causes the drift.

### 1.2 Charter-boundary drift on surfaces M4 was not granted

The charter's M4 block grants exactly one contract surface: `eval/program/product_backlog.yaml`. The fixes necessarily touch:

| Surface | Charter's own assignment | Conflict |
|---|---|---|
| `eval/content/legal_register_verifier.py` | §4 documented **non-hub**, "M8/W5 only" | M4 must edit it for `PB-legal_register-locator-chunk-resolution`. Two extenders ⇒ the non-hub classification is wrong; it is a hub with ordered extenders M4 → M8. |
| `eval/retrieval/gold_labels/elder_care.yaml`, `eval/retrieval/fixtures/elder_care_slice.json` | M1/W3 surfaces (retrieval baselines, gold) | A CIM re-parse forces a re-bootstrap and re-pin here. |
| `eval/content/calibration_samples/calibration_sample_fta_numeric.yaml` | Not chartered to any milestone; spec O4 explicitly **defers** `fta_numeric` sample remediation | Re-parse invalidates 2 `expected_span.chunk_id` pins in it. |
| `eval/content/calibration.py`, `databricks/agents/**`, `databricks/jobs/scripts/ingestion_parser.py` | Not listed under any milestone | Unchartered but uncontested; recorded for completeness rather than as a conflict. |

### 1.3 Cross-row interference with a row M4 may not touch

`PB-fta_numeric-post-m4-chunk-citation-drift` (`kind: measurement_caveat`, open, `fix_lane: eval`) names both `027ec667…` and `b1feca18…` and states that spot-check claims "may need re-verification on `uc13_ale:55812+` corpus **before attributing to extraction bugs**". D8 declares the caveat rows disjoint from W4's scope by `kind`, so M4 may not touch it — yet a CIM re-parse directly changes the state that row measures.

---

## 2. Quantified blast radius of the CIM re-parse

Measured against the live warehouse (`uc13_ale.ingestion.chunks`, company `Elder Care`, 450 documents) and the committed pinning artifacts at `bab8f7a`:

| Fact | Value |
|---|---|
| `chunk_id` generation | `str(uuid.uuid4())` at `ingestion_parser.py:485,525,565,797` — **not** content-derived |
| Re-parse stability | None. A per-document `force=` re-parse deletes by `doc_id` and re-appends with all-new UUIDs |
| Targeted patch utility | None exists in the repo |
| Distinct chunk UUIDs pinned across committed artifacts | **3,669** (all currently resolve; zero stale) |
| Of those, pins that live in `2024 Elder Care - CIM_vF.pdf` | **77** |
| CIM chunk count today | 521 |

Pinning artifacts and their exposure:

| Artifact | Distinct UUIDs | Exposure to a CIM-only re-parse |
|---|---|---|
| `eval/retrieval/gold_labels/elder_care.yaml` | 3,658 | 77 pins re-IDed; `ingestion_snapshot: uc13_ale:55812:2026-08-19` string invalidated corpus-wide |
| `signoffs/T4-staged-elder_care-full57.yaml` | 3,658 | same set (staged snapshot mirror) |
| `eval/retrieval/fixtures/elder_care_slice.json` | 31 | hard-coded UUIDs + score map |
| `eval/content/calibration_samples/calibration_sample_exec_summary.yaml` | 13 | M3 just re-balanced this sample; any overlap re-opens landed M3 evidence |
| `eval/content/calibration_samples/calibration_sample_fta_numeric.yaml` | 2 | `expected_span.chunk_id` for the affected claims |
| `eval/content/spot_check.py` | 2 constants | `BROKEN_CHUNK_ID` / `SIBLING_CHUNK_ID` become dangling |

**Interpretation.** The blast radius is bounded and tractable — 77 pins, not 3,669 — but it moves the corpus epoch that M1/W3's landed promote/reject evidence is pinned to, and it touches gold and calibration artifacts assigned to other milestones. Bounded is not the same as in-scope.

---

## 3. Correction to the corpus-gap premise (evidence-backed)

The two `corpus_gap` rows assert the LEGAL corpus lacks platform/reseller/channel and IP documents. **The warehouse contradicts this.** Elder Care's 450-document corpus already holds, among others:

- Platform / vendor dependency: `Elder Care Homecare, Inc_ClearCare SaaS agreement as of 8-4-17.pdf`, `Deel Contract_SAMPLE.pdf`, `dropbox_hipaa_agreement.pdf`, `Jotform BAA agreement.pdf`, `Hubspot invoice-613231405.pdf`, `Unicity_IT List.xlsx`, `Veta Virtual_Eldercare_Homecare_Agreement_May_30_2023_Signed.pdf`
- Channel / referral: `Atria Rye Brook Elder Care SA.pdf`, `Staffing Agreement ECHC Sunrise of Wilton Executed.pdf`, `Staffing Contract_The Club_0923.pdf`, `Elder Care HC + Brightview Port Jefferson Staffing Agreement.pdf`, `Jewish Family Services Agreement.pdf`, `Senior Care Authority.pdf`, `Marketing Contract_Grow Home Care_0524.pdf`
- IP-adjacent: `Non-Compete-Non Solicitation Agreement Template.docx`, `Employee ND Agreement.pdf`, `7 Employee Non-Disclosure.docx`, `Kate Marks Restricted Stock.pdf`, `Unicity_Asset Purchase Agreement_0824.pdf`

Several are already pinned in the gold labels (`Deel` 15 pins, `dropbox_hipaa` 8, `Non-Compete` 2, `Jotform` 1), so they are indexed and retrievable.

The `ip_privacy` pass's `file_name_filter` is `["IP", "Privacy", …]` (`legal_contracts_agent.py:611-665`), which matches **none** of the documents above. This is a **retrieval-reach defect mislabeled as `corpus_gap`**, not a missing-documents problem. Ingesting new platform/IP documents is therefore unnecessary and would not address the cause.

---

## 4. Proposed resolution (Tier-2 charter amendment)

Split M4 into two milestones and re-place the second one late in the program.

### M4a / W4a — Product code fixes and closures (8 rows)

| Field | Content |
|---|---|
| Rows closed | `PB-exec_summary-chunk-truncation`, `PB-fta_numeric-chunk-truncation`, `PB-fta_numeric-segment-json-dedupe`, `PB-fta_numeric-segment-source-location`, `PB-legal_register-extraction-depth-contracts`, `PB-legal_register-corpus-gap-platform`, `PB-legal_register-retrieval-ip`, `PB-legal_register-locator-chunk-resolution` |
| Contract surfaces extended | `eval/program/product_backlog.yaml`; `eval/content/calibration.py`; `eval/content/legal_register_verifier.py` (**hub**, ordered M4a → M8); `databricks/agents/workstreams/legal_contracts_agent.py`; `databricks/agents/subagents/workstream/financial/revenue_sub_agent.py`; `databricks/agents/workstreams/financial_trends_agent.py` |
| Position | Unchanged — fourth, after M3 |
| Sizing | `l`, fits the 4–10 budget at roughly 8–9 subtasks |
| Non-goals | The two ingestion rows; any chunk-id-moving operation; `PB-exec_summary-retrieval-scope-gap` |

### M4b / W4b — Elder Care corpus epoch refresh (2 rows)

| Field | Content |
|---|---|
| Rows closed | `PB-fta_numeric-broken-chunk-repoint`, `PB-fta_numeric-page46-vision-reextract` |
| Contract surfaces extended | `eval/program/product_backlog.yaml`; `databricks/jobs/scripts/ingestion_parser.py`; `eval/retrieval/gold_labels/elder_care.yaml`; `eval/retrieval/fixtures/elder_care_slice.json`; `eval/content/calibration_samples/calibration_sample_fta_numeric.yaml`; `eval/content/spot_check.py`; `signoffs/T4-staged-elder_care-full57.yaml` |
| Position | **After M8**, as a wave-closing refresh |
| Rationale for late placement | The epoch move is the milestone's whole point. Running it late means no downstream milestone's retrieval or calibration evidence is invalidated mid-program: M5/M6/M7 are Clearsulting/GKF/SPG and never read Elder Care's epoch, and M8's Elder Care work is Legal documents, not the CIM. Running it fourth would silently stale M1's landed baseline and every subsequent Elder Care retrieval figure. |
| Sizing | `m`–`l`; 5–7 subtasks |
| Additional obligation | Re-triage `PB-fta_numeric-post-m4-chunk-citation-drift` (§1.3), which this milestone is the natural owner of |

### Charter edits this implies

1. §3: replace the M4 block with M4a and M4b blocks; execution order becomes M1 → M2 → M3 → M4a → M5 → M6 → M7 → M8 → M4b.
2. §4: promote `eval/content/legal_register_verifier.py` from documented non-hub to **hub**, extenders M4a → M8. Add `eval/program/product_backlog.yaml` extenders M2 → M4a → M4b.
3. §5: G1's "Blocks" column keeps M4a; add a note that M4b is gated on G5 rather than G1.
4. §6: replace Stub M4 with Stub M4a and Stub M4b.
5. M4a's exit gate asserts **eight** rows closed, not ten; M4b's asserts the remaining two. The wave-level "ten rows closed" claim survives across the pair, so spec §2.1 and §4 W4 need no amendment — only the charter's slicing does.

---

## 5. Alternatives considered and rejected

| Alternative | Why rejected |
|---|---|
| Keep one M4 plan at 12 subtasks | Violates the declared budget; the skill forbids compressing to fit, and the items that would be compressed away are the epoch bookkeeping whose omission is the actual failure mode. |
| Eval-side-only fix for the two ingestion rows | Operator declined. It also closes the rows' letter while leaving the broken chunk served to every other consumer, which spec §7 forbids as a "code landed alone" closure. |
| Targeted DML `UPDATE` on `ingestion.chunks` preserving chunk_ids | No precedent, no utility, no provenance column to record it; contradicts the AGENTS.md read-only default and leaves the warehouse in a state no re-parse reproduces. |
| Split M4 but run M4b fourth (in place) | Moves the epoch before M5–M8, staling M1's landed evidence and every Elder Care retrieval figure produced afterwards. Late placement costs nothing and avoids this entirely. |
| Defer the locator row to M8 instead of hub-promoting the file | Viable, and cheaper on the charter; but M8 is already `l`-borderline by the charter's own sizing note, the locator defect is independent of D11, and it would leave M4a closing seven rows. Presented to the operator as an option rather than decided here. |

---

## 6. What unblocks planning

1. A charter decision on §4's split (accept, amend, or reject with an alternative).
2. A decision on the locator row's home: hub-promote `legal_register_verifier.py` for M4a, or defer the row to M8.
3. Ratification of §3's correction — the two `corpus_gap` rows are closed via widened retrieval reach plus documented exemption, not via new document ingestion.

On decisions 1–3, planning resumes immediately and the M4a plan plus packets can be emitted in one pass.
