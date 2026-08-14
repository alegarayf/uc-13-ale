# Exec Summary Spot-Check Review Queue — Elder Care (2026-08-12)

Review 45 of 53 claims; 8 high-confidence drafts are ready for batch approve.

- **Draft verdicts:** {'supported': 22, 'unsupported': 30, 'contradicted': 1}
- **Confidence:** {'medium': 10, 'low': 34, 'high': 9}
- **Mandatory always-flagged:** exec.claim.027, exec.claim.028 (calibration probes); any empty/irrelevant retrieval; any numeric mismatch, partial evidence, or inference-required verdict; exec.claim.029-053 default to human review absent unambiguous evidence.
- **Calibration disagreements (001-028 vs. operator sample):** claims where this draft differs from the M2 operator calibration verdict are flagged `needs_human: true` per contract, regardless of this draft's own confidence.

| claim_id | section | draft_verdict | confidence | rationale | best_chunk | operator action |
|---|---|---|---|---|---|---|
| exec.claim.001 | Business Overview | supported | medium | CIM p.5 (chunk 621e400f) confirms Elder Care Homecare is a private-pay, in-home care provider headquartered in Scarsdale, NY with additional locations across NY/NJ/CT/MA; the specific 'six locations' count is not enumerated in any top-5 chunk. | `621e400f-eb8b-4b3a-ab04-5bdbd3331dce` | Confirm `supported` or override. |
| exec.claim.002 | Business Overview | supported | medium | Retrieved KPI billing-log chunks (e.g. caeba4fd) show per-caregiver Bill Rate x Billed Hours records consistent with hourly private-pay billing, but no chunk states the business model definitionally. | `caeba4fd-638c-4f24-afc2-cba5db553487` | Confirm `supported` or override. |
| exec.claim.003 | Business Overview | unsupported | low | CIM p.5 'Elder Care by the Numbers' (chunk 31263800) states Clients Served: 1,186 -- a different figure/date basis than the claimed 352 active clients as of Q2 2025; the retrieved client-census rows are per-client detail, not an aggregate count. | `31263800-3261-4d24-b8b1-1bd4b7874482` | Confirm `unsupported` or override. **[disagrees w/ M2 calibration]** |
| exec.claim.004 | Business Overview | unsupported | low | Same CIM 'by the Numbers' figure (chunk 31263800, cited via claim.003 retrieval) shows Active Caregivers: 1,888, differing from the claimed 2,123; retrieved caregiver-census rows are per-caregiver detail, not an aggregate count. | `32aa89b6-86cb-4a1b-9cb4-f49aedad6611` | Confirm `unsupported` or override. **[disagrees w/ M2 calibration]** |
| exec.claim.007 | Financial Picture | supported | medium | CIM p.5 'by the Numbers' shows Adjusted Revenue by Location TTM Aug-24: $44.7M, close to but not identical to the claimed $46.4M pro forma total (likely a location-subtotal vs. total-company reconciling gap not visible in the excerpt). | `31263800-3261-4d24-b8b1-1bd4b7874482` | Confirm `supported` or override. |
| exec.claim.008 | Financial Picture | supported | medium | CIM p.47 Pro Forma Income Statement (chunk cd9773ea) begins 'Revenue \| 8,955 \| 14,176 \| 20,846 ...' confirming the 2020A starting figure; the TTM Aug-24 value is truncated past the retrieved excerpt window. | `cd9773ea-0a3c-460d-869a-bc963a15cd1f` | Confirm `supported` or override. |
| exec.claim.009 | Financial Picture | supported | medium | CIM p.46 Diligence Adjusted Income Statement (chunk b1feca18) shows the same Reported Net Revenue series (9,027...35,159) as the executive summary's financial buildup, but the EBITDA/margin line itself is truncated in the retrieved excerpt. | `b1feca18-d10a-4c4b-9a1b-af382f6d2f21` | Confirm `supported` or override. |
| exec.claim.010 | Financial Picture | supported | medium | CIM p.50 EBITDA Adjustment Detail (chunk 5fa7f39b) shows 'Reported EBITDA \| (342) \| 720 \| 180 \| (870) \| 2,773 \| % Reported...' with the percentage column truncated in the excerpt. | `5fa7f39b-cef6-4674-b74c-6d9277e14602` | Confirm `supported` or override. |
| exec.claim.011 | Financial Picture | unsupported | low | Top-5 retrieval surfaced unrelated tax-return Schedule M-2 statements (Guided Living, ECHC 2020) rather than the Tier 4 addback schedule itself; neither the count (17) nor the total ($7.3M) is corroborated. | `_none_` | Confirm `unsupported` or override. **[disagrees w/ M2 calibration]** |
| exec.claim.012 | Financial Picture | unsupported | low | Same EBITDA Adjustment Detail chunk (5fa7f39b) has its percentage figures truncated; other retrieved chunks (Montaigne Capital 2022 tax return) are an unrelated entity and do not corroborate the 247% figure. | `5fa7f39b-cef6-4674-b74c-6d9277e14602` | Confirm `unsupported` or override. **[disagrees w/ M2 calibration]** |
| exec.claim.013 | Financial Picture | unsupported | low | Retrieval surfaced unrelated Guided Living tax credit schedules, an Amex-expense mapping sheet, and KPI performance rows; no chunk discusses the VDR support-documentation rationale for Tier 4 classification. | `_none_` | Confirm `unsupported` or override. **[disagrees w/ M2 calibration]** |
| exec.claim.014 | Financial Picture | unsupported | low | Retrieved tax-return 'Compensation of Officers' lines show entity-specific figures (e.g. $234,302 at ECHC 2020) that do not match the claimed $2,490K run-rate addback; the addback schedule itself was not retrieved. | `5b718c82-b9ea-46a3-95f7-b0cbdecb14a5` | Confirm `unsupported` or override. **[disagrees w/ M2 calibration]** |
| exec.claim.015 | Financial Picture | unsupported | low | Retrieved Unicity/Estimated Homecare P&L spreadsheets contain granular monthly line items with no visible aggregate matching the claimed $1,077K pre-acquisition results addback. | `_none_` | Confirm `unsupported` or override. **[disagrees w/ M2 calibration]** |
| exec.claim.016 | Financial Picture | unsupported | low | Retrieved Unicity P&L spreadsheets (NC Sandbox, Unicity PL) are granular monthly cost-of-goods and income rows with no aggregate matching the claimed $909K synergies figure. | `_none_` | Confirm `unsupported` or override. **[disagrees w/ M2 calibration]** |
| exec.claim.017 | Financial Picture | unsupported | low | Retrieval surfaced bank-account reconciliation summaries (Reconciliation_5943_0521.pdf etc.) which are a different document type (monthly bank reconciliations) from the QoE 'reconciliation workstream' the claim describes; no '1 mismatch / 9 unverified' language found. | `_none_` | Confirm `unsupported` or override. **[disagrees w/ M2 calibration]** |
| exec.claim.018 | Financial Picture | supported | medium | Same CIM p.47 Pro Forma Income Statement & Projection chunk (cd9773ea) spans 2020A through 2029P columns per its header row, consistent with the claimed $47.2M (2024E) to $197.8M (2029P) trajectory, but the 2024E/2029P cell values are truncated in the retrieved excerpt. | `cd9773ea-0a3c-460d-869a-bc963a15cd1f` | Confirm `supported` or override. |
| exec.claim.019 | Financial Picture | unsupported | low | Retrieved chunks are raw Excel formula rows from the projection model (De Novo & Acquisitions, Revenue Build sheets) with no rating label; no chunk states a 'Red' rating for the forecast workstream. | `_none_` | Confirm `unsupported` or override. **[disagrees w/ M2 calibration]** |
| exec.claim.021 | Top Risks | supported | low | The underlying May 2023 NYSDOH survey deficiency document is retrieved (chunk 786faeac), confirming the citation exists; confirming the negative ('written closure confirmation has not been received') requires an absence-of-evidence inference the retrieved chunks cannot directly prove. | `786faeac-2ed3-424c-9453-96109d6dccc2` | Confirm `supported` or override. |
| exec.claim.022 | Top Risks | unsupported | low | Retrieved diligence-workbook rows reference the NYSDOH survey and a general 'Privacy/HIPAA' request-list item, but no chunk in the top-5 contains explicit OIG/SAM exclusion-screening language. | `_none_` | Confirm `unsupported` or override. **[disagrees w/ M2 calibration]** |
| exec.claim.025 | Confidence | unsupported | low | Top-5 retrieval surfaced unrelated CAC-LTV financial-model rows and a summary P&L sheet; no chunk contains an overall-confidence rating statement. | `_none_` | Confirm `unsupported` or override. **[disagrees w/ M2 calibration]** |
| exec.claim.026 | Confidence | unsupported | low | Retrieved chunks (diligence tracker table, MSDS hazard-label figure, tax return, file index, lease doc) do not state a '5 of 7 workstreams Red/Yellow' rating summary. | `_none_` | Confirm `unsupported` or override. **[disagrees w/ M2 calibration]** |
| exec.claim.027 | Business Overview | unsupported | medium | Calibration probe claim (rubric-flagged, not verbatim in executive_summary). Retrieved chunks are granular billing/performance rows with no explicit statement of Medicare/Medicaid certification status for any location. | `_none_` | Confirm `unsupported` or override. |
| exec.claim.028 | Financial Picture | contradicted | high | Calibration probe claim (rubric-flagged, not verbatim in executive_summary). The Project Orange QoE engagement letter (chunk 62a944a5) describes the QoE scope as identifying and analyzing addbacks, not validating them against audited financials; this is consistent with the executive_summary's own statement that the five largest addbacks 'have not been validated against audited standalone financials.' | `62a944a5-3905-4ebd-889a-f71a103c81c1` | Confirm `contradicted` or override. |
| exec.claim.031 | Financial Picture | unsupported | low | Same EBITDA Adjustment Detail chunk (5fa7f39b) has its reported-EBITDA-base figure implied but not clearly isolated as '$7.7M' in the retrieved excerpt; other retrieved chunks (bank statements) are unrelated. | `5fa7f39b-cef6-4674-b74c-6d9277e14602` | Confirm `unsupported` or override. |
| exec.claim.032 | Financial Picture | unsupported | low | Retrieved tax-return Schedule M-2 chunks (Montaigne Capital 2021/2022) do not contain a $665K cash-to-accrual revenue adjustment line item. | `_none_` | Confirm `unsupported` or override. |
| exec.claim.033 | Financial Picture | unsupported | low | Retrieved Guided Living tax-return and P&L chunks contain granular schedule/expense rows with no visible $430K ramp-up adjustment total. | `_none_` | Confirm `unsupported` or override. |
| exec.claim.034 | Financial Picture | unsupported | low | Retrieved chunks are unrelated Montaigne Capital partner-level tax data; no chunk enumerates the five largest addbacks or their percentage-of-EBITDA thresholds. | `_none_` | Confirm `unsupported` or override. |
| exec.claim.035 | Financial Picture | supported | medium | No VDR chunk explicitly discusses validation status of the five specific addback line items; the executive_summary text itself (internal source-artifact context) states these addbacks 'have not been validated against audited standalone financials or demonstrated post-close performance,' consistent with the pattern already confirmed for exec.claim.013/028. | `_none_` | Confirm `supported` or override. |
| exec.claim.036 | Financial Picture | unsupported | low | This is a forward-looking, interpretive statement about what could happen in a hypothetical buyer QoE; retrieved chunks (Unicity APA remedies section, bank cashflow summaries) do not address this scenario. | `_none_` | Confirm `unsupported` or override. |
| exec.claim.038 | Top Risks | supported | low | Diligence-tracker chunks (Guided Living / Elder Care workbooks) show open/partial/closed item-status tracking consistent with an active, issue-surfacing diligence process, but no chunk uses the specific 'critical and material issues' framing. | `ce6ea6c8-664f-4e10-a84c-f4cf5b756d52` | Confirm `supported` or override. |
| exec.claim.039 | Top Risks | unsupported | low | Retrieval for this query surfaced unrelated Elder Care billing/performance-detail rows rather than the NYSDOH survey or corrective-action documentation. | `_none_` | Confirm `unsupported` or override. |
| exec.claim.040 | Top Risks | unsupported | low | Retrieval for this query surfaced unrelated Amex credit-card transaction detail spreadsheets; no chunk addresses OIG/SAM exclusion screening or False Claims Act exposure. | `_none_` | Confirm `unsupported` or override. |
| exec.claim.041 | Top Risks | unsupported | low | CIM M&A strategy/integration chunks provide context on the addback stack's composition, but ranking it as the 'single most consequential open item' is an evaluative judgment not stated in any retrieved chunk. | `_none_` | Confirm `unsupported` or override. |
| exec.claim.042 | Top Risks | unsupported | low | Retrieved bank-balance-summary and performance-detail chunks do not discuss patient-receivables collection activity or billing-integrity concerns; the more relevant retainer-agreement chunk (from exec.claim.023) was not returned for this query. | `_none_` | Confirm `unsupported` or override. |
| exec.claim.043 | Top Risks | supported | low | Diligence workbook (Legal - Brownstein, chunk 951b56a0) references 'Agreements that cannot be terminated on notice of 60 days or less,' consistent with termination-provision review, but no chunk explicitly confirms the change-of-control interaction is unconfirmed. | `951b56a0-385a-4732-89d4-b16a533cbe27` | Confirm `supported` or override. |
| exec.claim.044 | Top Risks | unsupported | low | Retrieved performance-detail rows show individual 'Not Billable' status entries but do not identify two specific clients with multi-year billing declines or discuss run-rate treatment. | `_none_` | Confirm `unsupported` or override. |
| exec.claim.045 | Top Risks | supported | medium | Unicity Asset Purchase Agreement Section 6.5 'Liability Limitations' and the Breach/Remedies/Indemnification section (chunks 4e6bef9e, ec87067f) directly evidence indemnification provisions in the Unicity APA; whether they are 'unusual' relative to market and whether other contracts share the pattern is a characterization beyond raw fact. | `4e6bef9e-695f-4405-9ef5-bfc0e617d7a6` | Confirm `supported` or override. |
| exec.claim.046 | Confidence | unsupported | low | Retrieved chunks (engagement letter, projection-model rows, tax-return partner data) do not contain the workstream rating rollup or name the five specific Red-rated workstreams. | `_none_` | Confirm `unsupported` or override. |
| exec.claim.047 | Confidence | unsupported | low | Retrieved chunks (QoE engagement letter, Target Profile Metrics table, performance-detail rows) do not state a Yellow rating for Business Model or Customer Quality workstreams. | `_none_` | Confirm `unsupported` or override. |
| exec.claim.048 | Confidence | unsupported | low | Retrieved tax-return Schedule K/B chunks are unrelated to the open-items list; no chunk frames a requirement for seller-provided audited support of the 17 Tier 4 addbacks. | `_none_` | Confirm `unsupported` or override. |
| exec.claim.049 | Confidence | supported | low | The underlying NYSDOH survey document and diligence-workbook Q&A (chunks 41055a3e, a7cbdc65) confirm the regulatory matters referenced by this open item exist, but no chunk frames them as a numbered 'open item' requiring DOH confirmation and OIG/SAM screening. | `41055a3e-b1b8-4440-be5c-14b0b39c086f` | Confirm `supported` or override. |
| exec.claim.050 | Confidence | unsupported | low | Unicity APA 'Post-Closing Collections' section and the QoE engagement letter's balance-sheet-analysis scope are topically adjacent (collections, AR review) but do not frame a specific open item for quantifying/aging receivables in active legal collection. | `_none_` | Confirm `unsupported` or override. |
| exec.claim.051 | Confidence | unsupported | low | Unicity APA representations/warranties section and a Massachusetts regulatory-filing 'no control affidavit' document are topically related to change-of-control mechanics, but no chunk confirms an open item specifically about customer-contract CoC triggers. | `_none_` | Confirm `unsupported` or override. |
| exec.claim.052 | Confidence | supported | low | The Guided Living 'Diligence Template' business-diligence-request tracker (chunk c12caa0b) shows open items being tracked by category/status, consistent with an active open-items list, though it does not itself name the location-level P&L/KPI requirement verbatim. | `c12caa0b-aa74-4762-82c3-2b53edb3150e` | Confirm `supported` or override. |
| exec.claim.053 | Confidence | unsupported | low | Retrieval surfaced generic contractor-agreement assignment boilerplate (De Guzman, Momongan, etc.) rather than the Manhattan lease or a workstream recommendation to engage outside counsel. | `_none_` | Confirm `unsupported` or override. |

