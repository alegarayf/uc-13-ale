import { describe, expect, it } from "vitest";
import {
  buildCreatePayload,
  buildReplacePayload,
  EMPTY_RULE_FORM,
  ruleToFormState,
} from "./ruleForm.js";
import type { Rule } from "../../types/rule.js";

const sampleRule: Rule = {
  id: 1,
  name: "Revenue",
  description: "Min revenue",
  status: "active",
  rule_source: "form",
  nl_prompt: null,
  nl_summary: null,
  rule_definition: null,
  python_source: null,
  python_entrypoint: null,
  created_at: "2026-01-01T00:00:00.000Z",
  updated_at: "2026-01-01T00:00:00.000Z",
  last_updated_by: "tester",
};

describe("ruleForm", () => {
  it("maps rule to form state", () => {
    expect(ruleToFormState(sampleRule)).toEqual({
      name: "Revenue",
      description: "Min revenue",
      status: "active",
    });
  });

  it("builds create payload for form rules", () => {
    const result = buildCreatePayload(
      { ...EMPTY_RULE_FORM, name: "New rule", status: "active" },
      "tester",
    );
    expect(result.error).toBeUndefined();
    expect(result.payload).toMatchObject({
      name: "New rule",
      rule_source: "form",
      status: "active",
      last_updated_by: "tester",
    });
  });

  it("requires name", () => {
    const result = buildCreatePayload(EMPTY_RULE_FORM, "tester");
    expect(result.error).toMatch(/name/i);
  });

  it("builds replace payload", () => {
    const result = buildReplacePayload(
      { name: "Updated", description: "", status: "inactive" },
      "tester",
    );
    expect(result.payload?.status).toBe("inactive");
    expect(result.payload?.rule_source).toBe("form");
  });
});
