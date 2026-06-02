import { describe, expect, it, vi } from "vitest";
import { Rule } from "../src/types/rule.js";
import { createCachingRulesRepository } from "../src/repositories/cachingRulesRepository.js";
import type { RulesRepository } from "../src/repositories/rulesRepository.js";

const sample = new Rule({
  id: 1,
  name: "Cached",
  description: null,
  status: "active",
  rule_source: "form",
  nl_prompt: null,
  nl_summary: null,
  rule_definition: null,
  python_source: null,
  python_entrypoint: null,
  created_at: "2026-01-01T00:00:00.000Z",
  updated_at: "2026-01-01T00:00:00.000Z",
  last_updated_by: null,
});

function createMockInner(): RulesRepository {
  return {
    findAll: vi.fn(async () => [sample]),
    findById: vi.fn(async (id) => (id === 1 ? sample : null)),
    create: vi.fn(async () => new Rule({ ...sample, id: 2, name: "New" })),
    replace: vi.fn(async () => sample),
    update: vi.fn(async () => sample),
    delete: vi.fn(async () => true),
  };
}

describe("createCachingRulesRepository", () => {
  it("reuses cached list without second database call", async () => {
    const inner = createMockInner();
    const repo = createCachingRulesRepository(inner, { ttlMs: 60_000 });

    await repo.findAll();
    await repo.findAll();

    expect(inner.findAll).toHaveBeenCalledTimes(1);
  });

  it("reuses cached findById", async () => {
    const inner = createMockInner();
    const repo = createCachingRulesRepository(inner, { ttlMs: 60_000 });

    await repo.findById(1);
    await repo.findById(1);

    expect(inner.findById).toHaveBeenCalledTimes(1);
  });

  it("does not cache null findById results", async () => {
    const inner = createMockInner();
    const repo = createCachingRulesRepository(inner, { ttlMs: 60_000 });

    await repo.findById(404);
    await repo.findById(404);

    expect(inner.findById).toHaveBeenCalledTimes(2);
  });

  it("invalidates list cache on create", async () => {
    const inner = createMockInner();
    const repo = createCachingRulesRepository(inner, { ttlMs: 60_000 });

    await repo.findAll();
    await repo.create({
      name: "N",
      description: null,
      status: "active",
      rule_source: "form",
      nl_prompt: null,
      nl_summary: null,
      rule_definition: null,
      python_source: null,
      python_entrypoint: null,
      last_updated_by: null,
    });
    await repo.findAll();

    expect(inner.findAll).toHaveBeenCalledTimes(2);
  });

  it("invalidates list cache on update", async () => {
    const inner = createMockInner();
    const repo = createCachingRulesRepository(inner, { ttlMs: 60_000 });

    await repo.findAll();
    await repo.update(1, { nl_summary: "updated" });
    await repo.findAll();

    expect(inner.findAll).toHaveBeenCalledTimes(2);
  });

  it("invalidates on delete", async () => {
    const inner = createMockInner();
    const repo = createCachingRulesRepository(inner, { ttlMs: 60_000 });

    await repo.findById(1);
    await repo.delete(1);
    await repo.findById(1);

    expect(inner.findById).toHaveBeenCalledTimes(2);
  });
});
