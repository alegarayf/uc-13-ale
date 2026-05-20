/** Shared audit fields returned on all API entities. */
export interface BaseApiModel {
  id: number;
  created_at: string;
  updated_at: string;
  last_updated_by: string | null;
}

export type RuleComparison = "=" | "<" | ">" | "<=" | ">=";

export type RuleStatus = "active" | "inactive";

export interface Rule extends BaseApiModel {
  name: string;
  description: string | null;
  comparison: RuleComparison | null;
  minimum: number | null;
  maximum: number | null;
  uom: string | null;
  status: RuleStatus;
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
  comparison?: RuleComparison | null;
  minimum?: number | null;
  maximum?: number | null;
  uom?: string | null;
  status?: RuleStatus;
  last_updated_by?: string | null;
}

/** Full replacement body for PUT /api/rules/:id */
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

export interface ApiErrorBody {
  error: {
    message: string;
    code?: string;
  };
}
