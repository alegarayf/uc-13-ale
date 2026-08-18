# ESC-T12-1 — M5 handoff: bench `filename_closure` Tier-3 spec note (extends M1 escalation)

**Date:** 2026-08-18 · **From:** eval-multi-company-coverage-expansion T8 · **To:** operator → normative spec (idea-orch Update mode)  
**Status:** **OPEN** — program records landed at M1 T12/T13; spec absorption still pending  
**Tier:** **3 — spec return / spec note** (not the amendment itself — handoff only)  
**Prior escalation:** `.dev/plans/eval-consolidation-m1-metric-guardrail-hardening/escalations/ESC-T12-1-bench-spec-note.md`

---

## Continuity with M1 (no supersession)

This handoff **extends** the M1 ESC-T12-1 pack. It does **not** contradict Amendment A5 / T13 landed disposition:

- **`kpi.retrieve_bench_and_capacity`** remains `filename_closure` / ~2,925 positives / `aggregate_exclude: false` by operator choice **(a)** at G4.
- **Recall@10 ≤ ~0.34%** is the accepted interpretability bound for that intent until citation coverage exists or the intent is excluded.
- **Elder Care `aggregate_exclude` population** was restored to **5** (profiler + 4 KPI `no_citation_source`) after company-scoped `gold_exclusions.yaml` reshape (T13, 2026-08-14); F-04 closed by restored truth.
- **GAP-103-recall-at-10-bloated-gold** registry rationale remains authoritative: 7 of 8 item-12 bloated intents resolved; bench retained pending Tier-3 spec note.

The Tier-3 session should amend spec **§19** / **D4** per the M1 pack's requested edit block — naming the bench exception, stating the recall ceiling, and reconciling §6 S1 "mean recall interpretable" language with the one retained closure intent.

## M5 context

M5 (multi-company coverage expansion) does **not** re-open the bench gold row or re-run exclusion reshaping. ESC-T12-1 remains the **P1 cross-program item** in `eval/eval_program_playbook.md` §7.1 until spec absorbs or explicitly waives it.

**Evidence still current:**

| Artifact | Role |
|----------|------|
| `eval/retrieval/gold_labels/elder_care.yaml` | Shipped bench row |
| `signoffs/T12-bench-disposition.md` | Operator disposition (a) |
| `GAP-103-recall-at-10-bloated-gold` | Registry rationale |
| `.dev/pending/eval-consolidation-open-items.md` | Quick-open P1 ESC-T12-1 half-open |

---

## Exec-summary judge re-calibration gate (Flag 9)

M5 P3 references exec_summary judge re-calibration gated on operator language **"M2 §6.3 loop-back."**

### Citation status: **unverified**

Re-searched at T8 execution:

- `eval/eval_program_playbook.md` — no `6.3` or `loop-back` matches
- `.dev/plans/eval-consolidation-m2-s2-preplan-assessments/` — no `6.3` or `loop-back` matches
- `.dev/audits/eval-consolidation/M2/` — no `6.3` or `loop-back` matches

The UGA-1 standby prompt (`.dev/audits/eval-consolidation/M3/upstream-grounding-audit-prompt.md`) mentions a "post-M3 loop-back trigger (§6.3 of the M2 audit)" in a **constraint bullet**, but that section anchor was **not locatable** in the M2 audit folder as of this drafting. Treat the operator's **"M2 §6.3 loop-back"** citation as **unconfirmed** — not a hard gate until clarified.

### Interim gate (playbook §6.2)

Until the operator supplies the specific M2 section reference, treat exec_summary re-calibration as following **`eval/eval_program_playbook.md` §6.2**:

```
1. Product fixes (esp. analysis.* lookup for exec_summary)
2. Fix chunk truncation / broken chunk mapping (M2 WP-1, WP-2)
3. Re-run: python -m eval.content.calibration --surface ... --sample ...
4. If thresholds pass → update registry rung_assignments to judge
5. Build CHK-27 judge harness (reuse calibration judge_claim + s2_writer)
6. Block human spot_check for upgraded surfaces; run judge harness at scale
```

Re-calibration remains **post-M3 / operator-authorized** — it does not auto-resurrect CHK-27 (registry: descoped, empty rung-2 population).

**Current rung assignments (CHK-26a):** `exec_summary: human`, `fta_numeric: human`, `legal_register: deterministic`.

---

## Handoff checklist for Tier-3 session

- [ ] Read M1 ESC-T12-1 evidence pack (linked above) before editing §19/D4
- [ ] Preserve bench exception wording consistent with T13 / Amendment A5
- [ ] Do not re-litigate gold exclusion population (5 intents) — closed at T13
- [ ] If operator clarifies "M2 §6.3 loop-back", update this handoff's Flag 9 section and playbook cross-links in a follow-on doc pass (not in the spec amendment itself unless normative)

---

*This document is a draft escalation handoff per M5 non-goals — not the Tier-3 spec amendment.*
