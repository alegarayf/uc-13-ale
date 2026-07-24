"""UC13 Orchestrator Volume path helpers (M1)."""


def company_safe(company_name: str) -> str:
    """Normalize company name for Volume path segments (D-M1-2)."""
    return company_name.replace(" ", "_").replace("/", "_")


def reports_volume_dir(catalog: str, company_name: str) -> str:
    """Return the UC Volume directory for orchestrator + agent reports."""
    return f"/Volumes/{catalog}/analysis/reports/{company_safe(company_name)}"
