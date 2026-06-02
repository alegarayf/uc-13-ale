import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import * as databricksClientModule from "../src/db/databricksClient.js";
import { createDatabricksStore } from "../src/stores/databricksStore.js";

describe("createDatabricksStore", () => {
  afterEach(() => {
    databricksClientModule.resetSharedDatabricksClient();
  });

  it("reports missing env vars", async () => {
    const store = createDatabricksStore({
      serverHostname: "",
      httpPath: "",
      token: "",
      catalog: "",
      schema: "",
    });
    const result = await store.ping();
    expect(result.ok).toBe(false);
    expect(result.detail).toMatch(/DATABRICKS_SERVER_HOSTNAME/);
  });

  it("pings via shared client when configured", async () => {
    const ping = vi.fn().mockResolvedValue(undefined);
    vi.spyOn(databricksClientModule, "getSharedDatabricksClient").mockReturnValue({
      ping,
      query: vi.fn(),
      close: vi.fn(),
    });

    const store = createDatabricksStore({
      serverHostname: "host",
      httpPath: "/path",
      token: "tok",
      catalog: "cat",
      schema: "garden",
    });
    const result = await store.ping();
    expect(result.ok).toBe(true);
    expect(ping).toHaveBeenCalled();
  });

});
