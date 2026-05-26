import { describe, expect, it } from "vitest";
import type { Rule } from "../types/rule.js";
import { nlRuleMatchesSearch, ruleMatchesSearch } from "./ruleSearch.js";

const sampleRule: Rule = {
  id: 1,
  name: "Minimum ARR",
  description: "Revenue floor for enterprise deals",
  comparison: ">=",
  minimum: 1_000_000,
  maximum: null,
  uom: "USD",
  status: "active",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  last_updated_by: null,
};

describe("ruleMatchesSearch", () => {
  it("matches empty query", () => {
    expect(ruleMatchesSearch(sampleRule, "")).toBe(true);
  });

  it("matches name and description", () => {
    expect(ruleMatchesSearch(sampleRule, "arr")).toBe(true);
    expect(ruleMatchesSearch(sampleRule, "enterprise")).toBe(true);
  });

  it("returns false when no field matches", () => {
    expect(ruleMatchesSearch(sampleRule, "healthcare")).toBe(false);
  });
});

describe("nlRuleMatchesSearch", () => {
  it("matches filename and summary", () => {
    expect(
      nlRuleMatchesSearch(
        {
          filename: "rule-abc123.json",
          name: "Slack alert",
          summary: "Notify when revenue drops",
        },
        "slack",
      ),
    ).toBe(true);
    expect(
      nlRuleMatchesSearch(
        {
          filename: "rule-abc123.json",
          name: "Slack alert",
          summary: "Notify when revenue drops",
        },
        "rule-abc",
      ),
    ).toBe(true);
  });
});
