# Golden Checklist — Elder Care Financial Trends Agent (FTA)

| Field | Value |
|-------|-------|
| **catalog** | `uc13_ale` |
| **company** | `Elder Care` |
| **source table** | `uc13_ale.analysis.financial_trends` |
| **rubric source** | `.dev/g1_score_all_agents.py::score_fta()` (18-field; pass=1, partial=0.5, miss=0) |
| **scorecard ref** | `.dev/scorecards/scorecard_7_03_post_m3_vs_7_02.md` (M-RE3 post-hardening re-score) |
| **spec ref** | eval-consolidation-program §17 item 18 |

**Verdict key:** `pass` — field meets rubric threshold; `partial` — field partially populated or thinly grounded; `miss` — field absent or fails rubric threshold. **Floor:** ≥ **16/18** weighted points (same bar as `g1_score_all_agents.py` `_ELDER_CARE_BASELINES["fta"]`).

## Checklist (18 rows)

| item_id | display_name | verdict | notes |
|---------|--------------|---------|-------|
| 1_revenue_trend | Revenue trend (3yr) | pass | 12 records 2020A–2024E — reported, PF adjusted, and Pro Forma IS projection rows (`revenue_trend_json`). |
| 2_revenue_cagr_yoy | Revenue CAGR / YoY | pass | YoY % on PF Adj Revenue (58.3%, 47.1%, 63.9%, 35.9%, 30.2%). |
| 3_gross_margin | Gross margin (3yr) | pass | 11 records 2020A–2024E; Pro Forma IS vs Historical P&L divergence flagged via `discrepancy_note` on 2023A and TTM. |
| 4_ebitda_reported | EBITDA reported | pass | 5 reported EBITDA periods 2020A–TTM with margins. |
| 5_ebitda_pf_margin | EBITDA PF adjusted margin | pass | 5 PF adjusted records with margin % (23.5%, 22.3%, 19.3%, 19.5%, 19.9%). |
| 6_ebitda_bridge | EBITDA bridge (addbacks) | pass | 17 addback items (A–Q) with TTM Aug-24 amounts. |
| 7_addback_pct | Addback total / addback_pct_of_ebitda | pass | `addback_pct_of_ebitda` = 246.9%. |
| 8_working_capital | Working capital trend | miss | `working_capital_json` struct present but `dso_days`, `dpo_days`, `ar_aging_note` all null. |
| 9_opex_breakdown | OPEX breakdown | pass | 5 records, all `source_location` = Historical P&L Summary (reported basis). |
| 10_revenue_by_segment | Revenue by segment present | pass | 28 segment rows (NY, Westchester, LI, CT, MA, NJ, Existing/New Locations Total × periods). |
| 11_projected_financials | Projected financials | partial | 2024E revenue and gross margin present; `budget_vs_actual_json` empty. |
| 12_executive_summary | Executive summary | pass | ~485 chars — PF spine + adjustment risk framing (`executive_summary`). |
| 13_threshold_flags | Threshold flags | pass | 2 flags — Red (EBITDA margin 7.9% < 10%) + Yellow (addback 246.9% > 20%). |
| 14_discrepancies | Discrepancies | pass | 4 discrepancies surfaced (EBITDA TTM, margin 2020A/2022A, professional fees 2020A text/vision). |
| 15_data_room_gaps | Data room gaps count | pass | 1 gap — budget vs actual not found. |
| 16_citation_revenue | Citation on revenue | pass | `source_doc` + `source_location` on revenue records. |
| 17_citation_ebitda | Citation on EBITDA | pass | `source_doc` + `source_location` on EBITDA records. |
| 18_runtime | FTA runtime | pass | ~91s pipeline run (`reasoning_trace` step 2 elapsed; ≤120s rubric pass). |

**Summary:** 16 `pass`, 1 `partial`, 1 `miss` — weighted score **16/18** (floor ≥16/18 met).
