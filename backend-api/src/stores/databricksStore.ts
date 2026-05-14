import type { DataStore } from "./DataStore.js";

export interface DatabricksStoreConfig {
  serverHostname: string;
  httpPath: string;
  token: string;
  catalog: string;
  schema: string;
}

/**
 * Placeholder for Databricks connectivity (SQL warehouse, Unity Catalog, etc.).
 * Wire the official Databricks SQL driver or SDK here when credentials are present.
 */
export function createDatabricksStore(cfg: DatabricksStoreConfig): DataStore {
  const missing: string[] = [];
  if (!cfg.serverHostname) missing.push("DATABRICKS_SERVER_HOSTNAME");
  if (!cfg.httpPath) missing.push("DATABRICKS_HTTP_PATH");
  if (!cfg.token) missing.push("DATABRICKS_TOKEN");

  return {
    label: "databricks",
    async ping() {
      if (missing.length) {
        return {
          ok: false,
          detail: `Missing env: ${missing.join(", ")}`,
        };
      }
      return {
        ok: true,
        detail: `catalog=${cfg.catalog || "(default)"} schema=${cfg.schema || "(default)"}`,
      };
    },
  };
}
