# Exec-Summary Human Spot-Check Rubric (Rung 3)

| Field | Value |
|-------|-------|
| **surfaces** | `exec_summary` (primary); `fta_numeric` (DG-19 generalization — CHK-26a) |
| **catalog** | `uc13_ale` |
| **company** | `Elder Care` |
| **rung** | `human` (both surfaces per CHK-26a `rung_assignments`) |
| **spec ref** | eval-consolidation-program §17 item 26 · §12.1 rung 3 · §8.8 logical field set |
| **DG-19 record** | CHK-26a rationale (T5): item-23 no-go + item-26a threshold failure ⇒ rubric generalized to `fta_numeric` full claim set |

This rubric is the rung-3 human spot-check protocol M3 executes. A completed spot-check is a **whole-surface** run (HALT-15): every claim in the enumeration below receives a human verdict before the run closes.

---

## 1. Claim enumeration — `exec_summary`

**Source artifact:** `uc13_ale.analysis.diligence_report.executive_summary` (latest row for Elder Care).

**Source query (verbatim):**

```sql
SELECT executive_summary, created_at FROM uc13_ale.analysis.diligence_report WHERE company_name = 'Elder Care' ORDER BY created_at DESC LIMIT 1;
```

**Listing evidence:** `created_at = 2026-07-28T22:47:46.289Z`, text length 5641 chars. Claims decomposed atomically from the markdown sections **Business Overview**, **Financial Picture**, **Top Risks**, and **Confidence** — one row per factual assertion the operator can independently verify. Count: **49**.

**Note:** `.dev/eval-program/calibration_sample_exec_summary.yaml` (item 26a) labels 28 claims drawn from this same field for judge calibration; that sample is a **subset** of this enumeration (claims `exec.claim.001`–`028` align with the sample where text matches; additional claims `029`–`049` cover prose not atomized in the calibration sample).

