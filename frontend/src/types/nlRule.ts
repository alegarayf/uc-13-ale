export interface NlRuleInterpretResponse {
  sessionId: string;
  summary: string;
  ruleConfig: Record<string, unknown>;
  aiMode: string;
  canDeny: boolean;
}
