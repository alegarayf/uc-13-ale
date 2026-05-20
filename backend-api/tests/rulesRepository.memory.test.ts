import { beforeEach, describe, expect, it } from "vitest";
import { createMemoryRulesRepository } from "../src/repositories/rulesRepository.js";
import type { RuleInsertPayload } from "../src/types/rule.js";

const payload: RuleInsertPayload = {
  name: "New rule",
  description: "desc",
  comparison: "=",
  minimum: 1,
  maximum: 10,
  uom: "units",
  status: "active",
  last_updated_by: "test",
};

describe("createMemoryRulesRepository", () => {
  let repo: ReturnType<typeof createMemoryRulesRepository>;

  beforeEach(() => {
    repo = createMemoryRulesRepository();
  });

  it("lists seed rules ordered by id", async () => {
    const rules = await repo.findAll();
    expect(rules.length).toBeGreaterThanOrEqual(3);
    expect(rules[0]!.id).toBeLessThan(rules[1]!.id);
  });

  it("creates rules with generated id and timestamps", async () => {
    const created = await repo.create(payload);
    expect(created.id).toBeGreaterThan(3);
    expect(created.created_at).toBe(created.updated_at);
    expect(created.name).toBe(payload.name);
  });

  it("replaces and preserves created_at", async () => {
    const created = await repo.create(payload);
    const replaced = await repo.replace(created.id, {
      name: "Updated",
      description: null,
      comparison: null,
      minimum: null,
      maximum: null,
      uom: null,
      status: "inactive",
      last_updated_by: "editor",
    });
    expect(replaced?.status).toBe("inactive");
    expect(replaced?.name).toBe("Updated");
    expect(replaced?.created_at).toBe(created.created_at);
    expect(replaced?.last_updated_by).toBe("editor");
  });

  it("patches individual fields", async () => {
    const patched = await repo.update(1, { minimum: 99 });
    expect(patched?.minimum).toBe(99);
  });

  it("deletes existing rules", async () => {
    const created = await repo.create(payload);
    expect(await repo.delete(created.id)).toBe(true);
    expect(await repo.findById(created.id)).toBeNull();
  });

  it("returns null for missing ids", async () => {
    expect(await repo.findById(99999)).toBeNull();
    expect(await repo.replace(99999, { ...payload })).toBeNull();
  });
});
