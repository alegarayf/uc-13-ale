import { describe, expect, it } from "vitest";
import { mapRowToRule, mapRowToRuleFields } from "../src/repositories/ruleRowMapper.js";
import { Rule } from "../src/types/rule.js";

describe("mapRowToRuleFields", () => {
  it("maps lowercase column names", () => {
    const fields = mapRowToRuleFields({
      id: 1,
      name: "Test",
      description: "desc",
      comparison: ">=",
      minimum: 10,
      maximum: 20,
      uom: "USD",
      status: "active",
      created_at: "2026-01-01T00:00:00.000Z",
      updated_at: "2026-01-02T00:00:00.000Z",
      last_updated_by: "user",
    });
    expect(fields).toMatchObject({
      id: 1,
      name: "Test",
      comparison: ">=",
      minimum: 10,
      maximum: 20,
      status: "active",
      last_updated_by: "user",
    });
  });

  it("maps uppercase column names from drivers", () => {
    const fields = mapRowToRuleFields({
      ID: 2,
      NAME: "Upper",
      DESCRIPTION: null,
      COMPARISON: "=",
      MINIMUM: null,
      MAXIMUM: null,
      UOM: null,
      STATUS: "inactive",
      CREATED_AT: new Date("2026-03-01T12:00:00.000Z"),
      UPDATED_AT: new Date("2026-03-02T12:00:00.000Z"),
      LAST_UPDATED_BY: null,
    });
    expect(fields.id).toBe(2);
    expect(fields.name).toBe("Upper");
    expect(fields.status).toBe("inactive");
    expect(fields.created_at).toBe("2026-03-01T12:00:00.000Z");
  });
});

describe("mapRowToRule", () => {
  it("returns a Rule instance", () => {
    const rule = mapRowToRule({ id: 1, name: "N", created_at: "t", updated_at: "t" });
    expect(rule).toBeInstanceOf(Rule);
  });
});
