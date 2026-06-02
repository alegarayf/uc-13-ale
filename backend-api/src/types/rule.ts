import { BaseApiModel, type BaseApiModelFields } from "./baseApiModel.js";

export const RULE_SOURCES = ["form", "ai"] as const;

export type RuleSource = (typeof RULE_SOURCES)[number];

export const RULE_STATUSES = ["active", "inactive"] as const;

export type RuleStatus = (typeof RULE_STATUSES)[number];

export interface RuleFields extends BaseApiModelFields {
  name: string;
  description: string | null;
  status: RuleStatus;
  rule_source: RuleSource;
  nl_prompt: string | null;
  nl_summary: string | null;
  rule_definition: string | null;
  python_source: string | null;
  python_entrypoint: string | null;
}

export class Rule extends BaseApiModel implements RuleFields {
  readonly name: string;
  readonly description: string | null;
  readonly status: RuleStatus;
  readonly rule_source: RuleSource;
  readonly nl_prompt: string | null;
  readonly nl_summary: string | null;
  readonly rule_definition: string | null;
  readonly python_source: string | null;
  readonly python_entrypoint: string | null;

  constructor(fields: RuleFields) {
    super(fields);
    this.name = fields.name;
    this.description = fields.description;
    this.status = fields.status;
    this.rule_source = fields.rule_source;
    this.nl_prompt = fields.nl_prompt;
    this.nl_summary = fields.nl_summary;
    this.rule_definition = fields.rule_definition;
    this.python_source = fields.python_source;
    this.python_entrypoint = fields.python_entrypoint;
  }
}

/** Fields clients may send when creating a rule (identity and audit fields are server-owned). */
export interface CreateRuleInput {
  name: string;
  description?: string | null;
  status?: RuleStatus;
  rule_source?: RuleSource;
  nl_prompt?: string | null;
  nl_summary?: string | null;
  rule_definition?: string | null;
  python_source?: string | null;
  python_entrypoint?: string | null;
  last_updated_by?: string | null;
}

/** Full replacement body for PUT (all business fields required). */
export interface ReplaceRuleInput {
  name: string;
  description?: string | null;
  status: RuleStatus;
  rule_source: RuleSource;
  nl_prompt?: string | null;
  nl_summary?: string | null;
  rule_definition?: string | null;
  python_source?: string | null;
  python_entrypoint?: string | null;
  last_updated_by?: string | null;
}

/** Partial update body for PATCH. */
export interface UpdateRuleInput {
  name?: string;
  description?: string | null;
  status?: RuleStatus;
  rule_source?: RuleSource;
  nl_prompt?: string | null;
  nl_summary?: string | null;
  rule_definition?: string | null;
  python_source?: string | null;
  python_entrypoint?: string | null;
  last_updated_by?: string | null;
}

/** Payload passed to the repository on insert (audit timestamps set by the repository). */
export interface RuleInsertPayload {
  name: string;
  description: string | null;
  status: RuleStatus;
  rule_source: RuleSource;
  nl_prompt: string | null;
  nl_summary: string | null;
  rule_definition: string | null;
  python_source: string | null;
  python_entrypoint: string | null;
  last_updated_by: string | null;
}

/** Mutable rule fields used on update/replace (excludes id and created_at). */
export type RuleMutableFields = Omit<RuleFields, keyof BaseApiModelFields | "created_at"> & {
  last_updated_by: string | null;
};
