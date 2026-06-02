import type { DataStoreMode } from "../config.js";
import { getConfig } from "../config.js";
import { getSharedDatabricksClient } from "../db/databricksClient.js";
import type { DatabricksStoreConfig } from "../stores/databricksStore.js";
import { createCachingCompaniesRepository } from "./cachingCompaniesRepository.js";
import {
  createDatabricksCompaniesRepository,
  createMemoryCompaniesRepository,
  type CompaniesRepository,
} from "./companiesRepository.js";

export interface CreateCompaniesRepositoryOptions {
  cache?: boolean;
  cacheTtlMs?: number;
}

export function createCompaniesRepository(
  mode: DataStoreMode,
  databricks: DatabricksStoreConfig,
  options: CreateCompaniesRepositoryOptions = {},
): CompaniesRepository {
  const inner =
    mode === "databricks"
      ? createDatabricksCompaniesRepository(getSharedDatabricksClient(databricks))
      : createMemoryCompaniesRepository();

  const cfg = getConfig();
  const cacheEnabled = options.cache ?? cfg.cache.enabled;
  const ttlMs = options.cacheTtlMs ?? cfg.cache.ttlMs;

  if (cacheEnabled && ttlMs > 0) {
    return createCachingCompaniesRepository(inner, { ttlMs });
  }
  return inner;
}
