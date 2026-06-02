import type { DatabricksClient } from "../db/databricksClient.js";
import { rulesTableRef } from "../db/tableRef.js";
import {
  mapRowToRule,
  RULE_SELECT_COLUMNS,
} from "./ruleRowMapper.js";
import { Rule, type RuleInsertPayload, type RuleMutableFields } from "../types/rule.js";
import type { DatabricksStoreConfig } from "../stores/databricksStore.js";
import { nowTimestamp } from "../utils/timestamps.js";
import { SEED_AI_EMPLOYEE_HEADCOUNT } from "./rulesSeedData.js";

export interface RulesRepository {
  findAll(): Promise<Rule[]>;
  findById(id: number): Promise<Rule | null>;
  create(input: RuleInsertPayload): Promise<Rule>;
  replace(id: number, fields: RuleMutableFields): Promise<Rule | null>;
  update(id: number, patch: Partial<RuleMutableFields>): Promise<Rule | null>;
  delete(id: number): Promise<boolean>;
}

const SEED_TS = "2026-01-01T00:00:00.000Z";

const SEED_RULES: Rule[] = [
  new Rule({
    id: 1,
    ...SEED_AI_EMPLOYEE_HEADCOUNT,
    created_at: SEED_TS,
    updated_at: SEED_TS,
  }),
  new Rule({
    id: 2,
    name: "Geography",
    description: "Primary operating region for eligible companies.",
    status: "active",
    rule_source: "form",
    nl_prompt: null,
    nl_summary: null,
    rule_definition: null,
    python_source: null,
    python_entrypoint: null,
    created_at: SEED_TS,
    updated_at: SEED_TS,
    last_updated_by: "seed",
  }),
  new Rule({
    id: 3,
    name: "Growth mindset score",
    description: "Minimum qualitative score from partner review.",
    status: "inactive",
    rule_source: "form",
    nl_prompt: null,
    nl_summary: null,
    rule_definition: null,
    python_source: null,
    python_entrypoint: null,
    created_at: SEED_TS,
    updated_at: SEED_TS,
    last_updated_by: "seed",
  }),
];

function mergePatch(existing: Rule, patch: Partial<RuleMutableFields>): RuleMutableFields {
  return {
    name: patch.name ?? existing.name,
    description: patch.description !== undefined ? patch.description : existing.description,
    status: patch.status !== undefined ? patch.status : existing.status,
    rule_source: patch.rule_source !== undefined ? patch.rule_source : existing.rule_source,
    nl_prompt: patch.nl_prompt !== undefined ? patch.nl_prompt : existing.nl_prompt,
    nl_summary: patch.nl_summary !== undefined ? patch.nl_summary : existing.nl_summary,
    rule_definition:
      patch.rule_definition !== undefined ? patch.rule_definition : existing.rule_definition,
    python_source: patch.python_source !== undefined ? patch.python_source : existing.python_source,
    python_entrypoint:
      patch.python_entrypoint !== undefined
        ? patch.python_entrypoint
        : existing.python_entrypoint,
    last_updated_by:
      patch.last_updated_by !== undefined ? patch.last_updated_by : existing.last_updated_by,
  };
}

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
        created_at: existing.created_at,
        updated_at: nowTimestamp(),
        ...mergePatch(existing, patch),
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

  const insertColumns =
    "name, description, status, rule_source, nl_prompt, nl_summary, rule_definition, python_source, python_entrypoint, created_at, updated_at, last_updated_by";
  const insertValues =
    ":name, :description, :status, :rule_source, :nl_prompt, :nl_summary, :rule_definition, :python_source, :python_entrypoint, current_timestamp(), current_timestamp(), :last_updated_by";

  function insertParams(input: RuleInsertPayload) {
    return {
      name: input.name,
      description: input.description,
      status: input.status,
      rule_source: input.rule_source,
      nl_prompt: input.nl_prompt,
      nl_summary: input.nl_summary,
      rule_definition: input.rule_definition,
      python_source: input.python_source,
      python_entrypoint: input.python_entrypoint,
      last_updated_by: input.last_updated_by,
    };
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
        `INSERT INTO ${table} (${insertColumns}) VALUES (${insertValues})`,
        insertParams(input),
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
             status = :status,
             rule_source = :rule_source,
             nl_prompt = :nl_prompt,
             nl_summary = :nl_summary,
             rule_definition = :rule_definition,
             python_source = :python_source,
             python_entrypoint = :python_entrypoint,
             updated_at = current_timestamp(),
             last_updated_by = :last_updated_by
         WHERE id = :id`,
        { id, ...insertParams(fields) },
      );
      return this.findById(id);
    },

    async update(id, patch) {
      const existing = await this.findById(id);
      if (!existing) return null;
      return this.replace(id, mergePatch(existing, patch));
    },

    async delete(id) {
      const before = await this.findById(id);
      if (!before) return false;
      await db.query(`DELETE FROM ${table} WHERE id = :id`, { id });
      return true;
    },
  };
}
