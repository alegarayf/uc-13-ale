# Golden Checklist — Clearsulting Customer Quality Agent (CQA)

| Field | Value |
|-------|-------|
| **catalog** | `uc13_ale` |
| **company** | `Clearsulting` |
| **pipeline run_id** | `6e1b4f5d95284b33bbd08942b3595dd6` (pipeline agent manifest; correlated to CQA analysis row `2026-08-19 19:20:13`) |
| **source table** | `uc13_ale.analysis.customer_quality` |
| **rubric source** | `.dev/g1_score_all_agents.py::score_cqa()` (6-field; pass / partial / gap-correct) |
| **authoring provenance** | queried `uc13_ale.analysis.customer_quality` WHERE `company_name='Clearsulting'` ORDER BY `created_at` DESC LIMIT 1 -> `created_at` 2026-08-19 19:20:13 |

**Verdict key:** `pass` — field meets rubric threshold; `partial` — field partially populated or thinly grounded; `gap-correct` — absence correctly surfaced (empty concentration list, all-null retention with discrepancies, or valueless payor dict). Clearsulting G1 floor is informational (`BASELINES["clearsulting"]` unset).

## Checklist (6 rows)

| item_id | display_name | verdict | notes |
|---------|--------------|---------|-------|
| concentration | Customer concentration extraction | pass | `top_customers_json` has 10 anonymized clients. Sheet `Revenue by Client Detail` / Summary in `Project Infinity - Revenue by Client (2016-YTD May 2025).xlsx` has Client=1 (Energy, Utilities and Mining) `2024=10917798.83` (extracted $10,917,799), `2023=11589126.89`, `2022=1101830`, `2025=4423181.25`. |
| retention | Retention metrics extraction | pass | `retention_json.nrr_pct`=`73%` (2024) so `score_cqa()` is not in the all-null `gap-correct` branch. CIM `Project Infinity  - Confidential Information Memorandum.pdf` p.30 Enabling Industry Leading Clients Metrics: "73% Net Revenue Retention (2024)" and "72% Customer Retention (2024)". Agent also stored `logo_churn_rate_annual_pct`=`28%` (100-72); rubric reads `logo_churn_pct`, which is absent. |
| customer_tenure | Customer tenure extraction | partial | `customer_tenure_json.tenure_distribution_note` is null. No tenure-distribution table in the CIM metrics page used for NRR; `score_cqa()` requires a nonempty note for `pass`. |
| payor_mix | Payor mix extraction | partial | `payor_mix_json` is a 6-row healthcare list (Medicare / Medicaid / VA / Commercial / Managed Care / Other) with every `pct_of_revenue` null and `source_doc` "Not found in retrieved context". List-without-values is `partial` (not `gap-correct`). Correct for a consultancy corpus: no payor mix exists to extract. |
| discrepancies_json | Discrepancies correctly reported | pass | 5 `discrepancies_json` entries (NRR vs missing GRR; NRR 73% below 100%; healthcare overlay vs consulting documents; concentration % not stated; 2025 YTD May only). Meets `len >= 3`. |
| data_room_gaps | Data-room gaps correctly reported | pass | 5 `data_room_gaps` strings (referral/concentration %, T4C, CoC, payor mix, Client 1 contract). List type meets `score_cqa()`. |

**Summary:** 4 `pass`, 2 `partial`, 0 `gap-correct` — `score_cqa()` **4/6**.
