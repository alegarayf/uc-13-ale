# Golden Checklist — Clearsulting Financial Trends Agent (FTA)

| Field | Value |
|-------|-------|
| **catalog** | `uc13_ale` |
| **company** | `Clearsulting` |
| **pipeline run_id** | `<TBD: operator fills after pipeline run>` |
| **source table** | `uc13_ale.analysis.financial_trends` |
| **rubric source** | `.dev/g1_score_all_agents.py::score_fta()` (18-field; pass=1, partial=0.5, miss=0) |
| **scorecard ref** | `<TBD: operator fills after scoring>` |
| **spec ref** | eval-multi-company-coverage — W1 Clearsulting FTA onboarding |

**Verdict key:** `pass` — field meets rubric threshold; `partial` — field partially populated or thinly grounded; `miss` — field absent or fails rubric threshold. **Floor:** ≥ **16/18** weighted points (same bar as Elder Care FTA baseline in `g1_score_all_agents.py`).

**Operator note:** Score each row after a Clearsulting FTA pipeline run. Replace every `<TBD: …>` placeholder with the actual `run_id`, scorecard path, verdict, and evidence notes. Do not invent run_ids or scores in this template pass.

## Checklist (18 rows)

| item_id | display_name | verdict | notes |
|---------|--------------|---------|-------|
| 1_revenue_trend | Revenue trend (3yr) | `<TBD>` | `<TBD: operator fills after pipeline run>` |
| 2_revenue_cagr_yoy | Revenue CAGR / YoY | `<TBD>` | `<TBD: operator fills after pipeline run>` |
| 3_gross_margin | Gross margin (3yr) | `<TBD>` | `<TBD: operator fills after pipeline run>` |
| 4_ebitda_reported | EBITDA reported | `<TBD>` | `<TBD: operator fills after pipeline run>` |
| 5_ebitda_pf_margin | EBITDA PF adjusted margin | `<TBD>` | `<TBD: operator fills after pipeline run>` |
| 6_ebitda_bridge | EBITDA bridge (addbacks) | `<TBD>` | `<TBD: operator fills after pipeline run>` |
| 7_addback_pct | Addback total / addback_pct_of_ebitda | `<TBD>` | `<TBD: operator fills after pipeline run>` |
| 8_working_capital | Working capital trend | `<TBD>` | `<TBD: operator fills after pipeline run>` |
| 9_opex_breakdown | OPEX breakdown | `<TBD>` | `<TBD: operator fills after pipeline run>` |
| 10_revenue_by_segment | Revenue by segment present | `<TBD>` | `<TBD: operator fills after pipeline run>` |
| 11_projected_financials | Projected financials | `<TBD>` | `<TBD: operator fills after pipeline run>` |
| 12_executive_summary | Executive summary | `<TBD>` | `<TBD: operator fills after pipeline run>` |
| 13_threshold_flags | Threshold flags | `<TBD>` | `<TBD: operator fills after pipeline run>` |
| 14_discrepancies | Discrepancies | `<TBD>` | `<TBD: operator fills after pipeline run>` |
| 15_data_room_gaps | Data room gaps count | `<TBD>` | `<TBD: operator fills after pipeline run>` |
| 16_citation_revenue | Citation on revenue | `<TBD>` | `<TBD: operator fills after pipeline run>` |
| 17_citation_ebitda | Citation on EBITDA | `<TBD>` | `<TBD: operator fills after pipeline run>` |
| 18_runtime | FTA runtime | `<TBD>` | `<TBD: operator fills after pipeline run>` |

**Summary:** `<TBD: operator fills pass/partial/miss counts after scoring>` — weighted score **`<TBD>`/18** (floor ≥16/18 target).
