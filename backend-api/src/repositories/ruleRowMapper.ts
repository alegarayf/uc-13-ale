import {
  Rule,
  RULE_SOURCES,
  RULE_STATUSES,
  type RuleFields,
  type RuleSource,
  type RuleStatus,
} from "../types/rule.js";
import type { ApiTimestamp } from "../types/baseApiModel.js";

function pickField(row: Record<string, unknown>, key: string): unknown {
  if (key in row) return row[key];
  const upper = key.toUpperCase();
  if (upper in row) return row[upper];
  return undefined;
}

function toApiTimestamp(value: unknown): ApiTimestamp {
  if (value instanceof Date) return value.toISOString();
  if (typeof value === "string") return value;
  if (value == null) return new Date(0).toISOString();
  return String(value);
}

function toNullableString(value: unknown): string | null {
  if (value == null) return null;
  return String(value);
}

function toRuleSource(value: unknown): RuleSource {
  const s = String(value ?? "form").trim().toLowerCase();
  if ((RULE_SOURCES as readonly string[]).includes(s)) {
    return s as RuleSource;
  }
  return "form";
}

function toStatus(value: unknown): RuleStatus {
  const s = String(value ?? "active").trim().toLowerCase();
  if ((RULE_STATUSES as readonly string[]).includes(s)) {
    return s as RuleStatus;
  }
  return "active";
}

export const RULE_SELECT_COLUMNS =
  "id, name, description, status, rule_source, nl_prompt, nl_summary, rule_definition, python_source, python_entrypoint, created_at, updated_at, last_updated_by";

export function mapRowToRuleFields(row: Record<string, unknown>): RuleFields {
  return {
    id: Number(pickField(row, "id")),
    name: String(pickField(row, "name") ?? ""),
    description: toNullableString(pickField(row, "description")),
    status: toStatus(pickField(row, "status")),
    rule_source: toRuleSource(pickField(row, "rule_source")),
    nl_prompt: toNullableString(pickField(row, "nl_prompt")),
    nl_summary: toNullableString(pickField(row, "nl_summary")),
    rule_definition: toNullableString(pickField(row, "rule_definition")),
    python_source: toNullableString(pickField(row, "python_source")),
    python_entrypoint: toNullableString(pickField(row, "python_entrypoint")),
    created_at: toApiTimestamp(pickField(row, "created_at")),
    updated_at: toApiTimestamp(pickField(row, "updated_at")),
    last_updated_by: toNullableString(pickField(row, "last_updated_by")),
  };
}

export function mapRowToRule(row: Record<string, unknown>): Rule {
  return new Rule(mapRowToRuleFields(row));
}
