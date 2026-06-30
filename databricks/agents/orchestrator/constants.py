"""UC13 Orchestrator constants — Appendix B TL;DR field mapping (M1)."""

# Agent key → Delta table suffix under `{catalog}.analysis.*` (D-M2-8 single source)
AGENT_DELTA_TABLE_SUFFIXES: dict[str, str] = {
    "business_model": "business_model",
    "financial_trends": "financial_trends",
    "customer_quality": "customer_quality",
    "kpi": "kpi",
    "legal": "legal",
    "quality_of_earnings": "quality_of_earnings",
}

# Six workstream keys for meta.agents_present (not legal_contracts)
AGENTS_PRESENT_KEYS: tuple[str, ...] = (
    "business_model",
    "financial_trends",
    "customer_quality",
    "kpi",
    "legal",
    "quality_of_earnings",
)

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
