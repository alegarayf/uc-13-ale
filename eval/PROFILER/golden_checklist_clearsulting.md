# Golden Checklist — Clearsulting Company Profiler (PROFILER)

| Field | Value |
|-------|-------|
| **catalog** | `uc13_ale` |
| **company** | `Clearsulting` |
| **pipeline run_id** | `6e1b4f5d95284b33bbd08942b3595dd6` (pipeline agent manifest; Profiler output is `classification.company_profile` and is not keyed by this `run_id`, cited for T5 promotion consistency with the other Clearsulting checklists) |
| **source table** | `uc13_ale.classification.company_profile` |
| **rubric source** | `.dev/g1_score_all_agents.py::score_profiler()` (7-field; pass / partial; no `gap-correct` branch) |
| **authoring provenance** | queried `SELECT CAST(created_at AS STRING) AS ts, industry_overlay, overlay_confidence, revenue_model, revenue_model_note, business_description, deal_type, banked, banked_note, vertical_subsector, data_room_gaps FROM uc13_ale.classification.company_profile WHERE company_name = 'Clearsulting' ORDER BY created_at DESC LIMIT 1` -> `created_at` 2026-08-24 19:31:55.237812 (post-T1; not the pre-T1 stale `2026-07-07` row) |

**Verdict key:** `pass` — field meets `score_profiler()` threshold; `partial` — overlay is not `healthcare_services`, a presence field is empty, `banked` is not true, or `data_room_gaps` is not a JSON list. Clearsulting G1 floor is informational (`BASELINES["clearsulting"]` unset).

## Checklist (7 rows)

| item_id | display_name | verdict | notes |
|---------|--------------|---------|-------|
| industry_overlay | Industry overlay extraction | partial | Extracted `industry_overlay`=`tech_services`, `overlay_confidence`=`high` (not `healthcare_services`, so `score_profiler()` is `partial`). Independent: CIM `Project Infinity  - Confidential Information Memorandum.pdf` p.4 Executive Summary: "specialized consultancy" with "deep expertise in emerging financial cloud technologies" and "category leader for office of the CFO digital transformation". Matches the profiler prompt's `tech_services` overlay (tech-enabled / digital services). Frozen rubric still requires `healthcare_services` for `pass`. |
| revenue_model | Revenue model extraction | pass | Extracted `revenue_model`=`hybrid` (truthy, so `score_profiler()` is `pass`). Independent: `Project Infinity - Revenue Masterfile (Monthly Jan 2020 - Aug 2025).xlsx` sheet Revenue by Client & Project uses `Billing Type=Time and Materials` and `Billing Type=Fixed`; CIM p.11 Optimized Revenue & Delivery Model: "move from T&M to fixed-fee / outcome-based fee model" and recurring revenue via digital assets / Application Managed Services. `revenue_model_note` mentions value-at-risk contracts (not found as a verbatim chunk phrase); the hybrid mix still holds. |
| business_description | Business description extraction | pass | `business_description` nonempty (pass). Independent: CIM p.5 Company Overview is a "high-impact digital finance consulting firm"; p.47 Existing Account Expansion: "account ownership" / "repeat revenues"; p.11 New Capabilities & Managed Services. Extracted verticals manufacturing / energy / retail / healthcare vs CIM p.28 "healthcare, industrials, consumer, and financial services" (paraphrase; p.28 also names ExxonMobil). |
| deal_type | Deal type extraction | pass | Extracted `deal_type`=`growth_equity` (truthy, so `score_profiler()` is `pass`). Independent: CIM p.2 Important Disclaimer frames "a potential acquisition of or investment in the Company (the Transaction)". No chunk names `growth_equity` vs `buyout`; the rubric scores presence, not enum fidelity. |
| banked | Banked status extraction | pass | Extracted `banked`=`true`; `banked_note` is null. Independent of the LLM field: `uc13_ale.classification.doc_relevance` has `Project Infinity  - Confidential Information Memorandum.pdf` with workstream BUSINESS_MODEL (priority_tier 1). That filename matches `detect_banked`'s confidential-information-memorandum rule. CIM p.2 names the document a Confidential Information Memorandum. |
| vertical_subsector | Vertical subsector extraction | pass | Extracted `vertical_subsector`=`IT_services` (truthy, so `score_profiler()` is `pass`). Independent: CIM p.5 "digital finance consulting firm" / p.4 financial cloud technologies. `IT_services` is overlay-adjacent (the profiler prompt lists IT services under `tech_services`); the corpus does not use the token `IT_services`. |
| data_room_gaps | Data-room gaps field presence | partial | Warehouse `data_room_gaps` is SQL NULL. Profiler writes `None` when the in-memory gap list is empty (`data_room_gaps if data_room_gaps else None`). `score_profiler()` awards `pass` only when `json.loads` yields a list, so NULL is `partial`. Independent: `doc_relevance` has the BUSINESS_MODEL CIM row, so a no-chunks gap list would be unexpected. This is empty-to-NULL write-path, not a missing CIM. |

**Summary:** 5 `pass`, 2 `partial` — `score_profiler()` **5/7**. Clearsulting G1 floor is informational.