## Batch-approvable claims (8)

| claim_id | section | draft_verdict | rationale |
|---|---|---|---|
| exec.claim.005 | Business Overview | supported | CIM p.18 'Corporate Functions' (chunk ffdfd9cb) states the Company absorbed billing/payroll/HR/compliance functions 'for both Guided Living and Unicity', directly naming both transactions. |
| exec.claim.006 | Business Overview | supported | CIM p.41 'Key Entity Metrics: Elder Care Homecare - CT' (chunk a047ed66) states the Company entered the Connecticut market in October 2023, and the MD&A chunk references ongoing de novo strategy. |
| exec.claim.020 | Top Risks | supported | Diligence workbook Q&A (chunk e0d4f57a) states verbatim the Company 'was cited in the May 2023 NYSDOH Survey with regard to updating the Company's HCR Profile and with regard to obtaining [background-check consent]'; the underlying survey document (NYC DOH Survey and Approval 5.4.23.pdf) is also retrieved. |
| exec.claim.023 | Top Risks | supported | Chunk c258eb04 is the retainer-agreement document itself ('April 30 2025 Fully Executed Retainer Agreement for Collection Efforts by Peter Ackerman Esq.'), directly confirming outside counsel was retained on that date for collection efforts. |
| exec.claim.024 | Top Risks | supported | Manhattan_Lease_0424.pdf Section 11 'Assignment, Mortgage, Etc.' (chunk 3a8e1f08) is the anti-assignment covenant itself, directly on point. |
| exec.claim.029 | Business Overview | supported | Client service agreements across NY/MA/CT (chunks 69df4f29, 1fb9e854, 1ec79062) confirm home-care service delivery to elderly clients under the Elder Care Homecare brand, consistent with the claimed home health aide / live-in / nursing service lines. |
| exec.claim.030 | Business Overview | supported | CIM p.22 Management Discussion & Analysis (chunk d64e0cbf) states the Company 'implemented its organic growth initiatives and de novo strategies, and completed two strategic acquisitions,' directly confirming both growth channels. |
| exec.claim.037 | Financial Picture | supported | CIM p.48 'Projection Detail and Key Assumptions' (chunk 0fe67858) states organic growth was driven by increases in patients/hours, and the Connecticut de novo ramp is independently confirmed via exec.claim.006's evidence. |



