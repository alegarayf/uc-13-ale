import { describe, expect, it } from "vitest";
import { isAiRule, ruleMatchesSearch } from "./ruleSearch.js";
import type { Rule } from "../types/rule.js";

const baseRule: Rule = {
  id: 1,
  name: "Revenue threshold",
  description: "Minimum annual revenue",
  status: "active",
  rule_source: "ai",
  nl_prompt: "Require $10M revenue",
  nl_summary: "Requires at least $10M revenue",
  rule_definition: null,
  python_source: null,
  python_entrypoint: null,
  created_at: "2026-01-01T00:00:00.000Z",
  updated_at: "2026-01-01T00:00:00.000Z",
  last_updated_by: null,
};

describe("ruleMatchesSearch", () => {
  it("matches name and nl fields", () => {
    expect(ruleMatchesSearch(baseRule, "revenue")).toBe(true);
    expect(ruleMatchesSearch(baseRule, "$10m")).toBe(true);
    expect(ruleMatchesSearch(baseRule, "zzznomatch")).toBe(false);
  });

  it("returns true for empty query", () => {
    expect(ruleMatchesSearch(baseRule, "")).toBe(true);
  });
});

describe("isAiRule", () => {
  it("detects ai rules", () => {
    expect(isAiRule(baseRule)).toBe(true);
    expect(isAiRule({ ...baseRule, rule_source: "form" })).toBe(false);
  });
});