| section | claim_id | claim_text |
| --- | --- | --- |
| Business Overview | exec.claim.001 | Elder Care Homecare is a private-pay home care company operating across six locations in the Tri-State region (NY, NJ, CT, and MA). |
| Business Overview | exec.claim.002 | Elder Care provides home health aide, live-in, and nursing services to elderly patients. |
| Business Overview | exec.claim.003 | The company generates revenue by billing private-pay clients for caregiver hours delivered. |
| Business Overview | exec.claim.004 | Elder Care had approximately 352 active clients as of Q2 2025. |
| Business Overview | exec.claim.005 | Elder Care had 2,123 registered caregivers across markets including NYC, Long Island, Westchester, NJ, MA, and CT as of Q2 2025. |
| Business Overview | exec.claim.006 | The platform has grown both organically and through acquisition. |
| Business Overview | exec.claim.007 | The platform completed at least two transactions — Guided Living and Unicity — within the recent historical window. |
| Business Overview | exec.claim.008 | Elder Care is currently ramping a Connecticut de novo location. |
| Business Overview | exec.claim.009 | Pro Forma Adjusted Revenue reached $46.4M on a TTM Aug-24 basis per the Historical P&L Summary workstream. |
| Financial Picture | exec.claim.010 | Revenue grew from $8,955K in 2020A to $46,423K TTM Aug-24. |
| Financial Picture | exec.claim.011 | Pro Forma Adjusted EBITDA was $9,239K representing a 19.9% margin on a pro forma basis. |
| Financial Picture | exec.claim.012 | Reported (pre-addback) EBITDA margin is approximately 7.9%, below the ~10% healthcare services threshold. |
| Financial Picture | exec.claim.013 | The addback schedule contains 17 discrete Tier 4 items totaling approximately $7.3M in gross adjustments against a reported EBITDA base of roughly $7.7M. |
| Financial Picture | exec.claim.014 | Gross addbacks represent approximately 247% of reported EBITDA. |
| Financial Picture | exec.claim.015 | Every addback item has been classified Tier 4 because no supporting documents are referenced in the addback schedule within the VDR. |
| Financial Picture | exec.claim.016 | Run-rate executive compensation addback is $2,490K. |
| Financial Picture | exec.claim.017 | Unicity pre-acquisition results addback is $1,077K. |
| Financial Picture | exec.claim.018 | Unicity synergies addback is $909K. |
| Financial Picture | exec.claim.019 | Cash-to-accrual revenue adjustment addback is $665K. |
| Financial Picture | exec.claim.020 | Guided Living ramp-up adjustment addback is $430K. |
| Financial Picture | exec.claim.021 | Each of the five largest individual addbacks individually exceeds 5% of reported EBITDA. |
| Financial Picture | exec.claim.022 | The five largest addbacks include forward-looking pro forma synergies and pre-close acquisition earnings that have not been validated against audited standalone financials or demonstrated post-close performance. |
| Financial Picture | exec.claim.023 | The reconciliation workstream flagged one mismatch and was unable to verify nine items. |
| Financial Picture | exec.claim.024 | If even a portion of these addbacks are rejected in a buyer QofE, the defensible EBITDA base could approach zero or turn negative, fundamentally altering valuation and leverage capacity. |
| Financial Picture | exec.claim.025 | The forecast projects revenue growing from $47.2M (2024E) to $197.8M (2029P) — a 4.2x increase. |
| Financial Picture | exec.claim.026 | Forecast revenue growth is driven by organic growth, the Connecticut de novo ramp, and additional expansion. |
| Financial Picture | exec.claim.027 | The Forecast workstream rates the five-year revenue trajectory Red given aggressive assumptions embedded in that trajectory. |
| Top Risks | exec.claim.028 | The diligence process has surfaced several critical and material issues across workstreams. |
| Top Risks | exec.claim.029 | The company received adverse NYSDOH survey citations in May 2023 related to HCR Profile maintenance, background-check consent procedures, and Home Care Registry credentialing timelines. |
| Top Risks | exec.claim.030 | Written DOH confirmation of closure of the May 2023 NYSDOH citations has not been confirmed. |
| Top Risks | exec.claim.031 | Corrective action plans and the absence of ongoing monitoring obligations for the NYSDOH citations have not been confirmed. |
| Top Risks | exec.claim.032 | Verification that no agreements exist with OIG/SAM-excluded individuals or entities has not been cleared. |
| Top Risks | exec.claim.033 | Potential False Claims Act exposure from OIG/SAM exclusion screening has not been cleared. |
| Top Risks | exec.claim.034 | The addback stack's composition — including speculative forward synergies and unaudited pre-close acquisition earnings — represents the single most consequential open item for price and structure. |
| Top Risks | exec.claim.035 | Outside counsel was retained as recently as April 30, 2025 to pursue collection of patient receivables. |
| Top Risks | exec.claim.036 | Patient receivables collection activity raises questions about billing integrity and working capital quality. |
| Top Risks | exec.claim.037 | Material customer contracts contain termination-for-convenience provisions whose interaction with a change-of-control has not been confirmed. |
| Top Risks | exec.claim.038 | Two identified clients show significant multi-year billing declines whose treatment in the run-rate revenue base has not been clarified. |
| Top Risks | exec.claim.039 | The Manhattan office lease contains an anti-assignment covenant that may require landlord consent as a closing condition. |
| Top Risks | exec.claim.040 | Unusual indemnity provisions appear across multiple contracts including the Unicity Asset Purchase Agreement. |
| Confidence | exec.claim.041 | Overall analytical confidence across all seven workstreams is rated Medium. |
| Confidence | exec.claim.042 | Five of seven workstreams carry a Red rating (Financial Trends, KPI, Legal Contracts, Quality of Earnings, and Forecast). |
| Confidence | exec.claim.043 | Two workstreams are rated Yellow (Business Model, Customer Quality). |
| Confidence | exec.claim.044 | Open item 1: seller-provided audited or third-party-verified support is required for each of the 17 Tier 4 addbacks, with particular focus on the five items individually exceeding 5% of EBITDA. |
| Confidence | exec.claim.045 | Open item 2: written DOH confirmation of regulatory citation closure and a completed OIG/SAM exclusion screening for all employees, contractors, and vendors are required. |
| Confidence | exec.claim.046 | Open item 3: quantification and aging of receivables in active legal collection are required. |
| Confidence | exec.claim.047 | Open item 4: confirmation is required of whether material customer contracts contain change-of-control triggers. |
| Confidence | exec.claim.048 | Open item 5: location-level P&L and operational KPIs for Guided Living, Unicity, ECHC, and the Connecticut de novo are required to validate the entity-level EBITDA build-up. |
| Confidence | exec.claim.049 | The Legal Contracts workstream should engage outside counsel to confirm whether the Manhattan lease anti-assignment provision applies to the contemplated transaction structure. |

---

## 2. Claim enumeration — `fta_numeric` (DG-19 generalization)