--- 

## Operator's review and notes

### Notes: 

- by you I mean the agent that drafted, throughout the document. 

- the responses might point to suspected root causes, areas of improvements, opportunities to look into, etc - not just supported or not since the idea is to enhance the system and work through the failures to generate reliable and trust worthy output. 

### claims thoughts + veredict - some might need rationale or inference based on my notes instead of explicitly calling out a state but others will have an explicit state: 

1: So we can count 5 at least but is the llm hallucinating 6 locations that we can not claim as supported? if it's not supported doesn't mean it's wrong maybe just tweak the prompt to remove the integer if it can not support or substantiate the claim 

2: if its not verbatim but still correct because its supported or substantiated by the data then its ok and supported I think 

3: I think you're right - it's not supported enough the claim so probably hallucinated to some degree or wrongly interpreted data 

4: same as 3 

7: so it seems that its supported depending on interpretation so maybe its supported but with the caveat of making more explicit what it means - so prob a prompt tweak? 

8: so if it's supported then great - i dont get the truncated value at chunk boundry, is it not getting completed by adjacent retrieved chunks? signal that we need to look into something? 

9: again the retrieval truncation, should it not retrieve the adjacent chunks? - regardless of that which imo should be fixed, this one seems supported. 

10: seems supported as long as we're not displaying on claiming truncated unverifiable data 

