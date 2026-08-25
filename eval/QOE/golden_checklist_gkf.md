# Golden Checklist — GKF Quality of Earnings Agent (QOE)

| Field | Value |
|-------|-------|
| **catalog** | `uc13_ale` |
| **company** | `GKF` |
| **pipeline run_id** | `cd3abe7b4c3b4b9a91ffa977c5d2c1ce` (pipeline agent manifest; correlated to QOE analysis row `2026-08-19 19:24:36`) |
| **source table** | `uc13_ale.analysis.quality_of_earnings` |
| **rubric source** | `.dev/g1_score_all_agents.py::score_qoe()` (N=6 structural rows; pass / partial / gap-correct; only `qofe_report_present` can be `gap-correct`) |
| **authoring provenance** | queried `uc13_ale.analysis.quality_of_earnings` WHERE `company_name='GKF'` ORDER BY `created_at` DESC LIMIT 1 -> `created_at` 2026-08-19 19:24:36.291109 |
| **candidate_total M (Decision M2-C)** | **6** — live `addback_ledger_json` is a nonempty list (10 items). Corroborating FTA `uc13_ale.analysis.financial_trends.addback_schedule_json` for GKF is also a nonempty list (10 items, `created_at` 2026-08-19 19:20:54.14984). Precondition bar passes; `tier_classification_fidelity` stays in the denominator. |

**Verdict key:** `pass` — field meets rubric threshold; `partial` — below threshold, or QofE report present (`score_qoe()` never awards `pass` when `qofe_report_present` is true), or `tier4_addback_count` != ledger length; `gap-correct` — `qofe_report_present` is false. GKF G1 floor is informational (`BASELINES["gkf"]` unset).

## Checklist (6 rows)

| item_id | display_name | verdict | notes |
|---------|--------------|---------|-------|
| revenue_quality_flags | Revenue quality flags extraction | pass | 5 `revenue_quality_flags_json` entries (>=3). Databook QoE tab has `EBITDA: Diligence Adjusted` TTM25 `6662.001`; Executive Summary states occupants fell from 903 (FY23) to 872 (TTM25); Adjustment Narratives / Adjustments sheet include Reversal of Adjusting Journal Entries and the Bethesda expansion 97% occupancy / 36 additional occupants assumption. |
| ebitda_scenarios | EBITDA scenarios computation | pass | `ebitda_scenarios_json` populated: `reported_ebitda`=`6662001` (databook QoE -- Data `EBITDA: Diligence Adjusted` TTM25 `6662.001` in USD thousands). `tier1_plus_tier2_ebitda` and `tier1_only_ebitda` also populated. |
| pre_qofe_scope | Pre-QofE scope items extraction | pass | 11 `pre_qofe_scope_items_json` entries (>=5), tied to ledger ids (management fees $5,700 2025B, go-forward owner comp, rent normalization, R.AJE / $190k facility-cost reimbursement, owner personal / capitalizable items). CIM p.68 Management Fees `$5,700` (2025B) matches ledger item 3. |
| qofe_report_present | QofE report presence detection | partial | `qofe_report_present`=`true`. Databook has a `QoE` tab (8 GKF chunks, section `QoE -- Data`, header `Quality of Earnings Analysis`) and an `Adjustment Narratives` tab that links Diligence EBITDA Adjustments to QoE. Corpus confirms a QofE schedule is present. `score_qoe()` maps true to `partial` (`gap-correct` only when false). |
| tier_classification_fidelity | Addback tier classification fidelity | partial | `addback_ledger_json` has 10 items; `tier4_addback_count`=`0` (ledger labels are Tier 1 / 2 / 3 only; zero Tier 4). `score_qoe()` requires `str(tier4_addback_count) == str(len(ledger))` (0 vs 10) so `partial`. Precondition bar passed (nonempty ledger); item stays in M=6. |
| data_room_gaps | Data-room gaps correctly reported | pass | 1 `data_room_gaps` entry (CQA present but no per-customer GM). List type meets `score_qoe()`. |

**Summary:** 4 `pass`, 2 `partial`, 0 `gap-correct` — `score_qoe()` **4/6** with operator `candidate_total` **M=6**.
