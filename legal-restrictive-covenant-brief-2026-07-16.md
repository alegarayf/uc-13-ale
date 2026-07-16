# Brief — LCA restrictive covenant regression (7/16 run)

**Run:** Cell 16 · `legal_contracts_agent.main()` · `generated_at` `2026-07-16T00:05:22Z`  
**Artifacts:** `legal_report_7_15(16).yaml` · `legal_contracts_report_7_15(16).yaml`  
**Scorecard:** `.dev/scorecards/scorecard_lca_7_16_post_phv4_vs_7_03.md`

---

## Classification

| Layer | Verdict |
|-------|---------|
| **Scoring / procedure** | Not the issue — rubric and source file are correct |
| **Registry / harness** | Not involved |
| **Code / extraction logic** | **Root cause** — register field vs citation path diverge |

---

## What happened

One Cell 16 run writes **two YAML shapes** from the same `result` dict (dual-write by design):

| File | Writer | Role |
|------|--------|------|
| `legal_report.yaml` | `_write_normative_legal_report` | **Canonical** for 11-item checklist (`eval/retrieval/README.md` § Legal re-score) |
| `legal_contracts_report.yaml` | `_write_stakeholder_report` | Legacy A1-compat + roll-ups (`coc_consent_list`, `restrictive_covenant_map`, `citations`) |

Both local copies share **identical** `generated_at` and **identical** `contract_register` (3 rows). The restrictive regression is **not** “scored the wrong file.”

### Symptom

| Signal | 7/16 value | 7/03 baseline |
|--------|------------|---------------|
| Checklist `restrictive` | **gap-correct** | **pass** |
| `contract_register` rows | 3 | 5 |
| All `restrictive_covenants.present` | `not_found` | 4/5 `true` |
| `restrictive_covenant_map` | `[]` | populated |
| Restrictive Yellow flags | 0 | 5 |
| `data_room_gaps` | `'restrictive: chunks retrieved but no extractable terms'` | absent |

### Smoking gun (same run, contradictory outputs)

`legal_contracts_report_7_15(16).yaml`:

```yaml
restrictive_covenant_map: []          # roll-up requires present=true

citations:
  - claim: restrictive_covenants (contract_id 4)
    document: Guided Living - Asset Purchase Agreement - 02.07.24 ...
    raw_text: Seller has not made any changes to its Business operations...
```

LLM pass **cited** restrictive text for APA, but **never set** `restrictive_covenants.present=true` on the merged contract row → checklist predicate fails.

---

## Logic gap (where to fix)

### 1. Disconnected citation vs register paths

```
_domain_extract_pass()
  ├─ normalized registers  → _merge_registers() → _pred_restrictive()  ← checklist gate
  └─ parsed["citations"]   → _ingest_pass_citations() → citations JSON  ← audit only
```

**File:** `databricks/agents/workstreams/legal_contracts_agent.py`  
- Citations ingested at L1168 — **not** fed back into register fields.  
- Checklist uses `_pred_restrictive` (L666–673): requires `restrictive_covenants.present` ≠ `not_found` on `contract_register` with `source_doc`.

### 2. Merge may preserve `not_found` over `true`

**File:** `legal_contracts_agent.py` L181–208 (`_merge_nested_dicts`, `_merge_register_records`)

When two contract rows dedupe on `(counterparty_name, contract_type)` (L211–217), nested merge only fills missing keys. If the “winning” row (longer `raw_quote`) has `present: not_found`, a colliding row with `present: true` is **not promoted** — `not_found` is treated as a set value, not absent.

Likely contributor: Manhattan + Long Island leases collapsed to one **Landlord** row (`source_doc` union) with CoC extracted but restrictive lost.

### 3. Roll-ups and flags follow register, not citations

| Function | Line | Depends on |
|----------|------|------------|
| `_build_restrictive_covenant_map` | L1371–1380 | `present=true` only |
| `_apply_legal_flags` restrictive branch | L1532–1546 | `present=true` only |
| `_assess_coverage_gaps` | L1392+ | `_pred_*` predicates |

Citations do not drive any of these.

### 4. CoC improved on same run (context)

CoC **pass** on 7/16 (was gap-correct on 7/03) — same merge path, opposite outcome. Suggests LLM non-determinism **plus** merge semantics, not a scoring drift.

---

## Impact

