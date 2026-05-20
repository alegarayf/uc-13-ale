import { describe, expect, it } from "vitest";
import { BaseApiModel } from "../src/types/baseApiModel.js";
import { Rule } from "../src/types/rule.js";

class StubEntity extends BaseApiModel {
  readonly label: string;
  constructor(
    base: ConstructorParameters<typeof BaseApiModel>[0],
    label: string,
  ) {
    super(base);
    this.label = label;
  }
}

describe("BaseApiModel", () => {
  it("exposes shared audit fields", () => {
    const entity = new StubEntity(
      {
        id: 99,
        created_at: "2026-01-01T00:00:00.000Z",
        updated_at: "2026-01-02T00:00:00.000Z",
        last_updated_by: "tester",
      },
      "stub",
    );
    expect(entity.id).toBe(99);
    expect(entity.last_updated_by).toBe("tester");
  });
});

describe("Rule", () => {
  it("extends BaseApiModel with rule fields", () => {
    const rule = new Rule({
      id: 1,
      name: "Revenue",
      description: null,
      comparison: ">=",
      minimum: 1,
      maximum: null,
      uom: "USD",
      status: "active",
      created_at: "2026-01-01T00:00:00.000Z",
      updated_at: "2026-01-01T00:00:00.000Z",
      last_updated_by: null,
    });
    expect(rule).toBeInstanceOf(BaseApiModel);
    expect(rule.name).toBe("Revenue");
  });
});
