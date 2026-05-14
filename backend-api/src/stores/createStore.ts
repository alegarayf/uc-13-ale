import type { DataStore } from "./DataStore.js";
import type { DataStoreMode } from "../config.js";
import { createDatabricksStore } from "./databricksStore.js";
import { createMemoryStore } from "./memoryStore.js";

export function createDataStore(
  mode: DataStoreMode,
  databricks: {
    serverHostname: string;
    httpPath: string;
    token: string;
    catalog: string;
    schema: string;
  },
): DataStore {
  if (mode === "databricks") {
    return createDatabricksStore(databricks);
  }
  return createMemoryStore();
}
