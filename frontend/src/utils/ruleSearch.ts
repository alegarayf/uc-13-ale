import type { NlRuleConfigListItem } from "../types/nlRule.js";
import type { Rule } from "../types/rule.js";
import { formatRuleCriteria, formatRuleStatusLabel } from "./formatRule.js";

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
    formatRuleCriteria(rule),
    formatRuleStatusLabel(rule.status),
    rule.status,
    String(rule.id),
    rule.uom ?? "",
    rule.comparison ?? "",
    rule.minimum != null ? String(rule.minimum) : "",
    rule.maximum != null ? String(rule.maximum) : "",
  ];
  return fields.some((field) => fieldMatches(field, query));
}

export function nlRuleMatchesSearch(row: NlRuleConfigListItem, query: string): boolean {
  if (!query) return true;
  const fields = [
    row.name ?? "",
    row.summary ?? "",
    row.filename,
    row.id ?? "",
    row.createdAt ?? "",
    row.updatedAt ?? "",
  ];
  return fields.some((field) => fieldMatches(field, query));
}
