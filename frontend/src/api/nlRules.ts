import { aiDelete, aiGet, aiPost } from "./aiClient.js";
import type {
  NlRuleConfigDetail,
  NlRuleConfigListItem,
  NlRuleConfirmResponse,
  NlRuleInterpretResponse,
} from "../types/nlRule.js";

export function fetchNlRuleConfigs(): Promise<NlRuleConfigListItem[]> {
  return aiGet<NlRuleConfigListItem[]>("/api/ai/rules/configs");
}

export function interpretNlRule(prompt: string): Promise<NlRuleInterpretResponse> {
  return aiPost<NlRuleInterpretResponse>("/api/ai/rules/interpret", { prompt });
}

export function fetchNlRuleConfig(filename: string): Promise<NlRuleConfigDetail> {
  return aiGet<NlRuleConfigDetail>(`/api/ai/rules/configs/${encodeURIComponent(filename)}`);
}

export function deleteNlRuleConfig(filename: string): Promise<void> {
  return aiDelete(`/api/ai/rules/configs/${encodeURIComponent(filename)}`);
}

export function confirmNlRule(
  sessionId: string,
  updateFilename?: string,
): Promise<NlRuleConfirmResponse> {
  return aiPost<NlRuleConfirmResponse>(`/api/ai/rules/sessions/${sessionId}/confirm`, {
    updateFilename: updateFilename ?? undefined,
  });
}

export function denyNlRule(
  sessionId: string,
  feedback?: string,
): Promise<NlRuleInterpretResponse> {
  return aiPost<NlRuleInterpretResponse>(`/api/ai/rules/sessions/${sessionId}/deny`, {
    feedback: feedback?.trim() || undefined,
  });
}
