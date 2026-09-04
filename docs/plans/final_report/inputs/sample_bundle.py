"""sample_bundle.py — ILLUSTRATIVE DATA ONLY.

Exists solely to render the stakeholder preview of final_report.html.j2. Every
figure below is invented for a fictional company. It is not Elder Care, not
Simplistic, and not any company in the pipeline. Delete before production use.
"""

BUNDLE = {
    "meta": {
        "company_name": "Northwind Care Partners (ILLUSTRATIVE SAMPLE)",
        "generated_at": "2026-09-03T09:00:00Z",
        "overall_confidence": "medium",
        "vertical_overlay": "healthcare_services",
        "run_mode": "cim_only",
        "doc_count": 214,
        "disclaimer_text": "TEMPLATE PREVIEW — all figures are illustrative and invented to demonstrate layout. Not a real company and not investment advice.",
        "manifest": {"workstreams_ok": 7, "workstreams_total": 7, "degraded": "none"},
    },
    "executive": {
        "in_one_line": "Private-pay home care platform in three metro markets, 1,186 clients and 1,888 active caregivers, growing high-single-digit with margins held back by wage pressure and a thin management layer.",
        "thesis_bullets": [
            "Private-pay only: no Medicaid or managed-care reimbursement exposure, and pricing has moved with wages for three consecutive years.",
            "Referral base is genuinely diversified — no single source above 14% of new client starts across a 9-category mix.",
            "Fragmented three-metro footprint with 40+ sub-scale operators in radius; a credible platform for tuck-in M&A.",
        ],
        "key_watchouts": [
            "Caregiver turnover at 38% sits above our 30% screen and caps growth before demand does.",
            "Owner-operator runs sales, scheduling and payroll; no COO and no location-level P&L discipline.",
            "Adjusted EBITDA carries 22% of addbacks, of which the largest is a recurring rather than one-time cost.",
        ],
    },
    "headline_metrics": {
        "ltm_revenue": "$48.2M",
        "revenue_cagr": "8.4%",
        "ltm_ebitda": "$5.3M",
        "ltm_ebitda_margin_pct": "11.0%",
        "top1_concentration_pct": "14%",
        "enterprise_value_indicated": "$42-48M",
    },
    "company_framing": {
        "overview_bullets": [
            "Non-medical home care across three metro markets: personal care, companionship and respite, billed hourly.",
            "1,186 active clients served by 1,888 W-2 caregivers out of 7 branch offices.",
            "Founded 2009, owner-operated, first institutional capital sought in this process.",
            "Average client tenure 14 months; average 21 billable hours per client per week.",
        ],
        "thesis": {
            "value_creation_levers": [
                {"lever": "Professionalise the management layer (COO, branch P&L)", "size": "150-250bps margin", "owner": "Sponsor / management"},
                {"lever": "Caregiver retention programme", "size": "80-120bps margin", "owner": "Management"},
                {"lever": "Tuck-in M&A in adjacent metros", "size": "$15-20M revenue", "owner": "Sponsor"},
                {"lever": "Rate optimisation on legacy clients", "size": "60-90bps margin", "owner": "Management"},
            ]
        },
    },
    "financials": {
        "currency": "$",
        "unit": "millions",
        "unit_label": "$ millions, fiscal years",
        "segment_dimension": "Branch",
        "table_rows": [
            {"year": "FY2022", "revenue": "37.9", "cogs": "26.3", "gross_profit": "11.6", "gross_margin_pct": "30.6%",
             "opex": "8.0", "ebitda": "3.6", "ebitda_margin_pct": "9.5%", "adjusted_ebitda": "4.1", "adjusted_ebitda_margin_pct": "10.8%"},
            {"year": "FY2023", "revenue": "42.6", "cogs": "29.4", "gross_profit": "13.2", "gross_margin_pct": "31.0%",
             "opex": "8.7", "ebitda": "4.5", "ebitda_margin_pct": "10.6%", "adjusted_ebitda": "5.2", "adjusted_ebitda_margin_pct": "12.2%"},
            {"year": "FY2024", "revenue": "45.1", "cogs": "31.2", "gross_profit": "13.9", "gross_margin_pct": "30.8%",
             "opex": "9.1", "ebitda": "4.8", "ebitda_margin_pct": "10.6%", "adjusted_ebitda": "5.6", "adjusted_ebitda_margin_pct": "12.4%"},
            {"year": "LTM Jun-26", "revenue": "48.2", "cogs": "33.4", "gross_profit": "14.8", "gross_margin_pct": "30.7%",
             "opex": "9.5", "ebitda": "5.3", "ebitda_margin_pct": "11.0%", "adjusted_ebitda": "6.5", "adjusted_ebitda_margin_pct": "13.5%"},
        ],
        "forecast_rows": [
            {"year": "FY2027", "revenue": "55.4", "ebitda_margin_pct": "13.0%"},
            {"year": "FY2028", "revenue": "64.1", "ebitda_margin_pct": "14.5%"},
        ],
        "forecast_assumptions": [
            {"assumption": "15% revenue growth, against an 8.4% three-year actual", "support": "low", "test": "Reconcile to branch-level capacity and caregiver hiring plan"},
            {"assumption": "200bps gross margin expansion from rate increases", "support": "medium", "test": "Historical rate-increase acceptance by client cohort"},
            {"assumption": "Caregiver turnover falls to 28% without added cost", "support": "low", "test": "Cost of the retention programme and its effect on gross margin"},
            {"assumption": "Two tuck-ins close in FY2027 at 5.0x", "support": "low", "test": "Pipeline evidence and prior M&A execution track record"},
        ],
        "observations": [
            "Revenue compounding 8.4% since FY2022, all organic and all volume — hours grew 6.1%, rate 2.2%.",
            "Gross margin flat within a 40bps band for three years: rate increases are covering wage inflation, not beating it.",
            "Reported EBITDA margin improved 150bps, but the gap to adjusted widened from 130bps to 250bps.",
            "LTM includes one branch opened in Q2; contribution is negative and not adjusted out.",
        ],
        "growth_bridge": [
            {"driver": "Volume — billable hours", "value": "+$2.7M"},
            {"driver": "Rate — pricing", "value": "+$1.0M"},
            {"driver": "New branch", "value": "+$0.6M"},
            {"driver": "Client churn", "value": "-$1.2M"},
        ],
        "segment_performance": [
            {"name": "Metro North", "revenue": "18.4", "share_pct": "38%", "gross_margin_pct": "33.1%", "growth_pct": "+9.2%", "read": "low", "read_label": "Strong"},
            {"name": "Metro Central", "revenue": "15.1", "share_pct": "31%", "gross_margin_pct": "31.4%", "growth_pct": "+7.8%", "read": "low", "read_label": "Solid"},
            {"name": "Metro South", "revenue": "11.2", "share_pct": "23%", "gross_margin_pct": "27.9%", "growth_pct": "+4.1%", "read": "medium", "read_label": "Lagging"},
            {"name": "New branch", "revenue": "3.5", "share_pct": "7%", "gross_margin_pct": "21.0%", "growth_pct": "n/a", "read": "high", "read_label": "Dilutive"},
        ],
    },
    "revenue_quality": {
        "client_count": "1,186",
        "concentration_summary": {"top1_pct": "14%", "top3_pct": "31%", "top5_pct": "42%"},
        "retention": {"nrr_pct": "94%", "grr_pct": "81%", "logo_churn_rate_annual_pct": "19%"},
        "customer_tenure": {"average_tenure_years": "1.2"},
        "revenue_type_mix": [
            {"label": "Recurring weekly care plans", "pct_of_revenue": "68"},
            {"label": "Episodic / respite", "pct_of_revenue": "22"},
            {"label": "One-time assessments", "pct_of_revenue": "10"},
        ],
        "client_distribution": [
            {"label": "Private pay — self", "pct_of_revenue": "61"},
            {"label": "Private pay — family", "pct_of_revenue": "27"},
            {"label": "LTC insurance", "pct_of_revenue": "12"},
        ],
        "top_customers": [
            {"customer_name": "Referral source A — hospital system", "revenue_pct_yr1": "14%", "gm_pct": "31%",
             "contract_status": "no contract", "years_as_customer": "6", "revenue_trend_note": "Growing, but discharge-planner relationship is personal"},
            {"customer_name": "Referral source B — senior living", "revenue_pct_yr1": "11%", "gm_pct": "33%",
             "contract_status": "preferred provider", "years_as_customer": "5", "revenue_trend_note": "Flat two years"},
            {"customer_name": "Referral source C — LTC insurer", "revenue_pct_yr1": "9%", "gm_pct": "28%",
             "contract_status": "contracted", "years_as_customer": "4", "revenue_trend_note": "Growing, lower rate card"},
            {"customer_name": "Referral source D — physician group", "revenue_pct_yr1": "7%", "gm_pct": "32%",
             "contract_status": "no contract", "years_as_customer": "3", "revenue_trend_note": "Declining"},
            {"customer_name": "Referral source E — community", "revenue_pct_yr1": "6%", "gm_pct": "34%",
             "contract_status": "n/a", "years_as_customer": "7", "revenue_trend_note": "Stable"},
        ],
    },
    "kpi_dashboard": [
        {"metric_id": "gross_margin_pct", "display_name": "Gross margin", "stated_value": "30.7%", "fill_state": "filled"},
        {"metric_id": "ebitda_margin_pct", "display_name": "EBITDA margin", "stated_value": "11.0%", "fill_state": "filled"},
        {"metric_id": "revenue_growth_pct", "display_name": "Revenue growth", "stated_value": "8.4%", "fill_state": "filled"},
        {"metric_id": "top1_pct", "display_name": "Top referral source share", "stated_value": "14.0%", "fill_state": "filled"},
        {"metric_id": "government_payor_pct", "display_name": "Government payor share", "stated_value": "0.0%", "fill_state": "filled"},
        {"metric_id": "employee_turnover_pct", "display_name": "Caregiver turnover", "stated_value": "38.0%",
         "fill_state": "filled", "flag_note": "Above the 30% screen. Every point of turnover costs roughly $1,900 in recruiting and onboarding at this scale."},
        {"metric_id": "utilization_pct", "display_name": "Caregiver utilization", "stated_value": "64.0%",
         "fill_state": "filled", "flag_note": "Below the 70% screen; scheduling is manual and branch-level, which is also the margin lever."},
        {"metric_id": "revenue_per_client", "display_name": "Revenue per client", "stated_value": "40.6", "fill_state": "filled"},
        {"metric_id": "compliance_incidents", "display_name": "Compliance incidents", "stated_value": None, "fill_state": "gap_correct"},
        {"metric_id": "branch_level_pl", "display_name": "Branch-level P&L", "stated_value": None, "fill_state": "not_attempted"},
    ],
    "qoe": {
        "addback_pct_of_ebitda": "22%",
        "tier_summary": "Three of seven addbacks are Tier 3 (unsupported or recurring).",
        "addbacks": [
            {"label": "Owner compensation above market", "amount": "0.42", "tier": "Tier 1"},
            {"label": "One-time legal settlement", "amount": "0.31", "tier": "Tier 2"},
            {"label": "Recruiting agency spend", "amount": "0.28", "tier": "Tier 3"},
            {"label": "Family payroll", "amount": "0.14", "tier": "Tier 1"},
            {"label": "Transaction preparation", "amount": "0.09", "tier": "Tier 2"},
        ],
        "flags": [
            {"description": "Recruiting agency spend added back as one-time, but appears in all four years at similar magnitude.", "severity": "high"},
            {"description": "New branch losses are not adjusted out, understating the run-rate of the mature base.", "severity": "medium"},
            {"description": "AR over 90 days rose from 4% to 9% of receivables with no reserve change.", "severity": "medium"},
            {"description": "Q4 revenue includes a $0.3M retroactive rate adjustment recognised in one period.", "severity": "medium"},
        ],
    },
    "legal": {
        "assessed_count": 9,
        "checklist_total": 11,
        "section_confidence": "medium",
        "coc_consent_count": 3,
        "top_flags": [
            {"flag": "Change-of-control consent in LTC insurer agreement", "impact": "9% of revenue requires consent to assign; no fallback if withheld.", "severity": "high"},
            {"flag": "No caregiver non-solicit", "impact": "Competitor could lift a branch's caregiver base; no contractual recourse.", "severity": "medium"},
            {"flag": "Owner personally guarantees two branch leases", "impact": "Requires release or replacement at close.", "severity": "medium"},
            {"flag": "State licensure renewal pending in one metro", "impact": "Confirm status before signing; operating without it halts billing.", "severity": "high"},
        ],
    },
    "risks": [
        {"risk": "Caregiver supply caps growth", "severity": "high",
         "evidence": "38% turnover, 64% utilization, 41 unfilled shifts per week in the last quarter.",
         "mitigant_or_question": "Model growth on hiring capacity, not demand. Price the retention programme into the plan."},
        {"risk": "Addback quality overstates EBITDA", "severity": "high",
         "evidence": "Recruiting spend of $0.28M added back in all four years; new-branch losses not adjusted.",
         "mitigant_or_question": "Rebuild adjusted EBITDA on a defensible basis before pricing; expect a QoE haircut."},
        {"risk": "Referral relationships are personal, not contractual", "severity": "high",
         "evidence": "Top two sources, 25% of new starts combined, have no contract.",
         "mitigant_or_question": "Meet the discharge planners. Test what happens if the owner steps back."},
        {"risk": "Single-point management dependency", "severity": "high",
         "evidence": "Owner runs sales, scheduling and payroll. No COO, no branch P&L reporting.",
         "mitigant_or_question": "Cost the management build into the first 12 months; this is a use-of-funds item, not a synergy."},
        {"risk": "Forecast step-up unsupported", "severity": "medium",
         "evidence": "Plan assumes 15% growth against 8.4% actual, with no change in capacity assumptions.",
         "mitigant_or_question": "Underwrite to run-rate. Treat the plan as the upside case."},
        {"risk": "Metro South margin drag", "severity": "medium",
         "evidence": "27.9% gross margin against 33.1% in Metro North on similar service mix.",
         "mitigant_or_question": "Diligence why: wage rates, client mix, or scheduling discipline."},
        {"risk": "Licensure renewal outstanding", "severity": "medium",
         "evidence": "One metro's licence is pending renewal at the time of the data room.",
         "mitigant_or_question": "Confirm before signing; this is a condition, not a risk to price."},
        {"risk": "AR aging deterioration", "severity": "low",
         "evidence": "90-day AR rose from 4% to 9% with no reserve change.",
         "mitigant_or_question": "Working capital peg should reflect the true collectability."},
        {"risk": "Client tenure short relative to acquisition cost", "severity": "low",
         "evidence": "Average tenure 14 months.", "mitigant_or_question": "Test CAC payback per client cohort."},
    ],
    "diligence_questions": [
        {"category": "Caregiver supply", "question": "What is the fully loaded cost of reducing turnover from 38% to 28%, and where does it sit in the P&L?",
         "why_it_matters": "The plan assumes the improvement is free. If it costs 100bps of gross margin, the margin expansion story reverses."},
        {"category": "Earnings quality", "question": "Why is recruiting agency spend treated as one-time when it appears in all four years?",
         "why_it_matters": "This single line is roughly 5% of adjusted EBITDA and sets the tone for the rest of the addback schedule."},
        {"category": "Referrals", "question": "Which referral relationships are institutional versus personal to the owner, source by source?",
         "why_it_matters": "25% of new client starts sit with two uncontracted sources. Their durability post-close is the revenue question."},
        {"category": "Management", "question": "What is the plan and cost for the management layer, and who has run a multi-site operation before?",
         "why_it_matters": "Every value creation lever in the plan requires a management team that does not exist yet."},
        {"category": "Forecast", "question": "Reconcile the 15% growth plan to branch-level capacity and the hiring plan, branch by branch.",
         "why_it_matters": "Growth is capacity-constrained, not demand-constrained. A demand-based plan is the wrong model."},
        {"category": "Margin", "question": "What explains the 520bps gross margin gap between Metro South and Metro North?",
         "why_it_matters": "If it is fixable it is a lever worth 60-90bps at the group level; if structural, it caps the platform."},
        {"category": "Legal", "question": "What is the consent position with the LTC insurer, and what is the fallback if consent is withheld?",
         "why_it_matters": "9% of revenue and the only contracted payor relationship in the business."},
        {"category": "Reporting", "question": "Can the business produce branch-level revenue, margin, utilization and quality metrics monthly?",
         "why_it_matters": "If not, that is both a diligence gap and a statement about how the business is run."},
    ],
    "confidence_by_area": {
        "business_model": "high", "financial_trends": "high", "customer_quality": "medium",
        "kpi": "medium", "legal": "medium", "quality_of_earnings": "high", "forecast_support": "low",
    },
    "data_room_gaps": [
        {"item": "Branch-level P&L for FY2023-LTM", "priority": "high", "why": "Required to test the Metro South margin gap and to underwrite branch-level levers."},
        {"item": "Caregiver turnover by branch and tenure band", "priority": "high", "why": "Turnover is the binding growth constraint; group-level 38% hides the distribution."},
        {"item": "Full addback support schedule with invoices", "priority": "high", "why": "Three addbacks are unsupported; they drive the price."},
        {"item": "Referral source detail by new client starts, monthly", "priority": "medium", "why": "Revenue-share view understates the dependency on a few discharge planners."},
        {"item": "LTC insurer agreement, executed copy", "priority": "medium", "why": "Consent and rate-card terms are only summarised in the CIM."},
        {"item": "Client cohort retention by vintage", "priority": "medium", "why": "14-month average tenure needs a distribution to be underwritable."},
        {"item": "State licensure correspondence", "priority": "medium", "why": "Renewal status is asserted but not evidenced."},
        {"item": "Scheduling system reports on unfilled shifts", "priority": "low", "why": "Quantifies the revenue lost to capacity today."},
    ],
}

