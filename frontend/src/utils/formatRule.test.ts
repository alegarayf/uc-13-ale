import { describe, expect, it } from "vitest";
import { formatRuleStatusLabel, formatRuleSummary } from "./formatRule.js";
import type { Rule } from "../types/rule.js";

const baseRule: Rule = {
  id: 1,
  name: "Revenue threshold",
  description: "Minimum annual revenue",
  status: "active",
  rule_source: "ai",
  nl_prompt: "prompt",
  nl_summary: "Requires at least $10M revenue",
  rule_definition: JSON.stringify({
    conditions: [{ field: "annual_revenue", operator: ">=", value: 10_000_000 }],
  }),
  python_source: null,
  python_entrypoint: null,
  created_at: "2026-01-01T00:00:00.000Z",
  updated_at: "2026-01-01T00:00:00.000Z",
  last_updated_by: null,
};

describe("formatRuleSummary", () => {
  it("prefers nl_summary", () => {
    expect(formatRuleSummary(baseRule)).toBe("Requires at least $10M revenue");
  });

  it("falls back to conditions from rule_definition", () => {
    expect(
      formatRuleSummary({
        ...baseRule,
        nl_summary: null,
      }),
    ).toBe("annual_revenue >= 10000000");
  });
});

describe("formatRuleStatusLabel", () => {
  it("labels active and inactive", () => {
    expect(formatRuleStatusLabel("active")).toBe("Active");
    expect(formatRuleStatusLabel("inactive")).toBe("Inactive");
  });
});
