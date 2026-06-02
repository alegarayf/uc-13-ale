import { describe, expect, it, vi } from "vitest";
import { RulesService } from "../src/services/rulesService.js";
import { Rule, type RuleInsertPayload } from "../src/types/rule.js";

const basePayload: RuleInsertPayload = {
  name: "Test",
  description: null,
  status: "active",
  rule_source: "ai",
  nl_prompt: "p",
  nl_summary: "s",
  rule_definition: JSON.stringify({
    python_function: { source: "def run(): pass", entrypoint: "run" },
  }),
  python_source: null,
  python_entrypoint: null,
  last_updated_by: "tester",
};

function makeRepo() {
  return {
    findAll: vi.fn(),
    findById: vi.fn(),
    create: vi.fn(),
    replace: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
  };
}

describe("RulesService", () => {
  it("creates with python extracted from rule_definition", async () => {
    const repo = makeRepo();
    repo.create.mockResolvedValue(
      new Rule({
        id: 1,
        ...basePayload,
        python_source: "def run(): pass",
        python_entrypoint: "run",
        created_at: "2026-01-01T00:00:00.000Z",
        updated_at: "2026-01-01T00:00:00.000Z",
      }),
    );
    const service = new RulesService(repo);
    await service.create({
      name: "Test",
      rule_source: "ai",
      rule_definition: basePayload.rule_definition!,
      last_updated_by: "tester",
    });
    expect(repo.create).toHaveBeenCalledWith(
      expect.objectContaining({
        python_source: "def run(): pass",
        python_entrypoint: "run",
      }),
    );
  });

  it("create requires name", async () => {
    const service = new RulesService(makeRepo());
    await expect(service.create({ name: "  " })).rejects.toThrow(/name is required/);
  });

  it("replace updates rule", async () => {
    const repo = makeRepo();
    repo.replace.mockResolvedValue(
      new Rule({
        id: 1,
        ...basePayload,
        name: "Created",
        status: "inactive",
        created_at: "2026-01-01T00:00:00.000Z",
        updated_at: "2026-01-01T00:00:00.000Z",
      }),
    );
    const service = new RulesService(repo);
    await service.replace(1, {
      name: "Created",
      rule_source: "ai",
      status: "inactive",
      last_updated_by: "tester",
    });
    expect(repo.replace).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ name: "Created", status: "inactive" }),
    );
  });

  it("patch merges fields", async () => {
    const existing = new Rule({
      id: 1,
      ...basePayload,
      created_at: "2026-01-01T00:00:00.000Z",
      updated_at: "2026-01-01T00:00:00.000Z",
    });
    const repo = makeRepo();
    repo.findById.mockResolvedValue(existing);
    repo.replace.mockResolvedValue(existing);
    const service = new RulesService(repo);
    await service.patch(1, { nl_summary: "Updated" });
    expect(repo.replace).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ nl_summary: "Updated" }),
    );
  });
});
