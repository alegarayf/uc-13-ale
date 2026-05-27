export interface PythonFromDefinition {
  python_source: string | null;
  python_entrypoint: string | null;
}

/** Extract python_function from a parsed rule_definition object. */
export function pythonFromRuleDefinitionObject(
  definition: unknown,
): PythonFromDefinition {
  if (!definition || typeof definition !== "object") {
    return { python_source: null, python_entrypoint: null };
  }
  const pf = (definition as Record<string, unknown>).python_function;
  if (!pf || typeof pf !== "object") {
    return { python_source: null, python_entrypoint: null };
  }
  const record = pf as Record<string, unknown>;
  const source = typeof record.source === "string" ? record.source : null;
  const entrypoint = typeof record.entrypoint === "string" ? record.entrypoint : null;
  return { python_source: source, python_entrypoint: entrypoint };
}

export function pythonFromRuleDefinitionJson(
  ruleDefinition: string | null | undefined,
): PythonFromDefinition {
  if (!ruleDefinition?.trim()) {
    return { python_source: null, python_entrypoint: null };
  }
  try {
    return pythonFromRuleDefinitionObject(JSON.parse(ruleDefinition));
  } catch {
    return { python_source: null, python_entrypoint: null };
  }
}
