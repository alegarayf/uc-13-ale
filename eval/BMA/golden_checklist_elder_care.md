# Golden Checklist — Elder Care Business Model Agent (M1)

| Field | Value |
|-------|-------|
| **catalog** | `uc13_ale` |
| **company** | `Elder Care` |
| **git SHA** | `e7b65ce2ac6213979cb4a057439d07c66df18260` |
| **E2E timestamp** | `2026-07-21T21:47:47Z` |
| **source table** | `uc13_ale.analysis.business_model` |
| **spec ref** | `uc13-eval-harness-all-agents-spec.md §6.1` |
| **pipeline run_id** | `f0a4065e14e7407195721c872300c2de` |

**Verdict key:** `pass` — field populated with citation-backed extraction; `partial` — field partially populated or thinly grounded; `gap-correct` — absence or limitation correctly surfaced in `data_room_gaps` / structured nulls; `n/a` — not applicable to this corpus.

**Re-score note:** M4-T3 fresh Cell 11 re-score (2026-07-21). Reconciles prior 4/7 checklist (2026-07-14, SHA `94da269…`) with authoritative scorecard `.dev/scorecards/uc13-eval-harness-all-agents_bma_elder-care_2026-07-21.md` and INDEX row 15.

## Checklist (7 rows)

| item_id | display_name | verdict | notes |
|---------|--------------|---------|-------|
| products_services | Products and services extraction | pass | `products_services_json` populated — 5 service lines (HHA hourly, live-in daily, RN/LPN hourly, care management) with rates, margin bands, and CIM citations (`2024 Elder Care - CIM_vF.pdf` p.11, p.13). |
| people_org | People and organization extraction | pass | `people_and_org_json` populated — 5 key executives with tenure/background citations, headcount-by-function table (onsite + offshore), workforce model (64 onsite / 44 offshore, 40.7%), and hiring/growth metrics from CIM. |
| customer_profile | Customer profile extraction | pass | `customer_profile_json` populated with segments, end markets, geographic concentration, and healthcare overlay referral breakdown. |
| sales_motion | Sales motion extraction | pass | `sales_motion_tag`=`relationship`; `sales_motion_json` documents referral-driven GTM and named relationship owners. |
| key_dependencies | Key dependencies extraction | pass | `key_dependencies_json` lists platforms, vendors, channels, and offshore team dependencies. |
| data_room_gaps | Data-room gaps correctly reported | pass | 10 `data_room_gaps` entries align with remaining thin fields; no contradiction with populated extraction fields. |
| overlay_conflict | Overlay conflict correctly reported | pass | `overlay_conflict`=false; `overlay_conflict_note` and `overlay_conflict_evidence` null/empty — consistent with healthcare home-care CIM (no overlay mismatch surfaced). |

**Summary:** 7 `pass`, 0 `partial`, 0 `gap-correct`, 0 `n/a`
