# Golden Checklist — Elder Care Business Model Agent (M1)

| Field | Value |
|-------|-------|
| **catalog** | `uc13_ale` |
| **company** | `Elder Care` |
| **git SHA** | `94da269968c1c1f014118f93c1c5b9ad7243bb1e` |
| **E2E timestamp** | `2026-07-14T13:43:07Z` |
| **source table** | `uc13.analysis.business_model` |
| **spec ref** | `uc13-eval-harness-all-agents-spec.md §6.1` |

**Verdict key:** `pass` — field populated with citation-backed extraction; `partial` — field partially populated or thinly grounded; `gap-correct` — absence or limitation correctly surfaced in `data_room_gaps` / structured nulls; `n/a` — not applicable to this corpus.

## Checklist (7 rows)

| item_id | display_name | verdict | notes |
|---------|--------------|---------|-------|
| products_services | Products and services extraction | pass | 5 `products_services_json` entries (HHA hourly, live-in daily, RN/LPN hourly, care management) with rates, margin bands, and `source_doc`=`2024 Elder Care - CIM_vF.pdf` (p.11, p.13). |
| people_org | People and organization extraction | pass | `people_and_org_json` populated — 5 key executives with tenure/background citations, headcount-by-function table (onsite + offshore), workforce model (64 onsite / 44 offshore, 40.7%), and hiring/growth metrics from CIM. |
| customer_profile | Customer profile extraction | gap-correct | `customer_profile_json`={} (empty after truncation recovery). `data_room_gaps` correctly flags healthcare overlay `referral_source_breakdown` and `payor_mix` not extracted; `customer_operational_metrics_json` has client counts by market but lives outside `customer_profile_json`. |
| sales_motion | Sales motion extraction | gap-correct | `sales_motion_tag`=null; `sales_motion_json`={}. `data_room_gaps` entry documents sales-motion tag not extracted and suggests GTM/sales retrieval gap. |
| key_dependencies | Key dependencies extraction | gap-correct | `key_dependencies_json`=[]; `data_room_gaps` documents vendor/platform/channel/people dependencies not extracted and retrieval coverage gap. |
| data_room_gaps | Data-room gaps correctly reported | pass | 7 `data_room_gaps` entries — LLM truncation recovery note, sales_motion, revenue_visibility, recent_model_changes, key_dependencies, healthcare referral_source_breakdown, healthcare payor_mix — align with null/empty extraction fields in the scored row. |
| overlay_conflict | Overlay conflict correctly reported | pass | `overlay_conflict`=false; `overlay_conflict_note` and `overlay_conflict_evidence` null/empty — consistent with healthcare home-care CIM (no overlay mismatch surfaced). |

**Summary:** 4 `pass`, 0 `partial`, 3 `gap-correct`, 0 `n/a`
