import { aiPost } from "./aiClient.js";
import type { NlRuleInterpretResponse } from "../types/nlRule.js";

export function interpretNlRule(prompt: string): Promise<NlRuleInterpretResponse> {
  return aiPost<NlRuleInterpretResponse>("/api/ai/rules/interpret", { prompt });
}

export function denyNlRule(
  sessionId: string,
  feedback?: string,
): Promise<NlRuleInterpretResponse> {
  return aiPost<NlRuleInterpretResponse>(`/api/ai/rules/sessions/${sessionId}/deny`, {
    feedback: feedback?.trim() || undefined,
  });
}
