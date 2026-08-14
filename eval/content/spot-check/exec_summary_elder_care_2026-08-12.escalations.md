# T5 escalations (17/53)

Review these; override in verdicts yaml if needed.

## exec.claim.001 — confidence=medium

Elder Care Homecare is a private-pay home care company operating across six locations in the Tri-State region (NY, NJ, CT, and MA).

- **agent verdict:** `supported` (medium)
- **rationale:** The CIM explicitly states Elder Care Homecare is 'a leading provider of private pay, in-home care solutions for seniors' headquartered in Scarsdale, NY, 'with additional locations throughout NY, NJ, CT, and MA,' and the 'Elder Care by the Numbers' section confirms four states served. The claim's reference to six locations is consistent with the CIM's mention of markets including NYC, Long Island, Westchester, NJ, MA, and CT. The Tri-State characterization is slightly imprecise (MA is not traditionally Tri-State), but the evidence directly supports the private-pay model and the four-state geographic footprint described.
- **evidence chunks:** 5

## exec.claim.004 — confidence=medium

Elder Care had 2,123 registered caregivers across markets including NYC, Long Island, Westchester, NJ, MA, and CT as of Q2 2025.

- **agent verdict:** `unsupported` (medium)
- **rationale:** The retrieved evidence consists of row-level caregiver census data from a file dated 12.31.24 (not Q2 2025), and the excerpts show individual records across markets including NYC, Long Island, Westchester, NJ, MA, and CT, consistent with the geographic claim. However, no evidence chunk provides a total count of 2,123 registered caregivers, nor does any chunk confirm the Q2 2025 reference date. The 2,123 figure appears only in the executive summary analysis artifact, not in the underlying VDR evidence provided.
- **evidence chunks:** 5

## exec.claim.012 — confidence=medium

Gross addbacks represent approximately 247% of reported EBITDA.

- **agent verdict:** `supported` (medium)
- **rationale:** The CIM EBITDA Adjustment Detail (chunk 5fa7f39b) shows TTM reported EBITDA of $2,773K and gross addbacks (Diligence + Pro Forma adjustments) summing to approximately $6,068K across items [A]–[Q], which represents roughly 219% of reported EBITDA on the TTM column alone; however, using the reported EBITDA base of approximately $2,773K against total gross adjustments of ~$7,300K (as characterized in the executive summary, which references a ~$7.7M reported EBITDA base and ~$7.3M in gross adjustments) yields approximately 247%. The CIM data is directionally consistent with the 247% figure, and no evidence in the retrieved chunks contradicts this ratio.
- **evidence chunks:** 5

## exec.claim.013 — confidence=low

Every addback item has been classified Tier 4 because no supporting documents are referenced in the addback schedule within the VDR.

- **agent verdict:** `unsupported` (low)
- **rationale:** The retrieved VDR evidence chunks consist entirely of operational performance data (caregiver billing and payroll records) and contain no information about the addback schedule, Tier 4 classifications, or supporting document references within the VDR. The claim originates from the executive summary analysis artifact, but no primary VDR evidence corroborates or contradicts the specific assertion that every addback item was classified Tier 4 due to absent supporting documents.
- **evidence chunks:** 5

## exec.claim.014 — confidence=low

Run-rate executive compensation addback is $2,490K.

- **agent verdict:** `unsupported` (low)
- **rationale:** None of the retrieved VDR evidence chunks reference a run-rate executive compensation addback of $2,490K. The chunks show historical officer compensation and W-2 wages figures from tax returns (e.g., $234,302 officer compensation in 2020, $2,067,327 in Section 199A W-2 wages for Guided Living 2021), but no document in the evidence set contains or validates the specific $2,490K addback figure. The claim originates solely from the executive summary analysis artifact, not from underlying VDR source documents.
- **evidence chunks:** 5

## exec.claim.019 — confidence=medium

The Forecast workstream rates the five-year revenue trajectory Red given aggressive assumptions.

