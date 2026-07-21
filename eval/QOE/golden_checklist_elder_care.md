# Golden Checklist — Elder Care Quality of Earnings Agent (M2)

| Field | Value |
|-------|-------|
| **catalog** | `uc13_ale` |
| **company** | `Elder Care` |
| **git SHA** | `cdac3328454a350134427fdbdbee346afe5a89c1` |
| **E2E timestamp** | `2026-07-08T17:10:16Z` |
| **source table** | `uc13_ale.analysis.quality_of_earnings` |
| **spec ref** | `uc13-eval-harness-all-agents-spec.md §6.1` |

**Verdict key:** `pass` — field populated with citation-backed extraction; `partial` — field partially populated or thinly grounded; `gap-correct` — absence or limitation correctly surfaced in `data_room_gaps` / structured nulls; `n/a` — not applicable to this corpus.

**Precondition-gated item (not denominator-adjusted in this file):** `tier_classification_fidelity` is scored only when FTA `addback_schedule_json` is present for the in-run company (QoE `_load_addback_passthrough` non-empty). Elder Care FTA row (`created_at` 2026-07-16) carries 17 addback-schedule entries, so the gate passes for this corpus; denominator exclusion on failure is a scoring-time concern (T3/T4), not this file's row count.

## Checklist (6 rows)

| item_id | display_name | verdict | notes |
|---------|--------------|---------|-------|
| revenue_quality_flags | Revenue quality flags extraction | pass | 5 `revenue_quality_flags_json` entries — 3 Red (`non_recurring_in_run_rate` ×2, `addbacks_growing_faster`) and 2 Yellow (`revenue_recognition_change`, `episodic_revenue`) — with `source_doc` citations to `2024 Elder Care - CIM_vF.pdf` (EBITDA Adjustment Detail, Revenue Model) and `GUIDED LIVING SENIOR HOME CARE LLC_2022_1120S_Tax Returns.pdf` (Schedule M-1). |
| ebitda_scenarios | EBITDA scenarios computation | pass | `ebitda_scenarios_json` populated — reported EBITDA $2,773K; Tier-1+2 and Tier-1-only both $2,773K with `tier1_addback_total`=0 and `tier2_addback_total`=0, consistent with all 17 ledger items classified Tier 4; scenario note documents §8.3 three-scenario rule. |
| pre_qofe_scope | Pre-QofE scope items extraction | pass | 12 `pre_qofe_scope_items_json` entries — actionable diligence questions tied to `related_addback_ids` (e.g. [G] run-rate executive comp $2,490K, [K] Unicity pre-acquisition $1,077K, [N]/[O] pro-forma maturity/synergy addbacks); priorities high/medium assigned. |
| qofe_report_present | QofE report presence detection | gap-correct | `qofe_report_present`=false; aligns with `data_room_gaps` entry "No QofE report found in VDR — flag as data room gap" and absence of a sell-side QofE workbook in retrieved corpus. |
| tier_classification_fidelity | Addback tier classification fidelity | pass | 17/17 `addback_ledger_json` items assigned Tier 4 with `tier_rationale` citing the absolute rule (no `supporting_doc_referenced` beyond "Not referenced"); `tier4_addback_count`=17 matches ledger length. FTA `addback_schedule_json` present (17 rows) — precondition gate passes; assignment fidelity is LLM-executed (downstream Red-flag math owned by `tests/test_qoe_tier_classification.py`). |
| data_room_gaps | Data-room gaps correctly reported | pass | 1 `data_room_gaps` entry documents missing QofE report, consistent with `qofe_report_present`=false; revenue-quality and scope absences captured in structured flags/scope items rather than duplicate gap strings. |

**Summary:** 5 `pass`, 0 `partial`, 1 `gap-correct`, 0 `n/a`
