import { describe, expect, it } from "vitest";
import { createDataStore } from "../src/stores/createStore.js";

describe("createDataStore", () => {
  it("creates memory store", async () => {
    const store = createDataStore("memory", {
      serverHostname: "",
      httpPath: "",
      token: "",
      catalog: "",
      schema: "",
    });
    expect(store.label).toBe("memory");
    expect((await store.ping()).ok).toBe(true);
  });

  it("creates databricks store", () => {
    const store = createDataStore("databricks", {
      serverHostname: "h",
      httpPath: "/p",
      token: "t",
      catalog: "c",
      schema: "s",
    });
    expect(store.label).toBe("databricks");
  });
});
