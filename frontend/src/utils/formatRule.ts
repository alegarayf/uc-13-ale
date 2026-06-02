import type { Rule, RuleStatus } from "../types/rule.js";

interface RuleCondition {
  field?: string;
  operator?: string;
  value?: unknown;
}

function formatConditionsFromDefinition(ruleDefinition: string | null): string | null {
  if (!ruleDefinition?.trim()) return null;
  try {
    const def = JSON.parse(ruleDefinition) as { conditions?: unknown };
    if (!Array.isArray(def.conditions)) return null;
    const parts = def.conditions
      .filter((c): c is RuleCondition => typeof c === "object" && c !== null)
      .map((c) => {
        const field = c.field ?? "field";
        const op = c.operator ?? "?";
        const value = c.value != null ? String(c.value) : "";
        return `${field} ${op} ${value}`.trim();
      });
    return parts.length ? parts.join("; ") : null;
  } catch {
    return null;
  }
}

/** Short display text for a rule (summary or parsed conditions). */
export function formatRuleSummary(rule: Rule): string {
  if (rule.nl_summary?.trim()) return rule.nl_summary.trim();
  const fromDef = formatConditionsFromDefinition(rule.rule_definition);
  if (fromDef) return fromDef;
  return rule.description?.trim() || "—";
}

export function formatRuleStatusLabel(status: RuleStatus): string {
  return status === "active" ? "Active" : "Inactive";
}
