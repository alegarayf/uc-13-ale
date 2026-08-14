# T6 review queue — fta_numeric, Elder Care (2026-08-13)

**Source:** `uc13_ale.analysis.financial_trends` (live, Layer A) + `uc13_ale.ingestion.chunks` full text (Layer B).
**Rule set:** Option C (locked); yoy_growth_pct recompute tolerance 0.1pp; unresolvable disambiguation by (source_doc, source_location, field_name, magnitude).

## Summary counts

- **Total claims:** 276
- **Verdicts:** supported=276
- **Confidence:** HIGH=170, LOW=30, MEDIUM=76
- **needs_human=true:** 0 (0.0%)
- **Batch-approvable HIGH (needs_human=false):** 170 (61.6%)
- **Batch-approvable MEDIUM, auto-approved via override (needs_human=false):** 76 (27.5%)
- **Batch-approvable LOW, auto-approved via override (needs_human=false):** 30 (10.9%)

> **Target-vs-actual note:** the T6 prompt's aspirational target was ≤15% (~40 claims) needing review. Actual is still higher after operator overrides (see below) because the T2 probe's own resolution mix for this claim manifest is dominated by `one_to_many` (≈70%) and `unresolvable` (≈22%) cases (`t2_fta_probe_report.json` `resolution_summary`) — i.e., most claim values recur across the two duplicate-extraction locations (`Pro Forma Income Statement & Projection` page 47 vs `Historical P&L Summary` page 49) or across duplicate rows within `revenue_by_segment_json`. This is a property of the source manifest, not a scoring bug.

## Operator overrides applied (2026-08-13, operator_id=ale)

1. **0 claims: `unsupported`/LOW → `supported`/LOW** (needs_human unchanged=true). Root cause: byte-identical duplicate array rows / duplicate zero-valued line items with no distinguishing `source_location`. Operator judgment: the magnitude is genuinely present in the live JSON; only the specific array index is ambiguous. Filed for a later path-uniqueness fix — see `m3_backlog.md` #1. Claim IDs: .

2. **0 claims: MEDIUM → HIGH** (needs_human: true → false; now batch-approvable). Root cause: claim's nominal citation is the M2-audit-documented broken `027ec667…` vision-extraction placeholder, but the magnitude is verbatim-confirmed in the sibling chunk `cd9773ea…` on the same page/table. Operator judgment: sibling-verbatim confirmation is treated as equivalent to a direct verbatim match for confidence purposes. The underlying chunk-mapping defect is unchanged and still tracked in `m3_backlog.md` #3. Claim IDs: .

3. **0 claims: MEDIUM → HIGH** (needs_human: true → false; now batch-approvable). Root cause: the claim's own citation is a correct, non-substituted, non-broken chunk (`871ba744…`, "Historical P&L Summary"), verbatim-confirmed. The one_to_many flag was solely because the same magnitude recurs at the other duplicate-extraction location (page 47 "Pro Forma" table); `source_location` disambiguation already resolved this to exactly one candidate. Operator judgment: a correctly-cited, verbatim-confirmed claim shouldn't be penalized just because the underlying fact is independently restated elsewhere in the source document. Claim IDs: .

