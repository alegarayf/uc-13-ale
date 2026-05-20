import { beforeEach, describe, expect, it, vi } from "vitest";
import { NotFoundError, ValidationError } from "../src/errors/httpErrors.js";
import type { RulesRepository } from "../src/repositories/rulesRepository.js";
import { RulesService } from "../src/services/rulesService.js";
import { Rule } from "../src/types/rule.js";

const sample = new Rule({
  id: 1,
  name: "Sample",
  description: null,
  comparison: ">=",
  minimum: 1,
  maximum: null,
  uom: null,
  status: "active",
  created_at: "2026-01-01T00:00:00.000Z",
  updated_at: "2026-01-01T00:00:00.000Z",
  last_updated_by: null,
});

function createMockRepo(overrides: Partial<RulesRepository> = {}): RulesRepository {
  return {
    findAll: vi.fn(async () => [sample]),
    findById: vi.fn(async (id) => (id === 1 ? sample : null)),
    create: vi.fn(async (input) => new Rule({ ...sample, ...input, id: 2 })),
    replace: vi.fn(async (id, fields) =>
      id === 1 ? new Rule({ ...sample, ...fields, id: 1, updated_at: "2026-02-01T00:00:00.000Z" }) : null,
    ),
    update: vi.fn(async (id, patch) =>
      id === 1 ? new Rule({ ...sample, ...patch, id: 1 }) : null,
    ),
    delete: vi.fn(async (id) => id === 1),
    ...overrides,
  };
}

describe("RulesService", () => {
  let repo: RulesRepository;
  let service: RulesService;

  beforeEach(() => {
    repo = createMockRepo();
    service = new RulesService(repo);
  });

  it("lists rules from repository", async () => {
    const rules = await service.list();
    expect(rules).toHaveLength(1);
    expect(repo.findAll).toHaveBeenCalled();
  });

  it("throws NotFoundError when missing", async () => {
    await expect(service.getById(404)).rejects.toBeInstanceOf(NotFoundError);
  });

  it("creates with validated payload", async () => {
    const created = await service.create({
      name: "Created",
      comparison: "=",
      minimum: 1,
      status: "inactive",
    });
    expect(created.id).toBe(2);
    expect(repo.create).toHaveBeenCalledWith(
      expect.objectContaining({ name: "Created", comparison: "=", status: "inactive" }),
    );
  });

  it("defaults status to active on create", async () => {
    await service.create({ name: "Default status" });
    expect(repo.create).toHaveBeenCalledWith(
      expect.objectContaining({ status: "active" }),
    );
  });

  it("rejects invalid create body", async () => {
    await expect(service.create({ name: "" })).rejects.toBeInstanceOf(ValidationError);
  });

  it("replaces existing rule", async () => {
    const updated = await service.replace(1, {
      name: "Replaced",
      comparison: null,
      description: null,
      minimum: null,
      maximum: null,
      uom: null,
      status: "inactive",
    });
    expect(updated.name).toBe("Replaced");
    expect(updated.status).toBe("inactive");
  });

  it("throws when replace misses", async () => {
    vi.mocked(repo.replace).mockResolvedValue(null);
    await expect(
      service.replace(404, {
        name: "X",
        comparison: null,
        status: "active",
      }),
    ).rejects.toBeInstanceOf(NotFoundError);
  });

  it("rejects empty patch body", async () => {
    await expect(service.patch(1, {})).rejects.toBeInstanceOf(ValidationError);
  });

  it("patches a single field", async () => {
    await service.patch(1, { minimum: 99 });
    expect(repo.update).toHaveBeenCalledWith(1, expect.objectContaining({ minimum: 99 }));
  });

  it("removes existing rule", async () => {
    await service.remove(1);
    expect(repo.delete).toHaveBeenCalledWith(1);
  });

  it("throws when delete misses", async () => {
    vi.mocked(repo.delete).mockResolvedValue(false);
    await expect(service.remove(1)).rejects.toBeInstanceOf(NotFoundError);
  });
});
