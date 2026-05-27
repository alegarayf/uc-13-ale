import { describe, expect, it } from "vitest";
import { pythonFromRuleDefinitionJson } from "../src/services/ruleDefinition.js";

describe("pythonFromRuleDefinitionJson", () => {
  it("extracts python_function fields", () => {
    const result = pythonFromRuleDefinitionJson(
      JSON.stringify({
        python_function: {
          source: "def evaluate(): pass",
          entrypoint: "evaluate",
        },
      }),
    );
    expect(result).toEqual({
      python_source: "def evaluate(): pass",
      python_entrypoint: "evaluate",
    });
  });

  it("returns nulls for invalid json", () => {
    expect(pythonFromRuleDefinitionJson("not json")).toEqual({
      python_source: null,
      python_entrypoint: null,
    });
  });
});
