import { describe, expect, it, vi } from "vitest";
import { createCachingCompaniesRepository } from "../src/repositories/cachingCompaniesRepository.js";
import { createCompaniesRepository } from "../src/repositories/createCompaniesRepository.js";
import { createMemoryCompaniesRepository } from "../src/repositories/companiesRepository.js";

vi.mock("../src/db/databricksClient.js", () => ({
  getSharedDatabricksClient: vi.fn(() => ({
    ping: vi.fn(),
    close: vi.fn(),
    query: vi.fn(async () => []),
  })),
}));

const emptyDatabricks = {
  serverHostname: "",
  httpPath: "",
  token: "",
  catalog: "",
  schema: "",
};

describe("createCompaniesRepository", () => {
  it("returns memory repository when mode is memory and cache disabled", async () => {
    const repo = createCompaniesRepository("memory", emptyDatabricks, { cache: false });
    const companies = await repo.findByOwnerEmail("mcrysler@nimblegravity.com");
    expect(companies.length).toBeGreaterThan(0);
  });

  it("wraps with cache when enabled via options", async () => {
    const inner = createMemoryCompaniesRepository();
    const repo = createCachingCompaniesRepository(inner, { ttlMs: 60_000 });
    const spy = vi.spyOn(inner, "findByOwnerEmail");
    await repo.findByOwnerEmail("mcrysler@nimblegravity.com");
    await repo.findByOwnerEmail("mcrysler@nimblegravity.com");
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("returns databricks repository when mode is databricks", async () => {
    const repo = createCompaniesRepository(
      "databricks",
      {
        serverHostname: "host",
        httpPath: "/sql/1.0/warehouses/x",
        token: "token",
        catalog: "cat",
        schema: "garden",
      },
      { cache: false },
    );
    const companies = await repo.findByOwnerEmail("mcrysler@nimblegravity.com");
    expect(companies).toEqual([]);
  });

  it("applies TTL cache via factory when cache option is true", async () => {
    const repo = createCompaniesRepository("memory", emptyDatabricks, {
      cache: true,
      cacheTtlMs: 60_000,
    });
    const first = await repo.findByOwnerEmail("mcrysler@nimblegravity.com");
    const second = await repo.findByOwnerEmail("mcrysler@nimblegravity.com");
    expect(first).toBe(second);
  });

  it("returns fresh results when cache option is false", async () => {
    const repo = createCompaniesRepository("memory", emptyDatabricks, {
      cache: false,
      cacheTtlMs: 60_000,
    });
    const first = await repo.findByOwnerEmail("mcrysler@nimblegravity.com");
    const second = await repo.findByOwnerEmail("mcrysler@nimblegravity.com");
    expect(first).not.toBe(second);
    expect(first).toEqual(second);
  });
});
