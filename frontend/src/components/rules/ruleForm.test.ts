import { describe, expect, it } from "vitest";
import type { Rule } from "../../types/rule.js";
import {
  EMPTY_RULE_FORM,
  formStateToCreateInput,
  formStateToReplaceInput,
  parseOptionalInt,
  ruleToFormState,
} from "./ruleForm.js";

const sampleRule: Rule = {
  id: 42,
  name: "Revenue",
  description: "Annual revenue",
  comparison: ">=",
  minimum: 1_000_000,
  maximum: null,
  uom: "USD",
  status: "inactive",
  created_at: "2026-01-01T00:00:00.000Z",
  updated_at: "2026-01-02T00:00:00.000Z",
  last_updated_by: "tester",
};

describe("ruleToFormState", () => {
  it("maps API rule fields to form strings", () => {
    expect(ruleToFormState(sampleRule)).toEqual({
      name: "Revenue",
      description: "Annual revenue",
      comparison: ">=",
      minimum: "1000000",
      maximum: "",
      uom: "USD",
      status: "inactive",
    });
  });
});

describe("parseOptionalInt", () => {
  it("parses integers and empty as null", () => {
    expect(parseOptionalInt("5")).toBe(5);
    expect(parseOptionalInt("")).toBeNull();
    expect(parseOptionalInt("1.5")).toBeUndefined();
  });
});

describe("formStateToCreateInput", () => {
  it("builds create payload", () => {
    const result = formStateToCreateInput(
      { ...EMPTY_RULE_FORM, name: "New rule", comparison: ">=", minimum: "10", status: "active" },
      "Jane",
    );
    expect(result).toMatchObject({
      name: "New rule",
      comparison: ">=",
      minimum: 10,
      status: "active",
      last_updated_by: "Jane",
    });
  });

  it("returns error when name missing", () => {
    expect(formStateToCreateInput(EMPTY_RULE_FORM, "Jane")).toEqual({ error: "Name is required." });
  });
});

describe("formStateToReplaceInput", () => {
  it("builds PUT payload with required comparison and status", () => {
    const result = formStateToReplaceInput(
      ruleToFormState(sampleRule),
      "Editor",
    );
    expect(result).toMatchObject({
      name: "Revenue",
      comparison: ">=",
      status: "inactive",
      last_updated_by: "Editor",
    });
  });
});
