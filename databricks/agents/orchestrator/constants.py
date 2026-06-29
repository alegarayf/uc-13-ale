"""UC13 Orchestrator constants — Appendix B TL;DR field mapping (M1)."""

# Appendix B — TL;DR required bundle dot-paths (synthesis_gaps + demo_walkthrough gates)
TLDR_REQUIRED_FIELDS: list[str] = [
    "meta.company_name",
    "meta.vertical_overlay",
    "executive.in_one_line",
    "headline_metrics.ltm_revenue",
    "headline_metrics.ltm_ebitda_margin_pct",
    "headline_metrics.revenue_cagr",
    "company_framing.revenue_model.quality_flag",
    "financials.table_rows",
    "revenue_quality.concentration",
    "kpi_dashboard[]",
    "legal.assessed_count",
    "risks[]",
    "diligence_questions[]",
    "data_room_gaps[]",
    "confidence_by_area",
    "company_framing.thesis.bullets",
    "headline_metrics.*",
]

# Appendix B — typical Elder Care fill_state (path → expected enum for apply_fill_state)
# Omitted where Appendix B has no single enum (e.g. kpi_dashboard[] = "mixed").
FILL_STATE_RULES: dict[str, str] = {
    "meta.company_name": "filled_cited",
    "meta.vertical_overlay": "filled_cited",
    "executive.in_one_line": "filled_synthesized",
    "headline_metrics.ltm_revenue": "filled_cited",
    "headline_metrics.ltm_ebitda_margin_pct": "filled_cited",
    "headline_metrics.revenue_cagr": "filled_cited",
    "company_framing.revenue_model.quality_flag": "filled_cited",
    "financials.table_rows": "filled_cited",
    "revenue_quality.concentration": "gap_correct",
    "legal.assessed_count": "filled_cited",
    "risks[]": "filled_synthesized",
    "diligence_questions[]": "filled_synthesized",
    "data_room_gaps[]": "filled_cited",
    "confidence_by_area": "filled_synthesized",
    "company_framing.thesis.bullets": "not_attempted",
    "headline_metrics.*": "not_attempted",
}
