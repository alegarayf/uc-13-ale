import { TtlCache } from "../cache/TtlCache.js";
import type { Rule } from "../types/rule.js";
import type { RuleInsertPayload, RuleMutableFields } from "../types/rule.js";
import type { RulesRepository } from "./rulesRepository.js";

const LIST_KEY = "rules:all";

function idKey(id: number): string {
  return `rules:id:${id}`;
}

export interface CachingRulesRepositoryOptions {
  ttlMs: number;
}

/**
 * Decorator that caches read paths and invalidates on writes so Databricks
 * is not queried on every identical GET.
 */
export function createCachingRulesRepository(
  inner: RulesRepository,
  options: CachingRulesRepositoryOptions,
): RulesRepository {
  const listCache = new TtlCache<Rule[]>(options.ttlMs);
  const byIdCache = new TtlCache<Rule>(options.ttlMs);

  function invalidateList(): void {
    listCache.clear();
  }

  function invalidateId(id: number): void {
    byIdCache.delete(idKey(id));
    invalidateList();
  }

  function invalidateAll(): void {
    listCache.clear();
    byIdCache.clear();
  }

  return {
    async findAll() {
      const cached = listCache.get(LIST_KEY);
      if (cached) return cached;

      const rules = await inner.findAll();
      listCache.set(LIST_KEY, rules);
      for (const rule of rules) {
        byIdCache.set(idKey(rule.id), rule);
      }
      return rules;
    },

    async findById(id) {
      const cached = byIdCache.get(idKey(id));
      if (cached) return cached;

      const rule = await inner.findById(id);
      if (rule) {
        byIdCache.set(idKey(id), rule);
      }
      return rule;
    },

    async create(input: RuleInsertPayload) {
      const rule = await inner.create(input);
      invalidateAll();
      byIdCache.set(idKey(rule.id), rule);
      return rule;
    },

    async replace(id, fields: RuleMutableFields) {
      const rule = await inner.replace(id, fields);
      invalidateAll();
      if (rule) byIdCache.set(idKey(id), rule);
      return rule;
    },

    async update(id, patch: Partial<RuleMutableFields>) {
      const rule = await inner.update(id, patch);
      invalidateAll();
      if (rule) byIdCache.set(idKey(id), rule);
      return rule;
    },

    async delete(id) {
      const deleted = await inner.delete(id);
      if (deleted) {
        invalidateId(id);
      }
      return deleted;
    },
  };
}
