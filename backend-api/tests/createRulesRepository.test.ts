import { describe, expect, it, vi } from "vitest";
import { createCachingRulesRepository } from "../src/repositories/cachingRulesRepository.js";
import { createRulesRepository } from "../src/repositories/createRulesRepository.js";
import { createMemoryRulesRepository } from "../src/repositories/rulesRepository.js";

describe("createRulesRepository", () => {
  it("returns memory repository by default mode", async () => {
    const repo = createRulesRepository(
      "memory",
      {
        serverHostname: "",
        httpPath: "",
        token: "",
        catalog: "",
        schema: "",
      },
      { cache: false },
    );
    const rules = await repo.findAll();
    expect(rules.length).toBeGreaterThan(0);
  });

  it("wraps with cache when enabled via options", async () => {
    const inner = createMemoryRulesRepository();
    const repo = createCachingRulesRepository(inner, { ttlMs: 60_000 });
    const spy = vi.spyOn(inner, "findAll");
    await repo.findAll();
    await repo.findAll();
    expect(spy).toHaveBeenCalledTimes(1);
  });
});
