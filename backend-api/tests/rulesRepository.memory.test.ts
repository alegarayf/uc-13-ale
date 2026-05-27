import { describe, expect, it } from "vitest";
import { createMemoryRulesRepository } from "../src/repositories/rulesRepository.js";
import type { RuleInsertPayload } from "../src/types/rule.js";

const insertPayload: RuleInsertPayload = {
  name: "New rule",
  description: "desc",
  status: "active",
  rule_source: "ai",
  nl_prompt: "prompt",
  nl_summary: "summary",
  rule_definition: "{}",
  python_source: null,
  python_entrypoint: null,
  last_updated_by: "test",
};

describe("createMemoryRulesRepository", () => {
  it("lists seed rules", async () => {
    const repo = createMemoryRulesRepository();
    const all = await repo.findAll();
    expect(all.length).toBeGreaterThanOrEqual(3);
    expect(all[0]?.rule_source).toBe("ai");
  });

  it("creates and finds by id", async () => {
    const repo = createMemoryRulesRepository();
    const created = await repo.create(insertPayload);
    const found = await repo.findById(created.id);
    expect(found?.name).toBe("New rule");
    expect(found?.nl_prompt).toBe("prompt");
  });

  it("replaces a rule", async () => {
    const repo = createMemoryRulesRepository();
    const replaced = await repo.replace(1, {
      ...insertPayload,
      name: "Replaced",
      rule_source: "ai",
    });
    expect(replaced?.name).toBe("Replaced");
  });

  it("patches a rule", async () => {
    const repo = createMemoryRulesRepository();
    const patched = await repo.update(1, { nl_summary: "Patched summary" });
    expect(patched?.nl_summary).toBe("Patched summary");
  });

  it("deletes a rule", async () => {
    const repo = createMemoryRulesRepository();
    const created = await repo.create(insertPayload);
    expect(await repo.delete(created.id)).toBe(true);
    expect(await repo.findById(created.id)).toBeNull();
  });
});
