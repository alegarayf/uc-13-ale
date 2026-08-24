# Golden Checklist — Clearsulting KPI Agent (KPI)

| Field | Value |
|-------|-------|
| **catalog** | `uc13_ale` |
| **company** | `Clearsulting` |
| **pipeline run_id** | `6e1b4f5d95284b33bbd08942b3595dd6` (pipeline agent manifest; correlated to KPI analysis row `2026-08-19 19:20:16`) |
| **source table** | `uc13_ale.analysis.kpi` |
| **rubric source** | `.dev/g1_score_all_agents.py::score_kpi()` (3-field; pass / partial; no `gap-correct` branch) |
| **authoring provenance** | queried `uc13_ale.analysis.kpi` WHERE `company_name='Clearsulting'` ORDER BY `created_at` DESC LIMIT 1 -> `created_at` 2026-08-19 19:20:16 |

**Verdict key:** `pass` — field meets rubric threshold; `partial` — overlay is not `healthcare_services`, healthcare-block population is below 5, or missing-KPI list is shorter than 5 / inaccurate versus corpus. Clearsulting G1 floor is informational (`BASELINES["clearsulting"]` unset).

## Checklist (3 rows)

| item_id | display_name | verdict | notes |
|---------|--------------|---------|-------|
| overlay_confirmed | Overlay confirmation extraction fidelity | partial | Extracted `overlay_confirmed`=`tech_services` (not `healthcare_services`, so `score_kpi()` is `partial`). CIM p.4 Executive Summary: "specialized consultancy" / "office of the CFO digital transformation"; live `company_profile.industry_overlay`=`tech_services`. Extraction matches corpus; the frozen rubric still requires `healthcare_services` for `pass`. |
| overlay_block_fields | Selected overlay KPI block field presence | partial | `healthcare_kpis_json` is all-null except `site_level_visibility`=`false` (1 of 7 scored fields nonempty; bar is >=5). Correct for this corpus (no census / caregiver / clinician fields). `tech_services_kpis_json` is populated (e.g. `average_bill_rate_dollars`=179; headcount 279/290/292; billable hours 322K/330K/352K) but `score_kpi()` does not read that block. |
| missing_kpis_json | Missing KPI list accuracy | partial | 10 `missing_kpis_json` rows (length bar >=5 would be `pass`). Escalated after sampling: `Overall utilization rate %` is listed as missing, but `Project Infinity - Utilization Analysis (Monthly Jan 2023 - May 2025).xlsx` sheet Summary by Level states 2023 utilization 0.6598 with billed hours 308726.5 / available 467880. Contractor-%-of-workforce remains a real gap: diligence p.29 states Subcontracting fees $2,168 / $2,612 / $2,797K (2023/2024/TTM25) and p.10 notes 1099 subcontractors, with no headcount %. Length bar met; one named "missing" KPI is present in corpus, so not `pass`. |

**Summary:** 0 `pass`, 3 `partial` — `score_kpi()` candidate was 1/3 (`missing_kpis_json` length-pass); corpus review of that item lands **0/3**.
