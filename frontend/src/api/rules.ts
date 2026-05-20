import { apiDelete, apiGet, apiPost, apiPut } from "./client.js";
import type {
  ApiItemResponse,
  ApiListResponse,
  CreateRuleInput,
  ReplaceRuleInput,
  Rule,
} from "../types/rule.js";

export async function fetchRules(): Promise<Rule[]> {
  const res = await apiGet<ApiListResponse<Rule>>("/api/rules");
  return res.data;
}

export async function createRule(input: CreateRuleInput): Promise<Rule> {
  const res = await apiPost<ApiItemResponse<Rule>>("/api/rules", input);
  return res.data;
}

export async function replaceRule(id: number, input: ReplaceRuleInput): Promise<Rule> {
  const res = await apiPut<ApiItemResponse<Rule>>(`/api/rules/${id}`, input);
  return res.data;
}

export async function deleteRule(id: number): Promise<void> {
  await apiDelete(`/api/rules/${id}`);
}