11: if it cannot be supported then its unsupported 

12: seems unsupported and prob a retrieval failure on top 

13: unsupported then if retrieval did not pull relevant documents and the claim being made is not reflected upon those 

14: unsupported + retrieval miss, right? 

15: if the aggregated does not sum up to what it's being generated then it's wrong or unsupported, if the aggregated computes correctly to what's being shown then it's fine but probably should be best to not aggregate and show the source instead? 


16: same as 15 

17: unsupported + retrieval miss? 

18: so supported + the retrieval chunk boundry thing or truncated and incomplete retrieval thing again that we saw as well in prevs claims 

19: I think that red classification comes from reasoning within the agent and not from retrieval - if it does not and it's a retrieval miss or hallucination then it's unsupported but if by some logic it attributes the red label then it's ok as long as the rationale or logic checks out 

21: I agree with the note in the rationale field from the table 

22: unsupported if the claim is not verbatim or derive from rationale using the retrieved source chunks 

25: I think this comes from the agent itself about the confidence attributed to the analysis itself and not documentation really unless its a gap or follow up for the stakeholders - otherwise then it's unsupported as per the rationale 

26: I think this is the same as claim 19

27: If the claim being made can not be traced back to a verbatim chunk or rationale then it's unsupported [I think this is the main core philosophy to adopt]

