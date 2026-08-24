# Golden Checklist — Clearsulting Quality of Earnings Agent (QOE)

| Field | Value |
|-------|-------|
| **catalog** | `uc13_ale` |
| **company** | `Clearsulting` |
| **pipeline run_id** | `6e1b4f5d95284b33bbd08942b3595dd6` (pipeline agent manifest; correlated to QOE analysis row `2026-08-19 19:25:37`) |
| **source table** | `uc13_ale.analysis.quality_of_earnings` |
| **rubric source** | `.dev/g1_score_all_agents.py::score_qoe()` (N=6 structural rows; pass / partial / gap-correct; only `qofe_report_present` can be `gap-correct`) |
| **authoring provenance** | queried `uc13_ale.analysis.quality_of_earnings` WHERE `company_name='Clearsulting'` ORDER BY `created_at` DESC LIMIT 1 -> `created_at` 2026-08-19 19:25:37 |
| **candidate_total M (Decision M2-C)** | **6** — live `addback_ledger_json` is a nonempty list (11 items). Corroborating FTA `uc13_ale.analysis.financial_trends.addback_schedule_json` for Clearsulting is also a nonempty list (11 items, `created_at` 2026-08-19 19:20:44). Precondition bar passes; `tier_classification_fidelity` stays in the denominator. |

**Verdict key:** `pass` — field meets rubric threshold; `partial` — below threshold, or QofE report present (`score_qoe()` never awards `pass` when `qofe_report_present` is true), or `tier4_addback_count` != ledger length; `gap-correct` — `qofe_report_present` is false. Clearsulting G1 floor is informational (`BASELINES["clearsulting"]` unset).

## Checklist (6 rows)

| item_id | display_name | verdict | notes |
|---------|--------------|---------|-------|
| revenue_quality_flags | Revenue quality flags extraction | pass | 6 `revenue_quality_flags_json` entries (>=3). Diligence `Project Infinity - Draft Financial Diligence Report - August 29, 2025_redacted.pdf` p.7 Quality of earnings states Reported EBITDA $8,247 / $6,532 / $7,899K (2023/2024/TTM25) and TTM25 addbacks $839 / $777 / $721 / $501 / $486K, matching the flag evidence and the ledger amounts. |
| ebitda_scenarios | EBITDA scenarios computation | pass | `ebitda_scenarios_json` populated: `reported_ebitda`=7899 (TTM25 $7,899K on diligence p.7). `tier1_plus_tier2_ebitda` and `tier1_only_ebitda` also 7899 with `tier1_addback_total`=0 and `tier2_addback_total`=0 (ledger is almost all Tier 4). |
| pre_qofe_scope | Pre-QofE scope items extraction | pass | 11 `pre_qofe_scope_items_json` entries (>=5), tied to ledger ids (venture losses $839K, market bonus $777K, restructuring $721K, ramp-up $501K, one-time $486K) from the same p.7 TTM25 adjustment list. |
| qofe_report_present | QofE report presence detection | partial | `qofe_report_present`=`true`. Diligence PDF Contents p.4 lists "02 Quality of earnings"; p.7 is a Quality of earnings schedule. Corpus confirms a QofE section is present. `score_qoe()` maps true to `partial` (`gap-correct` only when false). |
| tier_classification_fidelity | Addback tier classification fidelity | partial | `addback_ledger_json` has 11 items; `tier4_addback_count`=9 (9 Tier 4, 1 Tier 3 restructuring $721K, 1 Tier 1 hindsight). `score_qoe()` requires `str(tier4_addback_count) == str(len(ledger))` (9 vs 11) so `partial`. Precondition bar passed (nonempty ledger); item stays in M=6. |
| data_room_gaps | Data-room gaps correctly reported | pass | 1 `data_room_gaps` entry (CQA present but no per-customer GM). List type meets `score_qoe()`. |

**Summary:** 4 `pass`, 2 `partial`, 0 `gap-correct` — `score_qoe()` **4/6** with operator `candidate_total` **M=6**.
