# Golden Checklist — Clearsulting Financial Trends Agent (FTA)

| Field | Value |
|-------|-------|
| **catalog** | `uc13_ale` |
| **company** | `Clearsulting` |
| **pipeline run_id** | `6e1b4f5d95284b33bbd08942b3595dd6` (pipeline agent manifest; correlated to FTA analysis row `2026-07-30 13:40:00`) |
| **source table** | `uc13_ale.analysis.financial_trends` |
| **rubric source** | `.dev/g1_score_all_agents.py::score_fta()` (18-field; pass=1, partial=0.5, miss=0) |
| **scorecard ref** | `.dev/plans/eval-multi-company-coverage-expansion/signoffs/T4-clearsulting-w1.md` §G1 |
| **spec ref** | eval-multi-company-coverage — W1 Clearsulting FTA onboarding |

**Verdict key:** `pass` — field meets rubric threshold; `partial` — field partially populated or thinly grounded; `miss` — field absent or fails rubric threshold. **Floor:** ≥ **16/18** weighted points (same bar as Elder Care FTA baseline in `g1_score_all_agents.py`).

## Checklist (18 rows)

| item_id | display_name | verdict | notes |
|---------|--------------|---------|-------|
| 1_revenue_trend | Revenue trend (3yr) | pass | 12 revenue periods in `revenue_trend_json` (2020A–2024E). |
| 2_revenue_cagr_yoy | Revenue CAGR / YoY | pass | YoY growth populated on PF revenue rows. |
| 3_gross_margin | Gross margin (3yr) | pass | 12 gross-margin records. |
| 4_ebitda_reported | EBITDA reported | pass | Reported EBITDA periods present in `ebitda_json`. |
| 5_ebitda_pf_margin | EBITDA PF adjusted margin | pass | PF adjusted EBITDA with margin %. |
| 6_ebitda_bridge | EBITDA bridge (addbacks) | pass | Addback schedule populated (≥10 items). |
| 7_addback_pct | Addback total / addback_pct_of_ebitda | pass | `addback_pct_of_ebitda` = 45.4%. |
| 8_working_capital | Working capital trend | pass | Working-capital struct populated (non-null fields). |
| 9_opex_breakdown | OPEX breakdown | pass | 5 OPEX records. |
| 10_revenue_by_segment | Revenue by segment present | partial | Segment rows present but below Elder Care density threshold (≥10). |
| 11_projected_financials | Projected financials | partial | 2024E revenue present; `budget_vs_actual_json` empty. |
| 12_executive_summary | Executive summary | pass | Executive summary length 515 chars (≥200). |
| 13_threshold_flags | Threshold flags | pass | ≥1 threshold flag in `flags`. |
| 14_discrepancies | Discrepancies | pass | Multiple discrepancy entries surfaced. |
| 15_data_room_gaps | Data room gaps count | pass | ≥1 data-room gap recorded. |
| 16_citation_revenue | Citation on revenue | pass | Revenue rows carry `source_doc`. |
| 17_citation_ebitda | Citation on EBITDA | pass | EBITDA rows carry `source_doc`. |
| 18_runtime | FTA runtime | pass | Post-success analysis row present (`reasoning_trace` step 2 elapsed 329s). |

**Summary:** 16 `pass`, 2 `partial`, 0 `miss` — weighted score **17/18** (floor ≥16/18 met).