| Area | Effect |
|------|--------|
| **Checklist score** | **7/11** (floor met) but **pass-row regression** on `restrictive` vs 7/03 / G3 |
| **Scorecard verdict** | **CONDITIONAL PASS** (`.dev/scorecards/scorecard_lca_7_16_post_phv4_vs_7_03.md`) |
| **Flags** | −5 Yellow restrictive flags; stakeholders lose covenant visibility |
| **Diligence quality** | False `unable_to_assess` + gap bullet despite retrieval/extraction evidence in `citations` |
| **Runbook** | `my_runbook.md` L317 — “≥ 7/11, no regression on pass rows” — **partial fail** on regression dimension |
| **Delta table** | Same bad `contract_register_json` persisted to `uc13_ale.analysis.legal` |

**Not impacted:** harness baseline, intent registry, insurance retrieval fix (`legal.insurance` BACKGROUND filter — separate win documented in `harness-baseline-2026-07-15.md`).

---

## Score if fixed properly

**Realistic target: 8/11 pass** (up from 7/11)

| item_id | 7/16 actual | After fix |
|---------|-------------|-----------|
| coc | pass | pass (already working) |
| **restrictive** | gap-correct | **pass** |
| t4c | gap-correct | gap-correct (extraction depth — POC delta) |
| platform | gap-correct | gap-correct (corpus gap) |
| ip | gap-correct | gap-correct (retrieval miss) |
| vendor, employment, founder, litigation, privacy, insurance | pass | pass |

**8/11** = maintains all 7/03 pass rows **and** keeps the CoC improvement. Matches G3 tally on count but **strictly better** on deal materiality (CoC Red flag + restrictive populated).

**Not achievable on this corpus without new docs:** 9–11 pass (t4c, platform, ip are documented thin-corpus items in `eval/LCA/poc_delta_elder_care.md`).

Optional qualitative wins if merge also restores 5 contract rows: richer restrictive flags (7/03 had 5 Yellow), not extra checklist points.

---

## Fix directions (pick-up list)

1. **Post-merge reconciliation** — if `citations` contain `restrictive_covenants` for a `contract_id` / `source_doc`, backfill `present=true` + `scope_note` from citation quote (deterministic repair).
2. **Merge semantics** — in `_merge_nested_dicts`, tri-state upgrade: `not_found` + `true` → `true`; prefer non-`not_found` for `present` fields.
3. **Dedupe key review** — `(counterparty_name, contract_type)` may over-collapse distinct leases (Manhattan vs Long Island → one Landlord row). Consider `source_doc` in key or split by location.
4. **LLM prompt / schema** — require `present=true` when citation emitted (single-pass consistency).
5. **Test** — add falsifier in `tests/test_legal_contracts_agent.py`: citation for restrictive + `present=not_found` on same contract should not ship.

---

## Key references

| Doc / file | What it says |
|------------|--------------|
| `eval/retrieval/README.md` L547–554 | Score from `legal_report.yaml`; verdict rules in golden checklist |
| `eval/LCA/golden_checklist_elder_care.md` | G3 baseline: `restrictive`=pass, `coc`=gap-correct |
| `eval/LCA/poc_delta_elder_care.md` § coc / restrictive | CoC was extraction-depth gap in M3; restrictive was pass |
| `eval/LCA/t7_volume_verify_elder_care.md` | Dual-write paths on Volume |
| `databricks/agents/workstreams/legal_contracts_agent.py` L1722–1891 | Dual-write + roll-ups |
| `databricks/agents/workstreams/legal_contracts_agent.py` L646–673 | `_pred_restrictive` |
| `databricks/agents/workstreams/legal_contracts_agent.py` L194–208 | Merge logic |
| `.dev/scorecards/scorecard_lca_7_16_post_phv4_vs_7_03.md` | Full 7/16 vs 7/03 scoring |
| `harness-baseline-2026-07-15.md` L69–71 | Runbook gate: Legal ≥ 7/11 |

---

## Verify after fix

1. Re-run Cell 16 on Elder Care / `uc13_ale`.
2. Re-score 11 rows in `eval/LCA/golden_checklist_elder_care.md`.
3. Confirm: `restrictive`=pass, `restrictive_covenant_map` non-empty, restrictive Yellow flags restored, no `restrictive` gap bullet in `data_room_gaps`.
4. Target: **8/11 pass**, `section_confidence=high`, clean pass-row regression vs 7/03.
