export interface NlRuleInterpretResponse {
  sessionId: string;
  summary: string;
  ruleConfig: Record<string, unknown>;
  aiMode: string;
  canDeny: boolean;
}

export interface NlRuleConfirmResponse {
  sessionId: string;
  configFile: string;
  ruleConfig: Record<string, unknown>;
}

export interface NlRuleConfigListItem {
  filename: string;
  id?: string;
  name?: string;
  summary?: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface NlRuleConfigDetail {
  filename: string;
  id?: string;
  sessionId?: string;
  prompt: string;
  summary: string;
  rule: Record<string, unknown>;
  createdAt?: string;
  updatedAt?: string;
}
