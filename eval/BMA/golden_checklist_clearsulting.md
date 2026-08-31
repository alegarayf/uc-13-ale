# Golden Checklist — Clearsulting Business Model Agent (BMA)

| Field | Value |
|-------|-------|
| **catalog** | `uc13_ale` |
| **company** | `Clearsulting` |
| **pipeline run_id** | `6e1b4f5d95284b33bbd08942b3595dd6` (pipeline agent manifest; correlated to BMA analysis row `2026-08-19 19:23:07`) |
| **source table** | `uc13_ale.analysis.business_model` |
| **rubric source** | `.dev/g1_score_all_agents.py::score_bma()` (7-field; pass / partial / gap-correct; only `sales_motion` can be `gap-correct`) |
| **authoring provenance** | queried `uc13_ale.analysis.business_model` WHERE `company_name='Clearsulting'` ORDER BY `created_at` DESC LIMIT 1 -> `created_at` 2026-08-19 19:23:07 |

**Verdict key:** `pass` — field meets rubric threshold; `partial` — field empty or thinly populated; `gap-correct` — sales-motion absence correctly surfaced (tag and JSON both empty). Clearsulting G1 floor is informational (`BASELINES["clearsulting"]` unset).

## Checklist (7 rows)

| item_id | display_name | verdict | notes |
|---------|--------------|---------|-------|
| products_services | Products and services extraction | pass | `products_services_json` has 10 practice lines. CIM `Project Infinity  - Confidential Information Memorandum.pdf` p.20 Core Services states Financial Close FY24 $26M / 44% (105 resources), Risk Advisory $8.6M / 15%, Digital Reporting & Compliance $6.7M / 11%, Treasury $7.9M / 14% — matches the extracted dollars and percents. |
| people_org | People and organization extraction | pass | `people_and_org_json` names 18 executives. CIM p.38 Executive Leadership Team lists Marc Ursick Founder & CEO, David Courtade President of NA, Tim Nicholls President of EMEA, Monica Engelhardt CFO & Head of Operations. |
| customer_profile | Customer profile extraction | pass | `customer_profile_json` populated (enterprise CFO buyers; 10 end-markets; NA + EMEA geography). CIM p.5 Blue-Chip Client Base and p.4 Executive Summary describe the same F500 / OCFO consultancy positioning. |
| sales_motion | Sales motion extraction | pass | `sales_motion_tag`=`enterprise_sales`; `sales_motion_json` cites Practice Commercial + delivery GTM. `Project Infinity - Go-to-Market Strategy Deep Dive.pdf` p.6 "Building and Maintaining Long Term Relationships Through a Cross-functional Collaborative GTM Structure" names Practice Commercial (sourcing, pipeline, winning deals, alliance management). |
| key_dependencies | Key dependencies extraction | pass | `key_dependencies_json` has 12 rows (BlackLine, Kyriba, Workiva, OneStream, Certinia, Salesforce, HighRadius, Coupa, SAP, Upsourced Accounting, Grant Thornton, Marc Ursick). CIM p.20 Core Services is the cited platform stack. |
| data_room_gaps | Data-room gaps correctly reported | pass | 4 `data_room_gaps` strings (ownership empty; healthcare overlay referral/payor empty; by-location metrics thin). List type meets `score_bma()`. |
| overlay_conflict | Overlay conflict correctly reported | pass | `overlay_conflict`=`false`. Extracted practices are finance-transformation consulting; live `company_profile.industry_overlay`=`tech_services` / `IT_services` (not a healthcare home-care overlay). |

**Summary:** 7 `pass`, 0 `partial`, 0 `gap-correct` — `score_bma()` **7/7**.
