# Golden Checklist — GKF Business Model Agent (BMA)

| Field | Value |
|-------|-------|
| **catalog** | `uc13_ale` |
| **company** | `GKF` |
| **pipeline run_id** | `cd3abe7b4c3b4b9a91ffa977c5d2c1ce` (pipeline agent manifest; correlated to BMA analysis row `2026-08-19 19:21:54`) |
| **source table** | `uc13_ale.analysis.business_model` |
| **rubric source** | `.dev/g1_score_all_agents.py::score_bma()` (7-field; pass / partial / gap-correct; only `sales_motion` can be `gap-correct`) |
| **authoring provenance** | queried `uc13_ale.analysis.business_model` WHERE `company_name='GKF'` ORDER BY `created_at` DESC LIMIT 1 -> `created_at` 2026-08-19 19:21:54.717361 |

**Verdict key:** `pass` — field meets rubric threshold; `partial` — field empty or thinly populated; `gap-correct` — sales-motion absence correctly surfaced (tag and JSON both empty). GKF G1 floor is informational (`BASELINES["gkf"]` unset).

## Checklist (7 rows)

| item_id | display_name | verdict | notes |
|---------|--------------|---------|-------|
| products_services | Products and services extraction | pass | `products_services_json` has 4 lines (tuition/core childcare, before-and-after, summer camp, registration fees). CIM `Project Ajax CIM vF - Rallyday Partners.pdf` p.53 COMPANY DEMOGRAPHICS BY THE NUMBERS states `$2,422 Average Monthly Tuition`; p.68 SUMMARY INCOME STATEMENT Gross Profit % Margin 53% / 52% / 53% / 54% (2023A-2026P) and Total Revenue `$21,403` / `$22,266` / `$23,022` (2023A/2024A/2025B); p.5 Dedicated Management Team states `10.3% Revenue CAGR` over 5 years. Databook `Project Ajax - Financial Due Diligence Databook - 12.22.25.xlsx` Revenue -- Summary has Summer Camp `28.225` / `24.89` / `24.045` and Registration Fees `45.9` / `49.2` / `44.5` (USD thousands), matching the extracted dollars. |
| people_org | People and organization extraction | pass | `people_and_org_json` names Mike Pesi (CEO), Laura Dinder (Designated Market Operator), and Ross Flax. CIM p.16 HIGHLY SEASONED MANAGEMENT TEAM / MANAGEMENT EXPERIENCE AND CREDENTIALS lists Mike Pesi Goddard 10 / industry 25+, Laura Dinder 7 / 10+, Ross Flax 27 / 35+. CIM p.58 section header is `Ross Flax Chief Growth and Strategy Officer`. CIM p.2 names the five school entities (Creative Learning, Top Farm, Smart Kids, Bethesda Kids, Tysons Kids). |
| customer_profile | Customer profile extraction | pass | `customer_profile_json` populated (families; $140k+ household income; 80%+ some college; 40k+ married families with kids; five DMV schools). CIM p.53 states the same demographic bullets plus `~3 Years Avg. Student Tenure` and `$177k Total Potential LTV Per Student`. CIM p.5 OVERVIEW & PROCESS: Goddard childcare for kids from 6 weeks to 6 years; CIM p.6 names five Northern Virginia / Maryland locations and ~$23mm revenue. |
| sales_motion | Sales motion extraction | pass | `sales_motion_tag`=`inbound_plg`; `sales_motion_json` cites the 2024 funnel 1,818 leads / 522 tours / 338 registrations. CIM p.54 COMPANY DEMOGRAPHICS BY THE NUMBERS (vision figure MARKETING FUNNEL 2024) states Leads `1,818`, Tours `522`, Registrations `338`, Lead-to-Tours `29%`, Tours-to-Registrations `65%`, plus franchisor-sponsored marketing campaigns. |
| key_dependencies | Key dependencies extraction | pass | `key_dependencies_json` has 6 rows (Goddard franchisor, Family Hub App, Mike Pesi, Laura Dinder, Ross Flax, DMV geography). CIM p.5 names The Goddard School and proprietary Wonder of Learning curriculum; p.60 GODDARD FAMILY HUB is the parent mobile app; p.68 Franchise Fees `$1,502` / `$1,563` / `$1,611` on `$21,403` / `$22,266` / `$23,022` revenue (~7% COGS). |
| data_room_gaps | Data-room gaps correctly reported | pass | 2 `data_room_gaps` strings (by-location client metrics thin; ownership empty). List type meets `score_bma()`. CIM p.2 / p.16 confirm entity names but not a cap-table ownership extract. |
| overlay_conflict | Overlay conflict correctly reported | pass | `overlay_conflict`=`false`. Extracted model is Goddard preschool / early-childhood franchise (CIM p.5 / p.6). Live `company_profile.industry_overlay`=`other` / `vertical_subsector`=`early_childhood_education` (not a healthcare home-care overlay). |

**Summary:** 7 `pass`, 0 `partial`, 0 `gap-correct` — `score_bma()` **7/7**.
