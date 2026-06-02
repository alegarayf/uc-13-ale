"""Canonical fields on salesforce_silver.opportunity_silver (company / opportunity records)."""

from __future__ import annotations

import re
from typing import Any

# Keep in sync with backend-api/src/types/company.ts and frontend companyDetailFields.ts
OPPORTUNITY_SILVER_VIEW = "salesforce_silver.opportunity_silver"

OPPORTUNITY_SILVER_FIELDS: tuple[str, ...] = (
    "id",
    "project_name",
    "account_name",
    "industry",
    "annual_revenue",
    "employee_head_count",
    "year_founded",
    "ebitda",
    "ebitda_margin",
    "days_since_last_activity",
    "website",
    "source_scrub_url",
    "linked_in_company_id",
    "zoom_info_company_id",
    "growth_rate_12_months",
    "growth_rate_9_months",
    "growth_rate_6_months",
    "investors",
    "name",
    "description",
    "stage_name",
    "type",
    "lead_source",
    "opportunity_owner",
    "opportunity_owner_role",
    "opportunity_owner_email",
    "status",
)

_ALLOWED = frozenset(OPPORTUNITY_SILVER_FIELDS)

# Common aliases / model mistakes -> canonical snake_case column
_FIELD_ALIASES: dict[str, str] = {
    "annualrevenue": "annual_revenue",
    "annual_revenues": "annual_revenue",
    "revenue": "annual_revenue",
    "arr": "annual_revenue",
    "employeeheadcount": "employee_head_count",
    "employees": "employee_head_count",
    "headcount": "employee_head_count",
    "yearfounded": "year_founded",
    "ebitdamargin": "ebitda_margin",
    "growthrate12months": "growth_rate_12_months",
    "growthrate9months": "growth_rate_9_months",
    "growthrate6months": "growth_rate_6_months",
    "stagename": "stage_name",
    "leadsource": "lead_source",
    "opportunityowner": "opportunity_owner",
    "opportunityowneremail": "opportunity_owner_email",
    "projectname": "project_name",
    "accountname": "account_name",
    "linkedincompanyid": "linked_in_company_id",
    "zoominfocompanyid": "zoom_info_company_id",
    "sourcescruburl": "source_scrub_url",
    "dayssincelastactivity": "days_since_last_activity",
}


def snake_to_pascal_field(field: str) -> str:
    """Map canonical snake_case column to PascalCase dict key for Python bracket access."""
    return "".join(part.capitalize() for part in field.split("_"))


def opportunity_silver_fields_prompt_block() -> str:
    """Text block for LLM prompts listing allowed columns."""
    examples = ", ".join(
        f"{f} -> opportunity['{snake_to_pascal_field(f)}']" for f in ("annual_revenue", "employee_head_count", "stage_name")
    )
    return (
        f"Allowed opportunity record fields from {OPPORTUNITY_SILVER_VIEW}:\n"
        f"- In JSON conditions: use snake_case keys only ({', '.join(OPPORTUNITY_SILVER_FIELDS[:6])}, …).\n"
        f"- In Python: use bracket access with PascalCase keys only, never .get(). Examples: {examples}."
    )


def _camel_to_snake(name: str) -> str:
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    s2 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1)
    return s2.replace("-", "_").replace(" ", "_").lower()


def normalize_field_name(field: str) -> str | None:
    """Map a field reference to a valid opportunity_silver column, or None."""
    raw = field.strip()
    if not raw:
        return None
    if raw in _ALLOWED:
        return raw

    snake = _camel_to_snake(raw)
    if snake in _ALLOWED:
        return snake

    compact = re.sub(r"[_\s-]+", "", raw).lower()
    if compact in _FIELD_ALIASES:
        return _FIELD_ALIASES[compact]

    if snake.replace("_", "") in _FIELD_ALIASES:
        return _FIELD_ALIASES[snake.replace("_", "")]

    return None


def extract_opportunity_get_fields(source: str) -> set[str]:
    return set(re.findall(r"""opportunity\.get\(\s*['"]([^'"]+)['"]""", source))


def extract_opportunity_bracket_fields(source: str) -> set[str]:
    return set(re.findall(r"""opportunity\[\s*['"]([^'"]+)['"]\s*\]""", source))


def python_source_uses_only_allowed_fields(source: str) -> bool:
    """True when opportunity field access uses only allowed columns (bracket PascalCase or legacy .get snake_case)."""
    if extract_opportunity_get_fields(source):
        return False
    bracket_refs = extract_opportunity_bracket_fields(source)
    if not bracket_refs:
        return True
    return all(normalize_field_name(ref) is not None for ref in bracket_refs)


def normalize_conditions(conditions: list[Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Return normalized conditions and dropped field names."""
    normalized: list[dict[str, Any]] = []
    dropped: list[str] = []

    for item in conditions:
        if not isinstance(item, dict):
            continue
        raw_field = item.get("field")
        if not raw_field:
            continue
        canonical = normalize_field_name(str(raw_field))
        if not canonical:
            dropped.append(str(raw_field))
            continue
        next_cond = dict(item)
        next_cond["field"] = canonical
        normalized.append(next_cond)

    return normalized, dropped


def normalize_rule_config(rule_config: dict[str, Any]) -> dict[str, Any]:
    """Ensure conditions and metadata only reference opportunity_silver columns."""
    out = dict(rule_config)
    conditions = out.get("conditions")
    if isinstance(conditions, list):
        normalized, dropped = normalize_conditions(conditions)
        out["conditions"] = normalized
        if dropped:
            meta = out.get("metadata")
            if not isinstance(meta, dict):
                meta = {}
            meta = dict(meta)
            meta["dropped_invalid_fields"] = dropped
            out["metadata"] = meta

    out["opportunity_schema"] = {
        "view": OPPORTUNITY_SILVER_VIEW,
        "fields": list(OPPORTUNITY_SILVER_FIELDS),
    }
    return out
