import { DBSQLClient } from "@databricks/sql";
import type { DatabricksStoreConfig } from "../stores/databricksStore.js";

type ConnectedClient = Awaited<ReturnType<DBSQLClient["connect"]>>;

export type QueryParams = Record<string, unknown>;

export interface DatabricksClient {
  ping(): Promise<void>;
  query<T extends Record<string, unknown> = Record<string, unknown>>(
    sql: string,
    params?: QueryParams,
  ): Promise<T[]>;
  close(): Promise<void>;
}

function missingDatabricksEnv(cfg: DatabricksStoreConfig): string[] {
  const missing: string[] = [];
  if (!cfg.serverHostname) missing.push("DATABRICKS_SERVER_HOSTNAME");
  if (!cfg.httpPath) missing.push("DATABRICKS_HTTP_PATH");
  if (!cfg.token) missing.push("DATABRICKS_TOKEN");
  if (!cfg.catalog) missing.push("DATABRICKS_CATALOG");
  if (!cfg.schema) missing.push("DATABRICKS_SCHEMA");
  return missing;
}

export function createDatabricksClient(cfg: DatabricksStoreConfig): DatabricksClient {
  const missing = missingDatabricksEnv(cfg);
  let connected: ConnectedClient | null = null;
  let connectPromise: Promise<ConnectedClient> | null = null;

  async function getClient(): Promise<ConnectedClient> {
    if (missing.length) {
      throw new Error(`Missing env: ${missing.join(", ")}`);
    }
    if (connected) return connected;
    if (!connectPromise) {
      const raw = new DBSQLClient();
      connectPromise = raw.connect({
        host: cfg.serverHostname,
        path: cfg.httpPath,
        token: cfg.token,
      });
    }
    connected = await connectPromise;
    return connected;
  }

  return {
    async ping() {
      await this.query("SELECT 1 AS ok");
    },

    async query<T extends Record<string, unknown> = Record<string, unknown>>(
      sql: string,
      params?: QueryParams,
    ): Promise<T[]> {
      const client = await getClient();
      const session = await client.openSession();
      try {
        const operation = await session.executeStatement(sql, {
          runAsync: true,
          maxRows: 10000,
          ...(params ? { namedParameters: params } : {}),
        });
        try {
          return (await operation.fetchAll()) as T[];
        } finally {
          await operation.close();
        }
      } finally {
        await session.close();
      }
    },

    async close() {
      if (connected) {
        await connected.close();
        connected = null;
        connectPromise = null;
      }
    },
  };
}

let sharedClient: DatabricksClient | null = null;

export function getSharedDatabricksClient(cfg: DatabricksStoreConfig): DatabricksClient {
  if (!sharedClient) {
    sharedClient = createDatabricksClient(cfg);
  }
  return sharedClient;
}

export function resetSharedDatabricksClient(): void {
  sharedClient = null;
}
