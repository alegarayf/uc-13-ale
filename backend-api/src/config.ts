import { loadEnv } from "./loadEnv.js";

export type DataStoreMode = "memory" | "databricks";

function normalizeDataStore(value: string | undefined): DataStoreMode {
  const v = (value ?? "memory").toLowerCase();
  if (v === "databricks") return "databricks";
  return "memory";
}

let loaded = false;
function loadEnvOnce(): void {
  if (loaded) return;
  loaded = true;
  loadEnv();
}

function parseCacheTtlSeconds(value: string | undefined): number {
  const n = Number(value ?? "60");
  if (!Number.isFinite(n) || n < 0) return 60;
  return Math.floor(n);
}

export function getConfig() {
  loadEnvOnce();
  const cacheTtlSeconds = parseCacheTtlSeconds(process.env.API_CACHE_TTL_SECONDS);
  return {
    port: Number(process.env.BACKEND_API_PORT) || 3001,
    dataStore: normalizeDataStore(process.env.DATA_STORE),
    cache: {
      enabled: cacheTtlSeconds > 0,
      ttlMs: cacheTtlSeconds * 1000,
      ttlSeconds: cacheTtlSeconds,
    },
    databricks: {
      serverHostname: process.env.DATABRICKS_SERVER_HOSTNAME ?? "",
      httpPath: process.env.DATABRICKS_HTTP_PATH ?? "",
      token: process.env.DATABRICKS_TOKEN ?? "",
      catalog: process.env.DATABRICKS_CATALOG ?? "",
      schema: process.env.DATABRICKS_SCHEMA ?? "",
    },
    aiBaseUrl: process.env.AI_API_BASE_URL ?? "http://localhost:8000",
  };
}
