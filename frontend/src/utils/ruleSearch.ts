import type { Rule } from "../types/rule.js";
import { formatRuleStatusLabel, formatRuleSummary } from "./formatRule.js";

export function normalizeRuleSearchQuery(query: string): string {
  return query.trim().toLowerCase();
}

function fieldMatches(value: string, query: string): boolean {
  return value.toLowerCase().includes(query);
}

export function ruleMatchesSearch(rule: Rule, query: string): boolean {
  if (!query) return true;
  const fields = [
    rule.name,
    rule.description ?? "",
    rule.nl_prompt ?? "",
    rule.nl_summary ?? "",
    rule.rule_definition ?? "",
    rule.python_entrypoint ?? "",
    formatRuleSummary(rule),
    formatRuleStatusLabel(rule.status),
    rule.status,
    rule.rule_source,
    String(rule.id),
  ];
  return fields.some((field) => fieldMatches(field, query));
}

export function isAiRule(rule: Rule): boolean {
  return rule.rule_source === "ai";
}
