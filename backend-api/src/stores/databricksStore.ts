import { getSharedDatabricksClient } from "../db/databricksClient.js";
import type { DataStore } from "./DataStore.js";

export interface DatabricksStoreConfig {
  serverHostname: string;
  httpPath: string;
  token: string;
  catalog: string;
  schema: string;
}

export function createDatabricksStore(cfg: DatabricksStoreConfig): DataStore {
  const missing: string[] = [];
  if (!cfg.serverHostname) missing.push("DATABRICKS_SERVER_HOSTNAME");
  if (!cfg.httpPath) missing.push("DATABRICKS_HTTP_PATH");
  if (!cfg.token) missing.push("DATABRICKS_TOKEN");
  if (!cfg.catalog) missing.push("DATABRICKS_CATALOG");
  if (!cfg.schema) missing.push("DATABRICKS_SCHEMA");

  return {
    label: "databricks",
    async ping() {
      if (missing.length) {
        return {
          ok: false,
          detail: `Missing env: ${missing.join(", ")}`,
        };
      }
      try {
        await getSharedDatabricksClient(cfg).ping();
        return {
          ok: true,
          detail: `catalog=${cfg.catalog} schema=${cfg.schema}`,
        };
      } catch (err: unknown) {
        return {
          ok: false,
          detail: err instanceof Error ? err.message : String(err),
        };
      }
    },
  };
}
