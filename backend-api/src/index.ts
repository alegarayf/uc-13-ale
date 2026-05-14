import cors from "cors";
import express from "express";
import { createDataStore } from "./stores/createStore.js";
import { getConfig } from "./config.js";

const cfg = getConfig();
const store = createDataStore(cfg.dataStore, cfg.databricks);

const app = express();
app.use(cors({ origin: true, credentials: true }));
app.use(express.json());

app.get("/health", (_req, res) => {
  void store
    .ping()
    .then((db) => {
      res.json({
        status: "ok",
        service: "backend-api",
        dataStore: cfg.dataStore,
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
    dataStore: cfg.dataStore,
    aiBaseUrl: cfg.aiBaseUrl,
  });
});

app.listen(cfg.port, () => {
  console.log(`backend-api listening on http://localhost:${cfg.port} (DATA_STORE=${cfg.dataStore})`);
});
