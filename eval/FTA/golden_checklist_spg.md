# Golden Checklist — SPG Financial Trends Agent (FTA)

| Field | Value |
|-------|-------|
| **catalog** | `uc13_ale` |
| **company** | `SPG` |
| **pipeline run_id** | Chip B e2e DAG `641030239604593` (FTA analysis correlated to `2026-07-30 13:47:17` row — pre-ingest-fix corpus) |
| **source table** | `uc13_ale.analysis.financial_trends` |
| **rubric source** | `.dev/g1_score_all_agents.py::score_fta()` (18-field; pass=1, partial=0.5, miss=0) |
| **scorecard ref** | `.dev/plans/eval-multi-company-coverage-expansion/signoffs/T8-spg-ingest-fta.md` |
| **spec ref** | eval-multi-company-coverage — SPG ingest gate + FTA checklist (post-ingest=1.0) |

**Scoring note:** Checklist scored **after** ingest preflight reached **1.0000** (363/363). The analysis row predates the 2026-08-19 ingest fix (SpreadsheetML `.xls` + projection model re-ingest); post-ingest FTA re-run **`run_id=970944326201371`** submitted — update this checklist when a newer row lands.

**Verdict key:** `pass` — field meets rubric threshold; `partial` — field partially populated or thinly grounded; `miss` — field absent or fails rubric threshold. **Floor:** ≥ **16/18** weighted points (same bar as Elder Care FTA baseline in `g1_score_all_agents.py`).

## Checklist (18 rows)

| item_id | display_name | verdict | notes |
|---------|--------------|---------|-------|
| 1_revenue_trend | Revenue trend (3yr) | partial | Revenue periods present but below ≥8 pass threshold. |
| 2_revenue_cagr_yoy | Revenue CAGR / YoY | partial | YoY/growth fields thin vs Elder Care density. |
| 3_gross_margin | Gross margin (3yr) | miss | `gross_margin_json` empty or below rubric threshold. |
| 4_ebitda_reported | EBITDA reported | partial | Some EBITDA periods; fewer than 3 reported-type rows. |
| 5_ebitda_pf_margin | EBITDA PF adjusted margin | partial | PF/adjusted EBITDA thin vs pass bar. |
| 6_ebitda_bridge | EBITDA bridge (addbacks) | partial | Addback schedule present but &lt;10 items. |
| 7_addback_pct | Addback total / addback_pct_of_ebitda | partial | `addback_pct_of_ebitda` populated but bridge thin. |
| 8_working_capital | Working capital trend | miss | Working-capital struct null / empty. |
| 9_opex_breakdown | OPEX breakdown | miss | `opex_breakdown_json` absent or empty. |
| 10_revenue_by_segment | Revenue by segment present | partial | Segment rows present but &lt;10. |
| 11_projected_financials | Projected financials | miss | No 2024E projection spine in revenue rows. |
| 12_executive_summary | Executive summary | pass | Executive summary ≥200 chars. |
| 13_threshold_flags | Threshold flags | miss | No threshold flags in `flags`. |
| 14_discrepancies | Discrepancies | partial | Fewer than 2 discrepancy entries. |
| 15_data_room_gaps | Data room gaps count | pass | ≥1 data-room gap recorded. |
| 16_citation_revenue | Citation on revenue | pass | Revenue rows carry `source_doc`. |
| 17_citation_ebitda | Citation on EBITDA | partial | EBITDA citations incomplete on first rows. |
| 18_runtime | FTA runtime | pass | Post-success analysis row present (Chip B e2e). |

**Summary:** 4 `pass`, 9 `partial`, 5 `miss` — weighted score **8.5/18** (floor ≥16/18 **not** met). Score reflects pre-ingest-fix analysis row; re-score after post-ingest FTA pipeline run completes.
