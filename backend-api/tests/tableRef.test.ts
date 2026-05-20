import { describe, expect, it } from "vitest";
import { rulesTableRef } from "../src/db/tableRef.js";

describe("rulesTableRef", () => {
  it("builds catalog.schema.table", () => {
    expect(
      rulesTableRef({ catalog: "rallyday_partners_llc", schema: "garden" }),
    ).toBe("rallyday_partners_llc.garden.rules");
  });

  it("throws when catalog or schema missing", () => {
    expect(() => rulesTableRef({ catalog: "", schema: "garden" })).toThrow(
      /DATABRICKS_CATALOG/,
    );
  });
});
