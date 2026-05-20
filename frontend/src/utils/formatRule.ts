import type { Rule, RuleStatus } from "../types/rule.js";

/** Human-readable criteria: comparison + bounds + unit of measure. */
export function formatRuleCriteria(rule: Rule): string {
  const { comparison, minimum, maximum, uom } = rule;
  if (comparison == null && minimum == null && maximum == null && !uom) {
    return "—";
  }

  const parts: string[] = [];
  if (comparison) parts.push(comparison);

  if (minimum != null && maximum != null) {
    parts.push(`${minimum.toLocaleString()} – ${maximum.toLocaleString()}`);
  } else if (minimum != null) {
    parts.push(minimum.toLocaleString());
  } else if (maximum != null) {
    parts.push(maximum.toLocaleString());
  }

  if (uom) parts.push(uom);
  const text = parts.join(" ").trim();
  return text || "—";
}

export function formatRuleStatusLabel(status: RuleStatus): string {
  return status === "active" ? "Active" : "Inactive";
}
