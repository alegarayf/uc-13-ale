import type { DatabricksClient } from "../db/databricksClient.js";
import { rulesTableRef } from "../db/tableRef.js";
import {
  mapRowToRule,
  RULE_SELECT_COLUMNS,
} from "./ruleRowMapper.js";
import { Rule, type RuleInsertPayload, type RuleMutableFields } from "../types/rule.js";
import type { DatabricksStoreConfig } from "../stores/databricksStore.js";
import { nowTimestamp } from "../utils/timestamps.js";

export interface RulesRepository {
  findAll(): Promise<Rule[]>;
  findById(id: number): Promise<Rule | null>;
  create(input: RuleInsertPayload): Promise<Rule>;
  replace(id: number, fields: RuleMutableFields): Promise<Rule | null>;
  update(id: number, patch: Partial<RuleMutableFields>): Promise<Rule | null>;
  delete(id: number): Promise<boolean>;
}

const SEED_RULES: Rule[] = [
  new Rule({
    id: 1,
    name: "Revenue threshold",
    description: "Minimum annual revenue for portfolio consideration.",
    comparison: ">=",
    minimum: 10_000_000,
    maximum: null,
    uom: "USD",
    status: "active",
    created_at: "2026-01-01T00:00:00.000Z",
    updated_at: "2026-01-01T00:00:00.000Z",
    last_updated_by: "seed",
  }),
  new Rule({
    id: 2,
    name: "Geography",
    description: "Primary operating region for eligible companies.",
    comparison: "=",
    minimum: null,
    maximum: null,
    uom: null,
    status: "active",
    created_at: "2026-01-01T00:00:00.000Z",
    updated_at: "2026-01-01T00:00:00.000Z",
    last_updated_by: "seed",
  }),
  new Rule({
    id: 3,
    name: "Growth mindset score",
    description: "Minimum qualitative score from partner review.",
    comparison: ">=",
    minimum: 7,
    maximum: 10,
    uom: "score",
    status: "inactive",
    created_at: "2026-01-01T00:00:00.000Z",
    updated_at: "2026-01-01T00:00:00.000Z",
    last_updated_by: "seed",
  }),
];

export function createMemoryRulesRepository(): RulesRepository {
  const rules = new Map(SEED_RULES.map((r) => [r.id, r]));
  let nextId = Math.max(0, ...rules.keys()) + 1;

  function stamp(input: RuleInsertPayload): Rule {
    const ts = nowTimestamp();
    const rule = new Rule({
      id: nextId++,
      ...input,
      created_at: ts,
      updated_at: ts,
    });
    rules.set(rule.id, rule);
    return rule;
  }

  return {
    async findAll() {
      return [...rules.values()].sort((a, b) => a.id - b.id);
    },

    async findById(id) {
      return rules.get(id) ?? null;
    },

    async create(input) {
      return stamp(input);
    },

    async replace(id, fields) {
      const existing = rules.get(id);
      if (!existing) return null;
      const rule = new Rule({
        id,
        created_at: existing.created_at,
        updated_at: nowTimestamp(),
        ...fields,
      });
      rules.set(id, rule);
      return rule;
    },

    async update(id, patch) {
      const existing = rules.get(id);
      if (!existing) return null;
      const rule = new Rule({
        id,
        name: patch.name ?? existing.name,
        description: patch.description !== undefined ? patch.description : existing.description,
        comparison: patch.comparison !== undefined ? patch.comparison : existing.comparison,
        minimum: patch.minimum !== undefined ? patch.minimum : existing.minimum,
        maximum: patch.maximum !== undefined ? patch.maximum : existing.maximum,
        uom: patch.uom !== undefined ? patch.uom : existing.uom,
        status: patch.status !== undefined ? patch.status : existing.status,
        created_at: existing.created_at,
        updated_at: nowTimestamp(),
        last_updated_by:
          patch.last_updated_by !== undefined ? patch.last_updated_by : existing.last_updated_by,
      });
      rules.set(id, rule);
      return rule;
    },

    async delete(id) {
      return rules.delete(id);
    },
  };
}

export function createDatabricksRulesRepository(
  db: DatabricksClient,
  cfg: DatabricksStoreConfig,
): RulesRepository {
  const table = rulesTableRef(cfg);

  async function findNewestAfterInsert(input: RuleInsertPayload): Promise<Rule> {
    const rows = await db.query(
      `SELECT ${RULE_SELECT_COLUMNS} FROM ${table}
       WHERE name = :name AND last_updated_by <=> :last_updated_by
       ORDER BY id DESC
       LIMIT 1`,
      {
        name: input.name,
        last_updated_by: input.last_updated_by,
      },
    );
    if (!rows.length) {
      throw new Error("Insert succeeded but could not load created rule");
    }
    return mapRowToRule(rows[0]!);
  }

  return {
    async findAll() {
      const rows = await db.query(
        `SELECT ${RULE_SELECT_COLUMNS} FROM ${table} ORDER BY id`,
      );
      return rows.map(mapRowToRule);
    },

    async findById(id) {
      const rows = await db.query(
        `SELECT ${RULE_SELECT_COLUMNS} FROM ${table} WHERE id = :id`,
        { id },
      );
      if (!rows.length) return null;
      return mapRowToRule(rows[0]!);
    },

    async create(input) {
      await db.query(
        `INSERT INTO ${table}
         (name, description, comparison, minimum, maximum, uom, status, created_at, updated_at, last_updated_by)
         VALUES
         (:name, :description, :comparison, :minimum, :maximum, :uom, :status, current_timestamp(), current_timestamp(), :last_updated_by)`,
        {
          name: input.name,
          description: input.description,
          comparison: input.comparison,
          minimum: input.minimum,
          maximum: input.maximum,
          uom: input.uom,
          status: input.status,
          last_updated_by: input.last_updated_by,
        },
      );
      return findNewestAfterInsert(input);
    },

    async replace(id, fields) {
      const existing = await this.findById(id);
      if (!existing) return null;
      await db.query(
        `UPDATE ${table}
         SET name = :name,
             description = :description,
             comparison = :comparison,
             minimum = :minimum,
             maximum = :maximum,
             uom = :uom,
             status = :status,
             updated_at = current_timestamp(),
             last_updated_by = :last_updated_by
         WHERE id = :id`,
        {
          id,
          name: fields.name,
          description: fields.description,
          comparison: fields.comparison,
          minimum: fields.minimum,
          maximum: fields.maximum,
          uom: fields.uom,
          status: fields.status,
          last_updated_by: fields.last_updated_by,
        },
      );
      return this.findById(id);
    },

    async update(id, patch) {
      const existing = await this.findById(id);
      if (!existing) return null;
      return this.replace(id, {
        name: patch.name ?? existing.name,
        description: patch.description !== undefined ? patch.description : existing.description,
        comparison: patch.comparison !== undefined ? patch.comparison : existing.comparison,
        minimum: patch.minimum !== undefined ? patch.minimum : existing.minimum,
        maximum: patch.maximum !== undefined ? patch.maximum : existing.maximum,
        uom: patch.uom !== undefined ? patch.uom : existing.uom,
        status: patch.status !== undefined ? patch.status : existing.status,
        last_updated_by:
          patch.last_updated_by !== undefined ? patch.last_updated_by : existing.last_updated_by,
      });
    },

    async delete(id) {
      const before = await this.findById(id);
      if (!before) return false;
      await db.query(`DELETE FROM ${table} WHERE id = :id`, { id });
      return true;
    },
  };
}