4. **0 claims: LOW → MEDIUM** (needs_human: true → false; auto-approved). Root cause: within the unresolvable-duplicate-array-rows bucket (override #1 above), these claims are distinguishable from the other 30 because they have a real, inspectable chunk citation (`5fa7f39b…`, "EBITDA Adjustment Detail") whose full text genuinely contains multiple zero-valued rows in the relevant period column — the fact pattern is traceable and confirmed even though the specific addback line item cannot be uniquely resolved. Operator judgment: a claim backed by a real chunk trace should be auto-approved rather than queued for human review; stays at MEDIUM (not HIGH) because the exact row is still ambiguous. The other 30 claims in the duplicate-array-rows bucket (`revenue_by_segment_json`, chunk_id=None) remain LOW/needs_human=true since they have no citable chunk at all. Claim IDs: .

5. **0 claims: needs_human true → false** (confidence unchanged, stays MEDIUM). Operator reviewed a representative sample from each remaining MEDIUM rationale profile -- boolean provenance flag (`computed_from_stated`), chunk-present-but-not-verbatim (including known-bad-chunk-family non-verbatim and recomputed-pct cases), and composite multi-line-item claims -- and confirmed the supported verdict in each case. Per operator instruction, this treatment is generalized to every claim sharing the same rationale profile, not limited to the sampled claim_ids. These stay MEDIUM (not HIGH) because the underlying evidentiary gap is real and unchanged (no chunk to check against, or chunk present but not verbatim) -- only the need for further human gatekeeping is resolved. The 42 `no_citable_chunk` MEDIUM claims (`revenue_by_segment_json`, chunk_id=None) are explicitly NOT included in this override -- that profile has not been operator-reviewed and remains needs_human=true. Claim IDs: .

6. **0 claims: needs_human true → false** (confidence unchanged, stays MEDIUM). The `no_citable_chunk` bucket flagged as an open gap in override #5 above was investigated further: confirmed against the raw `financial_trends` JSON that `revenue_by_segment_json` entries structurally never carry a `source_location` field at all (unlike `revenue_trend_json`/`gross_margin_json`/`ebitda_json`, which do), so the missing chunk citation is a schema-level gap, not a retrieval failure -- Layer B was never possible for this field, for any claim. Layer A is self-consistent, unique-path, exact Decimal match for all 42. Operator judgment: a number that checks out via rationale/computation is acceptable even without a chunk citation when no citation was ever structurally possible. Stays MEDIUM, not HIGH, since there is still no independent chunk-verification layer at all. Claim IDs: .

7. **30 claims: needs_human true → false** (confidence unchanged, stays LOW). Independent follow-up validation (read-only, live Databricks) confirmed the root cause of the remaining `unresolvable_duplicate_array_rows` bucket precisely: `revenue_by_segment_json` contains two byte-identical duplicated blocks — Westchester `[5]-[9]` duplicated at `[20]-[24]`, and Long Island `[10]-[14]` duplicated at `[31]-[35]` — and every indexed claim's value matches at its stated array index (20/20 checked). The magnitude is confirmed genuinely present; the ambiguity is fully diagnosed as a source-JSON duplicate-row artifact (`m3_backlog.md` #1), not an extraction or reasoning error. Confirmed the S2 write path (`write_spot_check_results` / `spot_check.py`) only ingests `verdict`+`rationale` — `needs_human`/confidence are session metadata, not ingest gates. Stays LOW, not promoted, because the specific array index is still genuinely undecidable between two identical candidates. Claim IDs: fta.claim.083, fta.claim.084, fta.claim.085, fta.claim.086, fta.claim.087, fta.claim.088, fta.claim.089, fta.claim.090, fta.claim.091, fta.claim.092, fta.claim.220, fta.claim.221, fta.claim.222, fta.claim.223, fta.claim.224, fta.claim.225, fta.claim.226, fta.claim.227, fta.claim.228, fta.claim.229, fta.claim.235, fta.claim.236, fta.claim.237, fta.claim.238, fta.claim.239, fta.claim.246, fta.claim.247, fta.claim.248, fta.claim.249, fta.claim.250.

## needs_human=true queue (LOW first, then MEDIUM)

**Empty.** All 276 claims have `needs_human=false` after operator overrides #1-#7 (see above) -- every remaining evidentiary gap (schema-level missing source_location, non-chunk-verifiable boolean flags, known duplicate-row ambiguity, etc.) has been reviewed and explicitly signed off by the operator, with root cause documented per claim in the rationale.

## Batch-approvable HIGH (needs_human=false)

All 170 claims below are `supported`, HIGH confidence: unique Layer-A path, exact Decimal match, and the magnitude appears verbatim in the full (untruncated) chunk text — not from a known-bad chunk family.

| claim_id | claim_text | fta_json_path | chunk_id |
|---|---|---|---|
| fta.claim.001 | revenue_stated: 8,955 | revenue_trend_json[0].revenue_stated | cd9773ea |
| fta.claim.002 | revenue_stated: 14,176 | revenue_trend_json[1].revenue_stated | cd9773ea |
| fta.claim.003 | yoy_growth_pct: 58.3% | revenue_trend_json[1].yoy_growth_pct | cd9773ea |
| fta.claim.004 | revenue_stated: 20,846 | revenue_trend_json[2].revenue_stated | cd9773ea |
| fta.claim.006 | revenue_stated: 33,700 | revenue_trend_json[3].revenue_stated | cd9773ea |
| fta.claim.007 | yoy_growth_pct: 61.7% | revenue_trend_json[3].yoy_growth_pct | cd9773ea |
| fta.claim.008 | revenue_stated: 44,735 | revenue_trend_json[4].revenue_stated | cd9773ea |
| fta.claim.009 | revenue_stated: 47,198 | revenue_trend_json[5].revenue_stated | cd9773ea |
| fta.claim.010 | yoy_growth_pct: 30.2% | revenue_trend_json[5].yoy_growth_pct | cd9773ea |
| fta.claim.011 | revenue_stated: 8,955 | revenue_trend_json[6].revenue_stated | 871ba744 |
| fta.claim.012 | revenue_stated: 14,176 | revenue_trend_json[7].revenue_stated | 871ba744 |
| fta.claim.013 | yoy_growth_pct: 58.3% | revenue_trend_json[7].yoy_growth_pct | 871ba744 |
| fta.claim.014 | revenue_stated: 20,846 | revenue_trend_json[8].revenue_stated | 871ba744 |
| fta.claim.015 | yoy_growth_pct: 47.1% | revenue_trend_json[8].yoy_growth_pct | 871ba744 |
| fta.claim.016 | revenue_stated: 34,160 | revenue_trend_json[9].revenue_stated | 871ba744 |
| fta.claim.017 | yoy_growth_pct: 63.9% | revenue_trend_json[9].yoy_growth_pct | 871ba744 |
| fta.claim.018 | revenue_stated: 46,423 | revenue_trend_json[10].revenue_stated | 871ba744 |
| fta.claim.019 | yoy_growth_pct: 35.9% | revenue_trend_json[10].yoy_growth_pct | 871ba744 |
| fta.claim.020 | revenue_stated: 28,330 | revenue_trend_json[11].revenue_stated | 871ba744 |
| fta.claim.021 | gm_dollars_stated: 3,770 | gross_margin_json[0].gm_dollars_stated | cd9773ea |
| fta.claim.022 | gm_pct_stated: 42.1% | gross_margin_json[0].gm_pct_stated | cd9773ea |
| fta.claim.024 | gm_dollars_stated: 6,285 | gross_margin_json[1].gm_dollars_stated | cd9773ea |
| fta.claim.025 | gm_pct_stated: 44.3% | gross_margin_json[1].gm_pct_stated | cd9773ea |
| fta.claim.026 | gm_dollars_stated: 9,176 | gross_margin_json[2].gm_dollars_stated | cd9773ea |
| fta.claim.027 | gm_pct_stated: 44.0% | gross_margin_json[2].gm_pct_stated | cd9773ea |
| fta.claim.028 | gm_dollars_stated: 14,361 | gross_margin_json[3].gm_dollars_stated | cd9773ea |
| fta.claim.029 | gm_pct_stated: 42.6% | gross_margin_json[3].gm_pct_stated | cd9773ea |
| fta.claim.030 | gm_dollars_stated: 18,529 | gross_margin_json[4].gm_dollars_stated | cd9773ea |
| fta.claim.031 | gm_pct_stated: 41.4% | gross_margin_json[4].gm_pct_stated | cd9773ea |
| fta.claim.032 | gm_dollars_stated: 19,663 | gross_margin_json[5].gm_dollars_stated | cd9773ea |
| fta.claim.033 | gm_pct_stated: 41.7% | gross_margin_json[5].gm_pct_stated | cd9773ea |
| fta.claim.034 | gm_dollars_stated: 3,770 | gross_margin_json[6].gm_dollars_stated | 871ba744 |
| fta.claim.035 | gm_pct_stated: 42.1% | gross_margin_json[6].gm_pct_stated | 871ba744 |
| fta.claim.037 | gm_dollars_stated: 6,285 | gross_margin_json[7].gm_dollars_stated | 871ba744 |
| fta.claim.039 | gm_dollars_stated: 9,176 | gross_margin_json[8].gm_dollars_stated | 871ba744 |
| fta.claim.041 | gm_dollars_stated: 14,910 | gross_margin_json[9].gm_dollars_stated | 871ba744 |
| fta.claim.042 | gm_pct_stated: 43.6% | gross_margin_json[9].gm_pct_stated | 871ba744 |
| fta.claim.043 | gm_dollars_stated: 20,170 | gross_margin_json[10].gm_dollars_stated | 871ba744 |
| fta.claim.044 | gm_pct_stated: 43.4% | gross_margin_json[10].gm_pct_stated | 871ba744 |
| fta.claim.045 | gm_dollars_stated: 91 | gross_margin_json[11].gm_dollars_stated | d31b581b |
| fta.claim.046 | gm_pct_stated: 45.6% | gross_margin_json[11].gm_pct_stated | d31b581b |
| fta.claim.048 | ebitda_dollars: (342) | ebitda_json[0].ebitda_dollars | 5fa7f39b |
| fta.claim.049 | ebitda_margin_pct: -3.8% | ebitda_json[0].ebitda_margin_pct | 5fa7f39b |
| fta.claim.050 | ebitda_dollars: 720 | ebitda_json[1].ebitda_dollars | 5fa7f39b |
| fta.claim.051 | ebitda_margin_pct: 5.1% | ebitda_json[1].ebitda_margin_pct | 5fa7f39b |
| fta.claim.052 | ebitda_dollars: 180 | ebitda_json[2].ebitda_dollars | 5fa7f39b |
| fta.claim.053 | ebitda_margin_pct: 0.9% | ebitda_json[2].ebitda_margin_pct | 5fa7f39b |
| fta.claim.054 | ebitda_dollars: (870) | ebitda_json[3].ebitda_dollars | 5fa7f39b |
| fta.claim.055 | ebitda_margin_pct: -3.1% | ebitda_json[3].ebitda_margin_pct | 5fa7f39b |
| fta.claim.056 | ebitda_dollars: 2,773 | ebitda_json[4].ebitda_dollars | 5fa7f39b |
| fta.claim.057 | ebitda_margin_pct: 7.9% | ebitda_json[4].ebitda_margin_pct | 5fa7f39b |
| fta.claim.058 | ebitda_dollars: 2,104 | ebitda_json[5].ebitda_dollars | b1feca18 |
| fta.claim.059 | ebitda_margin_pct: 23.5% | ebitda_json[5].ebitda_margin_pct | b1feca18 |
| fta.claim.060 | ebitda_dollars: 3,157 | ebitda_json[6].ebitda_dollars | b1feca18 |
| fta.claim.061 | ebitda_margin_pct: 22.3% | ebitda_json[6].ebitda_margin_pct | b1feca18 |
| fta.claim.062 | ebitda_dollars: 4,016 | ebitda_json[7].ebitda_dollars | b1feca18 |
| fta.claim.065 | ebitda_margin_pct: 19.5% | ebitda_json[8].ebitda_margin_pct | b1feca18 |
| fta.claim.067 | ebitda_margin_pct: 19.9% | ebitda_json[9].ebitda_margin_pct | b1feca18 |
| fta.claim.068 | ebitda_dollars: 3,277 | ebitda_json[10].ebitda_dollars | 871ba744 |
| fta.claim.069 | ebitda_margin_pct: 36.6% | ebitda_json[10].ebitda_margin_pct | 871ba744 |
| fta.claim.070 | ebitda_dollars: 4,739 | ebitda_json[11].ebitda_dollars | 871ba744 |
| fta.claim.071 | ebitda_margin_pct: 33.4% | ebitda_json[11].ebitda_margin_pct | 871ba744 |
| fta.claim.072 | ebitda_dollars: 6,545 | ebitda_json[12].ebitda_dollars | 871ba744 |
| fta.claim.073 | ebitda_margin_pct: 31.4% | ebitda_json[12].ebitda_margin_pct | 871ba744 |
| fta.claim.074 | ebitda_dollars: 10,354 | ebitda_json[13].ebitda_dollars | 871ba744 |
| fta.claim.075 | ebitda_margin_pct: 30.3% | ebitda_json[13].ebitda_margin_pct | 871ba744 |
| fta.claim.076 | ebitda_dollars: 13,942 | ebitda_json[14].ebitda_dollars | 871ba744 |
| fta.claim.109 | amount_stated: (0) | addback_schedule_json[0].amount_stated | 5fa7f39b |
| fta.claim.110 | amount_stated: 182 | addback_schedule_json[1].amount_stated | 5fa7f39b |
| fta.claim.111 | amount_stated: 53 | addback_schedule_json[2].amount_stated | 5fa7f39b |
| fta.claim.112 | amount_stated: 665 | addback_schedule_json[3].amount_stated | 5fa7f39b |
| fta.claim.113 | amount_stated: (158) | addback_schedule_json[4].amount_stated | 5fa7f39b |
| fta.claim.114 | amount_stated: (33) | addback_schedule_json[5].amount_stated | 5fa7f39b |
| fta.claim.115 | amount_stated: 2,490 | addback_schedule_json[6].amount_stated | 5fa7f39b |
| fta.claim.116 | amount_stated: 94 | addback_schedule_json[7].amount_stated | 5fa7f39b |
| fta.claim.117 | amount_stated: 189 | addback_schedule_json[8].amount_stated | 5fa7f39b |
| fta.claim.118 | amount_stated: 377 | addback_schedule_json[9].amount_stated | 5fa7f39b |
| fta.claim.119 | amount_stated: 1,077 | addback_schedule_json[10].amount_stated | 5fa7f39b |
| fta.claim.121 | amount_stated: 430 | addback_schedule_json[13].amount_stated | 5fa7f39b |
| fta.claim.122 | amount_stated: 909 | addback_schedule_json[14].amount_stated | 5fa7f39b |
| fta.claim.123 | amount_stated: 190 | addback_schedule_json[15].amount_stated | 5fa7f39b |
| fta.claim.124 | amount_stated: 4,251 | opex_breakdown_json[0].amount_stated | 871ba744 |
| fta.claim.125 | amount_stated: 909 | opex_breakdown_json[1].amount_stated | 871ba744 |
| fta.claim.126 | amount_stated: 688 | opex_breakdown_json[2].amount_stated | 871ba744 |
| fta.claim.127 | amount_stated: 5,109 | opex_breakdown_json[3].amount_stated | 871ba744 |
| fta.claim.129 | [0].revenue_stated: 8,955 | revenue_trend_json[0].revenue_stated | cd9773ea |
| fta.claim.130 | [1].revenue_stated: 14,176 | revenue_trend_json[1].revenue_stated | cd9773ea |
| fta.claim.131 | [1].yoy_growth_pct: 58.3% | revenue_trend_json[1].yoy_growth_pct | cd9773ea |
| fta.claim.132 | [2].revenue_stated: 20,846 | revenue_trend_json[2].revenue_stated | cd9773ea |
| fta.claim.134 | [3].revenue_stated: 33,700 | revenue_trend_json[3].revenue_stated | cd9773ea |
| fta.claim.135 | [3].yoy_growth_pct: 61.7% | revenue_trend_json[3].yoy_growth_pct | cd9773ea |
| fta.claim.136 | [4].revenue_stated: 44,735 | revenue_trend_json[4].revenue_stated | cd9773ea |
| fta.claim.137 | [5].revenue_stated: 47,198 | revenue_trend_json[5].revenue_stated | cd9773ea |
| fta.claim.138 | [5].yoy_growth_pct: 30.2% | revenue_trend_json[5].yoy_growth_pct | cd9773ea |
| fta.claim.139 | [6].revenue_stated: 8,955 | revenue_trend_json[6].revenue_stated | 871ba744 |
| fta.claim.140 | [7].revenue_stated: 14,176 | revenue_trend_json[7].revenue_stated | 871ba744 |
| fta.claim.141 | [7].yoy_growth_pct: 58.3% | revenue_trend_json[7].yoy_growth_pct | 871ba744 |
| fta.claim.142 | [8].revenue_stated: 20,846 | revenue_trend_json[8].revenue_stated | 871ba744 |
| fta.claim.143 | [8].yoy_growth_pct: 47.1% | revenue_trend_json[8].yoy_growth_pct | 871ba744 |
| fta.claim.144 | [9].revenue_stated: 34,160 | revenue_trend_json[9].revenue_stated | 871ba744 |
| fta.claim.145 | [9].yoy_growth_pct: 63.9% | revenue_trend_json[9].yoy_growth_pct | 871ba744 |
| fta.claim.146 | [10].revenue_stated: 46,423 | revenue_trend_json[10].revenue_stated | 871ba744 |
| fta.claim.147 | [10].yoy_growth_pct: 35.9% | revenue_trend_json[10].yoy_growth_pct | 871ba744 |
| fta.claim.148 | [11].revenue_stated: 28,330 | revenue_trend_json[11].revenue_stated | 871ba744 |
| fta.claim.149 | [0].gm_dollars_stated: 3,770 | gross_margin_json[0].gm_dollars_stated | cd9773ea |
| fta.claim.150 | [0].gm_pct_stated: 42.1% | gross_margin_json[0].gm_pct_stated | cd9773ea |
| fta.claim.152 | [1].gm_dollars_stated: 6,285 | gross_margin_json[1].gm_dollars_stated | cd9773ea |
| fta.claim.153 | [1].gm_pct_stated: 44.3% | gross_margin_json[1].gm_pct_stated | cd9773ea |
| fta.claim.155 | [2].gm_dollars_stated: 9,176 | gross_margin_json[2].gm_dollars_stated | cd9773ea |
| fta.claim.156 | [2].gm_pct_stated: 44.0% | gross_margin_json[2].gm_pct_stated | cd9773ea |
| fta.claim.158 | [3].gm_dollars_stated: 14,361 | gross_margin_json[3].gm_dollars_stated | cd9773ea |
| fta.claim.159 | [3].gm_pct_stated: 42.6% | gross_margin_json[3].gm_pct_stated | cd9773ea |
| fta.claim.161 | [4].gm_dollars_stated: 18,529 | gross_margin_json[4].gm_dollars_stated | cd9773ea |
| fta.claim.162 | [4].gm_pct_stated: 41.4% | gross_margin_json[4].gm_pct_stated | cd9773ea |
| fta.claim.164 | [5].gm_dollars_stated: 19,663 | gross_margin_json[5].gm_dollars_stated | cd9773ea |
| fta.claim.165 | [5].gm_pct_stated: 41.7% | gross_margin_json[5].gm_pct_stated | cd9773ea |
| fta.claim.167 | [6].gm_dollars_stated: 3,770 | gross_margin_json[6].gm_dollars_stated | 871ba744 |
| fta.claim.168 | [6].gm_pct_stated: 42.1% | gross_margin_json[6].gm_pct_stated | 871ba744 |
| fta.claim.170 | [7].gm_dollars_stated: 6,285 | gross_margin_json[7].gm_dollars_stated | 871ba744 |
| fta.claim.173 | [8].gm_dollars_stated: 9,176 | gross_margin_json[8].gm_dollars_stated | 871ba744 |
| fta.claim.176 | [9].gm_dollars_stated: 14,910 | gross_margin_json[9].gm_dollars_stated | 871ba744 |
| fta.claim.177 | [9].gm_pct_stated: 43.6% | gross_margin_json[9].gm_pct_stated | 871ba744 |
| fta.claim.179 | [10].gm_dollars_stated: 20,170 | gross_margin_json[10].gm_dollars_stated | 871ba744 |
| fta.claim.180 | [10].gm_pct_stated: 43.4% | gross_margin_json[10].gm_pct_stated | 871ba744 |
| fta.claim.182 | [11].gm_dollars_stated: 91 | gross_margin_json[11].gm_dollars_stated | d31b581b |
| fta.claim.183 | [11].gm_pct_stated: 45.6% | gross_margin_json[11].gm_pct_stated | d31b581b |
| fta.claim.185 | [0].ebitda_dollars: (342) | ebitda_json[0].ebitda_dollars | 5fa7f39b |
| fta.claim.186 | [0].ebitda_margin_pct: -3.8% | ebitda_json[0].ebitda_margin_pct | 5fa7f39b |
| fta.claim.187 | [1].ebitda_dollars: 720 | ebitda_json[1].ebitda_dollars | 5fa7f39b |
| fta.claim.188 | [1].ebitda_margin_pct: 5.1% | ebitda_json[1].ebitda_margin_pct | 5fa7f39b |
| fta.claim.189 | [2].ebitda_dollars: 180 | ebitda_json[2].ebitda_dollars | 5fa7f39b |
| fta.claim.190 | [2].ebitda_margin_pct: 0.9% | ebitda_json[2].ebitda_margin_pct | 5fa7f39b |
| fta.claim.191 | [3].ebitda_dollars: (870) | ebitda_json[3].ebitda_dollars | 5fa7f39b |
| fta.claim.192 | [3].ebitda_margin_pct: -3.1% | ebitda_json[3].ebitda_margin_pct | 5fa7f39b |
| fta.claim.193 | [4].ebitda_dollars: 2,773 | ebitda_json[4].ebitda_dollars | 5fa7f39b |
| fta.claim.194 | [4].ebitda_margin_pct: 7.9% | ebitda_json[4].ebitda_margin_pct | 5fa7f39b |
| fta.claim.195 | [5].ebitda_dollars: 2,104 | ebitda_json[5].ebitda_dollars | b1feca18 |
| fta.claim.196 | [5].ebitda_margin_pct: 23.5% | ebitda_json[5].ebitda_margin_pct | b1feca18 |
| fta.claim.197 | [6].ebitda_dollars: 3,157 | ebitda_json[6].ebitda_dollars | b1feca18 |
| fta.claim.198 | [6].ebitda_margin_pct: 22.3% | ebitda_json[6].ebitda_margin_pct | b1feca18 |
| fta.claim.199 | [7].ebitda_dollars: 4,016 | ebitda_json[7].ebitda_dollars | b1feca18 |
| fta.claim.202 | [8].ebitda_margin_pct: 19.5% | ebitda_json[8].ebitda_margin_pct | b1feca18 |
| fta.claim.204 | [9].ebitda_margin_pct: 19.9% | ebitda_json[9].ebitda_margin_pct | b1feca18 |
| fta.claim.205 | [10].ebitda_dollars: 3,277 | ebitda_json[10].ebitda_dollars | 871ba744 |
| fta.claim.206 | [10].ebitda_margin_pct: 36.6% | ebitda_json[10].ebitda_margin_pct | 871ba744 |
| fta.claim.207 | [11].ebitda_dollars: 4,739 | ebitda_json[11].ebitda_dollars | 871ba744 |
| fta.claim.208 | [11].ebitda_margin_pct: 33.4% | ebitda_json[11].ebitda_margin_pct | 871ba744 |
| fta.claim.209 | [12].ebitda_dollars: 6,545 | ebitda_json[12].ebitda_dollars | 871ba744 |
| fta.claim.210 | [12].ebitda_margin_pct: 31.4% | ebitda_json[12].ebitda_margin_pct | 871ba744 |
| fta.claim.211 | [13].ebitda_dollars: 10,354 | ebitda_json[13].ebitda_dollars | 871ba744 |
| fta.claim.212 | [13].ebitda_margin_pct: 30.3% | ebitda_json[13].ebitda_margin_pct | 871ba744 |
| fta.claim.213 | [14].ebitda_dollars: 13,942 | ebitda_json[14].ebitda_dollars | 871ba744 |
| fta.claim.256 | [0].amount_stated: (0) | addback_schedule_json[0].amount_stated | 5fa7f39b |
| fta.claim.257 | [1].amount_stated: 182 | addback_schedule_json[1].amount_stated | 5fa7f39b |
| fta.claim.258 | [2].amount_stated: 53 | addback_schedule_json[2].amount_stated | 5fa7f39b |
| fta.claim.259 | [3].amount_stated: 665 | addback_schedule_json[3].amount_stated | 5fa7f39b |
| fta.claim.260 | [4].amount_stated: (158) | addback_schedule_json[4].amount_stated | 5fa7f39b |
| fta.claim.261 | [5].amount_stated: (33) | addback_schedule_json[5].amount_stated | 5fa7f39b |
| fta.claim.262 | [6].amount_stated: 2,490 | addback_schedule_json[6].amount_stated | 5fa7f39b |
| fta.claim.263 | [7].amount_stated: 94 | addback_schedule_json[7].amount_stated | 5fa7f39b |
| fta.claim.264 | [8].amount_stated: 189 | addback_schedule_json[8].amount_stated | 5fa7f39b |
| fta.claim.265 | [9].amount_stated: 377 | addback_schedule_json[9].amount_stated | 5fa7f39b |
| fta.claim.266 | [10].amount_stated: 1,077 | addback_schedule_json[10].amount_stated | 5fa7f39b |
| fta.claim.269 | [13].amount_stated: 430 | addback_schedule_json[13].amount_stated | 5fa7f39b |
| fta.claim.270 | [14].amount_stated: 909 | addback_schedule_json[14].amount_stated | 5fa7f39b |
| fta.claim.271 | [15].amount_stated: 190 | addback_schedule_json[15].amount_stated | 5fa7f39b |
| fta.claim.272 | [0].amount_stated: 4,251 | opex_breakdown_json[0].amount_stated | 871ba744 |
| fta.claim.273 | [1].amount_stated: 909 | opex_breakdown_json[1].amount_stated | 871ba744 |
| fta.claim.274 | [2].amount_stated: 688 | opex_breakdown_json[2].amount_stated | 871ba744 |
| fta.claim.275 | [3].amount_stated: 5,109 | opex_breakdown_json[3].amount_stated | 871ba744 |

## Batch-approvable MEDIUM, auto-approved via operator override (needs_human=false)

All 76 claims below are `supported`, MEDIUM confidence — not HIGH. needs_human was set to false by override #4 (traceable-LOW auto-approve, 3 claims), override #5 (operator-reviewed rationale profile, 31 claims: boolean provenance flag / chunk-present-but-not-verbatim / composite multi-line-item), or override #6 (structurally no-citable-chunk `revenue_by_segment_json`, 42 claims). See the operator-overrides section above for the exact claim_id lists per override. Do not conflate with the HIGH table above.

| claim_id | claim_text | fta_json_path | chunk_id |
|---|---|---|---|
| fta.claim.005 | yoy_growth_pct: 47.1% | revenue_trend_json[2].yoy_growth_pct | cd9773ea |
| fta.claim.023 | computed_from_stated: False | gross_margin_json[0/1/2/3/4/5].computed_from_stated | cd9773ea |
| fta.claim.036 | computed_from_stated: False | gross_margin_json[6/7/8/9/10].computed_from_stated | 871ba744 |
| fta.claim.038 | gm_pct_stated: 44.3% | gross_margin_json[7].gm_pct_stated | 871ba744 |
| fta.claim.040 | gm_pct_stated: 44.0% | gross_margin_json[8].gm_pct_stated | 871ba744 |
| fta.claim.047 | computed_from_stated: False | gross_margin_json[11].computed_from_stated | d31b581b |
| fta.claim.063 | ebitda_margin_pct: 19.3% | ebitda_json[7].ebitda_margin_pct | b1feca18 |
| fta.claim.064 | ebitda_dollars: 6,677 | ebitda_json[8].ebitda_dollars | b1feca18 |
| fta.claim.066 | ebitda_dollars: 9,239 | ebitda_json[9].ebitda_dollars | b1feca18 |
| fta.claim.077 | ebitda_margin_pct: 30.0% | ebitda_json[14].ebitda_margin_pct | 871ba744 |
| fta.claim.078 | revenue_dollars: 1,525 | revenue_by_segment_json[0].revenue_dollars | n/a |
| fta.claim.079 | revenue_dollars: 4,517 | revenue_by_segment_json[1].revenue_dollars | n/a |
| fta.claim.080 | revenue_dollars: 10,496 | revenue_by_segment_json[2].revenue_dollars | n/a |
| fta.claim.081 | revenue_dollars: 12,972 | revenue_by_segment_json[3].revenue_dollars | n/a |
| fta.claim.082 | revenue_dollars: 13,588 | revenue_by_segment_json[4].revenue_dollars | n/a |
| fta.claim.093 | revenue_dollars: 8,796 | revenue_by_segment_json[15].revenue_dollars | n/a |
| fta.claim.094 | revenue_dollars: 14,151 | revenue_by_segment_json[16].revenue_dollars | n/a |
| fta.claim.095 | revenue_dollars: 20,835 | revenue_by_segment_json[17].revenue_dollars | n/a |
| fta.claim.096 | revenue_dollars: 30,009 | revenue_by_segment_json[18].revenue_dollars | n/a |
| fta.claim.097 | revenue_dollars: 33,991 | revenue_by_segment_json[19].revenue_dollars | n/a |
| fta.claim.098 | revenue_dollars: 200 | revenue_by_segment_json[25].revenue_dollars | n/a |
| fta.claim.099 | revenue_dollars: 600 | revenue_by_segment_json[26].revenue_dollars | n/a |
| fta.claim.100 | revenue_dollars: 2,523 | revenue_by_segment_json[27].revenue_dollars | n/a |
| fta.claim.101 | revenue_dollars: 7,569 | revenue_by_segment_json[28].revenue_dollars | n/a |
| fta.claim.102 | revenue_dollars: 1,417 | revenue_by_segment_json[29].revenue_dollars | n/a |
| fta.claim.103 | revenue_dollars: 4,250 | revenue_by_segment_json[30].revenue_dollars | n/a |
| fta.claim.104 | revenue_dollars: 160 | revenue_by_segment_json[36].revenue_dollars | n/a |
| fta.claim.105 | revenue_dollars: 25 | revenue_by_segment_json[37].revenue_dollars | n/a |
| fta.claim.106 | revenue_dollars: 10 | revenue_by_segment_json[38].revenue_dollars | n/a |
| fta.claim.107 | revenue_dollars: 11 | revenue_by_segment_json[39].revenue_dollars | n/a |
| fta.claim.108 | revenue_dollars: 13 | revenue_by_segment_json[40].revenue_dollars | n/a |
| fta.claim.120 | amount_stated: 0 | addback_schedule_json[?].amount_stated | 5fa7f39b |
| fta.claim.128 | amount_stated: 242 + 62 + 113 + 128 + 20 + 72 + 86 + 497 = multiple line items; see source | opex_breakdown_json[composite] | 871ba744 |
| fta.claim.133 | [2].yoy_growth_pct: 47.1% | revenue_trend_json[2].yoy_growth_pct | cd9773ea |
| fta.claim.151 | [0].computed_from_stated: False | gross_margin_json[0].computed_from_stated | cd9773ea |
| fta.claim.154 | [1].computed_from_stated: False | gross_margin_json[1].computed_from_stated | cd9773ea |
| fta.claim.157 | [2].computed_from_stated: False | gross_margin_json[2].computed_from_stated | cd9773ea |
| fta.claim.160 | [3].computed_from_stated: False | gross_margin_json[3].computed_from_stated | cd9773ea |
| fta.claim.163 | [4].computed_from_stated: False | gross_margin_json[4].computed_from_stated | cd9773ea |
| fta.claim.166 | [5].computed_from_stated: False | gross_margin_json[5].computed_from_stated | cd9773ea |
| fta.claim.169 | [6].computed_from_stated: False | gross_margin_json[6].computed_from_stated | 871ba744 |
| fta.claim.171 | [7].gm_pct_stated: 44.3% | gross_margin_json[7].gm_pct_stated | 871ba744 |
| fta.claim.172 | [7].computed_from_stated: False | gross_margin_json[7].computed_from_stated | 871ba744 |
| fta.claim.174 | [8].gm_pct_stated: 44.0% | gross_margin_json[8].gm_pct_stated | 871ba744 |
| fta.claim.175 | [8].computed_from_stated: False | gross_margin_json[8].computed_from_stated | 871ba744 |
| fta.claim.178 | [9].computed_from_stated: False | gross_margin_json[9].computed_from_stated | 871ba744 |
| fta.claim.181 | [10].computed_from_stated: False | gross_margin_json[10].computed_from_stated | 871ba744 |
| fta.claim.184 | [11].computed_from_stated: False | gross_margin_json[11].computed_from_stated | d31b581b |
| fta.claim.200 | [7].ebitda_margin_pct: 19.3% | ebitda_json[7].ebitda_margin_pct | b1feca18 |
| fta.claim.201 | [8].ebitda_dollars: 6,677 | ebitda_json[8].ebitda_dollars | b1feca18 |
| fta.claim.203 | [9].ebitda_dollars: 9,239 | ebitda_json[9].ebitda_dollars | b1feca18 |
| fta.claim.214 | [14].ebitda_margin_pct: 30.0% | ebitda_json[14].ebitda_margin_pct | 871ba744 |
| fta.claim.215 | [0].revenue_dollars: 1,525 | revenue_by_segment_json[0].revenue_dollars | n/a |
| fta.claim.216 | [1].revenue_dollars: 4,517 | revenue_by_segment_json[1].revenue_dollars | n/a |
| fta.claim.217 | [2].revenue_dollars: 10,496 | revenue_by_segment_json[2].revenue_dollars | n/a |
| fta.claim.218 | [3].revenue_dollars: 12,972 | revenue_by_segment_json[3].revenue_dollars | n/a |
| fta.claim.219 | [4].revenue_dollars: 13,588 | revenue_by_segment_json[4].revenue_dollars | n/a |
| fta.claim.230 | [15].revenue_dollars: 8,796 | revenue_by_segment_json[15].revenue_dollars | n/a |
| fta.claim.231 | [16].revenue_dollars: 14,151 | revenue_by_segment_json[16].revenue_dollars | n/a |
| fta.claim.232 | [17].revenue_dollars: 20,835 | revenue_by_segment_json[17].revenue_dollars | n/a |
| fta.claim.233 | [18].revenue_dollars: 30,009 | revenue_by_segment_json[18].revenue_dollars | n/a |
| fta.claim.234 | [19].revenue_dollars: 33,991 | revenue_by_segment_json[19].revenue_dollars | n/a |
| fta.claim.240 | [25].revenue_dollars: 200 | revenue_by_segment_json[25].revenue_dollars | n/a |
| fta.claim.241 | [26].revenue_dollars: 600 | revenue_by_segment_json[26].revenue_dollars | n/a |
| fta.claim.242 | [27].revenue_dollars: 2,523 | revenue_by_segment_json[27].revenue_dollars | n/a |
| fta.claim.243 | [28].revenue_dollars: 7,569 | revenue_by_segment_json[28].revenue_dollars | n/a |
| fta.claim.244 | [29].revenue_dollars: 1,417 | revenue_by_segment_json[29].revenue_dollars | n/a |
| fta.claim.245 | [30].revenue_dollars: 4,250 | revenue_by_segment_json[30].revenue_dollars | n/a |
| fta.claim.251 | [36].revenue_dollars: 160 | revenue_by_segment_json[36].revenue_dollars | n/a |
| fta.claim.252 | [37].revenue_dollars: 25 | revenue_by_segment_json[37].revenue_dollars | n/a |
| fta.claim.253 | [38].revenue_dollars: 10 | revenue_by_segment_json[38].revenue_dollars | n/a |
| fta.claim.254 | [39].revenue_dollars: 11 | revenue_by_segment_json[39].revenue_dollars | n/a |
| fta.claim.255 | [40].revenue_dollars: 13 | revenue_by_segment_json[40].revenue_dollars | n/a |
| fta.claim.267 | [11].amount_stated: 0 | addback_schedule_json[11].amount_stated | 5fa7f39b |
| fta.claim.268 | [12].amount_stated: 0 | addback_schedule_json[12].amount_stated | 5fa7f39b |
| fta.claim.276 | [4].amount_stated: 242 + 62 + 113 + 128 + 20 + 72 + 86 + 497 = multiple line items; see source | opex_breakdown_json[composite] | 871ba744 |

## Batch-approvable LOW, auto-approved via operator override (needs_human=false)

All 30 claims below are `supported`, LOW confidence — genuinely the weakest evidentiary tier in this run. needs_human was set to false by override #1 (unresolvable-duplicate-array-rows -> supported, 33 claims minus the 3 later promoted to MEDIUM by override #4) plus override #7 (duplicate-block root cause independently confirmed via follow-up Databricks validation: exact Westchester/Long Island duplicate blocks identified, 20/20 indexed values match). Stays LOW because the specific array index is genuinely undecidable between two byte-identical candidates -- this is accepted operator judgment, not a confidence upgrade. Per `spot_check.py`/S2 write path, only verdict+rationale are ingested; confidence/needs_human are session metadata that do not gate the warehouse write.

| claim_id | claim_text | fta_json_path | chunk_id |
|---|---|---|---|
| fta.claim.083 | revenue_dollars: 7,042 | revenue_by_segment_json[?].revenue_dollars | n/a |
| fta.claim.084 | revenue_dollars: 7,990 | revenue_by_segment_json[?].revenue_dollars | n/a |
| fta.claim.085 | revenue_dollars: 7,524 | revenue_by_segment_json[?].revenue_dollars | n/a |
| fta.claim.086 | revenue_dollars: 8,200 | revenue_by_segment_json[?].revenue_dollars | n/a |
| fta.claim.087 | revenue_dollars: 8,759 | revenue_by_segment_json[?].revenue_dollars | n/a |
| fta.claim.088 | revenue_dollars: 229 | revenue_by_segment_json[?].revenue_dollars | n/a |
| fta.claim.089 | revenue_dollars: 1,644 | revenue_by_segment_json[?].revenue_dollars | n/a |
| fta.claim.090 | revenue_dollars: 2,815 | revenue_by_segment_json[?].revenue_dollars | n/a |
| fta.claim.091 | revenue_dollars: 8,837 | revenue_by_segment_json[?].revenue_dollars | n/a |
| fta.claim.092 | revenue_dollars: 11,644 | revenue_by_segment_json[?].revenue_dollars | n/a |
| fta.claim.220 | [5].revenue_dollars: 7,042 | revenue_by_segment_json[5].revenue_dollars | n/a |
| fta.claim.221 | [6].revenue_dollars: 7,990 | revenue_by_segment_json[6].revenue_dollars | n/a |
| fta.claim.222 | [7].revenue_dollars: 7,524 | revenue_by_segment_json[7].revenue_dollars | n/a |
| fta.claim.223 | [8].revenue_dollars: 8,200 | revenue_by_segment_json[8].revenue_dollars | n/a |
| fta.claim.224 | [9].revenue_dollars: 8,759 | revenue_by_segment_json[9].revenue_dollars | n/a |
| fta.claim.225 | [10].revenue_dollars: 229 | revenue_by_segment_json[10].revenue_dollars | n/a |
| fta.claim.226 | [11].revenue_dollars: 1,644 | revenue_by_segment_json[11].revenue_dollars | n/a |
| fta.claim.227 | [12].revenue_dollars: 2,815 | revenue_by_segment_json[12].revenue_dollars | n/a |
| fta.claim.228 | [13].revenue_dollars: 8,837 | revenue_by_segment_json[13].revenue_dollars | n/a |
| fta.claim.229 | [14].revenue_dollars: 11,644 | revenue_by_segment_json[14].revenue_dollars | n/a |
| fta.claim.235 | [20].revenue_dollars: 7,042 | revenue_by_segment_json[20].revenue_dollars | n/a |
| fta.claim.236 | [21].revenue_dollars: 7,990 | revenue_by_segment_json[21].revenue_dollars | n/a |
| fta.claim.237 | [22].revenue_dollars: 7,524 | revenue_by_segment_json[22].revenue_dollars | n/a |
| fta.claim.238 | [23].revenue_dollars: 8,200 | revenue_by_segment_json[23].revenue_dollars | n/a |
| fta.claim.239 | [24].revenue_dollars: 8,759 | revenue_by_segment_json[24].revenue_dollars | n/a |
| fta.claim.246 | [31].revenue_dollars: 229 | revenue_by_segment_json[31].revenue_dollars | n/a |
| fta.claim.247 | [32].revenue_dollars: 1,644 | revenue_by_segment_json[32].revenue_dollars | n/a |
| fta.claim.248 | [33].revenue_dollars: 2,815 | revenue_by_segment_json[33].revenue_dollars | n/a |
| fta.claim.249 | [34].revenue_dollars: 8,837 | revenue_by_segment_json[34].revenue_dollars | n/a |
| fta.claim.250 | [35].revenue_dollars: 11,644 | revenue_by_segment_json[35].revenue_dollars | n/a |