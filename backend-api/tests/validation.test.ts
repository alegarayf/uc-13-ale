import { describe, expect, it } from "vitest";
import { ValidationError } from "../src/errors/httpErrors.js";
import {
  normalizeComparison,
  normalizeStatus,
  optionalInt,
  optionalNullableString,
  optionalString,
  requireLastUpdatedBy,
  requireNonEmptyString,
} from "../src/services/validation.js";

describe("requireNonEmptyString", () => {
  it("returns trimmed string", () => {
    expect(requireNonEmptyString("  foo  ", "name")).toBe("foo");
  });

  it("throws when empty", () => {
    expect(() => requireNonEmptyString("  ", "name")).toThrow(ValidationError);
  });
});

describe("optionalString", () => {
  it("passes through null and undefined", () => {
    expect(optionalString(undefined)).toBeUndefined();
    expect(optionalString(null)).toBeNull();
  });

  it("rejects non-strings", () => {
    expect(() => optionalString(1)).toThrow(ValidationError);
  });
});

describe("optionalInt", () => {
  it("accepts integers and null", () => {
    expect(optionalInt(5, "minimum")).toBe(5);
    expect(optionalInt(null, "minimum")).toBeNull();
  });

  it("rejects non-integers", () => {
    expect(() => optionalInt(1.5, "minimum")).toThrow(ValidationError);
  });
});

describe("normalizeComparison", () => {
  it("accepts valid operators", () => {
    expect(normalizeComparison(">=")).toBe(">=");
  });

  it("returns null for empty when not required", () => {
    expect(normalizeComparison(null)).toBeNull();
  });

  it("throws for invalid operator", () => {
    expect(() => normalizeComparison("!=")).toThrow(ValidationError);
  });

  it("throws when required and missing", () => {
    expect(() => normalizeComparison(undefined, true)).toThrow(ValidationError);
  });
});

describe("normalizeStatus", () => {
  it("defaults to active when omitted", () => {
    expect(normalizeStatus(undefined)).toBe("active");
  });

  it("accepts active and inactive case-insensitively", () => {
    expect(normalizeStatus("Inactive")).toBe("inactive");
  });

  it("throws for invalid status", () => {
    expect(() => normalizeStatus("draft")).toThrow(ValidationError);
  });

  it("throws when required and missing", () => {
    expect(() => normalizeStatus(undefined, true)).toThrow(ValidationError);
  });
});

describe("requireLastUpdatedBy", () => {
  it("normalizes blank to null", () => {
    expect(requireLastUpdatedBy("  ")).toBeNull();
    expect(requireLastUpdatedBy("alice")).toBe("alice");
  });
});

describe("optionalNullableString", () => {
  it("delegates to optionalString", () => {
    expect(optionalNullableString("x")).toBe("x");
  });
});
