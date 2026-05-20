import { describe, expect, it } from "vitest";
import { formatRuleCriteria, formatRuleStatusLabel } from "./formatRule.js";
import type { Rule } from "../types/rule.js";

const baseRule: Rule = {
  id: 1,
  name: "Test",
  description: null,
  comparison: ">=",
  minimum: 10_000_000,
  maximum: null,
  uom: "USD",
  status: "active",
  created_at: "2026-01-01T00:00:00.000Z",
  updated_at: "2026-01-01T00:00:00.000Z",
  last_updated_by: null,
};

describe("formatRuleCriteria", () => {
  it("formats comparison, minimum, and uom", () => {
    expect(formatRuleCriteria(baseRule)).toBe(">= 10,000,000 USD");
  });

  it("formats a range when min and max are set", () => {
    expect(
      formatRuleCriteria({ ...baseRule, minimum: 7, maximum: 10, uom: "score" }),
    ).toBe(">= 7 – 10 score");
  });

  it("returns em dash when no criteria fields", () => {
    expect(
      formatRuleCriteria({
        ...baseRule,
        comparison: null,
        minimum: null,
        maximum: null,
        uom: null,
      }),
    ).toBe("—");
  });
});

describe("formatRuleStatusLabel", () => {
  it("capitalizes status for display", () => {
    expect(formatRuleStatusLabel("active")).toBe("Active");
    expect(formatRuleStatusLabel("inactive")).toBe("Inactive");
  });
});
