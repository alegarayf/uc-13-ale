import { describe, expect, it } from "vitest";
import { ValidationError } from "../src/errors/httpErrors.js";
import { parseEntityId } from "../src/utils/parseEntityId.js";

describe("parseEntityId", () => {
  it("parses positive integers", () => {
    expect(parseEntityId("42")).toBe(42);
  });

  it("rejects non-numeric ids", () => {
    expect(() => parseEntityId("abc")).toThrow(ValidationError);
    expect(() => parseEntityId("0")).toThrow(ValidationError);
    expect(() => parseEntityId("1.5")).toThrow(ValidationError);
  });
});