**Source artifact:** `uc13_ale.analysis.financial_trends` (latest Elder Care row) — numeric fields with `source_doc` / `source_location` provenance.

**Source query (verbatim):**

```sql
SELECT * FROM uc13_ale.analysis.financial_trends WHERE company_name = 'Elder Care' ORDER BY created_at DESC LIMIT 1;
```

**Listing evidence:** T2 item-23 probe session (`.dev/plans/eval-consolidation-m2-s2-preplan-assessments/t2_fta_probe.py`) enumerated **276** numeric claims; full per-claim record in `.dev/plans/eval-consolidation-m2-s2-preplan-assessments/t2_fta_probe_report.json` (`numeric_claim_count: 276`). Claim IDs below use stable `fta.claim.NNN` keys aligned to that probe ordering.

| claim_id | claim_text | source_doc | source_location |
| --- | --- | --- | --- |
| fta.claim.001 | revenue_stated: 8,955 | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.002 | revenue_stated: 14,176 | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.003 | yoy_growth_pct: 58.3% | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.004 | revenue_stated: 20,846 | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.005 | yoy_growth_pct: 47.1% | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.006 | revenue_stated: 33,700 | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.007 | yoy_growth_pct: 61.7% | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.008 | revenue_stated: 44,735 | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.009 | revenue_stated: 47,198 | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.010 | yoy_growth_pct: 30.2% | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.011 | revenue_stated: 8,955 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.012 | revenue_stated: 14,176 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.013 | yoy_growth_pct: 58.3% | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.014 | revenue_stated: 20,846 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.015 | yoy_growth_pct: 47.1% | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.016 | revenue_stated: 34,160 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.017 | yoy_growth_pct: 63.9% | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.018 | revenue_stated: 46,423 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.019 | yoy_growth_pct: 35.9% | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.020 | revenue_stated: 28,330 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.021 | gm_dollars_stated: 3,770 | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.022 | gm_pct_stated: 42.1% | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.023 | computed_from_stated: False | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.024 | gm_dollars_stated: 6,285 | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.025 | gm_pct_stated: 44.3% | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.026 | gm_dollars_stated: 9,176 | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.027 | gm_pct_stated: 44.0% | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.028 | gm_dollars_stated: 14,361 | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.029 | gm_pct_stated: 42.6% | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.030 | gm_dollars_stated: 18,529 | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.031 | gm_pct_stated: 41.4% | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.032 | gm_dollars_stated: 19,663 | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.033 | gm_pct_stated: 41.7% | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.034 | gm_dollars_stated: 3,770 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.035 | gm_pct_stated: 42.1% | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.036 | computed_from_stated: False | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.037 | gm_dollars_stated: 6,285 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.038 | gm_pct_stated: 44.3% | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.039 | gm_dollars_stated: 9,176 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.040 | gm_pct_stated: 44.0% | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.041 | gm_dollars_stated: 14,910 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.042 | gm_pct_stated: 43.6% | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.043 | gm_dollars_stated: 20,170 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.044 | gm_pct_stated: 43.4% | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.045 | gm_dollars_stated: 91 | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement – Connecticut, Page 54 |
| fta.claim.046 | gm_pct_stated: 45.6% | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement – Connecticut, Page 54 |
| fta.claim.047 | computed_from_stated: False | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement – Connecticut, Page 54 |
| fta.claim.048 | ebitda_dollars: (342) | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.049 | ebitda_margin_pct: -3.8% | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.050 | ebitda_dollars: 720 | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.051 | ebitda_margin_pct: 5.1% | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.052 | ebitda_dollars: 180 | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.053 | ebitda_margin_pct: 0.9% | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.054 | ebitda_dollars: (870) | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.055 | ebitda_margin_pct: -3.1% | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.056 | ebitda_dollars: 2,773 | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.057 | ebitda_margin_pct: 7.9% | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.058 | ebitda_dollars: 2,104 | 2024 Elder Care - CIM_vF.pdf | Diligence Adjusted Income Statement |
| fta.claim.059 | ebitda_margin_pct: 23.5% | 2024 Elder Care - CIM_vF.pdf | Diligence Adjusted Income Statement |
| fta.claim.060 | ebitda_dollars: 3,157 | 2024 Elder Care - CIM_vF.pdf | Diligence Adjusted Income Statement |
| fta.claim.061 | ebitda_margin_pct: 22.3% | 2024 Elder Care - CIM_vF.pdf | Diligence Adjusted Income Statement |
| fta.claim.062 | ebitda_dollars: 4,016 | 2024 Elder Care - CIM_vF.pdf | Diligence Adjusted Income Statement |
| fta.claim.063 | ebitda_margin_pct: 19.3% | 2024 Elder Care - CIM_vF.pdf | Diligence Adjusted Income Statement |
| fta.claim.064 | ebitda_dollars: 6,677 | 2024 Elder Care - CIM_vF.pdf | Diligence Adjusted Income Statement |
| fta.claim.065 | ebitda_margin_pct: 19.5% | 2024 Elder Care - CIM_vF.pdf | Diligence Adjusted Income Statement |
| fta.claim.066 | ebitda_dollars: 9,239 | 2024 Elder Care - CIM_vF.pdf | Diligence Adjusted Income Statement |
| fta.claim.067 | ebitda_margin_pct: 19.9% | 2024 Elder Care - CIM_vF.pdf | Diligence Adjusted Income Statement |
| fta.claim.068 | ebitda_dollars: 3,277 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary |
| fta.claim.069 | ebitda_margin_pct: 36.6% | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary |
| fta.claim.070 | ebitda_dollars: 4,739 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary |
| fta.claim.071 | ebitda_margin_pct: 33.4% | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary |
| fta.claim.072 | ebitda_dollars: 6,545 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary |
| fta.claim.073 | ebitda_margin_pct: 31.4% | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary |
| fta.claim.074 | ebitda_dollars: 10,354 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary |
| fta.claim.075 | ebitda_margin_pct: 30.3% | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary |
| fta.claim.076 | ebitda_dollars: 13,942 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary |
| fta.claim.077 | ebitda_margin_pct: 30.0% | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary |
| fta.claim.078 | revenue_dollars: 1,525 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.079 | revenue_dollars: 4,517 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.080 | revenue_dollars: 10,496 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.081 | revenue_dollars: 12,972 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.082 | revenue_dollars: 13,588 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.083 | revenue_dollars: 7,042 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.084 | revenue_dollars: 7,990 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.085 | revenue_dollars: 7,524 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.086 | revenue_dollars: 8,200 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.087 | revenue_dollars: 8,759 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.088 | revenue_dollars: 229 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.089 | revenue_dollars: 1,644 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.090 | revenue_dollars: 2,815 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.091 | revenue_dollars: 8,837 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.092 | revenue_dollars: 11,644 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.093 | revenue_dollars: 8,796 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.094 | revenue_dollars: 14,151 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.095 | revenue_dollars: 20,835 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.096 | revenue_dollars: 30,009 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.097 | revenue_dollars: 33,991 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.098 | revenue_dollars: 200 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.099 | revenue_dollars: 600 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.100 | revenue_dollars: 2,523 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.101 | revenue_dollars: 7,569 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.102 | revenue_dollars: 1,417 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.103 | revenue_dollars: 4,250 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.104 | revenue_dollars: 160 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.105 | revenue_dollars: 25 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.106 | revenue_dollars: 10 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.107 | revenue_dollars: 11 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.108 | revenue_dollars: 13 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.109 | amount_stated: (0) | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.110 | amount_stated: 182 | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.111 | amount_stated: 53 | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.112 | amount_stated: 665 | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.113 | amount_stated: (158) | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.114 | amount_stated: (33) | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.115 | amount_stated: 2,490 | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.116 | amount_stated: 94 | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.117 | amount_stated: 189 | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.118 | amount_stated: 377 | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.119 | amount_stated: 1,077 | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.120 | amount_stated: 0 | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.121 | amount_stated: 430 | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.122 | amount_stated: 909 | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.123 | amount_stated: 190 | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.124 | amount_stated: 4,251 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Corporate Operating Expenses Section |
| fta.claim.125 | amount_stated: 909 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Corporate Operating Expenses Section |
| fta.claim.126 | amount_stated: 688 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Corporate Operating Expenses Section |
| fta.claim.127 | amount_stated: 5,109 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Clinic-Level Operating Expenses Section |
| fta.claim.128 | amount_stated: 242 + 62 + 113 + 128 + 20 + 72 + 86 + 497 = multiple line items; see source | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Clinic-Level Operating Expenses Section and Corporate Operating Expenses Section |
| fta.claim.129 | [0].revenue_stated: 8,955 | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.130 | [1].revenue_stated: 14,176 | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.131 | [1].yoy_growth_pct: 58.3% | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.132 | [2].revenue_stated: 20,846 | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.133 | [2].yoy_growth_pct: 47.1% | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.134 | [3].revenue_stated: 33,700 | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.135 | [3].yoy_growth_pct: 61.7% | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.136 | [4].revenue_stated: 44,735 | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.137 | [5].revenue_stated: 47,198 | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.138 | [5].yoy_growth_pct: 30.2% | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.139 | [6].revenue_stated: 8,955 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.140 | [7].revenue_stated: 14,176 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.141 | [7].yoy_growth_pct: 58.3% | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.142 | [8].revenue_stated: 20,846 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.143 | [8].yoy_growth_pct: 47.1% | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.144 | [9].revenue_stated: 34,160 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.145 | [9].yoy_growth_pct: 63.9% | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.146 | [10].revenue_stated: 46,423 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.147 | [10].yoy_growth_pct: 35.9% | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.148 | [11].revenue_stated: 28,330 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.149 | [0].gm_dollars_stated: 3,770 | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.150 | [0].gm_pct_stated: 42.1% | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.151 | [0].computed_from_stated: False | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.152 | [1].gm_dollars_stated: 6,285 | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.153 | [1].gm_pct_stated: 44.3% | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.154 | [1].computed_from_stated: False | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.155 | [2].gm_dollars_stated: 9,176 | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.156 | [2].gm_pct_stated: 44.0% | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.157 | [2].computed_from_stated: False | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.158 | [3].gm_dollars_stated: 14,361 | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.159 | [3].gm_pct_stated: 42.6% | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.160 | [3].computed_from_stated: False | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.161 | [4].gm_dollars_stated: 18,529 | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.162 | [4].gm_pct_stated: 41.4% | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.163 | [4].computed_from_stated: False | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.164 | [5].gm_dollars_stated: 19,663 | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.165 | [5].gm_pct_stated: 41.7% | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.166 | [5].computed_from_stated: False | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement & Projection |
| fta.claim.167 | [6].gm_dollars_stated: 3,770 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.168 | [6].gm_pct_stated: 42.1% | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.169 | [6].computed_from_stated: False | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.170 | [7].gm_dollars_stated: 6,285 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.171 | [7].gm_pct_stated: 44.3% | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.172 | [7].computed_from_stated: False | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.173 | [8].gm_dollars_stated: 9,176 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.174 | [8].gm_pct_stated: 44.0% | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.175 | [8].computed_from_stated: False | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.176 | [9].gm_dollars_stated: 14,910 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.177 | [9].gm_pct_stated: 43.6% | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.178 | [9].computed_from_stated: False | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.179 | [10].gm_dollars_stated: 20,170 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.180 | [10].gm_pct_stated: 43.4% | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.181 | [10].computed_from_stated: False | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Page 49 |
| fta.claim.182 | [11].gm_dollars_stated: 91 | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement – Connecticut, Page 54 |
| fta.claim.183 | [11].gm_pct_stated: 45.6% | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement – Connecticut, Page 54 |
| fta.claim.184 | [11].computed_from_stated: False | 2024 Elder Care - CIM_vF.pdf | Pro Forma Income Statement – Connecticut, Page 54 |
| fta.claim.185 | [0].ebitda_dollars: (342) | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.186 | [0].ebitda_margin_pct: -3.8% | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.187 | [1].ebitda_dollars: 720 | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.188 | [1].ebitda_margin_pct: 5.1% | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.189 | [2].ebitda_dollars: 180 | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.190 | [2].ebitda_margin_pct: 0.9% | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.191 | [3].ebitda_dollars: (870) | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.192 | [3].ebitda_margin_pct: -3.1% | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.193 | [4].ebitda_dollars: 2,773 | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.194 | [4].ebitda_margin_pct: 7.9% | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.195 | [5].ebitda_dollars: 2,104 | 2024 Elder Care - CIM_vF.pdf | Diligence Adjusted Income Statement |
| fta.claim.196 | [5].ebitda_margin_pct: 23.5% | 2024 Elder Care - CIM_vF.pdf | Diligence Adjusted Income Statement |
| fta.claim.197 | [6].ebitda_dollars: 3,157 | 2024 Elder Care - CIM_vF.pdf | Diligence Adjusted Income Statement |
| fta.claim.198 | [6].ebitda_margin_pct: 22.3% | 2024 Elder Care - CIM_vF.pdf | Diligence Adjusted Income Statement |
| fta.claim.199 | [7].ebitda_dollars: 4,016 | 2024 Elder Care - CIM_vF.pdf | Diligence Adjusted Income Statement |
| fta.claim.200 | [7].ebitda_margin_pct: 19.3% | 2024 Elder Care - CIM_vF.pdf | Diligence Adjusted Income Statement |
| fta.claim.201 | [8].ebitda_dollars: 6,677 | 2024 Elder Care - CIM_vF.pdf | Diligence Adjusted Income Statement |
| fta.claim.202 | [8].ebitda_margin_pct: 19.5% | 2024 Elder Care - CIM_vF.pdf | Diligence Adjusted Income Statement |
| fta.claim.203 | [9].ebitda_dollars: 9,239 | 2024 Elder Care - CIM_vF.pdf | Diligence Adjusted Income Statement |
| fta.claim.204 | [9].ebitda_margin_pct: 19.9% | 2024 Elder Care - CIM_vF.pdf | Diligence Adjusted Income Statement |
| fta.claim.205 | [10].ebitda_dollars: 3,277 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary |
| fta.claim.206 | [10].ebitda_margin_pct: 36.6% | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary |
| fta.claim.207 | [11].ebitda_dollars: 4,739 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary |
| fta.claim.208 | [11].ebitda_margin_pct: 33.4% | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary |
| fta.claim.209 | [12].ebitda_dollars: 6,545 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary |
| fta.claim.210 | [12].ebitda_margin_pct: 31.4% | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary |
| fta.claim.211 | [13].ebitda_dollars: 10,354 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary |
| fta.claim.212 | [13].ebitda_margin_pct: 30.3% | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary |
| fta.claim.213 | [14].ebitda_dollars: 13,942 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary |
| fta.claim.214 | [14].ebitda_margin_pct: 30.0% | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary |
| fta.claim.215 | [0].revenue_dollars: 1,525 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.216 | [1].revenue_dollars: 4,517 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.217 | [2].revenue_dollars: 10,496 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.218 | [3].revenue_dollars: 12,972 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.219 | [4].revenue_dollars: 13,588 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.220 | [5].revenue_dollars: 7,042 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.221 | [6].revenue_dollars: 7,990 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.222 | [7].revenue_dollars: 7,524 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.223 | [8].revenue_dollars: 8,200 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.224 | [9].revenue_dollars: 8,759 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.225 | [10].revenue_dollars: 229 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.226 | [11].revenue_dollars: 1,644 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.227 | [12].revenue_dollars: 2,815 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.228 | [13].revenue_dollars: 8,837 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.229 | [14].revenue_dollars: 11,644 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.230 | [15].revenue_dollars: 8,796 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.231 | [16].revenue_dollars: 14,151 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.232 | [17].revenue_dollars: 20,835 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.233 | [18].revenue_dollars: 30,009 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.234 | [19].revenue_dollars: 33,991 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.235 | [20].revenue_dollars: 7,042 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.236 | [21].revenue_dollars: 7,990 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.237 | [22].revenue_dollars: 7,524 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.238 | [23].revenue_dollars: 8,200 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.239 | [24].revenue_dollars: 8,759 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.240 | [25].revenue_dollars: 200 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.241 | [26].revenue_dollars: 600 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.242 | [27].revenue_dollars: 2,523 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.243 | [28].revenue_dollars: 7,569 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.244 | [29].revenue_dollars: 1,417 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.245 | [30].revenue_dollars: 4,250 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.246 | [31].revenue_dollars: 229 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.247 | [32].revenue_dollars: 1,644 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.248 | [33].revenue_dollars: 2,815 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.249 | [34].revenue_dollars: 8,837 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.250 | [35].revenue_dollars: 11,644 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.251 | [36].revenue_dollars: 160 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.252 | [37].revenue_dollars: 25 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.253 | [38].revenue_dollars: 10 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.254 | [39].revenue_dollars: 11 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.255 | [40].revenue_dollars: 13 | 2024 Elder Care - CIM_vF.pdf |  |
| fta.claim.256 | [0].amount_stated: (0) | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.257 | [1].amount_stated: 182 | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.258 | [2].amount_stated: 53 | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.259 | [3].amount_stated: 665 | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.260 | [4].amount_stated: (158) | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.261 | [5].amount_stated: (33) | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.262 | [6].amount_stated: 2,490 | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.263 | [7].amount_stated: 94 | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.264 | [8].amount_stated: 189 | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.265 | [9].amount_stated: 377 | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.266 | [10].amount_stated: 1,077 | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.267 | [11].amount_stated: 0 | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.268 | [12].amount_stated: 0 | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.269 | [13].amount_stated: 430 | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.270 | [14].amount_stated: 909 | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.271 | [15].amount_stated: 190 | 2024 Elder Care - CIM_vF.pdf | EBITDA Adjustment Detail |
| fta.claim.272 | [0].amount_stated: 4,251 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Corporate Operating Expenses Section |
| fta.claim.273 | [1].amount_stated: 909 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Corporate Operating Expenses Section |
| fta.claim.274 | [2].amount_stated: 688 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Corporate Operating Expenses Section |
| fta.claim.275 | [3].amount_stated: 5,109 | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Clinic-Level Operating Expenses Section |
| fta.claim.276 | [4].amount_stated: 242 + 62 + 113 + 128 + 20 + 72 + 86 + 497 = multiple line items; see source | 2024 Elder Care - CIM_vF.pdf | Historical P&L Summary, Clinic-Level Operating Expenses Section and Corporate Operating Expenses Section |

