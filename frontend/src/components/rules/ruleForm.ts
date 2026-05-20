import type { CreateRuleInput, ReplaceRuleInput, Rule, RuleComparison, RuleStatus } from "../../types/rule.js";

export const RULE_COMPARISON_OPTIONS: { value: RuleComparison; label: string }[] = [
  { value: "=", label: "= (equals)" },
  { value: "<", label: "< (less than)" },
  { value: ">", label: "> (greater than)" },
  { value: "<=", label: "≤ (at most)" },
  { value: ">=", label: "≥ (at least)" },
];

export interface RuleFormState {
  name: string;
  description: string;
  comparison: string;
  minimum: string;
  maximum: string;
  uom: string;
  status: RuleStatus;
}

export const EMPTY_RULE_FORM: RuleFormState = {
  name: "",
  description: "",
  comparison: "",
  minimum: "",
  maximum: "",
  uom: "",
  status: "active",
};

export function ruleToFormState(rule: Rule): RuleFormState {
  return {
    name: rule.name,
    description: rule.description ?? "",
    comparison: rule.comparison ?? "",
    minimum: rule.minimum != null ? String(rule.minimum) : "",
    maximum: rule.maximum != null ? String(rule.maximum) : "",
    uom: rule.uom ?? "",
    status: rule.status,
  };
}

export function parseOptionalInt(value: string): number | null | undefined {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const n = Number(trimmed);
  if (!Number.isInteger(n)) return undefined;
  return n;
}

export function formStateToCreateInput(
  form: RuleFormState,
  lastUpdatedBy: string,
): CreateRuleInput | { error: string } {
  const name = form.name.trim();
  if (!name) return { error: "Name is required." };

  const minimum = parseOptionalInt(form.minimum);
  const maximum = parseOptionalInt(form.maximum);
  if (minimum === undefined || maximum === undefined) {
    return { error: "Minimum and maximum must be whole numbers when provided." };
  }

  return {
    name,
    description: form.description.trim() || null,
    comparison: form.comparison ? (form.comparison as RuleComparison) : null,
    minimum,
    maximum,
    uom: form.uom.trim() || null,
    status: form.status,
    last_updated_by: lastUpdatedBy,
  };
}

export function formStateToReplaceInput(
  form: RuleFormState,
  lastUpdatedBy: string,
): ReplaceRuleInput | { error: string } {
  const base = formStateToCreateInput(form, lastUpdatedBy);
  if ("error" in base) return base;
  return {
    ...base,
    comparison: base.comparison ?? null,
    status: base.status ?? "active",
  };
}
