# Content-correctness rung rationale (historical digest)

Appendix digest of why UC-13 content-correctness verification rungs are assigned as they are today. For the authoritative rung table, see `eval/eval_program_playbook.md` §1.2.

## Why the `judge` rung is empty

No surface has earned rung 2 (`judge`) clearance. M2 calibration (CHK-26a, Elder Care, Aug 2026) attempted judge-capability measurement on `exec_summary` (N=28) and `fta_numeric` (N=30) and **both failed** C5 agreement thresholds. Operator disposition **Option A (caveat-and-carry)** locked those outcomes as evidence-of-record only — they do **not** support a future upgrade argument without a fresh re-calibration on remediated instrumentation.

The 2026-08-12 disagreement audit found the failures were **not primarily judge incapability**:

- **Retrieval confound:** The judge only sees what `retrieve_evidence()` returns (BGE, top_k=5). For `fta_numeric`, **0/30** disagreements had the operator-expected `chunk_id` in a fresh top-5 re-run — a hard retrieval miss, not a locate failure. For `exec_summary`, **13/17** disagreements were retrieval misses; injected-evidence probes showed the judge often answers correctly when given the right chunk.
- **Sample power vs count:** C5 satisfied count pins (N ≥ 25) and numeric thresholds, but the samples lacked **discriminative power** — e.g. `exec_summary` was 26/28 `supported` (majority-class baseline 0.93 above the 0.80 verdict threshold), so a constant-`supported` degenerate responder could pass; `fta_numeric` span half had only two unique `chunk_id`s over N=30.
- **Instrument validity (pre-audit):** Ground-truth leak on the judge path (`apply_three_branch_locator` overwrote judge locators with operator metadata, making `span_agreement ≡ chunk_id agreement`); undeclared retrieval leg; malformed judge output silently coerced to `unsupported`; evidence truncation (see fixes below).

Re-calibration was explicitly **deferred** until instrument remediation (WP-1–3) landed and the M3 harness exists — not because the judge was judged permanently unfit, but because re-running on the same broken stack would reproduce the same confounded failure.

## Why `fta_numeric` and `exec_summary` stay on `human`

Both surfaces were assigned rung 3 (`human`) at M2 close and **M3 built against those assignments** — it cannot re-decide rungs from M2 evidence. Human spot-check is the operational verification path today (`eval/content/spot-check/`, rubrics in `eval/content/exec_summary_spot_check_rubric.md`).

**`fta_numeric`:** 0% pass on the calibration sample. Dominant failure mode was **null extraction** (13/30) from retrieval starvation; when the judge did extract a value, it matched **15/17** times (88%). Ten claims pointed at a **broken vision-extraction chunk** (`027ec667`) — label issue, not judge or retrieval fix alone. Even with correct chunks injected, **locator-kind mismatch** (`page` vs `section`) blocked `span_agreement` regardless of value correctness.

**`exec_summary`:** 17/28 disagreements; failure population is heterogeneous:
- Retrieval-fixable claims (~7) — worth re-measurement after retrieval work.
- **Structurally unverifiable at chunk grain** (claims 003, 004, 017, 019, 025, 026 — rollups, synthesis, workstream-level judgments with no literal single source chunk) — **permanent rung-3 lane** by operator disposition D3; item-26 human rubric covers them regardless of any future judge outcome.
- Label-too-generous (001), ambiguous ratio/completeness cases (012, 020) — need label review before re-calibration adds signal.

Conservative `human` assignment matched available evidence at session time and remains correct even though many failures traced to instrumentation, not corpus unsupport.

## Instrument fixes identified and applied

These shipped on the parallel **calibration instrument remediation** track (WP-1–3, approved D2/D4) so M3 harness runs and any future re-calibration inherit fixed measurement — not as M3 charter deliverables, but as product/eval code fixes:

| Fix | Problem | Remediation |
|-----|---------|-------------|
| **FTA revenue-family label (WP-1)** | Claims `fta.numeric.021`–`030` labelled against chunk `027ec667` — failed vision-extraction placeholder ("Five black, oval shapes…") with no numeric content; correct duplicate exists (`cd9773ea`) | Re-point `expected_span.chunk_id` to `cd9773ea` |
| **Evidence truncation (WP-2)** | `fetch_chunk_metadata` / `retrieve_evidence` truncated `chunk_text` to **1,200 characters** — values past truncation (e.g. `fta.numeric.007` "Pro Forma Adjusted EBITDA" in `b1feca18`) never reached the judge | Remove or raise cap for numeric-transcription evidence in `eval/content/calibration.py` |
| **Locator-kind handling (WP-3)** | Operator labels use `kind: section`; judge emits `kind: page` for the same chunk — `spans_agree()` required exact kind match, capping span_agreement below threshold even when `chunk_id` matched | Page/section interchangeability when `chunk_id` matches (predicate and/or prompt patch in `eval/content/agreement.py`) |
| **Ground-truth leak on judge path (T8)** | `apply_three_branch_locator` replaced judge locators with operator-side metadata on the comparison path | Judge locators compared as emitted; operator normalisation stays in sample validator only |
| **Parse fail-closed (T8)** | Malformed judge JSON silently coerced to `unsupported` | Fail-closed parsing on calibration driver |
| **Retrieval declared (A-C8 / T9)** | Retrieval leg undeclared; per-claim `retrieved_chunk_ids` not persisted — could not separate retrieval vs judge failure | Surface declared; retrieval metadata persisted for diagnostics |
| **M3 producer reproducibility (R16+)** | Gitignored draft artifact silently overrode FTA citations; locators derived from manifest fields instead of resolved chunks | Exclusive `ChunkIndex.lookup` resolution; shared `derive_locator` from cited chunk; re-ingest from committed inputs |

**Optional / advisory:** WP-4 — retrieval query quality for templated FTA claims (near-identical claim text differing only by number flattens embedding signal); consider discriminating queries or higher `top_k` at re-measurement time.

**Explicit non-goals from disposition:** No `exec_summary` sample re-author for structural claims (D3); no blind re-calibration before the loop-back trigger; M2 CHK-26a metrics never reused as upgrade arguments under Option A.

## Before `judge` at scale is viable

All of the following would need to be true before any surface could earn rung 2 or before judge-at-scale (CHK-27) is in scope:

1. **Re-calibration on remediated instrumentation** — WP-1–3 landed; operator authorizes new agreement figures; results feed repeatable M3+ measurement, not one-off sessions.
2. **C5 power pins satisfied** — sample balance, minimum unique chunk diversity, and degenerate-responder floors (ESC-T2-3 items 1–2) addressed at the charter session that owns an upgrade — count pins alone are insufficient.
3. **Retrieval quality separated from judge capability** — templated numeric query ranking investigated; structural/exec-synthesis claims accepted as permanent human-lane or given an alternate verifier (e.g. `analysis.*` table trace — Tier 3 spec change).
4. **Production judge harness** — M3 held rung-2 surfaces as charter non-goal; item 27 exists for samples but judge-at-production-scale remains descoped.
5. **Fresh metrics only** — any upgrade argument must use amended samples/instrument post-remediation; M2 figures are evidence-of-record for the `human` assignments they justified, not for promotion.

---

## Sources

- `.dev/archive/eval-consolidation-m2-s2-preplan-assessments/audits/calibration-disagreement-audit-2026-08-12.md`
- `.dev/retrospectives/learning/2026-08-13-eval-consolidation-m2-s2-preplan-assessments.md`
- `.dev/retrospectives/learning/2026-08-15-eval-consolidation-m3-s2-build.md`
