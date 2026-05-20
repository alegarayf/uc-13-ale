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
import {
  normalizeComparison,
  normalizeStatus,
  optionalInt,
  optionalNullableString,
  optionalString,
  requireLastUpdatedBy,
  requireNonEmptyString,
} from "./validation.js";

function toInsertPayload(body: CreateRuleInput): RuleInsertPayload {
  return {
    name: requireNonEmptyString(body.name, "name"),
    description: optionalString(body.description) ?? null,
    comparison: normalizeComparison(body.comparison),
    minimum: optionalInt(body.minimum, "minimum") ?? null,
    maximum: optionalInt(body.maximum, "maximum") ?? null,
    uom: optionalString(body.uom) ?? null,
    status: normalizeStatus(body.status),
    last_updated_by: requireLastUpdatedBy(body.last_updated_by),
  };
}

function toMutableFields(body: ReplaceRuleInput): RuleMutableFields {
  return {
    name: requireNonEmptyString(body.name, "name"),
    description: optionalString(body.description) ?? null,
    comparison: normalizeComparison(body.comparison),
    minimum: optionalInt(body.minimum, "minimum") ?? null,
    maximum: optionalInt(body.maximum, "maximum") ?? null,
    uom: optionalString(body.uom) ?? null,
    status: normalizeStatus(body.status, true),
    last_updated_by: requireLastUpdatedBy(body.last_updated_by),
  };
}

function patchToMutableFields(body: UpdateRuleInput): Partial<RuleMutableFields> {
  const patch: Partial<RuleMutableFields> = {};
  if (body.name !== undefined) patch.name = requireNonEmptyString(body.name, "name");
  if (body.description !== undefined) patch.description = optionalNullableString(body.description) ?? null;
  if (body.comparison !== undefined) patch.comparison = normalizeComparison(body.comparison, false);
  if (body.minimum !== undefined) patch.minimum = optionalInt(body.minimum, "minimum") ?? null;
  if (body.maximum !== undefined) patch.maximum = optionalInt(body.maximum, "maximum") ?? null;
  if (body.uom !== undefined) patch.uom = optionalNullableString(body.uom) ?? null;
  if (body.status !== undefined) patch.status = normalizeStatus(body.status, true);
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
    const updated = await this.repo.update(id, patch);
    if (!updated) throw new NotFoundError(`Rule not found: ${id}`);
    return updated;
  }

  async remove(id: number): Promise<void> {
    const deleted = await this.repo.delete(id);
    if (!deleted) throw new NotFoundError(`Rule not found: ${id}`);
  }
}
