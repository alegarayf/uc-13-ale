import {
  Rule,
  RULE_COMPARISONS,
  RULE_STATUSES,
  type RuleComparison,
  type RuleFields,
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

function toNullableInt(value: unknown): number | null {
  if (value == null || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? Math.trunc(n) : null;
}

function toComparison(value: unknown): RuleComparison | null {
  if (value == null || value === "") return null;
  const s = String(value);
  if ((RULE_COMPARISONS as readonly string[]).includes(s)) {
    return s as RuleComparison;
  }
  return null;
}

function toStatus(value: unknown): RuleStatus {
  const s = String(value ?? "active").trim().toLowerCase();
  if ((RULE_STATUSES as readonly string[]).includes(s)) {
    return s as RuleStatus;
  }
  return "active";
}

export const RULE_SELECT_COLUMNS =
  "id, name, description, comparison, minimum, maximum, uom, status, created_at, updated_at, last_updated_by";

export function mapRowToRuleFields(row: Record<string, unknown>): RuleFields {
  return {
    id: Number(pickField(row, "id")),
    name: String(pickField(row, "name") ?? ""),
    description: toNullableString(pickField(row, "description")),
    comparison: toComparison(pickField(row, "comparison")),
    minimum: toNullableInt(pickField(row, "minimum")),
    maximum: toNullableInt(pickField(row, "maximum")),
    uom: toNullableString(pickField(row, "uom")),
    status: toStatus(pickField(row, "status")),
    created_at: toApiTimestamp(pickField(row, "created_at")),
    updated_at: toApiTimestamp(pickField(row, "updated_at")),
    last_updated_by: toNullableString(pickField(row, "last_updated_by")),
  };
}

export function mapRowToRule(row: Record<string, unknown>): Rule {
  return new Rule(mapRowToRuleFields(row));
}
