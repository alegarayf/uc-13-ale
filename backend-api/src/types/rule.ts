import { BaseApiModel, type BaseApiModelFields } from "./baseApiModel.js";

export const RULE_COMPARISONS = ["=", "<", ">", "<=", ">="] as const;

export type RuleComparison = (typeof RULE_COMPARISONS)[number];

export const RULE_STATUSES = ["active", "inactive"] as const;

export type RuleStatus = (typeof RULE_STATUSES)[number];

export interface RuleFields extends BaseApiModelFields {
  name: string;
  description: string | null;
  comparison: RuleComparison | null;
  minimum: number | null;
  maximum: number | null;
  uom: string | null;
  status: RuleStatus;
}

export class Rule extends BaseApiModel implements RuleFields {
  readonly name: string;
  readonly description: string | null;
  readonly comparison: RuleComparison | null;
  readonly minimum: number | null;
  readonly maximum: number | null;
  readonly uom: string | null;
  readonly status: RuleStatus;

  constructor(fields: RuleFields) {
    super(fields);
    this.name = fields.name;
    this.description = fields.description;
    this.comparison = fields.comparison;
    this.minimum = fields.minimum;
    this.maximum = fields.maximum;
    this.uom = fields.uom;
    this.status = fields.status;
  }
}

/** Fields clients may send when creating a rule (identity and audit fields are server-owned). */
export interface CreateRuleInput {
  name: string;
  description?: string | null;
  comparison?: RuleComparison | null;
  minimum?: number | null;
  maximum?: number | null;
  uom?: string | null;
  status?: RuleStatus;
  last_updated_by?: string | null;
}

/** Full replacement body for PUT (all business fields required). */
export interface ReplaceRuleInput {
  name: string;
  description?: string | null;
  comparison: RuleComparison | null;
  minimum?: number | null;
  maximum?: number | null;
  uom?: string | null;
  status: RuleStatus;
  last_updated_by?: string | null;
}

/** Partial update body for PATCH. */
export interface UpdateRuleInput {
  name?: string;
  description?: string | null;
  comparison?: RuleComparison | null;
  minimum?: number | null;
  maximum?: number | null;
  uom?: string | null;
  status?: RuleStatus;
  last_updated_by?: string | null;
}

/** Payload passed to the repository on insert (audit timestamps set by the repository). */
export interface RuleInsertPayload {
  name: string;
  description: string | null;
  comparison: RuleComparison | null;
  minimum: number | null;
  maximum: number | null;
  uom: string | null;
  status: RuleStatus;
  last_updated_by: string | null;
}

/** Mutable rule fields used on update/replace (excludes id and created_at). */
export type RuleMutableFields = Omit<RuleFields, keyof BaseApiModelFields | "created_at"> & {
  last_updated_by: string | null;
};