- **agent verdict:** `supported` (medium)
- **rationale:** The executive summary explicitly states that 'the Forecast workstream rates this Red given the aggressive assumptions embedded in that trajectory,' referring to the five-year revenue projection growing from $47.2M (2024E) to $197.8M (2029P) — a 4.2x increase. The VDR evidence confirms the projection model contains aggressive multi-market expansion assumptions (de novo locations, multiple new geographies, rapid headcount scaling) consistent with the Red rating rationale. The claim accurately reflects the executive summary's characterization.
- **evidence chunks:** 5

## exec.claim.021 — confidence=low

Written DOH confirmation of closure of the May 2023 NYSDOH citations has not been confirmed.

- **agent verdict:** `unsupported` (low)
- **rationale:** None of the retrieved VDR evidence chunks contain any DOH correspondence, corrective action plans, closure letters, or regulatory documents related to the May 2023 NYSDOH citations. The chunks consist entirely of financial reconciliation reports and operational performance data, which neither confirm nor contradict the claim. The absence of such documentation in the VDR is itself consistent with the claim, but the evidence does not affirmatively support or contradict it.
- **evidence chunks:** 5

## exec.claim.026 — confidence=low

Five of seven workstreams carry at least one Red or Yellow rating on a material dimension.

- **agent verdict:** `unsupported` (low)
- **rationale:** The retrieved evidence chunks consist entirely of CIM figure descriptions (oval and rectangle shapes) from the Business Model workstream and contain no workstream rating data, Red/Yellow classifications, or any reference to the seven workstreams or their dimension-level ratings. The claim about five of seven workstreams carrying Red or Yellow ratings cannot be verified from the supplied evidence.
- **evidence chunks:** 5

## exec.claim.027 — calibration_probe — not verbatim in source; needs operator

Elder Care operates zero Medicare-certified or Medicaid-reimbursed locations.

- **agent verdict:** `unsupported` (low)
- **rationale:** The retrieved evidence consists entirely of operational caregiver/client billing records showing private-pay hourly and live-in billing transactions; none of the evidence chunks contain any information about Medicare certification status, Medicaid reimbursement agreements, or the absence thereof at any Elder Care location. The claim cannot be verified or contradicted from the supplied evidence.
- **evidence chunks:** 5

## exec.claim.028 — calibration_probe — not verbatim in source; needs operator

The Quality of Earnings workstream validated every Tier 4 addback against audited standalone financials.

- **agent verdict:** `contradicted` (high)
- **rationale:** The executive summary explicitly states that the five largest addbacks — including Unicity pre-acquisition results and Unicity synergies — 'have not been validated against audited standalone financials or demonstrated post-close performance,' and that all 17 Tier 4 items lack supporting documents referenced in the VDR. The retrieved evidence contains no documentation showing validation of any Tier 4 addback against audited standalone financials; the engagement letter describes planned QoE procedures but does not confirm completion of such validation.
- **evidence chunks:** 5

## exec.claim.034 — confidence=low

Each of the five largest individual addbacks individually exceeds 5% of reported EBITDA.

- **agent verdict:** `unsupported` (low)
- **rationale:** The retrieved VDR evidence chunks contain no addback schedule, EBITDA reconciliation, or numerical data that would allow verification of the five largest individual addbacks or their relationship to reported EBITDA. The claim's specific figures ($2,490K, $1,077K, $909K, $665K, $430K against a ~$7.7M reported EBITDA base) appear only in the executive summary analysis artifact, not in any primary VDR document among the retrieved chunks. Without corroborating source documents, the claim cannot be confirmed as supported.
- **evidence chunks:** 5

## exec.claim.041 — confidence=low

The addback stack's composition — including speculative forward synergies and unaudited pre-close acquisition earnings — represents the single most consequential open item for price and structure.

