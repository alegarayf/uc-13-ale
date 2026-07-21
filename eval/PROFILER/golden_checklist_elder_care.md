# Golden Checklist — Elder Care Company Profiler (M1)

| Field | Value |
|-------|-------|
| **catalog** | `uc13_ale` |
| **company** | `Elder Care` |
| **git SHA** | `94da269968c1c1f014118f93c1c5b9ad7243bb1e` |
| **E2E timestamp** | `2026-06-16T18:26:09Z` |
| **source table** | `uc13.classification.company_profile` |
| **spec ref** | `uc13-eval-harness-all-agents-spec.md §6.1` |

**Verdict key:** `pass` — field present and meaningfully populated; `partial` — field present but null, empty, or thin extraction; `gap-correct` — not scored for Profiler (no citations/flags/reasoning_trace); `n/a` — not applicable to this corpus.

## Checklist (7 rows)

| item_id | display_name | verdict | notes |
|---------|--------------|---------|-------|
| industry_overlay | Industry overlay extraction | pass | `industry_overlay`=`healthcare_services`; `overlay_confidence`=`high`. |
| revenue_model | Revenue model extraction | pass | `revenue_model`=`repeat_services`; `revenue_model_note` cites payor mix (Private Pay 64%, Medicaid Waiver 11%, LTCI 11%, VA 7%, Other 7%). |
| business_description | Business description extraction | pass | `business_description` populated — coordinated home care, practice model, care management/caregiver/nursing services. |
| deal_type | Deal type extraction | pass | `deal_type`=`buyout`. |
| banked | Banked status extraction | pass | `banked`=`true`; `banked_note`=null (CIM detected). |
| vertical_subsector | Vertical subsector extraction | pass | `vertical_subsector`=`home_care`. |
| data_room_gaps | Data-room gaps field presence | pass | `data_room_gaps` array present with 1 entry (`No revenue model documentation found`) despite revenue fields populated. |

**Summary:** 7 `pass`, 0 `partial`, 0 `gap-correct`, 0 `n/a`
