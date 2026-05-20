import { describe, expect, it, vi } from "vitest";
import { createDatabricksRulesRepository } from "../src/repositories/rulesRepository.js";
import type { DatabricksClient } from "../src/db/databricksClient.js";
import type { RuleInsertPayload } from "../src/types/rule.js";

const cfg = {
  serverHostname: "host",
  httpPath: "/sql/1.0/warehouses/x",
  token: "token",
  catalog: "cat",
  schema: "garden",
};

const insertPayload: RuleInsertPayload = {
  name: "Databricks rule",
  description: "d",
  comparison: ">=",
  minimum: 5,
  maximum: null,
  uom: "ea",
  status: "active",
  last_updated_by: "sql",
};

function mockClient(handlers: {
  onQuery?: (sql: string, params?: Record<string, unknown>) => Record<string, unknown>[];
}): DatabricksClient {
  return {
    ping: vi.fn(),
    close: vi.fn(),
    query: vi.fn(async (sql, params) => {
      if (handlers.onQuery) return handlers.onQuery(sql, params);
      return [];
    }),
  };
}

describe("createDatabricksRulesRepository", () => {
  it("queries fully qualified table on list", async () => {
    const db = mockClient({
      onQuery: (sql) => {
        expect(sql).toContain("cat.garden.rules");
        return [{ id: 1, name: "R", created_at: "t", updated_at: "t" }];
      },
    });
    const repo = createDatabricksRulesRepository(db, cfg);
    const rules = await repo.findAll();
    expect(rules).toHaveLength(1);
    expect(db.query).toHaveBeenCalled();
  });

  it("inserts without id then loads created row", async () => {
    const db = mockClient({
      onQuery: (sql, params) => {
        if (sql.startsWith("INSERT")) {
          expect(params).toMatchObject({ name: insertPayload.name });
          return [];
        }
        return [
          {
            id: 10,
            name: insertPayload.name,
            description: insertPayload.description,
            comparison: insertPayload.comparison,
            minimum: insertPayload.minimum,
            maximum: null,
            uom: insertPayload.uom,
            status: insertPayload.status,
            created_at: "2026-05-20T00:00:00.000Z",
            updated_at: "2026-05-20T00:00:00.000Z",
            last_updated_by: insertPayload.last_updated_by,
          },
        ];
      },
    });
    const repo = createDatabricksRulesRepository(db, cfg);
    const created = await repo.create(insertPayload);
    expect(created.id).toBe(10);
    expect(db.query).toHaveBeenCalledTimes(2);
  });

  it("updates and deletes by id", async () => {
    const db = mockClient({
      onQuery: (sql) => {
        if (sql.includes("WHERE id = :id") && sql.startsWith("SELECT")) {
          return [
            {
              id: 5,
              name: "Old",
              description: null,
              comparison: null,
              minimum: null,
              maximum: null,
              uom: null,
              status: "active",
              created_at: "t",
              updated_at: "t",
              last_updated_by: null,
            },
          ];
        }
        return [];
      },
    });
    const repo = createDatabricksRulesRepository(db, cfg);
    const updated = await repo.replace(5, {
      name: "New",
      description: null,
      comparison: "=",
      minimum: null,
      maximum: null,
      uom: null,
      status: "inactive",
      last_updated_by: "u",
    });
    expect(updated).not.toBeNull();
    expect(db.query).toHaveBeenCalledWith(
      expect.stringContaining("UPDATE"),
      expect.objectContaining({ name: "New", id: 5 }),
    );
    expect(await repo.delete(5)).toBe(true);
  });

  it("returns false when delete target missing", async () => {
    const db = mockClient({ onQuery: () => [] });
    const repo = createDatabricksRulesRepository(db, cfg);
    expect(await repo.delete(404)).toBe(false);
  });
});
