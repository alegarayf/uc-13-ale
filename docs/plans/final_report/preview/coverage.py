"""Panel-by-panel data coverage for the UC13 final report.

The single source of truth behind both stakeholder artifacts: the annotated
preview (which panels are backed by data today) and the "today" render (what the
same template produces when the panels with no producer stay empty).

Status vocabulary — deliberately three values, not two:

``ready``    the bundle field this panel reads is populated by an agent today.
``partial``  the panel renders, but one or more of its sub-fields has no producer.
``pending``  no agent populates this panel's field; it renders "not extracted".

Every ``pending`` carries the bundle path and the reason, so the list can be read
as a work list rather than as a complaint. Verified against ``field_mapping.py``,
``bundle_builder.py``, ``populate.py`` and ``constants.py`` on 2026-09-03 — see
``../final_report_plan.md`` §1.4/§1.5. T02 re-runs this audit properly and is
allowed to move entries from ``pending`` to ``ready``; when it does, update this
file in the same commit.
"""

from __future__ import annotations

# (page label, heading text as it appears in the render, status, bundle path, note)
PANELS: tuple[tuple[str, str, str, str, str], ...] = (
    # ---- Page 1 — cover -------------------------------------------------
    ("1 · Cover", "The Numbers That Drive The Call", "ready",
     "headline_metrics.*", "Headline tiles come from the financial agents."),
    ("1 · Cover", "Why This Could Work — Top 3", "ready",
     "narrative.thesis_bullets / executive.thesis_bullets", "Falls back to the bundle when the LLM layer degrades."),
    ("1 · Cover", "What Could Break It — Top 3", "ready",
     "narrative.key_watchouts", "Produced by the existing executive-review narrative."),
    ("1 · Cover", "Recommendation", "ready",
     "narrative.recommendation", "Structured verdict/rationale/conditions — built by T11."),

    # ---- Page 2 — contents ----------------------------------------------
    ("2 · Contents", "What this report answers", "ready",
     "(static)", "Fixed table of contents in the view module."),

    # ---- Page 3 — business and revenue model ----------------------------
    ("3 · Business model", "What The Business Does", "ready",
     "company_framing.overview_bullets", ""),
    ("3 · Business model", "How It Makes Money", "ready",
     "narrative.business_model", "Produced by the existing narrative."),
    ("3 · Business model", "Revenue mix — durability", "pending",
     "revenue_quality.revenue_type_mix", "No agent emits a recurring-vs-project split."),
    ("3 · Business model", "Client distribution", "pending",
     "revenue_quality.client_distribution", "Nearest existing field is `clients`; T02 checks whether the shape is compatible."),
    ("3 · Business model", "Performance By Branch", "pending",
     "financials.segment_performance", "Nearest existing field is `revenue_by_segment` (field_mapping.py:223); T02 checks the shape."),

    # ---- Page 4 — financial performance ---------------------------------
    ("4 · Financials", "P&amp;L Summary", "ready",
     "financials.table_rows", "The financial-trends agent populates this."),
    ("4 · Financials", "Revenue vs prior years, with EBITDA margin", "ready",
     "financials.table_rows", ""),
    ("4 · Financials", "Reported vs adjusted EBITDA", "ready",
     "financials.table_rows", ""),
    ("4 · Financials", "What the trend says", "ready",
     "financials.observations", ""),
    ("4 · Financials", "Growth bridge — latest period", "pending",
     "financials.growth_bridge", "No agent decomposes growth into a bridge."),

    # ---- Page 5 — customers ---------------------------------------------
    # Verified by rendering: _concentration() builds its bars from
    # revenue_quality.top_customers, NOT from concentration_summary — so the
    # chart goes dark with the top-customer list even though the Top 1 / Top 5
    # tiles above it stay populated.
    ("5 · Customers", "Concentration — share of revenue", "pending",
     "revenue_quality.top_customers", "The chart is built from the top-customer list (final_report_view.py:322); the Top 1 / Top 5 tiles come from concentration_summary and do render."),
    ("5 · Customers", "Retention and tenure", "partial",
     "revenue_quality.retention / customer_tenure", "NRR/GRR/churn are populated; average tenure has no producer."),
    ("5 · Customers", "Top Accounts", "pending",
     "revenue_quality.top_customers", "No producer found in the bundle layer."),

    # ---- Page 6 — KPIs ---------------------------------------------------
    ("6 · KPIs", "Operating KPIs against our screens", "ready",
     "kpi_dashboard + final_report_view._SCREENS", "The screens are constants in the view module (plan F-5)."),
    ("6 · KPIs", "Flagged — And What It Means", "ready",
     "kpi_dashboard", ""),
    ("6 · KPIs", "Screens we could not run", "ready",
     "kpi_dashboard", "This panel is itself the honest-gap panel."),

    # ---- Page 7 — quality of earnings + legal ---------------------------
    ("7 · Quality of earnings", "Reported to adjusted EBITDA", "pending",
     "qoe.addbacks", "Nearest existing field is `addback_schedule` (field_mapping.py:586); T02 checks the shape."),
    ("7 · Quality of earnings", "Earnings quality flags", "ready",
     "qoe.flags", ""),
    ("7 · Legal", "Contract and legal risk", "partial",
     "legal.top_flags / coc_consent_count", "Flags and section confidence are populated; the CoC-consent count has no producer."),

    # ---- Page 8 — forecast ----------------------------------------------
    ("8 · Forecast", "Plan vs Historical Run-Rate", "pending",
     "financials.forecast_rows", "Decision D-03: forecast_agent extracts this into analysis.forecast, but BundleBuilder reads six agent tables and forecast is not one of them."),
    ("8 · Forecast", "Assumptions that carry the plan", "pending",
     "financials.forecast_assumptions", "Same as above — decision D-03."),
    ("8 · Forecast", "Value creation levers", "ready",
     "company_framing.thesis.value_creation_levers", ""),

    # ---- Page 9 — risks and questions -----------------------------------
    ("9 · Risks", "Risks, mitigants and what to test first", "ready",
     "risks", ""),
    ("9 · Risks", "Top Questions For Management", "partial",
     "diligence_questions[].why_it_matters", "The questions are populated; the 'why it matters' column has no producer."),

    # ---- Page 10 — MPS ---------------------------------------------------
    ("10 · MPS", "Does this clear Rallyday's bar for further pursuit?", "ready",
     "analysis.mps_score", "Already shipping in the executive review. On the CIM branch this page gains a second score column."),

    # ---- Page 11 — appendix ---------------------------------------------
    ("11 · Appendix", "Data Room Gaps — Information Request", "ready",
     "data_room_gaps", ""),
    ("11 · Appendix", "Confidence By Area", "ready",
     "confidence_by_area", ""),
    ("11 · Appendix", "Sources Cited", "pending",
     "(citation index)", "Already renders its own 'not populated' line in the template."),
    ("11 · Appendix", "Run Manifest", "pending",
     "meta.manifest", "No producer found in the bundle layer."),
)

# Bundle paths with no producer today — what the "today" render must strip from
# the illustrative bundle so the honest version shows the real gaps.
STRIP_PATHS: tuple[tuple[str, ...], ...] = (
    ("financials", "segment_performance"),
    ("financials", "segment_dimension"),
    ("financials", "growth_bridge"),
    ("financials", "forecast_rows"),
    ("financials", "forecast_assumptions"),
    ("revenue_quality", "revenue_type_mix"),
    ("revenue_quality", "client_distribution"),
    ("revenue_quality", "top_customers"),
    ("revenue_quality", "client_count"),
    ("revenue_quality", "customer_tenure"),
    ("qoe", "addbacks"),
    ("legal", "coc_consent_count"),
)

# Per-item keys to strip from list-of-dict fields.
STRIP_ITEM_KEYS: tuple[tuple[str, str], ...] = (
    ("diligence_questions", "why_it_matters"),
)


def counts() -> dict[str, int]:
    out = {"ready": 0, "partial": 0, "pending": 0}
    for _, _, status, _, _ in PANELS:
        out[status] += 1
    return out
