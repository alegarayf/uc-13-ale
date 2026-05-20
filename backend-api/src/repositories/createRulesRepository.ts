import type { DataStoreMode } from "../config.js";
import { getConfig } from "../config.js";
import { getSharedDatabricksClient } from "../db/databricksClient.js";
import type { DatabricksStoreConfig } from "../stores/databricksStore.js";
import { createCachingRulesRepository } from "./cachingRulesRepository.js";
import {
  createDatabricksRulesRepository,
  createMemoryRulesRepository,
  type RulesRepository,
} from "./rulesRepository.js";

export interface CreateRulesRepositoryOptions {
  /** When true, wrap reads with a TTL cache (default from API_CACHE_TTL_SECONDS). */
  cache?: boolean;
  cacheTtlMs?: number;
}

export function createRulesRepository(
  mode: DataStoreMode,
  databricks: DatabricksStoreConfig,
  options: CreateRulesRepositoryOptions = {},
): RulesRepository {
  const inner =
    mode === "databricks"
      ? createDatabricksRulesRepository(getSharedDatabricksClient(databricks), databricks)
      : createMemoryRulesRepository();

  const cfg = getConfig();
  const cacheEnabled = options.cache ?? cfg.cache.enabled;
  const ttlMs = options.cacheTtlMs ?? cfg.cache.ttlMs;

  if (cacheEnabled && ttlMs > 0) {
    return createCachingRulesRepository(inner, { ttlMs });
  }
  return inner;
}
