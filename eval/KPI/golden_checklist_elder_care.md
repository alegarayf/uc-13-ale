# Golden Checklist — Elder Care KPI Agent (G3)

| Field | Value |
|-------|-------|
| **catalog** | `uc13_ale` |
| **company** | `Elder Care` |
| **git SHA** | `94da269968c1c1f014118f93c1c5b9ad7243bb1e` |
| **E2E timestamp** | `2026-07-08T17:05:37Z` |
| **source reference** | `uc13_ale.analysis.kpi` |
| **spec ref** | `uc13-eval-harness-all-agents-spec.md §6.1` |

**Verdict key:** `pass` — extraction faithful to corpus with citations; `partial` — overlay-relevant fields partially extracted or thinly grounded; `gap-correct` — correctly surfaced missing/unable-to-extract when corpus thin; `n/a` — not applicable to this corpus.

## Checklist (3 rows)

| item_id | display_name | verdict | notes |
|---------|--------------|---------|-------|
| overlay_confirmed | Overlay confirmation extraction fidelity | pass | LLM extracted `overlay_confirmed`=`healthcare_services`, matching `uc13_ale.classification.company_profile.industry_overlay`=`healthcare_services`. Reasoning trace step 6 loaded company profile; step 7 extraction echoed same overlay. Non-selected overlay blocks (`tech_services_kpis`, `saas_kpis`, etc.) correctly left all-null. |
| overlay_block_fields | Selected overlay KPI block field presence | pass | Healthcare block populated from KPI dashboard, subsidiary DRL templates, and CIM: `census_or_patient_panel` (351.8 QTD avg clients by market), `caregiver_headcount` (2,123 all-markets + subsidiary splits), `clinician_headcount` (nurse hire metrics), `utilization_or_productivity_note` (caregiver/nurse not-utilized %, billed hours per client), `compliance_incidents` (1 DPS complaints entry with source), `credentialing_status_note` (Unicity/Guided Living W-2 and CNA/HHA rules), `site_level_visibility`=`partial` with market-level dashboard note. Fields absent from corpus (`turnover_rate_pct`, `referral_source_breakdown`, `ar_aging_by_payor_note`) correctly null — not conflated with extraction failure. |
| missing_kpis_json | Missing KPI list accuracy | pass | 8 `missing_kpis` entries, all `overlay`=`healthcare_services`: turnover rate, payor mix detail, AR aging by payor, referral source breakdown, average length of service, billing/coding audit history, licensing/regulatory status by state, revenue per caregiver FTE. Each carries `why_expected` and a specific `management_question`. `data_room_gaps` mirrors the same gaps (turnover + 8 missing-KPI prompts). Turnover correctly listed as missing despite utilization-proxy data in the healthcare block. |

**Summary:** 3 `pass`, 0 `partial`, 0 `gap-correct`, 0 `n/a`
