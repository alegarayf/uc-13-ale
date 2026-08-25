# Golden Checklist — GKF Company Profiler (PROFILER)

| Field | Value |
|-------|-------|
| **catalog** | `uc13_ale` |
| **company** | `GKF` |
| **pipeline run_id** | T1 job `599472715895762` (Profiler output is `classification.company_profile` and is not keyed by the 2026-08-19 diligence `cd3abe7b4c3b4b9a91ffa977c5d2c1ce`; cited for T5 scoring against T1's fresh row) |
| **source table** | `uc13_ale.classification.company_profile` |
| **rubric source** | `.dev/g1_score_all_agents.py::score_profiler()` (7-field; pass / partial; no `gap-correct` branch) |
| **authoring provenance** | queried `SELECT CAST(created_at AS STRING) AS ts, industry_overlay, overlay_confidence, revenue_model, revenue_model_note, business_description, deal_type, banked, banked_note, vertical_subsector, data_room_gaps FROM uc13_ale.classification.company_profile WHERE company_name = 'GKF' ORDER BY created_at DESC LIMIT 1` -> `created_at` 2026-08-25 13:18:14.578154 (post-T1; not the pre-T1 stale `2026-07-20` row) |

**Verdict key:** `pass` — field meets `score_profiler()` threshold; `partial` — overlay is not `healthcare_services`, a presence field is empty, `banked` is not true, or `data_room_gaps` is not a JSON list. GKF G1 floor is informational (`BASELINES["gkf"]` unset).

## Checklist (7 rows)

| item_id | display_name | verdict | notes |
|---------|--------------|---------|-------|
| industry_overlay | Industry overlay extraction | partial | Extracted `industry_overlay`=`other`, `overlay_confidence`=`medium` (not `healthcare_services`, so `score_profiler()` is `partial`). Independent: CIM `Project Ajax CIM vF - Rallyday Partners.pdf` p.5 OVERVIEW & PROCESS: one of the largest franchisees of The Goddard School, "premier provider of early childhood education"; section "Leading Franchise of Premium, Nationally Recognized Preschools"; childcare for kids from 6 weeks. CIM p.6: five Northern Virginia / Maryland locations, ~$23mm revenue. Matches a non-healthcare corpus (`other` / consumer preschool). Frozen rubric still requires `healthcare_services` for `pass`. |
| revenue_model | Revenue model extraction | pass | Extracted `revenue_model`=`repeat_services` (truthy, so `score_profiler()` is `pass`). Warehouse `revenue_model_note` is the string `null`. Independent: CIM p.53 COMPANY DEMOGRAPHICS BY THE NUMBERS states `$2,422 Average Monthly Tuition` and `~3 Years Avg. Student Tenure`; p.68 SUMMARY INCOME STATEMENT Total Revenue `$21,403` / `$22,266` / `$23,022` (2023A/2024A/2025B). Recurring tuition / enrollment, not a one-off project fee. |
| business_description | Business description extraction | pass | `business_description` nonempty (pass). Independent: CIM p.5 / p.6 Goddard franchisee, five DMV schools, ~$23mm revenue, Wonder of Learning curriculum, childcare from 6 weeks. Extracted prose is thinner (generic "early education sector") but the rubric scores presence. |
| deal_type | Deal type extraction | pass | Extracted `deal_type`=`growth_equity` (truthy, so `score_profiler()` is `pass`). Independent: CIM p.2 Confidentiality & Disclaimer: Navagant engaged to solicit a qualified buyer to acquire all or some of the Company; the document is a Confidential Information Memorandum. CIM p.5 section "Opportunity to be One of the First Institutional Capital with Successful & Experienced Franchisee". No chunk names `growth_equity` vs `buyout`; the rubric scores presence, not enum fidelity. |
| banked | Banked status extraction | pass | Extracted `banked`=`true`; `banked_note` is null. Independent of the LLM field: `uc13_ale.classification.doc_relevance` has `Project Ajax CIM vF - Rallyday Partners.pdf` with workstream BUSINESS_MODEL (priority_tier 1). That filename matches `detect_banked`'s CIM rule. CIM p.2 names the document a Confidential Information Memorandum. |
| vertical_subsector | Vertical subsector extraction | pass | Extracted `vertical_subsector`=`early_childhood_education` (truthy, so `score_profiler()` is `pass`). Independent: CIM p.5 "early childhood education" / "premium, nationally recognized preschools" / childcare from 6 weeks. The corpus uses the phrase; the rubric scores presence. |
| data_room_gaps | Data-room gaps field presence | partial | Warehouse `data_room_gaps` is SQL NULL. Profiler writes `None` when the in-memory gap list is empty (`data_room_gaps if data_room_gaps else None`). `score_profiler()` awards `pass` only when `json.loads` yields a list, so NULL is `partial`. Independent: `doc_relevance` has the BUSINESS_MODEL CIM row, so a no-chunks gap list would be unexpected. This is empty-to-NULL write-path, not a missing CIM. |

**Summary:** 5 `pass`, 2 `partial` — `score_profiler()` **5/7**. GKF G1 floor is informational.