---

## 3. Spot-check procedure

For each claim in the surface enumeration:

1. **Locate evidence** — retrieve the cited source material (`executive_summary` prose maps to underlying workstream outputs and VDR documents; FTA claims cite `source_doc` + `source_location` in the CIM).
2. **Judge disposition** — assign exactly one verdict from the §16 claim-verdict vocabulary:
   - `supported` — evidence substantiates the claim as stated.
   - `contradicted` — evidence refutes the claim or material numeric/text mismatch exists.
   - `unsupported` — evidence is absent, unlocatable, or insufficient to substantiate or refute.
3. **Record rationale** (recommended) — brief operator note when verdict is `contradicted` or `unsupported`, naming what was checked and why it failed.

**Pass/fail partition (§16, uniform across rungs):** `supported` passes; `contradicted` and `unsupported` are per-claim failures (`claim_failures`). Surface attestation derives from the run: any failure ⇒ `partial` with scored/failed counts; all pass ⇒ `attested`.

**Whole-surface rule (HALT-15):** the operator must verdict **every** enumerated claim in one session. Partial enumeration is not a valid rung-3 attestation.

---

## 4. Write-path contract (logical field set — §8.8 / §12.1 rung 3)

A completed spot-check lands in the S2 score table as a **marker-complete run** at **per-claim grain**:

