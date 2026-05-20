import cors from "cors";
import express, { type Express } from "express";
import { cacheControl } from "./middleware/cacheControl.js";
import { errorHandler } from "./middleware/errorHandler.js";
import { createRulesRepository } from "./repositories/createRulesRepository.js";
import { createRulesRouter } from "./routes/rules.js";
import { RulesService } from "./services/rulesService.js";
import type { DataStoreMode } from "./config.js";
import { getConfig } from "./config.js";
import { createDataStore } from "./stores/createStore.js";
import type { DataStore } from "./stores/DataStore.js";

export interface AppDependencies {
  rulesService?: RulesService;
  store?: DataStore;
  dataStore?: DataStoreMode;
  aiBaseUrl?: string;
}

/**
 * Builds the Express application (routes + middleware) without listening on a port.
 * Use {@link createApp} in tests with injected dependencies; {@link src/index.ts} calls listen().
 */
export function createApp(deps: AppDependencies = {}): Express {
  const cfg = getConfig();
  const dataStore = deps.dataStore ?? cfg.dataStore;
  const store = deps.store ?? createDataStore(dataStore, cfg.databricks);
  const rulesService =
    deps.rulesService ??
    new RulesService(createRulesRepository(dataStore, cfg.databricks));
  const aiBaseUrl = deps.aiBaseUrl ?? cfg.aiBaseUrl;

  const app = express();
  app.use(cors({ origin: true, credentials: true }));
  app.use(express.json());
  app.use(cacheControl(cfg.cache.ttlSeconds));

  app.get("/health", (_req, res) => {
    void store
      .ping()
      .then((db) => {
        res.json({
          status: "ok",
          service: "backend-api",
          dataStore,
          store: store.label,
          database: db,
        });
      })
      .catch((err: unknown) => {
        res.status(500).json({ status: "error", message: String(err) });
      });
  });

  app.get("/api/config", (_req, res) => {
    res.json({
      dataStore,
      aiBaseUrl,
      cache: {
        enabled: cfg.cache.enabled,
        ttlSeconds: cfg.cache.ttlSeconds,
      },
    });
  });

  app.use("/api/rules", createRulesRouter(rulesService));
  app.use(errorHandler);

  return app;
}