NARRATIVE = {
    "recommendation": {
        "verdict": "Pursue — proceed to management meetings, underwrite to run-rate not to plan",
        "tone": "pursue",
        "rationale": "A genuinely private-pay, referral-diversified home care platform in a fragmented market is the right shape of asset. The reasons to hesitate are execution and earnings quality, both of which are testable in the next two weeks and both of which are priceable.",
        "conditions": [
            "Adjusted EBITDA rebuilt on a defensible addback basis before any indicative range is given.",
            "Caregiver hiring capacity confirmed at the branch level as the real growth constraint.",
            "Management build cost included in the use of funds, not treated as a synergy.",
        ],
    },
    "business_model": [
        "Hourly billing, private pay only — no Medicaid, Medicare or managed-care reimbursement exposure.",
        "Revenue is a function of caregiver hours available, not of demand: the constraint sits on the supply side.",
        "68% of revenue is recurring weekly care plans; the balance is episodic respite and one-time assessments.",
        "Rate increases have tracked wage inflation for three years, holding gross margin flat rather than expanding it.",
    ],
    "business_take": "This is a real business with a real moat on the payor side. The model is supply-constrained, which means every growth assumption has to be a hiring assumption.",
    "financial_take": "The growth is organic and volume-led, which is the good version. The concern is that three years of flat gross margin says pricing power is exactly sufficient to cover wages and no more.",
    "customer_take": "Referral diversification is genuine and it is the strongest single fact in this file. The caveat is that concentration by revenue understates how much of it runs through two personal relationships.",
    "quality_take": "Expect a QoE haircut. The recruiting addback is the tell — it is a recurring cost of running a high-turnover model, not a one-time item.",
    "forecast_take": "The plan is a demand-side plan for a supply-side business. Underwrite to the 8.4% run-rate and treat 15% as the upside case that the retention programme has to earn.",
}

