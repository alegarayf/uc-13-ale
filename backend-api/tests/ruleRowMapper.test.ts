import { describe, expect, it } from "vitest";
import { mapRowToRuleFields } from "../src/repositories/ruleRowMapper.js";

describe("mapRowToRuleFields", () => {
  it("maps databricks row keys to rule fields", () => {
    const fields = mapRowToRuleFields({
      id: 1,
      name: "Test",
      description: "Desc",
      status: "active",
      rule_source: "ai",
      nl_prompt: "prompt",
      nl_summary: "summary",
      rule_definition: "{}",
      python_source: "def f(): pass",
      python_entrypoint: "f",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-02T00:00:00Z",
      last_updated_by: "tester",
    });
    expect(fields).toMatchObject({
      id: 1,
      name: "Test",
      rule_source: "ai",
      nl_summary: "summary",
      python_entrypoint: "f",
      status: "active",
    });
  });
});