28: so this is an agent feature failure or miss? maybe it either should validate as well or just surface without hard claims? but it does sound contradicted as per your draft 

31: so unsupported but the root cause could be agent failure and not retrieval miss? 

32: if there's no verbatim line or logical trace back to the claim then it's an unsupported hallucinated claim I think 

33: same as 32

34: then unsupported 

35: ok so the disclaimer + data check out so it's supported? 

36: does the agent logic or features require this to be done even if it's not verbatim? if so then ok otherwise your draft is ok 

38: Maybe the chunks dont but the agent or prompt do. regardless seems the claim is supported 

39: seems like a retrieval miss? unsupported 

40: same as 39? 

41: I agree - maybe an agent failure regarding the rationale or wording? 

42: seems like retrieval miss again? + unsupported claim

43: so could be derived from logic and knowledge of the agent but not supported in actual verbatim claims? maybe could have a disclaimer about where the rationale comes from or just avoid making unsupported claims by the docs or db altoghether 

44: I think unsupported here 

45: I agree with your note - claim seems supported but agent took it a bit further than that (tweak opportunity) 

46: again maybe this is derived from agent's reasoning or instructions but if not then unsupported 

47: The same about agent instructions or reasoning - otherwise unsupported but I'm sure it's part of their tasks to add a color rating which could take some tweaking perhaps 

48: Unsupported I think then although maybe it comes from reasoning and instructions in the agent itself 

49: Maybe this comes from agent reasoning and it's not wrong but poorly presented or worded but the info might be correct

50: could be the agent stretching things due to the instructions or prompt - so maybe somehow it is supported as its flagging a gap in coverage - should look into this to define if unsupported or supported 

51: since this is confidence as part of the analysis meta analysis then maybe also agent instructions or prompt stretching things or poorly wording things since it's a diligence flag - would need to look into it deeper to know why is saying that as with prevs examples 

52: the same goes about instructions or rationale from the agent - claims seems to be valid although maybe not verbatim - so to some degree supported but we should make sure it's valid not just supported + wording phrasing rationale 

53: seems like a retrieval miss? 


--- we should review my feedback and try to validate + look for root causes and areas of improvement to tackle them and then (idk the order) -> finish t5 -> m3 -> re calibrate the judge... 