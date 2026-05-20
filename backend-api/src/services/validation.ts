import { ValidationError } from "../errors/httpErrors.js";
import { RULE_COMPARISONS, RULE_STATUSES, type RuleComparison, type RuleStatus } from "../types/rule.js";

export function requireNonEmptyString(value: unknown, field: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new ValidationError(`${field} is required`);
  }
  return value.trim();
}

export function optionalString(value: unknown): string | null | undefined {
  if (value === undefined) return undefined;
  if (value === null) return null;
  if (typeof value !== "string") {
    throw new ValidationError("expected a string or null");
  }
  return value;
}

export function optionalNullableString(value: unknown): string | null | undefined {
  if (value === undefined) return undefined;
  return optionalString(value) ?? null;
}

export function optionalInt(value: unknown, field: string): number | null | undefined {
  if (value === undefined) return undefined;
  if (value === null) return null;
  if (typeof value !== "number" || !Number.isInteger(value)) {
    throw new ValidationError(`${field} must be an integer or null`);
  }
  return value;
}

export function normalizeComparison(value: unknown, required = false): RuleComparison | null {
  if (value === undefined || value === null || value === "") {
    if (required) throw new ValidationError(`comparison must be one of: ${RULE_COMPARISONS.join(", ")}`);
    return null;
  }
  if (typeof value !== "string") {
    throw new ValidationError(`comparison must be one of: ${RULE_COMPARISONS.join(", ")}`);
  }
  const trimmed = value.trim();
  if (!(RULE_COMPARISONS as readonly string[]).includes(trimmed)) {
    throw new ValidationError(`comparison must be one of: ${RULE_COMPARISONS.join(", ")}`);
  }
  return trimmed as RuleComparison;
}

export function normalizeStatus(value: unknown, required = false): RuleStatus {
  if (value === undefined || value === null || value === "") {
    if (required) {
      throw new ValidationError(`status must be one of: ${RULE_STATUSES.join(", ")}`);
    }
    return "active";
  }
  if (typeof value !== "string") {
    throw new ValidationError(`status must be one of: ${RULE_STATUSES.join(", ")}`);
  }
  const trimmed = value.trim().toLowerCase();
  if (!(RULE_STATUSES as readonly string[]).includes(trimmed)) {
    throw new ValidationError(`status must be one of: ${RULE_STATUSES.join(", ")}`);
  }
  return trimmed as RuleStatus;
}

export function requireLastUpdatedBy(value: unknown): string | null {
  if (value === undefined || value === null) return null;
  if (typeof value !== "string") {
    throw new ValidationError("last_updated_by must be a string or null");
  }
  const trimmed = value.trim();
  return trimmed.length ? trimmed : null;
}
