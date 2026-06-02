/** Shared audit fields returned on all API entities. */
export interface BaseApiModel {
  id: number;
  created_at: string;
  updated_at: string;
  last_updated_by: string | null;
}

export type RuleSource = "form" | "ai";

export type RuleStatus = "active" | "inactive";

export interface Rule extends BaseApiModel {
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

export interface ApiListResponse<T> {
  data: T[];
}

export interface ApiItemResponse<T> {
  data: T;
}

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

/** Full replacement body for PUT /api/rules/:id */
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

export interface ApiErrorBody {
  error: {
    message: string;
    code?: string;
  };
}