| Row class | Logical fields (no physical column names — M3 S2 charter pins DDL) |
|-----------|---------------------------------------------------------------------|
| **`claim` row** | `company`, `surface`, `run_id`, `run_ts`, `row_type: claim`, `claim_id`, `verdict` ∈ {`supported`, `contradicted`, `unsupported`}, `rationale` (operator prose, rungs 2–3) |
| **`completion_marker` row** | Same run keys, `row_type: completion_marker`, `writer: human_spot_check`, all claim columns null |

**Completion semantics (§9):** claim rows may be written incrementally; the completion marker is written **last**. Readers serve only marker-complete runs; the latest marker-complete run supersedes prior runs for the surface entirely.

**Writer membership (§16, M-27):** the write path validates `writer: human_spot_check` membership in the closed §16 `writer` vocabulary — fail-closed at write, same check as items 24/27.

**Rung derivation (§12.2):** `rung: human` is derivable from `writer: human_spot_check` on the completion marker.

**Numeric-surface note:** on `fta_numeric` at rung 3 the human writes `verdict` directly (non-numeric rung-3 path). The numeric hardening fields (`asserted_value`, `extracted_value`, `cited_span`) are rung-2-only per §8.8 and are **not** required on human spot-check rows.

**Zero-claim rule (§16):** a marker-complete run with zero claim rows ⇒ `not_attested` + `reason: zero_claim_run` — unreachable when this rubric is followed.

---

## 5. Surface scope statement

| Surface | In scope | Rung assignment source |
|---------|----------|------------------------|
| `exec_summary` | Yes — §17 item 26 MVP scope | CHK-26a: `human` |
| `fta_numeric` | Yes — DG-19 generalization (demoted surface + calibration failure) | CHK-26a: `human` |
| `legal_register` | **No** — item 23a go path; rung `deterministic` | CHK-23a |

