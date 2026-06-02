import { CURRENT_USER } from "../constants/user.js";
import type { CreateRuleInput, ReplaceRuleInput } from "../types/rule.js";

interface PythonFunction {
  source?: string;
  entrypoint?: string;
}

function extractPython(ruleConfig: Record<string, unknown>): {
  python_source: string | null;
  python_entrypoint: string | null;
} {
  const pf = ruleConfig.python_function;
  if (!pf || typeof pf !== "object") {
    return { python_source: null, python_entrypoint: null };
  }
  const fn = pf as PythonFunction;
  return {
    python_source: typeof fn.source === "string" ? fn.source : null,
    python_entrypoint: typeof fn.entrypoint === "string" ? fn.entrypoint : null,
  };
}

function displayName(ruleConfig: Record<string, unknown>): string {
  const raw = ruleConfig.name;
  if (typeof raw === "string" && raw.trim()) {
    return raw.trim().slice(0, 255);
  }
  return "AI rule";
}

function descriptionFromRuleConfig(
  ruleConfig: Record<string, unknown>,
  nlSummary: string,
): string | null {
  const fromConfig = ruleConfig.description;
  if (typeof fromConfig === "string" && fromConfig.trim()) {
    return fromConfig.trim();
  }
  const summary = nlSummary.trim();
  return summary || null;
}

export function buildAiRuleCreateInput(
  nlPrompt: string,
  nlSummary: string,
  ruleConfig: Record<string, unknown>,
): CreateRuleInput {
  const python = extractPython(ruleConfig);
  return {
    name: displayName(ruleConfig),
    description: descriptionFromRuleConfig(ruleConfig, nlSummary),
    status: "active",
    rule_source: "ai",
    nl_prompt: nlPrompt.trim(),
    nl_summary: nlSummary.trim(),
    rule_definition: JSON.stringify(ruleConfig),
    python_source: python.python_source,
    python_entrypoint: python.python_entrypoint,
    last_updated_by: CURRENT_USER.displayName,
  };
}

export function buildAiRuleReplaceInput(
  nlPrompt: string,
  nlSummary: string,
  ruleConfig: Record<string, unknown>,
  status: "active" | "inactive" = "active",
): ReplaceRuleInput {
  const python = extractPython(ruleConfig);
  return {
    name: displayName(ruleConfig),
    description: descriptionFromRuleConfig(ruleConfig, nlSummary),
    status,
    rule_source: "ai",
    nl_prompt: nlPrompt.trim(),
    nl_summary: nlSummary.trim(),
    rule_definition: JSON.stringify(ruleConfig),
    python_source: python.python_source,
    python_entrypoint: python.python_entrypoint,
    last_updated_by: CURRENT_USER.displayName,
  };
}