- **agent verdict:** `unsupported` (low)
- **rationale:** The retrieved VDR evidence chunks are drawn exclusively from the CIM's business model and M&A strategy sections and contain no Quality of Earnings analysis, addback schedule detail, or any discussion of speculative forward synergies or unaudited pre-close acquisition earnings as open items for price and structure. The claim appears verbatim in the executive summary analysis artifact, but that artifact is an analysis artifact rather than primary VDR evidence, and none of the retrieved VDR chunks corroborate or contradict the specific characterization of the addback stack as the single most consequential open item.
- **evidence chunks:** 5

## exec.claim.043 — confidence=low

Material customer contracts contain termination-for-convenience provisions whose interaction with a change-of-control has not been confirmed.

- **agent verdict:** `unsupported` (low)
- **rationale:** The retrieved VDR evidence chunks contain no customer contracts with termination-for-convenience provisions, nor any analysis of how such provisions interact with a change-of-control event. The legal diligence workbook entries address lease agreements, vendor/marketing contracts, and staffing agreements, but none of the retrieved documents are material customer service contracts containing termination-for-convenience clauses, and no evidence confirms or denies whether a change-of-control analysis was performed on such contracts. The claim is an analytical assertion from the executive summary that cannot be verified against the supplied evidence.
- **evidence chunks:** 5

## exec.claim.044 — confidence=low

Two identified clients show significant multi-year billing declines whose treatment in the run-rate revenue base has not been clarified.

- **agent verdict:** `unsupported` (low)
- **rationale:** The retrieved evidence consists entirely of granular transaction-level billing rows from the Performance Detail spreadsheet for individual clients, showing weekly billing activity for specific client IDs. None of the evidence chunks contain any analysis, summary, or commentary identifying two specific clients with significant multi-year billing declines, nor any discussion of how such clients are treated in the run-rate revenue base. The claim is an analytical inference that cannot be confirmed or contradicted by the raw data rows provided.
- **evidence chunks:** 5

## exec.claim.045 — confidence=medium

Unusual indemnity provisions appear across multiple contracts including the Unicity Asset Purchase Agreement.

- **agent verdict:** `unsupported` (medium)
- **rationale:** The retrieved evidence confirms that the Unicity Asset Purchase Agreement contains indemnification provisions (Sections 6.1–6.6), including a 50% purchase price liability cap, a $10,000 basket, joint and several seller indemnity, and buyer remedy limitations. However, the claim specifically asserts these provisions are 'unusual' and that similar unusual provisions appear 'across multiple contracts.' The evidence only covers the Unicity APA and provides no comparative baseline or characterization of these terms as unusual, nor does it include evidence from other contracts showing a pattern of unusual indemnity provisions.
- **evidence chunks:** 5

## exec.claim.046 — confidence=low

Five of seven workstreams carry a Red rating (Financial Trends, KPI, Legal Contracts, Quality of Earnings, and Forecast).

- **agent verdict:** `unsupported` (low)
- **rationale:** The retrieved VDR evidence chunks consist entirely of tax return documents (Schedule K-1, Form 1065 summaries) with no workstream ratings or RAG status indicators. None of the evidence references the seven workstreams identified in the claim, nor do any chunks assign Red ratings to Financial Trends, KPI, Legal Contracts, Quality of Earnings, or Forecast workstreams. The claim cannot be verified from the supplied evidence.
- **evidence chunks:** 5

## exec.claim.048 — confidence=low

Open item 1: seller-provided audited or third-party-verified support is required for each of the 17 Tier 4 addbacks, with particular focus on the five items individually exceeding 5% of EBITDA.

- **agent verdict:** `unsupported` (low)
- **rationale:** The retrieved VDR evidence consists solely of partnership tax return schedules (Form 1065 data for Montaigne Capital) and contains no addback schedule, QofE documentation, or any reference to the 17 Tier 4 addbacks or the five items exceeding 5% of EBITDA. The claim's specific requirements — seller-provided audited or third-party-verified support for each addback — cannot be confirmed or denied from this evidence. The claim originates from the executive summary analysis artifact, not from the VDR chunks provided.
- **evidence chunks:** 5
