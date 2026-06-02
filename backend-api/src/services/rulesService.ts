import { NotFoundError, ValidationError } from "../errors/httpErrors.js";
import type { RulesRepository } from "../repositories/rulesRepository.js";
import {
  Rule,
  type CreateRuleInput,
  type ReplaceRuleInput,
  type RuleInsertPayload,
  type RuleMutableFields,
  type UpdateRuleInput,
} from "../types/rule.js";
import { pythonFromRuleDefinitionJson } from "./ruleDefinition.js";
import {
  normalizeRuleSource,
  normalizeStatus,
  optionalNullableString,
  optionalString,
  requireLastUpdatedBy,
  requireNonEmptyString,
} from "./validation.js";

function enrichPythonFields(payload: RuleInsertPayload): RuleInsertPayload {
  if (payload.python_source && payload.python_entrypoint) {
    return payload;
  }
  const extracted = pythonFromRuleDefinitionJson(payload.rule_definition);
  return {
    ...payload,
    python_source: payload.python_source ?? extracted.python_source,
    python_entrypoint: payload.python_entrypoint ?? extracted.python_entrypoint,
  };
}

function toInsertPayload(body: CreateRuleInput): RuleInsertPayload {
  const ruleDefinition = optionalNullableString(body.rule_definition) ?? null;
  const payload: RuleInsertPayload = {
    name: requireNonEmptyString(body.name, "name"),
    description: optionalString(body.description) ?? null,
    status: normalizeStatus(body.status),
    rule_source: normalizeRuleSource(body.rule_source),
    nl_prompt: optionalNullableString(body.nl_prompt) ?? null,
    nl_summary: optionalNullableString(body.nl_summary) ?? null,
    rule_definition: ruleDefinition,
    python_source: optionalNullableString(body.python_source) ?? null,
    python_entrypoint: optionalNullableString(body.python_entrypoint) ?? null,
    last_updated_by: requireLastUpdatedBy(body.last_updated_by),
  };
  return enrichPythonFields(payload);
}

function toMutableFields(body: ReplaceRuleInput): RuleMutableFields {
  const ruleDefinition = optionalNullableString(body.rule_definition) ?? null;
  const payload: RuleMutableFields = {
    name: requireNonEmptyString(body.name, "name"),
    description: optionalString(body.description) ?? null,
    status: normalizeStatus(body.status, true),
    rule_source: normalizeRuleSource(body.rule_source, true),
    nl_prompt: optionalNullableString(body.nl_prompt) ?? null,
    nl_summary: optionalNullableString(body.nl_summary) ?? null,
    rule_definition: ruleDefinition,
    python_source: optionalNullableString(body.python_source) ?? null,
    python_entrypoint: optionalNullableString(body.python_entrypoint) ?? null,
    last_updated_by: requireLastUpdatedBy(body.last_updated_by),
  };
  return enrichPythonFields(payload);
}

function patchToMutableFields(body: UpdateRuleInput): Partial<RuleMutableFields> {
  const patch: Partial<RuleMutableFields> = {};
  if (body.name !== undefined) patch.name = requireNonEmptyString(body.name, "name");
  if (body.description !== undefined) patch.description = optionalNullableString(body.description) ?? null;
  if (body.status !== undefined) patch.status = normalizeStatus(body.status, true);
  if (body.rule_source !== undefined) patch.rule_source = normalizeRuleSource(body.rule_source, true);
  if (body.nl_prompt !== undefined) patch.nl_prompt = optionalNullableString(body.nl_prompt) ?? null;
  if (body.nl_summary !== undefined) patch.nl_summary = optionalNullableString(body.nl_summary) ?? null;
  if (body.rule_definition !== undefined) {
    patch.rule_definition = optionalNullableString(body.rule_definition) ?? null;
  }
  if (body.python_source !== undefined) {
    patch.python_source = optionalNullableString(body.python_source) ?? null;
  }
  if (body.python_entrypoint !== undefined) {
    patch.python_entrypoint = optionalNullableString(body.python_entrypoint) ?? null;
  }
  if (body.last_updated_by !== undefined) {
    patch.last_updated_by = requireLastUpdatedBy(body.last_updated_by);
  }
  return patch;
}

export class RulesService {
  constructor(private readonly repo: RulesRepository) {}

  async list(): Promise<Rule[]> {
    return this.repo.findAll();
  }

  async getById(id: number): Promise<Rule> {
    const rule = await this.repo.findById(id);
    if (!rule) throw new NotFoundError(`Rule not found: ${id}`);
    return rule;
  }

  async create(body: CreateRuleInput): Promise<Rule> {
    return this.repo.create(toInsertPayload(body));
  }

  async replace(id: number, body: ReplaceRuleInput): Promise<Rule> {
    const updated = await this.repo.replace(id, toMutableFields(body));
    if (!updated) throw new NotFoundError(`Rule not found: ${id}`);
    return updated;
  }

  async patch(id: number, body: UpdateRuleInput): Promise<Rule> {
    if (!body || typeof body !== "object" || Object.keys(body).length === 0) {
      throw new ValidationError("request body must include at least one field to update");
    }
    const patch = patchToMutableFields(body);
    if (Object.keys(patch).length === 0) {
      throw new ValidationError("request body must include at least one field to update");
    }
    const existing = await this.repo.findById(id);
    if (!existing) throw new NotFoundError(`Rule not found: ${id}`);
    const merged = enrichPythonFields({
      ...mergePatch(existing, patch),
    } as RuleMutableFields);
    const updated = await this.repo.replace(id, merged);
    if (!updated) throw new NotFoundError(`Rule not found: ${id}`);
    return updated;
  }

  async remove(id: number): Promise<void> {
    const deleted = await this.repo.delete(id);
    if (!deleted) throw new NotFoundError(`Rule not found: ${id}`);
  }
}

function mergePatch(existing: Rule, patch: Partial<RuleMutableFields>): RuleMutableFields {
  return {
    name: patch.name ?? existing.name,
    description: patch.description !== undefined ? patch.description : existing.description,
    status: patch.status !== undefined ? patch.status : existing.status,
    rule_source: patch.rule_source !== undefined ? patch.rule_source : existing.rule_source,
    nl_prompt: patch.nl_prompt !== undefined ? patch.nl_prompt : existing.nl_prompt,
    nl_summary: patch.nl_summary !== undefined ? patch.nl_summary : existing.nl_summary,
    rule_definition:
      patch.rule_definition !== undefined ? patch.rule_definition : existing.rule_definition,
    python_source: patch.python_source !== undefined ? patch.python_source : existing.python_source,
    python_entrypoint:
      patch.python_entrypoint !== undefined
        ? patch.python_entrypoint
        : existing.python_entrypoint,
    last_updated_by:
      patch.last_updated_by !== undefined ? patch.last_updated_by : existing.last_updated_by,
  };
}
