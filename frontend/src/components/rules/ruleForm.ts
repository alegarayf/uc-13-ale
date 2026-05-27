import type { CreateRuleInput, ReplaceRuleInput, Rule, RuleStatus } from "../../types/rule.js";

export interface RuleFormState {
  name: string;
  description: string;
  status: RuleStatus;
}

export const EMPTY_RULE_FORM: RuleFormState = {
  name: "",
  description: "",
  status: "active",
};

export function ruleToFormState(rule: Rule): RuleFormState {
  return {
    name: rule.name,
    description: rule.description ?? "",
    status: rule.status,
  };
}

export function buildCreatePayload(
  form: RuleFormState,
  lastUpdatedBy: string,
): { payload?: CreateRuleInput; error?: string } {
  const name = form.name.trim();
  if (!name) return { error: "Name is required." };

  return {
    payload: {
      name,
      description: form.description.trim() || null,
      status: form.status,
      rule_source: "form",
      last_updated_by: lastUpdatedBy,
    },
  };
}

export function buildReplacePayload(
  form: RuleFormState,
  lastUpdatedBy: string,
): { payload?: ReplaceRuleInput; error?: string } {
  const name = form.name.trim();
  if (!name) return { error: "Name is required." };

  return {
    payload: {
      name,
      description: form.description.trim() || null,
      status: form.status,
      rule_source: "form",
      last_updated_by: lastUpdatedBy,
    },
  };
}
