# Golden Checklist — GKF KPI Agent (KPI)

| Field | Value |
|-------|-------|
| **catalog** | `uc13_ale` |
| **company** | `GKF` |
| **pipeline run_id** | `cd3abe7b4c3b4b9a91ffa977c5d2c1ce` (pipeline agent manifest; correlated to KPI analysis row `2026-08-19 19:15:18`) |
| **source table** | `uc13_ale.analysis.kpi` |
| **rubric source** | `.dev/g1_score_all_agents.py::score_kpi()` (3-field; pass / partial; no `gap-correct` branch) |
| **authoring provenance** | queried `uc13_ale.analysis.kpi` WHERE `company_name='GKF'` ORDER BY `created_at` DESC LIMIT 1 -> `created_at` 2026-08-19 19:15:18.553998 |

**Verdict key:** `pass` — field meets rubric threshold; `partial` — overlay is not `healthcare_services`, healthcare-block population is below 5, or missing-KPI list is shorter than 5 / inaccurate versus corpus. GKF G1 floor is informational (`BASELINES["gkf"]` unset).

## Checklist (3 rows)

| item_id | display_name | verdict | notes |
|---------|--------------|---------|-------|
| overlay_confirmed | Overlay confirmation extraction fidelity | partial | Extracted `overlay_confirmed`=`consumer` (not `healthcare_services`, so `score_kpi()` is `partial`). CIM p.5 / p.6: largest Goddard School franchisee; premium preschool / early childhood education in the DMV. Live `company_profile.industry_overlay`=`other` / `vertical_subsector`=`early_childhood_education`. Extraction matches a non-healthcare corpus; the frozen rubric still requires `healthcare_services` for `pass`. |
| overlay_block_fields | Selected overlay KPI block field presence | partial | `healthcare_kpis_json` is all-null except `site_level_visibility`=`true` (1 of 7 scored fields nonempty; bar is >=5). Correct for this corpus (no census / caregiver / clinician fields). Site-level P&Ls do exist (CIM p.2 entities; databook Location Analysis / school P&Ls), so the one populated healthcare-block field is grounded. `score_kpi()` does not read a consumer KPI block. |
| missing_kpis_json | Missing KPI list accuracy | partial | 10 `missing_kpis_json` rows (length bar >=5 would be `pass`). Escalated after sampling: `Enrollment capacity utilization by location` is listed as missing, but CIM p.14 `Ajax Student Utilization by School (2025B)` states Ellicott City 94.7% / 95%, Bethesda 91%, Tysons 85%, median 86.7%. Company-level `$2,422` monthly tuition (CIM p.53) and Franchise Fees on the p.68 income statement are also present. Length bar met; one named "missing" KPI is present in corpus, so not `pass`. |

**Summary:** 0 `pass`, 3 `partial` — `score_kpi()` candidate was 1/3 (`missing_kpis_json` length-pass); corpus review of that item lands **0/3**.
