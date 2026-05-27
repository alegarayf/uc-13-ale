import ast
import re
from typing import Any

from app.opportunity_silver_fields import (
    normalize_field_name,
    normalize_rule_config,
    python_source_uses_only_allowed_fields,
    snake_to_pascal_field,
)


def _sanitize_function_name(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_]", "_", name.strip().lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    if not slug or slug[0].isdigit():
        slug = f"rule_{slug}" if slug else "evaluate_opportunity_rule"
    if not slug.startswith("evaluate_"):
        slug = f"evaluate_{slug}"
    return slug[:80]


def _field_access(field: str) -> str | None:
    canonical = normalize_field_name(field)
    if not canonical:
        return None
    pascal = snake_to_pascal_field(canonical)
    return f"opportunity['{pascal}']"


def _condition_to_python(condition: dict[str, Any]) -> str | None:
    field = condition.get("field")
    operator = condition.get("operator")
    value = condition.get("value")
    if not field or operator is None:
        return None

    access = _field_access(str(field))
    if not access:
        return None
    op = str(operator).strip()

    if op in ("=", "==", "equals"):
        return f"{access} == {repr(value)}"
    if op in ("!=", "not_equals"):
        return f"{access} != {repr(value)}"
    if op in (">", "greater_than"):
        return f"{access} is not None and {access} > {repr(value)}"
    if op in (">=", "greater_than_or_equal"):
        return f"{access} is not None and {access} >= {repr(value)}"
    if op in ("<", "less_than"):
        return f"{access} is not None and {access} < {repr(value)}"
    if op in ("<=", "less_than_or_equal"):
        return f"{access} is not None and {access} <= {repr(value)}"
    if op in ("in", "contains"):
        return f"{repr(value)} in ({access} or [])"
    if op in ("matches_intent",):
        return None
    return f"# Unsupported operator {op!r} for field {field!r}"


def generate_python_function(
    rule_config: dict[str, Any],
    *,
    user_prompt: str,
    summary: str,
) -> dict[str, str]:
    """Build an extractable python_function block for saved rule JSON."""
    name = str(rule_config.get("name") or "opportunity_rule")
    func_name = _sanitize_function_name(name)
    description = str(rule_config.get("description") or summary or user_prompt).strip()
    conditions = rule_config.get("conditions")
    if not isinstance(conditions, list):
        conditions = []

    checks: list[str] = []
    for cond in conditions:
        if not isinstance(cond, dict):
            continue
        expr = _condition_to_python(cond)
        if expr and not expr.startswith("#"):
            checks.append(expr)

    if checks:
        lines = []
        for expr in checks:
            lines.append(f"if not ({expr}):")
            lines.append(f"            return _fail({expr!r})")
        condition_block = "\n        ".join(lines)
        logic = f"""{condition_block}
        return _pass("All conditions satisfied.")"""
    else:
        logic = f"""# Rule intent (no structured conditions): {description[:500]}
        return _pass("Rule evaluated (no structured conditions to enforce).")"""

    source = f'''def {func_name}(opportunity: dict) -> dict:
    """
    {description[:800]}
    """
    def _pass(reason: str) -> dict:
        return {{"passed": True, "reason": reason, "rule": {name!r}}}

    def _fail(reason: str) -> dict:
        return {{"passed": False, "reason": reason, "rule": {name!r}}}

    if not isinstance(opportunity, dict):
        return _fail("opportunity must be a dict")

    try:
        {logic}
    except Exception as exc:  # noqa: BLE001
        return _fail(f"Rule evaluation error: {{exc}}")
'''

    ast.parse(source)
    return {
        "language": "python",
        "version": "3.11",
        "entrypoint": func_name,
        "source": source,
    }


def ensure_rule_python_function(
    rule_config: dict[str, Any],
    *,
    user_prompt: str,
    summary: str,
) -> dict[str, Any]:
    """Attach or replace python_function on rule_config; return updated rule dict."""
    enriched = normalize_rule_config(rule_config)
    existing = enriched.get("python_function")
    if isinstance(existing, dict) and existing.get("source"):
        source = str(existing["source"])
        try:
            ast.parse(source)
            if python_source_uses_only_allowed_fields(source):
                return enriched
        except SyntaxError:
            pass

    enriched["python_function"] = generate_python_function(
        enriched,
        user_prompt=user_prompt,
        summary=summary,
    )
    return enriched