# Shaped exactly like rainmaker_view._mps_table() output — the projection the
# executive review already renders. Two runs: the CIM-only run from stage 1 and
# the full-data-room run from stage 2, so the page shows the score movement.
MPS = {
    "mps_status": "ok",
    "threshold": 15,
    "verdict": "Above threshold",
    "n_scored": 7,
    "show_legend": True,
    "columns": [{"header": "CIM-only preview"}, {"header": "Full data room"}],
    "total_cells": ["19.4", "21.6"],
    "rows": [
        {"key": "founder_mindset", "display_name": "Founder / Owner Mindset", "evidence_marker": "\u25c7",
         "score_cells": [3, 3], "bullets": [
             {"kind": "rationale", "axis": None, "text": "Owner is engaged and has run the business for 17 years."},
             {"kind": "counter_evidence", "axis": None, "text": "No evidence yet of willingness to cede operating control; needs a management meeting."}]},
        {"key": "attractive_market", "display_name": "Attractive Market", "evidence_marker": None,
         "score_cells": [4, 4], "bullets": [
             {"kind": "sub_axis", "axis": "Demand", "text": "Ageing demographics and private-pay willingness in all three metros."},
             {"kind": "rationale", "axis": None, "text": "40+ sub-scale operators in radius support a platform thesis."}]},
        {"key": "quality_growth", "display_name": "Quality Growth", "evidence_marker": None,
         "score_cells": [3, 3], "bullets": [
             {"kind": "rationale", "axis": None, "text": "8.4% organic CAGR, all volume-led."},
             {"kind": "counter_evidence", "axis": None, "text": "Flat gross margin means growth is not creating operating leverage."}]},
        {"key": "systemic_risk", "display_name": "Manageable Systemic Risk", "evidence_marker": None,
         "score_cells": [4, 3], "bullets": [
             {"kind": "rationale", "axis": None, "text": "No reimbursement or regulatory payor risk — the key structural strength."},
             {"kind": "counter_evidence", "axis": None, "text": "Score cut on the full room: caregiver turnover at 38% and 41 unfilled shifts per week were only visible in the scheduling reports."}]},
        {"key": "untapped_growth", "display_name": "Untapped Growth Opportunities", "evidence_marker": None,
         "score_cells": [4, 4], "bullets": [
             {"kind": "rationale", "axis": None, "text": "Branch P&L discipline, scheduling, rate optimisation and tuck-in M&A all unexploited."}]},
        {"key": "transformational_equity", "display_name": "Transformational Equity", "evidence_marker": "\u25c7",
         "score_cells": [4, 4], "bullets": [
             {"kind": "rationale", "axis": None, "text": "Clear use of funds: management layer, systems, M&A."}]},
        {"key": "financeable", "display_name": "Financeable", "evidence_marker": "\u25c7",
         "score_cells": [3, 3], "bullets": [
             {"kind": "rationale", "axis": None, "text": "Indicated range implies 7-8x adjusted EBITDA before the QoE haircut."},
             {"kind": "counter_evidence", "axis": None, "text": "Lender appetite for home care is present but wage-pressure sensitive."}]},
    ],
}
